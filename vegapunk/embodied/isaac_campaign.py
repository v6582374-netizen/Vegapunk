"""A sealed Isaac Lab perturbation campaign for one frozen Candidate.

The Golden Scene remains the common task contract.  This module adds only the
robustness question that a nominal replay cannot answer: which pre-registered
worlds did the Candidate see, what happened in each one, and whether any
result makes a later stage unsafe to start.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Protocol, TypeVar

from vegapunk.embodied.episode import QualifiedReplay
from vegapunk.embodied.isaac import (
    GOLDEN_ISAAC_SCENE,
    ISAAC_LAB_SOURCE,
    IsaacLabEpisode,
    IsaacRuntimeProvenance,
)
from vegapunk.embodied.promotion import (
    GATE_ISAAC_LAB,
    GOLDEN_EMBODIMENT,
    GOLDEN_PROMOTION_CONFIGURATION,
    CandidateBundle,
    PromotionLedger,
    PromotionSubmission,
    SealedRejection,
    promote_generation,
)

CALIBRATED_FACT = "calibrated_fact"
UNVERIFIED_PERTURBATION_AXIS = "unverified_perturbation_axis"
_PERTURBATION_CLASSIFICATIONS = frozenset(
    {CALIBRATED_FACT, UNVERIFIED_PERTURBATION_AXIS}
)

PERTURBATION_OBJECT_INITIAL_STATE = "object_initial_state"
PERTURBATION_FRICTION = "friction"
PERTURBATION_MASS = "mass"
PERTURBATION_LIGHTING = "lighting"
PERTURBATION_CAMERA_CALIBRATION = "camera_calibration"
PERTURBATION_SENSOR_NOISE = "sensor_noise"
PERTURBATION_LATENCY = "latency"
REQUIRED_PERTURBATION_PARAMETERS = frozenset(
    {
        PERTURBATION_OBJECT_INITIAL_STATE,
        PERTURBATION_FRICTION,
        PERTURBATION_MASS,
        PERTURBATION_LIGHTING,
        PERTURBATION_CAMERA_CALIBRATION,
        PERTURBATION_SENSOR_NOISE,
        PERTURBATION_LATENCY,
    }
)
_REQUIRED_VALUE_COMPONENTS = {
    PERTURBATION_OBJECT_INITIAL_STATE: frozenset(
        {"x_m", "y_m", "z_m", "roll_rad", "pitch_rad", "yaw_rad"}
    ),
    PERTURBATION_FRICTION: frozenset({"coefficient"}),
    PERTURBATION_MASS: frozenset({"mass_kg"}),
    PERTURBATION_LIGHTING: frozenset({"illuminance_lux"}),
    PERTURBATION_CAMERA_CALIBRATION: frozenset(
        {
            "fx_px",
            "fy_px",
            "cx_px",
            "cy_px",
            "x_m",
            "y_m",
            "z_m",
            "roll_rad",
            "pitch_rad",
            "yaw_rad",
        }
    ),
    PERTURBATION_SENSOR_NOISE: frozenset({"standard_deviation"}),
    PERTURBATION_LATENCY: frozenset({"delay_ms"}),
}

ISAAC_ATTEMPT_SUCCEEDED = "succeeded"
ISAAC_ATTEMPT_SAFETY_VIOLATION = "safety_violation"
ISAAC_ATTEMPT_HARD_FAILURE = "hard_failure"
ISAAC_ATTEMPT_INDETERMINATE = "indeterminate"
_ATTEMPT_VERDICTS = frozenset(
    {
        ISAAC_ATTEMPT_SUCCEEDED,
        ISAAC_ATTEMPT_SAFETY_VIOLATION,
        ISAAC_ATTEMPT_HARD_FAILURE,
        ISAAC_ATTEMPT_INDETERMINATE,
    }
)


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class IsaacPerturbation:
    """One named world quantity and whether its value is established or probed."""

    parameter: str
    classification: str
    value: Mapping[str, float]
    unit: str

    def __post_init__(self) -> None:
        if self.parameter not in REQUIRED_PERTURBATION_PARAMETERS:
            raise ValueError(f"unknown Isaac perturbation parameter {self.parameter!r}")
        object.__setattr__(self, "value", MappingProxyType(dict(self.value)))
        if self.classification not in _PERTURBATION_CLASSIFICATIONS:
            raise ValueError(
                "an Isaac perturbation is either a calibrated fact or an unverified axis"
            )
        if set(self.value) != _REQUIRED_VALUE_COMPONENTS[self.parameter]:
            raise ValueError(
                f"Isaac perturbation {self.parameter!r} needs its complete named value"
            )
        if not all(math.isfinite(component) for component in self.value.values()):
            raise ValueError("an Isaac perturbation value must be finite")
        if not self.unit.strip():
            raise ValueError("an Isaac perturbation must declare its unit")

    def as_payload(self) -> dict[str, object]:
        return {
            "parameter": self.parameter,
            "classification": self.classification,
            "value": dict(sorted(self.value.items())),
            "unit": self.unit,
        }


@dataclass(frozen=True)
class IsaacCampaignCondition:
    """One complete, pre-registered simulated world and its independent seed."""

    condition_id: str
    seed: int
    perturbations: tuple[IsaacPerturbation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "perturbations", tuple(self.perturbations))
        if not self.condition_id.strip():
            raise ValueError("an Isaac campaign condition needs an identity")
        if not self.perturbations:
            raise ValueError("an Isaac campaign condition needs perturbations")
        if not all(isinstance(item, IsaacPerturbation) for item in self.perturbations):
            raise TypeError(
                "an Isaac campaign condition contains IsaacPerturbation values"
            )
        names = self.parameter_names
        if set(names) != REQUIRED_PERTURBATION_PARAMETERS or len(names) != len(
            REQUIRED_PERTURBATION_PARAMETERS
        ):
            raise ValueError(
                "each Isaac campaign condition must declare object initial state, "
                "friction, mass, lighting, camera calibration, sensor noise, and latency exactly once"
            )

    @property
    def parameter_names(self) -> tuple[str, ...]:
        return tuple(item.parameter for item in self.perturbations)

    def as_payload(self) -> dict[str, object]:
        return {
            "condition_id": self.condition_id,
            "seed": self.seed,
            "perturbations": [item.as_payload() for item in self.perturbations],
        }

    def digest(self) -> str:
        return _digest(self.as_payload())


@dataclass(frozen=True)
class IsaacCampaignPlan:
    """The whole registered world set for a Candidate and Qualified Replay."""

    campaign_id: str
    candidate_digest: str
    replay_digest: str
    conditions: tuple[IsaacCampaignCondition, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "conditions", tuple(self.conditions))
        if not all(
            value.strip()
            for value in (self.campaign_id, self.candidate_digest, self.replay_digest)
        ):
            raise ValueError(
                "an Isaac campaign plan names its campaign, Candidate, and replay"
            )
        if not self.conditions:
            raise ValueError("an Isaac campaign plan must pre-register conditions")
        if not all(
            isinstance(item, IsaacCampaignCondition) for item in self.conditions
        ):
            raise TypeError(
                "an Isaac campaign plan contains IsaacCampaignCondition values"
            )
        identifiers = tuple(item.condition_id for item in self.conditions)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("an Isaac campaign plan cannot reuse a condition identity")
        seeds = tuple(item.seed for item in self.conditions)
        if len(seeds) != len(set(seeds)):
            raise ValueError("each Isaac campaign attempt requires its own seed")

    def as_payload(self) -> dict[str, object]:
        return {
            "campaign_id": self.campaign_id,
            "candidate_digest": self.candidate_digest,
            "replay_digest": self.replay_digest,
            "conditions": [item.as_payload() for item in self.conditions],
        }

    def digest(self) -> str:
        return _digest(self.as_payload())


@dataclass(frozen=True)
class IsaacCampaignResult:
    """A host's classified result for one perturbed Isaac trajectory."""

    trajectory: IsaacLabEpisode
    applied_condition_digest: str
    executed_target_sequences: tuple[int, ...]
    verdict: str
    detail: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "executed_target_sequences", tuple(self.executed_target_sequences)
        )
        if not isinstance(self.trajectory, IsaacLabEpisode):
            raise TypeError("an Isaac campaign result must retain an Isaac trajectory")
        if not self.applied_condition_digest.strip():
            raise ValueError(
                "an Isaac campaign result carries its applied condition receipt"
            )
        if not self.executed_target_sequences:
            raise ValueError("an Isaac campaign result records every consumed target")
        if self.verdict not in _ATTEMPT_VERDICTS:
            raise ValueError("an Isaac campaign result has an unknown verdict")
        if not self.detail.strip():
            raise ValueError(
                "an Isaac campaign result records why it received its verdict"
            )
        if (self.verdict == ISAAC_ATTEMPT_SUCCEEDED) != self.trajectory.succeeded:
            raise ValueError(
                "a successful campaign verdict must match the trajectory verdict"
            )


class IsaacCampaignRuntime(Protocol):
    """The host seam that applies a registered condition to the Golden Scene."""

    @property
    def provenance(self) -> IsaacRuntimeProvenance:
        """The Isaac Lab host identity that may certify campaign evidence."""

    def run(
        self,
        replay: QualifiedReplay,
        *,
        condition: IsaacCampaignCondition,
        seed: int,
    ) -> IsaacCampaignResult:
        """Run the frozen replay in exactly one registered condition."""


@dataclass(frozen=True)
class IsaacCampaignAttempt:
    """An immutable link from a pre-registered condition to its trajectory."""

    attempt_id: str
    candidate_digest: str
    replay_digest: str
    seed: int
    condition_id: str
    condition_digest: str
    trajectory: IsaacLabEpisode
    verdict: str
    detail: str

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.attempt_id,
                self.candidate_digest,
                self.replay_digest,
                self.condition_id,
                self.condition_digest,
                self.detail,
            )
        ):
            raise ValueError(
                "an Isaac attempt names its identity, condition, and result"
            )
        if not isinstance(self.trajectory, IsaacLabEpisode):
            raise TypeError("an Isaac attempt records an Isaac trajectory")
        if self.trajectory.seed != self.seed:
            raise ValueError("an Isaac attempt seed must match its trajectory")
        if self.trajectory.replay_digest != self.replay_digest:
            raise ValueError("an Isaac attempt trajectory names another replay")
        if self.verdict not in _ATTEMPT_VERDICTS:
            raise ValueError("an Isaac attempt has an unknown verdict")

    def as_payload(self) -> dict[str, object]:
        return {
            "attempt_id": self.attempt_id,
            "candidate_digest": self.candidate_digest,
            "replay_digest": self.replay_digest,
            "seed": self.seed,
            "condition_id": self.condition_id,
            "condition_digest": self.condition_digest,
            "trajectory_digest": self.trajectory.trace_digest,
            "verdict": self.verdict,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class IsaacCampaignEvidence:
    """The sealed, simulator-scoped result set used by the Isaac Gate."""

    campaign_digest: str
    campaign_id: str
    candidate_digest: str
    replay_digest: str
    source: str
    simulator_version: str
    scene_digest: str
    attempts: tuple[IsaacCampaignAttempt, ...]
    recorded_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempts", tuple(self.attempts))
        if not all(
            value.strip()
            for value in (
                self.campaign_digest,
                self.campaign_id,
                self.candidate_digest,
                self.replay_digest,
                self.simulator_version,
                self.scene_digest,
            )
        ):
            raise ValueError("Isaac campaign evidence names every frozen input")
        if self.source != ISAAC_LAB_SOURCE:
            raise ValueError(
                "Isaac campaign evidence is simulator-scoped and never real"
            )
        if not self.attempts:
            raise ValueError("Isaac campaign evidence needs every attempted condition")
        if not all(isinstance(item, IsaacCampaignAttempt) for item in self.attempts):
            raise TypeError(
                "Isaac campaign evidence contains IsaacCampaignAttempt values"
            )
        if any(
            item.candidate_digest != self.candidate_digest for item in self.attempts
        ):
            raise ValueError("an Isaac campaign attempt names another Candidate")
        if any(item.replay_digest != self.replay_digest for item in self.attempts):
            raise ValueError("an Isaac campaign attempt names another replay")
        if any(item.trajectory.source != self.source for item in self.attempts):
            raise ValueError("an Isaac campaign mixes simulator sources")
        if any(
            item.trajectory.simulator_version != self.simulator_version
            for item in self.attempts
        ):
            raise ValueError("an Isaac campaign mixes simulator versions")
        if any(
            item.trajectory.scene_digest != self.scene_digest for item in self.attempts
        ):
            raise ValueError("an Isaac campaign mixes scenes")

    @property
    def success_count(self) -> int:
        return sum(item.verdict == ISAAC_ATTEMPT_SUCCEEDED for item in self.attempts)

    @property
    def safety_violation_count(self) -> int:
        return sum(
            item.verdict == ISAAC_ATTEMPT_SAFETY_VIOLATION for item in self.attempts
        )

    @property
    def hard_failure_count(self) -> int:
        return sum(item.verdict == ISAAC_ATTEMPT_HARD_FAILURE for item in self.attempts)

    @property
    def indeterminate_count(self) -> int:
        return sum(
            item.verdict == ISAAC_ATTEMPT_INDETERMINATE for item in self.attempts
        )

    @property
    def success_rate(self) -> float:
        return self.success_count / len(self.attempts)

    def as_payload(self) -> dict[str, object]:
        return {
            "campaign_digest": self.campaign_digest,
            "campaign_id": self.campaign_id,
            "candidate_digest": self.candidate_digest,
            "replay_digest": self.replay_digest,
            "source": self.source,
            "simulator_version": self.simulator_version,
            "scene_digest": self.scene_digest,
            "attempts": [item.as_payload() for item in self.attempts],
            "recorded_at": self.recorded_at.isoformat(),
        }

    def digest(self) -> str:
        return _digest(self.as_payload())


@dataclass(frozen=True)
class IsaacGateDecision:
    evidence_digest: str
    admitted: bool
    blocking_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "blocking_reasons", tuple(self.blocking_reasons))
        if not self.evidence_digest.strip():
            raise ValueError("an Isaac Gate decision names the sealed evidence")
        if self.admitted and self.blocking_reasons:
            raise ValueError("an admitted Isaac Gate decision has no blocking reasons")
        if not self.admitted and not self.blocking_reasons:
            raise ValueError("a rejected Isaac Gate decision names its blockers")


@dataclass(frozen=True)
class IsaacGatePolicy:
    """A policy in which the success rate never washes out a dangerous run."""

    min_success_rate: float

    def __post_init__(self) -> None:
        if not 0.0 < self.min_success_rate <= 1.0:
            raise ValueError("the Isaac Gate minimum success rate must be in (0, 1]")

    def decide(self, evidence: IsaacCampaignEvidence) -> IsaacGateDecision:
        reasons: list[str] = []
        if evidence.safety_violation_count:
            reasons.append(
                f"sealed Isaac evidence contains {evidence.safety_violation_count} safety violation attempt(s)"
            )
        if evidence.hard_failure_count:
            reasons.append(
                f"sealed Isaac evidence contains {evidence.hard_failure_count} hard failure attempt(s)"
            )
        if evidence.indeterminate_count:
            reasons.append(
                f"sealed Isaac evidence contains {evidence.indeterminate_count} indeterminate attempt(s)"
            )
        if evidence.success_rate < self.min_success_rate:
            reasons.append(
                "sealed Isaac success rate "
                f"{evidence.success_rate:.1%} is below the required {self.min_success_rate:.1%}"
            )
        return IsaacGateDecision(
            evidence_digest=evidence.digest(),
            admitted=not reasons,
            blocking_reasons=tuple(reasons),
        )


class IsaacCampaignEvidenceLedger:
    """Append-only campaign evidence, kept outside real-world evidence stores."""

    def __init__(self) -> None:
        self._evidence: dict[str, IsaacCampaignEvidence] = {}

    def seal(self, evidence: IsaacCampaignEvidence) -> IsaacCampaignEvidence:
        return self._evidence.setdefault(evidence.digest(), evidence)

    def evidence_for(self, digest: str) -> IsaacCampaignEvidence | None:
        return self._evidence.get(digest)

    def evidence(self) -> tuple[IsaacCampaignEvidence, ...]:
        return tuple(self._evidence.values())

    def decide(
        self,
        evidence: IsaacCampaignEvidence,
        policy: IsaacGatePolicy,
    ) -> IsaacGateDecision:
        if self.evidence_for(evidence.digest()) is None:
            raise ValueError("Isaac Gate decisions require sealed campaign evidence")
        return policy.decide(evidence)


def execute_isaac_campaign(
    campaign: IsaacCampaignPlan,
    *,
    candidate: CandidateBundle,
    replay: QualifiedReplay,
    runtime: IsaacCampaignRuntime,
    ledger: IsaacCampaignEvidenceLedger,
    now: datetime,
) -> IsaacCampaignEvidence:
    """Run every registered condition and seal its complete simulator evidence."""
    replay_digest = replay.digest()
    if candidate.embodiment_digest != GOLDEN_EMBODIMENT.digest():
        raise ValueError("Isaac campaign admits only the Golden embodiment")
    if candidate.configuration_digest != GOLDEN_PROMOTION_CONFIGURATION.digest():
        raise ValueError("Isaac campaign admits only the Golden configuration")
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
    if campaign.candidate_digest != candidate.digest():
        raise ValueError("the Isaac campaign names a different Candidate")
    if campaign.replay_digest != replay_digest:
        raise ValueError("the Isaac campaign names a different Qualified Replay")
    provenance = runtime.provenance
    if not provenance.admission_capable or provenance.source != ISAAC_LAB_SOURCE:
        raise ValueError("Isaac campaign evidence requires an Isaac Lab host runtime")

    attempts: list[IsaacCampaignAttempt] = []
    for condition in campaign.conditions:
        result = runtime.run(replay, condition=condition, seed=condition.seed)
        trajectory = result.trajectory
        expected_sequences = tuple(target.sequence for target in replay.targets)
        if result.applied_condition_digest != condition.digest():
            raise ValueError("Isaac campaign condition receipt differs from its plan")
        if result.executed_target_sequences != expected_sequences:
            raise ValueError(
                "Isaac campaign receipt did not consume the Qualified Replay targets"
            )
        if trajectory.target_sequences != expected_sequences:
            raise ValueError(
                "Isaac campaign trajectory did not consume the Qualified Replay targets"
            )
        if trajectory.source != provenance.source:
            raise ValueError("Isaac campaign trajectory source differs from its host")
        if trajectory.simulator_version != provenance.simulator_version:
            raise ValueError("Isaac campaign trajectory version differs from its host")
        if trajectory.scene_digest != GOLDEN_ISAAC_SCENE.digest():
            raise ValueError("Isaac campaign trajectories must use the Golden Scene")
        attempts.append(
            IsaacCampaignAttempt(
                attempt_id=f"{campaign.campaign_id}:{condition.condition_id}",
                candidate_digest=candidate.digest(),
                replay_digest=replay_digest,
                seed=condition.seed,
                condition_id=condition.condition_id,
                condition_digest=condition.digest(),
                trajectory=trajectory,
                verdict=result.verdict,
                detail=result.detail,
            )
        )

    return ledger.seal(
        IsaacCampaignEvidence(
            campaign_digest=campaign.digest(),
            campaign_id=campaign.campaign_id,
            candidate_digest=candidate.digest(),
            replay_digest=replay_digest,
            source=provenance.source,
            simulator_version=provenance.simulator_version,
            scene_digest=GOLDEN_ISAAC_SCENE.digest(),
            attempts=tuple(attempts),
            recorded_at=now,
        )
    )


ResultT = TypeVar("ResultT")


def promote_through_isaac_gate(
    submission: PromotionSubmission,
    *,
    campaign: IsaacCampaignPlan,
    replay: QualifiedReplay,
    runtime: IsaacCampaignRuntime,
    evidence_ledger: IsaacCampaignEvidenceLedger,
    gate_policy: IsaacGatePolicy,
    promotion_ledger: PromotionLedger,
    execute_later: Callable[[PromotionSubmission], ResultT],
    now: datetime,
) -> ResultT | SealedRejection:
    """Stop the promotion at Isaac on rejection; only an admission reaches later work."""

    def execute(valid: PromotionSubmission) -> ResultT | SealedRejection:
        candidate = valid.candidate
        assert candidate is not None
        try:
            evidence = execute_isaac_campaign(
                campaign,
                candidate=candidate,
                replay=replay,
                runtime=runtime,
                ledger=evidence_ledger,
                now=now,
            )
            decision = evidence_ledger.decide(evidence, gate_policy)
        except ValueError as error:
            return promotion_ledger.seal_rejection(
                SealedRejection(
                    promotion_digest=valid.digest(),
                    failed_gate=GATE_ISAAC_LAB,
                    reasons=(f"Isaac Gate could not seal valid evidence: {error}",),
                    input_identities=valid.identities(),
                    sealed_at=now,
                )
            )
        if not decision.admitted:
            return promotion_ledger.seal_rejection(
                SealedRejection(
                    promotion_digest=valid.digest(),
                    failed_gate=GATE_ISAAC_LAB,
                    reasons=decision.blocking_reasons,
                    input_identities=valid.identities(),
                    sealed_at=now,
                )
            )
        return execute_later(valid)

    return promote_generation(
        submission,
        ledger=promotion_ledger,
        execute=execute,
        now=now,
    )
