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


def _missing_fields(fields: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(name for name, value in fields.items() if not value.strip())


@dataclass(frozen=True)
class InstrumentOperationLoop:
    """The ordered whole task; its identity is not a set of segments."""

    steps: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", tuple(self.steps))

    def digest(self) -> str:
        return _digest(list(self.steps))


@dataclass(frozen=True)
class GoldenSkillRevision:
    """The reviewed Physical Skill contract plus its complete ordered loop."""

    skill: PhysicalSkill
    operation_loop: InstrumentOperationLoop

    @property
    def version_id(self) -> str:
        return self.skill.version_id

    def digest(self) -> str:
        return _digest(
            {
                "physical_skill_contract": self.skill.contract_digest(),
                "operation_loop": self.operation_loop.digest(),
            }
        )


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

    def as_contract(self) -> dict[str, str]:
        return {
            "configuration_id": self.configuration_id,
            "embodiment_digest": self.embodiment_digest,
            "observation_schema_digest": self.observation_schema_digest,
            "action_protocol_digest": self.action_protocol_digest,
            "independent_witness_digest": self.independent_witness_digest,
            "calibration_digest": self.calibration_digest,
            "isaac_lab_config_digest": self.isaac_lab_config_digest,
            "mujoco_config_digest": self.mujoco_config_digest,
        }

    def missing_fields(self) -> tuple[str, ...]:
        return _missing_fields(self.as_contract())

    def digest(self) -> str:
        return _digest(self.as_contract())


@dataclass(frozen=True)
class CandidateBundle:
    candidate_id: str
    policy_artifact_digest: str
    data_manifest_digest: str
    training_recipe_digest: str
    observation_schema_digest: str
    action_schema_digest: str
    skill_revision_id: str
    skill_revision_digest: str
    embodiment_digest: str
    configuration_digest: str

    def as_contract(self) -> dict[str, str]:
        return {
            "candidate_id": self.candidate_id,
            "policy_artifact_digest": self.policy_artifact_digest,
            "data_manifest_digest": self.data_manifest_digest,
            "training_recipe_digest": self.training_recipe_digest,
            "observation_schema_digest": self.observation_schema_digest,
            "action_schema_digest": self.action_schema_digest,
            "skill_revision_id": self.skill_revision_id,
            "skill_revision_digest": self.skill_revision_digest,
            "embodiment_digest": self.embodiment_digest,
            "configuration_digest": self.configuration_digest,
        }

    def missing_fields(self) -> tuple[str, ...]:
        return _missing_fields(self.as_contract())

    def digest(self) -> str:
        return _digest(self.as_contract())


@dataclass(frozen=True)
class CampaignPlan:
    campaign_id: str
    skill_revision_id: str
    candidate_digest: str
    embodiment_digest: str
    configuration_digest: str
    ordered_gates: tuple[str, ...]
    hardware_attempts: int
    prepared_by: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "ordered_gates", tuple(self.ordered_gates))

    def as_contract(self) -> dict[str, object]:
        return {
            "campaign_id": self.campaign_id,
            "skill_revision_id": self.skill_revision_id,
            "candidate_digest": self.candidate_digest,
            "embodiment_digest": self.embodiment_digest,
            "configuration_digest": self.configuration_digest,
            "ordered_gates": list(self.ordered_gates),
            "hardware_attempts": self.hardware_attempts,
            "prepared_by": self.prepared_by,
        }

    def digest(self) -> str:
        return _digest(self.as_contract())


GOLDEN_INSTRUMENT_OPERATION_LOOP = InstrumentOperationLoop(
    steps=(
        "open_lid",
        "pick_up_cup",
        "tilt_cup",
        "return_cup",
        "close_lid",
    )
)

GOLDEN_EMBODIMENT = EmbodimentProfile(
    robot_model="unitree_g1",
    arm_dof=14,
    end_effector="dex3",
    camera_map={"observation.images.top": "head_camera"},
    control_frequency_hz=30.0,
    control_authority="target_bridge_v1",
    state_dim=29,
    action_dim=29,
    onboard_image_service=True,
)

GOLDEN_PROMOTION_CONFIGURATION = PromotionConfiguration(
    configuration_id="golden-bench-v1",
    embodiment_digest=GOLDEN_EMBODIMENT.digest(),
    observation_schema_digest="golden-observation-v1",
    action_protocol_digest="joint-whole-body-target-v1",
    independent_witness_digest="lid-and-volume-witness-v1",
    calibration_digest="golden-bench-calibration-v1",
    isaac_lab_config_digest="isaac-golden-bench-v1",
    mujoco_config_digest="mujoco-golden-control-v1",
)


@dataclass(frozen=True)
class PromotionSubmission:
    skill: GoldenSkillRevision | None
    candidate: CandidateBundle | None
    embodiment: EmbodimentProfile | None
    configuration: PromotionConfiguration | None
    plan: CampaignPlan | None

    def identities(self) -> Mapping[str, str]:
        skill_identity = "missing"
        if self.skill is not None:
            skill_identity = f"{self.skill.version_id}:{self.skill.digest()}"
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

    def digest(self) -> str:
        return _digest(
            {
                "promotion_digest": self.promotion_digest,
                "failed_gate": self.failed_gate,
                "reasons": list(self.reasons),
                "input_identities": dict(self.input_identities),
                "sealed_at": self.sealed_at.isoformat(),
            }
        )


class PromotionLedger:
    """The append-only rejection record for one promotion authority."""

    def __init__(self) -> None:
        self._rejections: dict[str, SealedRejection] = {}

    def rejection_for(self, promotion_digest: str) -> SealedRejection | None:
        return self._rejections.get(promotion_digest)

    def seal_rejection(self, rejection: SealedRejection) -> SealedRejection:
        return self._rejections.setdefault(rejection.promotion_digest, rejection)

    def rejections(self) -> tuple[SealedRejection, ...]:
        return tuple(self._rejections.values())


def _contract_reasons(submission: PromotionSubmission) -> tuple[str, ...]:
    reasons: list[str] = []
    skill = submission.skill
    candidate = submission.candidate
    embodiment = submission.embodiment
    configuration = submission.configuration
    plan = submission.plan

    if skill is None:
        reasons.append("a frozen Physical Skill revision is required")
    else:
        if skill.skill.skill_id != GOLDEN_SKILL_ID:
            reasons.append(
                f"the first Generation accepts only {GOLDEN_SKILL_ID!r}"
            )
        if skill.operation_loop != GOLDEN_INSTRUMENT_OPERATION_LOOP:
            reasons.append(
                "the Golden Skill must declare the complete ordered Instrument "
                "Operation Loop"
            )

    if candidate is None:
        reasons.append("a frozen Candidate Bundle is required")
    else:
        missing = candidate.missing_fields()
        if missing:
            reasons.append(
                "the Candidate Bundle is missing: " + ", ".join(missing)
            )
        if skill is not None:
            if candidate.skill_revision_id != skill.version_id:
                reasons.append(
                    "the Candidate Bundle names a different Physical Skill "
                    "revision"
                )
            if candidate.skill_revision_digest != skill.digest():
                reasons.append(
                    "the Candidate Bundle names a different Physical Skill "
                    "contract"
                )

    if embodiment is None:
        reasons.append("a frozen embodiment is required")
    else:
        if not embodiment.fully_verified:
            reasons.append(
                "the embodiment still has unverified configuration fields: "
                + ", ".join(embodiment.unverified_fields)
            )
        if embodiment.digest() != GOLDEN_EMBODIMENT.digest():
            reasons.append(
                "the first Generation accepts only the named Golden embodiment"
            )
        if candidate is not None and candidate.embodiment_digest != embodiment.digest():
            reasons.append("the Candidate Bundle names a different embodiment")

    if configuration is None:
        reasons.append("a frozen promotion configuration is required")
    else:
        missing = configuration.missing_fields()
        if missing:
            reasons.append(
                "the promotion configuration is missing: " + ", ".join(missing)
            )
        if configuration.digest() != GOLDEN_PROMOTION_CONFIGURATION.digest():
            reasons.append(
                "the first Generation accepts only the named Golden "
                "configuration"
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
        if skill is not None and plan.skill_revision_id != skill.version_id:
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

    return tuple(reasons)


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

    reasons = _contract_reasons(submission)
    if reasons:
        return ledger.seal_rejection(
            SealedRejection(
                promotion_digest=submission.digest(),
                failed_gate=GATE_CONTRACT_VALIDATION,
                reasons=reasons,
                input_identities=submission.identities(),
                sealed_at=now,
            )
        )

    return execute(submission)
