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
    evaluate_admission,
)
from vegapunk.embodied.embodiment import UNIFOLM_VLA_BASE_G1_DEX1_JOINT

_NOW = datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)
_SKILL = "press_physical_button@1"
_EMBODIMENT = "e0f1a2b3c4d5e6f7"
_POLICY = UNIFOLM_VLA_BASE_G1_DEX1_JOINT.digest()


def _evidence(stage: str, **overrides: object) -> EvidenceRecord:
    fields: dict[str, object] = {
        "stage": stage,
        "skill_version_id": _SKILL,
        "embodiment_digest": _EMBODIMENT,
        "policy_digest": _POLICY,
        "attempts": 20,
        "successes": 20,
        "safety_violations": 0,
        "recorded_at": _NOW - timedelta(days=1),
        "notes": "",
    }
    fields.update(overrides)
    return EvidenceRecord(**fields)  # type: ignore[arg-type]


def _approval(**overrides: object) -> HumanApproval:
    fields: dict[str, object] = {
        "skill_version_id": _SKILL,
        "embodiment_digest": _EMBODIMENT,
        "policy_digest": _POLICY,
        "approver": "lab_owner",
        "approved_at": _NOW - timedelta(hours=1),
        "evidence_digest": "",
        "statement": "Workspace cleared, guardian present, e-stop verified.",
    }
    fields.update(overrides)
    return HumanApproval(**fields)  # type: ignore[arg-type]


def _full_ledger() -> AdmissionLedger:
    ledger = AdmissionLedger()
    ledger.record(_evidence(STAGE_POLICY_EVALUATION))
    ledger.record(_evidence(STAGE_OFFLINE_REPLAY))
    ledger.record(_evidence(STAGE_SHADOW_MODE))
    return ledger


class EvidenceRecordTest(unittest.TestCase):
    def test_successes_cannot_exceed_attempts(self) -> None:
        with self.assertRaises(ValueError):
            _evidence(STAGE_SHADOW_MODE, attempts=5, successes=6)

    def test_an_unknown_stage_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _evidence("vibes_check")

    def test_success_rate_is_zero_without_attempts(self) -> None:
        record = _evidence(STAGE_OFFLINE_REPLAY, attempts=0, successes=0)

        self.assertEqual(record.success_rate, 0.0)


class AdmissionStageOrderTest(unittest.TestCase):
    def test_hardware_execution_requires_every_prior_stage(self) -> None:
        ledger = AdmissionLedger()
        ledger.record(_evidence(STAGE_POLICY_EVALUATION))

        decision = evaluate_admission(
            ledger,
            skill_version_id=_SKILL,
            embodiment_digest=_EMBODIMENT,
            policy_digest=_POLICY,
            target_stage=STAGE_HARDWARE_SUPERVISED,
            approval=_approval(),
            now=_NOW,
        )

        self.assertFalse(decision.admitted)
        joined = " ".join(decision.blocking_reasons)
        self.assertIn(STAGE_OFFLINE_REPLAY, joined)
        self.assertIn(STAGE_SHADOW_MODE, joined)

    def test_a_complete_ledger_with_approval_admits_hardware_execution(
        self,
    ) -> None:
        decision = evaluate_admission(
            _full_ledger(),
            skill_version_id=_SKILL,
            embodiment_digest=_EMBODIMENT,
            policy_digest=_POLICY,
            target_stage=STAGE_HARDWARE_SUPERVISED,
            approval=_approval(),
            now=_NOW,
        )

        self.assertTrue(decision.admitted)
        self.assertEqual(decision.blocking_reasons, ())
        self.assertNotEqual(decision.evidence_digest, "")

    def test_shadow_mode_does_not_require_a_human_approval(self) -> None:
        ledger = AdmissionLedger()
        ledger.record(_evidence(STAGE_POLICY_EVALUATION))
        ledger.record(_evidence(STAGE_OFFLINE_REPLAY))

        decision = evaluate_admission(
            ledger,
            skill_version_id=_SKILL,
            embodiment_digest=_EMBODIMENT,
            policy_digest=_POLICY,
            target_stage=STAGE_SHADOW_MODE,
            approval=None,
            now=_NOW,
        )

        self.assertTrue(decision.admitted)

    def test_policy_evaluation_alone_never_admits_hardware(self) -> None:
        ledger = AdmissionLedger()
        ledger.record(
            _evidence(STAGE_POLICY_EVALUATION, attempts=500, successes=500)
        )

        decision = evaluate_admission(
            ledger,
            skill_version_id=_SKILL,
            embodiment_digest=_EMBODIMENT,
            policy_digest=_POLICY,
            target_stage=STAGE_HARDWARE_SUPERVISED,
            approval=_approval(),
            now=_NOW,
        )

        self.assertFalse(decision.admitted)


class EvidenceScopeTest(unittest.TestCase):
    def test_evidence_from_another_embodiment_does_not_transfer(self) -> None:
        ledger = _full_ledger()

        decision = evaluate_admission(
            ledger,
            skill_version_id=_SKILL,
            embodiment_digest="different_robot_00",
            policy_digest=_POLICY,
            target_stage=STAGE_HARDWARE_SUPERVISED,
            approval=_approval(embodiment_digest="different_robot_00"),
            now=_NOW,
        )

        self.assertFalse(decision.admitted)

    def test_evidence_from_another_skill_revision_does_not_transfer(
        self,
    ) -> None:
        ledger = _full_ledger()

        decision = evaluate_admission(
            ledger,
            skill_version_id="press_physical_button@2",
            embodiment_digest=_EMBODIMENT,
            policy_digest=_POLICY,
            target_stage=STAGE_HARDWARE_SUPERVISED,
            approval=_approval(skill_version_id="press_physical_button@2"),
            now=_NOW,
        )

        self.assertFalse(decision.admitted)

    def test_evidence_from_another_policy_digest_does_not_transfer(
        self,
    ) -> None:
        ledger = _full_ledger()

        decision = evaluate_admission(
            ledger,
            skill_version_id=_SKILL,
            embodiment_digest=_EMBODIMENT,
            policy_digest="finetuned_candidate",
            target_stage=STAGE_HARDWARE_SUPERVISED,
            approval=_approval(policy_digest="finetuned_candidate"),
            now=_NOW,
        )

        self.assertFalse(decision.admitted)


class EvidenceQualityTest(unittest.TestCase):
    def test_a_safety_violation_blocks_admission(self) -> None:
        ledger = AdmissionLedger()
        ledger.record(_evidence(STAGE_POLICY_EVALUATION))
        ledger.record(_evidence(STAGE_OFFLINE_REPLAY))
        ledger.record(_evidence(STAGE_SHADOW_MODE, safety_violations=1))

        decision = evaluate_admission(
            ledger,
            skill_version_id=_SKILL,
            embodiment_digest=_EMBODIMENT,
            policy_digest=_POLICY,
            target_stage=STAGE_HARDWARE_SUPERVISED,
            approval=_approval(),
            now=_NOW,
        )

        self.assertFalse(decision.admitted)
        self.assertIn("safety", " ".join(decision.blocking_reasons))

    def test_too_few_attempts_block_admission(self) -> None:
        ledger = AdmissionLedger()
        ledger.record(_evidence(STAGE_POLICY_EVALUATION))
        ledger.record(_evidence(STAGE_OFFLINE_REPLAY))
        ledger.record(_evidence(STAGE_SHADOW_MODE, attempts=3, successes=3))

        decision = evaluate_admission(
            ledger,
            skill_version_id=_SKILL,
            embodiment_digest=_EMBODIMENT,
            policy_digest=_POLICY,
            target_stage=STAGE_HARDWARE_SUPERVISED,
            approval=_approval(),
            now=_NOW,
        )

        self.assertFalse(decision.admitted)
        self.assertIn("attempts", " ".join(decision.blocking_reasons))

    def test_a_low_success_rate_blocks_admission(self) -> None:
        ledger = AdmissionLedger()
        ledger.record(_evidence(STAGE_POLICY_EVALUATION))
        ledger.record(_evidence(STAGE_OFFLINE_REPLAY))
        ledger.record(_evidence(STAGE_SHADOW_MODE, attempts=20, successes=10))

        decision = evaluate_admission(
            ledger,
            skill_version_id=_SKILL,
            embodiment_digest=_EMBODIMENT,
            policy_digest=_POLICY,
            target_stage=STAGE_HARDWARE_SUPERVISED,
            approval=_approval(),
            now=_NOW,
        )

        self.assertFalse(decision.admitted)
        self.assertIn("success rate", " ".join(decision.blocking_reasons))


class HumanApprovalTest(unittest.TestCase):
    def test_hardware_execution_without_approval_is_blocked(self) -> None:
        decision = evaluate_admission(
            _full_ledger(),
            skill_version_id=_SKILL,
            embodiment_digest=_EMBODIMENT,
            policy_digest=_POLICY,
            target_stage=STAGE_HARDWARE_SUPERVISED,
            approval=None,
            now=_NOW,
        )

        self.assertFalse(decision.admitted)
        self.assertIn("approval", " ".join(decision.blocking_reasons))

    def test_an_expired_approval_does_not_admit(self) -> None:
        decision = evaluate_admission(
            _full_ledger(),
            skill_version_id=_SKILL,
            embodiment_digest=_EMBODIMENT,
            policy_digest=_POLICY,
            target_stage=STAGE_HARDWARE_SUPERVISED,
            approval=_approval(approved_at=_NOW - timedelta(days=2)),
            now=_NOW,
        )

        self.assertFalse(decision.admitted)
        self.assertIn("expired", " ".join(decision.blocking_reasons))

    def test_an_approval_for_a_stale_evidence_set_does_not_admit(self) -> None:
        ledger = _full_ledger()
        decision = evaluate_admission(
            ledger,
            skill_version_id=_SKILL,
            embodiment_digest=_EMBODIMENT,
            policy_digest=_POLICY,
            target_stage=STAGE_HARDWARE_SUPERVISED,
            approval=_approval(evidence_digest="approved_an_older_set"),
            now=_NOW,
        )

        self.assertFalse(decision.admitted)
        self.assertIn("evidence", " ".join(decision.blocking_reasons))

    def test_an_approval_pinned_to_the_current_evidence_admits(self) -> None:
        ledger = _full_ledger()
        digest = ledger.evidence_digest(
            skill_version_id=_SKILL,
            embodiment_digest=_EMBODIMENT,
            policy_digest=_POLICY,
        )

        decision = evaluate_admission(
            ledger,
            skill_version_id=_SKILL,
            embodiment_digest=_EMBODIMENT,
            policy_digest=_POLICY,
            target_stage=STAGE_HARDWARE_SUPERVISED,
            approval=_approval(evidence_digest=digest),
            now=_NOW,
        )

        self.assertTrue(decision.admitted)

    def test_an_approval_without_a_named_approver_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _approval(approver="")

    def test_an_approval_without_a_statement_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _approval(statement="  ")

    def test_new_evidence_invalidates_an_earlier_pinned_approval(self) -> None:
        ledger = _full_ledger()
        digest = ledger.evidence_digest(
            skill_version_id=_SKILL,
            embodiment_digest=_EMBODIMENT,
            policy_digest=_POLICY,
        )
        approval = _approval(evidence_digest=digest)
        ledger.record(
            _evidence(STAGE_SHADOW_MODE, attempts=1, successes=0, notes="regression")
        )

        decision = evaluate_admission(
            ledger,
            skill_version_id=_SKILL,
            embodiment_digest=_EMBODIMENT,
            policy_digest=_POLICY,
            target_stage=STAGE_HARDWARE_SUPERVISED,
            approval=approval,
            now=_NOW,
        )

        self.assertFalse(decision.admitted)


class LedgerImmutabilityTest(unittest.TestCase):
    def test_recorded_evidence_cannot_be_removed(self) -> None:
        ledger = AdmissionLedger()
        ledger.record(_evidence(STAGE_SHADOW_MODE, attempts=1, successes=0))

        self.assertFalse(hasattr(ledger, "remove"))
        self.assertEqual(len(ledger.records()), 1)

    def test_records_are_returned_as_an_immutable_sequence(self) -> None:
        ledger = _full_ledger()

        records = ledger.records()

        self.assertIsInstance(records, tuple)
        self.assertEqual(len(records), 3)


if __name__ == "__main__":
    unittest.main()
