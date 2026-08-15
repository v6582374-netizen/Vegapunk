"""How fast this robot may be *told* to move, measured rather than chosen.

``runtime.py`` bounds what it commands, and ``safety.py`` bounds what the robot
is observed to do. Those are not the same number. A position-controlled joint
handed a setpoint one control period ahead does not travel at the rate that
spacing implies: it accelerates towards the setpoint, peaks above the average,
and settles, all inside the period nobody is looking at. So a runtime handed the
envelope's velocity limit as its command rate breaches that envelope, and the
lower the control frequency the worse the breach.

The size of that gap is a property of one robot's servo gains at one control
frequency. It cannot be derived from the envelope and it must not be guessed.
This module measures it: it commands exactly the motion the runtime commands,
at a candidate rate, and reports the peak velocity that rate was *observed* to
produce as one inseparable ``CommandRateCalibration``.

Five refusals define what a measurement here is worth:

- It refuses to probe hardware. Escalating a command rate until something
  breaches an envelope is the one experiment that must never run on a real G1,
  and repeating a motion from an identical start is impossible there anyway. A
  probe therefore requires ``reset``, and rejects a robot that admits to being
  real.
- It refuses a motion too short to saturate the step bound. If every step lands
  inside the bound, the probe measured the distance travelled and learned
  nothing about the rate.
- It refuses a measurement whose peak force says the probe hit something. That
  velocity peak would be a fact about a collision, not about the servo.
- It refuses to interpolate. The ladder measures every candidate rate it
  reports; a rate nobody tried is not calibrated. In particular it does not
  bisect, because bisection assumes that a rate which fits implies every slower
  rate fits, and a servo is under no obligation to be monotone. The ladder
  measures all of them and names the inversion when it finds one.
- It refuses to spend the whole envelope. The probe measured one trajectory,
  and a skill will fly a different one; the admitted rate must peak at or below
  a declared fraction of the limit so the supervisor is not the first thing to
  notice the difference.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Optional, Sequence

from vegapunk.embodied.runtime import (
    CommandRateCalibration,
    ResettableRobot,
    RobotInterface,
    RobotState,
    bounded_waypoint,
)
from vegapunk.embodied.safety import SafetyEnvelope

_PROBE_TOLERANCE_RAD = 0.01
_MIN_SATURATED_STEPS = 5
_DEFAULT_SETTLE_STEPS = 10
_STEP_BUDGET_FACTOR = 4

DEFAULT_VELOCITY_MARGIN = 0.8
"""The fraction of the envelope's velocity limit an admitted rate may reach.

A defensible default, not a measured one. The probe flies one trajectory from
one start; a skill flies a different one, and the difference has to land
somewhere other than in an abort. Kept as one named constant so the first real
evidence can move it deliberately.
"""


def _largest_gap(
    setpoint_rad: Sequence[float], measured_rad: Sequence[float]
) -> float:
    """The widest gap between what was commanded and what the robot did."""
    return max(
        (
            abs(commanded - measured)
            for commanded, measured in zip(setpoint_rad, measured_rad)
        ),
        default=0.0,
    )


def _peak_velocity(state: RobotState) -> float:
    """The largest joint-velocity magnitude in one reported interval.

    ``RobotState`` requires velocity to be the peak since the previous read, so
    this reduces an interval that already happened rather than sampling an
    instant.
    """
    if not state.joint_velocity_rps:
        return 0.0
    return max(abs(value) for value in state.joint_velocity_rps)


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ProbeMotion:
    """The one motion every candidate rate is measured on.

    Holding the motion fixed across rates is what makes the resulting numbers
    comparable: two peaks measured on two different trajectories say nothing
    about which rate is faster. ``start_offsets_rad`` is applied through the
    robot's own reset, so the probe begins each measurement from the same place
    rather than wherever the previous one stopped.
    """

    target_joint_positions_rad: tuple[float, ...]
    start_offsets_rad: tuple[float, ...] = ()
    settle_steps: int = _DEFAULT_SETTLE_STEPS

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_joint_positions_rad",
            tuple(float(value) for value in self.target_joint_positions_rad),
        )
        object.__setattr__(
            self,
            "start_offsets_rad",
            tuple(float(value) for value in self.start_offsets_rad),
        )
        if not self.target_joint_positions_rad:
            raise ValueError("a probe motion declares no target joints")
        if self.settle_steps < 1:
            raise ValueError(
                "settle_steps must be at least one: a servo's largest "
                "velocity is often reached while it settles onto the final "
                "setpoint, and a probe that stops commanding on arrival never "
                "observes it"
            )

    def digest(self) -> str:
        return _digest(
            {
                "target_joint_positions_rad": [
                    round(value, 9)
                    for value in self.target_joint_positions_rad
                ],
                "start_offsets_rad": [
                    round(value, 9) for value in self.start_offsets_rad
                ],
                "settle_steps": self.settle_steps,
            }
        )


class CommandRateProbe:
    """Runs one motion at one commanded rate and reports the peak it caused.

    The probe commands through ``bounded_waypoint``, the same function the
    runtime commands through, because a probe that ramped differently would be
    measuring a different controller. It never calls ``hold``: a latched robot
    cannot be measured again, and the next measurement's ``reset`` is what
    returns the robot to a known start.
    """

    def __init__(
        self,
        robot: RobotInterface,
        motion: ProbeMotion,
        envelope: SafetyEnvelope,
        control_frequency_hz: float,
        measured_on: str,
    ) -> None:
        if control_frequency_hz <= 0:
            raise ValueError("control_frequency_hz must be positive")
        if not measured_on:
            raise ValueError(
                "a probe must name the configuration it measures; an "
                "unattributed peak is not a fact about any robot"
            )
        reset = getattr(robot, "reset", None)
        if not callable(reset):
            raise TypeError(
                "calibration requires a robot that can be reset to a known "
                "start, so every candidate rate is measured on the same "
                "motion; hardware cannot be, which is the point"
            )
        if getattr(robot, "is_real_robot", False):
            raise ValueError(
                "refusing to probe command rates on a real robot: this "
                "procedure deliberately pushes a rate until the measured peak "
                "leaves the envelope, which is an experiment that belongs in "
                "simulation"
            )

        self._robot = robot
        self._resettable: ResettableRobot = robot  # type: ignore[assignment]
        self._motion = motion
        self._envelope = envelope
        self._frequency_hz = float(control_frequency_hz)
        self._measured_on = measured_on

    @property
    def envelope(self) -> SafetyEnvelope:
        return self._envelope

    @property
    def motion(self) -> ProbeMotion:
        return self._motion

    @property
    def control_frequency_hz(self) -> float:
        return self._frequency_hz

    @property
    def measured_on(self) -> str:
        return self._measured_on

    def measure(self, commanded_rate_rps: float) -> CommandRateCalibration:
        """Command the motion at ``commanded_rate_rps`` and report the peak.

        The ramp runs until the *setpoint* arrives at the target, not until the
        measured position does. That is the command this probe exists to
        characterise, and it is the one termination condition that cannot be
        confounded by the very lag being measured: a servo holding a joint
        against gravity settles a fixed distance short of its setpoint, so a
        probe waiting for the measurement to arrive would either spin out its
        budget or, worse, silently report the budget's end as an arrival.

        Settling then holds that final setpoint rather than jumping to the raw
        target, because the leash may legitimately have held the ramp back and
        commanding the target directly would measure a step response nothing in
        this system ever commands.
        """
        if commanded_rate_rps <= 0:
            raise ValueError("commanded_rate_rps must be positive")

        max_step_rad = commanded_rate_rps / self._frequency_hz
        target = self._motion.target_joint_positions_rad

        self._resettable.reset(
            joint_offsets_rad=self._motion.start_offsets_rad or None
        )
        state = self._robot.read_state()
        positions = state.joint_positions_rad
        if len(positions) != len(target):
            raise ValueError(
                f"probe motion targets {len(target)} joints but "
                f"{self._measured_on} reported {len(positions)}"
            )

        # The probe measures the servo's own lag, so it cannot be leashed by a
        # lag it has not measured yet. It runs the ramp unleashed and reports
        # what the gap turned out to be; the force ceiling below is what stops
        # a blocked joint from being ramped into indefinitely.
        unleashed = float("inf")
        setpoint = tuple(positions)
        peak_velocity = 0.0
        peak_force = 0.0
        tracking_error = 0.0
        saturated_steps = 0
        for _ in range(self._step_budget(positions, max_step_rad)):
            if self._arrived(setpoint, target):
                break
            if self._saturates(setpoint, target, max_step_rad):
                saturated_steps += 1
            setpoint = bounded_waypoint(
                setpoint, positions, target, max_step_rad, unleashed
            )
            self._robot.command_joint_positions(setpoint)
            state = self._robot.read_state()
            peak_velocity = max(peak_velocity, _peak_velocity(state))
            peak_force = max(peak_force, state.end_effector_force_n)
            positions = state.joint_positions_rad
            tracking_error = max(
                tracking_error, _largest_gap(setpoint, positions)
            )

        for _ in range(self._motion.settle_steps):
            self._robot.command_joint_positions(setpoint)
            state = self._robot.read_state()
            peak_velocity = max(peak_velocity, _peak_velocity(state))
            peak_force = max(peak_force, state.end_effector_force_n)
            positions = state.joint_positions_rad

        settled_error = _largest_gap(setpoint, positions)

        if saturated_steps < _MIN_SATURATED_STEPS:
            raise ValueError(
                f"commanding {commanded_rate_rps} rad/s saturated the step "
                f"bound on only {saturated_steps} of the probe's steps; below "
                f"{_MIN_SATURATED_STEPS} the motion is too short to be a "
                "measurement of the rate rather than of the distance"
            )
        if peak_force > self._envelope.max_end_effector_force_n:
            raise ValueError(
                f"the probe peaked at {peak_force:.3f}N, above the envelope's "
                f"{self._envelope.max_end_effector_force_n}N; it hit "
                "something, so its velocity peak is a fact about a collision "
                "and not about the servo"
            )
        if not self._arrived(setpoint, target):
            raise ValueError(
                f"commanding {commanded_rate_rps} rad/s did not ramp the "
                f"setpoint onto the probe's target within its step budget; the "
                "measurement describes an unfinished motion and is discarded"
            )

        return CommandRateCalibration(
            commanded_rate_rps=float(commanded_rate_rps),
            peak_joint_velocity_rps=peak_velocity,
            control_frequency_hz=self._frequency_hz,
            measured_on=self._measured_on,
            tracking_error_rad=tracking_error,
            settled_error_rad=settled_error,
        )

    def _step_budget(
        self, positions: Sequence[float], max_step_rad: float
    ) -> int:
        largest = max(
            (
                abs(target - current)
                for current, target in zip(
                    positions, self._motion.target_joint_positions_rad
                )
            ),
            default=0.0,
        )
        needed = math.ceil(largest / max_step_rad) if largest > 0 else 0
        return max(1, needed * _STEP_BUDGET_FACTOR)

    @staticmethod
    def _arrived(
        setpoint: Sequence[float], target: Sequence[float]
    ) -> bool:
        """Whether the commanded ramp has landed on the target.

        Compared exactly rather than within a tolerance: the setpoint is
        arithmetic this module performed, not something it measured.
        """
        return all(
            commanded == goal for commanded, goal in zip(setpoint, target)
        )

    @staticmethod
    def _saturates(
        setpoint: Sequence[float],
        target: Sequence[float],
        max_step_rad: float,
    ) -> bool:
        return any(
            abs(goal - commanded) >= max_step_rad
            for commanded, goal in zip(setpoint, target)
        )


@dataclass(frozen=True)
class CalibrationReport:
    """Every rate that was tried, and the fastest one that may be commanded.

    The rejected measurements are kept rather than discarded. They are the
    evidence that the admitted rate is the fastest safe one instead of the
    first one somebody guessed, and an inversion among them is a finding about
    the robot that a reviewer needs to see.
    """

    measured_on: str
    control_frequency_hz: float
    velocity_limit_rps: float
    margin: float
    measurements: tuple[CommandRateCalibration, ...]
    admitted: Optional[CommandRateCalibration]
    findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "measurements", tuple(self.measurements))
        object.__setattr__(self, "findings", tuple(self.findings))

    @property
    def budget_rps(self) -> float:
        """The peak an admitted rate may reach: the limit, less the margin."""
        return self.velocity_limit_rps * self.margin

    def digest(self) -> str:
        return _digest(
            {
                "measured_on": self.measured_on,
                "control_frequency_hz": self.control_frequency_hz,
                "velocity_limit_rps": self.velocity_limit_rps,
                "margin": self.margin,
                "measurements": [
                    {
                        "commanded_rate_rps": round(item.commanded_rate_rps, 9),
                        "peak_joint_velocity_rps": round(
                            item.peak_joint_velocity_rps, 9
                        ),
                    }
                    for item in self.measurements
                ],
                "admitted": (
                    None
                    if self.admitted is None
                    else round(self.admitted.commanded_rate_rps, 9)
                ),
            }
        )


def calibrate_command_rate(
    probe: CommandRateProbe,
    candidate_rates_rps: Sequence[float],
    margin: float = DEFAULT_VELOCITY_MARGIN,
) -> CalibrationReport:
    """Measure every candidate rate; admit the fastest that fits the budget.

    Slowest first, so an unexpectedly violent robot is discovered at the rate
    least likely to damage it. Every candidate is measured even after one fails,
    because a peak that stops rising with the commanded rate is the inversion
    this procedure exists to notice, and a search that stopped early would
    report it as a clean result.
    """
    if not candidate_rates_rps:
        raise ValueError(
            "calibration needs at least one candidate rate to measure; there "
            "is no rate this procedure will propose on its own"
        )
    if not 0 < margin <= 1:
        raise ValueError("margin must be within (0, 1]")

    ordered = sorted(float(rate) for rate in candidate_rates_rps)
    if len(set(ordered)) != len(ordered):
        raise ValueError("candidate rates must be distinct")

    budget = probe.envelope.max_joint_velocity_rps * margin
    measurements = tuple(probe.measure(rate) for rate in ordered)

    findings: list[str] = []
    previous: Optional[CommandRateCalibration] = None
    for measurement in measurements:
        if (
            previous is not None
            and measurement.peak_joint_velocity_rps
            < previous.peak_joint_velocity_rps
        ):
            findings.append(
                f"commanding {measurement.commanded_rate_rps} rad/s peaked at "
                f"{measurement.peak_joint_velocity_rps:.4f} rad/s, below the "
                f"{previous.peak_joint_velocity_rps:.4f} rad/s measured at the "
                f"slower {previous.commanded_rate_rps} rad/s; the peak is not "
                "monotone in the commanded rate on this configuration"
            )
        previous = measurement

    fitting = [
        measurement
        for measurement in measurements
        if measurement.peak_joint_velocity_rps <= budget
    ]
    admitted: Optional[CommandRateCalibration] = None
    if fitting:
        candidate = fitting[-1]
        breached_below = [
            measurement
            for measurement in measurements
            if measurement.commanded_rate_rps < candidate.commanded_rate_rps
            and measurement.peak_joint_velocity_rps > budget
        ]
        if breached_below:
            findings.append(
                f"{candidate.commanded_rate_rps} rad/s fits the budget but "
                f"{len(breached_below)} slower rate(s) did not, so no rate is "
                "admitted: a bound that does not hold for every slower rate "
                "cannot be trusted for a trajectory this probe never flew"
            )
        else:
            admitted = candidate
    else:
        findings.append(
            f"no candidate rate peaked at or below {budget:.4f} rad/s; the "
            "slowest rate tried is still too fast for this envelope, or the "
            "envelope is tighter than this robot can be commanded"
        )

    return CalibrationReport(
        measured_on=probe.measured_on,
        control_frequency_hz=probe.control_frequency_hz,
        velocity_limit_rps=probe.envelope.max_joint_velocity_rps,
        margin=float(margin),
        measurements=measurements,
        admitted=admitted,
        findings=tuple(findings),
    )
