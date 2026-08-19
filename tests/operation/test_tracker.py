from __future__ import annotations

import json
import unittest

from vegapunk.operation.target import (
    CONTROL_PERIOD_S,
    HAND_CLOSED,
    HAND_DIM,
    HAND_OPEN,
    STAND_BODY,
    WholeBodyTarget,
)
from vegapunk.operation.tracker import (
    LAPSE_ABSENT,
    LAPSE_EXPIRED,
    LAPSE_NONE,
    LAPSE_REGRESSED,
    STATE_BODY_DIM,
    TARGET_BODY_KEY,
    TARGET_ENVELOPE_KEY,
    TARGET_LEFT_HAND_KEY,
    TARGET_RIGHT_HAND_KEY,
    RedisTrackerTransport,
    TrackerLoopGuard,
    TrackerState,
)

_NOW = 1_000_000_000
_PERIOD_NS = int(CONTROL_PERIOD_S * 1e9)


class _FakePipeline:
    def __init__(self, store: dict[str, str]) -> None:
        self._store = store
        self._ops: list[tuple[str, str, str | None]] = []

    def set(self, key: str, value: str) -> None:
        self._ops.append(("set", key, value))

    def get(self, key: str) -> None:
        self._ops.append(("get", key, None))

    def execute(self) -> list[str | None]:
        results: list[str | None] = []
        for kind, key, value in self._ops:
            if kind == "set":
                self._store[key] = value  # type: ignore[assignment]
                results.append("OK")
            else:
                results.append(self._store.get(key))
        self._ops.clear()
        return results


class _FakeRedis:
    """A store with a real pipeline, so torn frames would be observable."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self.store)


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


class TransportTest(unittest.TestCase):
    def test_a_commit_writes_the_whole_actuation_set_and_an_envelope(self) -> None:
        redis = _FakeRedis()
        transport = RedisTrackerTransport(redis)

        transport.commit(_target())

        self.assertEqual(
            sorted(redis.store),
            sorted(
                [
                    TARGET_BODY_KEY,
                    TARGET_LEFT_HAND_KEY,
                    TARGET_RIGHT_HAND_KEY,
                    TARGET_ENVELOPE_KEY,
                ]
            ),
        )
        self.assertEqual(len(json.loads(redis.store[TARGET_BODY_KEY])), 35)

    def test_a_committed_frame_reads_back_identically(self) -> None:
        redis = _FakeRedis()
        transport = RedisTrackerTransport(redis)
        published = _target(sequence=7, left_hand=HAND_CLOSED)

        transport.commit(published)
        read = transport.read_target(_NOW)

        self.assertIsNotNone(read)
        assert read is not None
        self.assertEqual(read.sequence, 7)
        self.assertEqual(read.body, published.body)
        self.assertEqual(read.left_hand, HAND_CLOSED)

    def test_a_missing_key_reads_as_nothing_rather_than_raising(self) -> None:
        """The vendored path turns this into an exception, then a process exit."""
        redis = _FakeRedis()
        transport = RedisTrackerTransport(redis)
        transport.commit(_target())
        del redis.store[TARGET_LEFT_HAND_KEY]

        self.assertIsNone(transport.read_target(_NOW))

    def test_a_corrupt_value_reads_as_nothing_rather_than_raising(self) -> None:
        redis = _FakeRedis()
        transport = RedisTrackerTransport(redis)
        transport.commit(_target())
        redis.store[TARGET_BODY_KEY] = "not json"

        self.assertIsNone(transport.read_target(_NOW))

    def test_a_seven_value_hand_from_the_obsolete_producer_is_truncated(self) -> None:
        redis = _FakeRedis()
        transport = RedisTrackerTransport(redis)
        transport.commit(_target())
        redis.store[TARGET_LEFT_HAND_KEY] = json.dumps([0.0] * 7)

        read = transport.read_target(_NOW)

        self.assertIsNotNone(read)
        assert read is not None
        self.assertEqual(len(read.left_hand), HAND_DIM)

    def test_state_round_trips_with_the_alignment_fields(self) -> None:
        redis = _FakeRedis()
        transport = RedisTrackerTransport(redis)
        state = TrackerState(
            sequence=4,
            state_time_ns=_NOW,
            body=tuple([0.0] * STATE_BODY_DIM),
            left_hand=HAND_OPEN,
            right_hand=HAND_OPEN,
            applied_target_sequence=3,
        )

        transport.publish_state(state)
        read = transport.read_state()

        self.assertIsNotNone(read)
        assert read is not None
        self.assertEqual(read.sequence, 4)
        self.assertEqual(read.applied_target_sequence, 3)

    def test_state_feedback_of_the_wrong_width_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            TrackerState(
                sequence=1,
                state_time_ns=_NOW,
                body=(0.0, 0.0),
                left_hand=HAND_OPEN,
                right_hand=HAND_OPEN,
            )


class GuardTest(unittest.TestCase):
    def test_a_fresh_ordered_frame_is_executed_untouched(self) -> None:
        guard = TrackerLoopGuard()
        target = _target()

        verdict = guard.evaluate(target, _NOW)

        self.assertFalse(verdict.holding)
        self.assertEqual(verdict.lapse, LAPSE_NONE)
        self.assertIs(verdict.target, target)

    def test_an_absent_frame_holds_rather_than_returning_nothing(self) -> None:
        guard = TrackerLoopGuard()

        verdict = guard.evaluate(None, _NOW)

        self.assertTrue(verdict.holding)
        self.assertEqual(verdict.lapse, LAPSE_ABSENT)
        self.assertEqual(verdict.target.body, STAND_BODY)
        self.assertTrue(verdict.target.is_stationary())

    def test_an_expired_frame_holds_instead_of_being_ridden_out(self) -> None:
        guard = TrackerLoopGuard()
        walking = list(STAND_BODY)
        walking[0] = 0.4
        target = _target(body=tuple(walking))

        verdict = guard.evaluate(target, target.valid_until_ns + 1)

        self.assertTrue(verdict.holding)
        self.assertEqual(verdict.lapse, LAPSE_EXPIRED)
        self.assertTrue(verdict.target.is_stationary())

    def test_a_replayed_sequence_cannot_resurrect_an_old_intent(self) -> None:
        guard = TrackerLoopGuard()
        guard.evaluate(_target(sequence=5), _NOW)

        verdict = guard.evaluate(_target(sequence=5), _NOW)

        self.assertTrue(verdict.holding)
        self.assertEqual(verdict.lapse, LAPSE_REGRESSED)

    def test_the_hold_keeps_the_last_commanded_aperture(self) -> None:
        """Releasing a held vessel is irreversible; holding it is not."""
        guard = TrackerLoopGuard()
        guard.evaluate(_target(sequence=1, left_hand=HAND_CLOSED), _NOW)

        verdict = guard.evaluate(None, _NOW)

        self.assertEqual(verdict.target.left_hand, HAND_CLOSED)

    def test_a_hold_latches_and_fresh_frames_do_not_re_arm_it(self) -> None:
        guard = TrackerLoopGuard()
        guard.evaluate(None, _NOW)

        verdict = guard.evaluate(_target(sequence=99), _NOW)

        self.assertTrue(verdict.holding)
        self.assertTrue(guard.latched)

    def test_only_an_explicit_clear_re_arms_the_guard(self) -> None:
        guard = TrackerLoopGuard()
        guard.evaluate(None, _NOW)
        guard.clear_latch()

        verdict = guard.evaluate(_target(sequence=99), _NOW)

        self.assertFalse(verdict.holding)

    def test_the_hold_target_is_always_freshly_valid(self) -> None:
        """A hold that expired on arrival would trip the guard it came from."""
        guard = TrackerLoopGuard()

        verdict = guard.evaluate(None, _NOW)

        self.assertFalse(verdict.target.expired_at(_NOW))
        self.assertGreater(verdict.target.valid_until_ns, _NOW)

    def test_every_hold_carries_a_new_sequence(self) -> None:
        guard = TrackerLoopGuard()

        first = guard.evaluate(None, _NOW)
        second = guard.evaluate(None, _NOW + _PERIOD_NS)

        self.assertGreater(second.target.sequence, first.target.sequence)

    def test_the_guard_records_why_it_latched(self) -> None:
        guard = TrackerLoopGuard()

        guard.evaluate(None, _NOW)

        self.assertIn(LAPSE_ABSENT, guard.latch_reason)


if __name__ == "__main__":
    unittest.main()
