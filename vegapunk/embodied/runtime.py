"""A deterministic actuation implementation of the ``SkillRuntime`` boundary.

The profile's guarantees are all stated elsewhere; this module is the first
thing that actually moves a robot, and it is deliberately the least clever
component in the system. It needs no checkpoint, makes the same commands given
the same measured state, and can therefore be reasoned about offline and
replayed. It exists so the governed loop can be exercised end to end on
hardware before any learned policy is admitted.

It commands one thing only: a bounded joint-space move towards a declared goal
pose. Every step moves each joint by at most one control period's worth of the
calibrated command rate towards the target.

That bound is a bound on the *command*, and the distinction is load-bearing
rather than pedantic. A position-controlled joint does not travel at the rate
its setpoint spacing implies: it accelerates towards each new setpoint,
overshoots the average, and settles, all inside one control period. A runtime
handed the envelope's velocity limit as its command rate therefore breaches
that envelope, and the lower the control frequency the worse the breach.

How far past the command rate a servo goes is a property of one robot at one
control frequency. It cannot be derived here and it must not be guessed, so
``CommandRateCalibration`` is not a setting but a measurement: the rate that
was commanded and the peak joint velocity that rate was *observed* to produce,
taken together from one probe on a named configuration by
``vegapunk.embodied.calibration``. This runtime compares that measured peak
against the envelope it was handed and refuses a configuration that does not
fit. The supervisor still judges every observation; this refusal exists so a
run that was never admissible is rejected at construction instead of being
discovered by an abort halfway through a physical motion.

Four refusals matter more than the motion:

- A command rate whose measured peak exceeds the envelope cannot be
  constructed. Finding that out by abort costs a human's supervised run and
  quarantines the configuration.
- A goal whose tolerance is tighter than the calibration's measured resting
  droop cannot be registered. Such a goal reports a failed verification on
  every run while the robot sits exactly where it was told to go, which is a
  configuration error wearing the costume of a physical fault.
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
from vegapunk.embodied.safety import (
    AbortDirective,
    Observation,
    SafetyEnvelope,
)
from vegapunk.embodied.skill import SkillSelection

_DEFAULT_TOLERANCE_RAD = 0.01

_TOLERANCE_MARGIN = 1.5
"""How much slack a goal tolerance needs beyond the measured resting droop.

A defensible default, not a measured one. The probe's droop was measured on one
pose under one load; a skill's goal pose carries a different moment arm, so the
floor derived from it needs room. Kept as one named constant so the first real
evidence can move it deliberately.
"""


def bounded_waypoint(
    previous_setpoint_rad: Sequence[float],
    measured_rad: Sequence[float],
    target_rad: Sequence[float],
    max_step_rad: float,
    max_lead_rad: float,
) -> tuple[float, ...]:
    """One control period's setpoint: towards the target, never faster.

    The single rule that defines what this runtime commands, factored out
    because calibration has to command exactly the same motion it is
    measuring. A probe that ramped differently would measure a different
    robot.

    The step is taken from the *previous setpoint*, not from the measured
    position, and the distinction decides whether the motion converges at all.
    A position servo tracks a moving setpoint with a standing lag: it sits
    behind by however much error its gain needs to hold the joint against
    gravity. Re-deriving each setpoint from the measured position subtracts
    that lag from every step, so the commanded rate is silently reduced; and
    once the lag exceeds one step -- which it does at low rates, where the step
    is small and the lag is unchanged -- the next setpoint lands *behind* the
    current one and the joint creeps away from its target forever. Integrating
    the ramp keeps the commanded trajectory a property of the command alone.

    ``max_lead_rad`` is what measurement is still needed for. An integrated
    ramp that ignored the robot would keep advancing into a joint that is
    blocked, and a position servo answers a setpoint it cannot reach by pulling
    harder, so the runaway is a torque ramp rather than a motion. Clamping the
    setpoint to within ``max_lead_rad`` of the measured position bounds that
    error: a joint under unexpected load pulls its own setpoint back and the
    motion slows to whatever the robot can actually do, which is a degradation
    rather than an abort. The leash cannot be derived here -- it is the servo's
    own lag, a property of one robot's gains -- so it comes from the same probe
    that measured the rate.
    """
    return tuple(
        min(
            max(
                previous
                + max(-max_step_rad, min(max_step_rad, target - previous)),
                measured - max_lead_rad,
            ),
            measured + max_lead_rad,
        )
        for previous, measured, target in zip(
            previous_setpoint_rad, measured_rad, target_rad
        )
    )


@dataclass(frozen=True)
class CommandRateCalibration:
    """A measured pair: a commanded joint rate, and the peak it actually caused.

    Both numbers come from one probe, which is the point. A ratio carried apart
    from the rate it was measured at invites the one piece of arithmetic nobody
    can justify -- scaling a measurement to a rate that was never tried -- so
    the only way to change the command rate is to measure again.

    ``control_frequency_hz`` belongs to the measurement rather than sitting
    beside it as a separate setting: the same servo overshoots differently when
    setpoints arrive at a different cadence. ``measured_on`` names the
    configuration, because a peak measured elsewhere is not a fact about this
    robot.

    ``tracking_error_rad`` is the second thing one probe reports: the largest
    gap observed between the commanded setpoint and the measured position while
    the ramp was running. It is the servo's standing lag under load at this
    rate, and the runtime uses it as the leash that stops an integrated ramp
    from running away from a blocked joint. It belongs to the same measurement
    for the same reason the peak does: it is a property of one robot's gains at
    one cadence, and a lag borrowed from another configuration would loosen or
    throttle this one's motion by an unmeasured amount.

    ``settled_error_rad`` is the gap that remained once the ramp stopped and the
    joints came to rest on the final setpoint. It is the droop a position servo
    holds against gravity, and it is the reason a goal tolerance is not a free
    choice: a tolerance tighter than this measured residue can never be
    satisfied, so every run would report a failed verification while the robot
    was in fact exactly where it was told to go. ``minimum_goal_tolerance_rad``
    states that floor rather than leaving each caller to rediscover it.
    """

    commanded_rate_rps: float
    peak_joint_velocity_rps: float
    control_frequency_hz: float
    measured_on: str
    tracking_error_rad: float = 0.0
    settled_error_rad: float = 0.0

    def __post_init__(self) -> None:
        if self.commanded_rate_rps <= 0:
            raise ValueError("commanded_rate_rps must be positive")
        if self.peak_joint_velocity_rps <= 0:
            raise ValueError(
                "a calibration whose measured peak is zero is not a "
                "measurement of motion: the probe never moved the robot"
            )
        if self.control_frequency_hz <= 0:
            raise ValueError("control_frequency_hz must be positive")
        if not self.measured_on:
            raise ValueError(
                "a calibration must name the configuration it was measured "
                "on; an undeclared provenance is not a measurement"
            )
        if self.tracking_error_rad < 0:
            raise ValueError("tracking_error_rad cannot be negative")
        if self.settled_error_rad < 0:
            raise ValueError("settled_error_rad cannot be negative")

    @property
    def overshoot_ratio(self) -> float:
        """How far past the commanded rate the joints were seen to go."""
        return self.peak_joint_velocity_rps / self.commanded_rate_rps

    @property
    def max_step_rad(self) -> float:
        """The largest setpoint change one control period may command."""
        return self.commanded_rate_rps / self.control_frequency_hz

    @property
    def max_lead_rad(self) -> float:
        """How far ahead of the measured position a setpoint may sit.

        The measured lag plus one step: the servo is already this far behind
        when tracking normally, and the ramp is entitled to advance one more
        step before the robot has answered. A leash any tighter would throttle
        the motion the probe itself measured; any looser and a blocked joint
        would be handed a growing position error, which a position servo answers
        with torque.
        """
        return self.tracking_error_rad + self.max_step_rad

    @property
    def minimum_goal_tolerance_rad(self) -> float:
        """The tightest goal tolerance this configuration can actually reach.

        The measured resting droop, plus the tolerance's own margin for the
        fact that a skill's pose is not the pose this probe flew. A goal
        declared tighter than this is unreachable by construction.
        """
        return self.settled_error_rad * _TOLERANCE_MARGIN

    def fits_within(self, envelope: SafetyEnvelope) -> bool:
        """Whether the measured peak stays inside the envelope's velocity limit."""
        return (
            self.peak_joint_velocity_rps <= envelope.max_joint_velocity_rps
        )


@dataclass(frozen=True)
class RobotState:
    """One raw sensor snapshot, before any governance interpretation.

    This is what a hardware adapter reports. It is a superset of the safety
    view: ``Observation`` is derived from it, and the joint positions the
    controller needs to close its own loop stay here.

    ``joint_velocity_rps`` and ``end_effector_force_n`` are the one place this
    snapshot is not instantaneous, and the difference is load-bearing. The
    safety envelope bounds every instant, but a caller can only look between
    control periods, so an adapter that reports the value at the moment of the
    call hides whatever happened while nobody was asking. On a position-
    controlled joint that gap is the entire motion: the joint accelerates,
    peaks and settles inside one period, so the boundary sample reads near rest
    while the peak was several times the limit. Both fields must therefore
    report the largest magnitude observed since the previous read. Reporting
    the instant is a silent envelope hole.
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
        """Report the measured state without commanding motion.

        Velocity and force are peaks over the interval since the previous
        call, per ``RobotState``, so a read between control periods cannot
        miss a violation that happened inside one.
        """

    def command_joint_positions(self, positions_rad: Sequence[float]) -> None:
        """Command one joint-space waypoint."""

    def hold(self) -> None:
        """Stop motion and hold the current pose immediately."""


class ResettableRobot(Protocol):
    """A robot that can be returned to a known, optionally displaced pose.

    This is the one capability that separates a simulator from hardware, and it
    is load-bearing rather than convenient: a real G1 cannot be teleported to an
    initial condition. Anything that needs to repeat a run from a chosen start
    -- a campaign varying initial conditions, a probe re-running one motion at a
    different rate -- therefore cannot drive hardware even by accident.
    """

    def reset(
        self, joint_offsets_rad: Optional[Sequence[float]] = None
    ) -> None:
        """Return to the start pose, displaced by the given joint offsets."""


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
        command_rate: CommandRateCalibration,
        envelope: SafetyEnvelope,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if not command_rate.fits_within(envelope):
            raise ValueError(
                f"commanding {command_rate.commanded_rate_rps} rad/s at "
                f"{command_rate.control_frequency_hz}Hz was measured on "
                f"{command_rate.measured_on} to peak at "
                f"{command_rate.peak_joint_velocity_rps:.4f} rad/s, above the "
                f"envelope limit {envelope.max_joint_velocity_rps} rad/s; "
                "this run would be aborted partway through its motion, so it "
                "is refused before anything moves"
            )

        tolerance_floor = command_rate.minimum_goal_tolerance_rad

        registered: dict[str, JointPoseGoal] = {}
        for goal in goals:
            if goal.skill_version_id in registered:
                raise ValueError(
                    f"goal for {goal.skill_version_id!r} is registered twice"
                )
            if goal.tolerance_rad < tolerance_floor:
                raise ValueError(
                    f"goal for {goal.skill_version_id!r} declares a tolerance "
                    f"of {goal.tolerance_rad} rad, tighter than the "
                    f"{tolerance_floor:.4f} rad floor implied by the "
                    f"{command_rate.settled_error_rad:.4f} rad resting error "
                    f"measured on {command_rate.measured_on}; reaching it "
                    "would never be observed, so every run would report a "
                    "failed verification for a robot that arrived"
                )
            registered[goal.skill_version_id] = goal

        self._robot = robot
        self._goals = registered
        self._command_rate = command_rate
        self._frequency_hz = command_rate.control_frequency_hz
        self._max_step_rad = command_rate.max_step_rad
        self._max_lead_rad = command_rate.max_lead_rad
        self._tolerance_floor = tolerance_floor
        self._clock = clock if clock is not None else time.monotonic

        self._goal: Optional[JointPoseGoal] = None
        self._started_at: Optional[float] = None
        self._setpoint: Optional[tuple[float, ...]] = None
        self._aborted = False
        self._finished = False
        self._reached = False

    @property
    def max_step_rad(self) -> float:
        """The largest joint change ever commanded in one step."""
        return self._max_step_rad

    @property
    def max_lead_rad(self) -> float:
        """How far ahead of the measured position this runtime will command."""
        return self._max_lead_rad

    @property
    def minimum_goal_tolerance_rad(self) -> float:
        """The tightest goal tolerance this configuration can demonstrate."""
        return self._tolerance_floor

    @property
    def command_rate(self) -> CommandRateCalibration:
        """The measurement this runtime's motion bound rests on.

        Exposed so a caller can report the velocity margin it is running with,
        and so a reviewer can see which measurement was in force.
        """
        return self._command_rate

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
        # The ramp is seeded from where the robot actually is, once. Every
        # later setpoint is integrated from this one rather than re-derived
        # from measurement, so the commanded rate stays the commanded rate.
        self._setpoint = tuple(state.joint_positions_rad)
        self._started_at = self._clock()

    def step(self) -> RuntimeStep:
        if self._goal is None or self._started_at is None or self._setpoint is None:
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

        waypoint = bounded_waypoint(
            self._setpoint,
            measured,
            goal.target_joint_positions_rad,
            self._max_step_rad,
            self._max_lead_rad,
        )
        self._setpoint = waypoint
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
