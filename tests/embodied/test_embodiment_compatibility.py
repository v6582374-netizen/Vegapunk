from __future__ import annotations

import unittest

from vegapunk.embodied.embodiment import (
    ACTION_SPACE_EE_6D,
    ACTION_SPACE_JOINT,
    COMPATIBILITY_ADAPTATION_REQUIRED,
    COMPATIBILITY_MATCHED,
    UNIFOLM_VLA_BASE_G1_EE6D,
    UNIFOLM_VLA_BASE_TASK_KEYS,
    EmbodimentProfile,
    PolicyCheckpoint,
    assess_policy_compatibility,
)


def _matching_embodiment(**overrides: object) -> EmbodimentProfile:
    policy = UNIFOLM_VLA_BASE_G1_EE6D
    fields: dict[str, object] = {
        "robot_model": "unitree_g1_29dof",
        "arm_dof": 14,
        "end_effector": policy.expected_end_effector,
        "camera_map": {key: key for key in policy.expected_camera_keys},
        "control_frequency_hz": policy.control_frequency_hz,
        "control_authority": "dual_arm_and_gripper_position",
        "state_dim": policy.state_dim,
        "action_dim": policy.action_dim,
        "action_space": policy.action_space,
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
            _matching_embodiment(), UNIFOLM_VLA_BASE_G1_EE6D
        )

        self.assertEqual(assessment.verdict, COMPATIBILITY_MATCHED)
        self.assertEqual(assessment.findings, ())
        self.assertTrue(assessment.admissible)

    def test_an_unverified_physical_fact_is_never_treated_as_compatible(
        self,
    ) -> None:
        assessment = assess_policy_compatibility(
            _matching_embodiment(unverified_fields=("end_effector",)),
            UNIFOLM_VLA_BASE_G1_EE6D,
        )

        self.assertEqual(assessment.verdict, COMPATIBILITY_ADAPTATION_REQUIRED)
        self.assertFalse(assessment.admissible)
        self.assertIn("unverified_fields", " ".join(assessment.findings))

    def test_each_contract_mismatch_is_reported_separately(self) -> None:
        assessment = assess_policy_compatibility(
            _matching_embodiment(
                end_effector="dex3",
                action_dim=16,
                state_dim=16,
                action_space=ACTION_SPACE_JOINT,
                control_frequency_hz=15.0,
                camera_map={"observation.images.wrist": "cam_left_wrist"},
                onboard_image_service=False,
            ),
            UNIFOLM_VLA_BASE_G1_EE6D,
        )

        joined = " ".join(assessment.findings)
        self.assertEqual(assessment.verdict, COMPATIBILITY_ADAPTATION_REQUIRED)
        self.assertIn("end_effector", joined)
        self.assertIn("action_dim", joined)
        self.assertIn("state_dim", joined)
        self.assertIn("control_frequency_hz", joined)
        self.assertIn("action_space", joined)
        self.assertIn("observation.images.top", joined)
        self.assertIn("image service", joined)

    def test_non_commercial_checkpoint_blocks_a_commercial_intended_use(
        self,
    ) -> None:
        policy = UNIFOLM_VLA_BASE_G1_EE6D

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

    def test_published_baseline_records_the_checkpoints_own_statistics(
        self,
    ) -> None:
        """The contract comes from dataset_statistics.json, not the README.

        These numbers were read off the published checkpoint. They disagree
        with both its ``config.yaml`` (which declares ``action_dim: 7``, a
        LIBERO template leftover) and with what this repository asserted
        before the file was inspected (16-dimensional joint angles under a key
        named ``g1_joint``, which does not exist in the checkpoint at all).
        """
        policy = UNIFOLM_VLA_BASE_G1_EE6D

        self.assertEqual(policy.action_chunk_steps, 25)
        self.assertEqual(policy.action_dim, 23)
        self.assertEqual(policy.state_dim, 23)
        self.assertEqual(policy.action_space, ACTION_SPACE_EE_6D)
        self.assertEqual(policy.normalization, "bounds_q99")
        self.assertEqual(policy.expected_end_effector, "dex1_1")
        self.assertEqual(policy.license_id, "CC-BY-NC-SA-4.0")

    def test_a_key_the_checkpoint_does_not_publish_is_refused(self) -> None:
        """``g1_joint`` is the specific absence that matters.

        The upstream loader picks its action constants by matching text in the
        launch command, so a path containing "joint" selects 16-dimensional
        joint constants -- for which this checkpoint carries no statistics at
        all. Refusing the key here turns a silent mis-scaling into an error
        before a model is loaded.
        """
        from vegapunk.embodied.embodiment import unifolm_vla_base_g1

        self.assertNotIn("g1_joint", UNIFOLM_VLA_BASE_TASK_KEYS)
        with self.assertRaises(ValueError) as caught:
            unifolm_vla_base_g1("g1_joint")
        self.assertIn("g1_joint", str(caught.exception))

    def test_every_published_task_key_yields_the_same_action_contract(
        self,
    ) -> None:
        """Thirteen tasks, one shape, thirteen different normalizations.

        The dimensions are uniform, which is exactly why the key matters: no
        dimension check can catch loading the wrong task's statistics, so the
        digest has to carry the key itself.
        """
        from vegapunk.embodied.embodiment import unifolm_vla_base_g1

        digests = set()
        for key in UNIFOLM_VLA_BASE_TASK_KEYS:
            policy = unifolm_vla_base_g1(key)
            self.assertEqual(policy.action_dim, 23)
            self.assertEqual(policy.action_space, ACTION_SPACE_EE_6D)
            digests.add(policy.digest())
        self.assertEqual(len(digests), len(UNIFOLM_VLA_BASE_TASK_KEYS))

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
