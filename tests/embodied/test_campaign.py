"""What a campaign may and may not conclude from repeated simulated runs."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Mapping, Optional, Sequence

from vegapunk.embodied.admission import (
    MINIMUM_STAGE_ATTEMPTS,
    STAGE_HARDWARE_SUPERVISED,
    STAGE_OFFLINE_REPLAY,
    STAGE_POLICY_EVALUATION,
    STAGE_SHADOW_MODE,
    AdmissionLedger,
    EvidenceRecord,
)
from vegapunk.embodied.campaign import (
    HALTED_ABORTED,
    HALTED_COMPLETED,
    HALTED_REFUSED,
    AttemptVariation,
    RegimeEnvironment,
    RegimeSchedule,
    SimulatedCampaignEnvironment,
    SimulationCampaign,
    VariationSchedule,
)
from vegapunk.embodied.embodiment import (
    UNIFOLM_VLA_BASE_G1_EE6D,
    EmbodimentProfile,
)
from vegapunk.embodied.fidelity import SimulatedConfiguration
from vegapunk.embodied.loop import ExecutionLoop, RuntimeStep
from vegapunk.embodied.regime import (
    AXIS_FRICTION_SCALE,
    AXIS_JOINT_OFFSET_RAD,
    AXIS_PAYLOAD_KG,
    DEFAULT_CONTACT_REGIME,
    Regime,
    RegimeAxis,
    RegimeSample,
)
from vegapunk.embodied.safety import (
    ABORT_HUMAN_STOP,
    Observation,
    SafetyEnvelope,
    SafetySupervisor,
)
from vegapunk.embodied.skill import (
    SKILL_KIND_DETERMINISTIC,
    SKILL_KIND_VLA,
    PhysicalSkill,
    SkillRegistry,
)
from vegapunk.embodied.trajectory import (
    OUTCOME_ABORTED,
    OUTCOME_FAILED_VERIFICATION,
    OUTCOME_REFUSED,
    OUTCOME_SUCCEEDED,
    RunClearance,
    TrajectoryLedger,
)

NOW = datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)

LEGACY_VARIATION_DIGEST = "cb6b661c69b8bef2"
"""The digest of a sample-less variation, pinned rather than recomputed.

    seed 4, joint_offsets_rad (0.01, -0.02)

Written as a literal on purpose. Deriving it from the module's own digest
helper would make this test agree with any encoding change it was meant to
catch, and the point of it is that attempt records written before regimes
existed still hash to what they hashed to then.
"""


def _observation(**overrides: object) -> Observation:
    fields: dict[str, object] = {
        "elapsed_s": 0.0,
        "age_s": 0.02,
        "joint_velocity_rps": (0.0, 0.0),
        "end_effector_force_n": 1.0,
        "end_effector_position_m": (0.1, 0.0, 0.8),
        "guardian_present": True,
        "estop_engaged": False,
        "estop_reachable": True,
        "workspace_clear": True,
    }
    fields.update(overrides)
    return Observation(**fields)


class ScriptedRuntime:
    """A runtime whose outcome is decided by the test, not by physics."""

    def __init__(
        self,
        succeeds: bool = True,
        estop_at_step: Optional[int] = None,
    ) -> None:
        self._succeeds = succeeds
        self._estop_at_step = estop_at_step
        self._steps = 0
        self.started = False
        self.aborted = False

    def observe(self) -> Observation:
        return _observation()

    def start(self, selection: object) -> None:
        self.started = True

    def step(self) -> RuntimeStep:
        self._steps += 1
        if self._estop_at_step == self._steps:
            return RuntimeStep(
                observation=_observation(elapsed_s=0.5, estop_engaged=True)
            )
        return RuntimeStep(
            observation=_observation(elapsed_s=1.0), complete=True
        )

    def abort(self, directive: object) -> None:
        self.aborted = True

    def postconditions(self) -> Mapping[str, bool]:
        return {"at_home_pose": self._succeeds}


class FakeResettableRobot:
    """Records the initial condition it was asked to start each attempt from."""

    def __init__(self) -> None:
        self.resets: list[Optional[tuple[float, ...]]] = []

    def reset(
        self, joint_offsets_rad: Optional[Sequence[float]] = None
    ) -> None:
        self.resets.append(
            None
            if joint_offsets_rad is None
            else tuple(float(v) for v in joint_offsets_rad)
        )


def _skill() -> PhysicalSkill:
    return PhysicalSkill(
        skill_id="home_arm",
        revision=1,
        kind=SKILL_KIND_DETERMINISTIC,
        summary="Return the arm to its home pose.",
        parameters=(),
        preconditions=("workspace_clear",),
        postconditions=("at_home_pose",),
        abort_conditions=("force_exceeded",),
        max_duration_s=5.0,
        reviewed_by="reviewer",
    )


def _vla_skill() -> PhysicalSkill:
    """A skill whose motion comes from a checkpoint with a camera contract."""
    return PhysicalSkill(
        skill_id="place_block",
        revision=1,
        kind=SKILL_KIND_VLA,
        summary="Place the held block on the table.",
        parameters=(),
        preconditions=("workspace_clear",),
        postconditions=("block_placed",),
        abort_conditions=("force_exceeded",),
        max_duration_s=5.0,
        reviewed_by="reviewer",
        policy=UNIFOLM_VLA_BASE_G1_EE6D,
    )


def _embodiment() -> EmbodimentProfile:
    return EmbodimentProfile(
        robot_model="unitree_g1",
        arm_dof=7,
        end_effector="dex1_1",
        camera_map={"observation.images.top": "head_rgb"},
        control_frequency_hz=50.0,
        control_authority="arm_and_gripper",
        state_dim=16,
        action_dim=16,
        onboard_image_service=True,
    )


def _supervisor() -> SafetySupervisor:
    return SafetySupervisor(
        SafetyEnvelope(
            max_duration_s=20.0,
            max_joint_velocity_rps=1.5,
            max_end_effector_force_n=20.0,
            workspace_bounds_m=((-0.5, 0.5), (-0.4, 0.4), (0.0, 1.2)),
        )
    )


class Harness:
    """One registry, embodiment, loop and pair of ledgers, wired together."""

    def __init__(self, stage: str = STAGE_OFFLINE_REPLAY) -> None:
        self.skill = _skill()
        self.registry = SkillRegistry()
        self.registry.register(self.skill)
        self.embodiment = _embodiment()
        self.admission = AdmissionLedger()
        self.trajectories = TrajectoryLedger()
        self.loop = ExecutionLoop(
            registry=self.registry,
            embodiment=self.embodiment,
            supervisor=_supervisor(),
            admission=self.admission,
            trajectories=self.trajectories,
        )
        self.selection = self.registry.select("home_arm", {})
        self.robot = FakeResettableRobot()
        self.stage = stage
        self.now = NOW

    def campaign(self) -> SimulationCampaign:
        return SimulationCampaign(
            loop=self.loop,
            admission=self.admission,
            trajectories=self.trajectories,
            clock=self._clock,
            stage=self.stage,
        )

    def environment(
        self,
        succeeds: bool = True,
        estop_at_step: Optional[int] = None,
        **configuration_overrides: object,
    ) -> SimulatedCampaignEnvironment:
        self.runtimes: list[ScriptedRuntime] = []

        def factory() -> ScriptedRuntime:
            runtime = ScriptedRuntime(
                succeeds=succeeds, estop_at_step=estop_at_step
            )
            self.runtimes.append(runtime)
            return runtime

        return SimulatedCampaignEnvironment(
            robot=self.robot,
            runtime_factory=factory,
            configuration=self.configuration(**configuration_overrides),
        )

    def configuration(self, **overrides: object) -> SimulatedConfiguration:
        """An environment that matches ``_embodiment`` unless a test breaks it."""
        fields: dict[str, object] = {
            "environment_id": "sim-g1-left-arm",
            "is_real_robot": False,
            "control_frequency_hz": self.embodiment.control_frequency_hz,
            "controlled_joint_names": tuple(
                f"joint_{index}" for index in range(self.embodiment.arm_dof)
            ),
            "end_effector": self.embodiment.end_effector,
            "control_authority": self.embodiment.control_authority,
        }
        fields.update(overrides)
        return SimulatedConfiguration(**fields)

    def seed_prior_stage(self) -> None:
        """Record the policy_evaluation evidence offline_replay requires."""
        self.admission.record(
            EvidenceRecord(
                stage=STAGE_POLICY_EVALUATION,
                skill_version_id=self.skill.version_id,
                embodiment_digest=self.embodiment.digest(),
                policy_digest=None,
                attempts=MINIMUM_STAGE_ATTEMPTS,
                successes=MINIMUM_STAGE_ATTEMPTS,
                safety_violations=0,
                recorded_at=NOW - timedelta(days=1),
            )
        )

    def _clock(self) -> datetime:
        self.now = self.now + timedelta(seconds=1)
        return self.now


class VariationScheduleTest(unittest.TestCase):
    """Repeated attempts have to be different runs, reproducibly."""

    def test_the_same_seed_and_index_reproduce_the_same_offsets(self) -> None:
        first = VariationSchedule(joint_count=7, seed=11).variation(3)
        second = VariationSchedule(joint_count=7, seed=11).variation(3)
        self.assertEqual(
            first.joint_offsets_rad, second.joint_offsets_rad
        )
        self.assertEqual(first.digest(), second.digest())

    def test_different_attempts_get_different_initial_conditions(self) -> None:
        schedule = VariationSchedule(joint_count=7, seed=11)
        digests = {schedule.variation(index).digest() for index in range(10)}
        self.assertEqual(len(digests), 10)

    def test_offsets_stay_inside_the_declared_bound(self) -> None:
        schedule = VariationSchedule(
            joint_count=7, max_offset_rad=0.02, seed=3
        )
        for index in range(20):
            for offset in schedule.variation(index).joint_offsets_rad:
                self.assertLessEqual(abs(offset), 0.02)

    def test_a_schedule_that_cannot_vary_anything_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            VariationSchedule(joint_count=7, max_offset_rad=0.0)
        with self.assertRaises(ValueError):
            VariationSchedule(joint_count=0)

    def test_a_variation_without_offsets_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            AttemptVariation(index=0, seed=0, joint_offsets_rad=())

    def test_a_negative_attempt_index_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            VariationSchedule(joint_count=2).variation(-1)


class CampaignStageTest(unittest.TestCase):
    """A campaign iterates simulation only."""

    def test_only_simulated_stages_may_be_iterated(self) -> None:
        harness = Harness()
        for stage in (STAGE_SHADOW_MODE, STAGE_HARDWARE_SUPERVISED):
            with self.subTest(stage=stage):
                with self.assertRaises(ValueError) as error:
                    SimulationCampaign(
                        loop=harness.loop,
                        admission=harness.admission,
                        trajectories=harness.trajectories,
                        clock=lambda: NOW,
                        stage=stage,
                    )
                self.assertIn("simulated", str(error.exception))

    def test_both_simulated_stages_are_accepted(self) -> None:
        harness = Harness()
        for stage in (STAGE_POLICY_EVALUATION, STAGE_OFFLINE_REPLAY):
            with self.subTest(stage=stage):
                campaign = SimulationCampaign(
                    loop=harness.loop,
                    admission=harness.admission,
                    trajectories=harness.trajectories,
                    clock=lambda: NOW,
                    stage=stage,
                )
                self.assertEqual(campaign.stage, stage)


class CampaignIterationTest(unittest.TestCase):
    """Each attempt is a fresh, differently started, governed run."""

    def setUp(self) -> None:
        self.harness = Harness()
        self.harness.seed_prior_stage()

    def test_every_attempt_starts_from_its_own_initial_condition(self) -> None:
        report = self.harness.campaign().run(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(),
            schedule=VariationSchedule(joint_count=7, seed=5),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )
        self.assertEqual(len(self.harness.robot.resets), MINIMUM_STAGE_ATTEMPTS)
        self.assertEqual(
            len({reset for reset in self.harness.robot.resets}),
            MINIMUM_STAGE_ATTEMPTS,
        )
        self.assertEqual(
            len({attempt.variation_digest for attempt in report.attempts}),
            MINIMUM_STAGE_ATTEMPTS,
        )

    def test_each_attempt_gets_a_runtime_that_never_ran_before(self) -> None:
        self.harness.campaign().run(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(),
            schedule=VariationSchedule(joint_count=7),
            planned_attempts=3,
        )
        self.assertEqual(len(self.harness.runtimes), 3)
        self.assertEqual(len({id(r) for r in self.harness.runtimes}), 3)
        self.assertTrue(all(r.started for r in self.harness.runtimes))

    def test_every_attempt_writes_exactly_one_trajectory(self) -> None:
        report = self.harness.campaign().run(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(),
            schedule=VariationSchedule(joint_count=7),
            planned_attempts=4,
        )
        self.assertEqual(len(self.harness.trajectories.records()), 4)
        self.assertEqual(
            [attempt.run_id for attempt in report.attempts],
            ["c1-000", "c1-001", "c1-002", "c1-003"],
        )

    def test_a_campaign_must_plan_at_least_one_attempt(self) -> None:
        with self.assertRaises(ValueError):
            self.harness.campaign().run(
                campaign_id="c1",
                selection=self.harness.selection,
                environment=self.harness.environment(),
                schedule=VariationSchedule(joint_count=7),
                planned_attempts=0,
            )

    def test_an_unnamed_campaign_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.harness.campaign().run(
                campaign_id="",
                selection=self.harness.selection,
                environment=self.harness.environment(),
                schedule=VariationSchedule(joint_count=7),
                planned_attempts=1,
            )


class CampaignEvidenceTest(unittest.TestCase):
    """Evidence is derived from the recorded runs, never asserted."""

    def setUp(self) -> None:
        self.harness = Harness()
        self.harness.seed_prior_stage()

    def test_a_full_successful_campaign_opens_the_next_stage(self) -> None:
        report = self.harness.campaign().run(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(),
            schedule=VariationSchedule(joint_count=7),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )
        self.assertTrue(report.completed)
        self.assertEqual(report.halted, HALTED_COMPLETED)
        self.assertEqual(report.evidence.attempts, MINIMUM_STAGE_ATTEMPTS)
        self.assertEqual(report.evidence.successes, MINIMUM_STAGE_ATTEMPTS)
        self.assertEqual(report.next_stage, STAGE_SHADOW_MODE)
        self.assertTrue(report.next_stage_admitted)
        self.assertEqual(report.next_stage_blocking_reasons, ())

    def test_too_few_attempts_do_not_open_the_next_stage(self) -> None:
        report = self.harness.campaign().run(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(),
            schedule=VariationSchedule(joint_count=7),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS - 1,
        )
        self.assertTrue(report.completed)
        self.assertFalse(report.next_stage_admitted)
        self.assertTrue(
            any(
                "attempts" in reason
                for reason in report.next_stage_blocking_reasons
            )
        )

    def test_failed_verification_counts_as_an_attempt_but_not_a_success(
        self,
    ) -> None:
        report = self.harness.campaign().run(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(succeeds=False),
            schedule=VariationSchedule(joint_count=7),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )
        self.assertTrue(report.completed)
        self.assertEqual(report.evidence.attempts, MINIMUM_STAGE_ATTEMPTS)
        self.assertEqual(report.evidence.successes, 0)
        self.assertEqual(report.successes, 0)
        self.assertTrue(
            all(
                attempt.outcome == OUTCOME_FAILED_VERIFICATION
                for attempt in report.attempts
            )
        )
        self.assertFalse(report.next_stage_admitted)

    def test_the_campaign_cannot_disagree_with_the_trajectory_ledger(
        self,
    ) -> None:
        report = self.harness.campaign().run
        result = report(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(),
            schedule=VariationSchedule(joint_count=7),
            planned_attempts=6,
        )
        derived = self.harness.trajectories.derive_evidence(
            scope=result.scope,
            stage=STAGE_OFFLINE_REPLAY,
            recorded_at=NOW,
        )
        self.assertEqual(result.evidence.attempts, derived.attempts)
        self.assertEqual(result.evidence.successes, derived.successes)

    def test_evidence_accumulates_across_campaigns(self) -> None:
        campaign = self.harness.campaign()
        first = campaign.run(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(),
            schedule=VariationSchedule(joint_count=7, seed=1),
            planned_attempts=6,
        )
        second = campaign.run(
            campaign_id="c2",
            selection=self.harness.selection,
            environment=self.harness.environment(),
            schedule=VariationSchedule(joint_count=7, seed=100),
            planned_attempts=6,
        )
        self.assertEqual(first.evidence.attempts, 6)
        self.assertEqual(second.evidence.attempts, 12)
        self.assertTrue(second.next_stage_admitted)

    def test_the_recorded_evidence_names_the_campaign(self) -> None:
        report = self.harness.campaign().run(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(),
            schedule=VariationSchedule(joint_count=7),
            planned_attempts=2,
        )
        self.assertIn("c1", report.evidence.notes)
        self.assertIn(report.evidence, self.harness.admission.records())


class CampaignHaltTest(unittest.TestCase):
    """Continuing past an abort or a refusal would misreport the evidence."""

    def setUp(self) -> None:
        self.harness = Harness()

    def test_a_refusal_halts_the_campaign_and_names_the_reason(self) -> None:
        report = self.harness.campaign().run(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(),
            schedule=VariationSchedule(joint_count=7),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )
        self.assertEqual(report.halted, HALTED_REFUSED)
        self.assertFalse(report.completed)
        self.assertEqual(len(report.attempts), 1)
        self.assertEqual(report.attempts[0].outcome, OUTCOME_REFUSED)
        self.assertEqual(report.executed_attempts, 0)
        self.assertEqual(report.evidence.attempts, 0)
        self.assertIn("policy_evaluation", report.halt_detail)

    def test_an_abort_halts_the_campaign_and_reports_the_quarantine(
        self,
    ) -> None:
        self.harness.seed_prior_stage()
        report = self.harness.campaign().run(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(estop_at_step=1),
            schedule=VariationSchedule(joint_count=7),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )
        self.assertEqual(report.halted, HALTED_ABORTED)
        self.assertEqual(len(report.attempts), 1)
        self.assertEqual(report.attempts[0].outcome, OUTCOME_ABORTED)
        self.assertEqual(report.attempts[0].abort_cause, ABORT_HUMAN_STOP)
        self.assertIn("quarantined", report.halt_detail)
        self.assertIn("c1-000", report.halt_detail)

    def test_an_abort_withdraws_the_next_stage_despite_the_arithmetic(
        self,
    ) -> None:
        """The quarantine, not the success rate, is what withdraws the stage.

        A human stop is not a safety violation and one abort among eleven runs
        still clears the 90% threshold, so the thresholds alone would report
        the next stage as open while the loop refuses every further run.
        """
        self.harness.seed_prior_stage()
        campaign = self.harness.campaign()
        campaign.run(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(),
            schedule=VariationSchedule(joint_count=7, seed=1),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )
        after = campaign.run(
            campaign_id="c2",
            selection=self.harness.selection,
            environment=self.harness.environment(estop_at_step=1),
            schedule=VariationSchedule(joint_count=7, seed=100),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )
        self.assertGreaterEqual(
            after.evidence.successes / after.evidence.attempts, 0.9
        )
        self.assertFalse(after.next_stage_admitted)
        self.assertTrue(
            any(
                "clearance" in reason
                for reason in after.next_stage_blocking_reasons
            )
        )

    def test_a_clean_campaign_still_reports_the_next_stage_open(self) -> None:
        """The quarantine check must not withhold an honest admission."""
        self.harness.seed_prior_stage()
        report = self.harness.campaign().run(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(),
            schedule=VariationSchedule(joint_count=7, seed=7),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )
        self.assertTrue(report.next_stage_admitted)
        self.assertEqual(report.next_stage_blocking_reasons, ())

    def test_a_campaign_after_an_uncleared_abort_is_refused_immediately(
        self,
    ) -> None:
        self.harness.seed_prior_stage()
        campaign = self.harness.campaign()
        campaign.run(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(estop_at_step=1),
            schedule=VariationSchedule(joint_count=7),
            planned_attempts=3,
        )
        blocked = campaign.run(
            campaign_id="c2",
            selection=self.harness.selection,
            environment=self.harness.environment(),
            schedule=VariationSchedule(joint_count=7, seed=50),
            planned_attempts=3,
        )
        self.assertEqual(blocked.halted, HALTED_REFUSED)
        self.assertIn("clearance", blocked.halt_detail)

    def test_a_human_clearance_lets_the_campaign_resume(self) -> None:
        self.harness.seed_prior_stage()
        campaign = self.harness.campaign()
        aborted = campaign.run(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(estop_at_step=1),
            schedule=VariationSchedule(joint_count=7),
            planned_attempts=3,
        )
        self.harness.trajectories.clear(
            RunClearance(
                run_id=aborted.attempts[0].run_id,
                reviewer="reviewer",
                statement="The estop was pressed during a rehearsal.",
                cleared_at=NOW,
            )
        )
        resumed = campaign.run(
            campaign_id="c2",
            selection=self.harness.selection,
            environment=self.harness.environment(),
            schedule=VariationSchedule(joint_count=7, seed=50),
            planned_attempts=3,
        )
        self.assertEqual(resumed.halted, HALTED_COMPLETED)
        self.assertEqual(resumed.successes, 3)


class CampaignFidelityTest(unittest.TestCase):
    """Iterating in the wrong environment would file evidence about another robot.

    The check is a raise rather than a recorded refusal on purpose. A refused
    run is a fact about this configuration; a misrepresenting environment
    produces no fact about it at all, so there is nothing to write into the
    scope's ledger.
    """

    def setUp(self) -> None:
        self.harness = Harness()
        self.harness.seed_prior_stage()

    def _run(self, **configuration_overrides: object) -> None:
        self.harness.campaign().run(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(**configuration_overrides),
            schedule=VariationSchedule(joint_count=7),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )

    def test_a_mismatched_cadence_stops_the_campaign_before_it_starts(
        self,
    ) -> None:
        with self.assertRaises(ValueError) as error:
            self._run(control_frequency_hz=200.0)
        message = str(error.exception)
        self.assertIn("does not represent", message)
        self.assertIn("200.0Hz", message)
        self.assertIn("sim-g1-left-arm", message)

    def test_a_misrepresenting_environment_writes_no_evidence_and_no_run(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            self._run(end_effector="gripper_2f85")
        self.assertEqual(self.harness.trajectories.records(), ())
        self.assertEqual(
            [record.stage for record in self.harness.admission.records()],
            [STAGE_POLICY_EVALUATION],
        )
        self.assertEqual(self.harness.robot.resets, [])

    def test_a_matching_environment_carries_its_fidelity_into_the_report(
        self,
    ) -> None:
        report = self.harness.campaign().run(
            campaign_id="c1",
            selection=self.harness.selection,
            environment=self.harness.environment(),
            schedule=VariationSchedule(joint_count=7),
            planned_attempts=2,
        )
        self.assertTrue(report.fidelity.represents)
        self.assertEqual(report.fidelity.environment_id, "sim-g1-left-arm")
        self.assertTrue(report.fidelity.unrepresented)
        self.assertIn(report.fidelity.digest(), report.evidence.notes)

    def test_a_policy_skill_needs_the_views_its_observation_is_built_from(
        self,
    ) -> None:
        """The camera contract is checked because the loop knows the skill.

        A deterministic skill reads no images, so the same environment is a
        faithful one for it. Which contract applies is the loop's to decide,
        not the campaign's, and this is the difference showing.
        """
        harness = Harness()
        harness.registry.register(_vla_skill())
        selection = harness.registry.select("place_block", {})
        with self.assertRaises(ValueError) as error:
            harness.campaign().run(
                campaign_id="c1",
                selection=selection,
                environment=harness.environment(),
                schedule=VariationSchedule(joint_count=7),
                planned_attempts=1,
            )
        self.assertIn("observation.images.top", str(error.exception))

    def test_a_real_robot_cannot_be_reset_to_a_chosen_initial_condition(
        self,
    ) -> None:
        harness = Harness()
        with self.assertRaises(ValueError) as error:
            SimulatedCampaignEnvironment(
                robot=harness.robot,
                runtime_factory=ScriptedRuntime,
                configuration=harness.configuration(is_real_robot=True),
            )
        self.assertIn("real robot", str(error.exception))


class CampaignApprovalTest(unittest.TestCase):
    """A campaign never carries a human approval into a simulated run."""

    def test_new_evidence_is_recorded_even_when_nothing_is_approved(
        self,
    ) -> None:
        harness = Harness()
        harness.seed_prior_stage()
        report = harness.campaign().run(
            campaign_id="c1",
            selection=harness.selection,
            environment=harness.environment(),
            schedule=VariationSchedule(joint_count=7),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )
        self.assertTrue(
            all(
                attempt.outcome == OUTCOME_SUCCEEDED
                for attempt in report.attempts
            )
        )
        self.assertTrue(report.next_stage_admitted)

    def test_hardware_admission_still_needs_a_human_after_a_campaign(
        self,
    ) -> None:
        harness = Harness()
        harness.seed_prior_stage()
        campaign = harness.campaign()
        campaign.run(
            campaign_id="c1",
            selection=harness.selection,
            environment=harness.environment(),
            schedule=VariationSchedule(joint_count=7),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )
        report = harness.loop.run(
            selection=harness.selection,
            runtime=ScriptedRuntime(),
            run_id="hardware-1",
            stage=STAGE_HARDWARE_SUPERVISED,
            now=NOW,
        )
        self.assertEqual(report.outcome, OUTCOME_REFUSED)
        self.assertTrue(
            any(
                "human approval" in finding
                for finding in report.trajectory.findings
            )
        )


class RegimeAwareRobot:
    """Records the pose *and* the world it was asked to start each attempt in.

    Separate from ``FakeResettableRobot`` because accepting a sample is exactly
    the capability ``RegimeEnvironment`` requires, and a fake that accepted one
    silently would hide the refusal that matters.
    """

    def __init__(self) -> None:
        self.resets: list[tuple[Optional[tuple[float, ...]], object]] = []

    def reset(
        self,
        joint_offsets_rad: Optional[Sequence[float]] = None,
        sample: Optional[RegimeSample] = None,
    ) -> None:
        self.resets.append(
            (
                None
                if joint_offsets_rad is None
                else tuple(float(v) for v in joint_offsets_rad),
                sample,
            )
        )


def _offset_regime(samples: int = 10, seed: int = 0) -> Regime:
    """A minimal regime that still declares the axis a schedule needs."""
    return Regime(
        axes=(
            RegimeAxis(
                name=AXIS_JOINT_OFFSET_RAD,
                low=0.01,
                high=0.05,
                unit="rad",
                rationale="a bounded start displacement, as the default uses",
            ),
            RegimeAxis(
                name=AXIS_FRICTION_SCALE,
                low=0.8,
                high=1.25,
                unit="dimensionless",
                rationale="the contact band the default regime declares",
            ),
        ),
        samples=samples,
        seed=seed,
    )


class AttemptVariationSampleTest(unittest.TestCase):
    """The one field that lets an attempt record name its world."""

    def test_a_variation_without_a_sample_keeps_its_original_encoding(
        self,
    ) -> None:
        """Otherwise every attempt recorded before regimes existed looks new."""
        variation = AttemptVariation(
            index=0, seed=4, joint_offsets_rad=(0.01, -0.02)
        )

        self.assertIsNone(variation.sample)
        self.assertEqual(variation.digest(), LEGACY_VARIATION_DIGEST)

    def test_a_sample_changes_the_digest(self) -> None:
        offsets = (0.01, -0.02)
        without = AttemptVariation(index=0, seed=4, joint_offsets_rad=offsets)
        with_sample = AttemptVariation(
            index=0,
            seed=4,
            joint_offsets_rad=offsets,
            sample=RegimeSample(
                index=0, seed=4, values={AXIS_PAYLOAD_KG: 0.5}
            ),
        )

        self.assertNotEqual(without.digest(), with_sample.digest())

    def test_two_worlds_at_the_same_pose_are_distinguishable(self) -> None:
        """A digest that ignored the world would report them as one attempt."""
        offsets = (0.01, -0.02)
        first = AttemptVariation(
            index=0,
            seed=4,
            joint_offsets_rad=offsets,
            sample=RegimeSample(
                index=0, seed=4, values={AXIS_PAYLOAD_KG: 0.5}
            ),
        )
        second = AttemptVariation(
            index=0,
            seed=4,
            joint_offsets_rad=offsets,
            sample=RegimeSample(
                index=0, seed=4, values={AXIS_PAYLOAD_KG: 0.9}
            ),
        )

        self.assertNotEqual(first.digest(), second.digest())

    def test_the_existing_construction_signature_still_works(self) -> None:
        positional = AttemptVariation(1, 2, (0.01,))

        self.assertEqual(positional.index, 1)
        self.assertEqual(positional.seed, 2)
        self.assertIsNone(positional.sample)


class RegimeScheduleTest(unittest.TestCase):
    """The schedule that varies the world, not only the pose."""

    def test_it_satisfies_the_duck_type_the_campaign_uses(self) -> None:
        schedule = RegimeSchedule(regime=_offset_regime(), joint_count=7)

        self.assertEqual(schedule.joint_count, 7)
        variation = schedule.variation(0)
        self.assertIsInstance(variation, AttemptVariation)
        self.assertEqual(len(variation.joint_offsets_rad), 7)

    def test_every_variation_carries_the_world_it_was_drawn_from(self) -> None:
        schedule = RegimeSchedule(regime=_offset_regime(), joint_count=7)

        for index in range(10):
            variation = schedule.variation(index)
            self.assertIsNotNone(variation.sample)
            self.assertEqual(variation.sample.index, index)
            self.assertIn(AXIS_FRICTION_SCALE, variation.sample.values)

    def test_offsets_respect_the_regimes_declared_magnitude(self) -> None:
        schedule = RegimeSchedule(regime=_offset_regime(), joint_count=7)

        for index in range(10):
            variation = schedule.variation(index)
            bound = variation.sample.value(AXIS_JOINT_OFFSET_RAD, 0.0)
            self.assertLessEqual(bound, 0.05)
            for offset in variation.joint_offsets_rad:
                self.assertLessEqual(abs(offset), bound + 1e-12)

    def test_it_is_reproducible_and_varied(self) -> None:
        first = RegimeSchedule(regime=_offset_regime(seed=11), joint_count=7)
        second = RegimeSchedule(regime=_offset_regime(seed=11), joint_count=7)

        self.assertEqual(
            first.variation(3).digest(), second.variation(3).digest()
        )
        digests = {first.variation(i).digest() for i in range(10)}
        self.assertEqual(len(digests), 10)

    def test_a_different_regime_seed_draws_different_worlds(self) -> None:
        first = RegimeSchedule(regime=_offset_regime(seed=1), joint_count=7)
        second = RegimeSchedule(regime=_offset_regime(seed=2), joint_count=7)

        self.assertNotEqual(
            first.variation(0).digest(), second.variation(0).digest()
        )

    def test_a_regime_without_a_joint_offset_axis_is_refused(self) -> None:
        """The campaign's contract is that attempts start differently."""
        regime = Regime(
            axes=(
                RegimeAxis(
                    name=AXIS_FRICTION_SCALE,
                    low=0.8,
                    high=1.25,
                    unit="dimensionless",
                    rationale="contact only",
                ),
            ),
            samples=10,
        )

        with self.assertRaises(ValueError) as caught:
            RegimeSchedule(regime=regime, joint_count=7)

        self.assertIn(AXIS_JOINT_OFFSET_RAD, str(caught.exception))

    def test_a_non_positive_joint_count_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            RegimeSchedule(regime=_offset_regime(), joint_count=0)

    def test_the_default_regime_drives_a_schedule(self) -> None:
        schedule = RegimeSchedule(
            regime=DEFAULT_CONTACT_REGIME, joint_count=7
        )

        variation = schedule.variation(0)
        self.assertEqual(len(variation.joint_offsets_rad), 7)
        self.assertEqual(
            set(variation.sample.values),
            set(DEFAULT_CONTACT_REGIME.axis_names()),
        )


class RegimeEnvironmentTest(unittest.TestCase):
    """The seam that installs a world, and what it refuses to run without."""

    def _environment(
        self, robot: object, **overrides: object
    ) -> RegimeEnvironment:
        harness = Harness()
        return RegimeEnvironment(
            robot=robot,
            runtime_factory=ScriptedRuntime,
            configuration=harness.configuration(**overrides),
        )

    def test_it_passes_both_the_pose_and_the_world_to_the_robot(self) -> None:
        robot = RegimeAwareRobot()
        environment = self._environment(robot)
        schedule = RegimeSchedule(regime=_offset_regime(), joint_count=7)
        variation = schedule.variation(2)

        runtime = environment.prepare(variation)

        self.assertIsInstance(runtime, ScriptedRuntime)
        self.assertEqual(len(robot.resets), 1)
        offsets, sample = robot.resets[0]
        self.assertEqual(offsets, variation.joint_offsets_rad)
        self.assertIs(sample, variation.sample)

    def test_a_fresh_runtime_per_attempt(self) -> None:
        environment = self._environment(RegimeAwareRobot())
        schedule = RegimeSchedule(regime=_offset_regime(), joint_count=7)

        first = environment.prepare(schedule.variation(0))
        second = environment.prepare(schedule.variation(1))

        self.assertIsNot(first, second)

    def test_a_variation_with_no_sample_is_refused(self) -> None:
        """Running it would report a regime the physics never applied."""
        environment = self._environment(RegimeAwareRobot())

        with self.assertRaises(ValueError) as caught:
            environment.prepare(
                AttemptVariation(index=0, seed=0, joint_offsets_rad=(0.01,))
            )

        self.assertIn("RegimeSchedule", str(caught.exception))

    def test_it_refuses_to_describe_a_real_robot(self) -> None:
        with self.assertRaises(ValueError):
            self._environment(RegimeAwareRobot(), is_real_robot=True)

    def test_a_robot_that_cannot_accept_a_world_is_refused(self) -> None:
        """A silently ignored sample is the failure this module prevents."""
        with self.assertRaises(ValueError) as caught:
            self._environment(FakeResettableRobot())

        self.assertIn("sample", str(caught.exception))

    def test_the_configuration_is_unchanged_by_the_regime(self) -> None:
        """The digest is the anchor every stage's evidence is scoped to."""
        environment = self._environment(RegimeAwareRobot())
        before = environment.configuration.digest()
        schedule = RegimeSchedule(regime=_offset_regime(), joint_count=7)

        for index in range(10):
            environment.prepare(schedule.variation(index))

        self.assertEqual(environment.configuration.digest(), before)


class CampaignUnderARegimeTest(unittest.TestCase):
    """A campaign iterating a regime concludes exactly what it did before."""

    def _schedule(self, harness: "Harness", seed: int = 0) -> RegimeSchedule:
        return RegimeSchedule(
            regime=_offset_regime(
                samples=MINIMUM_STAGE_ATTEMPTS, seed=seed
            ),
            joint_count=harness.embodiment.arm_dof,
        )

    def test_a_full_run_records_evidence_over_a_band_of_worlds(self) -> None:
        harness = Harness()
        harness.seed_prior_stage()
        robot = RegimeAwareRobot()

        report = harness.campaign().run(
            campaign_id="regime-campaign",
            selection=harness.selection,
            environment=RegimeEnvironment(
                robot=robot,
                runtime_factory=ScriptedRuntime,
                configuration=harness.configuration(),
            ),
            schedule=self._schedule(harness),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )

        self.assertEqual(report.halted, HALTED_COMPLETED)
        self.assertEqual(report.successes, MINIMUM_STAGE_ATTEMPTS)
        self.assertEqual(len(robot.resets), MINIMUM_STAGE_ATTEMPTS)
        worlds = {attempt.variation_digest for attempt in report.attempts}
        self.assertEqual(len(worlds), MINIMUM_STAGE_ATTEMPTS)

    def test_every_attempt_ran_in_a_declared_world(self) -> None:
        harness = Harness()
        harness.seed_prior_stage()
        robot = RegimeAwareRobot()

        harness.campaign().run(
            campaign_id="regime-campaign",
            selection=harness.selection,
            environment=RegimeEnvironment(
                robot=robot,
                runtime_factory=ScriptedRuntime,
                configuration=harness.configuration(),
            ),
            schedule=self._schedule(harness),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )

        for _, sample in robot.resets:
            self.assertIsNotNone(sample)
            self.assertIn(AXIS_FRICTION_SCALE, sample.values)

    def test_an_abort_still_halts_under_a_regime(self) -> None:
        """No existing refusal is weakened by varying the world."""
        harness = Harness()
        harness.seed_prior_stage()

        def factory() -> ScriptedRuntime:
            return ScriptedRuntime(estop_at_step=1)

        report = harness.campaign().run(
            campaign_id="regime-abort",
            selection=harness.selection,
            environment=RegimeEnvironment(
                robot=RegimeAwareRobot(),
                runtime_factory=factory,
                configuration=harness.configuration(),
            ),
            schedule=self._schedule(harness),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )

        self.assertEqual(report.halted, HALTED_ABORTED)
        self.assertEqual(len(report.attempts), 1)
        self.assertEqual(report.attempts[0].outcome, OUTCOME_ABORTED)
        self.assertFalse(report.next_stage_admitted)

    def test_a_misrepresenting_environment_is_still_refused(self) -> None:
        harness = Harness()
        harness.seed_prior_stage()

        with self.assertRaises(ValueError):
            harness.campaign().run(
                campaign_id="regime-fidelity",
                selection=harness.selection,
                environment=RegimeEnvironment(
                    robot=RegimeAwareRobot(),
                    runtime_factory=ScriptedRuntime,
                    configuration=harness.configuration(
                        control_frequency_hz=5.0
                    ),
                ),
                schedule=self._schedule(harness),
                planned_attempts=MINIMUM_STAGE_ATTEMPTS,
            )

    def test_a_regime_campaign_is_reproducible(self) -> None:
        def run_once() -> tuple[str, ...]:
            harness = Harness()
            harness.seed_prior_stage()
            report = harness.campaign().run(
                campaign_id="regime-repeat",
                selection=harness.selection,
                environment=RegimeEnvironment(
                    robot=RegimeAwareRobot(),
                    runtime_factory=ScriptedRuntime,
                    configuration=harness.configuration(),
                ),
                schedule=self._schedule(harness, seed=7),
                planned_attempts=MINIMUM_STAGE_ATTEMPTS,
            )
            return tuple(
                attempt.variation_digest for attempt in report.attempts
            )

        self.assertEqual(run_once(), run_once())

    def test_the_variation_schedule_still_drives_a_campaign_unchanged(
        self,
    ) -> None:
        """The old schedule keeps working; the regime is an addition."""
        harness = Harness()
        harness.seed_prior_stage()

        report = harness.campaign().run(
            campaign_id="plain-campaign",
            selection=harness.selection,
            environment=harness.environment(),
            schedule=VariationSchedule(joint_count=7),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )

        self.assertEqual(report.halted, HALTED_COMPLETED)
        for attempt in report.attempts:
            self.assertEqual(attempt.outcome, OUTCOME_SUCCEEDED)


class AttemptRecordCarriesItsWorldTest(unittest.TestCase):
    """The campaign must hand the objective the world each attempt ran in.

    This is the seam where the anti-overfitting mechanism either works or is
    silently inert. ``RobustnessObjective`` buckets attempts by the regime
    values behind them and penalises a candidate whose worst bucket trails its
    mean. If an attempt record does not carry its sample, every attempt falls
    into one nominal bucket, the worst bucket equals the mean, the sensitivity
    is identically zero, and a candidate that is excellent in the easy corner
    and useless in the hard one scores exactly like one that is uniformly
    mediocre. The failure is invisible from the outside: the scores stay in
    range, the search still ranks, and it ranks by the wrong thing.
    """

    def test_a_regime_campaign_records_the_sample_behind_each_attempt(
        self,
    ) -> None:
        harness = Harness()
        harness.seed_prior_stage()

        report = harness.campaign().run(
            campaign_id="regime-sample-record",
            selection=harness.selection,
            environment=RegimeEnvironment(
                robot=RegimeAwareRobot(),
                runtime_factory=ScriptedRuntime,
                configuration=harness.configuration(),
            ),
            schedule=RegimeSchedule(
                regime=_offset_regime(samples=MINIMUM_STAGE_ATTEMPTS),
                joint_count=harness.embodiment.arm_dof,
            ),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )

        self.assertEqual(report.halted, HALTED_COMPLETED)
        for attempt in report.attempts:
            self.assertIsNotNone(
                attempt.sample,
                "an attempt that does not name its world cannot be bucketed, "
                "so the sensitivity penalty would silently never fire",
            )
            self.assertIn(AXIS_FRICTION_SCALE, attempt.sample.values)
            self.assertEqual(attempt.sample.index, attempt.index)

    def test_a_nominal_campaign_records_no_sample(self) -> None:
        """A plain schedule varies only the pose, and must not imply a regime."""
        harness = Harness()
        harness.seed_prior_stage()

        report = harness.campaign().run(
            campaign_id="nominal-sample-record",
            selection=harness.selection,
            environment=harness.environment(),
            schedule=VariationSchedule(
                joint_count=harness.embodiment.arm_dof
            ),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )

        self.assertEqual(report.halted, HALTED_COMPLETED)
        for attempt in report.attempts:
            self.assertIsNone(attempt.sample)

    def test_the_recorded_samples_let_the_objective_split_the_evidence(
        self,
    ) -> None:
        """End to end: a real campaign's report must bucket into the regime.

        Asserted against the real ``RobustnessObjective`` rather than by
        re-deriving buckets here, because the property that matters is that
        these two modules agree at their seam.
        """
        from vegapunk.embodied.objective import (
            NOMINAL_BUCKET,
            RobustnessObjective,
        )

        harness = Harness()
        harness.seed_prior_stage()

        report = harness.campaign().run(
            campaign_id="regime-objective-seam",
            selection=harness.selection,
            environment=RegimeEnvironment(
                robot=RegimeAwareRobot(),
                runtime_factory=ScriptedRuntime,
                configuration=harness.configuration(),
            ),
            schedule=RegimeSchedule(
                regime=_offset_regime(samples=MINIMUM_STAGE_ATTEMPTS),
                joint_count=harness.embodiment.arm_dof,
            ),
            planned_attempts=MINIMUM_STAGE_ATTEMPTS,
        )

        score = RobustnessObjective(minimum_attempts=2).score(
            "candidate-under-test", (report,)
        )

        self.assertEqual(score.attempts, MINIMUM_STAGE_ATTEMPTS)
        self.assertIsNotNone(score.worst_bucket)
        self.assertNotEqual(
            score.worst_bucket.label,
            NOMINAL_BUCKET,
            "the objective fell back to one nominal bucket, which means the "
            "campaign's samples never reached it",
        )
        self.assertLess(
            score.worst_bucket.attempts,
            MINIMUM_STAGE_ATTEMPTS,
            "a worst bucket holding every attempt is not a bucket",
        )


if __name__ == "__main__":
    unittest.main()
