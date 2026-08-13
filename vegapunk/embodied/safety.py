"""The deterministic Safety Supervisor.

A macro action may run to completion on hardware once it is prepared and
approved, but this supervisor keeps abort authority at every instant. It is
deliberately deterministic and free of learned components: given one
observation it always produces the same verdict, so a run's abort behaviour can
be reasoned about and reproduced offline.

The supervisor accepts advice only in the tightening direction. MAS or a policy
may propose narrower limits for a specific attempt, but nothing outside this
module can widen an envelope, remove a check, or override a human stop.

Missing information is treated as unsafe: a stale observation aborts rather
than assuming the previous state still holds, and a precondition the sensors
cannot report fails preflight rather than being presumed satisfied.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Optional

ABORT_HUMAN_STOP = "human_stop"
ABORT_ENVELOPE_VIOLATION = "envelope_violation"
ABORT_TIME_LIMIT = "time_limit"
ABORT_OBSERVATION_STALE = "observation_stale"

_TIGHTENABLE_LIMITS = (
    "max_duration_s",
    "max_joint_velocity_rps",
    "max_end_effector_force_n",
    "max_observation_age_s",
)

_PREFLIGHT_REST_VELOCITY_RPS = 0.05


@dataclass(frozen=True)
class SafetyEnvelope:
    """The hard physical limits one run may not exceed."""

    max_duration_s: float
    max_joint_velocity_rps: float
    max_end_effector_force_n: float
    workspace_bounds_m: tuple[tuple[float, float], ...]
    max_observation_age_s: float = 0.2

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "workspace_bounds_m",
            tuple(tuple(axis) for axis in self.workspace_bounds_m),
        )
        for name in _TIGHTENABLE_LIMITS:
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if len(self.workspace_bounds_m) != 3:
            raise ValueError(
                "workspace_bounds_m needs one (low, high) pair per axis"
            )
        for index, (low, high) in enumerate(self.workspace_bounds_m):
            if low >= high:
                raise ValueError(
                    f"workspace_bounds_m axis {index} is not ordered "
                    f"low-to-high: ({low}, {high})"
                )

    def contains(self, position_m: tuple[float, ...]) -> bool:
        if len(position_m) != len(self.workspace_bounds_m):
            return False
        return all(
            low <= value <= high
            for value, (low, high) in zip(position_m, self.workspace_bounds_m)
        )


@dataclass(frozen=True)
class Observation:
    """One deterministic snapshot the supervisor judges.

    This is the safety view of the robot, not the policy's observation: it
    carries no images, only the quantities an abort decision depends on.
    """

    elapsed_s: float
    age_s: float
    joint_velocity_rps: tuple[float, ...]
    end_effector_force_n: float
    end_effector_position_m: tuple[float, ...]
    guardian_present: bool
    estop_engaged: bool
    estop_reachable: bool
    workspace_clear: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "joint_velocity_rps", tuple(self.joint_velocity_rps)
        )
        object.__setattr__(
            self,
            "end_effector_position_m",
            tuple(self.end_effector_position_m),
        )

    @property
    def peak_joint_velocity_rps(self) -> float:
        if not self.joint_velocity_rps:
            return 0.0
        return max(abs(value) for value in self.joint_velocity_rps)

    def condition_flags(self) -> Mapping[str, bool]:
        """Named boolean facts a skill precondition may refer to."""
        return {
            "workspace_clear": self.workspace_clear,
            "guardian_present": self.guardian_present,
            "estop_reachable": self.estop_reachable,
        }


@dataclass(frozen=True)
class PreflightResult:
    """The deterministic go/no-go verdict recorded before a run starts."""

    passed: bool
    failures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "failures", tuple(self.failures))


@dataclass(frozen=True)
class AbortDirective:
    """The supervisor's instantaneous instruction to stop a run."""

    cause: str
    detail: str


class SafetySupervisor:
    """Owns preflight admission and runtime abort authority for one run."""

    def __init__(self, envelope: SafetyEnvelope) -> None:
        self._envelope = envelope

    @property
    def envelope(self) -> SafetyEnvelope:
        return self._envelope

    def with_advice(self, advice: Mapping[str, float]) -> "SafetySupervisor":
        """Derive a supervisor with narrower limits.

        Advice may come from a non-deterministic component, so it is accepted
        only when every proposed limit is at least as strict as the current
        one. An attempt to widen a limit or name an unknown one is an error
        rather than a silently ignored request.
        """
        unknown = sorted(set(advice) - set(_TIGHTENABLE_LIMITS))
        if unknown:
            raise ValueError(
                "advice may only tighten known limits; unknown: "
                + ", ".join(unknown)
            )
        for name, value in advice.items():
            if value > getattr(self._envelope, name):
                raise ValueError(
                    f"advice cannot relax {name} from "
                    f"{getattr(self._envelope, name)} to {value}"
                )
        return SafetySupervisor(
            replace(self._envelope, **{key: float(value) for key, value in advice.items()})
        )

    def preflight(
        self,
        observation: Observation,
        required_preconditions: tuple[str, ...],
    ) -> PreflightResult:
        """Check every admission condition before a run is allowed to start."""
        failures: list[str] = []

        if observation.age_s > self._envelope.max_observation_age_s:
            failures.append(
                f"observation is stale at {observation.age_s}s, above the "
                f"limit {self._envelope.max_observation_age_s}s"
            )
        if not observation.guardian_present:
            failures.append("no guardian is present to supervise the run")
        if not observation.estop_reachable:
            failures.append("the estop is not reachable by the guardian")
        if observation.estop_engaged:
            failures.append("the estop is engaged")
        if observation.peak_joint_velocity_rps > _PREFLIGHT_REST_VELOCITY_RPS:
            failures.append(
                "the robot is not at rest at "
                f"{observation.peak_joint_velocity_rps} rad/s"
            )
        if observation.end_effector_force_n > (
            self._envelope.max_end_effector_force_n
        ):
            failures.append(
                f"end-effector force {observation.end_effector_force_n}N is "
                f"already above the limit "
                f"{self._envelope.max_end_effector_force_n}N"
            )
        if not self._envelope.contains(observation.end_effector_position_m):
            failures.append(
                "the end effector starts outside the workspace bounds at "
                f"{observation.end_effector_position_m}"
            )

        flags = observation.condition_flags()
        for condition in required_preconditions:
            if condition not in flags:
                failures.append(
                    f"precondition {condition!r} is not observable, so it "
                    "cannot be presumed satisfied"
                )
            elif not flags[condition]:
                failures.append(f"precondition {condition!r} is not satisfied")

        return PreflightResult(passed=not failures, failures=tuple(failures))

    def evaluate(self, observation: Observation) -> Optional[AbortDirective]:
        """Judge one runtime observation, returning an abort when required.

        Human stop is checked first: when a person has intervened, the reason
        recorded is the intervention, not whatever physical limit followed it.
        """
        if observation.estop_engaged:
            return AbortDirective(
                cause=ABORT_HUMAN_STOP, detail="the estop was engaged"
            )
        if not observation.guardian_present:
            return AbortDirective(
                cause=ABORT_HUMAN_STOP,
                detail="the supervising guardian is no longer present",
            )
        if observation.age_s > self._envelope.max_observation_age_s:
            return AbortDirective(
                cause=ABORT_OBSERVATION_STALE,
                detail=(
                    f"observation age {observation.age_s}s exceeds "
                    f"{self._envelope.max_observation_age_s}s"
                ),
            )
        if observation.elapsed_s > self._envelope.max_duration_s:
            return AbortDirective(
                cause=ABORT_TIME_LIMIT,
                detail=(
                    f"elapsed {observation.elapsed_s}s exceeds "
                    f"{self._envelope.max_duration_s}s"
                ),
            )
        if observation.peak_joint_velocity_rps > (
            self._envelope.max_joint_velocity_rps
        ):
            return AbortDirective(
                cause=ABORT_ENVELOPE_VIOLATION,
                detail=(
                    f"peak joint velocity "
                    f"{observation.peak_joint_velocity_rps} rad/s exceeds "
                    f"{self._envelope.max_joint_velocity_rps} rad/s"
                ),
            )
        if observation.end_effector_force_n > (
            self._envelope.max_end_effector_force_n
        ):
            return AbortDirective(
                cause=ABORT_ENVELOPE_VIOLATION,
                detail=(
                    f"end-effector force {observation.end_effector_force_n}N "
                    f"exceeds {self._envelope.max_end_effector_force_n}N"
                ),
            )
        if not self._envelope.contains(observation.end_effector_position_m):
            return AbortDirective(
                cause=ABORT_ENVELOPE_VIOLATION,
                detail=(
                    "end-effector position "
                    f"{observation.end_effector_position_m} is outside the "
                    "workspace bounds"
                ),
            )
        return None
