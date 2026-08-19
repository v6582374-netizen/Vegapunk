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
    from vegapunk.embodied.regime import (
        AXIS_ACTUATOR_GAIN_SCALE,
        AXIS_COMMAND_LATENCY_STEPS,
        AXIS_DAMPING_SCALE,
        AXIS_FRICTION_SCALE,
        AXIS_JOINT_OFFSET_RAD,
        AXIS_PAYLOAD_KG,
        AXIS_SENSOR_NOISE_RAD,
        Regime,
        RegimeAxis,
        RegimeSample,
    )
    from vegapunk.embodied.simulation import (
        CAMERA_SLOT_HEAD,
        CAMERA_SLOT_LEFT_WRIST,
        CAMERA_SLOTS,
        SIMULATION_STAGE,
        SUPPORTED_PERTURBATION_AXES,
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


def _sample(index: int = 0, seed: int = 0, **values: float) -> "RegimeSample":
    """Build one world directly, so a test states the axis it is about."""
    return RegimeSample(index=index, seed=seed, values=values)


def _model_arrays(robot: "SimulatedG1") -> dict:
    """Every float array in a compiled model, for a bit-exactness comparison.

    Compared wholesale rather than against the list of arrays a regime writes,
    because the interesting failure is an array nobody thought to check: the
    solver derives inertias, subtree masses and body-relative camera positions
    from mass, and a restore that missed one of those would drift invisibly.
    """
    model = robot._model
    arrays = {}
    for name in dir(model):
        if name.startswith("_"):
            continue
        value = getattr(model, name, None)
        if isinstance(value, np.ndarray) and value.dtype.kind == "f":
            arrays[name] = np.array(value, copy=True)
    return arrays


def _differing_arrays(left: dict, right: dict) -> list:
    return sorted(
        name
        for name, value in left.items()
        if not np.array_equal(value, right[name])
    )


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class PerturbationScopeTest(unittest.TestCase):
    """What this simulator claims to apply, and what it refuses to fake."""

    def test_supported_axes_are_the_registry_the_regime_validates(self) -> None:
        regime = Regime(
            axes=(
                RegimeAxis(
                    name=name,
                    low=0.1,
                    high=0.2,
                    unit="unit",
                    rationale="a test band",
                )
                for name in SUPPORTED_PERTURBATION_AXES
            ),
            samples=2,
        )

        self.assertEqual(
            set(regime.axis_names()), set(SUPPORTED_PERTURBATION_AXES)
        )

    def test_an_unsupported_axis_in_a_sample_is_refused_not_ignored(
        self,
    ) -> None:
        robot = _robot(self)

        with self.assertRaises(ValueError) as raised:
            robot.perturb(_sample(lighting=0.5))

        self.assertIn("lighting", str(raised.exception))

    def test_an_unsupported_axis_is_refused_through_reset_too(self) -> None:
        robot = _robot(self)

        with self.assertRaises(ValueError):
            robot.reset(sample=_sample(image_noise=0.1))

    def test_a_negative_payload_is_refused(self) -> None:
        robot = _robot(self)

        with self.assertRaises(ValueError):
            robot.perturb(_sample(**{AXIS_PAYLOAD_KG: -1.0}))

    def test_a_non_positive_friction_scale_is_refused(self) -> None:
        robot = _robot(self)

        with self.assertRaises(ValueError):
            robot.perturb(_sample(**{AXIS_FRICTION_SCALE: 0.0}))

    def test_a_non_positive_gain_scale_is_refused(self) -> None:
        robot = _robot(self)

        with self.assertRaises(ValueError):
            robot.perturb(_sample(**{AXIS_ACTUATOR_GAIN_SCALE: 0.0}))

    def test_a_negative_latency_is_refused(self) -> None:
        robot = _robot(self)

        with self.assertRaises(ValueError):
            robot.perturb(_sample(**{AXIS_COMMAND_LATENCY_STEPS: -1.0}))

    def test_a_negative_noise_magnitude_is_refused(self) -> None:
        robot = _robot(self)

        with self.assertRaises(ValueError):
            robot.perturb(_sample(**{AXIS_SENSOR_NOISE_RAD: -0.001}))

    def test_a_regime_does_not_change_the_configuration_digest(self) -> None:
        """The anchor evidence is scoped to cannot move per attempt."""
        robot = _robot(self)
        before = robot.describe_configuration(
            environment_id="sim-g1",
            end_effector="dex1_gripper",
            control_authority="left_arm",
        )

        robot.reset(
            sample=_sample(
                **{
                    AXIS_FRICTION_SCALE: 0.8,
                    AXIS_PAYLOAD_KG: 1.0,
                    AXIS_ACTUATOR_GAIN_SCALE: 1.2,
                    AXIS_SENSOR_NOISE_RAD: 0.002,
                }
            )
        )
        after = robot.describe_configuration(
            environment_id="sim-g1",
            end_effector="dex1_gripper",
            control_authority="left_arm",
        )

        self.assertEqual(before, after)
        self.assertEqual(before.digest(), after.digest())


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class PerturbationAppliedTest(unittest.TestCase):
    """Each axis reaches the physics, which is what makes sampling it honest."""

    def test_friction_scale_multiplies_geom_friction(self) -> None:
        robot = _robot(self)
        nominal = np.array(robot._model.geom_friction, copy=True)

        robot.reset(sample=_sample(**{AXIS_FRICTION_SCALE: 0.5}))

        np.testing.assert_allclose(
            robot._model.geom_friction, nominal * 0.5
        )

    def test_payload_adds_mass_to_the_end_effector_body_only(self) -> None:
        robot = _robot(self)
        nominal = np.array(robot._model.body_mass, copy=True)
        body_id = robot._end_effector_body_id

        robot.reset(sample=_sample(**{AXIS_PAYLOAD_KG: 0.75}))

        self.assertAlmostEqual(
            float(robot._model.body_mass[body_id]),
            float(nominal[body_id]) + 0.75,
        )
        others = [i for i in range(len(nominal)) if i != body_id]
        np.testing.assert_allclose(
            robot._model.body_mass[others], nominal[others]
        )

    def test_payload_refreshes_the_solver_reference_inertias(self) -> None:
        """A payload the dynamics feel but the solver does not is half-applied."""
        robot = _robot(self)
        nominal = np.array(robot._model.body_subtreemass, copy=True)

        robot.reset(sample=_sample(**{AXIS_PAYLOAD_KG: 2.0}))

        self.assertGreater(
            float(robot._model.body_subtreemass[0]), float(nominal[0])
        )

    def test_damping_scale_reaches_the_dissipation_this_scene_uses(
        self,
    ) -> None:
        """The G1 keeps joint dissipation in frictionloss, not dof_damping."""
        robot = _robot(self)
        nominal_loss = np.array(robot._model.dof_frictionloss, copy=True)
        self.assertGreater(float(np.max(nominal_loss)), 0.0)

        robot.reset(sample=_sample(**{AXIS_DAMPING_SCALE: 2.0}))

        np.testing.assert_allclose(
            robot._model.dof_frictionloss, nominal_loss * 2.0
        )

    def test_gain_scale_moves_the_bias_term_that_mirrors_the_gain(self) -> None:
        """A position servo is affine: scaling one term alone biases it."""
        robot = _robot(self)
        gain = np.array(robot._model.actuator_gainprm, copy=True)
        bias = np.array(robot._model.actuator_biasprm, copy=True)

        robot.reset(sample=_sample(**{AXIS_ACTUATOR_GAIN_SCALE: 0.5}))

        np.testing.assert_allclose(
            robot._model.actuator_gainprm[:, 0], gain[:, 0] * 0.5
        )
        np.testing.assert_allclose(
            robot._model.actuator_biasprm[:, 1], bias[:, 1] * 0.5
        )
        # The dampratio term is the scene author's damping law, not a mirror of
        # the gain, so it is left exactly as compiled.
        np.testing.assert_allclose(
            robot._model.actuator_biasprm[:, 2], bias[:, 2]
        )

    def test_a_softer_servo_tracks_a_command_less_closely(self) -> None:
        """The gain axis has to change the run, not just the model."""

        def tracking_error(gain_scale: float) -> float:
            robot = _robot(self)
            robot.reset(
                sample=_sample(**{AXIS_ACTUATOR_GAIN_SCALE: gain_scale})
            )
            target = list(robot.stand_positions_rad)
            target[3] += 0.3
            worst = 0.0
            for _ in range(40):
                robot.command_joint_positions(target)
                reached = robot.read_state().joint_positions_rad
                worst = max(worst, abs(reached[3] - target[3]))
            return worst

        self.assertGreater(tracking_error(0.8), tracking_error(1.25))


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class PerturbationDoesNotCompoundTest(unittest.TestCase):
    """The refusal that keeps a campaign's earlier attempts valid."""

    def test_fifty_alternating_resets_leave_the_model_pristine_per_sample(
        self,
    ) -> None:
        """A drifting simulator invalidates every earlier attempt silently."""
        first = _sample(
            0,
            **{
                AXIS_FRICTION_SCALE: 0.85,
                AXIS_PAYLOAD_KG: 0.9,
                AXIS_DAMPING_SCALE: 1.7,
                AXIS_ACTUATOR_GAIN_SCALE: 0.9,
            },
        )
        second = _sample(
            1,
            **{
                AXIS_FRICTION_SCALE: 1.2,
                AXIS_PAYLOAD_KG: 0.1,
                AXIS_DAMPING_SCALE: 0.6,
                AXIS_ACTUATOR_GAIN_SCALE: 1.2,
            },
        )

        reference = _robot(self)
        reference.reset(sample=first)
        expected_first = _model_arrays(reference)

        fresh = _robot(self)
        fresh.reset(sample=second)
        expected_second = _model_arrays(fresh)

        pristine = _model_arrays(_robot(self))

        robot = _robot(self)
        for cycle in range(25):
            robot.reset(sample=first)
            self.assertEqual(
                _differing_arrays(_model_arrays(robot), expected_first),
                [],
                f"cycle {cycle} drifted from the first sample's world",
            )
            robot.reset(sample=second)
            self.assertEqual(
                _differing_arrays(_model_arrays(robot), expected_second),
                [],
                f"cycle {cycle} drifted from the second sample's world",
            )

        robot.reset()
        self.assertEqual(
            _differing_arrays(_model_arrays(robot), pristine),
            [],
            "a reset naming no sample left the previous world installed",
        )

    def test_the_same_sample_reproduces_the_same_trajectory(self) -> None:
        sample = _sample(
            3,
            **{
                AXIS_FRICTION_SCALE: 0.9,
                AXIS_PAYLOAD_KG: 0.4,
                AXIS_ACTUATOR_GAIN_SCALE: 1.1,
            },
        )

        def trajectory() -> list:
            robot = _robot(self)
            robot.reset(sample=sample)
            target = list(robot.stand_positions_rad)
            target[3] += 0.2
            positions = []
            for _ in range(20):
                robot.command_joint_positions(target)
                positions.append(robot.read_state().joint_positions_rad)
            return positions

        self.assertEqual(trajectory(), trajectory())

    def test_different_samples_produce_different_trajectories(self) -> None:
        """Otherwise the regime is ceremony around one replayed world."""

        def elbow_after(gain_scale: float) -> float:
            robot = _robot(self)
            robot.reset(
                sample=_sample(**{AXIS_ACTUATOR_GAIN_SCALE: gain_scale})
            )
            target = list(robot.stand_positions_rad)
            target[3] += 0.2
            for _ in range(10):
                robot.command_joint_positions(target)
            return robot.read_state().joint_positions_rad[3]

        self.assertNotAlmostEqual(
            elbow_after(0.8), elbow_after(1.25), places=6
        )


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class CommandLatencyTest(unittest.TestCase):
    """A delay applied to the command, never by rewinding the physics."""

    def test_no_latency_applies_the_command_the_step_it_was_issued(
        self,
    ) -> None:
        robot = _robot(self)
        robot.reset(sample=_sample(**{AXIS_COMMAND_LATENCY_STEPS: 0.0}))
        target = list(robot.stand_positions_rad)
        target[3] += 0.2

        robot.command_joint_positions(target)

        self.assertAlmostEqual(
            float(robot._data.ctrl[robot._ctrl_index][3]), target[3]
        )

    def test_a_delayed_command_takes_effect_n_control_steps_late(self) -> None:
        robot = _robot(self)
        robot.reset(sample=_sample(**{AXIS_COMMAND_LATENCY_STEPS: 2.0}))
        start = list(robot.stand_positions_rad)
        target = list(start)
        target[3] += 0.2

        robot.command_joint_positions(target)
        self.assertAlmostEqual(
            float(robot._data.ctrl[robot._ctrl_index][3]), start[3]
        )

        robot.command_joint_positions(target)
        self.assertAlmostEqual(
            float(robot._data.ctrl[robot._ctrl_index][3]), start[3]
        )

        robot.command_joint_positions(target)
        self.assertAlmostEqual(
            float(robot._data.ctrl[robot._ctrl_index][3]), target[3]
        )

    def test_latency_slows_a_move_without_stopping_it(self) -> None:
        def elbow_after(latency: float) -> float:
            robot = _robot(self)
            robot.reset(
                sample=_sample(**{AXIS_COMMAND_LATENCY_STEPS: latency})
            )
            target = list(robot.stand_positions_rad)
            target[3] += 0.3
            for _ in range(6):
                robot.command_joint_positions(target)
            return robot.read_state().joint_positions_rad[3]

        prompt = elbow_after(0.0)
        delayed = elbow_after(2.0)

        self.assertGreater(prompt, delayed)
        self.assertGreater(delayed, 0.0)

    def test_a_hold_discards_queued_commands(self) -> None:
        """A latch that a buffered command could outlive is not a stop."""
        robot = _robot(self)
        robot.reset(sample=_sample(**{AXIS_COMMAND_LATENCY_STEPS: 2.0}))
        target = list(robot.stand_positions_rad)
        target[3] += 0.3
        robot.command_joint_positions(target)

        robot.hold()

        self.assertEqual(len(robot._command_queue), 0)
        np.testing.assert_allclose(
            robot._data.ctrl[robot._ctrl_index],
            robot._data.qpos[robot._qpos_index],
        )

    def test_a_reset_empties_the_queue_between_attempts(self) -> None:
        robot = _robot(self)
        robot.reset(sample=_sample(**{AXIS_COMMAND_LATENCY_STEPS: 2.0}))
        target = list(robot.stand_positions_rad)
        target[3] += 0.3
        robot.command_joint_positions(target)

        robot.reset(sample=_sample(**{AXIS_COMMAND_LATENCY_STEPS: 2.0}))

        self.assertEqual(len(robot._command_queue), 0)


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class SensorNoiseTest(unittest.TestCase):
    """Noise on the instrument, never on the world it measures."""

    def test_noise_perturbs_reported_positions(self) -> None:
        robot = _robot(self)
        robot.reset(sample=_sample(**{AXIS_SENSOR_NOISE_RAD: 0.002}))

        reported = robot.read_state().joint_positions_rad
        truth = tuple(
            float(v) for v in robot._data.qpos[robot._qpos_index]
        )

        self.assertNotEqual(reported, truth)
        for noisy, exact in zip(reported, truth):
            self.assertLess(abs(noisy - exact), 0.02)

    def test_noise_does_not_touch_the_true_physics(self) -> None:
        """A simulator that moved the robot would model the opposite error."""
        quiet = _robot(self)
        quiet.reset(sample=_sample(7, **{AXIS_SENSOR_NOISE_RAD: 0.0}))
        noisy = _robot(self)
        noisy.reset(sample=_sample(7, **{AXIS_SENSOR_NOISE_RAD: 0.002}))

        target = list(quiet.stand_positions_rad)
        target[3] += 0.2
        for _ in range(15):
            quiet.command_joint_positions(target)
            noisy.command_joint_positions(target)
            quiet.read_state()
            noisy.read_state()

        np.testing.assert_allclose(
            noisy._data.qpos[noisy._qpos_index],
            quiet._data.qpos[quiet._qpos_index],
        )

    def test_noise_is_reproducible_from_the_sample(self) -> None:
        sample = _sample(4, **{AXIS_SENSOR_NOISE_RAD: 0.002})

        def readings() -> list:
            robot = _robot(self)
            robot.reset(sample=sample)
            return [
                robot.read_state().joint_positions_rad for _ in range(5)
            ]

        self.assertEqual(readings(), readings())

    def test_different_samples_draw_different_noise(self) -> None:
        def first_reading(index: int) -> tuple:
            robot = _robot(self)
            robot.reset(sample=_sample(index, **{AXIS_SENSOR_NOISE_RAD: 0.002}))
            return robot.read_state().joint_positions_rad

        self.assertNotEqual(first_reading(1), first_reading(2))

    def test_noise_is_zero_mean_rather_than_a_calibration_bias(self) -> None:
        robot = _robot(self)
        robot.reset(sample=_sample(**{AXIS_SENSOR_NOISE_RAD: 0.002}))
        truth = float(robot._data.qpos[robot._qpos_index][0])

        errors = [
            robot.read_state().joint_positions_rad[0] - truth
            for _ in range(400)
        ]

        self.assertLess(abs(sum(errors) / len(errors)), 0.0004)

    def test_a_nominal_reset_reports_the_truth_again(self) -> None:
        robot = _robot(self)
        robot.reset(sample=_sample(**{AXIS_SENSOR_NOISE_RAD: 0.002}))
        robot.read_state()

        robot.reset()

        self.assertEqual(
            robot.read_state().joint_positions_rad,
            tuple(float(v) for v in robot._data.qpos[robot._qpos_index]),
        )

    def test_peaks_still_report_the_interval_since_the_previous_read(
        self,
    ) -> None:
        """Noise must not disturb the accumulation the envelope is judged on."""
        robot = _robot(self)
        robot.reset(
            sample=_sample(
                **{AXIS_SENSOR_NOISE_RAD: 0.002, AXIS_PAYLOAD_KG: 0.5}
            )
        )
        target = list(robot.stand_positions_rad)
        target[3] += 0.3

        robot.command_joint_positions(target)
        moving = robot.read_state()
        for _ in range(60):
            robot.command_joint_positions(target)
        robot.read_state()
        robot.hold()
        robot.read_state()
        settled = robot.read_state()

        self.assertGreater(max(moving.joint_velocity_rps), 0.0)
        self.assertEqual(max(settled.joint_velocity_rps), 0.0)


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class RegimeSampledRunTest(unittest.TestCase):
    """A regime's own samples have to survive contact with the simulator."""

    def test_every_default_sample_applies_and_runs(self) -> None:
        from vegapunk.embodied.regime import DEFAULT_CONTACT_REGIME

        robot = _robot(self)
        for index in range(DEFAULT_CONTACT_REGIME.samples):
            sample = DEFAULT_CONTACT_REGIME.sample(index)
            offsets = [
                sample.value(AXIS_JOINT_OFFSET_RAD, 0.0)
            ] * len(robot.joint_names)

            robot.reset(joint_offsets_rad=offsets, sample=sample)
            target = list(robot.stand_positions_rad)
            target[3] += 0.1
            for _ in range(5):
                robot.command_joint_positions(target)
            state = robot.read_state()

            self.assertEqual(len(state.joint_positions_rad), 7)
            self.assertTrue(
                all(abs(v) < 50.0 for v in state.joint_velocity_rps)
            )
