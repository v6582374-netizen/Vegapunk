from __future__ import annotations

import unittest
from typing import Optional

from vegapunk.operation.policy import (
    ActionChunk,
    Observation,
    PolicyServer,
    ReplayFastPolicy,
    SlowIntent,
)
from vegapunk.operation.target import (
    CONTROL_PERIOD_S,
    HAND_OPEN,
    STAND_BODY,
    WholeBodyTarget,
)
from vegapunk.operation.tracker import TrackerState

_NOW = 1_000_000_000
_PERIOD_NS = int(CONTROL_PERIOD_S * 1e9)


def _state() -> TrackerState:
    return TrackerState(
        sequence=1, state_time_ns=_NOW, body=(0.0,) * 34,
        left_hand=HAND_OPEN, right_hand=HAND_OPEN,
    )


def _observation(tick: int = 0) -> Observation:
    return Observation(
        time_ns=_NOW + tick * _PERIOD_NS,
        images={"head": object()},
        state=_state(),
    )


def _frame(sequence: int) -> WholeBodyTarget:
    return WholeBodyTarget(
        sequence=sequence,
        source_time_ns=_NOW,
        valid_until_ns=_NOW + 60_000_000,
        body=STAND_BODY,
        left_hand=HAND_OPEN,
        right_hand=HAND_OPEN,
    )


class _RaisingPolicy:
    def act(self, observation, intent, first_tick):  # type: ignore[no-untyped-def]
        raise RuntimeError("the checkpoint is not loaded")


class _CountingPolicy:
    """Produces valid chunks and counts how often it was asked."""

    def __init__(self, chunk_periods: int = 8) -> None:
        self.calls = 0
        self._chunk_periods = chunk_periods

    def act(self, observation, intent, first_tick):  # type: ignore[no-untyped-def]
        self.calls += 1
        frames = tuple(
            _frame(first_tick + offset) for offset in range(self._chunk_periods)
        )
        return ActionChunk(first_tick=first_tick, frames=frames)


class ObservationTest(unittest.TestCase):
    def test_an_observation_with_no_image_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            Observation(time_ns=_NOW, images={}, state=_state())

    def test_the_observation_carries_no_lid_field(self) -> None:
        # The gate's evidence must be unreachable from the policy's input, or
        # the policy learns to key on it.
        self.assertNotIn("lid", Observation.__dataclass_fields__)
        self.assertNotIn("witness", Observation.__dataclass_fields__)


class IntentTest(unittest.TestCase):
    def test_an_empty_intent_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            SlowIntent(latent=(), produced_at_ns=_NOW, sequence=1)

    def test_age_is_measured_from_production(self) -> None:
        intent = SlowIntent(latent=(1.0,), produced_at_ns=_NOW, sequence=1)

        self.assertAlmostEqual(intent.age_s(_NOW + 500_000_000), 0.5)

    def test_a_stale_intent_is_withheld_from_the_fast_policy(self) -> None:
        server = PolicyServer(_CountingPolicy(), intent_max_age_s=1.0)
        server.offer_intent(SlowIntent(latent=(1.0,), produced_at_ns=_NOW, sequence=1))

        self.assertIsNotNone(server.usable_intent(_NOW))
        self.assertIsNone(server.usable_intent(_NOW + 2_000_000_000))

    def test_an_older_intent_never_replaces_a_newer_one(self) -> None:
        server = PolicyServer(_CountingPolicy())
        server.offer_intent(SlowIntent(latent=(2.0,), produced_at_ns=_NOW, sequence=5))
        server.offer_intent(SlowIntent(latent=(1.0,), produced_at_ns=_NOW, sequence=4))

        usable = server.usable_intent(_NOW)
        assert usable is not None
        self.assertEqual(usable.sequence, 5)


class ChunkTest(unittest.TestCase):
    def test_an_empty_chunk_commands_nothing_and_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            ActionChunk(first_tick=0, frames=())

    def test_a_chunk_knows_the_ticks_it_covers(self) -> None:
        chunk = ActionChunk(first_tick=4, frames=(_frame(1), _frame(2)))

        self.assertEqual(chunk.last_tick, 5)
        self.assertTrue(chunk.covers(4))
        self.assertFalse(chunk.covers(6))


class ServingTest(unittest.TestCase):
    def test_every_tick_gets_a_frame_with_no_gaps(self) -> None:
        policy = ReplayFastPolicy([_frame(i) for i in range(60)], chunk_periods=8)
        server = PolicyServer(policy)

        sequences = []
        for tick in range(40):
            target, starved = server.step(_observation(tick))
            self.assertFalse(starved)
            sequences.append(target.sequence)

        self.assertEqual(sequences, list(range(40)))

    def test_inference_runs_far_less_often_than_the_control_loop(self) -> None:
        policy = _CountingPolicy(chunk_periods=8)
        server = PolicyServer(policy)

        for tick in range(40):
            server.step(_observation(tick))

        self.assertLess(policy.calls, 12)
        self.assertEqual(server.tick, 40)

    def test_a_policy_that_raises_produces_a_hold_rather_than_an_exception(
        self,
    ) -> None:
        server = PolicyServer(_RaisingPolicy())

        target, starved = server.step(_observation(0))

        self.assertTrue(starved)
        self.assertTrue(target.is_stationary())
        self.assertEqual(server.failure_count, 1)
        self.assertIn("RuntimeError", server.last_failure)

    def test_a_starved_tick_holds_instead_of_repeating_the_last_frame(self) -> None:
        policy = ReplayFastPolicy([_frame(i) for i in range(4)], chunk_periods=4)
        server = PolicyServer(policy)

        seen_hold = False
        for tick in range(12):
            target, starved = server.step(_observation(tick))
            if starved:
                seen_hold = True
                self.assertTrue(target.is_stationary())

        self.assertTrue(seen_hold)
        self.assertGreater(server.starved_ticks, 0)

    def test_the_hold_preserves_the_last_commanded_aperture(self) -> None:
        grasped = tuple([1.0] * 6)
        held = WholeBodyTarget(
            sequence=0, source_time_ns=_NOW, valid_until_ns=_NOW + 60_000_000,
            body=STAND_BODY, left_hand=grasped, right_hand=grasped,
        )
        policy = ReplayFastPolicy([held], chunk_periods=1)
        server = PolicyServer(policy)

        server.step(_observation(0))
        target, starved = server.step(_observation(1))

        self.assertTrue(starved)
        self.assertEqual(target.left_hand, grasped)
        self.assertEqual(target.right_hand, grasped)

    def test_refill_lead_must_be_at_least_one_tick(self) -> None:
        with self.assertRaises(ValueError):
            PolicyServer(_CountingPolicy(), refill_lead=0)


class ReplayPolicyTest(unittest.TestCase):
    def test_a_replay_needs_at_least_one_frame(self) -> None:
        with self.assertRaises(ValueError):
            ReplayFastPolicy([])

    def test_replay_ignores_its_observations_by_design(self) -> None:
        policy = ReplayFastPolicy([_frame(0), _frame(1)], chunk_periods=2)

        first = policy.act(_observation(0), None, 0)
        second = policy.act(_observation(5), None, 0)

        self.assertEqual(
            [frame.body for frame in first.frames],
            [frame.body for frame in second.frames],
        )


if __name__ == "__main__":
    unittest.main()
