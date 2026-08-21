"""Independent MuJoCo control validation for an Isaac-admitted Candidate.

MuJoCo is intentionally not another rendering of the Isaac scene.  It shares
the frozen replay, skill identity, observation/action schema, and evidence
discipline, while testing only control continuity, joint limits, contacts,
latency, and fault holding.  Its evidence is therefore comparable to Isaac at
the contract boundary without being interchangeable with Isaac or hardware.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, TypeVar

from vegapunk.embodied.episode import QualifiedReplay
from vegapunk.embodied.isaac_campaign import (
    IsaacCampaignEvidence,
    IsaacCampaignEvidenceLedger,
    IsaacGatePolicy,
)
from vegapunk.embodied.promotion import (
    GATE_ISAAC_LAB,
    GATE_MUJOCO,
    GOLDEN_EMBODIMENT,
    GOLDEN_PROMOTION_CONFIGURATION,
    CandidateBundle,
    PromotionLedger,
    PromotionSubmission,
    SealedRejection,
    promote_generation,
)
from vegapunk.operation.target import WholeBodyTarget

MUJOCO_SOURCE = "mujoco"
MUJOCO_VERSION = "mujoco-g1-control-v1"

MUJOCO_OUTCOME_SUCCEEDED = "succeeded"
MUJOCO_OUTCOME_FAILED = "failed"
_MUJOCO_OUTCOMES = frozenset({MUJOCO_OUTCOME_SUCCEEDED, MUJOCO_OUTCOME_FAILED})


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class MujocoControlSurface:
    """The non-visual MuJoCo surface used to cross-check control semantics."""

    surface_id: str
    robot_model: str
    controlled_joint_count: int
    control_frequency_hz: float
    skill_revision_digest: str
    observation_schema_digest: str
    action_schema_digest: str

    def __post_init__(self) -> None:
        if not self.surface_id.strip():
            raise ValueError("a MuJoCo control surface names its build")
        if self.robot_model != "unitree_g1":
            raise ValueError("the MuJoCo control surface represents the Golden G1")
        if self.controlled_joint_count != GOLDEN_EMBODIMENT.action_dim:
            raise ValueError(
                "the MuJoCo surface uses the Golden whole-body action width"
            )
        if self.control_frequency_hz <= 0:
            raise ValueError("the MuJoCo control frequency must be positive")
        if not all(
            value.strip()
            for value in (
                self.skill_revision_digest,
                self.observation_schema_digest,
                self.action_schema_digest,
            )
        ):
            raise ValueError("the MuJoCo surface names the shared control contracts")

    @property
    def includes_visual_scene(self) -> bool:
        """Always false: image realism belongs to Isaac, not this cross-check."""
        return False

    def as_payload(self) -> dict[str, object]:
        return {
            "surface_id": self.surface_id,
            "robot_model": self.robot_model,
            "controlled_joint_count": self.controlled_joint_count,
            "control_frequency_hz": self.control_frequency_hz,
            "skill_revision_digest": self.skill_revision_digest,
            "observation_schema_digest": self.observation_schema_digest,
            "action_schema_digest": self.action_schema_digest,
            "includes_visual_scene": self.includes_visual_scene,
        }

    def digest(self) -> str:
        return _digest(self.as_payload())


@dataclass(frozen=True)
class MujocoRuntimeProvenance:
    source: str
    simulator_version: str
    admission_capable: bool

    def __post_init__(self) -> None:
        if self.source != MUJOCO_SOURCE:
            raise ValueError(
                "MuJoCo evidence is simulator-scoped and never Isaac or real"
            )
        if not self.simulator_version.strip():
            raise ValueError("a MuJoCo runtime names its version")
        if not self.admission_capable:
            raise ValueError(
                "a MuJoCo runtime must state whether it may certify evidence"
            )


@dataclass(frozen=True)
class MujocoRun:
    """The control facts a MuJoCo host observed while consuming one replay."""

    target_sequences: tuple[int, ...]
    max_joint_step_rad: float
    joint_boundary_violation: bool
    contact_anomaly: bool
    observed_latency_steps: int
    fault_detected: bool
    fault_held: bool
    completed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_sequences", tuple(self.target_sequences))
        if not self.target_sequences:
            raise ValueError("a MuJoCo run records every consumed target")
        if self.max_joint_step_rad < 0:
            raise ValueError("a maximum joint step cannot be negative")
        if self.observed_latency_steps < 0:
            raise ValueError("observed MuJoCo latency cannot be negative")


class MujocoRuntime(Protocol):
    """The production seam implemented by a MuJoCo host, not a visual scene."""

    @property
    def provenance(self) -> MujocoRuntimeProvenance:
        """The simulator identity carried into each MuJoCo episode."""

    def run(
        self,
        surface: MujocoControlSurface,
        targets: tuple[WholeBodyTarget, ...],
        *,
        seed: int,
        fault_injected: bool,
    ) -> MujocoRun:
        """Consume targets under one registered nominal or fault-injection case."""


@dataclass(frozen=True)
class MujocoControlPolicy:
    """Pre-registered bounds on one MuJoCo control trajectory."""

    max_joint_step_rad: float
    max_latency_steps: int
    require_fault_hold: bool

    def __post_init__(self) -> None:
        if self.max_joint_step_rad <= 0:
            raise ValueError("the MuJoCo joint-step limit must be positive")
        if self.max_latency_steps < 0:
            raise ValueError("the MuJoCo latency limit cannot be negative")

    def as_payload(self) -> dict[str, object]:
        return {
            "max_joint_step_rad": self.max_joint_step_rad,
            "max_latency_steps": self.max_latency_steps,
            "require_fault_hold": self.require_fault_hold,
        }

    def digest(self) -> str:
        return _digest(self.as_payload())


@dataclass(frozen=True)
class MujocoEpisode:
    """One simulator-scoped, contract-level outcome of a frozen replay."""

    source: str
    simulator_version: str
    surface_digest: str
    replay_digest: str
    seed: int
    target_sequences: tuple[int, ...]
    outcome: str
    findings: tuple[str, ...]
    trace_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_sequences", tuple(self.target_sequences))
        object.__setattr__(self, "findings", tuple(self.findings))
        if self.source != MUJOCO_SOURCE:
            raise ValueError(
                "a MuJoCo episode is simulator-scoped and never Isaac or real"
            )
        if not all(
            value.strip()
            for value in (
                self.simulator_version,
                self.surface_digest,
                self.replay_digest,
                self.trace_digest,
            )
        ):
            raise ValueError(
                "a MuJoCo episode names its runtime, surface, replay, and trace"
            )
        if not self.target_sequences:
            raise ValueError("a MuJoCo episode records WholeBodyTarget sequences")
        if self.outcome not in _MUJOCO_OUTCOMES:
            raise ValueError("a MuJoCo episode has a known contract outcome")
        if self.outcome == MUJOCO_OUTCOME_FAILED and not self.findings:
            raise ValueError(
                "a failed MuJoCo episode records the violated control fact"
            )
        if self.outcome == MUJOCO_OUTCOME_SUCCEEDED and self.findings:
            raise ValueError("a successful MuJoCo episode has no failure findings")

    @property
    def succeeded(self) -> bool:
        return self.outcome == MUJOCO_OUTCOME_SUCCEEDED


class MujocoAdapter:
    """The sole adapter from Qualified Replay to the compact MuJoCo surface."""

    def __init__(self, surface: MujocoControlSurface, runtime: MujocoRuntime) -> None:
        self._surface = surface
        self._runtime = runtime

    @property
    def provenance(self) -> MujocoRuntimeProvenance:
        return self._runtime.provenance

    @property
    def surface(self) -> MujocoControlSurface:
        return self._surface

    def run(
        self,
        replay: QualifiedReplay,
        *,
        seed: int,
        fault_injected: bool,
        policy: MujocoControlPolicy,
    ) -> MujocoEpisode:
        if replay.control_frequency_hz != self._surface.control_frequency_hz:
            raise ValueError(
                "the MuJoCo surface frequency differs from the Qualified Replay"
            )
        if not all(isinstance(target, WholeBodyTarget) for target in replay.targets):
            raise TypeError("MuJoCo consumes WholeBodyTarget values, not commands")
        observed = self._runtime.run(
            self._surface,
            replay.targets,
            seed=seed,
            fault_injected=fault_injected,
        )
        expected_sequences = tuple(target.sequence for target in replay.targets)
        if observed.target_sequences != expected_sequences:
            raise ValueError(
                "MuJoCo runtime did not consume the Qualified Replay targets"
            )

        findings: list[str] = []
        if observed.max_joint_step_rad > policy.max_joint_step_rad:
            findings.append(
                "joint-step continuity exceeded the pre-registered MuJoCo limit"
            )
        if observed.joint_boundary_violation:
            findings.append("MuJoCo observed a joint boundary violation")
        if observed.contact_anomaly:
            findings.append("MuJoCo observed a contact anomaly")
        if observed.observed_latency_steps > policy.max_latency_steps:
            findings.append("MuJoCo observed latency beyond the pre-registered limit")
        if fault_injected and not observed.fault_detected:
            findings.append("MuJoCo did not observe the pre-registered fault injection")
        if (
            policy.require_fault_hold
            and observed.fault_detected
            and not observed.fault_held
        ):
            findings.append("MuJoCo did not hold after its detected fault")
        if not observed.completed:
            findings.append("MuJoCo did not complete the frozen target sequence")
        outcome = MUJOCO_OUTCOME_SUCCEEDED if not findings else MUJOCO_OUTCOME_FAILED
        trace_digest = _digest(
            {
                "surface": self._surface.digest(),
                "replay": replay.digest(),
                "seed": seed,
                "target_sequences": list(observed.target_sequences),
                "max_joint_step_rad": observed.max_joint_step_rad,
                "joint_boundary_violation": observed.joint_boundary_violation,
                "contact_anomaly": observed.contact_anomaly,
                "observed_latency_steps": observed.observed_latency_steps,
                "fault_detected": observed.fault_detected,
                "fault_held": observed.fault_held,
                "fault_injected": fault_injected,
                "completed": observed.completed,
                "outcome": outcome,
            }
        )
        return MujocoEpisode(
            source=self.provenance.source,
            simulator_version=self.provenance.simulator_version,
            surface_digest=self._surface.digest(),
            replay_digest=replay.digest(),
            seed=seed,
            target_sequences=observed.target_sequences,
            outcome=outcome,
            findings=tuple(findings),
            trace_digest=trace_digest,
        )


@dataclass(frozen=True)
class MujocoValidationCase:
    """The Isaac attempt a MuJoCo run must independently cross-check."""

    isaac_attempt_id: str
    seed: int
    fault_injected: bool = False

    def __post_init__(self) -> None:
        if not self.isaac_attempt_id.strip():
            raise ValueError("a MuJoCo validation case names its Isaac attempt")

    def as_payload(self) -> dict[str, object]:
        return {
            "isaac_attempt_id": self.isaac_attempt_id,
            "seed": self.seed,
            "fault_injected": self.fault_injected,
        }


@dataclass(frozen=True)
class SimulatorDisagreementPolicy:
    """The outcome difference allowance, frozen before MuJoCo starts."""

    max_outcome_disagreements: int

    def __post_init__(self) -> None:
        if self.max_outcome_disagreements < 0:
            raise ValueError("a simulator disagreement allowance cannot be negative")

    def as_payload(self) -> dict[str, int]:
        return {"max_outcome_disagreements": self.max_outcome_disagreements}

    def digest(self) -> str:
        return _digest(self.as_payload())

    def decide(self, evidence: MujocoValidationEvidence) -> MujocoGateDecision:
        disagreements = evidence.outcome_disagreement_count
        reasons: tuple[str, ...] = ()
        if disagreements > self.max_outcome_disagreements:
            reasons = (
                (
                    "sealed simulator evidence has "
                    f"{disagreements} contract outcome disagreement(s), above the "
                    "pre-registered allowance of "
                    f"{self.max_outcome_disagreements}"
                ),
            )
        return MujocoGateDecision(
            evidence_digest=evidence.digest(),
            admitted=not reasons,
            blocking_reasons=reasons,
        )


@dataclass(frozen=True)
class MujocoValidationPlan:
    """The complete MuJoCo run set and disagreement rules, fixed before running."""

    validation_id: str
    candidate_digest: str
    skill_revision_digest: str
    replay_digest: str
    isaac_evidence_digest: str
    cases: tuple[MujocoValidationCase, ...]
    control_policy: MujocoControlPolicy
    disagreement_policy: SimulatorDisagreementPolicy

    def __post_init__(self) -> None:
        object.__setattr__(self, "cases", tuple(self.cases))
        if not all(
            value.strip()
            for value in (
                self.validation_id,
                self.candidate_digest,
                self.skill_revision_digest,
                self.replay_digest,
                self.isaac_evidence_digest,
            )
        ):
            raise ValueError("a MuJoCo plan names every frozen input")
        if not self.cases:
            raise ValueError("a MuJoCo plan pre-registers the Isaac attempts it checks")
        if not all(isinstance(case, MujocoValidationCase) for case in self.cases):
            raise TypeError("a MuJoCo plan contains MujocoValidationCase values")
        identifiers = tuple(case.isaac_attempt_id for case in self.cases)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("a MuJoCo plan cannot reuse an Isaac attempt")
        if not any(case.fault_injected for case in self.cases):
            raise ValueError("a MuJoCo plan must pre-register a fault-injection case")
        if not isinstance(self.control_policy, MujocoControlPolicy):
            raise TypeError("a MuJoCo plan carries a MujocoControlPolicy")
        if not isinstance(self.disagreement_policy, SimulatorDisagreementPolicy):
            raise TypeError("a MuJoCo plan carries a SimulatorDisagreementPolicy")

    def as_payload(self) -> dict[str, object]:
        return {
            "validation_id": self.validation_id,
            "candidate_digest": self.candidate_digest,
            "skill_revision_digest": self.skill_revision_digest,
            "replay_digest": self.replay_digest,
            "isaac_evidence_digest": self.isaac_evidence_digest,
            "cases": [case.as_payload() for case in self.cases],
            "control_policy": self.control_policy.as_payload(),
            "disagreement_policy": self.disagreement_policy.as_payload(),
        }

    def digest(self) -> str:
        return _digest(self.as_payload())


@dataclass(frozen=True)
class MujocoValidationAttempt:
    """Comparable Isaac and MuJoCo outcomes for one seed and target sequence."""

    isaac_attempt_id: str
    isaac_succeeded: bool
    episode: MujocoEpisode

    def __post_init__(self) -> None:
        if not self.isaac_attempt_id.strip():
            raise ValueError("a MuJoCo validation attempt names its Isaac attempt")
        if not isinstance(self.episode, MujocoEpisode):
            raise TypeError("a MuJoCo validation attempt records a MuJoCo episode")

    @property
    def outcome_disagrees(self) -> bool:
        return self.isaac_succeeded != self.episode.succeeded

    def as_payload(self) -> dict[str, object]:
        return {
            "isaac_attempt_id": self.isaac_attempt_id,
            "isaac_succeeded": self.isaac_succeeded,
            "mujoco_outcome": self.episode.outcome,
            "mujoco_trace_digest": self.episode.trace_digest,
        }


@dataclass(frozen=True)
class MujocoValidationEvidence:
    """Sealed MuJoCo-only evidence; it cannot amend Isaac or real-world records."""

    plan_digest: str
    validation_id: str
    candidate_digest: str
    replay_digest: str
    isaac_evidence_digest: str
    source: str
    simulator_version: str
    surface_digest: str
    disagreement_policy: SimulatorDisagreementPolicy
    attempts: tuple[MujocoValidationAttempt, ...]
    recorded_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempts", tuple(self.attempts))
        if not all(
            value.strip()
            for value in (
                self.plan_digest,
                self.validation_id,
                self.candidate_digest,
                self.replay_digest,
                self.isaac_evidence_digest,
                self.simulator_version,
                self.surface_digest,
            )
        ):
            raise ValueError("MuJoCo evidence names every frozen input")
        if self.source != MUJOCO_SOURCE:
            raise ValueError(
                "MuJoCo evidence is simulator-scoped and never Isaac or real"
            )
        if not isinstance(self.disagreement_policy, SimulatorDisagreementPolicy):
            raise TypeError("MuJoCo evidence retains its pre-registered policy")
        if not self.attempts:
            raise ValueError("MuJoCo evidence needs every planned validation attempt")
        if not all(isinstance(item, MujocoValidationAttempt) for item in self.attempts):
            raise TypeError("MuJoCo evidence contains MujocoValidationAttempt values")
        if any(item.episode.source != self.source for item in self.attempts):
            raise ValueError("MuJoCo evidence mixes simulator sources")
        if any(
            item.episode.simulator_version != self.simulator_version
            for item in self.attempts
        ):
            raise ValueError("MuJoCo evidence mixes simulator versions")
        if any(
            item.episode.surface_digest != self.surface_digest for item in self.attempts
        ):
            raise ValueError("MuJoCo evidence mixes control surfaces")

    @property
    def outcome_disagreement_count(self) -> int:
        return sum(item.outcome_disagrees for item in self.attempts)

    def as_payload(self) -> dict[str, object]:
        return {
            "plan_digest": self.plan_digest,
            "validation_id": self.validation_id,
            "candidate_digest": self.candidate_digest,
            "replay_digest": self.replay_digest,
            "isaac_evidence_digest": self.isaac_evidence_digest,
            "source": self.source,
            "simulator_version": self.simulator_version,
            "surface_digest": self.surface_digest,
            "disagreement_policy": self.disagreement_policy.as_payload(),
            "attempts": [item.as_payload() for item in self.attempts],
            "recorded_at": self.recorded_at.isoformat(),
        }

    def digest(self) -> str:
        return _digest(self.as_payload())


@dataclass(frozen=True)
class MujocoGateDecision:
    evidence_digest: str
    admitted: bool
    blocking_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "blocking_reasons", tuple(self.blocking_reasons))
        if not self.evidence_digest.strip():
            raise ValueError("a MuJoCo Gate decision names its sealed evidence")
        if self.admitted and self.blocking_reasons:
            raise ValueError("an admitted MuJoCo Gate decision has no blockers")
        if not self.admitted and not self.blocking_reasons:
            raise ValueError("a rejected MuJoCo Gate decision names its blockers")


class MujocoEvidenceLedger:
    """An append-only ledger separate from Isaac and real-world evidence."""

    def __init__(self) -> None:
        self._evidence: dict[str, MujocoValidationEvidence] = {}

    def seal(self, evidence: MujocoValidationEvidence) -> MujocoValidationEvidence:
        if not isinstance(evidence, MujocoValidationEvidence):
            raise TypeError("the MuJoCo ledger accepts MuJoCo evidence only")
        return self._evidence.setdefault(evidence.digest(), evidence)

    def evidence_for(self, digest: str) -> MujocoValidationEvidence | None:
        return self._evidence.get(digest)

    def evidence(self) -> tuple[MujocoValidationEvidence, ...]:
        return tuple(self._evidence.values())

    def decide(self, evidence: MujocoValidationEvidence) -> MujocoGateDecision:
        if self.evidence_for(evidence.digest()) is None:
            raise ValueError("MuJoCo Gate decisions require sealed MuJoCo evidence")
        return evidence.disagreement_policy.decide(evidence)


def _validate_shared_contracts(
    plan: MujocoValidationPlan,
    *,
    candidate: CandidateBundle,
    skill_revision_digest: str,
    replay: QualifiedReplay,
    isaac_evidence: IsaacCampaignEvidence,
    isaac_ledger: IsaacCampaignEvidenceLedger,
    isaac_policy: IsaacGatePolicy,
    adapter: MujocoAdapter,
) -> None:
    if candidate.embodiment_digest != GOLDEN_EMBODIMENT.digest():
        raise ValueError("MuJoCo validation admits only the Golden embodiment")
    if candidate.configuration_digest != GOLDEN_PROMOTION_CONFIGURATION.digest():
        raise ValueError("MuJoCo validation admits only the Golden configuration")
    if (
        candidate.action_schema_digest
        != GOLDEN_PROMOTION_CONFIGURATION.action_protocol_digest
    ):
        raise ValueError("the Candidate does not use the WholeBodyTarget contract")
    if (
        candidate.configuration_digest
        != replay.initial_state_envelope.configuration_digest
    ):
        raise ValueError("the Candidate and replay name different configurations")
    if isaac_ledger.evidence_for(isaac_evidence.digest()) is None:
        raise ValueError("MuJoCo validation requires sealed Isaac evidence")
    if not isaac_ledger.decide(isaac_evidence, isaac_policy).admitted:
        raise ValueError("MuJoCo validation requires an Isaac-admitted Candidate")
    if (
        plan.candidate_digest != candidate.digest()
        or plan.skill_revision_digest != skill_revision_digest
        or plan.replay_digest != replay.digest()
        or plan.isaac_evidence_digest != isaac_evidence.digest()
    ):
        raise ValueError("the MuJoCo plan names different frozen inputs")
    surface = adapter.surface
    if surface.skill_revision_digest != skill_revision_digest:
        raise ValueError("the MuJoCo surface names a different Skill revision")
    if surface.observation_schema_digest != candidate.observation_schema_digest:
        raise ValueError("the MuJoCo surface names a different observation contract")
    if surface.action_schema_digest != candidate.action_schema_digest:
        raise ValueError("the MuJoCo surface names a different action contract")
    provenance = adapter.provenance
    if not provenance.admission_capable or provenance.source != MUJOCO_SOURCE:
        raise ValueError("MuJoCo evidence requires a MuJoCo host runtime")

    expected_cases = tuple(
        (attempt.attempt_id, attempt.seed) for attempt in isaac_evidence.attempts
    )
    planned_cases = tuple((case.isaac_attempt_id, case.seed) for case in plan.cases)
    if planned_cases != expected_cases:
        raise ValueError(
            "the MuJoCo plan must pre-register every Isaac attempt exactly"
        )


def execute_mujoco_validation(
    plan: MujocoValidationPlan,
    *,
    candidate: CandidateBundle,
    skill_revision_digest: str,
    replay: QualifiedReplay,
    isaac_evidence: IsaacCampaignEvidence,
    isaac_ledger: IsaacCampaignEvidenceLedger,
    isaac_policy: IsaacGatePolicy,
    adapter: MujocoAdapter,
    ledger: MujocoEvidenceLedger,
    now: datetime,
) -> MujocoValidationEvidence:
    """Run each pre-registered cross-check and seal MuJoCo-only evidence."""
    _validate_shared_contracts(
        plan,
        candidate=candidate,
        skill_revision_digest=skill_revision_digest,
        replay=replay,
        isaac_evidence=isaac_evidence,
        isaac_ledger=isaac_ledger,
        isaac_policy=isaac_policy,
        adapter=adapter,
    )

    attempts: list[MujocoValidationAttempt] = []
    expected_sequences = tuple(target.sequence for target in replay.targets)
    for case, isaac_attempt in zip(plan.cases, isaac_evidence.attempts, strict=True):
        if isaac_attempt.trajectory.target_sequences != expected_sequences:
            raise ValueError(
                "Isaac evidence did not consume the Qualified Replay targets"
            )
        episode = adapter.run(
            replay,
            seed=case.seed,
            fault_injected=case.fault_injected,
            policy=plan.control_policy,
        )
        if episode.seed != case.seed or episode.target_sequences != expected_sequences:
            raise ValueError(
                "MuJoCo evidence did not consume the matching replay attempt"
            )
        attempts.append(
            MujocoValidationAttempt(
                isaac_attempt_id=case.isaac_attempt_id,
                isaac_succeeded=isaac_attempt.trajectory.succeeded,
                episode=episode,
            )
        )

    return ledger.seal(
        MujocoValidationEvidence(
            plan_digest=plan.digest(),
            validation_id=plan.validation_id,
            candidate_digest=candidate.digest(),
            replay_digest=replay.digest(),
            isaac_evidence_digest=isaac_evidence.digest(),
            source=adapter.provenance.source,
            simulator_version=adapter.provenance.simulator_version,
            surface_digest=adapter.surface.digest(),
            disagreement_policy=plan.disagreement_policy,
            attempts=tuple(attempts),
            recorded_at=now,
        )
    )


ResultT = TypeVar("ResultT")


def promote_through_mujoco_gate(
    submission: PromotionSubmission,
    *,
    plan: MujocoValidationPlan,
    replay: QualifiedReplay,
    isaac_evidence: IsaacCampaignEvidence,
    isaac_ledger: IsaacCampaignEvidenceLedger,
    isaac_policy: IsaacGatePolicy,
    adapter: MujocoAdapter,
    evidence_ledger: MujocoEvidenceLedger,
    promotion_ledger: PromotionLedger,
    execute_later: Callable[[PromotionSubmission], ResultT],
    now: datetime,
) -> ResultT | SealedRejection:
    """Reject at MuJoCo before Shadow or hardware can be invoked."""

    def reject(
        valid: PromotionSubmission,
        gate: str,
        reason: str | tuple[str, ...],
    ) -> SealedRejection:
        reasons = (reason,) if isinstance(reason, str) else reason
        return promotion_ledger.seal_rejection(
            SealedRejection(
                promotion_digest=valid.digest(),
                failed_gate=gate,
                reasons=reasons,
                input_identities=valid.identities(),
                sealed_at=now,
            )
        )

    def execute(valid: PromotionSubmission) -> ResultT | SealedRejection:
        candidate = valid.candidate
        skill = valid.skill
        assert candidate is not None
        assert skill is not None
        try:
            isaac_decision = isaac_ledger.decide(isaac_evidence, isaac_policy)
        except ValueError as error:
            return reject(
                valid,
                GATE_ISAAC_LAB,
                f"Isaac Gate could not read sealed evidence: {error}",
            )
        if not isaac_decision.admitted:
            return reject(valid, GATE_ISAAC_LAB, isaac_decision.blocking_reasons)
        try:
            evidence = execute_mujoco_validation(
                plan,
                candidate=candidate,
                skill_revision_digest=skill.digest(),
                replay=replay,
                isaac_evidence=isaac_evidence,
                isaac_ledger=isaac_ledger,
                isaac_policy=isaac_policy,
                adapter=adapter,
                ledger=evidence_ledger,
                now=now,
            )
            decision = evidence_ledger.decide(evidence)
        except ValueError as error:
            return reject(
                valid,
                GATE_MUJOCO,
                f"MuJoCo Gate could not seal valid evidence: {error}",
            )
        if not decision.admitted:
            return reject(valid, GATE_MUJOCO, decision.blocking_reasons)
        return execute_later(valid)

    return promote_generation(
        submission,
        ledger=promotion_ledger,
        execute=execute,
        now=now,
    )
