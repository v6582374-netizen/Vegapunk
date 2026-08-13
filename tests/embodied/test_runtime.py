from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from vegapunk.embodied.admission import (
    STAGE_HARDWARE_SUPERVISED,
    STAGE_OFFLINE_REPLAY,
    STAGE_POLICY_EVALUATION,
    STAGE_SHADOW_MODE,
    AdmissionLedger,
    EvidenceRecord,
    HumanApproval,
)
from vegapunk.embodied.embodiment import EmbodimentProfile
from vegapunk.embodied.loop import ExecutionLoop
from vegapunk.embodied.runtime import (
    DeterministicJointRuntime,
    JointPoseGoal,
    RobotState,
)
from vegapunk.embodied.safety import (
    ABORT_HUMAN_STOP,
    AbortDirective,
    SafetyEnvelope,
    SafetySupervisor,
)
from vegapunk.embodied.skill import (
    SKILL_KIND_DETERMINISTIC,
    PhysicalSkill,
    SkillRegistry,
)
from vegapunk.embodied.trajectory import (
    OUTCOME_ABORTED,
    OUTCOME_FAILED_VERIFICATION,
    OUTCOME_SUCCEEDED,
    TrajectoryLedger,
)

_NOW = datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)

_EMBODIMENT = EmbodimentProfile(
    robot_model="unitree_g1",
    arm_dof=7,
    end_effector="dex1_1",
    camera_map={"observation.images.top": "head_rgb"},
    control_frequency_hz=30.0,
    control_authority="arm_and_gripper",
    state_dim=16,
    action_dim=16,
    onboard_image_service=True,
)

_ENVELOPE = SafetyEnvelope(
    max_duration_s=20.0,
    max_joint_velocity_rps=1.5,
    max_end_effector_force_n=20.0,
    workspace_bounds_m=((-0.5, 0.5), (-0.4, 0.4), (0.0, 1.2)),
)


def _skill(**overrides: object) -> PhysicalSkill:
    fields: dict[str, object] = dict(
        skill_id="home_arm",
        revision=1,
        kind=SKILL_KIND_DETERMINISTIC,
        summary="Return the arm to its home pose.",
        parameters=(),
        preconditions=("workspace_clear", "guardian_present"),
        postconditions=("at_home_pose",),
        abort_conditions=("force_exceeded",),
        max_duration_s=5.0,
        reviewed_by="loongge",
    )
    fields.update(overrides)
    return PhysicalSkill(**fields)  # type: ignore[arg-type]


class FakeRobot:
    """A two-joint robot that tracks commands exactly."""

    def __init__(self, positions=(0.0, 0.0), **state_overrides):
        self.positions = tuple(positions)
        self.commands: list[tuple[float, ...]] = []
        self.holds = 0
        self.state_overrides = dict(state_overrides)
        self.moving = False

    def read_state(self) -> RobotState:
        fields = dict(
            joint_positions_rad=self.positions,
            joint_velocity_rps=(0.0,) * len(self.positions),
            end_effector_force_n=1.0,
            end_effector_position_m=(0.1, 0.0, 0.8),
            guardian_present=True,
            estop_engaged=False,
            estop_reachable=True,
            workspace_clear=True,
            age_s=0.05,
        )
        fields.update(self.state_overrides)
        return RobotState(**fields)

    def command_joint_positions(self, positions_rad) -> None:
        self.commands.append(tuple(positions_rad))
        self.positions = tuple(positions_rad)
        self.moving = True

    def hold(self) -> None:
        self.holds += 1
        self.moving = False


def _runtime(robot: FakeRobot, goal: JointPoseGoal, clock=None):
    return DeterministicJointRuntime(
        robot=robot,
        goals=(goal,),
        control_frequency_hz=30.0,
        max_joint_velocity_rps=1.5,
        clock=clock,
    )


def _goal(**overrides: object) -> JointPoseGoal:
    fields: dict[str, object] = dict(
        skill_version_id="home_arm@1",
        target_joint_positions_rad=(0.5, -0.5),
        satisfies=("at_home_pose",),
    )
    fields.update(overrides)
    return JointPoseGoal(**fields)  # type: ignore[arg-type]


class JointPoseGoalTests(unittest.TestCase):
    def test_a_goal_must_name_a_postcondition_it_demonstrates(self) -> None:
        with self.assertRaises(ValueError) as caught:
            _goal(satisfies=())
        self.assertIn("postcondition", str(caught.exception))

    def test_a_goal_requires_a_target(self) -> None:
        with self.assertRaises(ValueError):
            _goal(target_joint_positions_rad=())

    def test_tolerance_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            _goal(tolerance_rad=0.0)

    def test_a_differently_shaped_pose_is_never_reached(self) -> None:
        self.assertFalse(_goal().reached((0.5,)))


class DeterministicRuntimeTests(unittest.TestCase):
    def test_it_refuses_a_skill_with_no_registered_goal(self) -> None:
        registry = SkillRegistry()
        registry.register(_skill())
        runtime = _runtime(FakeRobot(), _goal(skill_version_id="other@1"))
        with self.assertRaises(KeyError) as caught:
            runtime.start(registry.select("home_arm", {}))
        self.assertIn("improvise", str(caught.exception))

    def test_no_single_command_exceeds_one_control_period_of_travel(
        self,
    ) -> None:
        robot = FakeRobot(positions=(0.0, 0.0))
        goal = _goal(target_joint_positions_rad=(1.2, -1.2))
        runtime = _runtime(robot, goal)
        registry = SkillRegistry()
        registry.register(_skill())
        selection = registry.select("home_arm", {})

        runtime.start(selection)
        previous = (0.0, 0.0)
        for _ in range(200):
            step = runtime.step()
            for before, after in zip(previous, robot.commands[-1]):
                self.assertLessEqual(
                    abs(after - before), runtime.max_step_rad + 1e-9
                )
            previous = robot.commands[-1]
            if step.complete:
                break
        self.assertTrue(step.complete)
        self.assertTrue(goal.reached(robot.positions))

    def test_it_reports_completion_without_commanding_a_stopped_robot(
        self,
    ) -> None:
        robot = FakeRobot(positions=(0.5, -0.5))
        runtime = _runtime(robot, _goal())
        registry = SkillRegistry()
        registry.register(_skill())
        runtime.start(registry.select("home_arm", {}))
        step = runtime.step()
        self.assertTrue(step.complete)
        with self.assertRaises(RuntimeError):
            runtime.step()

    def test_abort_latches_and_holds(self) -> None:
        robot = FakeRobot(positions=(0.0, 0.0))
        runtime = _runtime(robot, _goal())
        registry = SkillRegistry()
        registry.register(_skill())
        runtime.start(registry.select("home_arm", {}))
        runtime.step()
        runtime.abort(AbortDirective(cause=ABORT_HUMAN_STOP, detail="estop"))
        self.assertEqual(robot.holds, 1)
        commanded = len(robot.commands)
        with self.assertRaises(RuntimeError):
            runtime.step()
        self.assertEqual(len(robot.commands), commanded)

    def test_an_aborted_run_claims_no_postcondition(self) -> None:
        robot = FakeRobot(positions=(0.5, -0.5))
        runtime = _runtime(robot, _goal())
        registry = SkillRegistry()
        registry.register(_skill())
        runtime.start(registry.select("home_arm", {}))
        runtime.step()
        self.assertEqual(runtime.postconditions(), {"at_home_pose": True})
        runtime.abort(AbortDirective(cause=ABORT_HUMAN_STOP, detail="estop"))
        self.assertEqual(runtime.postconditions(), {"at_home_pose": False})

    def test_it_cannot_be_reused_across_runs(self) -> None:
        registry = SkillRegistry()
        registry.register(_skill())
        selection = registry.select("home_arm", {})
        runtime = _runtime(FakeRobot(positions=(0.5, -0.5)), _goal())
        runtime.start(selection)
        with self.assertRaises(RuntimeError):
            runtime.start(selection)

    def test_step_before_start_is_refused(self) -> None:
        runtime = _runtime(FakeRobot(), _goal())
        with self.assertRaises(RuntimeError):
            runtime.step()

    def test_a_joint_count_mismatch_is_an_error_not_a_move(self) -> None:
        robot = FakeRobot(positions=(0.0, 0.0, 0.0))
        runtime = _runtime(robot, _goal())
        registry = SkillRegistry()
        registry.register(_skill())
        with self.assertRaises(ValueError):
            runtime.start(registry.select("home_arm", {}))
        self.assertEqual(robot.commands, [])

    def test_observe_reports_state_without_commanding_motion(self) -> None:
        robot = FakeRobot()
        runtime = _runtime(robot, _goal())
        observation = runtime.observe()
        self.assertEqual(robot.commands, [])
        self.assertTrue(observation.workspace_clear)
        self.assertEqual(observation.elapsed_s, 0.0)

    def test_required_duration_is_measured_from_the_current_pose(self) -> None:
        registry = SkillRegistry()
        registry.register(_skill())
        selection = registry.select("home_arm", {})
        at_goal = _runtime(FakeRobot(positions=(0.5, -0.5)), _goal())
        self.assertEqual(at_goal.required_duration_s(selection), 0.0)
        far = _runtime(FakeRobot(positions=(0.0, 0.0)), _goal())
        self.assertGreater(far.required_duration_s(selection), 0.0)

    def test_elapsed_time_comes_from_the_clock(self) -> None:
        ticks = iter([100.0, 100.5, 100.5, 100.5])
        robot = FakeRobot(positions=(0.5, -0.5))
        runtime = _runtime(robot, _goal(), clock=lambda: next(ticks))
        registry = SkillRegistry()
        registry.register(_skill())
        runtime.start(registry.select("home_arm", {}))
        step = runtime.step()
        self.assertAlmostEqual(step.observation.elapsed_s, 0.5)


class RuntimeUnderTheGovernedLoopTests(unittest.TestCase):
    """The point of the runtime: the loop's guarantees still hold with it."""

    def _admitted_loop(self, trajectories=None):
        registry = SkillRegistry()
        skill = registry.register(_skill())
        admission = AdmissionLedger()
        for stage in (
            STAGE_POLICY_EVALUATION,
            STAGE_OFFLINE_REPLAY,
            STAGE_SHADOW_MODE,
        ):
            admission.record(
                EvidenceRecord(
                    stage=stage,
                    skill_version_id=skill.version_id,
                    embodiment_digest=_EMBODIMENT.digest(),
                    policy_digest=None,
                    attempts=20,
                    successes=20,
                    safety_violations=0,
                    recorded_at=_NOW - timedelta(days=1),
                )
            )
        approval = HumanApproval(
            skill_version_id=skill.version_id,
            embodiment_digest=_EMBODIMENT.digest(),
            policy_digest=None,
            approver="loongge",
            approved_at=_NOW - timedelta(minutes=10),
            statement="Workspace clear, guardian present, estop tested.",
            evidence_digest=admission.evidence_digest(
                skill.version_id, _EMBODIMENT.digest(), None
            ),
        )
        loop = ExecutionLoop(
            registry=registry,
            embodiment=_EMBODIMENT,
            supervisor=SafetySupervisor(_ENVELOPE),
            admission=admission,
            trajectories=trajectories or TrajectoryLedger(),
        )
        return loop, registry, approval

    def test_a_deterministic_move_can_succeed_end_to_end(self) -> None:
        loop, registry, approval = self._admitted_loop()
        robot = FakeRobot(positions=(0.0, 0.0))
        goal = _goal(target_joint_positions_rad=(0.2, -0.2))
        runtime = _runtime(robot, goal)
        report = loop.run(
            selection=registry.select("home_arm", {}),
            runtime=runtime,
            run_id="r1",
            stage=STAGE_HARDWARE_SUPERVISED,
            now=_NOW,
            approval=approval,
        )
        self.assertEqual(report.outcome, OUTCOME_SUCCEEDED)
        self.assertEqual(robot.holds, 0)
        self.assertTrue(report.trajectory.stream_complete)

    def test_an_estop_during_motion_aborts_and_holds_the_robot(self) -> None:
        loop, registry, approval = self._admitted_loop()
        robot = FakeRobot(positions=(0.0, 0.0))
        goal = _goal(target_joint_positions_rad=(1.2, -1.2))
        runtime = _runtime(robot, goal)

        original_read = robot.read_state
        counter = {"reads": 0}

        def read_state():
            counter["reads"] += 1
            if counter["reads"] > 4:
                robot.state_overrides["estop_engaged"] = True
            return original_read()

        robot.read_state = read_state  # type: ignore[method-assign]

        report = loop.run(
            selection=registry.select("home_arm", {}),
            runtime=runtime,
            run_id="r2",
            stage=STAGE_HARDWARE_SUPERVISED,
            now=_NOW,
            approval=approval,
        )
        self.assertEqual(report.outcome, OUTCOME_ABORTED)
        self.assertEqual(report.trajectory.abort_cause, ABORT_HUMAN_STOP)
        self.assertEqual(robot.holds, 1)
        self.assertFalse(robot.moving)

    def test_a_goal_that_proves_less_than_the_skill_fails_verification(
        self,
    ) -> None:
        registry = SkillRegistry()
        skill = registry.register(
            _skill(
                skill_id="place_cup",
                postconditions=("at_home_pose", "cup_upright"),
            )
        )
        admission = AdmissionLedger()
        for stage in (
            STAGE_POLICY_EVALUATION,
            STAGE_OFFLINE_REPLAY,
            STAGE_SHADOW_MODE,
        ):
            admission.record(
                EvidenceRecord(
                    stage=stage,
                    skill_version_id=skill.version_id,
                    embodiment_digest=_EMBODIMENT.digest(),
                    policy_digest=None,
                    attempts=20,
                    successes=20,
                    safety_violations=0,
                    recorded_at=_NOW - timedelta(days=1),
                )
            )
        approval = HumanApproval(
            skill_version_id=skill.version_id,
            embodiment_digest=_EMBODIMENT.digest(),
            policy_digest=None,
            approver="loongge",
            approved_at=_NOW - timedelta(minutes=10),
            statement="Workspace clear, guardian present, estop tested.",
            evidence_digest=admission.evidence_digest(
                skill.version_id, _EMBODIMENT.digest(), None
            ),
        )
        loop = ExecutionLoop(
            registry=registry,
            embodiment=_EMBODIMENT,
            supervisor=SafetySupervisor(_ENVELOPE),
            admission=admission,
            trajectories=TrajectoryLedger(),
        )
        runtime = _runtime(
            FakeRobot(positions=(0.5, -0.5)),
            _goal(skill_version_id="place_cup@1"),
        )
        report = loop.run(
            selection=registry.select("place_cup", {}),
            runtime=runtime,
            run_id="r3",
            stage=STAGE_HARDWARE_SUPERVISED,
            now=_NOW,
            approval=approval,
        )
        self.assertEqual(report.outcome, OUTCOME_FAILED_VERIFICATION)
        self.assertTrue(
            any(
                "cup_upright" in finding
                for finding in report.trajectory.findings
            )
        )

    def test_preflight_refusal_never_commands_motion(self) -> None:
        loop, registry, approval = self._admitted_loop()
        robot = FakeRobot(positions=(0.0, 0.0), workspace_clear=False)
        runtime = _runtime(robot, _goal())
        report = loop.run(
            selection=registry.select("home_arm", {}),
            runtime=runtime,
            run_id="r4",
            stage=STAGE_HARDWARE_SUPERVISED,
            now=_NOW,
            approval=approval,
        )
        self.assertEqual(robot.commands, [])
        self.assertFalse(report.succeeded)


if __name__ == "__main__":
    unittest.main()
