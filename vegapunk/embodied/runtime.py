"""A deterministic actuation implementation of the ``SkillRuntime`` boundary.

The profile's guarantees are all stated elsewhere; this module is the first
thing that actually moves a robot, and it is deliberately the least clever
component in the system. It needs no checkpoint, makes the same commands given
the same measured state, and can therefore be reasoned about offline and
replayed. It exists so the governed loop can be exercised end to end on
hardware before any learned policy is admitted.

It commands one thing only: a bounded joint-space move towards a declared goal
pose. Every step moves each joint by at most one control period's worth of the
declared velocity limit, so the commands are inside the safety envelope by
construction rather than by the supervisor's intervention. The supervisor still
judges every observation; this runtime simply does not rely on being stopped.

Three refusals matter more than the motion:

- A skill with no registered goal cannot start. An actuator that improvises a
  target for an unrecognised request is worse than one that refuses.
- After ``abort``, no later call commands motion again. Stopping is latched,
  not advisory, so a caller that keeps stepping cannot walk a stopped robot.
- ``postconditions`` reports only what was measured. A condition this runtime
  cannot observe is omitted rather than assumed, which the loop correctly reads
  as a failed verification.

``RobotInterface`` is the seam a real G1 SDK adapter fills. Keeping it separate
from ``SkillRuntime`` means the hardware adapter carries no policy at all: it
reads sensors, it commands joints, it holds.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Protocol, Sequence

from vegapunk.embodied.loop import RuntimeStep
from vegapunk.embodied.safety import AbortDirective, Observation
from vegapunk.embodied.skill import SkillSelection

_DEFAULT_TOLERANCE_RAD = 0.01


@dataclass(frozen=True)
class RobotState:
    """One raw sensor snapshot, before any governance interpretation.

    This is what a hardware adapter reports. It is a superset of the safety
    view: ``Observation`` is derived from it, and the joint positions the
    controller needs to close its own loop stay here.
    """

    joint_positions_rad: tuple[float, ...]
    joint_velocity_rps: tuple[float, ...]
    end_effector_force_n: float
    end_effector_position_m: tuple[float, ...]
    guardian_present: bool
    estop_engaged: bool
    estop_reachable: bool
    workspace_clear: bool
    age_s: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "joint_positions_rad", tuple(self.joint_positions_rad)
        )
        object.__setattr__(
            self, "joint_velocity_rps", tuple(self.joint_velocity_rps)
        )
        object.__setattr__(
            self,
            "end_effector_position_m",
            tuple(self.end_effector_position_m),
        )
        if self.age_s < 0:
            raise ValueError("age_s cannot be negative")


class RobotInterface(Protocol):
    """The hardware seam: read sensors, command joints, hold.

    Implementations carry no governance logic. Anything that decides whether a
    move is allowed belongs above this boundary.
    """

    def read_state(self) -> RobotState:
        """Report the current measured state without commanding motion."""

    def command_joint_positions(self, positions_rad: Sequence[float]) -> None:
        """Command one joint-space waypoint."""

    def hold(self) -> None:
        """Stop motion and hold the current pose immediately."""


@dataclass(frozen=True)
class JointPoseGoal:
    """A reviewed target pose for one skill revision.

    ``satisfies`` names only the postconditions reaching this pose actually
    demonstrates. It is deliberately not the skill's full postcondition list:
    claiming a condition this controller cannot measure is the failure mode the
    loop's verification step exists to catch.
    """

    skill_version_id: str
    target_joint_positions_rad: tuple[float, ...]
    satisfies: tuple[str, ...]
    tolerance_rad: float = _DEFAULT_TOLERANCE_RAD

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_joint_positions_rad",
            tuple(float(value) for value in self.target_joint_positions_rad),
        )
        object.__setattr__(self, "satisfies", tuple(self.satisfies))
        if not self.skill_version_id:
            raise ValueError("a JointPoseGoal requires a skill_version_id")
        if not self.target_joint_positions_rad:
            raise ValueError(
                f"goal for {self.skill_version_id!r} declares no target joint "
                "positions"
            )
        if not self.satisfies:
            raise ValueError(
                f"goal for {self.skill_version_id!r} must name at least one "
                "postcondition it demonstrates, or reaching it proves nothing"
            )
        if self.tolerance_rad <= 0:
            raise ValueError("tolerance_rad must be positive")

    def reached(self, positions_rad: Sequence[float]) -> bool:
        if len(positions_rad) != len(self.target_joint_positions_rad):
            return False
        return all(
            abs(measured - target) <= self.tolerance_rad
            for measured, target in zip(
                positions_rad, self.target_joint_positions_rad
            )
        )


class DeterministicJointRuntime:
    """Moves a robot to registered goal poses under bounded joint steps.

    One instance runs one skill at a time: ``start`` binds the goal, ``step``
    advances it, and neither can be replayed on the same instance. Reusing a
    runtime across runs would let a second run inherit the first one's motion
    state, so it is rejected.
    """

    def __init__(
        self,
        robot: RobotInterface,
        goals: Sequence[JointPoseGoal],
        control_frequency_hz: float,
        max_joint_velocity_rps: float,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if control_frequency_hz <= 0:
            raise ValueError("control_frequency_hz must be positive")
        if max_joint_velocity_rps <= 0:
            raise ValueError("max_joint_velocity_rps must be positive")

        registered: dict[str, JointPoseGoal] = {}
        for goal in goals:
            if goal.skill_version_id in registered:
                raise ValueError(
                    f"goal for {goal.skill_version_id!r} is registered twice"
                )
            registered[goal.skill_version_id] = goal

        self._robot = robot
        self._goals = registered
        self._frequency_hz = float(control_frequency_hz)
        self._max_step_rad = max_joint_velocity_rps / control_frequency_hz
        self._clock = clock if clock is not None else time.monotonic

        self._goal: Optional[JointPoseGoal] = None
        self._started_at: Optional[float] = None
        self._aborted = False
        self._finished = False
        self._reached = False

    @property
    def max_step_rad(self) -> float:
        """The largest joint change ever commanded in one step."""
        return self._max_step_rad

    def goal_for(self, selection: SkillSelection) -> JointPoseGoal:
        """Resolve the registered goal, or refuse the selection."""
        try:
            return self._goals[selection.skill_version_id]
        except KeyError as error:
            raise KeyError(
                f"no goal pose is registered for "
                f"{selection.skill_version_id!r}; this runtime will not "
                "improvise a physical target"
            ) from error

    def required_duration_s(self, selection: SkillSelection) -> float:
        """Estimate the move's duration from the current measured pose.

        Callers can compare this against a skill's ``max_duration_s`` before
        asking a human to stand next to the robot, rather than finding out
        the move was never feasible by being aborted halfway through it.
        """
        goal = self.goal_for(selection)
        positions = self._robot.read_state().joint_positions_rad
        self._require_matching_width(goal, positions)
        return self._steps_remaining(goal, positions) / self._frequency_hz

    def observe(self) -> Observation:
        return self._observation(self._robot.read_state())

    def start(self, selection: SkillSelection) -> None:
        if self._started_at is not None:
            raise RuntimeError(
                "this runtime already ran a skill; construct a new one "
                "per run so motion state cannot leak between runs"
            )
        goal = self.goal_for(selection)
        state = self._robot.read_state()
        self._require_matching_width(goal, state.joint_positions_rad)
        self._goal = goal
        self._started_at = self._clock()

    def step(self) -> RuntimeStep:
        if self._goal is None or self._started_at is None:
            raise RuntimeError("step() was called before start()")
        if self._aborted:
            raise RuntimeError(
                "this runtime was aborted and will not command motion again"
            )
        if self._finished:
            raise RuntimeError(
                "this runtime already reported completion; it will not "
                "command further motion"
            )

        goal = self._goal
        measured = self._robot.read_state().joint_positions_rad
        self._require_matching_width(goal, measured)

        waypoint = tuple(
            current
            + max(
                -self._max_step_rad,
                min(self._max_step_rad, target - current),
            )
            for current, target in zip(
                measured, goal.target_joint_positions_rad
            )
        )
        self._robot.command_joint_positions(waypoint)

        state = self._robot.read_state()
        self._require_matching_width(goal, state.joint_positions_rad)
        self._reached = goal.reached(state.joint_positions_rad)
        if self._reached:
            self._finished = True
        return RuntimeStep(
            observation=self._observation(state), complete=self._reached
        )

    def abort(self, directive: AbortDirective) -> None:
        self._aborted = True
        self._robot.hold()

    def postconditions(self) -> Mapping[str, bool]:
        """Report the measured truth of the goal's own postconditions.

        Nothing else is reported. The loop treats an unmeasured postcondition
        as a failed verification, which is the correct reading: this controller
        knows where its joints are and nothing more.
        """
        if self._goal is None:
            return {}
        reached = self._reached and not self._aborted
        return {condition: reached for condition in self._goal.satisfies}

    def _observation(self, state: RobotState) -> Observation:
        return Observation(
            elapsed_s=self._elapsed_s(),
            age_s=state.age_s,
            joint_velocity_rps=state.joint_velocity_rps,
            end_effector_force_n=state.end_effector_force_n,
            end_effector_position_m=state.end_effector_position_m,
            guardian_present=state.guardian_present,
            estop_engaged=state.estop_engaged,
            estop_reachable=state.estop_reachable,
            workspace_clear=state.workspace_clear,
        )

    def _elapsed_s(self) -> float:
        if self._started_at is None:
            return 0.0
        return max(0.0, self._clock() - self._started_at)

    def _steps_remaining(
        self, goal: JointPoseGoal, positions_rad: Sequence[float]
    ) -> int:
        largest = max(
            (
                abs(target - current)
                for current, target in zip(
                    positions_rad, goal.target_joint_positions_rad
                )
            ),
            default=0.0,
        )
        if largest <= goal.tolerance_rad:
            return 0
        return math.ceil(largest / self._max_step_rad)

    @staticmethod
    def _require_matching_width(
        goal: JointPoseGoal, positions_rad: Sequence[float]
    ) -> None:
        expected = len(goal.target_joint_positions_rad)
        if len(positions_rad) != expected:
            raise ValueError(
                f"goal for {goal.skill_version_id!r} targets {expected} "
                f"joints but the robot reported {len(positions_rad)}"
            )
