from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.embodied.test_generation_successor import _act_candidate, _skill
from tests.embodied.test_pilot import _episode, _manual_authority
from vegapunk.embodied.act_candidate import EndToEndACTCandidate
from vegapunk.embodied.act_generation import (
    ACT_GENERATION_GATE_ORDER,
    GATE_CONTRACT_VALIDATION,
    GATE_HARDWARE_APPROVAL,
    ACTGenerationPromotion,
    PromotionFailure,
    _execute_act_generation,
)
from vegapunk.embodied.generation_result import (
    CHANGE_TRAINING,
    FAILURE_POLICY_CAPACITY,
    SOURCE_ISAAC_LAB,
    SOURCE_MUJOCO,
    SOURCE_OBSERVATION_SHADOW,
    SOURCE_QUALIFIED_REPLAY,
    BoundedChange,
    BoundedWorkOrder,
    GateEvidenceReference,
    GenerationResultLedger,
    SealedGenerationResult,
)
from vegapunk.embodied.pilot import (
    PILOT_SOURCE_OPERATIONAL,
    PILOT_SOURCE_TEST_DOUBLE,
    HardwarePilotApproval,
    OperationalRunRegistration,
    PilotBatchEvidence,
    PilotRunProvenance,
    SupervisedPilotBatch,
)
from vegapunk.embodied.promotion import (
    GOLDEN_EMBODIMENT,
    GOLDEN_PROMOTION_CONFIGURATION,
    PROMOTION_GATE_ORDER,
    CampaignPlan,
    PromotionLedger,
    PromotionSubmission,
    SealedRejection,
    promote_generation,
)

AT = datetime(2026, 8, 21, 21, 0, tzinfo=timezone.utc)


def _submission(candidate: EndToEndACTCandidate) -> PromotionSubmission:
    bundle = candidate.bundle
    skill = _skill()
    plan = CampaignPlan(
        campaign_id="generation-act-pilot",
        skill_revision_id=skill.version_id,
        candidate_digest=bundle.digest(),
        embodiment_digest=bundle.embodiment_digest,
        configuration_digest=bundle.configuration_digest,
        ordered_gates=PROMOTION_GATE_ORDER,
        hardware_attempts=1,
        prepared_by="campaign_owner",
    )
    return PromotionSubmission(
        skill=skill,
        candidate=bundle,
        embodiment=GOLDEN_EMBODIMENT,
        configuration=GOLDEN_PROMOTION_CONFIGURATION,
        plan=plan,
    )


def _work_order(result: SealedGenerationResult) -> BoundedWorkOrder:
    return BoundedWorkOrder(
        order_id="order-next-001",
        result_digest=result.digest(),
        failure_class=FAILURE_POLICY_CAPACITY,
        change=BoundedChange(
            CHANGE_TRAINING, "ACT context window", "increase context", "at most 32"
        ),
        evidence_basis=(result.gate_evidence[-2], result.gate_evidence[-1]),
        unchanged_controls=("skill_revision", "action_protocol", "safety_envelope"),
        next_required_gate="offline_replay",
        proposed_at=AT + timedelta(seconds=1),
    )


def _promote(
    *,
    generation_id: str,
    candidate: EndToEndACTCandidate,
    submission: PromotionSubmission,
    gates: _Gates,
    result_ledger: GenerationResultLedger,
) -> ACTGenerationPromotion | PromotionFailure | SealedRejection:
    return promote_generation(
        submission,
        ledger=PromotionLedger(),
        execute=lambda accepted: _execute_act_generation(
            accepted,
            generation_id=generation_id,
            candidate=candidate,
            gates=gates,
            result_ledger=result_ledger,
            work_order_from=_work_order,
            now=AT,
        ),
        now=AT,
    )


class _Gates:
    def __init__(
        self,
        submission: PromotionSubmission,
        *,
        fail_at: str | None = None,
        pilot_source: str = PILOT_SOURCE_OPERATIONAL,
        corrupt_registration: bool = False,
    ) -> None:
        candidate = submission.candidate
        assert candidate is not None
        self.submission = submission
        self.candidate_digest = candidate.digest()
        self.fail_at = fail_at
        self.pilot_source = pilot_source
        self.corrupt_registration = corrupt_registration
        self.ran: list[str] = []
        self._approval: HardwarePilotApproval | None = None

    def offline_replay(self) -> GateEvidenceReference:
        return self._evidence("offline_replay", SOURCE_QUALIFIED_REPLAY, "replay")

    def isaac_lab(self) -> GateEvidenceReference:
        return self._evidence("isaac_lab", SOURCE_ISAAC_LAB, "isaac")

    def mujoco(self) -> GateEvidenceReference:
        return self._evidence("mujoco", SOURCE_MUJOCO, "mujoco")

    def observation_shadow(self) -> GateEvidenceReference:
        return self._evidence("observation_shadow", SOURCE_OBSERVATION_SHADOW, "shadow")

    def hardware_approval(self) -> HardwarePilotApproval:
        self.ran.append(GATE_HARDWARE_APPROVAL)
        candidate = self.submission.candidate
        skill = self.submission.skill
        configuration = self.submission.configuration
        embodiment = self.submission.embodiment
        plan = self.submission.plan
        assert candidate and skill and configuration and embodiment and plan
        candidate_digest = (
            "another-candidate"
            if self.fail_at == GATE_HARDWARE_APPROVAL
            else candidate.digest()
        )
        self._approval = HardwarePilotApproval(
            candidate_digest=candidate_digest,
            skill_revision_digest=skill.digest(),
            embodiment_digest=embodiment.digest(),
            configuration_digest=configuration.digest(),
            campaign_digest=plan.digest(),
            approved_by="safety_operator",
            approved_at=AT,
            statement="supervised operational pilot",
        )
        return self._approval

    def hardware_pilot(self) -> tuple[PilotBatchEvidence, OperationalRunRegistration]:
        self.ran.append("hardware_pilot")
        approval = self._approval
        plan = self.submission.plan
        assert approval is not None and plan is not None
        registration = OperationalRunRegistration(
            operational_run_id="run-act-001",
            batch_id="batch-act-001",
            campaign_digest=plan.digest(),
            approval_digest=approval.digest(),
            registered_by="operations_owner",
            registered_at=AT,
        )
        provenance = (
            PilotRunProvenance(PILOT_SOURCE_TEST_DOUBLE)
            if self.pilot_source == PILOT_SOURCE_TEST_DOUBLE
            else PilotRunProvenance(
                PILOT_SOURCE_OPERATIONAL,
                registration.operational_run_id,
                registration.digest(),
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            episode, _ = _episode(Path(directory), "real-anchor-001")
            evidence = SupervisedPilotBatch(
                submission=self.submission,
                batch_id=registration.batch_id,
                campaign_digest=registration.campaign_digest,
                approval=approval,
                manual_safety_authority=_manual_authority(self.submission),
                provenance=provenance,
                clock=lambda: AT,
                operational_registration=(
                    registration
                    if provenance.source == PILOT_SOURCE_OPERATIONAL
                    else None
                ),
            ).run((episode,))
        if self.corrupt_registration:
            registration = replace(registration, registered_by="another_operator")
        return evidence, registration

    def _evidence(self, gate: str, source: str, digest: str) -> GateEvidenceReference:
        self.ran.append(gate)
        return GateEvidenceReference(
            gate,
            source,
            digest,
            self.candidate_digest,
            refusals=("failed",) if self.fail_at == gate else (),
        )


class ACTGenerationPromotionAcceptanceTest(unittest.TestCase):
    def _candidate_and_submission(
        self, candidate_id: str
    ) -> tuple[EndToEndACTCandidate, PromotionSubmission]:
        skill = _skill()
        candidate = _act_candidate(candidate_id, skill=skill)
        return candidate, _submission(candidate)

    def test_act_candidate_closes_the_full_evidence_ladder_with_registered_real_pilot(self) -> None:
        candidate, submission = self._candidate_and_submission("act-promotion-001")
        gates = _Gates(submission)
        result_ledger = GenerationResultLedger()

        promotion = _promote(
            generation_id="generation-act-001",
            candidate=candidate,
            submission=submission,
            gates=gates,
            result_ledger=result_ledger,
        )

        self.assertNotIsInstance(promotion, (PromotionFailure, SealedRejection))
        assert not isinstance(promotion, (PromotionFailure, SealedRejection))
        self.assertEqual(promotion.executed_gates, ACT_GENERATION_GATE_ORDER)
        self.assertEqual(promotion.real_anchor_episode_ids, ("real-anchor-001",))
        self.assertEqual(promotion.real_anchor.generation_id, "generation-act-001")
        self.assertEqual(promotion.real_anchor.batch_id, "batch-act-001")
        assert submission.plan is not None
        self.assertEqual(promotion.real_anchor.campaign_digest, submission.plan.digest())
        self.assertEqual(promotion.real_anchor.candidate_digest, candidate.bundle.digest())
        self.assertEqual(promotion.real_anchor.operational_run_id, "run-act-001")
        sealed = result_ledger.result_for(promotion.result.digest())
        self.assertIs(sealed, promotion.result)
        assert sealed is not None
        self.assertEqual(sealed.real_anchor, promotion.real_anchor)
        self.assertIs(result_ledger.work_order_for(promotion.work_order.order_id), promotion.work_order)
        self.assertFalse(hasattr(promotion, "hardware_authority"))

    def test_a_test_double_cannot_become_a_real_generation_success(self) -> None:
        candidate, submission = self._candidate_and_submission("act-promotion-002")
        gates = _Gates(submission, pilot_source=PILOT_SOURCE_TEST_DOUBLE)

        failure = _promote(
            generation_id="generation-act-002",
            candidate=candidate,
            submission=submission,
            gates=gates,
            result_ledger=GenerationResultLedger(),
        )

        self.assertIsInstance(failure, PromotionFailure)
        assert isinstance(failure, PromotionFailure)
        self.assertEqual(failure.failed_gate, "hardware_pilot")

    def test_an_approval_for_another_candidate_stops_before_pilot_execution(self) -> None:
        candidate, submission = self._candidate_and_submission("act-promotion-approval")
        gates = _Gates(submission, fail_at=GATE_HARDWARE_APPROVAL)

        failure = _promote(
            generation_id="generation-act-approval",
            candidate=candidate,
            submission=submission,
            gates=gates,
            result_ledger=GenerationResultLedger(),
        )

        self.assertIsInstance(failure, PromotionFailure)
        assert isinstance(failure, PromotionFailure)
        self.assertEqual(failure.failed_gate, GATE_HARDWARE_APPROVAL)
        self.assertNotIn("hardware_pilot", gates.ran)

    def test_a_registration_mismatch_cannot_anchor_a_generation(self) -> None:
        candidate, submission = self._candidate_and_submission("act-promotion-registration")
        gates = _Gates(submission, corrupt_registration=True)

        failure = _promote(
            generation_id="generation-act-registration",
            candidate=candidate,
            submission=submission,
            gates=gates,
            result_ledger=GenerationResultLedger(),
        )

        self.assertIsInstance(failure, PromotionFailure)
        assert isinstance(failure, PromotionFailure)
        self.assertEqual(failure.failed_gate, "hardware_pilot")


    def test_contract_rejection_is_sealed_by_the_shared_promotion_gate(self) -> None:
        candidate, submission = self._candidate_and_submission("act-promotion-003")
        gates = _Gates(submission)
        rejected_submission = replace(submission, configuration=None)

        rejection = _promote(
            generation_id="generation-act-003",
            candidate=candidate,
            submission=rejected_submission,
            gates=gates,
            result_ledger=GenerationResultLedger(),
        )

        self.assertIsInstance(rejection, SealedRejection)
        assert isinstance(rejection, SealedRejection)
        self.assertEqual(rejection.failed_gate, GATE_CONTRACT_VALIDATION)
        self.assertEqual(gates.ran, [])

    def test_a_failed_gate_stops_later_gates_and_never_seals_real_success(self) -> None:
        candidate, submission = self._candidate_and_submission("act-promotion-004")
        gates = _Gates(submission, fail_at="isaac_lab")

        failure = _promote(
            generation_id="generation-act-004",
            candidate=candidate,
            submission=submission,
            gates=gates,
            result_ledger=GenerationResultLedger(),
        )

        self.assertIsInstance(failure, PromotionFailure)
        assert isinstance(failure, PromotionFailure)
        self.assertEqual(failure.failed_gate, "isaac_lab")
        self.assertEqual(gates.ran, ["offline_replay", "isaac_lab"])


if __name__ == "__main__":
    unittest.main()
