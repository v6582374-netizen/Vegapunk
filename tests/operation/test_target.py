from __future__ import annotations

import unittest

from vegapunk.operation.target import (
    BODY_DIM,
    CONTROL_PERIOD_S,
    HAND_CLOSED,
    HAND_DIM,
    HAND_OPEN,
    G1_JOINT_LIMITS_RAD,
    MAX_ROOT_SPEED_MPS,
    ROOT_HEIGHT_RANGE_M,
    STAND_BODY,
    WholeBodyTarget,
    safe_hold_target,
)

_NOW = 1_000_000_000


def _target(**overrides: object) -> WholeBodyTarget:
    fields: dict[str, object] = {
        "sequence": 1,
        "source_time_ns": _NOW,
        "valid_until_ns": _NOW + 100_000_000,
        "body": STAND_BODY,
        "left_hand": HAND_OPEN,
        "right_hand": HAND_OPEN,
    }
    fields.update(overrides)
    return WholeBodyTarget(**fields)  # type: ignore[arg-type]


class ShapeTest(unittest.TestCase):
    def test_the_vendored_stand_target_is_a_valid_frame(self) -> None:
        target = _target()

        self.assertEqual(len(target.body), BODY_DIM)
        self.assertEqual(len(target.left_hand), HAND_DIM)
        self.assertTrue(target.is_stationary())

    def test_a_wrong_length_hand_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "right_hand must carry 6"):
            _target(right_hand=(0.0,) * 7)

    def test_a_wrong_length_body_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "body must carry 35"):
            _target(body=STAND_BODY[:-1])

    def test_a_non_finite_value_is_refused(self) -> None:
        body = list(STAND_BODY)
        body[8] = float("nan")
        with self.assertRaisesRegex(ValueError, "not finite"):
            _target(body=tuple(body))


class BoundsTest(unittest.TestCase):
    def test_an_unexecutable_joint_is_refused_at_construction(self) -> None:
        body = list(STAND_BODY)
        body[6] = 9.0
        with self.assertRaisesRegex(ValueError, "left_hip_pitch_joint"):
            _target(body=tuple(body))

    def test_root_speed_beyond_the_ceiling_is_clamped_and_recorded(self) -> None:
        """Not refused: root velocity is a finite difference of human motion.

        Isolated frames overshoot any ceiling through differentiation noise
        alone -- across the six recorded episodes the longest run above the
        ceiling is a single 20 ms frame. Refusing those would end an episode
        over noise. Clamping silently would hide a producer running away, so the
        clamp is recorded instead.
        """
        body = list(STAND_BODY)
        body[0] = MAX_ROOT_SPEED_MPS + 0.5

        target = _target(body=tuple(body))

        self.assertAlmostEqual(target.body[0], MAX_ROOT_SPEED_MPS)
        self.assertTrue(target.saturated)
        self.assertTrue(any("speed" in entry for entry in target.clamped))

    def test_clamping_speed_preserves_the_commanded_direction(self) -> None:
        """The ceiling is on the magnitude, so the heading must survive it.

        Clamping each axis independently would rotate the commanded direction --
        a robot asked to walk diagonally would be sent somewhere else at the one
        moment it was moving fastest.
        """
        body = list(STAND_BODY)
        body[0] = MAX_ROOT_SPEED_MPS
        body[1] = MAX_ROOT_SPEED_MPS

        target = _target(body=tuple(body))
        vx, vy = target.root_velocity_mps

        self.assertAlmostEqual((vx**2 + vy**2) ** 0.5, MAX_ROOT_SPEED_MPS)
        self.assertAlmostEqual(vx, vy)

    def test_a_crouch_below_the_height_range_is_clamped(self) -> None:
        body = list(STAND_BODY)
        body[2] = 0.2

        target = _target(body=tuple(body))

        self.assertAlmostEqual(target.body[2], ROOT_HEIGHT_RANGE_M[0])
        self.assertTrue(any("height" in entry for entry in target.clamped))

    def test_float_round_trip_noise_is_absorbed_without_a_clamp_record(
        self,
    ) -> None:
        """The recorded episodes' knee references are one ULP outside the limit.

        The vendored retargeter clamps to the joint limit and the JSON round
        trip perturbs the last bit, so real frames carry -0.08726700000000001
        against a limit of -0.087267. Refusing that would reject a quarter of
        every real teleoperation episode over the representation of a number;
        recording it as a clamp would fill the record with noise nobody reads.
        """
        low = G1_JOINT_LIMITS_RAD[3][0]
        body = list(STAND_BODY)
        body[6 + 3] = low - 1e-17

        target = _target(body=tuple(body))

        self.assertEqual(target.clamped, ())
        self.assertGreaterEqual(target.body[6 + 3], low)

    def test_a_joint_just_outside_its_limit_is_saturated_and_recorded(
        self,
    ) -> None:
        high = G1_JOINT_LIMITS_RAD[0][1]
        body = list(STAND_BODY)
        body[6] = high + 0.02

        target = _target(body=tuple(body))

        self.assertAlmostEqual(target.body[6], high)
        self.assertTrue(
            any("left_hip_pitch_joint" in entry for entry in target.clamped)
        )

    def test_a_joint_far_outside_its_limit_is_still_refused(self) -> None:
        """Beyond the margin it is an authoring error, not a numerical one.

        Saturating a knee commanded to 9 rad would hand the tracker a pose
        nobody intended while reporting success.
        """
        high = G1_JOINT_LIMITS_RAD[0][1]
        body = list(STAND_BODY)
        body[6] = high + 1.0

        with self.assertRaisesRegex(ValueError, "left_hip_pitch_joint"):
            _target(body=tuple(body))

    def test_a_hand_beyond_its_mechanical_range_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "left_hand"):
            _target(left_hand=(2.0, 0.0, 0.0, 0.0, 0.0, 0.0))

    def test_the_fully_closed_hand_is_executable(self) -> None:
        target = _target(left_hand=HAND_CLOSED, right_hand=HAND_CLOSED)

        self.assertEqual(target.left_hand, HAND_CLOSED)


class ClockTest(unittest.TestCase):
    def test_a_frame_that_expires_on_arrival_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "valid_until_ns must be after"):
            _target(valid_until_ns=_NOW)

    def test_expiry_is_asked_of_the_frame_not_assumed(self) -> None:
        target = _target(valid_until_ns=_NOW + 1_000)

        self.assertFalse(target.expired_at(_NOW))
        self.assertTrue(target.expired_at(_NOW + 1_000))

    def test_a_frame_carries_no_position_field(self) -> None:
        payload = _target().as_payload()

        self.assertEqual(
            set(payload),
            {
                "sequence",
                "source_time_ns",
                "valid_until_ns",
                "body",
                "left_hand",
                "right_hand",
                "clamped",
            },
        )


class SafeHoldTest(unittest.TestCase):
    def test_the_body_holds_the_vendored_stand_target(self) -> None:
        hold = safe_hold_target(sequence=7, now_ns=_NOW)

        self.assertEqual(hold.body, STAND_BODY)
        self.assertTrue(hold.is_stationary())

    def test_the_hands_keep_their_last_commanded_aperture(self) -> None:
        grasp = (1.5, 1.0, 1.4, 1.4, 1.4, 1.4)

        hold = safe_hold_target(
            sequence=7, now_ns=_NOW, left_hand=grasp, right_hand=grasp
        )

        self.assertEqual(hold.left_hand, grasp)
        self.assertEqual(hold.right_hand, grasp)

    def test_a_safe_hold_is_a_published_frame_with_its_own_expiry(self) -> None:
        hold = safe_hold_target(sequence=7, now_ns=_NOW, hold_periods=5)

        self.assertGreater(hold.valid_until_ns, hold.source_time_ns)
        self.assertAlmostEqual(
            (hold.valid_until_ns - hold.source_time_ns) / 1e9,
            5 * CONTROL_PERIOD_S,
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
