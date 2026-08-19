"""Process entry for one governed embodied bench run.

The worker exists because of what the simulator is. ``SimulatedG1`` binds a
MuJoCo model, a data buffer and an EGL renderer to the thread that constructs it,
so the bench must own a thread; and a native GL context that can abort the
process must not share a process with the sidecar's control plane. Running the
bench here makes a simulator crash the run's failure rather than the desktop's,
and makes cancellation a process kill, which is the only thing that stops a
blocking native call.

It is a driver and not a judge. Every verdict it writes down was produced by the
module that owns it: ``run_bench`` decides what halted, the campaigns decide what
each stage opened, the ``SafetySupervisor`` decides whether a declared
supervision permits motion at all. The worker's own contribution is the run's
durable record.

Progress comes from the ledgers rather than from a callback. ``run_bench``
accepts the ``AdmissionLedger``, the ``TrajectoryLedger`` and the
``BenchMilestones`` it would otherwise create, so the worker holds all three and
a journal thread reads them as they fill. The ledger is the run's record of fact;
a callback would be a second, weaker account of the same events, and the two
could disagree.

Two ledgers, one story. The attempts arrive in the trajectory ledger and
everything else -- the calibration, the goal, each closed stage, the hardware
decision -- arrives in the milestone ledger, and each milestone carries the
number of attempts that preceded it. The journal merges on that count rather than
on a clock, so the event log states the run in the order the run happened: the
measurement that authorised a rate is on the record before the attempts it
authorised, and a stage closes before the next one opens.

What remains genuinely unobservable until the end is ``run_halted``: which halt a
run stopped on is ``run_bench``'s own verdict, produced as it returns.

Security, when a run is watched: the camera endpoints are unauthenticated and the
TLS certificate is self-signed. Anyone who can reach the ports can watch. The
bind host is loopback and watching is off unless the caller asked for it.
"""

from __future__ import annotations

import argparse
import importlib
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Optional

from .embodied import (
    CAMERA_SLOT_LABELS,
    PREVIEW_CERT_DIR,
    PREVIEW_HOST,
    TERMINAL_RUN_STATES,
    JOURNAL_POLL_SECONDS,
    RunEventLog,
    _atomic_write_json,
    _now_iso,
    _read_json,
    build_plan,
    ensure_importable,
    serialize_decision,
    serialize_goal,
    serialize_measurement,
    serialize_report,
    serialize_stage,
)

# One driver call: given the validated request, the plan, and the three ledgers
# the run will record into, drive one bench to a report. Production builds a
# ``SimulatedG1``; tests build a fast fake robot and call the same ``run_bench``,
# so the journal thread, the ledger injection and the event projection under test
# are the production ones.
BenchDriver = Callable[..., Any]

# ``vegapunk.embodied.bench``'s milestone vocabulary, mirrored rather than
# imported because that tree is a separate checkout this module resolves at run
# time via ``ensure_importable``. tests/test_embodied_api.py pins these against
# ``bench.BENCH_MILESTONES``, so a rename there cannot leave this journal quietly
# skipping a fact.
_MILESTONE_CALIBRATION = "calibration"
_MILESTONE_GOAL = "goal"
_MILESTONE_STAGE = "stage"
_MILESTONE_HARDWARE_DECISION = "hardware_decision"


class RunJournal:
    """The run's durable projection: its state document and its event log."""

    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.events = RunEventLog(self.run_dir / "events.jsonl")
        self._state: dict[str, Any] = _read_json(self.run_dir / "state.json") or {}

    @property
    def state(self) -> dict[str, Any]:
        return dict(self._state)

    def update_state(self, **changes: Any) -> dict[str, Any]:
        self._state.update(changes)
        _atomic_write_json(self.run_dir / "state.json", self._state)
        return dict(self._state)

    def cancelled(self) -> bool:
        return (self.run_dir / "cancel").exists()


class _LedgerJournal:
    """Appends what the run's ledgers gain, in the order the run gained it.

    It reads the ledgers and nothing else, so it cannot report a fact the run did
    not record, and it cannot report one differently than the ledger holds it.

    The merge is the whole of the design. Attempts land in one ledger and every
    other established fact lands in the other, and each milestone carries the
    number of attempts that existed when it became true. So the journal drains
    that many attempts, emits the milestone, and repeats: no clock, no shared
    lock, and no ledger needing to know the other's shape. The milestone ledger
    is read first so that a milestone can never name more attempts than the
    attempt snapshot taken after it holds.

    ``stage_started`` is inferred from the first record carrying a new stage
    rather than announced: the stage's plan is known from the plan, and the only
    observable moment a stage began is its first recorded attempt.
    """

    def __init__(
        self, journal: RunJournal, plan: Any, trajectories: Any, milestones: Any
    ):
        self._journal = journal
        self._plan = plan
        self._trajectories = trajectories
        self._milestones = milestones
        self._seen = 0
        self._milestones_seen = 0
        self._stage_counts: dict[str, int] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._poll, name="embodied-journal", daemon=True
        )

    def __enter__(self) -> "_LedgerJournal":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5.0)
        self.drain()

    def _poll(self) -> None:
        while not self._stop.wait(JOURNAL_POLL_SECONDS):
            self.drain()

    def drain(self) -> None:
        """Append every fact that appeared since the last read, in run order."""
        milestones = self._milestones.records()
        attempts = self._trajectories.records()

        for milestone in milestones[self._milestones_seen :]:
            if milestone.attempts_recorded > len(attempts):
                # Only reachable if a milestone was appended between the two
                # reads above. Its attempts are already recorded; this poll just
                # cannot see them yet, and emitting now would invert the order
                # this journal exists to preserve.
                break
            self._drain_attempts(attempts, milestone.attempts_recorded)
            self._append_milestone(milestone)
            self._milestones_seen += 1

        # Whatever followed the last milestone is the stage now in progress.
        self._drain_attempts(attempts, len(attempts))

    def _drain_attempts(self, attempts: tuple[Any, ...], through: int) -> None:
        for record in attempts[self._seen : through]:
            self._append_attempt(record)
        self._seen = max(self._seen, through)

    def _append_milestone(self, milestone: Any) -> None:
        kind = milestone.kind
        fact = milestone.fact
        if kind == _MILESTONE_CALIBRATION:
            self._append_calibration(fact)
        elif kind == _MILESTONE_GOAL:
            self._append_goal(fact, milestone.required_duration_s)
        elif kind == _MILESTONE_STAGE:
            self._append_stage(fact)
        elif kind == _MILESTONE_HARDWARE_DECISION:
            self._journal.events.append(
                "hardware_decision", {"decision": serialize_decision(fact)}
            )
        else:  # pragma: no cover - the bench validates its own vocabulary
            raise ValueError(f"unknown bench milestone {kind!r}")

    def _append_calibration(self, calibration: Any) -> None:
        budget = calibration.budget_rps
        for measurement in calibration.measurements:
            self._journal.events.append(
                "calibration_measured",
                {"measurement": serialize_measurement(measurement, budget)},
            )
        self._journal.events.append(
            "calibration_admitted",
            {
                "admitted": (
                    None
                    if calibration.admitted is None
                    else serialize_measurement(calibration.admitted, budget)
                ),
                "budget_rps": budget,
            },
        )

    def _append_goal(self, goal: Any, required_duration_s: Any) -> None:
        self._journal.events.append(
            "goal_derived",
            {
                "goal": serialize_goal(goal),
                "required_duration_s": required_duration_s,
                "allowed_duration_s": min(
                    self._plan.envelope.max_duration_s,
                    self._plan.skill.max_duration_s,
                ),
            },
        )

    def _append_stage(self, stage: Any) -> None:
        document = serialize_stage(stage)
        # A stage that closed without a single recorded attempt has no observable
        # moment it began, so its start is stated here rather than left missing.
        self._start_stage(document["stage"])
        self._journal.events.append(
            "stage_completed",
            {
                "stage": document["stage"],
                "halted": document["halted"],
                "halt_detail": document["halt_detail"],
                "successes": document["successes"],
                "executed_attempts": document["executed_attempts"],
                "next_stage": document["next_stage"],
                "next_stage_admitted": document["next_stage_admitted"],
                "next_stage_blocking_reasons": document["next_stage_blocking_reasons"],
            },
        )

    def _start_stage(self, stage: str) -> None:
        if stage in self._stage_counts:
            return
        self._stage_counts[stage] = 0
        self._journal.events.append(
            "stage_started",
            {
                "stage": stage,
                "planned_attempts": self._plan.attempts_per_stage,
                "max_offset_rad": self._plan.stage_offsets_rad[stage],
            },
        )

    def _append_attempt(self, record: Any) -> None:
        stage = record.stage
        self._start_stage(stage)
        index = self._stage_counts[stage]
        self._stage_counts[stage] = index + 1
        self._journal.events.append(
            "attempt_recorded",
            {
                "stage": stage,
                "index": index,
                "run_id": record.run_id,
                "outcome": record.outcome,
                "abort_cause": record.abort_cause,
                "findings": list(record.findings),
                "duration_s": record.duration_s,
                "observations": record.observations,
            },
        )


def _preview(request: Mapping[str, Any]) -> tuple[Optional[Any], Optional[Any], dict[str, Any]]:
    """Start the camera preview when asked, and say truthfully what is exposed.

    Watching happens outside the governed loop: the frame bus is handed to the
    robot, never to the loop, so nothing in the governed path can depend on
    whether anyone is looking.
    """
    if not request.get("watch"):
        return None, None, {"watching": False, "host": None, "camera_slots": []}

    ensure_importable()
    preview = importlib.import_module("vegapunk.embodied.preview")
    simulation = importlib.import_module("vegapunk.embodied.simulation")

    frames = simulation.FrameBus()
    server = preview.PreviewServer(
        frames,
        tuple(simulation.CAMERA_SLOTS.values()),
        host=PREVIEW_HOST,
        cert_dir=Path(PREVIEW_CERT_DIR),
    )
    endpoints = server.run_in_thread()
    slots = simulation.CAMERA_SLOTS
    return (
        frames,
        server,
        {
            "watching": True,
            "host": PREVIEW_HOST,
            "camera_slots": [
                {
                    "id": endpoint.slot_id,
                    "label": CAMERA_SLOT_LABELS.get(endpoint.slot_id, endpoint.slot_id),
                    "width": slots[endpoint.slot_id].width,
                    "height": slots[endpoint.slot_id].height,
                    "port": endpoint.port,
                }
                for endpoint in endpoints
            ],
        },
    )


def simulated_g1_bench(
    request: Mapping[str, Any],
    plan: Any,
    admission: Any,
    trajectories: Any,
    milestones: Any,
    frames: Optional[Any],
) -> Any:
    """Drive the real MuJoCo G1 through one bench, on this thread.

    The declared supervision is passed straight through to the robot. A run that
    declares no guardian is a real run that the ``SafetySupervisor`` refuses, and
    that refusal record is the answer the operator asked for; a check here would
    hide it behind a client error.
    """
    ensure_importable()
    bench = importlib.import_module("vegapunk.embodied.bench")
    simulation = importlib.import_module("vegapunk.embodied.simulation")

    robot = simulation.SimulatedG1(
        controlled_joints=simulation.G1_LEFT_ARM_JOINTS,
        supervision=simulation.SimulatedSupervision(
            **request["declared_supervision"]
        ),
        control_frequency_hz=request["control_frequency_hz"],
    )
    try:
        return bench.run_bench(
            robot,
            plan,
            frames=frames,
            admission=admission,
            trajectories=trajectories,
            milestones=milestones,
        )
    finally:
        robot.close()


def _report_events(journal: RunJournal, report: Any) -> None:
    """Append the one fact that does not exist until ``run_bench`` returns.

    Everything else this run established -- the calibration, the goal, each
    closed stage, the hardware decision -- was journalled from the milestone
    ledger at the moment it became true, so re-emitting any of it here would be
    the second, disagreeing account the ledgers exist to prevent. Which halt the
    run stopped on is the bench's verdict on the whole run, and a whole run has
    no earlier moment.
    """
    journal.events.append(
        "run_halted",
        {
            "halted": report.halted,
            "halt_detail": report.halt_detail,
            "completed": report.completed,
            "blocking_hardware": list(report.blocking_hardware),
        },
    )


def run_embodied(
    run_dir: str | Path, driver: BenchDriver = simulated_g1_bench
) -> dict[str, Any]:
    """Execute one prepared run to a terminal state and return its final state."""
    run_dir = Path(run_dir)
    record = _read_json(run_dir / "request.json")
    if not record:
        raise ValueError(f"embodied run request is missing: {run_dir}")
    request = record["request"]
    journal = RunJournal(run_dir)

    if journal.cancelled():
        journal.events.append("run_cancelled", {})
        return journal.update_state(state="cancelled", finished_at=_now_iso())

    ensure_importable()
    admission_module = importlib.import_module("vegapunk.embodied.admission")
    trajectory_module = importlib.import_module("vegapunk.embodied.trajectory")
    bench_module = importlib.import_module("vegapunk.embodied.bench")
    plan = build_plan(request)
    admission = admission_module.AdmissionLedger()
    trajectories = trajectory_module.TrajectoryLedger()
    milestones = bench_module.BenchMilestones()

    journal.update_state(
        state="running",
        pid=os.getpid(),
        started_at=_now_iso(),
        finished_at=None,
        error=None,
        report=None,
    )
    journal.events.append("run_started", {})

    frames: Optional[Any] = None
    server: Optional[Any] = None
    try:
        frames, server, preview = _preview(request)
        journal.update_state(preview=preview)
        with _LedgerJournal(journal, plan, trajectories, milestones):
            report = driver(
                request, plan, admission, trajectories, milestones, frames
            )
    except BaseException as error:  # SIGTERM arrives here as SystemExit
        if journal.cancelled() or isinstance(error, (KeyboardInterrupt, SystemExit)):
            journal.events.append("run_cancelled", {})
            return journal.update_state(state="cancelled", finished_at=_now_iso())
        message = f"{type(error).__name__}: {error}"
        journal.events.append("run_failed", {"message": message})
        journal.update_state(state="error", error=message, finished_at=_now_iso())
        raise
    finally:
        if server is not None:
            server.shutdown()

    _report_events(journal, report)
    # A halted bench is still a run that reached its own conclusion, so the
    # terminal state is ``done`` whatever it halted on. ``error`` is reserved for
    # a worker that could not produce a report at all.
    return journal.update_state(
        state="done",
        finished_at=_now_iso(),
        report=serialize_report(report),
    )


def spawn_worker(run_dir: str | Path) -> subprocess.Popen:
    """Start the worker for one run in its own session, logging into the run folder."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    log_handle = (run_dir / "worker.log").open("a", encoding="utf-8")
    try:
        return subprocess.Popen(
            [sys.executable, "-m", __spec__.name, "--run-dir", str(run_dir)],
            cwd=str(Path(__file__).resolve().parents[2]),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_handle.close()


def _install_cancellation() -> None:
    """Turn a SIGTERM into an exception the run can record.

    ``run_bench`` cannot be asked to stop: it is one blocking call with no
    cooperative check, and adding one would put the surface's concerns inside the
    governed loop. Raising here instead unwinds the bench, closes the robot, and
    lets the worker write down that the run was cancelled rather than leaving a
    process that vanished mid-run.
    """

    def stop(_signum: int, _frame: object) -> None:
        raise SystemExit("cancelled")

    signal.signal(signal.SIGTERM, stop)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one embodied bench.")
    parser.add_argument("--run-dir", required=True)
    arguments = parser.parse_args(argv)
    _install_cancellation()
    state = run_embodied(Path(arguments.run_dir))
    return 0 if state.get("state") == "done" else 1


if __name__ == "__main__":  # pragma: no cover - process entry
    raise SystemExit(main())


__all__ = [
    "BenchDriver",
    "RunJournal",
    "main",
    "run_embodied",
    "simulated_g1_bench",
    "spawn_worker",
]
