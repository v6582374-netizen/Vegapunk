from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from vegapunk.embodied.generation_result import (
    CHANGE_KINDS,
    CHANGE_TRAINING,
    FAILURE_POLICY_CAPACITY,
    FAILURE_TAXONOMY,
    GATE_HARDWARE_PILOT,
    GATE_ISAAC_LAB,
    GATE_MUJOCO,
    GATE_OBSERVATION_SHADOW,
    GATE_OFFLINE_REPLAY,
    SOURCE_HARDWARE_PILOT,
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
from vegapunk.embodied.promotion import CandidateBundle

AT = datetime(2026, 8, 21, 18, 0, tzinfo=timezone.utc)


def _candidate() -> CandidateBundle:
    return CandidateBundle(
        candidate_id="candidate-generation-001",
        policy_artifact_digest="policy-001",
        data_manifest_digest="data-001",
        training_recipe_digest="recipe-001",
        observation_schema_digest="observation-001",
        action_schema_digest="action-001",
        skill_revision_id="skill@1",
        skill_revision_digest="skill-digest-001",
        embodiment_digest="embodiment-001",
        configuration_digest="configuration-001",
    )


def _result() -> SealedGenerationResult:
    candidate = _candidate()
    digest = candidate.digest()
    return SealedGenerationResult(
        generation_id="generation-001",
        candidate=candidate,
        gate_evidence=(
            GateEvidenceReference(
                GATE_OFFLINE_REPLAY, SOURCE_QUALIFIED_REPLAY, "replay-001", digest
            ),
            GateEvidenceReference(
                GATE_ISAAC_LAB,
                SOURCE_ISAAC_LAB,
                "isaac-001",
                digest,
                refusals=("camera drift",),
            ),
            GateEvidenceReference(GATE_MUJOCO, SOURCE_MUJOCO, "mujoco-001", digest),
            GateEvidenceReference(
                GATE_OBSERVATION_SHADOW,
                SOURCE_OBSERVATION_SHADOW,
                "shadow-001",
                digest,
                indeterminate_outcomes=("witness unavailable",),
            ),
            GateEvidenceReference(
                GATE_HARDWARE_PILOT,
                SOURCE_HARDWARE_PILOT,
                "pilot-001",
                digest,
                episode_ids=("episode-001", "episode-002"),
            ),
        ),
        sealed_at=AT,
    )


def _order(
    result: SealedGenerationResult,
    *,
    order_id: str = "order-001",
    proposed_at: datetime = AT + timedelta(seconds=1),
) -> BoundedWorkOrder:
    return BoundedWorkOrder(
        order_id=order_id,
        result_digest=result.digest(),
        failure_class=FAILURE_POLICY_CAPACITY,
        change=BoundedChange(
            kind=CHANGE_TRAINING,
            target="ACT context window",
            proposal="Increase from 16 to 32 frames.",
            bound="No more than 32 frames.",
        ),
        evidence_basis=(result.gate_evidence[3], result.gate_evidence[4]),
        unchanged_controls=("skill revision", "action schema", "safety envelope"),
        next_required_gate=GATE_OFFLINE_REPLAY,
        proposed_at=proposed_at,
    )


def _seal(
    ledger: GenerationResultLedger, result: SealedGenerationResult
) -> SealedGenerationResult:
    for evidence in result.gate_evidence:
        ledger.record_gate_evidence(evidence)
    return ledger.seal(result)


class GenerationResultAcceptanceTest(unittest.TestCase):
    def test_seal_keeps_every_gate_source_identity_refusal_and_indeterminate(
        self,
    ) -> None:
        result = _result()

        self.assertEqual(
            tuple(item.gate for item in result.gate_evidence),
            (
                GATE_OFFLINE_REPLAY,
                GATE_ISAAC_LAB,
                GATE_MUJOCO,
                GATE_OBSERVATION_SHADOW,
                GATE_HARDWARE_PILOT,
            ),
        )
        self.assertEqual(result.refusals[GATE_ISAAC_LAB], ("camera drift",))
        self.assertEqual(
            result.indeterminate_outcomes[GATE_OBSERVATION_SHADOW],
            ("witness unavailable",),
        )
        self.assertEqual(
            result.gate_evidence[-1].episode_ids, ("episode-001", "episode-002")
        )

    def test_source_renaming_and_candidate_mixing_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "source"):
            GateEvidenceReference(
                GATE_MUJOCO, SOURCE_ISAAC_LAB, "x", _candidate().digest()
            )
        result = _result()
        mixed = list(result.gate_evidence)
        mixed[-1] = GateEvidenceReference(
            GATE_HARDWARE_PILOT, SOURCE_HARDWARE_PILOT, "pilot", "other"
        )
        with self.assertRaisesRegex(ValueError, "Candidate"):
            SealedGenerationResult("generation-001", _candidate(), tuple(mixed), AT)

    def test_work_order_can_only_follow_a_seal_and_is_bounded(self) -> None:
        ledger = GenerationResultLedger()
        result = _result()
        order = _order(result)
        result = _seal(ledger, result)
        self.assertIs(ledger.propose(order), order)
        with self.assertRaisesRegex(ValueError, "sealed"):
            GenerationResultLedger().propose(order)

    def test_one_order_follows_its_result_without_rewriting_its_history(self) -> None:
        ledger = GenerationResultLedger()
        result = _seal(ledger, _result())
        early_order = _order(result, order_id="order-early", proposed_at=AT)
        with self.assertRaisesRegex(ValueError, "predate"):
            ledger.propose(early_order)

        order = _order(result, order_id="order-002")
        ledger.propose(order)
        another_order = _order(result, order_id="order-003")
        with self.assertRaisesRegex(ValueError, "one next"):
            ledger.propose(another_order)

    def test_failure_taxonomy_has_every_required_attribution(self) -> None:
        self.assertEqual(
            FAILURE_TAXONOMY,
            {
                "task_definition",
                "reset",
                "data",
                "perception",
                "action_semantics",
                "transition",
                "contact",
                "latency",
                "safety",
                "witness",
                "policy_capacity",
            },
        )
        self.assertEqual(len(CHANGE_KINDS), 6)

    def test_work_order_rejects_foreign_evidence_and_unknown_next_gate(self) -> None:
        result = _result()
        foreign_evidence = GateEvidenceReference(
            GATE_ISAAC_LAB,
            SOURCE_ISAAC_LAB,
            "other-isaac-evidence",
            result.candidate.digest(),
        )
        order = _order(result)
        invalid_order = BoundedWorkOrder(
            order_id=order.order_id,
            result_digest=order.result_digest,
            failure_class=order.failure_class,
            change=order.change,
            evidence_basis=(foreign_evidence,),
            unchanged_controls=order.unchanged_controls,
            next_required_gate=order.next_required_gate,
            proposed_at=order.proposed_at,
        )
        ledger = GenerationResultLedger()
        _seal(ledger, result)
        with self.assertRaisesRegex(ValueError, "only sealed"):
            ledger.propose(invalid_order)
        with self.assertRaisesRegex(ValueError, "real next"):
            BoundedWorkOrder(
                order_id=order.order_id,
                result_digest=order.result_digest,
                failure_class=order.failure_class,
                change=order.change,
                evidence_basis=order.evidence_basis,
                unchanged_controls=order.unchanged_controls,
                next_required_gate="not-a-gate",
                proposed_at=order.proposed_at,
            )

    def test_result_can_only_seal_pre_recorded_source_evidence(self) -> None:
        result = _result()
        ledger = GenerationResultLedger()
        with self.assertRaisesRegex(ValueError, "recorded Gate evidence"):
            ledger.seal(result)
        _seal(ledger, result)
        with self.assertRaisesRegex(ValueError, "renamed"):
            ledger.record_gate_evidence(
                GateEvidenceReference(
                    GATE_ISAAC_LAB,
                    SOURCE_ISAAC_LAB,
                    result.gate_evidence[0].digest,
                    result.candidate.digest(),
                )
            )


if __name__ == "__main__":
    unittest.main()
