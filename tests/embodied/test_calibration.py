from __future__ import annotations

import importlib.util
import unittest

from vegapunk.embodied.calibration import (
    DEFAULT_VELOCITY_MARGIN,
    CalibrationReport,
    CommandRateProbe,
    ProbeMotion,
    calibrate_command_rate,
)
from vegapunk.embodied.runtime import (
    CommandRateCalibration,
    DeterministicJointRuntime,
    JointPoseGoal,
    RobotState,
)
from vegapunk.embodied.safety import SafetyEnvelope

_DEPENDENCIES = ("numpy", "mujoco")
_MISSING = tuple(
    name for name in _DEPENDENCIES if importlib.util.find_spec(name) is None
)

if _MISSING:
    _HAS_SIMULATION = False
    _SKIP_REASON = f"missing simulation dependencies: {', '.join(_MISSING)}"
else:
    from vegapunk.embodied.simulation import DEFAULT_SCENE_PATH

    _HAS_SIMULATION = DEFAULT_SCENE_PATH.exists()
    _SKIP_REASON = f"the G1 MJCF scene is not present at {DEFAULT_SCENE_PATH}"

if _HAS_SIMULATION:
    from vegapunk.embodied.simulation import (
        G1_LEFT_ARM_JOINTS,
        SimulatedG1,
        SimulatedSupervision,
    )

_ENVELOPE = SafetyEnvelope(
    max_duration_s=20.0,
    max_joint_velocity_rps=1.5,
    max_end_effector_force_n=20.0,
    workspace_bounds_m=((-1.0, 1.0), (-1.0, 1.0), (-1.0, 2.0)),
)


class SpringRobot:
    """A two-joint robot whose velocity overshoots its setpoint spacing.

    The overshoot is what makes this a useful double: a robot that tracked
    exactly would let the calibration ladder pass while measuring nothing. Each
    command lands on the setpoint and reports a peak velocity of
    ``gain`` times the average rate that step implied, which is the shape of a
    real position servo's behaviour without pretending to be its dynamics.
    """

    is_real_robot = False

    def __init__(
        self,
        gain: float = 1.5,
        control_frequency_hz: float = 30.0,
        force_n: float = 1.0,
        peak_override=None,
    ) -> None:
        self.start = (0.0, 0.0)
        self.positions = self.start
        self.gain = gain
        self.control_frequency_hz = control_frequency_hz
        self.force_n = force_n
        self.peak_override = peak_override
        self.commands: list[tuple[float, ...]] = []
        self.resets = 0
        self.holds = 0
        self._peak_velocity = 0.0

    def reset(self, joint_offsets_rad=None) -> None:
        self.resets += 1
        offsets = tuple(joint_offsets_rad or (0.0,) * len(self.start))
        self.positions = tuple(
            base + offset for base, offset in zip(self.start, offsets)
        )
        self._peak_velocity = 0.0

    def read_state(self) -> RobotState:
        peak = self._peak_velocity
        self._peak_velocity = 0.0
        return RobotState(
            joint_positions_rad=self.positions,
            joint_velocity_rps=(peak,) * len(self.positions),
            end_effector_force_n=self.force_n,
            end_effector_position_m=(0.1, 0.0, 0.8),
            guardian_present=True,
            estop_engaged=False,
            estop_reachable=True,
            workspace_clear=True,
            age_s=0.01,
        )

    def command_joint_positions(self, positions_rad) -> None:
        target = tuple(float(value) for value in positions_rad)
        travelled = max(
            (abs(new - old) for old, new in zip(self.positions, target)),
            default=0.0,
        )
        average_rate = travelled * self.control_frequency_hz
        if self.peak_override is None:
            peak = average_rate * self.gain
        else:
            peak = self.peak_override(average_rate)
        self._peak_velocity = max(self._peak_velocity, peak)
        self.commands.append(target)
        self.positions = target

    def hold(self) -> None:
        self.holds += 1


class RealRobot(SpringRobot):
    is_real_robot = True


class UnresettableRobot:
    is_real_robot = False

    def read_state(self) -> RobotState:  # pragma: no cover - never reached
        raise AssertionError("a probe must refuse before reading")

    def command_joint_positions(self, positions_rad) -> None:
        raise AssertionError("a probe must refuse before commanding")

    def hold(self) -> None:
        raise AssertionError("a probe must refuse before holding")


def _motion(**overrides: object) -> ProbeMotion:
    fields: dict[str, object] = dict(target_joint_positions_rad=(1.0, -1.0))
    fields.update(overrides)
    return ProbeMotion(**fields)  # type: ignore[arg-type]


def _probe(robot: object, **overrides: object) -> CommandRateProbe:
    fields: dict[str, object] = dict(
        robot=robot,
        motion=_motion(),
        envelope=_ENVELOPE,
        control_frequency_hz=30.0,
        measured_on="SpringRobot at 30Hz",
    )
    fields.update(overrides)
    return CommandRateProbe(**fields)  # type: ignore[arg-type]


class ProbeMotionTests(unittest.TestCase):
    """The motion is fixed so two rates are comparable measurements."""

    def test_a_motion_with_no_target_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            ProbeMotion(target_joint_positions_rad=())

    def test_a_motion_that_never_settles_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            _motion(settle_steps=0)

    def test_the_digest_distinguishes_two_motions(self) -> None:
        self.assertNotEqual(
            _motion().digest(),
            _motion(target_joint_positions_rad=(0.5, -0.5)).digest(),
        )

    def test_the_digest_is_stable_for_the_same_motion(self) -> None:
        self.assertEqual(_motion().digest(), _motion().digest())


class ProbeRefusalTests(unittest.TestCase):
    """What the probe will not measure matters more than what it will."""

    def test_a_real_robot_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            _probe(RealRobot())
        self.assertIn("real robot", str(caught.exception))

    def test_a_robot_that_cannot_be_reset_is_refused(self) -> None:
        with self.assertRaises(TypeError) as caught:
            _probe(UnresettableRobot())
        self.assertIn("reset", str(caught.exception))

    def test_an_unattributed_probe_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            _probe(SpringRobot(), measured_on="")

    def test_a_non_positive_rate_is_refused(self) -> None:
        probe = _probe(SpringRobot())
        with self.assertRaises(ValueError):
            probe.measure(0.0)

    def test_a_motion_too_short_to_saturate_is_refused(self) -> None:
        """A move finished in two steps measured distance, not rate."""
        probe = _probe(
            SpringRobot(), motion=_motion(target_joint_positions_rad=(0.02, 0.0))
        )
        with self.assertRaises(ValueError) as caught:
            probe.measure(1.0)
        self.assertIn("too short", str(caught.exception))

    def test_a_probe_that_hit_something_is_refused(self) -> None:
        robot = SpringRobot(force_n=_ENVELOPE.max_end_effector_force_n + 1.0)
        with self.assertRaises(ValueError) as caught:
            _probe(robot).measure(0.5)
        self.assertIn("collision", str(caught.exception))

    def test_a_probe_never_holds_the_robot(self) -> None:
        """A latched robot cannot be measured again; reset is the way back."""
        robot = SpringRobot()
        _probe(robot).measure(0.5)
        self.assertEqual(robot.holds, 0)


class ProbeMeasurementTests(unittest.TestCase):
    """One rate in, one measured pair out."""

    def test_the_measurement_reports_the_rate_that_was_commanded(self) -> None:
        measurement = _probe(SpringRobot()).measure(0.5)
        self.assertAlmostEqual(measurement.commanded_rate_rps, 0.5)
        self.assertEqual(measurement.control_frequency_hz, 30.0)
        self.assertEqual(measurement.measured_on, "SpringRobot at 30Hz")

    def test_the_measured_peak_exceeds_the_commanded_rate(self) -> None:
        measurement = _probe(SpringRobot(gain=1.5)).measure(0.5)
        self.assertGreater(
            measurement.peak_joint_velocity_rps, measurement.commanded_rate_rps
        )
        self.assertAlmostEqual(measurement.overshoot_ratio, 1.5, places=3)

    def test_every_measurement_starts_from_the_same_pose(self) -> None:
        robot = SpringRobot()
        probe = _probe(robot)
        first = probe.measure(0.5)
        second = probe.measure(0.5)
        self.assertGreaterEqual(robot.resets, 2)
        self.assertAlmostEqual(
            first.peak_joint_velocity_rps, second.peak_joint_velocity_rps
        )

    def test_the_probe_commands_the_declared_start_offsets(self) -> None:
        robot = SpringRobot()
        _probe(robot, motion=_motion(start_offsets_rad=(0.1, 0.1))).measure(0.5)
        self.assertEqual(robot.resets, 1)

    def test_no_commanded_step_exceeds_the_rate_s_step_bound(self) -> None:
        robot = SpringRobot()
        probe = _probe(robot)
        probe.measure(0.6)
        bound = 0.6 / 30.0
        previous = (0.0, 0.0)
        for command in robot.commands[:-1]:
            for old, new in zip(previous, command):
                self.assertLessEqual(abs(new - old), bound + 1e-9)
            previous = command


class CalibrationLadderTests(unittest.TestCase):
    """The ladder admits the fastest measured rate, not a chosen one."""

    def test_at_least_one_candidate_is_required(self) -> None:
        with self.assertRaises(ValueError):
            calibrate_command_rate(_probe(SpringRobot()), ())

    def test_duplicate_candidates_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            calibrate_command_rate(_probe(SpringRobot()), (0.5, 0.5))

    def test_a_margin_outside_the_unit_interval_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            calibrate_command_rate(_probe(SpringRobot()), (0.5,), margin=1.5)

    def test_every_candidate_is_measured(self) -> None:
        report = calibrate_command_rate(
            _probe(SpringRobot()), (0.8, 0.2, 0.5)
        )
        self.assertEqual(len(report.measurements), 3)
        self.assertEqual(
            [item.commanded_rate_rps for item in report.measurements],
            [0.2, 0.5, 0.8],
        )

    def test_the_fastest_rate_inside_the_budget_is_admitted(self) -> None:
        report = calibrate_command_rate(
            _probe(SpringRobot(gain=1.5)), (0.2, 0.5, 0.8, 1.2)
        )
        self.assertIsNotNone(report.admitted)
        admitted = report.admitted
        assert admitted is not None
        self.assertLessEqual(
            admitted.peak_joint_velocity_rps, report.budget_rps + 1e-9
        )
        faster = [
            item.commanded_rate_rps
            for item in report.measurements
            if item.commanded_rate_rps > admitted.commanded_rate_rps
        ]
        for rate in faster:
            measured = next(
                item
                for item in report.measurements
                if item.commanded_rate_rps == rate
            )
            self.assertGreater(
                measured.peak_joint_velocity_rps, report.budget_rps
            )

    def test_the_admitted_rate_leaves_the_declared_margin(self) -> None:
        report = calibrate_command_rate(
            _probe(SpringRobot(gain=1.5)), (0.2, 0.5, 0.8, 1.2)
        )
        assert report.admitted is not None
        self.assertLess(
            report.admitted.peak_joint_velocity_rps,
            _ENVELOPE.max_joint_velocity_rps,
        )
        self.assertAlmostEqual(
            report.budget_rps,
            _ENVELOPE.max_joint_velocity_rps * DEFAULT_VELOCITY_MARGIN,
        )

    def test_nothing_is_admitted_when_every_rate_is_too_fast(self) -> None:
        report = calibrate_command_rate(
            _probe(SpringRobot(gain=10.0)), (0.5, 1.0)
        )
        self.assertIsNone(report.admitted)
        self.assertTrue(report.findings)
        self.assertIn("no candidate rate", report.findings[0])

    def test_a_non_monotone_peak_is_named_rather_than_smoothed(self) -> None:
        """A slower rate that peaks higher is a finding, not a rounding error."""
        peaks = {0.2: 1.4, 0.5: 0.6}
        robot = SpringRobot()

        def override(average_rate: float) -> float:
            for rate, peak in peaks.items():
                if abs(average_rate - rate) < 1e-6:
                    return peak
            return average_rate

        robot.peak_override = override
        report = calibrate_command_rate(_probe(robot), (0.2, 0.5))
        self.assertTrue(
            any("not monotone" in finding for finding in report.findings)
        )

    def test_a_fitting_rate_above_a_breaching_one_admits_nothing(self) -> None:
        peaks = {0.2: 1.4, 0.5: 0.6}
        robot = SpringRobot()

        def override(average_rate: float) -> float:
            for rate, peak in peaks.items():
                if abs(average_rate - rate) < 1e-6:
                    return peak
            return average_rate

        robot.peak_override = override
        report = calibrate_command_rate(_probe(robot), (0.2, 0.5))
        self.assertIsNone(report.admitted)
        self.assertTrue(
            any("no rate is admitted" in finding for finding in report.findings)
        )

    def test_the_report_records_what_it_was_measured_against(self) -> None:
        report = calibrate_command_rate(_probe(SpringRobot()), (0.5,))
        self.assertEqual(report.measured_on, "SpringRobot at 30Hz")
        self.assertEqual(report.control_frequency_hz, 30.0)
        self.assertEqual(
            report.velocity_limit_rps, _ENVELOPE.max_joint_velocity_rps
        )

    def test_the_digest_changes_with_the_admitted_rate(self) -> None:
        tight = calibrate_command_rate(
            _probe(SpringRobot(gain=1.5)), (0.2, 0.5)
        )
        loose = calibrate_command_rate(_probe(SpringRobot(gain=1.5)), (0.2,))
        self.assertNotEqual(tight.digest(), loose.digest())


class CalibrationFeedsTheRuntimeTests(unittest.TestCase):
    """The point of the measurement: a runtime the envelope accepts."""

    def test_the_admitted_calibration_constructs_a_runtime(self) -> None:
        report = calibrate_command_rate(
            _probe(SpringRobot(gain=1.5)), (0.2, 0.5, 0.8, 1.2)
        )
        assert report.admitted is not None
        runtime = DeterministicJointRuntime(
            robot=SpringRobot(gain=1.5),
            goals=(
                JointPoseGoal(
                    skill_version_id="home_arm@1",
                    target_joint_positions_rad=(0.0, 0.0),
                    satisfies=("at_home_pose",),
                ),
            ),
            command_rate=report.admitted,
            envelope=_ENVELOPE,
        )
        self.assertAlmostEqual(
            runtime.max_step_rad, report.admitted.max_step_rad
        )

    def test_a_rejected_measurement_would_be_refused_by_the_runtime(
        self,
    ) -> None:
        report = calibrate_command_rate(
            _probe(SpringRobot(gain=1.5)), (0.2, 0.5, 0.8, 1.2)
        )
        rejected = [
            item
            for item in report.measurements
            if item.peak_joint_velocity_rps
            > _ENVELOPE.max_joint_velocity_rps
        ]
        self.assertTrue(rejected)
        for measurement in rejected:
            with self.assertRaises(ValueError):
                DeterministicJointRuntime(
                    robot=SpringRobot(gain=1.5),
                    goals=(
                        JointPoseGoal(
                            skill_version_id="home_arm@1",
                            target_joint_positions_rad=(0.0, 0.0),
                            satisfies=("at_home_pose",),
                        ),
                    ),
                    command_rate=measurement,
                    envelope=_ENVELOPE,
                )


@unittest.skipUnless(_HAS_SIMULATION, _SKIP_REASON)
class SimulatedG1CalibrationTests(unittest.TestCase):
    """The measurement that motivated this module, taken on the real model.

    These are not assertions about specific numbers, which belong to the G1
    model and its servo gains. They assert the claim the runtime's refusal
    rests on: a MuJoCo position servo peaks above its commanded rate, and the
    peak is measured rather than assumed.
    """

    def _simulated_probe(
        self, control_frequency_hz: float = 50.0
    ) -> CommandRateProbe:
        robot = SimulatedG1(
            supervision=SimulatedSupervision(
                guardian_present=True,
                estop_engaged=False,
                estop_reachable=True,
                workspace_clear=True,
            ),
            control_frequency_hz=control_frequency_hz,
        )
        self.addCleanup(robot.close)
        stand = robot.stand_positions_rad
        target = tuple(
            value + (0.35 if index == 1 else 0.0)
            for index, value in enumerate(stand)
        )
        return CommandRateProbe(
            robot=robot,
            motion=ProbeMotion(target_joint_positions_rad=target),
            envelope=SafetyEnvelope(
                max_duration_s=30.0,
                max_joint_velocity_rps=1.5,
                max_end_effector_force_n=200.0,
                workspace_bounds_m=(
                    (-2.0, 2.0),
                    (-2.0, 2.0),
                    (-2.0, 2.0),
                ),
            ),
            control_frequency_hz=control_frequency_hz,
            measured_on=f"SimulatedG1 {G1_LEFT_ARM_JOINTS[1]} at "
            f"{control_frequency_hz}Hz",
        )

    def test_the_measured_peak_exceeds_the_commanded_rate(self) -> None:
        measurement = self._simulated_probe().measure(0.3)
        self.assertGreater(measurement.overshoot_ratio, 1.0)

    def test_the_ladder_admits_a_rate_the_runtime_accepts(self) -> None:
        probe = self._simulated_probe()
        report = calibrate_command_rate(probe, (0.15, 0.3, 0.6))
        self.assertEqual(len(report.measurements), 3)
        if report.admitted is not None:
            self.assertLessEqual(
                report.admitted.peak_joint_velocity_rps,
                report.budget_rps + 1e-9,
            )

    def test_a_measurement_belongs_to_one_control_frequency(self) -> None:
        """The same servo overshoots differently at a different cadence."""
        fast = self._simulated_probe(control_frequency_hz=100.0).measure(0.3)
        slow = self._simulated_probe(control_frequency_hz=25.0).measure(0.3)
        self.assertNotAlmostEqual(
            fast.overshoot_ratio, slow.overshoot_ratio, places=2
        )


if __name__ == "__main__":
    unittest.main()
