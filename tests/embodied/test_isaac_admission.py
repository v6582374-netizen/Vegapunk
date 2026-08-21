from __future__ import annotations

import unittest
from datetime import datetime, timezone

from vegapunk.embodied.episode import (
    TimeSynchronization,
    TrainingEpisode,
    freeze_qualified_replay,
)
from vegapunk.embodied.isaac import (
    GOLDEN_ISAAC_SCENE,
    ISAAC_LAB_SOURCE,
    ISAAC_LAB_VERSION,
    IsaacEvidenceLedger,
    IsaacLabAdapter,
    IsaacLabEvidence,
    admit_qualified_replay,
)
from vegapunk.embodied.promotion import (
    GOLDEN_EMBODIMENT,
    GOLDEN_INSTRUMENT_OPERATION_LOOP,
    GOLDEN_PROMOTION_CONFIGURATION,
    GOLDEN_SKILL_ID,
    PROMOTION_GATE_ORDER,
    CampaignPlan,
    CandidateBundle,
    GoldenSkillRevision,
    PromotionLedger,
    PromotionSubmission,
    promote_generation,
)
from vegapunk.embodied.skill import SKILL_KIND_DETERMINISTIC, PhysicalSkill
from vegapunk.operation.episode import (
    TERMINATION_COMPLETED,
    TRANSFER_FULL,
    CameraCalibration,
    EpisodeOutcome,
    EpisodeRecord,
    Frame,
    ResetRecord,
)
from vegapunk.operation.target import HAND_OPEN, STAND_BODY, WholeBodyTarget
from vegapunk.operation.tracker import TrackerState
from vegapunk.operation.witness import LID_CLOSED

AT = datetime(2026, 8, 21, 14, 0, tzinfo=timezone.utc)
NOW = 2_000_000_000


def _skill() -> GoldenSkillRevision:
    return GoldenSkillRevision(
        skill=PhysicalSkill(
            skill_id=GOLDEN_SKILL_ID,
            revision=1,
            kind=SKILL_KIND_DETERMINISTIC,
            summary="Open, transfer, and restore the instrument.",
            parameters=(),
            preconditions=("instrument_closed",),
            postconditions=("instrument_closed", "transfer_complete"),
            abort_conditions=("safety_stop",),
            max_duration_s=90.0,
            reviewed_by="skill_owner",
        ),
        operation_loop=GOLDEN_INSTRUMENT_OPERATION_LOOP,
    )


def _replay():
    target = WholeBodyTarget(
        sequence=1,
        source_time_ns=NOW,
        valid_until_ns=NOW + 100_000_000,
        body=STAND_BODY,
        left_hand=HAND_OPEN,
        right_hand=HAND_OPEN,
    )
    frame = Frame(
        index=0,
        time_ns=NOW,
        images={"head": "head/00000.jpg"},
        state=TrackerState(
            sequence=1,
            state_time_ns=NOW,
            body=(0.0,) * 34,
            left_hand=HAND_OPEN,
            right_hand=HAND_OPEN,
            applied_target_sequence=target.sequence,
        ),
        target=target,
        lid=LID_CLOSED,
        monitor_decision="pass",
    )
    record = EpisodeRecord(
        episode_id="episode-isaac-001",
        configuration_digest=GOLDEN_PROMOTION_CONFIGURATION.digest(),
        started_at=AT,
        cameras=(
            CameraCalibration(
                identity="head", width=640, height=480, fps=30.0, mounted_on="torso"
            ),
        ),
        witness_identity="lid-limit-switch",
        reset=ResetRecord(
            performed_by="operator",
            performed_at=AT,
            lid_closed=True,
            vessel_restored=True,
            floor_and_tether_restored=True,
        ),
        frame_count=1,
        outcome=EpisodeOutcome(
            transfer=TRANSFER_FULL,
            judged_by="judge",
            judged_at=AT,
            lid_closed_at_end=True,
            termination=TERMINATION_COMPLETED,
        ),
        operator="campaign_operator",
    )
    episode = TrainingEpisode(
        record=record,
        skill=_skill(),
        embodiment=GOLDEN_EMBODIMENT,
        configuration=GOLDEN_PROMOTION_CONFIGURATION,
        synchronization=TimeSynchronization(
            synchronization_id="ptp-isaac",
            synchronized_at=AT,
            observation_clock="camera-ptp",
            target_clock="target-bridge-monotonic",
            witness_clock="lid-switch-monotonic",
            max_skew_ns=2_000_000,
        ),
        frames=(frame,),
    )
    return freeze_qualified_replay(episode)


def _submission() -> PromotionSubmission:
    skill = _skill()
    candidate = CandidateBundle(
        candidate_id="candidate-isaac-001",
        policy_artifact_digest="policy-artifact-001",
        data_manifest_digest="training-manifest-001",
        training_recipe_digest="recipe-001",
        observation_schema_digest=GOLDEN_PROMOTION_CONFIGURATION.observation_schema_digest,
        action_schema_digest=GOLDEN_PROMOTION_CONFIGURATION.action_protocol_digest,
        skill_revision_id=skill.version_id,
        skill_revision_digest=skill.digest(),
        embodiment_digest=GOLDEN_EMBODIMENT.digest(),
        configuration_digest=GOLDEN_PROMOTION_CONFIGURATION.digest(),
    )
    return PromotionSubmission(
        skill=skill,
        candidate=candidate,
        embodiment=GOLDEN_EMBODIMENT,
        configuration=GOLDEN_PROMOTION_CONFIGURATION,
        plan=CampaignPlan(
            campaign_id="isaac-gate-001",
            skill_revision_id=skill.version_id,
            candidate_digest=candidate.digest(),
            embodiment_digest=GOLDEN_EMBODIMENT.digest(),
            configuration_digest=GOLDEN_PROMOTION_CONFIGURATION.digest(),
            ordered_gates=PROMOTION_GATE_ORDER,
            hardware_attempts=1,
            prepared_by="campaign_owner",
        ),
    )


class IsaacAdmissionAcceptanceTest(unittest.TestCase):
    def test_the_minimal_scene_declares_every_task_relevant_fact(self) -> None:
        scene = GOLDEN_ISAAC_SCENE

        self.assertEqual(scene.robot_model, "unitree_g1")
        self.assertEqual(scene.end_effector, "dex3")
        self.assertEqual(scene.policy_camera_key, "observation.images.top")
        self.assertEqual(scene.task_objects, ("instrument", "cup", "receiving_vessel"))
        self.assertIn(("dex3", "cup"), scene.required_contacts)
        self.assertIn(("cup", "instrument"), scene.required_contacts)
        self.assertTrue(scene.independent_witness_visible)

    def test_a_fixed_seed_and_scene_reproduce_the_same_simulator_verdict(self) -> None:
        replay = _replay()
        adapter = IsaacLabAdapter(GOLDEN_ISAAC_SCENE)

        first = adapter.run(replay, seed=17)
        second = adapter.run(replay, seed=17)

        self.assertEqual(first, second)
        self.assertEqual(first.source, ISAAC_LAB_SOURCE)
        self.assertEqual(first.simulator_version, ISAAC_LAB_VERSION)
        self.assertEqual(first.target_sequences, (1,))
        self.assertTrue(first.succeeded)

    def test_simulator_evidence_is_scoped_and_cannot_be_relabelled_as_real(self) -> None:
        replay = _replay()
        candidate = _submission().candidate
        assert candidate is not None

        evidence = admit_qualified_replay(
            replay,
            candidate=candidate,
            adapter=IsaacLabAdapter(GOLDEN_ISAAC_SCENE),
            seed=17,
            ledger=IsaacEvidenceLedger(),
            now=AT,
        )

        self.assertEqual(evidence.source, ISAAC_LAB_SOURCE)
        self.assertEqual(evidence.simulator_version, ISAAC_LAB_VERSION)
        self.assertEqual(evidence.scene_digest, GOLDEN_ISAAC_SCENE.digest())
        self.assertEqual(evidence.candidate_digest, candidate.digest())
        with self.assertRaisesRegex(ValueError, "simulator-scoped"):
            IsaacLabEvidence(
                source="real",
                simulator_version=ISAAC_LAB_VERSION,
                scene_digest=GOLDEN_ISAAC_SCENE.digest(),
                candidate_digest=candidate.digest(),
                replay_digest=replay.digest(),
                seed=17,
                verdict="succeeded",
                recorded_at=AT,
            )

    def test_generation_promotion_reaches_the_isaac_gate_and_seals_its_verdict(self) -> None:
        submission = _submission()
        replay = _replay()
        isaac_ledger = IsaacEvidenceLedger()

        def execute(accepted: PromotionSubmission) -> IsaacLabEvidence:
            assert accepted.candidate is not None
            return admit_qualified_replay(
                replay,
                candidate=accepted.candidate,
                adapter=IsaacLabAdapter(GOLDEN_ISAAC_SCENE),
                seed=17,
                ledger=isaac_ledger,
                now=AT,
            )

        evidence = promote_generation(
            submission,
            ledger=PromotionLedger(),
            execute=execute,
            now=AT,
        )

        self.assertIsInstance(evidence, IsaacLabEvidence)
        assert isinstance(evidence, IsaacLabEvidence)
        self.assertTrue(evidence.succeeded)
        self.assertEqual(isaac_ledger.evidence_for(evidence.digest()), evidence)

