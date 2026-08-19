from __future__ import annotations

import unittest
from datetime import datetime, timezone

from vegapunk.operation.bridge import (
    ACCEPTED,
    REFUSED_SATURATED,
    SUSTAINED_SATURATION_PERIODS,
    REFUSED_LATCHED,
    REFUSED_NO_AUTHORITY,
    REFUSED_OUT_OF_ORDER,
    REFUSED_STALE,
    MotionGrant,
    TargetBridge,
)
from vegapunk.operation.target import (
    CONTROL_PERIOD_S,
    HAND_CLOSED,
    HAND_OPEN,
    STAND_BODY,
    WholeBodyTarget,
)

_NOW = 1_000_000_000
_PERIOD_NS = int(CONTROL_PERIOD_S * 1e9)
_CONFIG = "config-digest-1"


class _RecordingTransport:
    def __init__(self) -> None:
        self.committed: list[WholeBodyTarget] = []
        self.state = None

    def commit(self, target: WholeBodyTarget) -> None:
        self.committed.append(target)

    def read_state(self):  # noqa: ANN201 - protocol shape
        return self.state


def _grant(configuration_digest: str = _CONFIG) -> MotionGrant:
    return MotionGrant(
        authorized_by="operator-a",
        statement="instrument loop pilot, guardian at the stop",
        granted_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        configuration_digest=configuration_digest,
    )


def _target(**overrides: object) -> WholeBodyTarget:
    fields: dict[str, object] = {
        "sequence": 1,
        "source_time_ns": _NOW,
        "valid_until_ns": _NOW + 3 * _PERIOD_NS,
        "body": STAND_BODY,
        "left_hand": HAND_OPEN,
        "right_hand": HAND_OPEN,
    }
    fields.update(overrides)
    return WholeBodyTarget(**fields)  # type: ignore[arg-type]


def _bridge(
    transport: _RecordingTransport, *, granted: bool = True
) -> TargetBridge:
    bridge = TargetBridge(
        transport,
        _CONFIG,
        grant=_grant() if granted else None,
        clock_ns=lambda: _NOW,
    )
    return bridge


class AuthorityTest(unittest.TestCase):
    def test_without_a_grant_nothing_reaches_the_transport(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport, granted=False)

        result = bridge.publish(_target())

        self.assertEqual(result.verdict, REFUSED_NO_AUTHORITY)
        self.assertEqual(transport.committed, [])

    def test_a_grant_must_name_this_configuration(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport, granted=False)

        with self.assertRaises(ValueError):
            bridge.grant_authority(_grant("a-different-room"))

    def test_a_grant_must_name_a_human(self) -> None:
        with self.assertRaises(ValueError):
            MotionGrant(
                authorized_by="  ",
                statement="something",
                granted_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
                configuration_digest=_CONFIG,
            )

    def test_a_grant_must_state_what_was_authorized(self) -> None:
        with self.assertRaises(ValueError):
            MotionGrant(
                authorized_by="operator-a",
                statement="   ",
                granted_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
                configuration_digest=_CONFIG,
            )

    def test_withdrawing_authority_stops_publication(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport)
        bridge.publish(_target(sequence=1))

        bridge.withdraw_authority()
        result = bridge.publish(_target(sequence=2))

        self.assertEqual(result.verdict, REFUSED_NO_AUTHORITY)
        self.assertEqual(len(transport.committed), 1)


class ValidityTest(unittest.TestCase):
    def test_an_authorized_fresh_ordered_frame_is_committed(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport)

        result = bridge.publish(_target())

        self.assertEqual(result.verdict, ACCEPTED)
        self.assertTrue(result.published)
        self.assertEqual(len(transport.committed), 1)

    def test_a_replayed_sequence_is_refused(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport)
        bridge.publish(_target(sequence=5))

        result = bridge.publish(_target(sequence=5))

        self.assertEqual(result.verdict, REFUSED_OUT_OF_ORDER)
        self.assertEqual(len(transport.committed), 1)

    def test_a_frame_that_expired_before_publication_is_refused(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport)

        result = bridge.publish(
            _target(source_time_ns=_NOW - 10 * _PERIOD_NS, valid_until_ns=_NOW - 1)
        )

        self.assertEqual(result.verdict, REFUSED_STALE)
        self.assertEqual(transport.committed, [])

    def test_reading_state_needs_no_authority(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport, granted=False)

        self.assertIsNone(bridge.read_state())


class HoldTest(unittest.TestCase):
    def test_a_hold_publishes_a_stand_target_rather_than_withholding(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport)

        result = bridge.hold("monitor refused the pour gate")

        self.assertEqual(result.verdict, ACCEPTED)
        self.assertEqual(len(transport.committed), 1)
        self.assertEqual(transport.committed[0].body, STAND_BODY)

    def test_a_hold_keeps_the_last_commanded_aperture(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport)
        bridge.publish(_target(left_hand=HAND_CLOSED))

        bridge.hold("operator intervened")

        self.assertEqual(transport.committed[-1].left_hand, HAND_CLOSED)

    def test_a_hold_works_with_no_grant_installed(self) -> None:
        """Refusing to stop because nobody authorised stopping is worse."""
        transport = _RecordingTransport()
        bridge = _bridge(transport, granted=False)

        result = bridge.hold("estop path exercised")

        self.assertEqual(result.verdict, ACCEPTED)
        self.assertEqual(len(transport.committed), 1)

    def test_a_hold_latches_and_later_frames_are_refused(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport)
        bridge.hold("lid not open")

        result = bridge.publish(_target(sequence=50))

        self.assertEqual(result.verdict, REFUSED_LATCHED)
        self.assertTrue(bridge.latched)

    def test_a_hold_must_record_why(self) -> None:
        bridge = _bridge(_RecordingTransport())

        with self.assertRaises(ValueError):
            bridge.hold("   ")

    def test_clearing_a_latch_requires_a_named_human_and_a_statement(self) -> None:
        bridge = _bridge(_RecordingTransport())
        bridge.hold("lid not open")

        with self.assertRaises(ValueError):
            bridge.clear_latch("", "checked the lid")
        with self.assertRaises(ValueError):
            bridge.clear_latch("operator-a", "")
        self.assertTrue(bridge.latched)

    def test_a_cleared_latch_lets_new_frames_through(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport)
        bridge.hold("lid not open")

        bridge.clear_latch("operator-a", "reset the instrument and the cup")
        result = bridge.publish(_target(sequence=50))

        self.assertEqual(result.verdict, ACCEPTED)
        self.assertFalse(bridge.latched)

    def test_the_latch_records_the_first_reason_not_the_last(self) -> None:
        bridge = _bridge(_RecordingTransport())

        bridge.hold("lid not open")
        bridge.hold("a later, derivative hold")

        self.assertEqual(bridge.latch_reason, "lid not open")


class BookkeepingTest(unittest.TestCase):
    def test_the_bridge_counts_what_it_published_and_refused(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport)

        bridge.publish(_target(sequence=1))
        bridge.publish(_target(sequence=1))
        bridge.publish(_target(sequence=2))

        self.assertEqual(bridge.published_count, 2)
        self.assertEqual(bridge.refused_count, 1)

    def test_a_bridge_must_know_its_configuration(self) -> None:
        with self.assertRaises(ValueError):
            TargetBridge(_RecordingTransport(), "   ")


class SustainedSaturationTest(unittest.TestCase):
    """A clamp is information. A run of clamps is a producer out of control."""

    @staticmethod
    def _runaway(sequence: int) -> WholeBodyTarget:
        body = list(STAND_BODY)
        body[0] = 5.0
        return _target(sequence=sequence, body=tuple(body))

    def test_an_isolated_clamped_frame_is_published(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport)

        result = bridge.publish(self._runaway(1))

        self.assertEqual(result.verdict, ACCEPTED)
        self.assertFalse(bridge.latched)

    def test_isolated_spikes_separated_by_clean_frames_never_trip(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport)

        sequence = 0
        for _ in range(SUSTAINED_SATURATION_PERIODS * 3):
            sequence += 1
            self.assertEqual(
                bridge.publish(self._runaway(sequence)).verdict, ACCEPTED
            )
            sequence += 1
            self.assertEqual(
                bridge.publish(_target(sequence=sequence)).verdict, ACCEPTED
            )

        self.assertFalse(bridge.latched)
        self.assertEqual(bridge.longest_saturated_run, 1)

    def test_a_sustained_run_of_clamps_trips_and_holds(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport)

        verdicts = [
            bridge.publish(self._runaway(sequence)).verdict
            for sequence in range(1, SUSTAINED_SATURATION_PERIODS + 1)
        ]

        self.assertEqual(
            verdicts[: SUSTAINED_SATURATION_PERIODS - 1],
            [ACCEPTED] * (SUSTAINED_SATURATION_PERIODS - 1),
        )
        self.assertEqual(verdicts[-1], REFUSED_SATURATED)
        self.assertTrue(bridge.latched)

    def test_the_trip_leaves_a_stand_hold_on_the_wire(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport)

        for sequence in range(1, SUSTAINED_SATURATION_PERIODS + 1):
            bridge.publish(self._runaway(sequence))

        self.assertEqual(transport.committed[-1].body, STAND_BODY)
        self.assertTrue(transport.committed[-1].is_stationary())

    def test_the_trip_names_the_channel_that_was_clamped(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport)

        for sequence in range(1, SUSTAINED_SATURATION_PERIODS + 1):
            bridge.publish(self._runaway(sequence))

        self.assertIn("speed", bridge.latch_reason)

    def test_after_the_trip_every_frame_is_refused(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport)

        for sequence in range(1, SUSTAINED_SATURATION_PERIODS + 1):
            bridge.publish(self._runaway(sequence))

        result = bridge.publish(_target(sequence=10_000))

        self.assertEqual(result.verdict, REFUSED_LATCHED)

    def test_a_clean_frame_resets_the_run(self) -> None:
        transport = _RecordingTransport()
        bridge = _bridge(transport)

        for sequence in range(1, SUSTAINED_SATURATION_PERIODS):
            bridge.publish(self._runaway(sequence))
        self.assertEqual(bridge.saturated_run, SUSTAINED_SATURATION_PERIODS - 1)

        bridge.publish(_target(sequence=SUSTAINED_SATURATION_PERIODS))

        self.assertEqual(bridge.saturated_run, 0)
        self.assertFalse(bridge.latched)


if __name__ == "__main__":
    unittest.main()
