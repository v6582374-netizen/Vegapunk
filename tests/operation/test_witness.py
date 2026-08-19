from __future__ import annotations

import unittest
from typing import Optional

from vegapunk.operation.witness import (
    LID_CLOSED,
    LID_INDETERMINATE,
    LID_OPEN,
    GeometricWitness,
    IndependentWitness,
    SwitchWitness,
    LidReading,
    RegionTest,
)

_NOW = 1_000_000_000
_MS = 1_000_000


class _Clock:
    def __init__(self, now_ns: int = _NOW) -> None:
        self.now_ns = now_ns

    def __call__(self) -> int:
        return self.now_ns

    def advance_ms(self, ms: float) -> None:
        self.now_ns += int(ms * _MS)


class _StubChannel:
    identity = "stub"

    def __init__(self) -> None:
        self.reading: Optional[LidReading] = None

    def read(self) -> Optional[LidReading]:
        return self.reading


def _reading(value: str, at_ns: int) -> LidReading:
    return LidReading(value=value, observed_at_ns=at_ns, source="stub", detail=value)


class ReadingTest(unittest.TestCase):
    def test_a_reading_must_carry_one_of_the_three_values(self) -> None:
        with self.assertRaises(ValueError):
            LidReading(value="probably_open", observed_at_ns=_NOW, source="stub")


class InstrumentReportTest(unittest.TestCase):
    def test_a_reported_lid_becomes_open_or_closed(self) -> None:
        clock = _Clock()
        self.assertEqual(
            SwitchWitness(lambda: True, clock_ns=clock).read().value,
            LID_OPEN,
        )
        self.assertEqual(
            SwitchWitness(lambda: False, clock_ns=clock).read().value,
            LID_CLOSED,
        )

    def test_an_interface_that_answers_nothing_is_indeterminate(self) -> None:
        witness = SwitchWitness(lambda: None, clock_ns=_Clock())

        self.assertEqual(witness.read().value, LID_INDETERMINATE)

    def test_a_failing_probe_is_indeterminate_rather_than_an_exception(self) -> None:
        def probe() -> Optional[bool]:
            raise OSError("serial line dropped")

        witness = SwitchWitness(probe, clock_ns=_Clock())

        reading = witness.read()
        self.assertEqual(reading.value, LID_INDETERMINATE)
        self.assertIn("probe failed", reading.detail)


class RegionTestTest(unittest.TestCase):
    def _test(self) -> RegionTest:
        return RegionTest(
            row_span=(0, 2),
            column_span=(0, 2),
            open_at_or_above=200.0,
            closed_at_or_below=50.0,
            witness_pose_digest="bench-cam-pose-1",
        )

    def test_the_thresholds_must_leave_an_indeterminate_gap(self) -> None:
        with self.assertRaises(ValueError):
            RegionTest(
                row_span=(0, 2),
                column_span=(0, 2),
                open_at_or_above=100.0,
                closed_at_or_below=100.0,
                witness_pose_digest="bench-cam-pose-1",
            )

    def test_a_region_test_must_name_the_pose_it_was_calibrated_for(self) -> None:
        with self.assertRaises(ValueError):
            RegionTest(
                row_span=(0, 2),
                column_span=(0, 2),
                open_at_or_above=200.0,
                closed_at_or_below=50.0,
                witness_pose_digest="  ",
            )

    def test_a_value_between_the_thresholds_is_indeterminate(self) -> None:
        value, detail = self._test().classify(120.0)

        self.assertEqual(value, LID_INDETERMINATE)
        self.assertIn("ambiguous band", detail)

    def test_a_frame_too_small_for_the_region_is_indeterminate(self) -> None:
        test = self._test()

        self.assertIsNone(test.statistic([[0.0, 0.0]]))
        self.assertEqual(test.classify(None)[0], LID_INDETERMINATE)

    def test_the_bright_and_dark_extremes_resolve(self) -> None:
        test = self._test()
        bright = [[255.0, 255.0], [255.0, 255.0]]
        dark = [[10.0, 10.0], [10.0, 10.0]]

        self.assertEqual(test.classify(test.statistic(bright))[0], LID_OPEN)
        self.assertEqual(test.classify(test.statistic(dark))[0], LID_CLOSED)


class GeometricWitnessTest(unittest.TestCase):
    def _test(self) -> RegionTest:
        return RegionTest(
            row_span=(0, 2),
            column_span=(0, 2),
            open_at_or_above=200.0,
            closed_at_or_below=50.0,
            witness_pose_digest="bench-cam-pose-1",
        )

    def test_a_missing_frame_is_indeterminate(self) -> None:
        witness = GeometricWitness(lambda: None, self._test(), clock_ns=_Clock())

        self.assertEqual(witness.read().value, LID_INDETERMINATE)

    def test_a_failing_grab_is_indeterminate(self) -> None:
        def grab():  # noqa: ANN202
            raise RuntimeError("camera unplugged")

        witness = GeometricWitness(grab, self._test(), clock_ns=_Clock())

        self.assertEqual(witness.read().value, LID_INDETERMINATE)

    def test_the_witness_carries_its_pose_digest(self) -> None:
        witness = GeometricWitness(lambda: None, self._test())

        self.assertEqual(witness.witness_pose_digest, "bench-cam-pose-1")


class FreshnessTest(unittest.TestCase):
    def test_a_stale_reading_is_indeterminate_not_the_last_known_value(self) -> None:
        clock = _Clock()
        channel = _StubChannel()
        witness = IndependentWitness(
            channel, max_age_s=0.5, dwell_s=0.0, clock_ns=clock
        )
        channel.reading = _reading(LID_OPEN, clock.now_ns)
        self.assertEqual(witness.observe().value, LID_OPEN)

        clock.advance_ms(900)
        verdict = witness.observe()

        self.assertEqual(verdict.value, LID_INDETERMINATE)
        self.assertIn("freshness bound", verdict.detail)

    def test_a_channel_producing_nothing_is_indeterminate(self) -> None:
        channel = _StubChannel()
        witness = IndependentWitness(channel, clock_ns=_Clock())

        self.assertEqual(witness.observe().value, LID_INDETERMINATE)

    def test_max_age_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            IndependentWitness(_StubChannel(), max_age_s=0.0)


class DwellTest(unittest.TestCase):
    def test_a_single_frame_does_not_settle_a_new_value(self) -> None:
        clock = _Clock()
        channel = _StubChannel()
        witness = IndependentWitness(
            channel, max_age_s=1.0, dwell_s=0.3, clock_ns=clock
        )
        channel.reading = _reading(LID_OPEN, clock.now_ns)

        verdict = witness.observe()

        self.assertEqual(verdict.value, LID_INDETERMINATE)
        self.assertIn("dwell", verdict.detail)

    def test_a_value_held_through_the_dwell_settles(self) -> None:
        clock = _Clock()
        channel = _StubChannel()
        witness = IndependentWitness(
            channel, max_age_s=1.0, dwell_s=0.3, clock_ns=clock
        )
        channel.reading = _reading(LID_OPEN, clock.now_ns)
        witness.observe()

        clock.advance_ms(400)
        channel.reading = _reading(LID_OPEN, clock.now_ns)
        verdict = witness.observe()

        self.assertEqual(verdict.value, LID_OPEN)
        self.assertTrue(verdict.determinate)
        self.assertTrue(verdict.open)

    def test_a_flicker_resets_the_dwell(self) -> None:
        clock = _Clock()
        channel = _StubChannel()
        witness = IndependentWitness(
            channel, max_age_s=1.0, dwell_s=0.3, clock_ns=clock
        )
        channel.reading = _reading(LID_OPEN, clock.now_ns)
        witness.observe()

        clock.advance_ms(200)
        channel.reading = _reading(LID_CLOSED, clock.now_ns)
        witness.observe()
        clock.advance_ms(200)
        channel.reading = _reading(LID_OPEN, clock.now_ns)
        verdict = witness.observe()

        self.assertEqual(verdict.value, LID_INDETERMINATE)

    def test_an_indeterminate_reading_unsettles_a_settled_value(self) -> None:
        clock = _Clock()
        channel = _StubChannel()
        witness = IndependentWitness(
            channel, max_age_s=1.0, dwell_s=0.0, clock_ns=clock
        )
        channel.reading = _reading(LID_OPEN, clock.now_ns)
        self.assertTrue(witness.observe().open)

        channel.reading = _reading(LID_INDETERMINATE, clock.now_ns)
        verdict = witness.observe()

        self.assertEqual(verdict.value, LID_INDETERMINATE)
        self.assertFalse(verdict.open)

    def test_the_witness_reports_its_channel_identity(self) -> None:
        witness = IndependentWitness(_StubChannel())

        self.assertEqual(witness.identity, "stub")


if __name__ == "__main__":
    unittest.main()
