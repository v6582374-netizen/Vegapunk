"""The retargeting layer: every conversion that can be silently wrong.

These tests exist because the retargeting layer is the one place in the VLA
path where a defect produces numbers of the right shape and the wrong motion.
Each conversion is therefore checked against the published recordings rather
than against itself, and the two decisive facts -- the 6D convention and the
tool offset -- are checked by the fingerprints that distinguish them from their
plausible alternatives.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np
import pytest

from vegapunk.embodied.retarget import (
    ACTION_DIM,
    ArmRetargeter,
    GRIPPER_RANGE,
    ROTATION_6D_COLUMNS,
    ROTATION_6D_ROWS,
    TOOL_OFFSET_M,
    EndEffectorPose,
    PolicyAction,
    denormalize,
    rotation_from_6d,
    rotation_to_6d,
)


def _rotation(angle: float, axis: int = 2) -> np.ndarray:
    """One rotation matrix, built without depending on the module under test."""
    c, s = np.cos(angle), np.sin(angle)
    if axis == 2:
        return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    if axis == 1:
        return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def _euler_xyz_matrix(angles) -> np.ndarray:
    """Extrinsic xyz euler angles as a rotation matrix.

    Written out rather than taken from scipy so the convention under test is
    stated here explicitly: extrinsic xyz composes as Rz @ Ry @ Rx.
    """
    x, y, z = (float(v) for v in angles)
    return _rotation(z, axis=2) @ _rotation(y, axis=1) @ _rotation(x, axis=0)


def _action(
    left_position=(0.3, 0.2, 0.15),
    left_rotation=None,
    right_position=(0.3, -0.2, 0.15),
    right_rotation=None,
    grippers=(2.0, 3.0),
    waist=(0.1, 0.2, 0.3),
) -> np.ndarray:
    left = _rotation(0.3) if left_rotation is None else left_rotation
    right = _rotation(-0.4) if right_rotation is None else right_rotation
    values = np.zeros(ACTION_DIM)
    values[0:3] = left_position
    values[3:9] = rotation_to_6d(left)
    values[9:12] = right_position
    values[12:18] = rotation_to_6d(right)
    values[18:20] = grippers
    values[20:23] = waist
    return values


class Rotation6DTest(unittest.TestCase):
    """The convention that is indistinguishable by shape and not by motion."""

    def test_a_rotation_survives_the_round_trip(self) -> None:
        original = _rotation(0.7, axis=1)
        rebuilt = rotation_from_6d(rotation_to_6d(original))
        np.testing.assert_allclose(rebuilt, original, atol=1e-12)

    def test_the_result_is_a_rotation_matrix(self) -> None:
        rebuilt = rotation_from_6d(rotation_to_6d(_rotation(1.1)))
        np.testing.assert_allclose(
            rebuilt @ rebuilt.T, np.eye(3), atol=1e-12
        )
        self.assertAlmostEqual(float(np.linalg.det(rebuilt)), 1.0, places=12)

    def test_columns_and_rows_are_different_orientations(self) -> None:
        """The reason the convention has to be measured, not assumed."""
        encoded = rotation_to_6d(_rotation(0.9), ROTATION_6D_COLUMNS)
        as_columns = rotation_from_6d(encoded, ROTATION_6D_COLUMNS)
        as_rows = rotation_from_6d(encoded, ROTATION_6D_ROWS)

        self.assertFalse(np.allclose(as_columns, as_rows, atol=1e-6))
        # Both are valid rotations, which is exactly why a shape check cannot
        # tell them apart.
        np.testing.assert_allclose(as_rows @ as_rows.T, np.eye(3), atol=1e-12)

    def test_non_orthonormal_input_is_orthonormalised(self) -> None:
        """A policy's raw output is not guaranteed to be a rotation."""
        rebuilt = rotation_from_6d([2.0, 0.0, 0.0, 0.3, 1.5, 0.0])
        np.testing.assert_allclose(
            rebuilt @ rebuilt.T, np.eye(3), atol=1e-12
        )

    def test_a_degenerate_triple_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            rotation_from_6d([0.0, 0.0, 0.0, 1.0, 0.0, 0.0])

    def test_parallel_triples_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            rotation_from_6d([1.0, 0.0, 0.0, 2.0, 0.0, 0.0])


class ActionDecodingTest(unittest.TestCase):
    """The 23-vector is three unrelated encodings, and the split must hold."""

    def test_every_field_lands_where_it_belongs(self) -> None:
        left = _rotation(0.3)
        right = _rotation(-0.4)
        decoded = PolicyAction.decode(_action())

        np.testing.assert_allclose(
            decoded.left.position_m, (0.3, 0.2, 0.15), atol=1e-12
        )
        np.testing.assert_allclose(decoded.left.matrix, left, atol=1e-12)
        np.testing.assert_allclose(
            decoded.right.position_m, (0.3, -0.2, 0.15), atol=1e-12
        )
        np.testing.assert_allclose(decoded.right.matrix, right, atol=1e-12)
        self.assertEqual(decoded.gripper_apertures, (2.0, 3.0))
        np.testing.assert_allclose(decoded.waist, (0.1, 0.2, 0.3), atol=1e-12)

    def test_a_sixteen_dimensional_action_is_refused_by_name(self) -> None:
        """The exact failure the upstream text-matching loader produces."""
        with self.assertRaises(ValueError) as caught:
            PolicyAction.decode(np.zeros(16))

        message = str(caught.exception)
        self.assertIn("23", message)
        self.assertIn("16", message)
        self.assertIn("launch-command text", message)

    def test_the_left_and_right_arms_are_not_confused(self) -> None:
        decoded = PolicyAction.decode(
            _action(left_position=(0.1, 0.2, 0.3), right_position=(0.4, 0.5, 0.6))
        )
        np.testing.assert_allclose(
            decoded.left.position_m, (0.1, 0.2, 0.3), atol=1e-12
        )
        np.testing.assert_allclose(
            decoded.right.position_m, (0.4, 0.5, 0.6), atol=1e-12
        )

    def test_gripper_apertures_are_carried_in_their_own_units(self) -> None:
        """Not metres, not radians: the checkpoint's own actuator scale."""
        decoded = PolicyAction.decode(_action(grippers=GRIPPER_RANGE))
        self.assertEqual(decoded.gripper_apertures, tuple(GRIPPER_RANGE))


class ToolOffsetTest(unittest.TestCase):
    """The 5cm nobody documents, and the frame it lives in."""

    def test_the_offset_moves_along_the_tool_axis_not_the_world_axis(
        self,
    ) -> None:
        """Rotate the tool 90 degrees and the offset must rotate with it."""
        turned = EndEffectorPose(
            position_m=(0.0, 0.0, 0.0),
            rotation=tuple(tuple(r) for r in _rotation(np.pi / 2)),
        )
        wrist = turned.with_tool_offset((0.05, 0.0, 0.0))

        # The tool's x-axis now points along world +y, so the wrist sits at -y.
        np.testing.assert_allclose(
            wrist.position_m, (0.0, -0.05, 0.0), atol=1e-12
        )

    def test_the_offset_is_a_pure_translation(self) -> None:
        pose = EndEffectorPose(
            position_m=(0.3, 0.1, 0.2),
            rotation=tuple(tuple(r) for r in _rotation(0.4)),
        )
        np.testing.assert_allclose(
            pose.with_tool_offset().matrix, pose.matrix, atol=1e-12
        )

    def test_the_published_offset_is_along_the_wrist_x_axis(self) -> None:
        """The measured constant: 50mm forward, no lateral component."""
        self.assertAlmostEqual(TOOL_OFFSET_M[0], 0.05, places=4)
        self.assertAlmostEqual(TOOL_OFFSET_M[1], 0.0, places=6)
        self.assertAlmostEqual(TOOL_OFFSET_M[2], 0.0, places=6)

    def test_an_identity_orientation_reduces_to_a_plain_subtraction(
        self,
    ) -> None:
        pose = EndEffectorPose(
            position_m=(0.3, 0.0, 0.0), rotation=tuple(tuple(r) for r in np.eye(3))
        )
        np.testing.assert_allclose(
            pose.with_tool_offset((0.05, 0.0, 0.0)).position_m,
            (0.25, 0.0, 0.0),
            atol=1e-12,
        )

    def test_a_malformed_pose_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            EndEffectorPose(position_m=(0.0, 0.0), rotation=tuple(
                tuple(r) for r in np.eye(3)
            ))


class DenormalizationTest(unittest.TestCase):
    """The silent rescaling that makes a correct policy look incompetent."""

    def test_the_round_trip_is_exact(self) -> None:
        low = np.array([-1.0, 0.0, 2.0])
        high = np.array([1.0, 4.5, 3.0])
        raw = np.array([0.25, 3.0, 2.5])
        normalized = 2.0 * (raw - low) / (high - low) - 1.0

        np.testing.assert_allclose(
            denormalize(normalized, low, high), raw, atol=1e-12
        )

    def test_the_bounds_map_onto_minus_one_and_one(self) -> None:
        low = np.array([0.0, -2.0])
        high = np.array([4.5, 2.0])
        np.testing.assert_allclose(denormalize([-1.0, -1.0], low, high), low)
        np.testing.assert_allclose(denormalize([1.0, 1.0], low, high), high)

    def test_a_masked_dimension_passes_through_unscaled(self) -> None:
        """The statistics' own mask marks dimensions that were never scaled."""
        out = denormalize(
            [0.0, 0.7], [0.0, 0.0], [4.5, 4.5], mask=[True, False]
        )
        self.assertAlmostEqual(float(out[0]), 2.25, places=12)
        self.assertAlmostEqual(float(out[1]), 0.7, places=12)

    def test_a_width_mismatch_is_refused_rather_than_broadcast(self) -> None:
        with self.assertRaises(ValueError):
            denormalize(np.zeros(23), np.zeros(16), np.ones(16))

    def test_a_wrong_width_mask_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            denormalize(np.zeros(3), np.zeros(3), np.ones(3), mask=[True])


if __name__ == "__main__":
    unittest.main()


_SCENE = (
    Path(__file__).resolve().parents[2]
    / "third_party"
    / "mujoco_menagerie"
    / "unitree_g1"
    / "scene_with_hands.xml"
)

_LEFT_ARM_JOINTS = (
    "left_shoulder_pitch_joint",
    "left_shoulder_roll_joint",
    "left_shoulder_yaw_joint",
    "left_elbow_joint",
    "left_wrist_roll_joint",
    "left_wrist_pitch_joint",
    "left_wrist_yaw_joint",
)

_DATASET = Path(
    "/mnt/data-hdd/unifolm-vla/datasets/G1_Dex1_Stack_Block"
)


def _model():
    mujoco = pytest.importorskip("mujoco")
    if not _SCENE.exists():  # pragma: no cover - submodule not checked out
        pytest.skip(f"the G1 scene is not present at {_SCENE}")
    return mujoco.MjModel.from_xml_path(str(_SCENE))


def _retargeter():
    return ArmRetargeter(
        model=_model(),
        joint_names=_LEFT_ARM_JOINTS,
        wrist_body="left_wrist_yaw_link",
        reference_body="pelvis",
    )


class ArmRetargeterTest(unittest.TestCase):
    """The IK layer, against the model it resolves poses in."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.retargeter = _retargeter()
        cls.home = (0.2, 0.3, 0.0, 0.6, 0.0, 0.0, 0.0)

    def test_forward_then_solve_recovers_the_same_pose(self) -> None:
        """The one check that does not trust the solver: solve, then run it forward."""
        pose = self.retargeter.forward(self.home)
        result = self.retargeter.solve(pose, self.home)

        self.assertTrue(result.converged, result.detail)
        reached = self.retargeter.forward(result.joint_positions_rad)
        self.assertLess(
            float(
                np.linalg.norm(
                    np.asarray(reached.position_m)
                    - np.asarray(pose.position_m)
                )
            ),
            1e-4,
        )

    def test_a_displaced_target_is_reached_from_a_stale_seed(self) -> None:
        """The Jacobian must be usable from a seed that is not the answer.

        This is the regression for the ``mj_comPos`` omission: ``mj_kinematics``
        alone leaves the body-relative quantities ``mj_jac`` reads untouched, so
        every reported Jacobian was stale and the solver converged only when the
        seed already was the solution.
        """
        start = self.retargeter.forward(self.home)
        target = EndEffectorPose(
            position_m=(
                start.position_m[0] + 0.04,
                start.position_m[1] - 0.03,
                start.position_m[2] + 0.05,
            ),
            rotation=start.rotation,
        )

        result = self.retargeter.solve(target, self.home)

        self.assertTrue(result.converged, result.detail)
        self.assertLess(result.position_error_m, 1e-4)
        self.assertGreater(result.iterations, 1)

    def test_the_tool_offset_is_applied_once_not_twice(self) -> None:
        """``solve`` owns the offset; a caller must not pre-apply it.

        The failure this pins down is quiet. Pre-applying the offset gives the
        solver a target it can reach perfectly, so it converges and reports no
        error at all -- while the tool ends up exactly one offset short of
        where it was asked for. Checking the solver's own residual would miss
        it entirely, so the check runs the answer forward and compares against
        the original request.
        """
        wanted = self.retargeter.forward(self.home)

        honest = self.retargeter.solve(wanted, self.home)
        reached = self.retargeter.forward(honest.joint_positions_rad)
        self.assertTrue(honest.converged)
        self.assertLess(
            float(
                np.linalg.norm(
                    np.asarray(reached.position_m)
                    - np.asarray(wanted.position_m)
                )
            ),
            1e-3,
        )

        doubled = self.retargeter.solve(wanted.with_tool_offset(), self.home)
        drifted = self.retargeter.forward(doubled.joint_positions_rad)
        gap = float(
            np.linalg.norm(
                np.asarray(drifted.position_m)
                - np.asarray(wanted.position_m)
            )
        )
        self.assertTrue(doubled.converged)
        self.assertAlmostEqual(
            gap, float(np.linalg.norm(TOOL_OFFSET_M)), places=3
        )

    def test_an_unreachable_pose_is_reported_not_hidden(self) -> None:
        far = EndEffectorPose(
            position_m=(3.0, 0.0, 0.0), rotation=np.eye(3)
        )
        result = self.retargeter.solve(far, self.home)

        self.assertFalse(result.converged)
        self.assertIn("did not converge", result.detail)
        self.assertGreater(result.position_error_m, 0.1)

    def test_the_seed_selects_which_null_space_solution_is_returned(
        self,
    ) -> None:
        """A 6-DOF target does not determine 7 joints, and the seed is the choice."""
        pose = self.retargeter.forward(self.home)
        other_seed = (0.0, 0.6, 0.4, 0.9, 0.2, 0.0, 0.0)

        first = self.retargeter.solve(pose, self.home)
        second = self.retargeter.solve(pose, other_seed)

        self.assertTrue(first.converged and second.converged)
        joints_differ = float(
            np.max(
                np.abs(
                    np.asarray(first.joint_positions_rad)
                    - np.asarray(second.joint_positions_rad)
                )
            )
        )
        self.assertGreater(joints_differ, 1e-3)
        # ... and yet both reach the same pose.
        for result in (first, second):
            self.assertLess(result.position_error_m, 1e-4)
            self.assertLess(result.rotation_error_rad, 1e-3)

    def test_a_seed_of_the_wrong_width_is_refused(self) -> None:
        pose = self.retargeter.forward(self.home)
        with self.assertRaises(ValueError):
            self.retargeter.solve(pose, (0.0, 0.0))

    def test_an_unknown_joint_is_refused_at_construction(self) -> None:
        with self.assertRaises(ValueError):
            ArmRetargeter(
                model=_model(),
                joint_names=("no_such_joint",),
                wrist_body="left_wrist_yaw_link",
            )

    def test_an_unknown_body_is_refused_at_construction(self) -> None:
        with self.assertRaises(ValueError):
            ArmRetargeter(
                model=_model(),
                joint_names=_LEFT_ARM_JOINTS,
                wrist_body="no_such_body",
            )


@unittest.skipUnless(
    (_DATASET / "meta" / "info.json").exists(),
    f"the published recordings are not present at {_DATASET}",
)
class PublishedRecordingsTest(unittest.TestCase):
    """The empirical claims, checked against the data they were measured on.

    These are the tests that make the module's constants facts rather than
    choices. They are skipped when the recordings are absent, because the
    alternative -- hardcoding the expected numbers -- would assert only that
    someone once typed them.
    """

    @classmethod
    def setUpClass(cls) -> None:
        pq = pytest.importorskip("pyarrow.parquet")
        episode = _DATASET / "data" / "chunk-000" / "episode_000000.parquet"
        if not episode.exists():  # pragma: no cover
            raise unittest.SkipTest("no episode parquet present")
        table = pq.read_table(episode).to_pydict()
        cls.left_ee = np.asarray(
            [np.asarray(v) for v in table["action.left_ee"]]
        )
        cls.left_arm = np.asarray(
            [np.asarray(v) for v in table["action.left_arm"]]
        )
        cls.retargeter = _retargeter()

    def test_the_recorded_joints_reproduce_the_recorded_pose(self) -> None:
        """The ground truth: the dataset's own two encodings must agree.

        Each frame carries both the joint vector and the end-effector pose, so
        forward kinematics through this module's tool offset and reference frame
        must map one onto the other. If it does not, the frame contract is
        wrong, and no amount of IK quality would fix it.
        """
        errors = []
        for index in range(0, len(self.left_arm), 60):
            pose = self.retargeter.forward(self.left_arm[index])
            recorded = self.left_ee[index]
            errors.append(
                float(
                    np.linalg.norm(
                        np.asarray(pose.position_m) - recorded[:3]
                    )
                )
            )

        self.assertLess(max(errors), 1e-3, f"worst frame off by {max(errors)} m")

    def test_the_recorded_rotation_is_extrinsic_xyz_euler(self) -> None:
        """The convention is a measurement, and a wrong one is tens of degrees."""
        worst = 0.0
        for index in range(0, len(self.left_arm), 60):
            pose = self.retargeter.forward(self.left_arm[index])
            recorded = self.left_ee[index]
            expected = _euler_xyz_matrix(recorded[3:6])
            relative = np.asarray(pose.rotation).T @ expected
            angle = float(
                np.arccos(
                    np.clip((np.trace(relative) - 1.0) / 2.0, -1.0, 1.0)
                )
            )
            worst = max(worst, np.degrees(angle))

        self.assertLess(worst, 2.0, f"worst frame off by {worst:.2f} degrees")

    def test_a_recorded_pose_is_solved_back_to_joints_that_reach_it(
        self,
    ) -> None:
        """The whole chain, on real numbers, warm-started as a chunk would be."""
        seed = tuple(self.left_arm[0])
        worst_position = 0.0
        worst_rotation = 0.0
        for index in range(0, 600, 50):
            if index >= len(self.left_arm):
                break
            recorded = self.left_ee[index]
            target = EndEffectorPose(
                position_m=tuple(recorded[:3]),
                rotation=_euler_xyz_matrix(recorded[3:6]),
            )
            result = self.retargeter.solve(target, seed)
            self.assertTrue(result.converged, result.detail)
            worst_position = max(worst_position, result.position_error_m)
            worst_rotation = max(worst_rotation, result.rotation_error_rad)
            seed = result.joint_positions_rad

        self.assertLess(worst_position, 1e-3)
        self.assertLess(worst_rotation, 1e-2)

    def test_the_column_layout_is_what_the_checkpoint_published(self) -> None:
        """The fingerprint that distinguishes columns from rows.

        Both readings are unit-norm and six-wide. The one that is right puts
        every recorded frame inside the checkpoint's own action envelope; the
        other puts almost none there.
        """
        statistics = (
            Path("/mnt/data-hdd/unifolm-vla/models/UnifoLM-VLA-Base")
            / "dataset_statistics.json"
        )
        if not statistics.exists():  # pragma: no cover
            self.skipTest("the checkpoint statistics are not present")
        stats = json.loads(statistics.read_text())["g1_stack_block"]["action"]
        low = np.asarray(stats["min"][3:9])
        high = np.asarray(stats["max"][3:9])

        inside = {"columns": 0, "rows": 0}
        total = 0
        for index in range(0, len(self.left_arm), 10):
            matrix = _euler_xyz_matrix(self.left_ee[index][3:6])
            total += 1
            for layout in inside:
                encoded = rotation_to_6d(matrix, layout)
                if np.all(encoded >= low) and np.all(encoded <= high):
                    inside[layout] += 1

        self.assertGreater(inside["columns"] / total, 0.95)
        self.assertLess(inside["rows"] / total, 0.5)
