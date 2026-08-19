"""The governed embodied bench, exposed as runs: environment, refusals, progress.

Every run here is driven through the real ``run_bench`` — the module under test is
the seam, not the physics, so replacing the driver would leave the ledger
injection and the event projection untested. What is injected is the *robot*: a
tracking fake with a servo's overshoot, which keeps the suite fast and free of a
GL context while the governance path stays entirely real. One test drives the
production subprocess worker against MuJoCo itself and skips when it is absent.

The behaviour these tests guard above all is the refusal path. A caller who
declares no guardian must get a real run whose preflight refuses and whose
refusal is recorded, not a client error: an API that rejected the request would
be answering the question the Safety Supervisor exists to answer.
"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from typing import Any, Optional, Sequence

import pytest
from fastapi.testclient import TestClient

from coworker.server import SessionManager, create_app
from coworker.server.embodied import (
    CAMERA_SLOT_PORTS,
    CANDIDATE_RATES_RPS,
    ENVELOPE_LIMITS,
    ENVIRONMENT_ID,
    GOAL_OFFSETS_RAD,
    EmbodiedFacade,
    probe_simulator,
)
from coworker.server.embodied_worker import run_embodied

TOKEN = "a" * 64
TERMINAL = {"done", "error", "cancelled"}

_HAS_MUJOCO = probe_simulator()["available"]
_JOINT_COUNT = len(GOAL_OFFSETS_RAD)


# -- a robot, without a simulator -------------------------------------------------


class FakeG1:
    """A tracking arm with a servo's overshoot, and the declared room facts.

    It answers every command exactly, so these tests are about the surface rather
    than about convergence, and reports a peak above the rate its setpoint
    spacing implies, which is the one physical fact the calibration ladder has to
    see. The supervision it reports is whatever the caller declared, because that
    passthrough is the thing under test: a fake that asserted a guardian would
    manufacture the precondition the refusal test is looking for.
    """

    is_real_robot = False

    def __init__(self, supervision: Any, control_frequency_hz: float, gain: float = 1.5):
        self._joints = tuple(f"joint_{index}" for index in range(_JOINT_COUNT))
        self._stand = (0.0,) * _JOINT_COUNT
        self._supervision = supervision
        self._frequency_hz = float(control_frequency_hz)
        self._gain = gain
        self.positions = self._stand
        self.published = 0
        self._time = 0.0
        self._peak = 0.0

    @property
    def joint_names(self) -> tuple[str, ...]:
        return self._joints

    @property
    def control_frequency_hz(self) -> float:
        return self._frequency_hz

    @property
    def stand_positions_rad(self) -> tuple[float, ...]:
        return self._stand

    def clock(self) -> float:
        return self._time

    def reset(self, joint_offsets_rad: Optional[Sequence[float]] = None) -> None:
        offsets = tuple(joint_offsets_rad or (0.0,) * _JOINT_COUNT)
        self.positions = tuple(
            base + offset for base, offset in zip(self._stand, offsets)
        )
        self._peak = 0.0
        self._time = 0.0

    def read_state(self):
        from vegapunk.embodied.runtime import RobotState

        peak = self._peak
        self._peak = 0.0
        return RobotState(
            joint_positions_rad=self.positions,
            joint_velocity_rps=(peak,) * len(self.positions),
            end_effector_force_n=1.0,
            end_effector_position_m=(0.1, 0.0, 0.8),
            guardian_present=self._supervision.guardian_present,
            estop_engaged=self._supervision.estop_engaged,
            estop_reachable=self._supervision.estop_reachable,
            workspace_clear=self._supervision.workspace_clear,
            age_s=0.01,
        )

    def command_joint_positions(self, positions_rad: Sequence[float]) -> None:
        target = tuple(float(value) for value in positions_rad)
        travelled = max(
            (abs(new - old) for old, new in zip(self.positions, target)), default=0.0
        )
        self._peak = max(self._peak, travelled * self._frequency_hz * self._gain)
        self._time += 1.0 / self._frequency_hz
        self.positions = target

    def hold(self) -> None:
        pass

    def publish_frames(self, bus: object) -> None:
        self.published += 1

    def describe_configuration(
        self,
        environment_id: str,
        end_effector: str,
        control_authority: str,
        represented_camera_keys: Sequence[str] = (),
    ):
        from vegapunk.embodied.fidelity import SimulatedConfiguration

        return SimulatedConfiguration(
            environment_id=environment_id,
            is_real_robot=False,
            control_frequency_hz=self._frequency_hz,
            controlled_joint_names=self._joints,
            end_effector=end_effector,
            control_authority=control_authority,
            represented_camera_keys=tuple(represented_camera_keys),
        )


def fake_robot_bench(request, plan, admission, trajectories, milestones, frames):
    """The production driver with the simulator swapped for the fake arm."""
    from vegapunk.embodied.bench import run_bench
    from vegapunk.embodied.simulation import SimulatedSupervision

    robot = FakeG1(
        SimulatedSupervision(**request["declared_supervision"]),
        request["control_frequency_hz"],
    )
    return run_bench(
        robot,
        plan,
        frames=frames,
        admission=admission,
        trajectories=trajectories,
        milestones=milestones,
    )


@pytest.fixture
def facade(tmp_path) -> EmbodiedFacade:
    return EmbodiedFacade(
        tmp_path / "state",
        runner=lambda run_dir: run_embodied(run_dir, driver=fake_robot_bench),
    )


@pytest.fixture
def client(tmp_path, monkeypatch, facade):
    monkeypatch.setenv("COWORKER_API_TOKEN", TOKEN)
    manager = SessionManager(data_dir=tmp_path / "session-state")
    app = create_app(manager)
    # Same facade, same worker core: only the robot is injected.
    app.state.embodied = facade
    with TestClient(app) as running:
        yield running


def _headers() -> dict[str, str]:
    return {"X-OpenWorker-Token": TOKEN}


SUPERVISED = {
    "guardian_present": True,
    "estop_engaged": False,
    "estop_reachable": True,
    "workspace_clear": True,
}


def _await_terminal(source, run_id: str, timeout: float = 60.0) -> dict[str, Any]:
    """Poll one run until it reaches a terminal state, or fail loudly."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        snapshot = (
            source.run(run_id)
            if isinstance(source, EmbodiedFacade)
            else source.get(f"/v1/embodied/runs/{run_id}", headers=_headers()).json()
        )
        if snapshot["state"] in TERMINAL:
            return snapshot
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} never reached a terminal state")


# -- the environment --------------------------------------------------------------


def test_the_environment_describes_the_bench_without_building_a_robot(client):
    assert client.get("/v1/embodied/environment").status_code == 401

    document = client.get("/v1/embodied/environment", headers=_headers()).json()

    assert document["environment_id"] == ENVIRONMENT_ID
    assert document["joint_count"] == len(document["joints"]) == _JOINT_COUNT
    assert document["joints"][1] == "left_shoulder_roll_joint"
    assert document["goal_offsets_rad"] == list(GOAL_OFFSETS_RAD)
    assert document["candidate_rates_rps"] == list(CANDIDATE_RATES_RPS)
    assert document["velocity_budget_rps"] == pytest.approx(
        ENVELOPE_LIMITS["max_joint_velocity_rps"] * document["velocity_margin"]
    )
    assert document["envelope"]["workspace_bounds_m"] == [[-1, 1], [-1, 1], [0, 2]]
    assert document["skill"]["version_id"] == "raise_left_shoulder@1"
    assert document["skill"]["kind"] == "deterministic"
    assert [stage["stage"] for stage in document["ladder"]] == [
        "policy_evaluation",
        "offline_replay",
        "shadow_mode",
        "hardware_supervised",
    ]
    assert [stage["simulated"] for stage in document["ladder"]] == [
        True,
        True,
        False,
        False,
    ]
    assert document["minimum_stage_attempts"] == 10
    assert document["minimum_stage_success_rate"] == 0.9
    assert document["approval_validity_hours"] == 8
    assert document["stage_offsets_rad"] == {
        "policy_evaluation": 0.01,
        "offline_replay": 0.05,
    }
    assert len(document["unrepresentable"]) == 4
    assert [slot["port"] for slot in document["camera_slots"]] == [60001, 60002, 60003]
    assert document["camera_slots"][0] == {
        "id": "head",
        "label": "Head stereo",
        "width": 1280,
        "height": 480,
        "port": 60001,
    }


def test_the_declaration_matches_the_bench_script(client):
    """The server's defaults are the script's, not a second set of numbers."""
    script = (
        Path(__file__).resolve().parents[4] / "scripts" / "run_embodied_bench.py"
    ).read_text(encoding="utf-8")

    assert f'ENVIRONMENT_ID = "{ENVIRONMENT_ID}"' in script
    assert f"CANDIDATE_RATES_RPS = {CANDIDATE_RATES_RPS}" in script
    assert f"GOAL_OFFSETS_RAD = {GOAL_OFFSETS_RAD}" in script
    for value in ENVELOPE_LIMITS.values():
        if isinstance(value, float):
            assert str(value) in script


def test_the_simulator_is_described_rather_than_assumed(client):
    document = client.get("/v1/embodied/environment", headers=_headers()).json()
    simulator = document["simulator"]

    assert simulator["available"] is _HAS_MUJOCO
    if _HAS_MUJOCO:
        assert simulator["detail"].startswith("mujoco ")
        assert simulator["reason"] is None
        assert simulator["scene_path"].endswith("scene_with_hands.xml")
    else:
        assert simulator["reason"]


# -- a full run -------------------------------------------------------------------


def test_a_supervised_run_climbs_both_stages_and_names_what_blocks_hardware(client):
    created = client.post(
        "/v1/embodied/runs",
        headers=_headers(),
        json={"declared_supervision": SUPERVISED},
    )
    assert created.status_code == 201
    queued = created.json()["run"]
    assert queued["state"] in {"queued", "running"}
    assert queued["request"]["attempts_per_stage"] == 10
    assert queued["request"]["control_frequency_hz"] == 50.0
    assert queued["request"]["watch"] is False
    assert queued["preview"] == {"watching": False, "host": None, "camera_slots": []}

    run = _await_terminal(client, queued["run_id"])

    assert run["state"] == "done"
    assert run["error"] is None
    assert run["halted"] == "completed"
    assert run["completed"] is True
    assert run["environment_id"] == ENVIRONMENT_ID
    assert run["skill_version_id"] == "raise_left_shoulder@1"
    assert run["embodiment_digest"]
    assert run["started_at"] and run["finished_at"]

    # The two facts a completed simulation leaves standing between it and a
    # person next to a moving robot.
    assert run["blocking_hardware"] == [
        "stage shadow_mode has no evidence for this configuration",
        "supervised hardware execution requires a human approval",
    ]
    assert run["hardware_decision"]["target_stage"] == "hardware_supervised"
    assert run["hardware_decision"]["admitted"] is False
    assert run["hardware_decision"]["blocking_reasons"] == run["blocking_hardware"]

    calibration = run["calibration"]
    assert [item["commanded_rate_rps"] for item in calibration["measurements"]] == list(
        CANDIDATE_RATES_RPS
    )
    assert all(item["fits"] for item in calibration["measurements"])
    assert calibration["admitted"]["commanded_rate_rps"] == max(CANDIDATE_RATES_RPS)
    assert calibration["budget_rps"] == pytest.approx(1.2)
    assert calibration["margin"] == 0.8

    assert run["goal"]["satisfies"] == ["at_reviewed_pose"]
    assert len(run["goal"]["target_joint_positions_rad"]) == _JOINT_COUNT
    assert run["goal"]["tolerance_rad"] >= 0.02
    assert run["required_duration_s"] > 0

    assert [stage["stage"] for stage in run["stages"]] == [
        "policy_evaluation",
        "offline_replay",
    ]
    for stage in run["stages"]:
        assert stage["planned_attempts"] == 10
        assert stage["executed_attempts"] == 10
        assert stage["successes"] == 10
        assert stage["completed"] is True
        assert stage["halted"] == "completed"
        assert stage["next_stage_admitted"] is True
        assert stage["next_stage_blocking_reasons"] == []
        assert len(stage["attempts"]) == 10
        assert stage["attempts"][0]["index"] == 0
        assert {attempt["outcome"] for attempt in stage["attempts"]} == {"succeeded"}
        assert stage["evidence"]["success_rate"] == 1.0
        assert stage["evidence"]["safety_violations"] == 0
        assert stage["fidelity"]["represents"] is True
        assert len(stage["fidelity"]["unrepresented"]) == 4
        assert len(stage["scope"]) == 3
    assert run["stages"][0]["next_stage"] == "offline_replay"
    assert run["stages"][1]["next_stage"] == "shadow_mode"


def _assert_causal_order(events: list[dict], stages: tuple[str, ...]) -> None:
    """Pin the full causal order of one run's event log.

    Written as positions rather than as a single expected list so that a failure
    names the pair of events that inverted, and so a run with a different number
    of attempts is checked by the same assertions.
    """
    types = [event["type"] for event in events]

    # The sequence is the GUI's incremental cursor: a gap would make an event
    # unreachable, a duplicate would render one twice.
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))

    def positions(kind: str, stage: str | None = None) -> list[int]:
        return [
            index
            for index, event in enumerate(events)
            if event["type"] == kind
            and (stage is None or event.get("stage") == stage)
        ]

    assert types[0] == "run_started"
    assert types[-1] == "run_halted"

    measured = positions("calibration_measured")
    admitted = positions("calibration_admitted")
    attempts = positions("attempt_recorded")
    goals = positions("goal_derived")
    assert measured and len(admitted) == 1

    # Nothing was attempted before the calibration that authorised it.
    assert max(measured) < admitted[0]
    if attempts:
        assert admitted[0] < attempts[0]
    assert len(goals) == 1
    assert admitted[0] < goals[0]

    starts = positions("stage_started")
    assert starts and goals[0] < starts[0]

    previous_close: int | None = None
    for stage in stages:
        started = positions("stage_started", stage)
        completed = positions("stage_completed", stage)
        stage_attempts = positions("attempt_recorded", stage)
        assert len(started) == 1, f"{stage} started {len(started)} times"
        assert len(completed) == 1, f"{stage} closed {len(completed)} times"
        # The stage opens, its attempts land inside it, and it closes.
        assert all(started[0] < index < completed[0] for index in stage_attempts)
        # A stage closes before the next one opens.
        if previous_close is not None:
            assert previous_close < started[0]
        previous_close = completed[0]

    # Both stage names are accounted for: no stage event belongs to a stage the
    # caller did not name.
    assert {event["stage"] for event in events if "stage" in event} == set(stages)

    # The whole run's verdicts come last, in that order.
    tail = types[max(positions("stage_completed")) + 1 :]
    assert tail == ["hardware_decision", "run_halted"] or tail == ["run_halted"]


def test_a_run_journals_every_attempt_as_the_ledger_gains_it(client):
    created = client.post(
        "/v1/embodied/runs",
        headers=_headers(),
        json={"declared_supervision": SUPERVISED},
    )
    run_id = created.json()["run"]["run_id"]
    _await_terminal(client, run_id)

    page = client.get(
        f"/v1/embodied/runs/{run_id}/events", headers=_headers()
    ).json()
    events = page["events"]
    types = [event["type"] for event in events]

    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
    assert page["latest_sequence"] == len(events)
    assert all(event["at"] for event in events)
    assert types[0] == "run_started"
    assert types[-1] == "run_halted"

    assert types.count("stage_started") == 2
    assert types.count("attempt_recorded") == 20
    assert types.count("stage_completed") == 2
    assert types.count("calibration_measured") == len(CANDIDATE_RATES_RPS)
    assert types.count("calibration_admitted") == 1
    assert types.count("goal_derived") == 1
    assert types.count("hardware_decision") == 1

    started = [event for event in events if event["type"] == "stage_started"]
    assert [event["stage"] for event in started] == [
        "policy_evaluation",
        "offline_replay",
    ]
    assert [event["max_offset_rad"] for event in started] == [0.01, 0.05]
    assert all(event["planned_attempts"] == 10 for event in started)

    attempts = [event for event in events if event["type"] == "attempt_recorded"]
    assert [event["index"] for event in attempts[:10]] == list(range(10))
    assert [event["index"] for event in attempts[10:]] == list(range(10))
    assert {event["outcome"] for event in attempts} == {"succeeded"}
    assert all(event["abort_cause"] is None for event in attempts)
    assert all(event["observations"] > 0 for event in attempts)

    # The log must state the run in the order the run happened. This product's
    # claim is that the command rate was measured rather than chosen, so a log
    # showing attempts before the measurement that authorised them contradicts
    # the claim it exists to evidence.
    _assert_causal_order(events, stages=("policy_evaluation", "offline_replay"))

    halted = events[-1]
    assert halted["halted"] == "completed"
    assert halted["completed"] is True
    assert len(halted["blocking_hardware"]) == 2


def test_events_page_from_a_cursor(client):
    created = client.post(
        "/v1/embodied/runs",
        headers=_headers(),
        json={"declared_supervision": SUPERVISED},
    )
    run_id = created.json()["run"]["run_id"]
    _await_terminal(client, run_id)

    whole = client.get(
        f"/v1/embodied/runs/{run_id}/events", headers=_headers()
    ).json()
    latest = whole["latest_sequence"]

    tail = client.get(
        f"/v1/embodied/runs/{run_id}/events?after=5", headers=_headers()
    ).json()
    assert [event["seq"] for event in tail["events"]] == list(range(6, latest + 1))
    assert tail["latest_sequence"] == latest

    exhausted = client.get(
        f"/v1/embodied/runs/{run_id}/events?after={latest}", headers=_headers()
    ).json()
    assert exhausted["events"] == []
    assert exhausted["latest_sequence"] == latest

    # A cursor from the future is a cursor, not an error: nothing is newer.
    ahead = client.get(
        f"/v1/embodied/runs/{run_id}/events?after={latest + 500}", headers=_headers()
    ).json()
    assert ahead["events"] == []


# -- the refusal path -------------------------------------------------------------


def test_an_undeclared_guardian_produces_a_real_refusal_not_a_client_error(client):
    """The product: the supervisor refuses, and the refusal is on the record."""
    created = client.post(
        "/v1/embodied/runs",
        headers=_headers(),
        json={"declared_supervision": {**SUPERVISED, "guardian_present": False}},
    )
    assert created.status_code == 201

    run = _await_terminal(client, created.json()["run"]["run_id"])

    assert run["state"] == "done"
    assert run["error"] is None
    assert run["request"]["declared_supervision"]["guardian_present"] is False

    # The run happened: it calibrated, derived a goal, and then the governed loop
    # refused the first attempt.
    assert run["calibration"]["admitted"] is not None
    assert run["goal"] is not None
    assert run["halted"] == "stage_incomplete"
    assert run["completed"] is False

    stage = run["stages"][0]
    assert stage["stage"] == "policy_evaluation"
    assert stage["completed"] is False
    assert stage["halted"] == "refused"
    assert stage["executed_attempts"] == 0
    attempt = stage["attempts"][0]
    assert attempt["outcome"] == "refused"
    assert any("guardian_present" in finding for finding in attempt["findings"])
    assert stage["next_stage_admitted"] is False
    assert run["hardware_decision"] is None
    assert run["blocking_hardware"] == [run["halt_detail"]]

    events = client.get(
        f"/v1/embodied/runs/{run['run_id']}/events", headers=_headers()
    ).json()["events"]
    refusals = [
        event
        for event in events
        if event["type"] == "attempt_recorded" and event["outcome"] == "refused"
    ]
    assert len(refusals) == 1
    assert refusals[0]["observations"] == 0


def test_a_refused_run_journals_its_calibration_before_its_one_attempt(client):
    """A refusal degrades honestly: it reports the phases that ran, and no more.

    The run really calibrated and really derived a goal, so both are on the
    record; the governed loop then refused the first attempt, so
    ``policy_evaluation`` closes after exactly one attempt and ``offline_replay``
    never opens. No event is invented for a phase that never ran.
    """
    created = client.post(
        "/v1/embodied/runs",
        headers=_headers(),
        json={"declared_supervision": {**SUPERVISED, "guardian_present": False}},
    )
    run_id = created.json()["run"]["run_id"]
    _await_terminal(client, run_id)

    events = client.get(
        f"/v1/embodied/runs/{run_id}/events", headers=_headers()
    ).json()["events"]
    types = [event["type"] for event in events]

    _assert_causal_order(events, stages=("policy_evaluation",))

    assert types.count("calibration_measured") == len(CANDIDATE_RATES_RPS)
    assert types.count("calibration_admitted") == 1
    assert types.count("goal_derived") == 1
    assert types.count("stage_started") == 1
    assert types.count("attempt_recorded") == 1
    assert types.count("stage_completed") == 1
    # Nothing opened supervised hardware, so no decision was evaluated.
    assert types.count("hardware_decision") == 0

    attempt = next(event for event in events if event["type"] == "attempt_recorded")
    assert attempt["outcome"] == "refused"
    assert attempt["stage"] == "policy_evaluation"

    completed = next(event for event in events if event["type"] == "stage_completed")
    assert completed["stage"] == "policy_evaluation"
    assert completed["halted"] == "refused"
    assert completed["executed_attempts"] == 0

    assert events[-1]["halted"] == "stage_incomplete"


def test_the_journal_reads_the_whole_milestone_vocabulary(client):
    """The worker mirrors the bench's milestone names; a rename must not drift.

    The journal switches on these strings and would silently skip a fact whose
    name changed, so the mirror is pinned to the bench's own vocabulary here
    rather than discovered by a missing event in production.
    """
    from vegapunk.embodied import bench

    from coworker.server import embodied_worker

    mirrored = {
        embodied_worker._MILESTONE_CALIBRATION,
        embodied_worker._MILESTONE_GOAL,
        embodied_worker._MILESTONE_STAGE,
        embodied_worker._MILESTONE_HARDWARE_DECISION,
    }
    assert mirrored == set(bench.BENCH_MILESTONES)


def test_an_engaged_estop_is_also_run_rather_than_rejected(client):
    created = client.post(
        "/v1/embodied/runs",
        headers=_headers(),
        json={"declared_supervision": {**SUPERVISED, "estop_engaged": True}},
    )
    assert created.status_code == 201

    run = _await_terminal(client, created.json()["run"]["run_id"])
    assert run["state"] == "done"
    assert run["stages"][0]["attempts"][0]["outcome"] == "refused"


# -- what the surface refuses ------------------------------------------------------


def test_too_few_attempts_cannot_open_anything(client):
    response = client.post(
        "/v1/embodied/runs",
        headers=_headers(),
        json={"declared_supervision": SUPERVISED, "attempts_per_stage": 5},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "cannot open anything" in detail["message"]
    assert detail["violations"] == []


def test_supervision_must_be_declared_fact_by_fact(client):
    response = client.post(
        "/v1/embodied/runs",
        headers=_headers(),
        json={"declared_supervision": {"guardian_present": True}},
    )
    assert response.status_code == 422
    paths = {item["path"] for item in response.json()["detail"]["violations"]}
    assert paths == {
        "declared_supervision.estop_engaged",
        "declared_supervision.estop_reachable",
        "declared_supervision.workspace_clear",
    }


def test_a_run_needs_a_supervision_declaration_at_all(client):
    response = client.post("/v1/embodied/runs", headers=_headers(), json={})
    assert response.status_code == 422
    assert (
        response.json()["detail"]["violations"][0]["path"] == "declared_supervision"
    )


def test_a_nonpositive_cadence_is_refused(client):
    response = client.post(
        "/v1/embodied/runs",
        headers=_headers(),
        json={"declared_supervision": SUPERVISED, "control_frequency_hz": 0},
    )
    assert response.status_code == 422
    assert (
        response.json()["detail"]["violations"][0]["path"] == "control_frequency_hz"
    )


def test_a_second_run_is_a_conflict_rather_than_a_queue(client):
    first = client.post(
        "/v1/embodied/runs",
        headers=_headers(),
        json={"declared_supervision": SUPERVISED},
    )
    assert first.status_code == 201
    second = client.post(
        "/v1/embodied/runs",
        headers=_headers(),
        json={"declared_supervision": SUPERVISED},
    )
    assert second.status_code == 409
    assert "still running" in second.json()["detail"]

    _await_terminal(client, first.json()["run"]["run_id"])

    # Once the scene is free, the next run is accepted.
    third = client.post(
        "/v1/embodied/runs",
        headers=_headers(),
        json={"declared_supervision": SUPERVISED},
    )
    assert third.status_code == 201
    _await_terminal(client, third.json()["run"]["run_id"])


def test_unknown_runs_are_not_found(client):
    for path in (
        "/v1/embodied/runs/deadbeef",
        f"/v1/embodied/runs/{'0' * 32}",
        f"/v1/embodied/runs/{'0' * 32}/events",
    ):
        assert client.get(path, headers=_headers()).status_code == 404
    assert (
        client.post(
            f"/v1/embodied/runs/{'0' * 32}/cancel", headers=_headers()
        ).status_code
        == 404
    )


def test_runs_are_listed_newest_first(client):
    identifiers = []
    for _ in range(2):
        created = client.post(
            "/v1/embodied/runs",
            headers=_headers(),
            json={"declared_supervision": SUPERVISED},
        )
        run_id = created.json()["run"]["run_id"]
        identifiers.append(run_id)
        _await_terminal(client, run_id)

    listed = client.get("/v1/embodied/runs", headers=_headers()).json()["runs"]
    assert [run["run_id"] for run in listed] == list(reversed(identifiers))


# -- terminal state is the run's own fact -----------------------------------------


def test_a_worker_that_could_not_be_started_reconciles_to_error(facade):
    """A runner that raises is the run's failure, not a run stuck at running."""

    def refuse(run_dir: Path) -> None:
        raise OSError("no interpreter")

    facade._runner = refuse
    run = facade.start_run({"declared_supervision": SUPERVISED})
    run = _await_terminal(facade, run["run_id"], timeout=10.0)

    assert run["state"] == "error"
    assert "could not be run" in (run["error"] or "")
    assert facade.events(run["run_id"])["events"][-1]["type"] == "run_failed"


def test_a_worker_that_never_lands_a_state_reconciles_to_error(facade):
    """A worker that returns having written nothing must still settle the run.

    This is the SIGKILL shape seen from the sidecar: the driver returned, only
    the worker writes ``state.json``, and nothing terminal ever arrived.
    """
    facade._runner = lambda run_dir: None  # a worker that produced nothing
    run = facade.start_run({"declared_supervision": SUPERVISED})
    run = _await_terminal(facade, run["run_id"], timeout=10.0)

    assert run["state"] == "error"
    assert "stopped without finishing" in (run["error"] or "")


def test_a_run_whose_process_vanished_is_settled_from_its_pid(facade, tmp_path):
    def vanish(run_dir: Path) -> None:
        # A pid that cannot be alive: the state the worker would have replaced
        # never arrives, exactly as after a SIGKILL or a simulator crash.
        from coworker.server.embodied import _atomic_write_json

        _atomic_write_json(
            run_dir / "state.json",
            {"state": "running", "pid": 2**22 - 1, "started_at": None},
        )

    facade._runner = vanish
    run = facade.start_run({"declared_supervision": SUPERVISED})
    run = _await_terminal(facade, run["run_id"], timeout=10.0)

    assert run["state"] == "error"
    assert "stopped without finishing" in (run["error"] or "")
    events = facade.events(run["run_id"])["events"]
    assert events[-1]["type"] == "run_failed"


def test_cancelling_a_queued_run_settles_it_without_running_anything(facade):
    started = {"seen": False}

    def slow(run_dir: Path) -> None:
        started["seen"] = True
        run_embodied(run_dir, driver=fake_robot_bench)

    facade._runner = slow
    run = facade.start_run({"declared_supervision": SUPERVISED})
    cancelled = facade.cancel(run["run_id"])

    assert cancelled["state"] in {"cancelled", "running", "done"}
    settled = _await_terminal(facade, run["run_id"], timeout=30.0)
    assert settled["state"] in {"cancelled", "done"}


def test_cancelling_an_unknown_run_is_a_lookup_error(facade):
    with pytest.raises(KeyError):
        facade.cancel("0" * 32)


# -- camera signalling -------------------------------------------------------------
#
# The robot's image service serves HTTPS with a self-signed certificate carrying no
# subjectAltName. No browser can be taught to trust it, so the page cannot perform
# the WebRTC offer/answer exchange itself and the sidecar relays it. These tests
# guard the two things that makes true: that the relay reaches only a robot, and
# that it stays a signalling relay rather than a general-purpose proxy.


class FakeCameraService:
    """Stands in for the robot's aiohttp image service, recording what it was asked."""

    def __init__(self, status: int = 200, payload: Any = None):
        self.status = status
        self.payload = {"sdp": "answer-sdp", "type": "answer"} if payload is None else payload
        self.calls: list[tuple[str, Any]] = []

    def client(self, **kwargs):
        service = self

        class Client:
            def __init__(self):
                self.kwargs = kwargs

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def post(self, url, json=None):
                service.calls.append((url, json))

                class Response:
                    status_code = service.status

                    def json(self_inner):
                        if isinstance(service.payload, Exception):
                            raise service.payload
                        return service.payload

                return Response()

        return Client()


OFFER = {"sdp": "v=0\r\n", "type": "offer"}


def test_a_camera_offer_is_relayed_to_the_robot_and_only_the_answer_returns(
    client, monkeypatch
):
    service = FakeCameraService()
    monkeypatch.setattr("httpx.Client", service.client)

    response = client.post(
        "/v1/embodied/cameras/head/offer",
        json={"host": "192.168.123.164", "offer": OFFER},
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"sdp": "answer-sdp", "type": "answer"}
    url, body = service.calls[0]
    assert url == "https://192.168.123.164:60001/offer"
    assert body == {"sdp": OFFER["sdp"], "type": "offer"}


def test_each_pane_is_relayed_to_its_own_fixed_camera_port(client, monkeypatch):
    service = FakeCameraService()
    monkeypatch.setattr("httpx.Client", service.client)

    for slot in ("head", "leftWrist", "rightWrist"):
        client.post(
            f"/v1/embodied/cameras/{slot}/offer",
            json={"host": "192.168.123.164", "offer": OFFER},
            headers=_headers(),
        )

    assert [url for url, _ in service.calls] == [
        "https://192.168.123.164:60001/offer",
        "https://192.168.123.164:60002/offer",
        "https://192.168.123.164:60003/offer",
    ]


def test_the_relayed_ports_are_the_ports_the_simulation_previews_on():
    """The mirrored literal cannot drift from the simulation's own declaration."""
    if not _HAS_MUJOCO:
        pytest.skip("the vegapunk simulation tree is not importable here")
    import importlib

    simulation = importlib.import_module("vegapunk.embodied.simulation")
    assert CAMERA_SLOT_PORTS == {
        slot.slot_id: slot.preview_port for slot in simulation.CAMERA_SLOTS.values()
    }


def test_the_relay_refuses_a_public_address(client, monkeypatch):
    service = FakeCameraService()
    monkeypatch.setattr("httpx.Client", service.client)

    response = client.post(
        "/v1/embodied/cameras/head/offer",
        json={"host": "93.184.216.34", "offer": OFFER},
        headers=_headers(),
    )

    assert response.status_code == 422
    assert "private-network" in response.json()["detail"]
    assert service.calls == []


def test_the_relay_refuses_a_hostname_rather_than_resolving_it(client, monkeypatch):
    """A name that resolves privately once can resolve anywhere later."""
    service = FakeCameraService()
    monkeypatch.setattr("httpx.Client", service.client)

    response = client.post(
        "/v1/embodied/cameras/head/offer",
        json={"host": "robot.internal", "offer": OFFER},
        headers=_headers(),
    )

    assert response.status_code == 422
    assert "literal address" in response.json()["detail"]
    assert service.calls == []


def test_the_relay_reaches_only_the_known_camera_panes(client, monkeypatch):
    service = FakeCameraService()
    monkeypatch.setattr("httpx.Client", service.client)

    response = client.post(
        "/v1/embodied/cameras/chest/offer",
        json={"host": "192.168.123.164", "offer": OFFER},
        headers=_headers(),
    )

    assert response.status_code == 404
    assert service.calls == []


def test_an_offer_without_a_description_is_refused(client, monkeypatch):
    service = FakeCameraService()
    monkeypatch.setattr("httpx.Client", service.client)

    response = client.post(
        "/v1/embodied/cameras/head/offer",
        json={"host": "192.168.123.164", "offer": {"type": "offer"}},
        headers=_headers(),
    )

    assert response.status_code == 422
    assert service.calls == []


def test_a_camera_that_refuses_the_offer_is_reported_as_the_robot_failing(
    client, monkeypatch
):
    service = FakeCameraService(status=500)
    monkeypatch.setattr("httpx.Client", service.client)

    response = client.post(
        "/v1/embodied/cameras/head/offer",
        json={"host": "192.168.123.164", "offer": OFFER},
        headers=_headers(),
    )

    assert response.status_code == 502
    assert "refused the offer" in response.json()["detail"]


def test_an_unreachable_camera_is_a_timeout_not_a_server_error(client, monkeypatch):
    import httpx

    def refuse(**kwargs):
        raise AssertionError("the client should not be constructed for this test")

    class Failing:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, json=None):
            raise httpx.ConnectError("no route to host")

    monkeypatch.setattr("httpx.Client", Failing)

    response = client.post(
        "/v1/embodied/cameras/head/offer",
        json={"host": "192.168.123.99", "offer": OFFER},
        headers=_headers(),
    )

    assert response.status_code == 504
    assert "did not answer" in response.json()["detail"]


def test_camera_signalling_requires_the_sidecar_token(client):
    assert (
        client.post(
            "/v1/embodied/cameras/head/offer",
            json={"host": "192.168.123.164", "offer": OFFER},
        ).status_code
        == 401
    )


# -- the real thing ----------------------------------------------------------------


@pytest.mark.skipif(
    not _HAS_MUJOCO, reason="MuJoCo or the G1 MJCF scene is not available"
)
def test_the_production_worker_drives_the_real_simulated_g1(tmp_path):
    """One run through the shipped path: subprocess, MuJoCo, EGL, real physics."""
    facade = EmbodiedFacade(tmp_path / "state")  # no injected runner
    run = facade.start_run({"declared_supervision": SUPERVISED})
    run = _await_terminal(facade, run["run_id"], timeout=300.0)

    assert run["state"] == "done", run["error"]
    assert run["halted"] == "completed"
    assert run["blocking_hardware"] == [
        "stage shadow_mode has no evidence for this configuration",
        "supervised hardware execution requires a human approval",
    ]
    assert run["embodiment_digest"] == "e1a2e469f21c000f"
    assert len(run["stages"]) == 2
    assert all(stage["successes"] == 10 for stage in run["stages"])

    types = [event["type"] for event in facade.events(run["run_id"])["events"]]
    assert types.count("attempt_recorded") == 20
    assert types[-1] == "run_halted"
