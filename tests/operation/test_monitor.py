from __future__ import annotations

import unittest
from typing import Optional

from vegapunk.operation.monitor import (
    HOLD_LID_NOT_OPEN,
    LEFT_WRIST_ROLL,
    PASS,
    RIGHT_WRIST_ROLL,
    InstrumentMonitor,
    PourPosture,
)
from vegapunk.operation.target import (
    HAND_CLOSED,
    HAND_OPEN,
    STAND_BODY,
    WholeBodyTarget,
)
from vegapunk.operation.witness import (
    LID_CLOSED,
    LID_INDETERMINATE,
    LID_OPEN,
    IndependentWitness,
    LidReading,
)

_NOW = 1_000_000_000


class _FixedChannel:
    """A lid channel pinned to one value, with no timing behaviour."""

    identity = "fixed"

    def __init__(self, value: str) -> None:
        self.value = value

    def read(self) -> Optional[LidReading]:
        return LidReading(
            value=self.value,
            observed_at_ns=_NOW,
            source=self.identity,
            detail=f"reported {self.value}",
        )


def _witness(value: str) -> IndependentWitness:
    return IndependentWitness(
        _FixedChannel(value), max_age_s=10.0, dwell_s=0.0, clock_ns=lambda: _NOW
    )


def _target(
    *,
    left_hand: tuple[float, ...] = HAND_OPEN,
    right_hand: tuple[float, ...] = HAND_OPEN,
    left_roll: float = 0.0,
    right_roll: float = 0.0,
    sequence: int = 1,
) -> WholeBodyTarget:
    body = list(STAND_BODY)
    body[LEFT_WRIST_ROLL] = left_roll
    body[RIGHT_WRIST_ROLL] = right_roll
    return WholeBodyTarget(
        sequence=sequence,
        source_time_ns=_NOW,
        valid_until_ns=_NOW + 100_000_000,
        body=tuple(body),
        left_hand=left_hand,
        right_hand=right_hand,
    )


class PourPostureTest(unittest.TestCase):
    def test_an_open_hand_is_never_pouring_however_rolled(self) -> None:
        posture = PourPosture()

        self.assertIsNone(posture.detect(_target(right_roll=1.9)))

    def test_a_grasping_hand_held_level_is_not_pouring(self) -> None:
        posture = PourPosture()

        self.assertIsNone(
            posture.detect(_target(right_hand=HAND_CLOSED, right_roll=0.0))
        )

    def test_either_hand_can_be_the_pouring_hand(self) -> None:
        posture = PourPosture()

        self.assertEqual(
            posture.detect(_target(right_hand=HAND_CLOSED, right_roll=1.2)),
            "right",
        )
        self.assertEqual(
            posture.detect(_target(left_hand=HAND_CLOSED, left_roll=-1.2)),
            "left",
        )

    def test_the_tilt_test_is_signed_agnostic(self) -> None:
        posture = PourPosture()

        self.assertEqual(
            posture.detect(_target(right_hand=HAND_CLOSED, right_roll=-1.2)),
            "right",
        )

    def test_posture_thresholds_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            PourPosture(grasp_closure_rad=0.0)
        with self.assertRaises(ValueError):
            PourPosture(pour_tilt_rad=-0.1)


class GateTest(unittest.TestCase):
    def test_a_pour_into_an_open_lid_passes(self) -> None:
        monitor = InstrumentMonitor(_witness(LID_OPEN))

        verdict = monitor.evaluate(_target(right_hand=HAND_CLOSED, right_roll=1.2))

        self.assertEqual(verdict.decision, PASS)
        self.assertFalse(verdict.holds)
        self.assertEqual(verdict.pouring_hand, "right")

    def test_a_pour_into_a_closed_lid_holds(self) -> None:
        monitor = InstrumentMonitor(_witness(LID_CLOSED))

        verdict = monitor.evaluate(_target(right_hand=HAND_CLOSED, right_roll=1.2))

        self.assertEqual(verdict.decision, HOLD_LID_NOT_OPEN)
        self.assertTrue(verdict.holds)
        self.assertEqual(verdict.lid, LID_CLOSED)

    def test_an_indeterminate_lid_holds_rather_than_guessing(self) -> None:
        monitor = InstrumentMonitor(_witness(LID_INDETERMINATE))

        verdict = monitor.evaluate(_target(right_hand=HAND_CLOSED, right_roll=1.2))

        self.assertEqual(verdict.decision, HOLD_LID_NOT_OPEN)
        self.assertEqual(verdict.lid, LID_INDETERMINATE)


class NonSequencingTest(unittest.TestCase):
    """The monitor must not become the thing that drives the robot."""

    def test_every_recoverable_frame_passes_regardless_of_lid_state(self) -> None:
        monitor = InstrumentMonitor(_witness(LID_CLOSED))

        walking = list(STAND_BODY)
        walking[0] = 0.4
        frames = (
            _target(),
            _target(right_hand=HAND_CLOSED),
            _target(left_hand=HAND_CLOSED, right_hand=HAND_CLOSED),
            WholeBodyTarget(
                sequence=9,
                source_time_ns=_NOW,
                valid_until_ns=_NOW + 100_000_000,
                body=tuple(walking),
                left_hand=HAND_OPEN,
                right_hand=HAND_CLOSED,
            ),
        )

        for frame in frames:
            self.assertEqual(monitor.evaluate(frame).decision, PASS)

    def test_the_witness_is_not_consulted_when_the_gate_is_not_in_play(self) -> None:
        class _CountingChannel(_FixedChannel):
            def __init__(self) -> None:
                super().__init__(LID_CLOSED)
                self.reads = 0

            def read(self) -> Optional[LidReading]:
                self.reads += 1
                return super().read()

        channel = _CountingChannel()
        monitor = InstrumentMonitor(
            IndependentWitness(
                channel, max_age_s=10.0, dwell_s=0.0, clock_ns=lambda: _NOW
            )
        )

        monitor.evaluate(_target())
        monitor.evaluate(_target(right_hand=HAND_CLOSED))

        self.assertEqual(channel.reads, 0)

    def test_the_monitor_holds_no_progress_state(self) -> None:
        monitor = InstrumentMonitor(_witness(LID_CLOSED))
        pour = _target(right_hand=HAND_CLOSED, right_roll=1.2)

        first = monitor.evaluate(pour)
        second = monitor.evaluate(pour)

        self.assertEqual(first.decision, second.decision)
        self.assertEqual(monitor.evaluate(_target()).decision, PASS)

    def test_the_monitor_reports_the_witness_identity_for_the_record(self) -> None:
        monitor = InstrumentMonitor(_witness(LID_OPEN))

        self.assertEqual(monitor.witness_identity, "fixed")


if __name__ == "__main__":
    unittest.main()
