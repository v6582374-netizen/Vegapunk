"""The governed embodied simulation loop, exposed as runs the GUI can watch.

``vegapunk/embodied`` assembles one inner loop -- calibrate, derive a goal, climb
the two simulated admission stages, report what still blocks hardware -- and
``run_bench`` is its only driver. That driver is synchronous, owns a MuJoCo model
bound to its own thread, and serializes to nothing. This module is the seam
between it and an HTTP surface, and it is deliberately thin: it declares the
plan, spawns a worker, and projects what the worker recorded.

Four refusals shape it:

- It refuses to import ``vegapunk`` at import time. The sidecar ships in desktop
  builds where that tree is absent, and a module-level import would take the
  whole control plane down with it. Availability is probed lazily and reported
  through ``environment()``, so the surface can say what is missing instead of
  failing to start.
- It refuses to judge the caller's declared supervision. ``SimulatedSupervision``
  has no defaults because a simulation cannot observe whether a guardian is
  present; the declaration is passed through to the robot and the
  ``SafetySupervisor`` refuses the run. An API-layer check would manufacture the
  precondition the supervisor exists to check, and the operator would never see
  the refusal record that is the whole point of the exercise.
- It refuses to re-implement the plan's validations. ``BenchPlan.__post_init__``
  owns them, so the facade constructs the real plan and maps its ``ValueError``
  verbatim to 422. A second copy of those rules here would drift from the one
  that governs the run.
- It refuses to run two benches at once. One MuJoCo scene, one preview port
  triple, one governed run: a second concurrent start is a 409 rather than a
  queue, because a bench that waited its turn would report evidence about a
  configuration the operator has since changed.

The run's own directory is the record. ``state.json`` is written only by the
worker and ``events.jsonl`` only appended to, so a sidecar restart never invents
progress it did not observe, and a worker that died without landing a terminal
state is reconciled from the liveness of its recorded pid.
"""

from __future__ import annotations

import copy
import importlib
import importlib.metadata
import importlib.util
import ipaddress
import os
import re
import signal
import sys
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .translation import RunEventLog, _atomic_write_json, _read_json

# The sidecar package and the ``vegapunk`` tree are separate checkouts that
# happen to share a repository root; nothing installs one into the other.
_REPO_ROOT = Path(__file__).resolve().parents[5]

RUN_LIST_LIMIT = 50
ACTIVE_RUN_STATES = frozenset({"queued", "running"})
TERMINAL_RUN_STATES = frozenset({"done", "error", "cancelled"})
JOURNAL_POLL_SECONDS = 0.05

# Mirrored from scripts/run_embodied_bench.py, which is the working construction
# sequence for this bench. Mirrored rather than imported because ``scripts`` is
# not a package and the name collides with other ``scripts`` distributions on a
# developer's path; tests/test_embodied_api.py pins these against the script.
ENVIRONMENT_ID = "sim-g1-left-arm"
CANDIDATE_RATES_RPS = (0.15, 0.3, 0.6)
GOAL_OFFSETS_RAD = (0.0, 0.35, 0.0, 0.0, 0.0, 0.0, 0.0)
SATISFIES = ("at_reviewed_pose",)
END_EFFECTOR = "dex1_1"
CONTROL_AUTHORITY = "arm_and_gripper"
CAMERA_MAP = {
    "observation.images.head": "head",
    "observation.images.left_wrist": "leftWrist",
    "observation.images.right_wrist": "rightWrist",
}
ENVELOPE_LIMITS = {
    "max_duration_s": 20.0,
    "max_joint_velocity_rps": 1.5,
    "max_end_effector_force_n": 20.0,
    "workspace_bounds_m": ((-1.0, 1.0), (-1.0, 1.0), (0.0, 2.0)),
}
SKILL_DECLARATION = {
    "skill_id": "raise_left_shoulder",
    "revision": 1,
    "summary": "Raise the left shoulder roll to a reviewed joint pose.",
    "preconditions": ("workspace_clear", "guardian_present", "estop_reachable"),
    "postconditions": ("at_reviewed_pose",),
    "abort_conditions": ("force_exceeded", "human_stop"),
    "max_duration_s": 10.0,
    "reviewed_by": "loongge",
}

# SimulatedG1's own default cadence. Declared here because the API's default has
# to be answerable without constructing a robot.
DEFAULT_CONTROL_FREQUENCY_HZ = 50.0
DEFAULT_ATTEMPTS_PER_STAGE = 10

PREVIEW_HOST = "127.0.0.1"
PREVIEW_CERT_DIR = ".scratch/embodied-sim-preview"

# The panes the GUI shows. The geometry and ports belong to
# ``simulation.CAMERA_SLOTS``; only these labels are the surface's own.
CAMERA_SLOT_LABELS = {
    "head": "Head stereo",
    "leftWrist": "Left wrist",
    "rightWrist": "Right wrist",
}

# One fixed port per pane, as the Unitree image service publishes them. This is a
# fact about the robot, not a preference, which is why the simulated preview in
# ``simulation.CAMERA_SLOTS`` mirrors these numbers rather than choosing its own;
# tests/test_embodied_api.py pins the two together. Declared here, and not read
# off the simulation, because relaying a real robot's signalling must work in a
# desktop build where the ``vegapunk`` tree is absent.
CAMERA_SLOT_PORTS = {
    "head": 60001,
    "leftWrist": 60002,
    "rightWrist": 60003,
}

_SUPERVISION_FACTS = (
    "guardian_present",
    "estop_engaged",
    "estop_reachable",
    "workspace_clear",
)

_RUN_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


class EmbodiedValidationError(ValueError):
    """Raised when a run request cannot be turned into a governed plan."""

    def __init__(self, message: str, violations: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.violations = violations or []

    def to_dict(self) -> dict[str, Any]:
        return {"message": str(self), "violations": copy.deepcopy(self.violations)}


class SimulatorUnavailableError(RuntimeError):
    """Raised when no run can be started because the simulator is not here."""


class ActiveRunConflict(RuntimeError):
    """Raised when a bench is already running; there is only one scene."""


def _violation(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> Optional[str]:
    """Render a stored timestamp as ISO 8601, whichever form it was stored in."""
    if isinstance(value, str) and value:
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    return None


# -- the vegapunk tree, probed rather than imported -------------------------------


def ensure_importable() -> None:
    """Put the repository root on ``sys.path`` so ``vegapunk`` can be found."""
    root = str(_REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _find_spec(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _mujoco_version() -> str:
    """Read MuJoCo's version from its metadata rather than by importing it.

    Importing ``mujoco`` binds a GL backend for the life of the process, which is
    the sidecar's process. Describing the simulator must not do that.
    """
    try:
        return f"mujoco {importlib.metadata.version('mujoco')}"
    except importlib.metadata.PackageNotFoundError:
        return "mujoco, version unknown"


def probe_simulator() -> dict[str, Any]:
    """State whether a bench could run here, and if not, what is missing."""
    ensure_importable()
    if not _find_spec("vegapunk.embodied.bench"):
        return {
            "available": False,
            "detail": "",
            "scene_path": None,
            "reason": (
                "the vegapunk package is not part of this build, so the "
                "governed simulation loop it owns cannot be driven from here"
            ),
        }
    if not _find_spec("mujoco"):
        return {
            "available": False,
            "detail": "",
            "scene_path": None,
            "reason": "mujoco is not installed, so there is no simulator to run",
        }
    try:
        simulation = importlib.import_module("vegapunk.embodied.simulation")
    except Exception as error:  # a broken tree is unavailability, not a crash
        return {
            "available": False,
            "detail": "",
            "scene_path": None,
            "reason": f"the simulation module could not be loaded: {error}",
        }
    scene_path = Path(simulation.DEFAULT_SCENE_PATH)
    if not scene_path.exists():
        return {
            "available": False,
            "detail": _mujoco_version(),
            "scene_path": str(scene_path),
            "reason": (
                f"the G1 MJCF scene is not present at {scene_path}; it comes "
                "from mujoco_menagerie and is not vendored in this repository"
            ),
        }
    return {
        "available": True,
        "detail": _mujoco_version(),
        "scene_path": str(scene_path),
        "reason": None,
    }


# -- the declaration, and the plan it produces -----------------------------------


def _skill():
    """Build the reviewed skill this bench iterates."""
    ensure_importable()
    skill_module = importlib.import_module("vegapunk.embodied.skill")
    return skill_module.PhysicalSkill(
        kind=skill_module.SKILL_KIND_DETERMINISTIC,
        parameters=(),
        **SKILL_DECLARATION,
    )


def _envelope():
    """Build the limits the supervisor enforces for this bench."""
    ensure_importable()
    safety = importlib.import_module("vegapunk.embodied.safety")
    return safety.SafetyEnvelope(**ENVELOPE_LIMITS)


def build_plan(request: Mapping[str, Any]):
    """Turn a validated request into the ``BenchPlan`` that governs the run.

    Shared by the facade and the worker so that the plan a request is rejected
    against is the same object the bench is later driven with. Every refusal
    raised here belongs to ``BenchPlan.__post_init__``.
    """
    ensure_importable()
    bench = importlib.import_module("vegapunk.embodied.bench")
    return bench.BenchPlan(
        skill=_skill(),
        goal_offsets_rad=GOAL_OFFSETS_RAD,
        satisfies=SATISFIES,
        envelope=_envelope(),
        candidate_rates_rps=CANDIDATE_RATES_RPS,
        environment_id=ENVIRONMENT_ID,
        end_effector=END_EFFECTOR,
        control_authority=CONTROL_AUTHORITY,
        camera_map=CAMERA_MAP,
        attempts_per_stage=int(request["attempts_per_stage"]),
    )


def embodiment_digest_for(control_frequency_hz: float) -> str:
    """The digest this run's evidence will be scoped to.

    Derived from the same facts ``embodiment_for`` reads off the environment --
    the controlled joints and the cadence -- so it can be reported before a
    robot exists, and so a snapshot names the scope before the first attempt.
    """
    ensure_importable()
    embodiment = importlib.import_module("vegapunk.embodied.embodiment")
    simulation = importlib.import_module("vegapunk.embodied.simulation")
    joints = len(simulation.G1_LEFT_ARM_JOINTS)
    return embodiment.EmbodimentProfile(
        robot_model="unitree_g1_simulated",
        arm_dof=joints,
        end_effector=END_EFFECTOR,
        camera_map=dict(CAMERA_MAP),
        control_frequency_hz=float(control_frequency_hz),
        control_authority=CONTROL_AUTHORITY,
        state_dim=joints,
        action_dim=joints,
        onboard_image_service=bool(CAMERA_MAP),
    ).digest()


def camera_slot_documents() -> list[dict[str, Any]]:
    """The GUI's camera panes, as the simulation declares them."""
    ensure_importable()
    try:
        simulation = importlib.import_module("vegapunk.embodied.simulation")
    except Exception:
        return []
    return [
        {
            "id": slot.slot_id,
            "label": CAMERA_SLOT_LABELS.get(slot.slot_id, slot.slot_id),
            "width": slot.width,
            "height": slot.height,
            "port": slot.preview_port,
        }
        for slot in simulation.CAMERA_SLOTS.values()
    ]


class CameraRelayError(RuntimeError):
    """Raised when a camera's signalling exchange cannot be completed."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _relay_host(raw: Any) -> str:
    """Accept only a private-network literal address for the robot.

    The relay is a server-side fetch driven by browser input, so an unrestricted
    host would turn the sidecar into an open proxy for the machine's whole network
    position. A literal private address is the entire legitimate use -- the robot
    sits on a wired 192.168.123.0/24 link -- so names are refused rather than
    resolved: a name that resolves privately once can resolve anywhere later, and
    a DNS round that decides reachability cannot be reasoned about.
    """
    host = str(raw or "").strip()
    if not host:
        raise CameraRelayError("no robot address was given", status=422)
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise CameraRelayError(
            "the robot must be given as a literal address, for example 192.168.123.164",
            status=422,
        ) from error
    if not (address.is_private or address.is_loopback or address.is_link_local):
        raise CameraRelayError(
            "only a private-network robot address can be relayed",
            status=422,
        )
    return address.compressed


def relay_camera_offer(host: Any, slot_id: str, offer: Any) -> dict[str, Any]:
    """Exchange one WebRTC offer with a robot camera on the operator's behalf.

    The robot's image service serves HTTPS with a self-signed certificate that
    carries no subjectAltName, so no browser can ever be taught to trust it: name
    verification has nothing to check against. The exchange is therefore performed
    here, server-to-server, and only the answer crosses back to the page -- the
    media itself still flows browser-to-robot over WebRTC's own DTLS, whose
    fingerprint is carried inside this signalling.

    Transport verification is off by design, and that is the honest description of
    what is available on a wired link to an appliance: it buys confidentiality
    against a passive listener and no identity guarantee. The relay is confined to
    private addresses and to the three known camera ports so it cannot be used to
    reach anything else.
    """
    resolved = _relay_host(host)
    try:
        port = CAMERA_SLOT_PORTS[slot_id]
    except KeyError as error:
        raise CameraRelayError(
            f"unknown camera {slot_id!r}; this robot publishes "
            f"{sorted(CAMERA_SLOT_PORTS)}",
            status=404,
        ) from error

    if not isinstance(offer, Mapping) or not offer.get("sdp") or not offer.get("type"):
        raise CameraRelayError("the offer must carry an sdp and a type", status=422)

    import httpx

    try:
        with httpx.Client(verify=False, timeout=10.0) as client:
            response = client.post(
                f"https://{resolved}:{port}/offer",
                json={"sdp": str(offer["sdp"]), "type": str(offer["type"])},
            )
    except httpx.HTTPError as error:
        raise CameraRelayError(
            f"the camera at {resolved}:{port} did not answer", status=504
        ) from error

    if response.status_code >= 400:
        raise CameraRelayError(
            f"the camera at {resolved}:{port} refused the offer "
            f"({response.status_code})",
            status=502,
        )
    try:
        answer = response.json()
    except ValueError as error:
        raise CameraRelayError(
            f"the camera at {resolved}:{port} did not return an answer", status=502
        ) from error
    if not isinstance(answer, Mapping) or not answer.get("sdp"):
        raise CameraRelayError(
            f"the camera at {resolved}:{port} did not return an answer", status=502
        )
    return {"sdp": str(answer["sdp"]), "type": str(answer.get("type") or "answer")}


def environment_document() -> dict[str, Any]:
    """Everything the surface needs to describe this bench before running one.

    No ``SimulatedG1`` is constructed. Building one compiles the MJCF model and
    binds a GL context to the calling thread, and the sidecar's thread is the
    last place either belongs; every fact below is read off the declaration or
    off the model's joint list instead.
    """
    simulator = probe_simulator()
    document: dict[str, Any] = {
        "environment_id": ENVIRONMENT_ID,
        "simulator": simulator,
        "control_frequency_hz": DEFAULT_CONTROL_FREQUENCY_HZ,
        "joints": [],
        "joint_count": 0,
        "goal_offsets_rad": list(GOAL_OFFSETS_RAD),
        "candidate_rates_rps": list(CANDIDATE_RATES_RPS),
        "velocity_margin": 0.0,
        "velocity_budget_rps": 0.0,
        "envelope": None,
        "skill": None,
        "ladder": [],
        "minimum_stage_attempts": 0,
        "minimum_stage_success_rate": 0.0,
        "approval_validity_hours": 0.0,
        "stage_offsets_rad": {},
        "unrepresentable": [],
        "camera_slots": camera_slot_documents(),
    }
    if not _find_spec("vegapunk.embodied.bench"):
        return document

    ensure_importable()
    admission = importlib.import_module("vegapunk.embodied.admission")
    bench = importlib.import_module("vegapunk.embodied.bench")
    calibration = importlib.import_module("vegapunk.embodied.calibration")
    fidelity = importlib.import_module("vegapunk.embodied.fidelity")
    simulation = importlib.import_module("vegapunk.embodied.simulation")

    envelope = _envelope()
    skill = _skill()
    plan = build_plan({"attempts_per_stage": DEFAULT_ATTEMPTS_PER_STAGE})
    margin = calibration.DEFAULT_VELOCITY_MARGIN
    joints = list(simulation.G1_LEFT_ARM_JOINTS)

    document.update(
        {
            "joints": joints,
            "joint_count": len(joints),
            "velocity_margin": margin,
            "velocity_budget_rps": envelope.max_joint_velocity_rps * margin,
            "envelope": {
                "max_duration_s": envelope.max_duration_s,
                "max_joint_velocity_rps": envelope.max_joint_velocity_rps,
                "max_end_effector_force_n": envelope.max_end_effector_force_n,
                "max_observation_age_s": envelope.max_observation_age_s,
                "workspace_bounds_m": [list(axis) for axis in envelope.workspace_bounds_m],
            },
            "skill": {
                "skill_id": skill.skill_id,
                "revision": skill.revision,
                "version_id": skill.version_id,
                "kind": skill.kind,
                "summary": skill.summary,
                "preconditions": list(skill.preconditions),
                "postconditions": list(skill.postconditions),
                "abort_conditions": list(skill.abort_conditions),
                "max_duration_s": skill.max_duration_s,
                "reviewed_by": skill.reviewed_by,
            },
            "ladder": [
                {"stage": stage, "simulated": stage in bench.BENCH_STAGES}
                for stage in admission.ADMISSION_STAGE_ORDER
            ],
            "minimum_stage_attempts": admission.MINIMUM_STAGE_ATTEMPTS,
            "minimum_stage_success_rate": admission.MINIMUM_STAGE_SUCCESS_RATE,
            "approval_validity_hours": (
                admission.APPROVAL_VALIDITY.total_seconds() / 3600.0
            ),
            "stage_offsets_rad": dict(plan.stage_offsets_rad),
            "unrepresentable": list(fidelity.UNREPRESENTABLE_IN_SIMULATION),
        }
    )
    return document


# -- serializers -----------------------------------------------------------------
#
# The embodied package serializes to nothing by design: its reports are frozen
# dataclasses of measured facts, and JSON is this surface's concern. Every
# function below is a projection with no arithmetic of its own, except where the
# report already exposes the derived value as a property.


def serialize_measurement(measurement: Any, budget_rps: float) -> dict[str, Any]:
    return {
        "commanded_rate_rps": measurement.commanded_rate_rps,
        "peak_joint_velocity_rps": measurement.peak_joint_velocity_rps,
        "tracking_error_rad": measurement.tracking_error_rad,
        "settled_error_rad": measurement.settled_error_rad,
        "overshoot_ratio": measurement.overshoot_ratio,
        "max_step_rad": measurement.max_step_rad,
        "max_lead_rad": measurement.max_lead_rad,
        "minimum_goal_tolerance_rad": measurement.minimum_goal_tolerance_rad,
        # The admission arithmetic itself: a rate is admissible when its
        # measured peak stayed inside the budget.
        "fits": measurement.peak_joint_velocity_rps <= budget_rps,
    }


def serialize_calibration(report: Any) -> dict[str, Any]:
    budget = report.budget_rps
    return {
        "measured_on": report.measured_on,
        "control_frequency_hz": report.control_frequency_hz,
        "velocity_limit_rps": report.velocity_limit_rps,
        "margin": report.margin,
        "budget_rps": budget,
        "measurements": [
            serialize_measurement(item, budget) for item in report.measurements
        ],
        "admitted": (
            None
            if report.admitted is None
            else serialize_measurement(report.admitted, budget)
        ),
        "findings": list(report.findings),
    }


def serialize_goal(goal: Any) -> Optional[dict[str, Any]]:
    if goal is None:
        return None
    return {
        "skill_version_id": goal.skill_version_id,
        "target_joint_positions_rad": list(goal.target_joint_positions_rad),
        "satisfies": list(goal.satisfies),
        "tolerance_rad": goal.tolerance_rad,
    }


def serialize_attempt(attempt: Any) -> dict[str, Any]:
    return {
        "index": attempt.index,
        "run_id": attempt.run_id,
        "outcome": attempt.outcome,
        "variation_digest": attempt.variation_digest,
        "findings": list(attempt.findings),
        "abort_cause": attempt.abort_cause,
    }


def serialize_evidence(evidence: Any) -> dict[str, Any]:
    return {**evidence.as_evidence(), "success_rate": evidence.success_rate}


def serialize_fidelity(fidelity: Any) -> dict[str, Any]:
    return {
        "verdict": fidelity.verdict,
        "environment_id": fidelity.environment_id,
        "environment_digest": fidelity.environment_digest,
        "embodiment_digest": fidelity.embodiment_digest,
        "findings": list(fidelity.findings),
        "unrepresented": list(fidelity.unrepresented),
        "represents": fidelity.represents,
    }


def serialize_stage(stage: Any) -> dict[str, Any]:
    return {
        "campaign_id": stage.campaign_id,
        "stage": stage.stage,
        "scope": list(stage.scope),
        "planned_attempts": stage.planned_attempts,
        "executed_attempts": stage.executed_attempts,
        "successes": stage.successes,
        "completed": stage.completed,
        "attempts": [serialize_attempt(item) for item in stage.attempts],
        "evidence": serialize_evidence(stage.evidence),
        "fidelity": serialize_fidelity(stage.fidelity),
        "halted": stage.halted,
        "halt_detail": stage.halt_detail,
        "next_stage": stage.next_stage,
        "next_stage_admitted": stage.next_stage_admitted,
        "next_stage_blocking_reasons": list(stage.next_stage_blocking_reasons),
    }


def serialize_decision(decision: Any) -> Optional[dict[str, Any]]:
    if decision is None:
        return None
    return {
        "target_stage": decision.target_stage,
        "admitted": decision.admitted,
        "evidence_digest": decision.evidence_digest,
        "blocking_reasons": list(decision.blocking_reasons),
    }


def serialize_report(report: Any) -> dict[str, Any]:
    return {
        "environment_id": report.environment_id,
        "skill_version_id": report.skill_version_id,
        "embodiment_digest": report.embodiment_digest,
        "halted": report.halted,
        "halt_detail": report.halt_detail,
        "completed": report.completed,
        "blocking_hardware": list(report.blocking_hardware),
        "calibration": serialize_calibration(report.calibration),
        "goal": serialize_goal(report.goal),
        "required_duration_s": report.required_duration_s,
        "stages": [serialize_stage(stage) for stage in report.stages],
        "hardware_decision": serialize_decision(report.hardware_decision),
    }


# -- request validation ----------------------------------------------------------


def _supervision(value: Any) -> dict[str, bool]:
    """Read the operator's declaration, and refuse to guess a missing fact.

    Nothing here judges what was declared. ``guardian_present: false`` is a
    perfectly valid request: it produces a real run whose preflight refuses, and
    that refusal record is the answer the operator asked for.
    """
    if not isinstance(value, Mapping):
        raise EmbodiedValidationError(
            "declared_supervision must be an object naming all four "
            "supervision facts; a simulation cannot observe any of them",
            [_violation("declared_supervision", "an object is required")],
        )
    declared: dict[str, bool] = {}
    violations: list[dict[str, Any]] = []
    for fact in _SUPERVISION_FACTS:
        raw = value.get(fact)
        if not isinstance(raw, bool):
            violations.append(
                _violation(
                    f"declared_supervision.{fact}",
                    "must be declared true or false by the operator",
                )
            )
            continue
        declared[fact] = raw
    if violations:
        raise EmbodiedValidationError(
            "every supervision fact must be declared, because a simulated run "
            "cannot measure one and a default would manufacture it",
            violations,
        )
    return declared


def normalize_request(body: Any) -> dict[str, Any]:
    """Validate the request body's shape; the plan validates its content."""
    if not isinstance(body, Mapping):
        raise EmbodiedValidationError(
            "an embodied run request must be an object",
            [_violation("", "an object is required")],
        )
    attempts = body.get("attempts_per_stage", DEFAULT_ATTEMPTS_PER_STAGE)
    if isinstance(attempts, bool) or not isinstance(attempts, int):
        raise EmbodiedValidationError(
            "attempts_per_stage must be an integer",
            [_violation("attempts_per_stage", "must be an integer")],
        )
    frequency = body.get("control_frequency_hz", DEFAULT_CONTROL_FREQUENCY_HZ)
    if isinstance(frequency, bool) or not isinstance(frequency, (int, float)):
        raise EmbodiedValidationError(
            "control_frequency_hz must be a number",
            [_violation("control_frequency_hz", "must be a number")],
        )
    # SimulatedG1 refuses this itself, but its constructor compiles the model and
    # binds a GL context, so it cannot be reached from here to do the refusing.
    if float(frequency) <= 0:
        raise EmbodiedValidationError(
            "control_frequency_hz must be positive",
            [_violation("control_frequency_hz", "must be positive")],
        )
    return {
        "declared_supervision": _supervision(body.get("declared_supervision")),
        "attempts_per_stage": attempts,
        "control_frequency_hz": float(frequency),
        "watch": bool(body.get("watch", False)),
    }


# -- the facade ------------------------------------------------------------------


class EmbodiedFacade:
    """The module's only seam: the environment, and one bench run at a time.

    ``runner`` receives a prepared run directory and returns once that run has
    reached a terminal state. Production spawns the worker process; tests supply
    a runner that drives the same worker core with a fake robot, so no
    production path carries a test-only branch.
    """

    schema_version = 1

    def __init__(
        self,
        data_base: str | Path,
        *,
        runner: Callable[[Path], None] | None = None,
    ):
        self._root = Path(data_base) / "embodied"
        self._runs_root = self._root / "runs"
        self._runner = runner or _spawn_worker_process
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    # -- environment -------------------------------------------------------------

    def environment(self) -> dict[str, Any]:
        return environment_document()

    # -- runs --------------------------------------------------------------------

    def start_run(self, body: Any) -> dict[str, Any]:
        request = normalize_request(body)
        status = probe_simulator()
        # The plan is validated before the simulator is required, because a
        # request no configuration could satisfy is the caller's error whether or
        # not this host happens to be able to run one.
        if _find_spec("vegapunk.embodied.bench"):
            try:
                build_plan(request)
            except ValueError as error:
                # BenchPlan owns these nine refusals; this maps them, verbatim.
                raise EmbodiedValidationError(str(error), []) from error
        if not status["available"]:
            raise SimulatorUnavailableError(status["reason"])

        run_id = uuid.uuid4().hex
        run_dir = self._runs_root / run_id
        with self._lock:
            active = self._active_run_id()
            if active is not None:
                raise ActiveRunConflict(
                    f"embodied run {active} is still running; there is one "
                    "simulated G1 and one governed loop, so a second run would "
                    "either contend for the scene or report evidence about a "
                    "configuration nobody is watching"
                )
            run_dir.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(
                run_dir / "request.json",
                {
                    "schema_version": self.schema_version,
                    "run_id": run_id,
                    "created_at": _now_iso(),
                    "request": request,
                    # Recorded now rather than derived on read: these are facts
                    # about this run, and the tree they come from may be gone by
                    # the time the run is read back.
                    "environment_id": ENVIRONMENT_ID,
                    "skill_version_id": _skill().version_id,
                    "embodiment_digest": embodiment_digest_for(
                        request["control_frequency_hz"]
                    ),
                },
            )
            _atomic_write_json(
                run_dir / "state.json",
                {"state": "queued", "started_at": None, "finished_at": None},
            )
            thread = threading.Thread(
                target=self._drive, args=(run_dir,), name="embodied-run", daemon=True
            )
            self._thread = thread
        thread.start()
        return self._snapshot(run_id)

    def list_runs(self) -> dict[str, Any]:
        snapshots = [self._snapshot(run_id) for run_id in self._run_ids()]
        snapshots.sort(key=lambda run: run["created_at"] or "", reverse=True)
        return {"runs": snapshots[:RUN_LIST_LIMIT]}

    def run(self, run_id: str) -> dict[str, Any]:
        return self._snapshot(self._validated_run_id(run_id))

    def events(self, run_id: str, after: int = 0) -> dict[str, Any]:
        validated = self._validated_run_id(run_id)
        page = RunEventLog(self._runs_root / validated / "events.jsonl").page(after)
        return {
            "events": [_wire_event(event) for event in page["events"]],
            "latest_sequence": page["latest_sequence"],
        }

    def cancel(self, run_id: str) -> dict[str, Any]:
        validated = self._validated_run_id(run_id)
        run_dir = self._runs_root / validated
        state = self._reconcile_dead_run(
            run_dir, _read_json(run_dir / "state.json") or {}
        )
        current = state.get("state")
        if current in TERMINAL_RUN_STATES:
            return self._snapshot(validated)
        # The marker is the cancellation fact both processes read; the signal is
        # only an accelerator for a worker blocked inside a bench.
        (run_dir / "cancel").write_text(_now_iso(), encoding="utf-8")
        if current == "queued":
            self._write_state(
                run_dir,
                {**state, "state": "cancelled", "finished_at": _now_iso()},
            )
            RunEventLog(run_dir / "events.jsonl").append("run_cancelled", {})
            return self._snapshot(validated)
        pid = state.get("pid")
        if isinstance(pid, int) and pid > 0 and pid != os.getpid():
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        return self._snapshot(validated)

    # -- execution ---------------------------------------------------------------

    def _drive(self, run_dir: Path) -> None:
        """Run one bench to a terminal state, whatever the runner does.

        A runner can fail two ways, and both must end as the run's own recorded
        fact rather than as a run that reads ``running`` forever: it can raise,
        or it can return having written nothing -- a worker killed before it
        landed a state, or a process that never started at all. Only the worker
        writes ``state.json``, so the sidecar's one entitlement here is to settle
        a run whose driver has provably stopped.
        """
        message: Optional[str] = None
        try:
            self._runner(run_dir)
        except Exception as error:
            message = f"the embodied worker could not be run: {error}"
        state = _read_json(run_dir / "state.json") or {}
        if state.get("state") in TERMINAL_RUN_STATES:
            return
        cancelled = (run_dir / "cancel").is_file()
        if message is None:
            message = "the embodied worker stopped without finishing"
        settled = {
            **state,
            "state": "cancelled" if cancelled else "error",
            "finished_at": _now_iso(),
        }
        if not cancelled:
            settled["error"] = message
        self._write_state(run_dir, settled)
        RunEventLog(run_dir / "events.jsonl").append(
            "run_cancelled" if cancelled else "run_failed",
            {} if cancelled else {"message": message},
        )

    # -- projection --------------------------------------------------------------

    def _run_ids(self) -> list[str]:
        try:
            return [entry.name for entry in self._runs_root.iterdir() if entry.is_dir()]
        except (FileNotFoundError, OSError):
            return []

    def _active_run_id(self) -> Optional[str]:
        for run_id in self._run_ids():
            run_dir = self._runs_root / run_id
            state = self._reconcile_dead_run(
                run_dir, _read_json(run_dir / "state.json") or {}
            )
            if state.get("state") in ACTIVE_RUN_STATES:
                return run_id
        return None

    def _validated_run_id(self, run_id: str) -> str:
        if (
            not isinstance(run_id, str)
            or not _RUN_ID_PATTERN.fullmatch(run_id)
            or not (self._runs_root / run_id / "request.json").is_file()
        ):
            raise KeyError(run_id)
        return run_id

    def _write_state(self, run_dir: Path, state: Mapping[str, Any]) -> None:
        _atomic_write_json(run_dir / "state.json", dict(state))

    def _reconcile_dead_run(
        self, run_dir: Path, state: dict[str, Any]
    ) -> dict[str, Any]:
        """Turn an abandoned run into a terminal one.

        Only the worker writes ``state.json``, so a worker that died without
        landing a terminal state -- a SIGKILL, a simulator that took the process
        with it -- would leave the run reading ``running`` forever. The liveness
        of the recorded pid is the fact that settles it, so every projection
        checks it.
        """
        if state.get("state") not in ACTIVE_RUN_STATES:
            return state
        pid = state.get("pid")
        if not isinstance(pid, int) or pid <= 0 or pid == os.getpid():
            return state
        try:
            os.kill(pid, 0)
            return state
        except PermissionError:  # alive, just not ours to signal
            return state
        except OSError:
            pass
        cancelled = (run_dir / "cancel").is_file()
        settled = {
            **state,
            "state": "cancelled" if cancelled else "error",
            "finished_at": _now_iso(),
        }
        if not cancelled:
            settled["error"] = "the embodied worker stopped without finishing"
        self._write_state(run_dir, settled)
        RunEventLog(run_dir / "events.jsonl").append(
            "run_cancelled" if cancelled else "run_failed",
            {} if cancelled else {"message": settled["error"]},
        )
        return settled

    def _snapshot(self, run_id: str) -> dict[str, Any]:
        run_dir = self._runs_root / run_id
        record = _read_json(run_dir / "request.json") or {}
        state = self._reconcile_dead_run(
            run_dir, _read_json(run_dir / "state.json") or {}
        )
        run_state = state.get("state")
        if run_state not in ACTIVE_RUN_STATES | TERMINAL_RUN_STATES:
            run_state = "queued"
        report = state.get("report") if isinstance(state.get("report"), dict) else {}
        preview = state.get("preview") if isinstance(state.get("preview"), dict) else {}
        request = record.get("request") if isinstance(record.get("request"), dict) else {}
        return {
            "run_id": run_id,
            "state": run_state,
            "created_at": _iso(record.get("created_at")),
            "started_at": _iso(state.get("started_at")),
            "finished_at": _iso(state.get("finished_at")),
            "request": request,
            "environment_id": report.get("environment_id")
            or record.get("environment_id")
            or ENVIRONMENT_ID,
            "skill_version_id": report.get("skill_version_id")
            or record.get("skill_version_id")
            or "",
            "embodiment_digest": report.get("embodiment_digest")
            or record.get("embodiment_digest")
            or "",
            "halted": report.get("halted"),
            "halt_detail": report.get("halt_detail") or "",
            "completed": bool(report.get("completed")),
            "blocking_hardware": report.get("blocking_hardware") or [],
            "calibration": report.get("calibration"),
            "goal": report.get("goal"),
            "required_duration_s": report.get("required_duration_s"),
            "stages": report.get("stages") or [],
            "hardware_decision": report.get("hardware_decision"),
            "error": state.get("error") if isinstance(state.get("error"), str) else None,
            "preview": {
                "watching": bool(preview.get("watching")),
                "host": preview.get("host"),
                "camera_slots": preview.get("camera_slots") or [],
            },
        }


def _wire_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Project one stored event onto the wire.

    The durable log is the house's ``RunEventLog``, which spells its cursor
    ``sequence`` and stamps wall-clock floats. The surface promises ``seq`` and
    ISO 8601, and the frontend's cursor is this ``seq``; the two are the same
    number, so paging is unaffected by the rename.
    """
    payload = {
        key: value
        for key, value in event.items()
        if key not in {"sequence", "at", "type"}
    }
    return {
        "seq": event.get("sequence"),
        "at": _iso(event.get("at")),
        "type": event.get("type"),
        **payload,
    }


def _spawn_worker_process(run_dir: Path) -> None:
    """Start the worker in its own process and wait for it to finish.

    A subprocess rather than a thread, for three reasons that are all about
    what MuJoCo is: its EGL context must not live in the sidecar's process, a
    simulator that segfaults must not take the control plane down with it, and
    cancelling a blocking native call is a process kill or nothing.
    """
    from .embodied_worker import spawn_worker

    process = spawn_worker(run_dir)
    process.wait()


__all__ = [
    "ActiveRunConflict",
    "CAMERA_MAP",
    "CANDIDATE_RATES_RPS",
    "EmbodiedFacade",
    "EmbodiedValidationError",
    "ENVELOPE_LIMITS",
    "ENVIRONMENT_ID",
    "GOAL_OFFSETS_RAD",
    "SKILL_DECLARATION",
    "SimulatorUnavailableError",
    "build_plan",
    "embodiment_digest_for",
    "environment_document",
    "normalize_request",
    "probe_simulator",
    "serialize_report",
]
