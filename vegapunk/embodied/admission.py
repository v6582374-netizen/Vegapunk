"""The layered admission path from policy evaluation to supervised hardware.

Version 1 admits a skill to hardware only after evidence accumulates through
an ordered ladder, and only with a fresh human approval pinned to the exact
evidence that was reviewed:

``policy_evaluation`` -> ``offline_replay`` -> ``shadow_mode`` ->
``hardware_supervised``

Two properties matter more than the specific thresholds. Evidence is scoped:
a record is valid only for the one skill revision, embodiment digest, and
policy digest it was produced on, because a benchmark score or a run on a
different end effector says nothing about this robot. And approval is pinned:
an approval names the evidence digest it reviewed, so newly recorded evidence
withdraws the admission instead of inheriting it.

A benchmark stage can establish software-contract correctness but never that a
physical action is safe, which is why ``policy_evaluation`` alone cannot admit
hardware execution no matter how many attempts it accumulates.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

STAGE_POLICY_EVALUATION = "policy_evaluation"
STAGE_OFFLINE_REPLAY = "offline_replay"
STAGE_SHADOW_MODE = "shadow_mode"
STAGE_HARDWARE_SUPERVISED = "hardware_supervised"

ADMISSION_STAGE_ORDER = (
    STAGE_POLICY_EVALUATION,
    STAGE_OFFLINE_REPLAY,
    STAGE_SHADOW_MODE,
    STAGE_HARDWARE_SUPERVISED,
)

MINIMUM_STAGE_ATTEMPTS = 10
MINIMUM_STAGE_SUCCESS_RATE = 0.9
APPROVAL_VALIDITY = timedelta(hours=8)


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class EvidenceRecord:
    """One validation result for one skill revision on one configuration."""

    stage: str
    skill_version_id: str
    embodiment_digest: str
    policy_digest: Optional[str]
    attempts: int
    successes: int
    safety_violations: int
    recorded_at: datetime
    notes: str = ""

    def __post_init__(self) -> None:
        if self.stage not in ADMISSION_STAGE_ORDER:
            raise ValueError(
                f"unknown admission stage {self.stage!r}; expected one of "
                f"{list(ADMISSION_STAGE_ORDER)!r}"
            )
        if self.attempts < 0 or self.successes < 0:
            raise ValueError("attempts and successes cannot be negative")
        if self.successes > self.attempts:
            raise ValueError(
                f"stage {self.stage!r} records {self.successes} successes for "
                f"{self.attempts} attempts"
            )
        if self.safety_violations < 0:
            raise ValueError("safety_violations cannot be negative")

    @property
    def success_rate(self) -> float:
        if self.attempts == 0:
            return 0.0
        return self.successes / self.attempts

    def scope_key(self) -> tuple[str, str, Optional[str]]:
        return (
            self.skill_version_id,
            self.embodiment_digest,
            self.policy_digest,
        )

    def as_evidence(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "skill_version_id": self.skill_version_id,
            "embodiment_digest": self.embodiment_digest,
            "policy_digest": self.policy_digest,
            "attempts": self.attempts,
            "successes": self.successes,
            "safety_violations": self.safety_violations,
            "recorded_at": self.recorded_at.isoformat(),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class HumanApproval:
    """One human's durable authorization for supervised hardware execution.

    ``evidence_digest`` may be empty when the approver did not pin a specific
    evidence set; the decision then relies on approval freshness alone. A
    pinned digest is stronger and is what a review surface should record.
    """

    skill_version_id: str
    embodiment_digest: str
    policy_digest: Optional[str]
    approver: str
    approved_at: datetime
    statement: str
    evidence_digest: str = ""

    def __post_init__(self) -> None:
        if not self.approver.strip():
            raise ValueError("a HumanApproval must name its approver")
        if not self.statement.strip():
            raise ValueError(
                "a HumanApproval must record what the approver verified"
            )

    def scope_key(self) -> tuple[str, str, Optional[str]]:
        return (
            self.skill_version_id,
            self.embodiment_digest,
            self.policy_digest,
        )


@dataclass(frozen=True)
class AdmissionDecision:
    """Whether a target stage may run, with every blocking reason listed."""

    target_stage: str
    admitted: bool
    evidence_digest: str
    blocking_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "blocking_reasons", tuple(self.blocking_reasons)
        )


class AdmissionLedger:
    """The append-only record of validation evidence."""

    def __init__(self) -> None:
        self._records: list[EvidenceRecord] = []

    def record(self, evidence: EvidenceRecord) -> EvidenceRecord:
        self._records.append(evidence)
        return evidence

    def records(self) -> tuple[EvidenceRecord, ...]:
        return tuple(self._records)

    def scoped_records(
        self,
        skill_version_id: str,
        embodiment_digest: str,
        policy_digest: Optional[str],
    ) -> tuple[EvidenceRecord, ...]:
        scope = (skill_version_id, embodiment_digest, policy_digest)
        return tuple(
            record for record in self._records if record.scope_key() == scope
        )

    def evidence_digest(
        self,
        skill_version_id: str,
        embodiment_digest: str,
        policy_digest: Optional[str],
    ) -> str:
        """Identify the exact evidence set an approver can pin to."""
        return _digest(
            [
                record.as_evidence()
                for record in self.scoped_records(
                    skill_version_id, embodiment_digest, policy_digest
                )
            ]
        )


def _stage_findings(
    stage: str, records: tuple[EvidenceRecord, ...]
) -> list[str]:
    stage_records = [record for record in records if record.stage == stage]
    if not stage_records:
        return [f"stage {stage} has no evidence for this configuration"]

    findings: list[str] = []
    attempts = sum(record.attempts for record in stage_records)
    successes = sum(record.successes for record in stage_records)
    violations = sum(record.safety_violations for record in stage_records)

    if violations:
        findings.append(
            f"stage {stage} recorded {violations} safety violation(s); "
            "hardware admission is withdrawn until they are resolved"
        )
    if attempts < MINIMUM_STAGE_ATTEMPTS:
        findings.append(
            f"stage {stage} has {attempts} attempts, below the required "
            f"{MINIMUM_STAGE_ATTEMPTS}"
        )
    rate = successes / attempts if attempts else 0.0
    if rate < MINIMUM_STAGE_SUCCESS_RATE:
        findings.append(
            f"stage {stage} success rate {rate:.2f} is below the required "
            f"{MINIMUM_STAGE_SUCCESS_RATE:.2f}"
        )
    return findings


def evaluate_admission(
    ledger: AdmissionLedger,
    skill_version_id: str,
    embodiment_digest: str,
    policy_digest: Optional[str],
    target_stage: str,
    approval: Optional[HumanApproval],
    now: datetime,
) -> AdmissionDecision:
    """Decide whether one configuration may run at ``target_stage``."""
    if target_stage not in ADMISSION_STAGE_ORDER:
        raise ValueError(f"unknown admission stage {target_stage!r}")

    records = ledger.scoped_records(
        skill_version_id, embodiment_digest, policy_digest
    )
    digest = ledger.evidence_digest(
        skill_version_id, embodiment_digest, policy_digest
    )

    blocking: list[str] = []
    required_stages = ADMISSION_STAGE_ORDER[
        : ADMISSION_STAGE_ORDER.index(target_stage)
    ]
    for stage in required_stages:
        blocking.extend(_stage_findings(stage, records))

    if target_stage == STAGE_HARDWARE_SUPERVISED:
        if approval is None:
            blocking.append(
                "supervised hardware execution requires a human approval"
            )
        else:
            if approval.scope_key() != (
                skill_version_id,
                embodiment_digest,
                policy_digest,
            ):
                blocking.append(
                    "the human approval was issued for a different skill "
                    "revision, embodiment, or policy"
                )
            if now - approval.approved_at > APPROVAL_VALIDITY:
                blocking.append(
                    "the human approval has expired and must be re-issued "
                    "before hardware execution"
                )
            if approval.evidence_digest and approval.evidence_digest != digest:
                blocking.append(
                    "the human approval was pinned to a different evidence "
                    "set; re-review the current evidence"
                )

    return AdmissionDecision(
        target_stage=target_stage,
        admitted=not blocking,
        evidence_digest=digest,
        blocking_reasons=tuple(blocking),
    )
