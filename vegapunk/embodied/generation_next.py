"""Create a human-approved successor Generation without inheriting admission."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from vegapunk.embodied.act_candidate import EndToEndACTCandidate
from vegapunk.embodied.generation_result import (
    GATE_OFFLINE_REPLAY,
    BoundedWorkOrder,
    GateEvidenceReference,
    GenerationResultLedger,
    SealedGenerationResult,
)
from vegapunk.embodied.promotion import (
    GATE_CONTRACT_VALIDATION,
    CandidateBundle,
    PromotionConfiguration,
)

ENTRY_GATES = (GATE_CONTRACT_VALIDATION, GATE_OFFLINE_REPLAY)

_NEXT_GENERATION_SEAL = object()

CONTROL_POLICY = "policy"
CONTROL_SKILL = "skill_revision"
CONTROL_INDEPENDENT_WITNESS = "independent_witness"
CONTROL_ACTION_PROTOCOL = "action_protocol"
CONTROL_EMBODIMENT = "embodiment"
CONTROL_CRITICAL_CALIBRATION = "critical_calibration"
CONTROL_SAFETY_ENVELOPE = "safety_envelope"

_CONTROL_IDENTITIES = {
    CONTROL_POLICY: "policy",
    CONTROL_SKILL: "skill",
    CONTROL_INDEPENDENT_WITNESS: "independent_witness",
    CONTROL_ACTION_PROTOCOL: "action_protocol",
    CONTROL_EMBODIMENT: "embodiment",
    CONTROL_CRITICAL_CALIBRATION: "critical_calibration",
}
_UNCHANGED_CONTROLS = frozenset((*_CONTROL_IDENTITIES, CONTROL_SAFETY_ENVELOPE))


@dataclass(frozen=True)
class HumanGenerationApproval:
    """A named person's approval of one Work Order and one ACT Candidate."""

    work_order_id: str
    candidate_digest: str
    approved_by: str
    approved_at: datetime
    approval_proof: str

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.work_order_id,
                self.candidate_digest,
                self.approved_by,
                self.approval_proof,
            )
        ):
            raise ValueError("a Generation approval names the order, Candidate, and human")


class HumanGenerationApprovalAuthority(Protocol):
    """The external trust boundary that verifies a named human's approval."""

    def verifies(self, approval: HumanGenerationApproval) -> bool: ...


class GenerationApprovalLedger:
    """The append-only record of human approvals verified at the trust boundary."""

    def __init__(self) -> None:
        self._approvals: dict[tuple[str, str], HumanGenerationApproval] = {}

    def record(self, approval: HumanGenerationApproval) -> HumanGenerationApproval:
        key = (approval.work_order_id, approval.candidate_digest)
        existing = self._approvals.get(key)
        if existing is not None and existing != approval:
            raise ValueError("a human Generation approval cannot be rewritten")
        self._approvals[key] = approval
        return approval

    def approval_for(
        self, work_order_id: str, candidate_digest: str
    ) -> HumanGenerationApproval | None:
        return self._approvals.get((work_order_id, candidate_digest))


@dataclass(frozen=True)
class GenerationIdentity:
    """The contract identities whose change invalidates prior Gate evidence."""

    policy_artifact_digest: str
    skill_revision: tuple[str, str]
    independent_witness_digest: str
    action_protocol_digest: str
    embodiment_digest: str
    calibration_digest: str

    @classmethod
    def from_candidate(
        cls, candidate: CandidateBundle, configuration: PromotionConfiguration
    ) -> GenerationIdentity:
        if candidate.configuration_digest != configuration.digest():
            raise ValueError("the ACT Candidate names a different configuration")
        if candidate.action_schema_digest != configuration.action_protocol_digest:
            raise ValueError("the ACT Candidate action protocol is incompatible")
        if candidate.observation_schema_digest != configuration.observation_schema_digest:
            raise ValueError("the ACT Candidate observation schema is incompatible")
        if candidate.embodiment_digest != configuration.embodiment_digest:
            raise ValueError("the ACT Candidate names a different embodiment")
        return cls(
            policy_artifact_digest=candidate.policy_artifact_digest,
            skill_revision=(candidate.skill_revision_id, candidate.skill_revision_digest),
            independent_witness_digest=configuration.independent_witness_digest,
            action_protocol_digest=configuration.action_protocol_digest,
            embodiment_digest=configuration.embodiment_digest,
            calibration_digest=configuration.calibration_digest,
        )

    def changed_from(self, parent: GenerationIdentity) -> tuple[str, ...]:
        identities = (
            ("policy", self.policy_artifact_digest, parent.policy_artifact_digest),
            ("skill", self.skill_revision, parent.skill_revision),
            (
                "independent_witness",
                self.independent_witness_digest,
                parent.independent_witness_digest,
            ),
            (
                "action_protocol",
                self.action_protocol_digest,
                parent.action_protocol_digest,
            ),
            ("embodiment", self.embodiment_digest, parent.embodiment_digest),
            ("critical_calibration", self.calibration_digest, parent.calibration_digest),
        )
        return tuple(name for name, current, previous in identities if current != previous)


@dataclass(frozen=True)
class NextGeneration:
    """A new, non-admitted Generation with an explicit immutable lineage."""

    generation_id: str
    source_generation_id: str
    source_result_digest: str
    source_result: SealedGenerationResult
    work_order: BoundedWorkOrder
    candidate: EndToEndACTCandidate
    approval: HumanGenerationApproval
    changed_variable: str
    changed_critical_identities: tuple[str, ...]
    unchanged_controls: tuple[str, ...]
    invalidated_gate_evidence: tuple[GateEvidenceReference, ...]
    entry_gates: tuple[str, ...]
    _next_generation_seal: object = field(
        default=None, repr=False, compare=False, hash=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "changed_critical_identities", tuple(self.changed_critical_identities)
        )
        object.__setattr__(self, "unchanged_controls", tuple(self.unchanged_controls))
        object.__setattr__(
            self, "invalidated_gate_evidence", tuple(self.invalidated_gate_evidence)
        )
        object.__setattr__(self, "entry_gates", tuple(self.entry_gates))
        if self._next_generation_seal is not _NEXT_GENERATION_SEAL:
            raise ValueError("a next Generation must be issued by GenerationSuccessor")
        if not all(
            value.strip()
            for value in (
                self.generation_id,
                self.source_generation_id,
                self.source_result_digest,
                self.changed_variable,
            )
        ):
            raise ValueError("a next Generation names its lineage and changed variable")
        if self.generation_id == self.source_generation_id:
            raise ValueError("a successor Generation has a new identity")
        if not self.changed_critical_identities or not self.unchanged_controls:
            raise ValueError("a next Generation records changed and unchanged controls")
        if self.entry_gates != ENTRY_GATES:
            raise ValueError("a next Generation starts from contract and offline Gates")
        if self.invalidated_gate_evidence != self.source_result.gate_evidence:
            raise ValueError("a next Generation invalidates all inherited Gate evidence")


class GenerationSuccessor:
    """The sole authority that turns a sealed Work Order into Generation N+1."""

    def __init__(self, approvals: HumanGenerationApprovalAuthority) -> None:
        if not callable(getattr(approvals, "verifies", None)):
            raise TypeError("a Generation successor needs a trusted human approval authority")
        self._approvals = approvals

    def create_next(
        self,
        *,
        generation_id: str,
        ledger: GenerationResultLedger,
        approval_ledger: GenerationApprovalLedger,
        source_configuration: PromotionConfiguration,
        configuration: PromotionConfiguration,
        work_order: BoundedWorkOrder,
        candidate: EndToEndACTCandidate,
        approval: HumanGenerationApproval,
    ) -> NextGeneration:
        if not isinstance(ledger, GenerationResultLedger):
            raise TypeError("a next Generation needs the sealed Generation ledger")
        if not isinstance(approval_ledger, GenerationApprovalLedger):
            raise TypeError("a next Generation needs the human approval ledger")
        if not isinstance(work_order, BoundedWorkOrder):
            raise TypeError("a next Generation needs a bounded Work Order")
        if not isinstance(candidate, EndToEndACTCandidate):
            raise TypeError("a next Generation needs an end-to-end ACT Candidate")
        if not isinstance(approval, HumanGenerationApproval):
            raise TypeError("a next Generation needs named human approval")
        recorded_order = ledger.work_order_for(work_order.order_id)
        if recorded_order != work_order:
            raise ValueError("a next Generation needs a sealed Work Order")
        source_result = ledger.result_for(work_order.result_digest)
        if source_result is None:
            raise ValueError("the Work Order must reference its sealed source Generation")
        if approval.work_order_id != work_order.order_id:
            raise ValueError("human approval names a different Work Order")
        if approval.candidate_digest != candidate.bundle.digest():
            raise ValueError("human approval names a different ACT Candidate")
        if approval_ledger.approval_for(
            approval.work_order_id, approval.candidate_digest
        ) != approval:
            raise ValueError("a next Generation needs recorded human approval")
        if not self._approvals.verifies(approval):
            raise ValueError("a next Generation needs verified human approval")
        if approval.approved_at <= work_order.proposed_at:
            raise ValueError("human approval must follow the proposed Work Order")

        source_identity = GenerationIdentity.from_candidate(
            source_result.candidate, source_configuration
        )
        next_identity = GenerationIdentity.from_candidate(candidate.bundle, configuration)
        changed_identities = next_identity.changed_from(source_identity)
        if not changed_identities:
            raise ValueError("a next Generation requires an explicit critical identity change")
        _reject_changed_controls(work_order.unchanged_controls, changed_identities)
        return NextGeneration(
            generation_id=generation_id,
            source_generation_id=source_result.generation_id,
            source_result_digest=source_result.digest(),
            source_result=source_result,
            work_order=work_order,
            candidate=candidate,
            approval=approval,
            changed_variable=work_order.change.target,
            changed_critical_identities=changed_identities,
            unchanged_controls=work_order.unchanged_controls,
            invalidated_gate_evidence=source_result.gate_evidence,
            entry_gates=ENTRY_GATES,
            _next_generation_seal=_NEXT_GENERATION_SEAL,
        )
def _reject_changed_controls(
    unchanged_controls: tuple[str, ...], changed_identities: tuple[str, ...]
) -> None:
    declared_unchanged = frozenset(unchanged_controls)
    if not declared_unchanged.issubset(_UNCHANGED_CONTROLS):
        raise ValueError("a Work Order names only structured unchanged controls")
    conflicting = tuple(
        identity
        for identity in changed_identities
        if any(
            control_identity == identity
            for control, control_identity in _CONTROL_IDENTITIES.items()
            if control in declared_unchanged
        )
    )
    if conflicting:
        raise ValueError("a Work Order cannot declare changed controls unchanged")
