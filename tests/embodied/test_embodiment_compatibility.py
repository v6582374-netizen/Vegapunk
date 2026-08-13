from __future__ import annotations

import unittest

from vegapunk.embodied.embodiment import (
    COMPATIBILITY_ADAPTATION_REQUIRED,
    COMPATIBILITY_MATCHED,
    UNIFOLM_VLA_BASE_G1_DEX1_JOINT,
    EmbodimentProfile,
    PolicyCheckpoint,
    assess_policy_compatibility,
)


def _matching_embodiment(**overrides: object) -> EmbodimentProfile:
    policy = UNIFOLM_VLA_BASE_G1_DEX1_JOINT
    fields: dict[str, object] = {
        "robot_model": "unitree_g1_29dof",
        "arm_dof": 14,
        "end_effector": policy.expected_end_effector,
        "camera_map": {key: key for key in policy.expected_camera_keys},
        "control_frequency_hz": policy.control_frequency_hz,
        "control_authority": "dual_arm_and_gripper_position",
        "state_dim": policy.state_dim,
        "action_dim": policy.action_dim,
        "onboard_image_service": True,
        "unverified_fields": (),
    }
    fields.update(overrides)
    return EmbodimentProfile(**fields)  # type: ignore[arg-type]


class EmbodimentDigestTest(unittest.TestCase):
    def test_digest_changes_when_any_physical_fact_changes(self) -> None:
        baseline = _matching_embodiment()

        self.assertNotEqual(
            baseline.digest(),
            _matching_embodiment(end_effector="dex3").digest(),
        )
        self.assertNotEqual(
            baseline.digest(),
            _matching_embodiment(
                camera_map={"observation.images.top": "cam_left_high"}
            ).digest(),
        )
        self.assertEqual(baseline.digest(), _matching_embodiment().digest())

    def test_camera_map_cannot_be_mutated_after_construction(self) -> None:
        embodiment = _matching_embodiment()

        with self.assertRaises(TypeError):
            embodiment.camera_map["observation.images.top"] = "cam_left_high"  # type: ignore[index]


class PolicyCompatibilityTest(unittest.TestCase):
    def test_exactly_matching_contract_is_the_only_matched_verdict(self) -> None:
        assessment = assess_policy_compatibility(
            _matching_embodiment(), UNIFOLM_VLA_BASE_G1_DEX1_JOINT
        )

        self.assertEqual(assessment.verdict, COMPATIBILITY_MATCHED)
        self.assertEqual(assessment.findings, ())
        self.assertTrue(assessment.admissible)

    def test_an_unverified_physical_fact_is_never_treated_as_compatible(
        self,
    ) -> None:
        assessment = assess_policy_compatibility(
            _matching_embodiment(unverified_fields=("end_effector",)),
            UNIFOLM_VLA_BASE_G1_DEX1_JOINT,
        )

        self.assertEqual(assessment.verdict, COMPATIBILITY_ADAPTATION_REQUIRED)
        self.assertFalse(assessment.admissible)
        self.assertIn("unverified_fields", " ".join(assessment.findings))

    def test_each_contract_mismatch_is_reported_separately(self) -> None:
        assessment = assess_policy_compatibility(
            _matching_embodiment(
                end_effector="dex3",
                action_dim=23,
                state_dim=23,
                control_frequency_hz=15.0,
                camera_map={"observation.images.wrist": "cam_left_wrist"},
                onboard_image_service=False,
            ),
            UNIFOLM_VLA_BASE_G1_DEX1_JOINT,
        )

        joined = " ".join(assessment.findings)
        self.assertEqual(assessment.verdict, COMPATIBILITY_ADAPTATION_REQUIRED)
        self.assertIn("end_effector", joined)
        self.assertIn("action_dim", joined)
        self.assertIn("state_dim", joined)
        self.assertIn("control_frequency_hz", joined)
        self.assertIn("observation.images.top", joined)
        self.assertIn("image service", joined)

    def test_non_commercial_checkpoint_blocks_a_commercial_intended_use(
        self,
    ) -> None:
        policy = UNIFOLM_VLA_BASE_G1_DEX1_JOINT

        self.assertFalse(policy.commercial_use_permitted)
        assessment = assess_policy_compatibility(
            _matching_embodiment(), policy, intended_use="commercial_service"
        )

        self.assertEqual(assessment.verdict, COMPATIBILITY_ADAPTATION_REQUIRED)
        self.assertIn("license", " ".join(assessment.findings))

    def test_deterministic_skills_have_no_policy_contract_to_satisfy(
        self,
    ) -> None:
        assessment = assess_policy_compatibility(_matching_embodiment(), None)

        self.assertEqual(assessment.verdict, COMPATIBILITY_MATCHED)
        self.assertIsNone(assessment.policy_digest)

    def test_published_baseline_records_the_documented_joint_contract(
        self,
    ) -> None:
        policy = UNIFOLM_VLA_BASE_G1_DEX1_JOINT

        self.assertEqual(policy.action_chunk_steps, 25)
        self.assertEqual(policy.action_dim, 16)
        self.assertEqual(policy.state_dim, 16)
        self.assertEqual(policy.expected_end_effector, "dex1_1")
        self.assertEqual(policy.license_id, "CC-BY-NC-SA-4.0")

    def test_unverified_policy_field_also_requires_adaptation(self) -> None:
        drifted = PolicyCheckpoint(
            checkpoint_id="lab-candidate",
            unnorm_key="g1_lab_task",
            action_chunk_steps=25,
            action_dim=16,
            state_dim=16,
            expected_end_effector="dex1_1",
            expected_camera_keys=("observation.images.top",),
            control_frequency_hz=30.0,
            license_id="CC-BY-NC-SA-4.0",
            commercial_use_permitted=False,
            unverified_fields=("unnorm_key",),
        )

        assessment = assess_policy_compatibility(
            _matching_embodiment(
                camera_map={"observation.images.top": "cam_right_high"}
            ),
            drifted,
        )

        self.assertEqual(assessment.verdict, COMPATIBILITY_ADAPTATION_REQUIRED)
        self.assertIn("unnorm_key", " ".join(assessment.findings))


if __name__ == "__main__":
    unittest.main()
