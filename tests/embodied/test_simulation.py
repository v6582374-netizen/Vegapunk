from __future__ import annotations

import importlib.util
import threading
import unittest
from pathlib import Path

_DEPENDENCIES = ("numpy", "mujoco")
_MISSING = tuple(
    name for name in _DEPENDENCIES if importlib.util.find_spec(name) is None
)

if _MISSING:
    _HAS_DEPENDENCIES = False
    _SKIP_REASON = f"missing simulation dependencies: {', '.join(_MISSING)}"
else:
    from vegapunk.embodied.simulation import DEFAULT_SCENE_PATH

    _HAS_DEPENDENCIES = DEFAULT_SCENE_PATH.exists()
    _SKIP_REASON = f"the G1 MJCF scene is not present at {DEFAULT_SCENE_PATH}"

if _HAS_DEPENDENCIES:
    import numpy as np

    from vegapunk.embodied.admission import STAGE_OFFLINE_REPLAY
    from vegapunk.embodied.safety import (
        ABORT_ENVELOPE_VIOLATION,
        Observation,
        SafetyEnvelope,
        SafetySupervisor,
    )
    from vegapunk.embodied.simulation import (
        CAMERA_SLOT_HEAD,
        CAMERA_SLOT_LEFT_WRIST,
        CAMERA_SLOTS,
        SIMULATION_STAGE,
        FrameBus,
        G1_LEFT_ARM_JOINTS,
        SimulatedG1,
        SimulatedSupervision,
    )

def _supervised() -> "SimulatedSupervision":
    return SimulatedSupervision(
        guardian_present=True,
        estop_engaged=False,
        estop_reachable=True,
        workspace_clear=True,
    )


def _robot(test: unittest.TestCase, **overrides: object) -> "SimulatedG1":
    robot = SimulatedG1(supervision=_supervised(), **overrides)
    test.addCleanup(robot.close)
    return robot


def _observation_from(state, elapsed_s: float) -> "Observation":
    """Build the safety view of a raw simulated state, as the runtime does."""
    return Observation(
        elapsed_s=elapsed_s,
        age_s=state.age_s,
        joint_velocity_rps=state.joint_velocity_rps,
        end_effector_force_n=state.end_effector_force_n,
        end_effector_position_m=state.end_effector_position_m,
        guardian_present=state.guardian_present,
        estop_engaged=state.estop_engaged,
        estop_reachable=state.estop_reachable,
        workspace_clear=state.workspace_clear,
    )


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class FrameBusTest(unittest.TestCase):
    """The only seam between the render thread and the transport."""

    def test_latest_frame_replaces_the_previous_one(self) -> None:
        bus = FrameBus()
        bus.publish("head", np.zeros((4, 8, 3), dtype=np.uint8))
        bus.publish("head", np.full((4, 8, 3), 200, dtype=np.uint8))

        self.assertEqual(int(bus.latest("head").mean()), 200)
        self.assertEqual(bus.frame_count("head"), 2)

    def test_an_unpublished_slot_reads_as_absent_rather_than_failing(self) -> None:
        bus = FrameBus()

        self.assertIsNone(bus.latest("head"))
        self.assertEqual(bus.frame_count("head"), 0)

    def test_frames_that_are_not_rgb_uint8_are_refused(self) -> None:
        bus = FrameBus()

        with self.assertRaises(ValueError):
            bus.publish("head", np.zeros((4, 8), dtype=np.uint8))
        with self.assertRaises(ValueError):
            bus.publish("head", np.zeros((4, 8, 4), dtype=np.uint8))
        with self.assertRaises(ValueError):
            bus.publish("head", np.zeros((4, 8, 3), dtype=np.float32))


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class CameraSlotTest(unittest.TestCase):
    """Slot geometry has to match what the fixed GUI panel will display."""

    def test_every_gui_slot_declares_a_distinct_port(self) -> None:
        ports = [slot.preview_port for slot in CAMERA_SLOTS.values()]

        self.assertEqual(len(ports), len(set(ports)))

    def test_declared_width_matches_the_tiled_sources(self) -> None:
        head = CAMERA_SLOTS[CAMERA_SLOT_HEAD]
        wrist = CAMERA_SLOTS[CAMERA_SLOT_LEFT_WRIST]

        self.assertEqual(len(head.sources), 2)
        self.assertEqual(head.width, wrist.width * 2)


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class SimulatedSupervisionTest(unittest.TestCase):
    """Room facts must be declared, never invented by the simulator."""

    def test_a_run_without_declared_supervision_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            SimulatedG1()

    def test_declared_facts_are_reported_as_given(self) -> None:
        robot = _robot(self)

        robot.declare_supervision(
            SimulatedSupervision(
                guardian_present=False,
                estop_engaged=True,
                estop_reachable=False,
                workspace_clear=False,
            )
        )
        state = robot.read_state()

        self.assertFalse(state.guardian_present)
        self.assertTrue(state.estop_engaged)
        self.assertFalse(state.estop_reachable)
        self.assertFalse(state.workspace_clear)


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class SimulatedG1IdentityTest(unittest.TestCase):
    """A simulated run must never be mistaken for hardware evidence."""

    def test_it_never_claims_to_be_a_real_robot(self) -> None:
        robot = _robot(self)

        self.assertFalse(robot.is_real_robot)
        self.assertEqual(SIMULATION_STAGE, STAGE_OFFLINE_REPLAY)

    def test_the_controlled_joint_vector_has_the_declared_meaning(self) -> None:
        robot = _robot(self, controlled_joints=G1_LEFT_ARM_JOINTS[:3])

        state = robot.read_state()

        self.assertEqual(robot.joint_names, G1_LEFT_ARM_JOINTS[:3])
        self.assertEqual(len(state.joint_positions_rad), 3)
        self.assertEqual(len(robot.stand_positions_rad), 3)

    def test_unknown_or_empty_joint_lists_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            SimulatedG1(supervision=_supervised(), controlled_joints=())
        with self.assertRaises(ValueError):
            SimulatedG1(
                supervision=_supervised(),
                controlled_joints=("no_such_joint",),
            )

    def test_a_missing_scene_is_reported_rather_than_improvised(self) -> None:
        with self.assertRaises(FileNotFoundError):
            SimulatedG1(
                supervision=_supervised(),
                scene_path=Path("/nonexistent/scene.xml"),
            )

    def test_the_clock_advances_with_the_physics_not_the_host(self) -> None:
        robot = _robot(self, control_frequency_hz=50.0)

        before = robot.clock()
        robot.command_joint_positions(robot.stand_positions_rad)
        after = robot.clock()

        self.assertAlmostEqual(after - before, robot.control_period_s, places=6)


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class WithinPeriodPeakTest(unittest.TestCase):
    """The envelope bounds every instant, so a read may not miss one.

    A position actuator converges inside one control period: it accelerates,
    peaks, and settles before the period ends. Sampling only the boundary
    therefore reads a near-resting joint no matter how fast it just moved,
    which would let a violation pass the supervisor unseen.
    """

    def test_a_read_reports_the_peak_reached_inside_the_period(self) -> None:
        robot = _robot(self, control_frequency_hz=10.0)
        target = list(robot.stand_positions_rad)
        target[3] += 0.2

        robot.command_joint_positions(target)
        peak = max(abs(v) for v in robot.read_state().joint_velocity_rps)
        settled = max(abs(v) for v in robot.read_state().joint_velocity_rps)

        self.assertGreater(peak, 1.0)
        self.assertGreater(peak, settled * 4)

    def test_the_supervisor_catches_a_violation_the_boundary_would_hide(self) -> None:
        robot = _robot(self, control_frequency_hz=10.0)
        supervisor = SafetySupervisor(
            SafetyEnvelope(
                max_duration_s=60.0,
                max_joint_velocity_rps=1.0,
                max_end_effector_force_n=50.0,
                workspace_bounds_m=((-1.0, 1.0), (-1.0, 1.0), (0.0, 2.0)),
                max_observation_age_s=1.0,
            )
        )
        target = list(robot.stand_positions_rad)
        target[3] += 0.2

        robot.command_joint_positions(target)
        state = robot.read_state()
        directive = supervisor.evaluate(
            _observation_from(state, elapsed_s=0.1)
        )

        self.assertIsNotNone(directive)
        self.assertEqual(directive.cause, ABORT_ENVELOPE_VIOLATION)

    def test_reading_drains_the_interval_so_peaks_do_not_persist(self) -> None:
        robot = _robot(self, control_frequency_hz=10.0)
        target = list(robot.stand_positions_rad)
        target[3] += 0.2
        robot.command_joint_positions(target)
        robot.read_state()

        robot.command_joint_positions(robot.read_state().joint_positions_rad)
        after = max(abs(v) for v in robot.read_state().joint_velocity_rps)

        self.assertLess(after, 1.0)

    def test_a_robot_that_never_moved_reports_rest(self) -> None:
        robot = _robot(self)

        state = robot.read_state()

        self.assertLess(max(abs(v) for v in state.joint_velocity_rps), 0.05)
        self.assertEqual(state.end_effector_force_n, 0.0)

    def test_a_hold_keeps_the_peak_that_preceded_it(self) -> None:
        robot = _robot(self, control_frequency_hz=10.0)
        target = list(robot.stand_positions_rad)
        target[3] += 0.2
        robot.command_joint_positions(target)

        robot.hold()
        state = robot.read_state()

        self.assertGreater(max(abs(v) for v in state.joint_velocity_rps), 1.0)


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class SimulatedG1MotionTest(unittest.TestCase):
    """Commanding, stopping, and the measurements a run depends on."""

    def test_a_commanded_pose_is_approached(self) -> None:
        robot = _robot(self, control_frequency_hz=50.0)
        start = np.array(robot.stand_positions_rad)
        target = start.copy()
        target[3] += 0.1

        for _ in range(60):
            robot.command_joint_positions(target)
        reached = np.array(robot.read_state().joint_positions_rad)

        self.assertLess(abs(reached[3] - target[3]), 0.02)

    def test_a_wrong_width_command_is_refused(self) -> None:
        robot = _robot(self)

        with self.assertRaises(ValueError):
            robot.command_joint_positions((0.0, 0.0))

    def test_hold_latches_and_refuses_all_later_motion(self) -> None:
        robot = _robot(self)

        robot.hold()

        self.assertTrue(robot.held)
        with self.assertRaises(RuntimeError):
            robot.command_joint_positions(robot.stand_positions_rad)

    def test_reset_clears_the_hold_latch_and_returns_to_standing(self) -> None:
        robot = _robot(self)
        robot.hold()

        robot.reset()

        self.assertFalse(robot.held)
        np.testing.assert_allclose(
            robot.read_state().joint_positions_rad,
            robot.stand_positions_rad,
            atol=1e-9,
        )

    def test_the_end_effector_position_is_reported_in_three_axes(self) -> None:
        robot = _robot(self)

        position = robot.read_state().end_effector_position_m

        self.assertEqual(len(position), 3)
        self.assertGreater(position[2], 0.0)

    def test_the_observation_age_is_one_control_period_by_default(self) -> None:
        robot = _robot(self, control_frequency_hz=25.0)

        self.assertAlmostEqual(
            robot.read_state().age_s, robot.control_period_s, places=9
        )

    def test_a_control_rate_faster_than_the_scene_timestep_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            SimulatedG1(supervision=_supervised(), control_frequency_hz=100000.0)
        with self.assertRaises(ValueError):
            SimulatedG1(supervision=_supervised(), control_frequency_hz=0.0)


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class SimulatedG1RenderTest(unittest.TestCase):
    """Rendering feeds the transport and stays on its own thread."""

    def test_each_gui_slot_renders_at_its_declared_geometry(self) -> None:
        robot = _robot(self)

        for slot_id, slot in CAMERA_SLOTS.items():
            frame = robot.render(slot_id)

            self.assertEqual(frame.shape, (slot.height, slot.width, 3))
            self.assertEqual(frame.dtype, np.uint8)

    def test_an_unknown_slot_is_refused(self) -> None:
        robot = _robot(self)

        with self.assertRaises(KeyError):
            robot.render("thirdEye")

    def test_publishing_fills_every_slot_on_the_bus(self) -> None:
        robot = _robot(self)
        bus = FrameBus()

        robot.publish_frames(bus)

        for slot_id in CAMERA_SLOTS:
            self.assertEqual(bus.frame_count(slot_id), 1)
            self.assertIsNotNone(bus.latest(slot_id))

    def test_rendering_from_another_thread_is_refused_not_corrupted(self) -> None:
        robot = _robot(self)
        failures: list[BaseException] = []

        def render_elsewhere() -> None:
            try:
                robot.render(CAMERA_SLOT_HEAD)
            except BaseException as error:
                failures.append(error)

        thread = threading.Thread(target=render_elsewhere)
        thread.start()
        thread.join(30)

        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], RuntimeError)

    def test_commanding_from_another_thread_is_refused(self) -> None:
        robot = _robot(self)
        failures: list[BaseException] = []

        def command_elsewhere() -> None:
            try:
                robot.command_joint_positions(robot.stand_positions_rad)
            except BaseException as error:
                failures.append(error)

        thread = threading.Thread(target=command_elsewhere)
        thread.start()
        thread.join(30)

        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], RuntimeError)
