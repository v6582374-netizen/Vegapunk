"""ACT's private execution adapter for the shared Generation promotion seam."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from vegapunk.embodied.act_candidate import EndToEndACTCandidate
from vegapunk.embodied.generation_result import (
    GATE_HARDWARE_PILOT,
    GATE_ISAAC_LAB,
    GATE_MUJOCO,
    GATE_OBSERVATION_SHADOW,
    GATE_OFFLINE_REPLAY,
    SOURCE_HARDWARE_PILOT,
    BoundedWorkOrder,
    GateEvidenceReference,
    GenerationPilotAnchor,
    GenerationResultLedger,
    SealedGenerationResult,
)
from vegapunk.embodied.pilot import (
    PILOT_SOURCE_OPERATIONAL,
    HardwarePilotApproval,
    OperationalRunRegistration,
    PilotBatchEvidence,
)
from vegapunk.embodied.promotion import (
    GATE_CONTRACT_VALIDATION,
    GATE_EVIDENCE_SEALING,
    GATE_HARDWARE_APPROVAL,
    PROMOTION_GATE_ORDER,
    PromotionSubmission,
)

ACT_GENERATION_GATE_ORDER = PROMOTION_GATE_ORDER


class ACTEvidenceGates(Protocol):
    """The owned evidence gates; none exposes a second actuator path."""

    def offline_replay(self) -> GateEvidenceReference: ...

    def isaac_lab(self) -> GateEvidenceReference: ...

    def mujoco(self) -> GateEvidenceReference: ...

    def observation_shadow(self) -> GateEvidenceReference: ...

    def hardware_approval(self) -> HardwarePilotApproval: ...

    def hardware_pilot(self) -> tuple[PilotBatchEvidence, OperationalRunRegistration]: ...


@dataclass(frozen=True)
class PromotionFailure:
    generation_id: str
    failed_gate: str
    executed_gates: tuple[str, ...]


@dataclass(frozen=True)
class ACTGenerationPromotion:
    """The sealed result and bounded next action, without execution authority."""

    result: SealedGenerationResult
    work_order: BoundedWorkOrder
    executed_gates: tuple[str, ...]
    previous_result: SealedGenerationResult | None = None

    @property
    def compared_candidate_digests(self) -> tuple[str, str] | None:
        if self.previous_result is None:
            return None
        return (self.previous_result.candidate.digest(), self.result.candidate.digest())

    @property
    def real_anchor_episode_ids(self) -> tuple[str, ...]:
        return self.real_anchor.episode_ids

    @property
    def real_anchor(self) -> GenerationPilotAnchor:
        anchor = self.result.real_anchor
        if anchor is None:
            raise AssertionError("an ACT promotion must seal its real pilot anchor")
        return anchor


def _execute_act_generation(
    submission: PromotionSubmission,
    *,
    generation_id: str,
    candidate: EndToEndACTCandidate,
    gates: ACTEvidenceGates,
    result_ledger: GenerationResultLedger,
    work_order_from: Callable[[SealedGenerationResult], BoundedWorkOrder],
    now: datetime,
    previous_result_digest: str | None = None,
) -> ACTGenerationPromotion | PromotionFailure:
    """Run ACT's evidence ladder after ``promote_generation`` admits it."""
    if not isinstance(candidate, EndToEndACTCandidate):
        raise TypeError("ACT promotion needs an end-to-end ACT Candidate")
    if submission.candidate != candidate.bundle:
        raise ValueError("ACT promotion submission must name its exact Candidate")
    previous_result = (
        None
        if previous_result_digest is None
        else result_ledger.result_for(previous_result_digest)
    )
    if previous_result_digest is not None and previous_result is None:
        raise ValueError("a comparison names a sealed previous Generation")

    executed = [GATE_CONTRACT_VALIDATION]
    evidence: list[GateEvidenceReference] = []
    for gate, run in (
        (GATE_OFFLINE_REPLAY, gates.offline_replay),
        (GATE_ISAAC_LAB, gates.isaac_lab),
        (GATE_MUJOCO, gates.mujoco),
        (GATE_OBSERVATION_SHADOW, gates.observation_shadow),
    ):
        record = run()
        executed.append(gate)
        if not _passes(record, gate, candidate):
            return PromotionFailure(generation_id, gate, tuple(executed))
        evidence.append(result_ledger.record_gate_evidence(record))

    executed.append(GATE_HARDWARE_APPROVAL)
    approval = gates.hardware_approval()
    plan = submission.plan
    assert plan is not None
    campaign_digest = plan.digest()
    if not approval.covers(submission, campaign_digest):
        return PromotionFailure(generation_id, GATE_HARDWARE_APPROVAL, tuple(executed))

    pilot, registration = gates.hardware_pilot()
    executed.append(GATE_HARDWARE_PILOT)
    if not pilot.is_operational_success_for(submission, approval, registration):
        return PromotionFailure(generation_id, GATE_HARDWARE_PILOT, tuple(executed))
    anchor = GenerationPilotAnchor(
        generation_id=generation_id,
        batch_id=pilot.batch_id,
        campaign_digest=pilot.campaign_digest,
        candidate_digest=pilot.candidate_digest,
        operational_run_id=pilot.source.operational_run_id,
        registration_digest=pilot.source.registration_digest,
        episode_ids=tuple(episode.episode_id for episode in pilot.episodes),
    )
    if pilot.source.source != PILOT_SOURCE_OPERATIONAL:
        raise AssertionError("operational pilot validation accepted a non-operational source")
    evidence.append(
        result_ledger.record_gate_evidence(
            GateEvidenceReference(
                GATE_HARDWARE_PILOT,
                SOURCE_HARDWARE_PILOT,
                pilot.digest(),
                candidate.bundle.digest(),
                episode_ids=anchor.episode_ids,
            )
        )
    )

    result = result_ledger.seal(
        SealedGenerationResult(
            generation_id,
            candidate.bundle,
            tuple(evidence),
            now,
            anchor,
        )
    )
    order = result_ledger.propose(work_order_from(result))
    return ACTGenerationPromotion(
        result,
        order,
        tuple(executed + [GATE_EVIDENCE_SEALING]),
        previous_result,
    )


def _passes(
    evidence: GateEvidenceReference, gate: str, candidate: EndToEndACTCandidate
) -> bool:
    return (
        evidence.gate == gate
        and evidence.candidate_digest == candidate.bundle.digest()
        and not evidence.refusals
        and not evidence.indeterminate_outcomes
    )
