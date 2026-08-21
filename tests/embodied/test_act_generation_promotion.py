from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from tests.embodied.test_generation_successor import _act_candidate
from vegapunk.embodied.act_generation import (
    ACT_GENERATION_GATE_ORDER,
    GATE_CONTRACT_VALIDATION,
    GATE_HARDWARE_APPROVAL,
    ACTGenerationPromoter,
    PromotionFailure,
)
from vegapunk.embodied.generation_result import (
    CHANGE_TRAINING,
    FAILURE_POLICY_CAPACITY,
    SOURCE_HARDWARE_PILOT,
    SOURCE_ISAAC_LAB,
    SOURCE_MUJOCO,
    SOURCE_OBSERVATION_SHADOW,
    SOURCE_QUALIFIED_REPLAY,
    BoundedChange,
    BoundedWorkOrder,
    GateEvidenceReference,
    GenerationResultLedger,
)

AT = datetime(2026, 8, 21, 21, 0, tzinfo=timezone.utc)


class _Gates:
    def __init__(self, candidate_digest: str, *, fail_at: str | None = None) -> None:
        self.candidate_digest = candidate_digest
        self.fail_at = fail_at
        self.ran: list[str] = []

    def contract_validation(self) -> bool:
        self.ran.append(GATE_CONTRACT_VALIDATION)
        return self.fail_at != GATE_CONTRACT_VALIDATION

    def offline_replay(self) -> GateEvidenceReference:
        return self._evidence("offline_replay", SOURCE_QUALIFIED_REPLAY, "replay")

    def isaac_lab(self) -> GateEvidenceReference:
        return self._evidence("isaac_lab", SOURCE_ISAAC_LAB, "isaac")

    def mujoco(self) -> GateEvidenceReference:
        return self._evidence("mujoco", SOURCE_MUJOCO, "mujoco")

    def observation_shadow(self) -> GateEvidenceReference:
        return self._evidence("observation_shadow", SOURCE_OBSERVATION_SHADOW, "shadow")

    def hardware_approval(self) -> bool:
        self.ran.append(GATE_HARDWARE_APPROVAL)
        return self.fail_at != GATE_HARDWARE_APPROVAL

    def hardware_pilot(self) -> GateEvidenceReference:
        return self._evidence("hardware_pilot", SOURCE_HARDWARE_PILOT, "pilot")

    def _evidence(self, gate: str, source: str, digest: str) -> GateEvidenceReference:
        self.ran.append(gate)
        return GateEvidenceReference(
            gate,
            source,
            digest,
            self.candidate_digest,
            episode_ids=("real-anchor-001",) if gate == "hardware_pilot" else (),
            refusals=("failed",) if self.fail_at == gate else (),
        )


def _work_order(result) -> BoundedWorkOrder:
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


class ACTGenerationPromotionAcceptanceTest(unittest.TestCase):
    def test_act_candidate_closes_the_full_evidence_ladder_without_hardware_authority(self) -> None:
        candidate = _act_candidate("act-promotion-001")
        gates = _Gates(candidate.bundle.digest())
        ledger = GenerationResultLedger()

        promotion = ACTGenerationPromoter().promote(
            generation_id="generation-act-001",
            candidate=candidate,
            gates=gates,
            ledger=ledger,
            work_order_from=_work_order,
            now=AT,
        )

        self.assertNotIsInstance(promotion, PromotionFailure)
        assert not isinstance(promotion, PromotionFailure)
        self.assertEqual(promotion.executed_gates, ACT_GENERATION_GATE_ORDER)
        self.assertEqual(promotion.real_anchor_episode_ids, ("real-anchor-001",))
        self.assertIs(ledger.result_for(promotion.result.digest()), promotion.result)
        self.assertIs(ledger.work_order_for(promotion.work_order.order_id), promotion.work_order)
        self.assertFalse(hasattr(promotion, "hardware_authority"))

    def test_a_failed_gate_stops_later_gates_and_never_seals_real_success(self) -> None:
        candidate = _act_candidate("act-promotion-002")
        gates = _Gates(candidate.bundle.digest(), fail_at="isaac_lab")

        failure = ACTGenerationPromoter().promote(
            generation_id="generation-act-002",
            candidate=candidate,
            gates=gates,
            ledger=GenerationResultLedger(),
            work_order_from=_work_order,
            now=AT,
        )

        self.assertIsInstance(failure, PromotionFailure)
        assert isinstance(failure, PromotionFailure)
        self.assertEqual(failure.failed_gate, "isaac_lab")
        self.assertEqual(gates.ran, [GATE_CONTRACT_VALIDATION, "offline_replay", "isaac_lab"])


if __name__ == "__main__":
    unittest.main()
