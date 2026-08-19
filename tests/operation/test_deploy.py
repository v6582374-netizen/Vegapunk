from __future__ import annotations

import json
import unittest

from vegapunk.operation.deploy import TrackerLoopAdapter
from vegapunk.operation.target import (
    BODY_DIM,
    HAND_DIM,
    STAND_BODY,
    WholeBodyTarget,
)
from vegapunk.operation.tracker import (
    LAPSE_ABSENT,
    LAPSE_EXPIRED,
    LAPSE_NONE,
    RedisTrackerTransport,
    STATE_ENVELOPE_KEY,
)

_NOW = 5_000_000_000
_PERIOD_NS = 20_000_000


class FakePipeline:
    def __init__(self, store: dict) -> None:
        self._store = store
        self._ops: list[tuple] = []

    def set(self, key: str, value: str):
        self._ops.append(("set", key, value))
        return self

    def get(self, key: str):
        self._ops.append(("get", key))
        return self

    def execute(self) -> list:
        out = []
        for op in self._ops:
            if op[0] == "set":
                self._store[op[1]] = op[2]
                out.append(True)
            else:
                out.append(self._store.get(op[1]))
        self._ops = []
        return out


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self.store)


class BrokenRedis:
    def pipeline(self):
        raise ConnectionError("redis is gone")


def _frame(sequence: int, now_ns: int = _NOW, *, walking: bool = True) -> WholeBodyTarget:
    body = list(STAND_BODY)
    if walking:
        body[0] = 0.4
    return WholeBodyTarget(
        sequence=sequence,
        source_time_ns=now_ns,
        valid_until_ns=now_ns + 3 * _PERIOD_NS,
        body=tuple(body),
        left_hand=(0.0,) * HAND_DIM,
        right_hand=(0.0,) * HAND_DIM,
    )


class ShapeTest(unittest.TestCase):
    def test_it_returns_the_vendored_shapes(self) -> None:
        redis = FakeRedis()
        RedisTrackerTransport(redis).commit(_frame(1))
        adapter = TrackerLoopAdapter(redis, clock_ns=lambda: _NOW)

        body, left, right, holding = adapter.next_target()

        self.assertEqual(len(body), BODY_DIM)
        self.assertEqual(len(left), HAND_DIM)
        self.assertEqual(len(right), HAND_DIM)
        self.assertFalse(holding)
        self.assertEqual(adapter.last_lapse, LAPSE_NONE)

    def test_a_live_frame_is_passed_through_unchanged(self) -> None:
        redis = FakeRedis()
        frame = _frame(1)
        RedisTrackerTransport(redis).commit(frame)
        adapter = TrackerLoopAdapter(redis, clock_ns=lambda: _NOW)

        body, _, _, _ = adapter.next_target()

        self.assertEqual(tuple(body), frame.body)


class NeverRaisesTest(unittest.TestCase):
    """The whole reason this adapter exists: the loop must never die."""

    def test_an_empty_wire_holds_instead_of_raising(self) -> None:
        adapter = TrackerLoopAdapter(FakeRedis(), clock_ns=lambda: _NOW)

        body, _, _, holding = adapter.next_target()

        self.assertTrue(holding)
        self.assertEqual(adapter.last_lapse, LAPSE_ABSENT)
        self.assertEqual(tuple(body), STAND_BODY)

    def test_unparseable_values_hold_instead_of_raising(self) -> None:
        redis = FakeRedis()
        redis.store["action_body_unitree_g1_with_hands"] = "{not json"
        adapter = TrackerLoopAdapter(redis, clock_ns=lambda: _NOW)

        _, _, _, holding = adapter.next_target()

        self.assertTrue(holding)

    def test_an_unreachable_transport_holds_instead_of_raising(self) -> None:
        adapter = TrackerLoopAdapter(BrokenRedis(), clock_ns=lambda: _NOW)

        body, _, _, holding = adapter.next_target()

        self.assertTrue(holding)
        self.assertEqual(tuple(body), STAND_BODY)

    def test_a_stale_resident_frame_stops_the_walk(self) -> None:
        """The vendored keys have no TTL, so a dead producer looks alive."""
        redis = FakeRedis()
        RedisTrackerTransport(redis).commit(_frame(1, walking=True))
        later = _NOW + 10 * _PERIOD_NS
        adapter = TrackerLoopAdapter(redis, clock_ns=lambda: later)

        body, _, _, holding = adapter.next_target()

        self.assertTrue(holding)
        self.assertEqual(adapter.last_lapse, LAPSE_EXPIRED)
        self.assertEqual(body[0], 0.0)


class LatchTest(unittest.TestCase):
    def test_a_hold_latches_until_a_named_human_clears_it(self) -> None:
        redis = FakeRedis()
        clock = {"now": _NOW}
        adapter = TrackerLoopAdapter(redis, clock_ns=lambda: clock["now"])

        adapter.next_target()
        self.assertTrue(adapter.holding)

        RedisTrackerTransport(redis).commit(_frame(9))
        _, _, _, holding = adapter.next_target()
        self.assertTrue(holding, "a fresh frame must not silently re-arm")

        adapter.clear_hold("Wei")
        RedisTrackerTransport(redis).commit(_frame(10))
        _, _, _, holding = adapter.next_target()
        self.assertFalse(holding)

    def test_code_cannot_clear_a_hold_anonymously(self) -> None:
        adapter = TrackerLoopAdapter(FakeRedis(), clock_ns=lambda: _NOW)
        adapter.next_target()

        with self.assertRaises(ValueError):
            adapter.clear_hold("  ")

    def test_holds_are_counted_for_the_record(self) -> None:
        adapter = TrackerLoopAdapter(FakeRedis(), clock_ns=lambda: _NOW)

        for _ in range(4):
            adapter.next_target()

        self.assertEqual(adapter.tick_count, 4)
        self.assertEqual(adapter.hold_ticks, 4)


class StatePublishTest(unittest.TestCase):
    def test_state_carries_the_alignment_fields_the_vendored_path_omits(
        self,
    ) -> None:
        redis = FakeRedis()
        adapter = TrackerLoopAdapter(redis, clock_ns=lambda: _NOW)

        adapter.publish_state(
            [0.0] * 34, [0.0] * HAND_DIM, [0.0] * HAND_DIM,
            applied_target_sequence=12,
        )

        envelope = json.loads(redis.store[STATE_ENVELOPE_KEY])
        self.assertEqual(envelope["applied_target_sequence"], 12)
        self.assertEqual(envelope["state_time_ns"], _NOW)

    def test_malformed_feedback_is_dropped_not_raised(self) -> None:
        redis = FakeRedis()
        adapter = TrackerLoopAdapter(redis, clock_ns=lambda: _NOW)

        adapter.publish_state([0.0] * 3, [0.0] * HAND_DIM, [0.0] * HAND_DIM)

        self.assertNotIn(STATE_ENVELOPE_KEY, redis.store)

    def test_an_unreachable_transport_does_not_raise_on_feedback(self) -> None:
        adapter = TrackerLoopAdapter(BrokenRedis(), clock_ns=lambda: _NOW)

        adapter.publish_state([0.0] * 34, [0.0] * HAND_DIM, [0.0] * HAND_DIM)


if __name__ == "__main__":
    unittest.main()
