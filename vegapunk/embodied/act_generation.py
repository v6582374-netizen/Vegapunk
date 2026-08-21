"""The single promotion seam for one end-to-end ACT Generation."""

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
    BoundedWorkOrder,
    GateEvidenceReference,
    GenerationResultLedger,
    SealedGenerationResult,
)
from vegapunk.embodied.promotion import (
    GATE_CONTRACT_VALIDATION,
    GATE_EVIDENCE_SEALING,
    GATE_HARDWARE_APPROVAL,
    PROMOTION_GATE_ORDER,
)

ACT_GENERATION_GATE_ORDER = PROMOTION_GATE_ORDER


class ACTEvidenceGates(Protocol):
    """The owned evidence gates; none exposes a second actuator path."""

    def contract_validation(self) -> bool: ...

    def offline_replay(self) -> GateEvidenceReference: ...

    def isaac_lab(self) -> GateEvidenceReference: ...

    def mujoco(self) -> GateEvidenceReference: ...

    def observation_shadow(self) -> GateEvidenceReference: ...

    def hardware_approval(self) -> bool: ...

    def hardware_pilot(self) -> GateEvidenceReference: ...


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
    real_anchor_episode_ids: tuple[str, ...]
    executed_gates: tuple[str, ...]
    previous_result: SealedGenerationResult | None = None

    @property
    def compared_candidate_digests(self) -> tuple[str, str] | None:
        if self.previous_result is None:
            return None
        return (self.previous_result.candidate.digest(), self.result.candidate.digest())


class ACTGenerationPromoter:
    """Promote one ACT Candidate through the only complete evidence ladder."""

    def promote(
        self,
        *,
        generation_id: str,
        candidate: EndToEndACTCandidate,
        gates: ACTEvidenceGates,
        ledger: GenerationResultLedger,
        work_order_from: Callable[[SealedGenerationResult], BoundedWorkOrder],
        now: datetime,
        previous_result_digest: str | None = None,
    ) -> ACTGenerationPromotion | PromotionFailure:
        if not isinstance(candidate, EndToEndACTCandidate):
            raise TypeError("ACT promotion needs an end-to-end ACT Candidate")
        previous_result = (
            None if previous_result_digest is None else ledger.result_for(previous_result_digest)
        )
        if previous_result_digest is not None and previous_result is None:
            raise ValueError("a comparison names a sealed previous Generation")
        if not gates.contract_validation():
            return PromotionFailure(generation_id, GATE_CONTRACT_VALIDATION, ())

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
            evidence.append(ledger.record_gate_evidence(record))

        executed.append(GATE_HARDWARE_APPROVAL)
        if not gates.hardware_approval():
            return PromotionFailure(generation_id, GATE_HARDWARE_APPROVAL, tuple(executed))

        pilot = gates.hardware_pilot()
        executed.append(GATE_HARDWARE_PILOT)
        if not _passes(pilot, GATE_HARDWARE_PILOT, candidate) or not pilot.episode_ids:
            return PromotionFailure(generation_id, GATE_HARDWARE_PILOT, tuple(executed))
        evidence.append(ledger.record_gate_evidence(pilot))

        result = ledger.seal(
            SealedGenerationResult(generation_id, candidate.bundle, tuple(evidence), now)
        )
        order = ledger.propose(work_order_from(result))
        return ACTGenerationPromotion(
            result,
            order,
            pilot.episode_ids,
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
