"""Physical compatibility facts for the Embodied Execution Profile.

A VLA checkpoint is only meaningful against the exact embodiment it was
trained for: the end effector, camera keys, control frequency, and the
action/state dimensions are one contract, not independent settings. This
module makes that contract explicit data so an execution attempt can be
refused before any hardware moves.

Two facts drive the conservative design. First, the upstream checkpoint
selects its action/state constants by matching text in the launch command and
silently falls back to a 23-dimensional end-effector mode, so a checkpoint's
contract must be declared here and verified rather than inferred. Second, a
laboratory G1 that differs from the published ``g1_dex1`` path is an
adaptation project, not a deployment; the assessment therefore treats any
unverified fact as a mismatch instead of an assumption.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Optional

COMPATIBILITY_MATCHED = "matched"
COMPATIBILITY_ADAPTATION_REQUIRED = "adaptation_required"

NORMALIZATION_BOUNDS = "bounds"
NORMALIZATION_BOUNDS_Q99 = "bounds_q99"

INTENDED_USE_LABORATORY_RESEARCH = "laboratory_research"


def _digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class EmbodimentProfile:
    """The verified physical facts of one laboratory robot configuration.

    ``unverified_fields`` names the facts a human has not yet confirmed on the
    real hardware. It exists so an inventory can be recorded while incomplete
    without that incompleteness being mistaken for compatibility.
    """

    robot_model: str
    arm_dof: int
    end_effector: str
    camera_map: Mapping[str, str]
    control_frequency_hz: float
    control_authority: str
    state_dim: int
    action_dim: int
    onboard_image_service: bool
    unverified_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "camera_map", MappingProxyType(dict(self.camera_map))
        )
        object.__setattr__(
            self, "unverified_fields", tuple(self.unverified_fields)
        )

    def digest(self) -> str:
        """Identify this exact physical configuration.

        Every recorded run carries this digest so evidence collected on one
        configuration can never be read as evidence for another.
        """
        return _digest(
            {
                "robot_model": self.robot_model,
                "arm_dof": self.arm_dof,
                "end_effector": self.end_effector,
                "camera_map": dict(sorted(self.camera_map.items())),
                "control_frequency_hz": self.control_frequency_hz,
                "control_authority": self.control_authority,
                "state_dim": self.state_dim,
                "action_dim": self.action_dim,
                "onboard_image_service": self.onboard_image_service,
                "unverified_fields": sorted(self.unverified_fields),
            }
        )

    @property
    def fully_verified(self) -> bool:
        return not self.unverified_fields


@dataclass(frozen=True)
class PolicyCheckpoint:
    """The observation, action, and licence contract of one VLA checkpoint."""

    checkpoint_id: str
    unnorm_key: str
    action_chunk_steps: int
    action_dim: int
    state_dim: int
    expected_end_effector: str
    expected_camera_keys: tuple[str, ...]
    control_frequency_hz: float
    license_id: str
    commercial_use_permitted: bool
    normalization: str = NORMALIZATION_BOUNDS
    unverified_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "expected_camera_keys", tuple(self.expected_camera_keys)
        )
        object.__setattr__(
            self, "unverified_fields", tuple(self.unverified_fields)
        )

    def digest(self) -> str:
        return _digest(
            {
                "checkpoint_id": self.checkpoint_id,
                "unnorm_key": self.unnorm_key,
                "action_chunk_steps": self.action_chunk_steps,
                "action_dim": self.action_dim,
                "state_dim": self.state_dim,
                "expected_end_effector": self.expected_end_effector,
                "expected_camera_keys": sorted(self.expected_camera_keys),
                "control_frequency_hz": self.control_frequency_hz,
                "license_id": self.license_id,
                "commercial_use_permitted": self.commercial_use_permitted,
                "normalization": self.normalization,
                "unverified_fields": sorted(self.unverified_fields),
            }
        )


# The published G1 joint-mode contract: 25 action-chunk steps by 16 dimensions
# with bounds normalization, a Dex1-1 gripper pair, and an onboard image
# service. Recorded here because the upstream loader would otherwise choose
# these constants from launch-command text.
UNIFOLM_VLA_BASE_G1_DEX1_JOINT = PolicyCheckpoint(
    checkpoint_id="unifolm-vla-base/g1_dex1/joint",
    unnorm_key="g1_joint",
    action_chunk_steps=25,
    action_dim=16,
    state_dim=16,
    expected_end_effector="dex1_1",
    expected_camera_keys=("observation.images.top",),
    control_frequency_hz=30.0,
    license_id="CC-BY-NC-SA-4.0",
    commercial_use_permitted=False,
    normalization=NORMALIZATION_BOUNDS,
)


@dataclass(frozen=True)
class CompatibilityAssessment:
    """Whether one embodiment may run one policy, and why not if it may not."""

    verdict: str
    embodiment_digest: str
    policy_digest: Optional[str]
    findings: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))

    @property
    def admissible(self) -> bool:
        return self.verdict == COMPATIBILITY_MATCHED


def assess_policy_compatibility(
    embodiment: EmbodimentProfile,
    policy: Optional[PolicyCheckpoint],
    intended_use: str = INTENDED_USE_LABORATORY_RESEARCH,
) -> CompatibilityAssessment:
    """Compare a laboratory embodiment against a checkpoint's contract.

    ``policy`` is ``None`` for a deterministic skill, which has no learned
    observation or action contract to satisfy. Findings are reported per
    mismatched fact rather than as one summary so an adaptation plan can be
    derived from the result.
    """
    findings: list[str] = []

    if embodiment.unverified_fields:
        findings.append(
            "embodiment unverified_fields must be confirmed on hardware: "
            + ", ".join(sorted(embodiment.unverified_fields))
        )

    if policy is None:
        verdict = (
            COMPATIBILITY_ADAPTATION_REQUIRED
            if findings
            else COMPATIBILITY_MATCHED
        )
        return CompatibilityAssessment(
            verdict=verdict,
            embodiment_digest=embodiment.digest(),
            policy_digest=None,
            findings=tuple(findings),
        )

    if policy.unverified_fields:
        findings.append(
            "policy unverified_fields must be confirmed against the "
            "checkpoint: " + ", ".join(sorted(policy.unverified_fields))
        )

    if embodiment.end_effector != policy.expected_end_effector:
        findings.append(
            f"end_effector {embodiment.end_effector!r} does not match the "
            f"policy contract {policy.expected_end_effector!r}"
        )

    if embodiment.action_dim != policy.action_dim:
        findings.append(
            f"action_dim {embodiment.action_dim} does not match the policy "
            f"contract {policy.action_dim}"
        )

    if embodiment.state_dim != policy.state_dim:
        findings.append(
            f"state_dim {embodiment.state_dim} does not match the policy "
            f"contract {policy.state_dim}"
        )

    if embodiment.control_frequency_hz != policy.control_frequency_hz:
        findings.append(
            f"control_frequency_hz {embodiment.control_frequency_hz} does not "
            f"match the policy contract {policy.control_frequency_hz}"
        )

    for camera_key in policy.expected_camera_keys:
        if camera_key not in embodiment.camera_map:
            findings.append(
                f"camera_map provides no source for {camera_key!r}"
            )

    if not embodiment.onboard_image_service:
        findings.append(
            "the onboard image service is unavailable, so the policy cannot "
            "receive a trained-equivalent observation stream"
        )

    if not policy.commercial_use_permitted and intended_use != (
        INTENDED_USE_LABORATORY_RESEARCH
    ):
        findings.append(
            f"the checkpoint license {policy.license_id} does not permit "
            f"intended_use {intended_use!r}"
        )

    verdict = (
        COMPATIBILITY_ADAPTATION_REQUIRED if findings else COMPATIBILITY_MATCHED
    )
    return CompatibilityAssessment(
        verdict=verdict,
        embodiment_digest=embodiment.digest(),
        policy_digest=policy.digest(),
        findings=tuple(findings),
    )
