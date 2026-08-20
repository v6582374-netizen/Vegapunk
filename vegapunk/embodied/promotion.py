"""The sole public contract gate for one Generation promotion attempt."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import TypeVar

from vegapunk.embodied.embodiment import EmbodimentProfile
from vegapunk.embodied.skill import PhysicalSkill

GOLDEN_SKILL_ID = "golden_instrument_operation_loop"
GOLDEN_INSTRUMENT_OPERATION_STEPS = (
    "open_lid",
    "pick_up_cup",
    "tilt_cup",
    "return_cup",
    "close_lid",
)

GATE_CONTRACT_VALIDATION = "contract_validation"
GATE_OFFLINE_REPLAY = "offline_replay"
GATE_ISAAC_LAB = "isaac_lab"
GATE_MUJOCO = "mujoco"
GATE_OBSERVATION_SHADOW = "observation_shadow"
GATE_HARDWARE_APPROVAL = "hardware_approval"
GATE_HARDWARE_PILOT = "hardware_pilot"
GATE_EVIDENCE_SEALING = "evidence_sealing"

PROMOTION_GATE_ORDER = (
    GATE_CONTRACT_VALIDATION,
    GATE_OFFLINE_REPLAY,
    GATE_ISAAC_LAB,
    GATE_MUJOCO,
    GATE_OBSERVATION_SHADOW,
    GATE_HARDWARE_APPROVAL,
    GATE_HARDWARE_PILOT,
    GATE_EVIDENCE_SEALING,
)


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class PromotionConfiguration:
    configuration_id: str
    embodiment_digest: str
    observation_schema_digest: str
    action_protocol_digest: str
    independent_witness_digest: str
    calibration_digest: str
    isaac_lab_config_digest: str
    mujoco_config_digest: str

    def digest(self) -> str:
        return _digest(
            {
                "configuration_id": self.configuration_id,
                "embodiment_digest": self.embodiment_digest,
                "observation_schema_digest": self.observation_schema_digest,
                "action_protocol_digest": self.action_protocol_digest,
                "independent_witness_digest": self.independent_witness_digest,
                "calibration_digest": self.calibration_digest,
                "isaac_lab_config_digest": self.isaac_lab_config_digest,
                "mujoco_config_digest": self.mujoco_config_digest,
            }
        )


@dataclass(frozen=True)
class CandidateBundle:
    candidate_id: str
    policy_artifact_digest: str
    data_manifest_digest: str
    training_recipe_digest: str
    observation_schema_digest: str
    action_schema_digest: str
    skill_version_id: str
    skill_contract_digest: str
    embodiment_digest: str
    configuration_digest: str

    def digest(self) -> str:
        return _digest(
            {
                "candidate_id": self.candidate_id,
                "policy_artifact_digest": self.policy_artifact_digest,
                "data_manifest_digest": self.data_manifest_digest,
                "training_recipe_digest": self.training_recipe_digest,
                "observation_schema_digest": self.observation_schema_digest,
                "action_schema_digest": self.action_schema_digest,
                "skill_version_id": self.skill_version_id,
                "skill_contract_digest": self.skill_contract_digest,
                "embodiment_digest": self.embodiment_digest,
                "configuration_digest": self.configuration_digest,
            }
        )


@dataclass(frozen=True)
class CampaignPlan:
    campaign_id: str
    skill_version_id: str
    candidate_digest: str
    embodiment_digest: str
    configuration_digest: str
    ordered_gates: tuple[str, ...]
    hardware_attempts: int
    prepared_by: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "ordered_gates", tuple(self.ordered_gates))

    def digest(self) -> str:
        return _digest(
            {
                "campaign_id": self.campaign_id,
                "skill_version_id": self.skill_version_id,
                "candidate_digest": self.candidate_digest,
                "embodiment_digest": self.embodiment_digest,
                "configuration_digest": self.configuration_digest,
                "ordered_gates": list(self.ordered_gates),
                "hardware_attempts": self.hardware_attempts,
                "prepared_by": self.prepared_by,
            }
        )


@dataclass(frozen=True)
class PromotionSubmission:
    skill: PhysicalSkill | None
    candidate: CandidateBundle | None
    embodiment: EmbodimentProfile | None
    configuration: PromotionConfiguration | None
    plan: CampaignPlan | None

    def identities(self) -> Mapping[str, str]:
        skill_identity = "missing"
        if self.skill is not None:
            skill_identity = (
                f"{self.skill.version_id}:{self.skill.contract_digest()}"
            )
        identities = {
            "skill_revision": skill_identity,
            "candidate_bundle": (
                "missing" if self.candidate is None else self.candidate.digest()
            ),
            "embodiment": (
                "missing" if self.embodiment is None else self.embodiment.digest()
            ),
            "configuration": (
                "missing"
                if self.configuration is None
                else self.configuration.digest()
            ),
            "campaign_plan": "missing" if self.plan is None else self.plan.digest(),
        }
        return MappingProxyType(identities)

    def digest(self) -> str:
        return _digest(dict(self.identities()))


@dataclass(frozen=True)
class SealedRejection:
    promotion_digest: str
    failed_gate: str
    reasons: tuple[str, ...]
    input_identities: Mapping[str, str]
    sealed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(
            self,
            "input_identities",
            MappingProxyType(dict(self.input_identities)),
        )


class PromotionLedger:
    def __init__(self) -> None:
        self._rejections: dict[str, SealedRejection] = {}

    def rejection_for(self, promotion_digest: str) -> SealedRejection | None:
        return self._rejections.get(promotion_digest)

    def seal_rejection(self, rejection: SealedRejection) -> SealedRejection:
        return self._rejections.setdefault(rejection.promotion_digest, rejection)

    def rejections(self) -> tuple[SealedRejection, ...]:
        return tuple(self._rejections.values())


ResultT = TypeVar("ResultT")


def promote_generation(
    submission: PromotionSubmission,
    *,
    ledger: PromotionLedger,
    execute: Callable[[PromotionSubmission], ResultT],
    now: datetime,
) -> ResultT | SealedRejection:
    """Validate frozen identities before handing the attempt to any executor."""
    existing = ledger.rejection_for(submission.digest())
    if existing is not None:
        return existing

    skill = submission.skill
    reasons: list[str] = []
    if skill is None:
        reasons.append("a frozen Physical Skill revision is required")
    elif skill.skill_id != GOLDEN_SKILL_ID:
        reasons.append(f"the first Generation accepts only {GOLDEN_SKILL_ID!r}")
    elif skill.operation_steps != GOLDEN_INSTRUMENT_OPERATION_STEPS:
        reasons.append(
            "the Golden Skill must declare the complete ordered Instrument "
            "Operation Loop"
        )

    candidate = submission.candidate
    if candidate is None:
        reasons.append("a frozen Candidate Bundle is required")
    else:
        candidate_fields = {
            "candidate_id": candidate.candidate_id,
            "policy_artifact_digest": candidate.policy_artifact_digest,
            "data_manifest_digest": candidate.data_manifest_digest,
            "training_recipe_digest": candidate.training_recipe_digest,
            "observation_schema_digest": candidate.observation_schema_digest,
            "action_schema_digest": candidate.action_schema_digest,
            "skill_version_id": candidate.skill_version_id,
            "skill_contract_digest": candidate.skill_contract_digest,
            "embodiment_digest": candidate.embodiment_digest,
            "configuration_digest": candidate.configuration_digest,
        }
        missing_candidate_fields = tuple(
            name for name, value in candidate_fields.items() if not value.strip()
        )
        if missing_candidate_fields:
            reasons.append(
                "the Candidate Bundle is missing: "
                + ", ".join(missing_candidate_fields)
            )
        if skill is not None:
            if candidate.skill_version_id != skill.version_id:
                reasons.append(
                    "the Candidate Bundle names a different Physical Skill "
                    "revision"
                )
            if candidate.skill_contract_digest != skill.contract_digest():
                reasons.append(
                    "the Candidate Bundle names a different Physical Skill "
                    "contract"
                )

    embodiment = submission.embodiment
    if embodiment is None:
        reasons.append("a frozen embodiment is required")
    else:
        if not embodiment.fully_verified:
            reasons.append(
                "the embodiment still has unverified configuration fields: "
                + ", ".join(embodiment.unverified_fields)
            )
        if candidate is not None and candidate.embodiment_digest != embodiment.digest():
            reasons.append("the Candidate Bundle names a different embodiment")

    configuration = submission.configuration
    if configuration is None:
        reasons.append("a frozen promotion configuration is required")
    else:
        configuration_fields = {
            "configuration_id": configuration.configuration_id,
            "embodiment_digest": configuration.embodiment_digest,
            "observation_schema_digest": configuration.observation_schema_digest,
            "action_protocol_digest": configuration.action_protocol_digest,
            "independent_witness_digest": configuration.independent_witness_digest,
            "calibration_digest": configuration.calibration_digest,
            "isaac_lab_config_digest": configuration.isaac_lab_config_digest,
            "mujoco_config_digest": configuration.mujoco_config_digest,
        }
        missing_configuration_fields = tuple(
            name
            for name, value in configuration_fields.items()
            if not value.strip()
        )
        if missing_configuration_fields:
            reasons.append(
                "the promotion configuration is missing: "
                + ", ".join(missing_configuration_fields)
            )
        if (
            embodiment is not None
            and configuration.embodiment_digest != embodiment.digest()
        ):
            reasons.append("the configuration names a different embodiment")
        if (
            candidate is not None
            and candidate.configuration_digest != configuration.digest()
        ):
            reasons.append("the Candidate Bundle names a different configuration")
        if (
            candidate is not None
            and candidate.observation_schema_digest
            != configuration.observation_schema_digest
        ):
            reasons.append(
                "the Candidate Bundle observation schema is incompatible with "
                "the promotion configuration"
            )
        if (
            candidate is not None
            and candidate.action_schema_digest
            != configuration.action_protocol_digest
        ):
            reasons.append(
                "the Candidate Bundle action schema is incompatible with the "
                "promotion configuration"
            )

    plan = submission.plan
    if plan is None:
        reasons.append("a frozen Campaign Plan is required")
    else:
        if not plan.campaign_id.strip():
            reasons.append("the Campaign Plan requires a campaign_id")
        if not plan.prepared_by.strip():
            reasons.append("the Campaign Plan must name its human owner")
        if plan.hardware_attempts <= 0:
            reasons.append(
                "the Campaign Plan must pre-register at least one hardware attempt"
            )
        if plan.ordered_gates != PROMOTION_GATE_ORDER:
            reasons.append(
                "the Campaign Plan gate order must match the Generation "
                "promotion ladder exactly"
            )
        if skill is not None and plan.skill_version_id != skill.version_id:
            reasons.append("the Campaign Plan names a different skill revision")
        if candidate is not None and plan.candidate_digest != candidate.digest():
            reasons.append("the Campaign Plan names a different Candidate Bundle")
        if embodiment is not None and plan.embodiment_digest != embodiment.digest():
            reasons.append("the Campaign Plan names a different embodiment")
        if (
            configuration is not None
            and plan.configuration_digest != configuration.digest()
        ):
            reasons.append("the Campaign Plan names a different configuration")

    if reasons:
        return ledger.seal_rejection(
            SealedRejection(
                promotion_digest=submission.digest(),
                failed_gate=GATE_CONTRACT_VALIDATION,
                reasons=tuple(reasons),
                input_identities=submission.identities(),
                sealed_at=now,
            )
        )

    return execute(submission)
