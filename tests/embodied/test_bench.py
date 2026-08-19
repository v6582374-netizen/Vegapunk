"""What an assembled inner loop may conclude, and where it must stop.

The bench is the one module whose job is composition, so these tests are about
ordering and refusal rather than about physics: that a stage is earned rather
than seeded, that a measurement fixes the goal it is used with, and that the
bench stops at the first result which makes the next step meaningless.
"""

from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from vegapunk.embodied.admission import (
    MINIMUM_STAGE_ATTEMPTS,
    STAGE_OFFLINE_REPLAY,
    STAGE_POLICY_EVALUATION,
    STAGE_SHADOW_MODE,
)
from vegapunk.embodied.bench import (
    HALTED_COMPLETED,
    HALTED_GOAL_INFEASIBLE,
    HALTED_NO_ADMITTED_RATE,
    HALTED_STAGE_INCOMPLETE,
    HALTED_STAGE_NOT_ADMITTED,
    BenchPlan,
    embodiment_for,
    run_bench,
)
from vegapunk.embodied.embodiment import UNIFOLM_VLA_BASE_G1_EE6D
from vegapunk.embodied.fidelity import SimulatedConfiguration
from vegapunk.embodied.runtime import RobotState
from vegapunk.embodied.safety import SafetyEnvelope
from vegapunk.embodied.skill import (
    SKILL_KIND_DETERMINISTIC,
    SKILL_KIND_VLA,
    ParameterSpec,
    PhysicalSkill,
    SkillRegistry,
)

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

NOW = datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)

_JOINTS = ("joint_a", "joint_b", "joint_c")

_ENVELOPE = SafetyEnvelope(
    max_duration_s=10.0,
    max_joint_velocity_rps=1.5,
    max_end_effector_force_n=20.0,
    workspace_bounds_m=((-1.0, 1.0), (-1.0, 1.0), (0.0, 2.0)),
)


class FakeSimRobot:
    """A tracking robot with a servo's overshoot and nothing else.

    It answers every command exactly, which keeps these tests about the bench's
    ordering rather than about convergence, and reports a peak velocity above
    the rate its setpoint spacing implies, which is the one physical fact the
    calibration ladder has to see.

    It deliberately has no "fails to converge" mode. A robot that lagged its
    setpoint would be measured lagging by the calibration probe too, which is
    the whole point of measuring: the tolerance floor would widen to cover the
    lag and the pose would be reached anyway. Failed verification is therefore
    provoked the way it actually happens -- by a goal that demonstrates less
    than the skill declares -- rather than by a robot that misbehaves only when
    a test needs it to.
    """

    is_real_robot = False

    def __init__(
        self,
        gain: float = 1.5,
        control_frequency_hz: float = 50.0,
        estop_after: Optional[int] = None,
    ) -> None:
        self._stand = (0.0,) * len(_JOINTS)
        self.positions = self._stand
        self.gain = gain
        self._frequency_hz = control_frequency_hz
        self._estop_after = estop_after
        self.commands: list[tuple[float, ...]] = []
        self.resets: list[Optional[tuple[float, ...]]] = []
        self.holds = 0
        self.published = 0
        self._time = 0.0
        self._peak = 0.0
        self._commands_since_reset = 0

    @property
    def joint_names(self) -> tuple[str, ...]:
        return _JOINTS

    @property
    def control_frequency_hz(self) -> float:
        return self._frequency_hz

    @property
    def stand_positions_rad(self) -> tuple[float, ...]:
        return self._stand

    def clock(self) -> float:
        return self._time

    def reset(
        self, joint_offsets_rad: Optional[Sequence[float]] = None
    ) -> None:
        self.resets.append(
            None if joint_offsets_rad is None else tuple(joint_offsets_rad)
        )
        offsets = tuple(joint_offsets_rad or (0.0,) * len(self._stand))
        self.positions = tuple(
            base + offset for base, offset in zip(self._stand, offsets)
        )
        self._peak = 0.0
        self._time = 0.0
        self._commands_since_reset = 0

    def read_state(self) -> RobotState:
        peak = self._peak
        self._peak = 0.0
        estopped = (
            self._estop_after is not None
            and self._commands_since_reset > self._estop_after
        )
        return RobotState(
            joint_positions_rad=self.positions,
            joint_velocity_rps=(peak,) * len(self.positions),
            end_effector_force_n=1.0,
            end_effector_position_m=(0.1, 0.0, 0.8),
            guardian_present=True,
            estop_engaged=estopped,
            estop_reachable=True,
            workspace_clear=True,
            age_s=0.01,
        )

    def command_joint_positions(self, positions_rad: Sequence[float]) -> None:
        target = tuple(float(value) for value in positions_rad)
        travelled = max(
            (abs(new - old) for old, new in zip(self.positions, target)),
            default=0.0,
        )
        self._peak = max(self._peak, travelled * self._frequency_hz * self.gain)
        self.commands.append(target)
        self._commands_since_reset += 1
        self._time += 1.0 / self._frequency_hz
        self.positions = target

    def hold(self) -> None:
        self.holds += 1

    def publish_frames(self, bus: object) -> None:
        self.published += 1

    def describe_configuration(
        self,
        environment_id: str,
        end_effector: str,
        control_authority: str,
        represented_camera_keys: Sequence[str] = (),
    ) -> SimulatedConfiguration:
        return SimulatedConfiguration(
            environment_id=environment_id,
            is_real_robot=self.is_real_robot,
            control_frequency_hz=self._frequency_hz,
            controlled_joint_names=_JOINTS,
            end_effector=end_effector,
            control_authority=control_authority,
            represented_camera_keys=tuple(represented_camera_keys),
        )


class RealFakeRobot(FakeSimRobot):
    is_real_robot = True


def _skill(**overrides: object) -> PhysicalSkill:
    fields: dict[str, object] = {
        "skill_id": "reach_pose",
        "revision": 1,
        "kind": SKILL_KIND_DETERMINISTIC,
        "summary": "Move the arm to a reviewed joint pose.",
        "parameters": (),
        "preconditions": ("workspace_clear", "guardian_present"),
        "postconditions": ("at_pose",),
        "abort_conditions": ("force_exceeded",),
        "max_duration_s": 5.0,
        "reviewed_by": "loongge",
    }
    fields.update(overrides)
    return PhysicalSkill(**fields)  # type: ignore[arg-type]


def _plan(**overrides: object) -> BenchPlan:
    fields: dict[str, object] = {
        "skill": _skill(),
        "goal_offsets_rad": (0.3, 0.0, 0.0),
        "satisfies": ("at_pose",),
        "envelope": _ENVELOPE,
        "candidate_rates_rps": (0.4, 0.8, 1.2),
        "environment_id": "fake-bench",
        "end_effector": "dex1_1",
        "control_authority": "arm_and_gripper",
        "camera_map": {"observation.images.top": "head_rgb"},
    }
    fields.update(overrides)
    return BenchPlan(**fields)  # type: ignore[arg-type]


class _Clock:
    """A clock that advances, so evidence is never recorded at one instant."""

    def __init__(self) -> None:
        self._now = NOW

    def __call__(self) -> datetime:
        self._now = self._now + timedelta(seconds=1)
        return self._now


class PlanDeclarationTests(unittest.TestCase):
    """A plan states claims a person is accountable for, and is checked."""

    def test_a_policy_authored_skill_is_refused(self) -> None:
        with self.assertRaises(ValueError) as error:
            _plan(
                skill=_skill(
                    kind=SKILL_KIND_VLA,
                    policy=UNIFOLM_VLA_BASE_G1_EE6D,
                )
            )
        self.assertIn("checkpoint's digest", str(error.exception))

    def test_a_parameterised_skill_is_refused(self) -> None:
        with self.assertRaises(ValueError) as error:
            _plan(
                skill=_skill(
                    parameters=(
                        ParameterSpec(
                            name="height_m",
                            minimum=0.0,
                            maximum=1.0,
                        ),
                    )
                )
            )
        self.assertIn("one reviewed goal pose", str(error.exception))

    def test_a_goal_that_displaces_nothing_is_refused(self) -> None:
        with self.assertRaises(ValueError) as error:
            _plan(goal_offsets_rad=(0.0, 0.0, 0.0))
        self.assertIn("displaces no joint", str(error.exception))

    def test_a_goal_cannot_claim_an_undeclared_postcondition(self) -> None:
        with self.assertRaises(ValueError) as error:
            _plan(satisfies=("block_placed",))
        self.assertIn("block_placed", str(error.exception))

    def test_a_stage_below_the_ladder_minimum_is_refused(self) -> None:
        with self.assertRaises(ValueError) as error:
            _plan(attempts_per_stage=MINIMUM_STAGE_ATTEMPTS - 1)
        self.assertIn("cannot open anything", str(error.exception))

    def test_the_two_stages_must_perturb_differently(self) -> None:
        with self.assertRaises(ValueError) as error:
            _plan(nominal_offset_rad=0.05, deployment_offset_rad=0.05)
        self.assertIn("one measurement reported twice", str(error.exception))

    def test_calibration_needs_candidate_rates(self) -> None:
        with self.assertRaises(ValueError) as error:
            _plan(candidate_rates_rps=())
        self.assertIn("proposes none of its own", str(error.exception))

    def test_each_stage_declares_its_own_perturbation_bound(self) -> None:
        plan = _plan()
        self.assertEqual(
            plan.stage_offsets_rad[STAGE_POLICY_EVALUATION],
            plan.nominal_offset_rad,
        )
        self.assertEqual(
            plan.stage_offsets_rad[STAGE_OFFLINE_REPLAY],
            plan.deployment_offset_rad,
        )


class DerivedEmbodimentTests(unittest.TestCase):
    """The profile evidence is scoped to is read off the environment."""

    def test_the_cadence_and_joints_are_not_declarable(self) -> None:
        robot = FakeSimRobot(control_frequency_hz=37.0)
        embodiment = embodiment_for(
            robot,
            end_effector="dex1_1",
            control_authority="arm_and_gripper",
            camera_map={},
        )
        self.assertEqual(embodiment.control_frequency_hz, 37.0)
        self.assertEqual(embodiment.arm_dof, len(_JOINTS))
        self.assertEqual(embodiment.action_dim, len(_JOINTS))

    def test_a_simulated_profile_has_nothing_unverified(self) -> None:
        embodiment = embodiment_for(
            FakeSimRobot(),
            end_effector="dex1_1",
            control_authority="arm_and_gripper",
            camera_map={},
        )
        self.assertTrue(embodiment.fully_verified)

    def test_a_simulated_profile_is_not_a_hardware_profile(self) -> None:
        """The digests differ, which is what keeps the two sets of evidence apart."""
        simulated = embodiment_for(
            FakeSimRobot(),
            end_effector="dex1_1",
            control_authority="arm_and_gripper",
            camera_map={},
        )
        self.assertNotEqual(simulated.robot_model, "unitree_g1")

    def test_a_real_robot_cannot_be_derived_into_a_simulated_profile(
        self,
    ) -> None:
        with self.assertRaises(ValueError) as error:
            embodiment_for(
                RealFakeRobot(),
                end_effector="dex1_1",
                control_authority="arm_and_gripper",
                camera_map={},
            )
        self.assertIn("laboratory measurement", str(error.exception))


class BenchOrderingTests(unittest.TestCase):
    """The ladder is climbed by running it, in order."""

    def setUp(self) -> None:
        self.robot = FakeSimRobot()
        self.report = run_bench(
            self.robot, _plan(), clock=_Clock()
        )

    def test_both_simulated_stages_run_in_ladder_order(self) -> None:
        self.assertEqual(
            [stage.stage for stage in self.report.stages],
            [STAGE_POLICY_EVALUATION, STAGE_OFFLINE_REPLAY],
        )

    def test_every_stage_earns_its_attempts(self) -> None:
        for stage in self.report.stages:
            self.assertEqual(stage.executed_attempts, MINIMUM_STAGE_ATTEMPTS)
            self.assertEqual(stage.successes, MINIMUM_STAGE_ATTEMPTS)

    def test_the_deployment_stage_perturbs_further_than_the_nominal_one(
        self,
    ) -> None:
        offsets = [
            max(abs(value) for value in reset)
            for reset in self.robot.resets
            if reset
        ]
        nominal = [value for value in offsets if value <= 0.01]
        deployment = [value for value in offsets if value > 0.01]
        self.assertTrue(nominal)
        self.assertTrue(deployment)
        self.assertLessEqual(max(nominal), _plan().nominal_offset_rad)
        self.assertLessEqual(max(deployment), _plan().deployment_offset_rad)

    def test_the_full_plan_completes_and_reports_what_remains(self) -> None:
        self.assertEqual(self.report.halted, HALTED_COMPLETED)
        self.assertTrue(self.report.completed)
        self.assertIsNotNone(self.report.hardware_decision)

    def test_simulated_evidence_never_admits_hardware(self) -> None:
        decision = self.report.hardware_decision
        assert decision is not None
        self.assertFalse(decision.admitted)
        reasons = " ".join(decision.blocking_reasons)
        self.assertIn(STAGE_SHADOW_MODE, reasons)
        self.assertIn("human approval", reasons)

    def test_the_goal_tolerance_comes_from_the_calibration(self) -> None:
        goal = self.report.goal
        assert goal is not None
        admitted = self.report.calibration.admitted
        assert admitted is not None
        self.assertGreaterEqual(
            goal.tolerance_rad, admitted.minimum_goal_tolerance_rad
        )

    def test_the_admitted_rate_fits_the_measured_budget(self) -> None:
        admitted = self.report.calibration.admitted
        assert admitted is not None
        self.assertLessEqual(
            admitted.peak_joint_velocity_rps,
            self.report.calibration.budget_rps + 1e-9,
        )

    def test_the_duration_is_known_before_any_attempt(self) -> None:
        self.assertIsNotNone(self.report.required_duration_s)


class BenchRefusalTests(unittest.TestCase):
    """Where the bench stops, and what it refuses to file when it does."""

    def test_no_admitted_rate_means_no_stage_is_attempted(self) -> None:
        robot = FakeSimRobot(gain=6.0)
        report = run_bench(robot, _plan(), clock=_Clock())
        self.assertEqual(report.halted, HALTED_NO_ADMITTED_RATE)
        self.assertEqual(report.stages, ())
        self.assertIsNone(report.goal)
        self.assertEqual(
            report.blocking_hardware, (report.halt_detail,)
        )
        self.assertIn("no probe measured", report.halt_detail)

    def test_a_goal_that_cannot_finish_in_time_is_refused_before_it_runs(
        self,
    ) -> None:
        report = run_bench(
            FakeSimRobot(),
            _plan(
                skill=_skill(max_duration_s=0.05),
                candidate_rates_rps=(0.1, 0.2),
            ),
            clock=_Clock(),
        )
        self.assertEqual(report.halted, HALTED_GOAL_INFEASIBLE)
        self.assertEqual(report.stages, ())
        self.assertIsNotNone(report.goal)
        self.assertIn("aborted partway", report.halt_detail)

    def test_a_stage_that_never_verifies_does_not_open_the_next(self) -> None:
        """A goal that proves less than the skill declares fails every attempt.

        The runtime reports only what reaching the pose demonstrates, so the
        skill's second postcondition is never measured and the loop reads that
        as a failed verification. The stage still runs its full plan -- nothing
        was unsafe -- and then correctly opens nothing.
        """
        report = run_bench(
            FakeSimRobot(),
            _plan(
                skill=_skill(postconditions=("at_pose", "gripper_closed")),
                satisfies=("at_pose",),
            ),
            clock=_Clock(),
        )
        self.assertEqual(report.halted, HALTED_STAGE_NOT_ADMITTED)
        self.assertEqual(len(report.stages), 1)
        self.assertEqual(report.stages[0].executed_attempts, MINIMUM_STAGE_ATTEMPTS)
        self.assertEqual(report.stages[0].successes, 0)
        self.assertIn("success rate", report.halt_detail)

    def test_an_abort_stops_the_bench_at_the_stage_it_happened_in(
        self,
    ) -> None:
        report = run_bench(
            FakeSimRobot(estop_after=2), _plan(), clock=_Clock()
        )
        self.assertEqual(report.halted, HALTED_STAGE_INCOMPLETE)
        self.assertEqual(len(report.stages), 1)
        self.assertLess(
            report.stages[0].executed_attempts, MINIMUM_STAGE_ATTEMPTS
        )
        self.assertIn("quarantined", report.halt_detail)

    def test_a_plan_whose_offsets_do_not_match_the_environment_is_refused(
        self,
    ) -> None:
        with self.assertRaises(ValueError) as error:
            run_bench(
                FakeSimRobot(),
                _plan(goal_offsets_rad=(0.3, 0.0, 0.0, 0.0)),
                clock=_Clock(),
            )
        self.assertIn("4 joint offsets", str(error.exception))

    def test_a_registry_holding_another_contract_is_refused(self) -> None:
        registry = SkillRegistry()
        registry.register(_skill(summary="A different reviewed action."))
        with self.assertRaises(ValueError) as error:
            run_bench(
                FakeSimRobot(),
                _plan(),
                registry=registry,
                clock=_Clock(),
            )
        self.assertIn("different contract", str(error.exception))

    def test_a_real_robot_is_refused_before_anything_moves(self) -> None:
        robot = RealFakeRobot()
        with self.assertRaises(ValueError):
            run_bench(robot, _plan(), clock=_Clock())
        self.assertEqual(robot.commands, [])


class WatchedRunTests(unittest.TestCase):
    """Watching a run must not change it."""

    def test_frames_are_published_while_the_run_advances(self) -> None:
        robot = FakeSimRobot()
        run_bench(robot, _plan(), clock=_Clock(), frames=object())
        self.assertGreater(robot.published, 0)

    def test_a_watched_run_commands_the_same_motion(self) -> None:
        unwatched = FakeSimRobot()
        watched = FakeSimRobot()
        first = run_bench(unwatched, _plan(), clock=_Clock())
        second = run_bench(
            watched, _plan(), clock=_Clock(), frames=object()
        )
        self.assertEqual(unwatched.commands, watched.commands)
        self.assertEqual(first.halted, second.halted)

    def test_an_environment_that_cannot_render_is_refused(self) -> None:
        class Blind(FakeSimRobot):
            publish_frames = None  # type: ignore[assignment]

        with self.assertRaises(TypeError) as error:
            run_bench(Blind(), _plan(), clock=_Clock(), frames=object())
        self.assertIn("publishes no frames", str(error.exception))


@unittest.skipUnless(_HAS_SIMULATION, _SKIP_REASON)
class SimulatedG1BenchTest(unittest.TestCase):
    """The assembly, on the MuJoCo G1 it exists to drive.

    One test, deliberately: this is the only place where the whole inner loop
    runs against real physics, and what it asserts is that the composition holds
    end to end, not any particular number.
    """

    def test_the_inner_loop_runs_end_to_end_on_the_g1(self) -> None:
        from vegapunk.embodied.simulation import (
            G1_LEFT_ARM_JOINTS,
            SimulatedG1,
            SimulatedSupervision,
        )

        robot = SimulatedG1(
            supervision=SimulatedSupervision(
                guardian_present=True,
                estop_engaged=False,
                estop_reachable=True,
                workspace_clear=True,
            ),
            control_frequency_hz=50.0,
        )
        self.addCleanup(robot.close)

        offsets = tuple(
            0.3 if index == 1 else 0.0
            for index in range(len(G1_LEFT_ARM_JOINTS))
        )
        report = run_bench(
            robot,
            _plan(
                goal_offsets_rad=offsets,
                candidate_rates_rps=(0.3, 0.6, 0.9),
                environment_id="sim-g1-left-arm",
                envelope=SafetyEnvelope(
                    max_duration_s=20.0,
                    max_joint_velocity_rps=1.5,
                    max_end_effector_force_n=50.0,
                    workspace_bounds_m=(
                        (-1.0, 1.0),
                        (-1.0, 1.0),
                        (0.0, 2.0),
                    ),
                ),
                camera_map={},
            ),
            clock=_Clock(),
        )
        self.assertEqual(report.halted, HALTED_COMPLETED, report.halt_detail)
        self.assertEqual(len(report.stages), 2)
        decision = report.hardware_decision
        assert decision is not None
        self.assertFalse(decision.admitted)


if __name__ == "__main__":
    unittest.main()
