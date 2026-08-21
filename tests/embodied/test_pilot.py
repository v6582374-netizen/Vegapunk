from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from vegapunk.embodied.episode import Intervention
from vegapunk.embodied.hardware import MotionAuthority
from vegapunk.embodied.pilot import (
    PILOT_ABORTED,
    PILOT_INDETERMINATE,
    PILOT_INTERVENED,
    PILOT_SOURCE_TEST_DOUBLE,
    PILOT_SUCCEEDED,
    HardwarePilotApproval,
    PilotEpisode,
    PilotRunProvenance,
    SupervisedPilotBatch,
)
from vegapunk.embodied.promotion import (
    GOLDEN_EMBODIMENT,
    GOLDEN_INSTRUMENT_OPERATION_LOOP,
    GOLDEN_PROMOTION_CONFIGURATION,
    GOLDEN_SKILL_ID,
    CampaignPlan,
    CandidateBundle,
    GoldenSkillRevision,
    PromotionSubmission,
)
from vegapunk.embodied.skill import SKILL_KIND_DETERMINISTIC, PhysicalSkill
from vegapunk.operation.bridge import TargetBridge
from vegapunk.operation.episode import (
    TERMINATION_COMPLETED,
    TERMINATION_HELD,
    TERMINATION_OPERATOR_STOP,
    TRANSFER_FULL,
    TRANSFER_NONE,
    CameraCalibration,
    EpisodeOutcome,
    EpisodeRecord,
    EpisodeWriter,
    ResetRecord,
)
from vegapunk.operation.monitor import InstrumentMonitor
from vegapunk.operation.policy import ActionChunk, Observation, PolicyServer
from vegapunk.operation.session import OperationSession
from vegapunk.operation.target import HAND_OPEN, STAND_BODY, WholeBodyTarget
from vegapunk.operation.tracker import TrackerState
from vegapunk.operation.witness import IndependentWitness, SwitchWitness

NOW_NS = 2_000_000_000
AT = datetime(2026, 8, 21, 17, 0, tzinfo=timezone.utc)


class _Transport:
    def __init__(self) -> None:
        self.committed: list[WholeBodyTarget] = []

    def commit(self, target: WholeBodyTarget) -> None:
        self.committed.append(target)

    def read_state(self):  # type: ignore[no-untyped-def]
        return None


class _SingleFramePolicy:
    def __init__(self, target: WholeBodyTarget) -> None:
        self._target = target

    def act(self, observation, intent, first_tick):  # type: ignore[no-untyped-def]
        return ActionChunk(first_tick=first_tick, frames=(self._target,))


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


def _submission() -> PromotionSubmission:
    skill = _skill()
    candidate = CandidateBundle(
        candidate_id="candidate-pilot-001",
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
            campaign_id="pilot-campaign-001",
            skill_revision_id=skill.version_id,
            candidate_digest=candidate.digest(),
            embodiment_digest=GOLDEN_EMBODIMENT.digest(),
            configuration_digest=GOLDEN_PROMOTION_CONFIGURATION.digest(),
            ordered_gates=(),
            hardware_attempts=1,
            prepared_by="campaign_owner",
        ),
    )


def _approval(submission: PromotionSubmission) -> HardwarePilotApproval:
    candidate = submission.candidate
    skill = submission.skill
    assert candidate is not None and skill is not None
    return HardwarePilotApproval(
        candidate_digest=candidate.digest(),
        skill_revision_digest=skill.digest(),
        embodiment_digest=GOLDEN_EMBODIMENT.digest(),
        configuration_digest=GOLDEN_PROMOTION_CONFIGURATION.digest(),
        campaign_digest="campaign-digest-001",
        approved_by="safety_operator",
        approved_at=AT,
        statement="supervised pilot with physical stop present",
    )


def _manual_authority(submission: PromotionSubmission) -> MotionAuthority:
    skill = submission.skill
    assert skill is not None
    return MotionAuthority(
        authorized_by="safety_operator",
        statement="physical stop is present and reachable",
        granted_at=AT,
        skill_version_id=skill.version_id,
        embodiment_digest=GOLDEN_EMBODIMENT.digest(),
    )


def _observation() -> Observation:
    return Observation(
        time_ns=NOW_NS,
        images={"head": "head/0.jpg"},
        state=TrackerState(
            sequence=0,
            state_time_ns=NOW_NS,
            body=(0.0,) * 34,
            left_hand=HAND_OPEN,
            right_hand=HAND_OPEN,
        ),
    )


def _outcome(disposition: str) -> EpisodeOutcome:
    if disposition == PILOT_INTERVENED:
        termination = TERMINATION_OPERATOR_STOP
    elif disposition in {PILOT_ABORTED, PILOT_INDETERMINATE}:
        termination = TERMINATION_HELD
    else:
        termination = TERMINATION_COMPLETED
    return EpisodeOutcome(
        transfer=TRANSFER_FULL if disposition == PILOT_SUCCEEDED else TRANSFER_NONE,
        judged_by="outcome_reviewer",
        judged_at=AT,
        lid_closed_at_end=True,
        termination=termination,
        detail=disposition,
    )


def _episode(
    root: Path,
    episode_id: str,
    *,
    witness_value: bool | None = True,
    stale: bool = False,
    intervention: Intervention | None = None,
) -> tuple[PilotEpisode, _Transport]:
    transport = _Transport()
    configuration = GOLDEN_PROMOTION_CONFIGURATION.digest()
    bridge = TargetBridge(transport, configuration, clock_ns=lambda: NOW_NS)
    witness = IndependentWitness(
        SwitchWitness(lambda: witness_value, clock_ns=lambda: NOW_NS),
        clock_ns=lambda: NOW_NS,
        dwell_s=0.0,
    )
    body = list(STAND_BODY)
    body[0] = 0.2
    target = WholeBodyTarget(
        sequence=0,
        source_time_ns=NOW_NS - 1 if stale else NOW_NS,
        valid_until_ns=NOW_NS if stale else NOW_NS + 60_000_000,
        body=tuple(body),
        left_hand=HAND_OPEN,
        right_hand=HAND_OPEN,
    )
    record = EpisodeRecord(
        episode_id=episode_id,
        configuration_digest=configuration,
        started_at=AT,
        cameras=(CameraCalibration("head", 640, 480, 30.0, "head"),),
        witness_identity=witness.identity,
        reset=ResetRecord(
            performed_by="reset_operator",
            performed_at=AT,
            lid_closed=True,
            vessel_restored=True,
            floor_and_tether_restored=True,
        ),
        operator="campaign_operator",
    )
    session = OperationSession(
        policy=PolicyServer(_SingleFramePolicy(target)),
        monitor=InstrumentMonitor(witness),
        bridge=bridge,
        writer=EpisodeWriter(root, record),
        clock_ns=lambda: NOW_NS,
    )
    return (
        PilotEpisode(
            episode_id=episode_id,
            session=session,
            observations=(_observation(),),
            judge=_outcome,
            intervention=intervention,
        ),
        transport,
    )


class SupervisedPilotBatchAcceptanceTest(unittest.TestCase):
    def _pilot(self, submission: PromotionSubmission) -> SupervisedPilotBatch:
        return SupervisedPilotBatch(
            submission=submission,
            batch_id="pilot-batch-001",
            campaign_digest="campaign-digest-001",
            approval=_approval(submission),
            manual_safety_authority=_manual_authority(submission),
            provenance=PilotRunProvenance(PILOT_SOURCE_TEST_DOUBLE),
            clock=lambda: AT,
        )

    def test_exact_approval_reaches_the_robot_only_through_target_bridge(self) -> None:
        submission = _submission()
        with tempfile.TemporaryDirectory() as directory:
            episode, transport = _episode(Path(directory), "pilot-001")
            evidence = self._pilot(submission).run((episode,))

        self.assertEqual(evidence.dispositions, (PILOT_SUCCEEDED,))
        self.assertEqual(len(transport.committed), 1)
        self.assertFalse(transport.committed[0].is_stationary())
        self.assertEqual(evidence.source.source, PILOT_SOURCE_TEST_DOUBLE)
        assert evidence.episodes[0].record.outcome is not None
        self.assertEqual(evidence.episodes[0].record.outcome.transfer, TRANSFER_FULL)

    def test_unusable_witness_and_stale_target_are_retained_as_safe_stops(self) -> None:
        submission = _submission()
        with tempfile.TemporaryDirectory() as directory:
            witness_failure, witness_transport = _episode(
                Path(directory), "pilot-witness", witness_value=None
            )
            evidence = self._pilot(submission).run((witness_failure,))
            self.assertEqual(evidence.dispositions, (PILOT_INDETERMINATE,))
            self.assertTrue(witness_transport.committed[-1].is_stationary())

        with tempfile.TemporaryDirectory() as directory:
            stale, stale_transport = _episode(
                Path(directory), "pilot-stale", stale=True
            )
            evidence = self._pilot(submission).run((stale,))
            self.assertEqual(evidence.dispositions, (PILOT_ABORTED,))
            self.assertTrue(stale_transport.committed[-1].is_stationary())

    def test_intervention_ends_the_batch_and_requires_a_new_episode_identity(
        self,
    ) -> None:
        submission = _submission()
        intervention = Intervention(NOW_NS, "safety_operator", "hand near fixture")
        with tempfile.TemporaryDirectory() as directory:
            interrupted, transport = _episode(
                Path(directory), "pilot-intervened", intervention=intervention
            )
            later, _ = _episode(Path(directory), "pilot-recovery")
            evidence = self._pilot(submission).run((interrupted, later))

            self.assertEqual(evidence.dispositions, (PILOT_INTERVENED,))
            self.assertEqual(evidence.episodes[0].intervention, intervention)
            self.assertTrue(transport.committed[-1].is_stationary())
            with self.assertRaisesRegex(ValueError, "new episode identity"):
                self._pilot(submission).run((later, later))

    def test_approval_for_another_candidate_is_refused_before_motion(self) -> None:
        submission = _submission()
        wrong = HardwarePilotApproval(
            **{**_approval(submission).__dict__, "candidate_digest": "other"}
        )
        with self.assertRaisesRegex(ValueError, "does not cover"):
            SupervisedPilotBatch(
                submission=submission,
                batch_id="pilot-batch-001",
                campaign_digest="campaign-digest-001",
                approval=wrong,
                manual_safety_authority=_manual_authority(submission),
                provenance=PilotRunProvenance(PILOT_SOURCE_TEST_DOUBLE),
                clock=lambda: AT,
            )


if __name__ == "__main__":
    unittest.main()
