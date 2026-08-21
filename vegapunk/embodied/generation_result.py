"""Seal one Generation's independent evidence and one bounded next experiment."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from vegapunk.embodied.promotion import CandidateBundle

GATE_OFFLINE_REPLAY = "offline_replay"
GATE_ISAAC_LAB = "isaac_lab"
GATE_MUJOCO = "mujoco"
GATE_OBSERVATION_SHADOW = "observation_shadow"
GATE_HARDWARE_PILOT = "hardware_pilot"

REQUIRED_GATES = (
    GATE_OFFLINE_REPLAY,
    GATE_ISAAC_LAB,
    GATE_MUJOCO,
    GATE_OBSERVATION_SHADOW,
    GATE_HARDWARE_PILOT,
)

SOURCE_QUALIFIED_REPLAY = "qualified_replay"
SOURCE_ISAAC_LAB = "isaac_lab"
SOURCE_MUJOCO = "mujoco"
SOURCE_OBSERVATION_SHADOW = "real_observation_shadow"
SOURCE_HARDWARE_PILOT = "supervised_hardware_pilot"

_GATE_SOURCES = {
    GATE_OFFLINE_REPLAY: SOURCE_QUALIFIED_REPLAY,
    GATE_ISAAC_LAB: SOURCE_ISAAC_LAB,
    GATE_MUJOCO: SOURCE_MUJOCO,
    GATE_OBSERVATION_SHADOW: SOURCE_OBSERVATION_SHADOW,
    GATE_HARDWARE_PILOT: SOURCE_HARDWARE_PILOT,
}

FAILURE_TASK_DEFINITION = "task_definition"
FAILURE_RESET = "reset"
FAILURE_DATA = "data"
FAILURE_PERCEPTION = "perception"
FAILURE_ACTION_SEMANTICS = "action_semantics"
FAILURE_TRANSITION = "transition"
FAILURE_CONTACT = "contact"
FAILURE_LATENCY = "latency"
FAILURE_SAFETY = "safety"
FAILURE_WITNESS = "witness"
FAILURE_POLICY_CAPACITY = "policy_capacity"

FAILURE_TAXONOMY = frozenset(
    {
        FAILURE_TASK_DEFINITION,
        FAILURE_RESET,
        FAILURE_DATA,
        FAILURE_PERCEPTION,
        FAILURE_ACTION_SEMANTICS,
        FAILURE_TRANSITION,
        FAILURE_CONTACT,
        FAILURE_LATENCY,
        FAILURE_SAFETY,
        FAILURE_WITNESS,
        FAILURE_POLICY_CAPACITY,
    }
)

CHANGE_DATA = "collect_data"
CHANGE_CALIBRATION = "recalibrate"
CHANGE_SIMULATOR = "modify_simulator"
CHANGE_TRAINING = "modify_training"
CHANGE_ENVELOPE = "adjust_envelope"
CHANGE_STOP = "stop_formulation"

CHANGE_KINDS = frozenset(
    {
        CHANGE_DATA,
        CHANGE_CALIBRATION,
        CHANGE_SIMULATOR,
        CHANGE_TRAINING,
        CHANGE_ENVELOPE,
        CHANGE_STOP,
    }
)


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]


@dataclass(frozen=True)
class GateEvidenceReference:
    """An immutable pointer into exactly one gate's own evidence ledger."""

    gate: str
    source: str
    digest: str
    candidate_digest: str
    episode_ids: tuple[str, ...] = ()
    refusals: tuple[str, ...] = ()
    indeterminate_outcomes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "episode_ids", tuple(self.episode_ids))
        object.__setattr__(self, "refusals", tuple(self.refusals))
        object.__setattr__(
            self, "indeterminate_outcomes", tuple(self.indeterminate_outcomes)
        )
        if self.gate not in REQUIRED_GATES or _GATE_SOURCES[self.gate] != self.source:
            raise ValueError("a Generation gate retains its own evidence source")
        if not all(value.strip() for value in (self.digest, self.candidate_digest)):
            raise ValueError("gate evidence names its sealed digest and Candidate")

    def as_payload(self) -> dict[str, object]:
        return {
            "gate": self.gate,
            "source": self.source,
            "digest": self.digest,
            "candidate_digest": self.candidate_digest,
            "episode_ids": list(self.episode_ids),
            "refusals": list(self.refusals),
            "indeterminate_outcomes": list(self.indeterminate_outcomes),
        }


@dataclass(frozen=True)
class SealedGenerationResult:
    generation_id: str
    candidate: CandidateBundle
    gate_evidence: tuple[GateEvidenceReference, ...]
    sealed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "gate_evidence", tuple(self.gate_evidence))
        if not self.generation_id.strip():
            raise ValueError("a sealed result names its Generation")
        gates = tuple(item.gate for item in self.gate_evidence)
        if gates != REQUIRED_GATES:
            raise ValueError("a sealed Generation records every gate in fixed order")
        candidate_digest = self.candidate.digest()
        if any(
            item.candidate_digest != candidate_digest for item in self.gate_evidence
        ):
            raise ValueError("Generation evidence cannot mix Candidate identities")

    @property
    def refusals(self) -> Mapping[str, tuple[str, ...]]:
        return MappingProxyType(
            {item.gate: item.refusals for item in self.gate_evidence if item.refusals}
        )

    @property
    def indeterminate_outcomes(self) -> Mapping[str, tuple[str, ...]]:
        return MappingProxyType(
            {
                item.gate: item.indeterminate_outcomes
                for item in self.gate_evidence
                if item.indeterminate_outcomes
            }
        )

    def digest(self) -> str:
        return _digest(
            {
                "generation_id": self.generation_id,
                "candidate_digest": self.candidate.digest(),
                "gate_evidence": [item.as_payload() for item in self.gate_evidence],
                "sealed_at": self.sealed_at.isoformat(),
            }
        )


@dataclass(frozen=True)
class BoundedWorkOrder:
    order_id: str
    result_digest: str
    failure_class: str
    change: BoundedChange
    evidence_basis: tuple[GateEvidenceReference, ...]
    unchanged_controls: tuple[str, ...]
    next_required_gate: str
    proposed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_basis", tuple(self.evidence_basis))
        object.__setattr__(self, "unchanged_controls", tuple(self.unchanged_controls))
        if self.failure_class not in FAILURE_TAXONOMY:
            raise ValueError("a Work Order names one Failure Taxonomy class")
        if not isinstance(self.change, BoundedChange):
            raise TypeError("a Work Order carries exactly one BoundedChange")
        if not all(
            value.strip()
            for value in (
                self.order_id,
                self.result_digest,
                self.next_required_gate,
            )
        ):
            raise ValueError("a Work Order names its result, change, and next gate")
        if self.next_required_gate not in REQUIRED_GATES:
            raise ValueError("a Work Order names a real next required Gate")
        if not self.evidence_basis or not self.unchanged_controls:
            raise ValueError(
                "a Work Order states its evidence basis and unchanged controls"
            )
        if not all(
            isinstance(item, GateEvidenceReference) for item in self.evidence_basis
        ):
            raise TypeError("a Work Order basis contains GateEvidenceReference values")


@dataclass(frozen=True)
class BoundedChange:
    """One deliberately limited modification for the next Generation."""

    kind: str
    target: str
    proposal: str
    bound: str

    def __post_init__(self) -> None:
        if self.kind not in CHANGE_KINDS:
            raise ValueError("a bounded change uses a supported change kind")
        if not all(value.strip() for value in (self.target, self.proposal, self.bound)):
            raise ValueError("a bounded change states one target, proposal, and bound")


class GenerationResultLedger:
    """Append-only gate evidence, Generation seals, then bounded proposals."""

    def __init__(self) -> None:
        self._evidence: dict[tuple[str, str], GateEvidenceReference] = {}
        self._results: dict[str, SealedGenerationResult] = {}
        self._orders: dict[str, BoundedWorkOrder] = {}
        self._orders_by_result: dict[str, BoundedWorkOrder] = {}

    def record_gate_evidence(
        self, evidence: GateEvidenceReference
    ) -> GateEvidenceReference:
        """Record one source-scoped evidence pointer before it enters a Result."""
        key = (evidence.gate, evidence.digest)
        existing = self._evidence.get(key)
        if existing is not None and existing != evidence:
            raise ValueError("a gate evidence digest cannot be rewritten")
        if any(
            item.digest == evidence.digest and item.gate != evidence.gate
            for item in self._evidence.values()
        ):
            raise ValueError("one evidence digest cannot be renamed across sources")
        self._evidence[key] = evidence
        return evidence

    def seal(self, result: SealedGenerationResult) -> SealedGenerationResult:
        if any(
            self._evidence.get((item.gate, item.digest)) != item
            for item in result.gate_evidence
        ):
            raise ValueError("a Generation Result references recorded Gate evidence")
        return self._results.setdefault(result.digest(), result)

    def result_for(self, result_digest: str) -> SealedGenerationResult | None:
        """Read one sealed result without exposing any way to rewrite it."""
        return self._results.get(result_digest)

    def propose(self, order: BoundedWorkOrder) -> BoundedWorkOrder:
        result = self._results.get(order.result_digest)
        if result is None:
            raise ValueError("a Work Order can only follow sealed Generation evidence")
        if order.proposed_at <= result.sealed_at:
            raise ValueError("a Work Order cannot predate its sealed Generation result")
        known_evidence = frozenset(result.gate_evidence)
        if (
            not set(order.evidence_basis).issubset(known_evidence)
            or len(set(order.evidence_basis)) != len(order.evidence_basis)
        ):
            raise ValueError("a Work Order basis names only sealed Generation evidence")
        existing = self._orders.get(order.order_id)
        if existing is not None:
            if existing != order:
                raise ValueError("a Work Order identifier cannot be rewritten")
            return existing
        if order.result_digest in self._orders_by_result:
            raise ValueError("a sealed Generation produces one next Work Order")
        self._orders[order.order_id] = order
        self._orders_by_result[order.result_digest] = order
        return order

    def work_order_for(self, order_id: str) -> BoundedWorkOrder | None:
        """Read one approved-for-review Work Order without mutating its ledger."""
        return self._orders.get(order_id)
