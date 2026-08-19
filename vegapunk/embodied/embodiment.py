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

ACTION_SPACE_JOINT = "joint"
ACTION_SPACE_EE_6D = "ee_6d"
"""What the numbers in an action vector *mean*.

The most consequential fact about a checkpoint, and the one most easily lost:
two contracts can agree on every dimension count and still describe different
physics. A joint-space action is an angle per motor. An ``ee_6d`` action is a
pose for the hand, which a robot cannot execute at all without an inverse
kinematics layer converting it into angles.

Recorded as a field rather than inferred from the dimension count because the
inference is not available: 23 numbers could be angles for a 23-DoF arm or a
dual-arm pose pair, and guessing wrong produces motion that is confidently and
completely wrong rather than absent.
"""

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
    action_space: str = ACTION_SPACE_JOINT
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
                "action_space": self.action_space,
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
    action_space: str = ACTION_SPACE_JOINT
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
                "action_space": self.action_space,
                "unverified_fields": sorted(self.unverified_fields),
            }
        )


# The task-scoped contracts actually published with UnifoLM-VLA-Base, read
# from the checkpoint's own ``dataset_statistics.json`` rather than from its
# README or its ``config.yaml``. Both of those documents disagree with the
# weights: the config declares ``action_dim: 7``, a leftover from the LIBERO
# template, and no key named ``g1_joint`` exists at all.
#
# The statistics file is the authority because it is what the server loads at
# runtime to un-normalize actions. If these numbers are wrong, every action the
# policy emits is scaled by the wrong constants, and the robot moves
# confidently to the wrong place -- which is indistinguishable, from the
# outside, from a policy that simply cannot do the task.
UNIFOLM_VLA_BASE_TASK_KEYS = (
    "g1_bag_insert",
    "g1_clean_table",
    "g1_dual_clean_table_left",
    "g1_dual_clean_table_right",
    "g1_erase_board",
    "g1_fold_towel",
    "g1_organize_tools",
    "g1_pack_pencilbox",
    "g1_pack_pingpong",
    "g1_pour_medicine",
    "g1_prepare_fruit",
    "g1_stack_block",
    "g1_wipe_table",
)
"""Every un-normalization key the published checkpoint actually carries.

Enumerated so that a key which does not exist is a rejection rather than a
``KeyError`` at inference time, and so that nobody has to discover the absence
of ``g1_joint`` by watching an arm move.
"""

UNIFOLM_VLA_BASE_ACTION_DIM = 23
UNIFOLM_VLA_BASE_CHUNK_STEPS = 25


def unifolm_vla_base_g1(
    unnorm_key: str = "g1_stack_block",
) -> PolicyCheckpoint:
    """The contract of one task's slice of UnifoLM-VLA-Base.

    Parameterised by task because the checkpoint is not one contract but
    thirteen: each task carries its own normalization statistics, and loading
    the wrong one mis-scales every action while every dimension check still
    passes. The key is therefore something a caller must state, and stating one
    that does not exist is refused here rather than at inference.
    """
    if unnorm_key not in UNIFOLM_VLA_BASE_TASK_KEYS:
        raise ValueError(
            f"unnorm_key {unnorm_key!r} is not published with this "
            f"checkpoint; it carries {list(UNIFOLM_VLA_BASE_TASK_KEYS)!r}. "
            "Note in particular that no 'g1_joint' key exists: the upstream "
            "loader would select 16-dimensional joint constants for it from "
            "launch-command text and then fail to find any matching statistics"
        )
    return PolicyCheckpoint(
        checkpoint_id=f"unifolm-vla-base/{unnorm_key}",
        unnorm_key=unnorm_key,
        action_chunk_steps=UNIFOLM_VLA_BASE_CHUNK_STEPS,
        action_dim=UNIFOLM_VLA_BASE_ACTION_DIM,
        state_dim=UNIFOLM_VLA_BASE_ACTION_DIM,
        expected_end_effector="dex1_1",
        expected_camera_keys=("observation.images.top",),
        control_frequency_hz=30.0,
        license_id="CC-BY-NC-SA-4.0",
        commercial_use_permitted=False,
        normalization=NORMALIZATION_BOUNDS_Q99,
        action_space=ACTION_SPACE_EE_6D,
    )


UNIFOLM_VLA_BASE_G1_EE6D = unifolm_vla_base_g1()
"""One representative task contract, for callers that need a concrete policy.

``g1_stack_block`` because it is the largest of the thirteen datasets and the
one the upstream evaluation scripts use as their example.
"""


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

    if embodiment.action_space != policy.action_space:
        findings.append(
            f"action_space {embodiment.action_space!r} does not match the "
            f"policy contract {policy.action_space!r}; the checkpoint's "
            "numbers are not the quantity this robot is commanded with, so a "
            "retargeting layer must convert them and its correctness is a "
            "separate claim that no dimension check can establish"
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
