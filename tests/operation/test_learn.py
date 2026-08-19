from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vegapunk.operation.dataset import ALIGNED_BY_CLOCK, ConversionReport, TrainingSample
from vegapunk.operation.learn import (
    ACTION_DIM,
    PROJECTION_ALARM_RAD,
    STATE_DIM,
    ChunkDataset,
    ImageEncoder,
    LearnedFastPolicy,
    Normalizer,
    TrainingConfig,
    TrainingResult,
    save_checkpoint,
    train,
)
from vegapunk.operation.policy import Observation, PolicyServer
from vegapunk.operation.target import (
    BODY_DIM,
    HAND_DIM,
    HAND_OPEN,
    STAND_BODY,
    WholeBodyTarget,
)
from vegapunk.operation.tracker import STATE_BODY_DIM, TrackerState

_NOW = 1_000_000_000
_PERIOD_NS = 20_000_000


def _state(sequence: int = 0, lean: float = 0.0) -> TrackerState:
    body = [0.0] * STATE_BODY_DIM
    body[3] = lean
    return TrackerState(
        sequence=sequence,
        state_time_ns=_NOW + sequence * _PERIOD_NS,
        body=tuple(body),
        left_hand=HAND_OPEN,
        right_hand=HAND_OPEN,
        applied_target_sequence=sequence,
    )


def _frame(sequence: int, *, knee: float = 0.4) -> WholeBodyTarget:
    body = list(STAND_BODY)
    body[9] = knee
    return WholeBodyTarget(
        sequence=sequence,
        source_time_ns=_NOW + sequence * _PERIOD_NS,
        valid_until_ns=_NOW + (sequence + 3) * _PERIOD_NS,
        body=tuple(body),
        left_hand=HAND_OPEN,
        right_hand=HAND_OPEN,
    )


def _sample(episode: str, index: int, horizon: int = 4) -> TrainingSample:
    return TrainingSample(
        episode_id=episode,
        index=index,
        time_ns=_NOW + index * _PERIOD_NS,
        images={"head": f"rgb/{index:06d}.jpg"},
        state=_state(index, lean=0.01 * index),
        chunk=tuple(
            _frame(index + offset, knee=0.4 + 0.01 * offset)
            for offset in range(horizon)
        ),
        alignment=ALIGNED_BY_CLOCK,
    )


def _samples(episodes: int = 3, per_episode: int = 24) -> list[TrainingSample]:
    return [
        _sample(f"episode_{number}", index)
        for number in range(episodes)
        for index in range(per_episode)
    ]


class NormalizerTest(unittest.TestCase):
    def test_a_constant_channel_gets_the_floor_not_a_zero_scale(self) -> None:
        normalizer = Normalizer.fit([[1.0, 5.0], [1.0, 7.0]])

        self.assertGreater(normalizer.scale[0], 0.0)

    def test_normalize_and_denormalize_round_trip(self) -> None:
        normalizer = Normalizer.fit([[0.0, 10.0], [2.0, 20.0], [4.0, 30.0]])

        original = [3.0, 25.0]
        restored = normalizer.denormalize(normalizer.normalize(original))

        for expected, actual in zip(original, restored):
            self.assertAlmostEqual(expected, actual, places=6)

    def test_statistics_survive_a_payload_round_trip(self) -> None:
        normalizer = Normalizer.fit([[1.0, 2.0], [3.0, 8.0]])

        restored = Normalizer.from_payload(dict(normalizer.as_payload()))

        self.assertEqual(restored.mean, normalizer.mean)
        self.assertEqual(restored.scale, normalizer.scale)


class DatasetTest(unittest.TestCase):
    def test_the_flattened_widths_match_the_contract(self) -> None:
        dataset = ChunkDataset(_samples(), horizon=4)

        self.assertEqual(dataset.observation_dim, STATE_DIM)
        self.assertEqual(dataset.output_dim, 4 * ACTION_DIM)

    def test_a_horizon_longer_than_every_chunk_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "no sample carries a chunk"):
            ChunkDataset(_samples(), horizon=99)

    def test_the_validation_split_holds_out_whole_episodes(self) -> None:
        samples = _samples(episodes=4, per_episode=10)
        dataset = ChunkDataset(samples, horizon=4)

        train_indices, validation_indices = dataset.split_by_episode(0.25)

        train_episodes = {samples[i].episode_id for i in train_indices}
        validation_episodes = {samples[i].episode_id for i in validation_indices}
        self.assertTrue(validation_episodes)
        self.assertFalse(train_episodes & validation_episodes)

    def test_image_features_widen_the_observation(self) -> None:
        dataset = ChunkDataset(
            _samples(), horizon=4, encoder=ImageEncoder(feature_dim=8)
        )

        self.assertEqual(dataset.observation_dim, STATE_DIM + 8)


class DeployabilityTest(unittest.TestCase):
    def test_a_provenance_gap_makes_a_result_undeployable(self) -> None:
        result = TrainingResult(
            config=TrainingConfig(horizon=4),
            train_losses=[0.001],
            validation_losses=[0.001],
            provenance_gaps=["no measured outcomes"],
        )

        deployable, why = result.deployable
        self.assertFalse(deployable)
        self.assertIn("no measured outcomes", why)

    def test_a_low_loss_cannot_buy_deployability(self) -> None:
        result = TrainingResult(
            config=TrainingConfig(horizon=4),
            train_losses=[1e-9],
            validation_losses=[1e-9],
            provenance_gaps=["no lid witness value was recorded"],
        )

        self.assertFalse(result.deployable[0])

    def test_no_held_out_episode_is_also_undeployable(self) -> None:
        result = TrainingResult(
            config=TrainingConfig(horizon=4),
            train_losses=[0.01],
            validation_losses=[],
        )

        deployable, why = result.deployable
        self.assertFalse(deployable)
        self.assertIn("held-out", why)


class TrainingTest(unittest.TestCase):
    def test_training_reduces_loss_on_a_learnable_set(self) -> None:
        dataset = ChunkDataset(_samples(), horizon=4)
        config = TrainingConfig(
            horizon=4, epochs=8, hidden=64, layers=2, batch_size=32
        )

        _, result = train(dataset, config)

        self.assertLess(result.train_losses[-1], result.train_losses[0])

    def test_conversion_gaps_travel_into_the_result(self) -> None:
        dataset = ChunkDataset(_samples(), horizon=4)
        report = ConversionReport()
        report.provenance_gaps.append("no measured outcome")

        _, result = train(
            dataset,
            TrainingConfig(horizon=4, epochs=2, hidden=32, layers=1),
            report,
        )

        self.assertEqual(result.provenance_gaps, ["no measured outcome"])
        self.assertFalse(result.deployable[0])


class ServingTest(unittest.TestCase):
    def _trained(self, tmp: Path):
        dataset = ChunkDataset(_samples(), horizon=4)
        report = ConversionReport()
        report.provenance_gaps.append("pilot data is not training-grade")
        network, result = train(
            dataset,
            TrainingConfig(horizon=4, epochs=4, hidden=64, layers=2),
            report,
        )
        directory = save_checkpoint(tmp / "ckpt", network, dataset, result)
        return directory

    def test_a_checkpoint_round_trips_with_its_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = self._trained(Path(raw))

            policy = LearnedFastPolicy.load(directory)

            self.assertEqual(policy.horizon, 4)
            self.assertFalse(policy.deployable[0])
            self.assertIn("training-grade", policy.deployable[1])

    def test_a_learned_policy_never_starves_the_control_loop(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            policy = LearnedFastPolicy.load(self._trained(Path(raw)))
            server = PolicyServer(policy)

            starved = 0
            for tick in range(30):
                observation = Observation(
                    time_ns=_NOW + tick * _PERIOD_NS,
                    images={"head": "rgb/000000.jpg"},
                    state=_state(tick),
                )
                target, was_starved = server.step(observation)
                starved += int(was_starved)
                self.assertEqual(len(target.body), BODY_DIM)
                self.assertEqual(len(target.left_hand), HAND_DIM)

            self.assertEqual(starved, 0, server.last_failure)

    def test_every_emitted_frame_is_an_executable_contract_frame(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            policy = LearnedFastPolicy.load(self._trained(Path(raw)))

            chunk = policy.act(
                Observation(
                    time_ns=_NOW,
                    images={"head": "rgb/000000.jpg"},
                    state=_state(0),
                ),
                None,
                0,
            )

            self.assertEqual(len(chunk.frames), 4)
            for frame in chunk.frames:
                self.assertIsInstance(frame, WholeBodyTarget)


class ProjectionTest(unittest.TestCase):
    """A regression head lands slightly outside a joint range; that is normal.

    The contract cannot tell that from a hand-authored mistake, so the learned
    producer projects onto the feasible set and reports how far it had to move.
    """

    class _Fixed:
        """A network standing in for one whose output lands where we choose."""

        def __init__(self, row: list[float]) -> None:
            self._row = list(row)

        def __call__(self, tensor):  # noqa: ANN001 - torch tensor
            import torch

            rows = tensor.shape[0]
            return torch.tensor([self._row] * rows, dtype=torch.float32)

        def eval(self):  # noqa: ANN201 - torch protocol
            return self

    @staticmethod
    def _row(*, finger: float) -> list[float]:
        """One executable frame, with the left pinky moved where we want it.

        Every other channel is the vendored stand target, so exactly one thing
        is out of range in each case below. A row of one repeated value would
        put root height at that value too, and the projection under test would
        then be measuring the wrong channel.
        """
        row = list(STAND_BODY) + list(HAND_OPEN) + list(HAND_OPEN)
        row[BODY_DIM + HAND_DIM - 1] = finger
        return row

    def _policy(self, finger: float) -> LearnedFastPolicy:
        identity = Normalizer(
            mean=(0.0,) * ACTION_DIM, scale=(1.0,) * ACTION_DIM
        )
        return LearnedFastPolicy(
            self._Fixed(self._row(finger=finger)),
            horizon=1,
            state_normalizer=Normalizer(
                mean=(0.0,) * STATE_DIM, scale=(1.0,) * STATE_DIM
            ),
            action_normalizer=identity,
            deployable=False,
        )

    def _act(self, policy: LearnedFastPolicy):
        return policy.act(
            Observation(
                time_ns=_NOW,
                images={"head": "rgb/000000.jpg"},
                state=_state(0),
            ),
            None,
            0,
        )

    def test_an_out_of_range_output_is_projected_rather_than_dropped(self) -> None:
        policy = self._policy(-0.5)

        chunk = self._act(policy)

        self.assertEqual(len(chunk.frames), 1)
        self.assertGreaterEqual(min(chunk.frames[0].left_hand), 0.0)

    def test_the_projection_distance_is_reported(self) -> None:
        policy = self._policy(-0.5)

        self._act(policy)

        self.assertGreater(policy.projected_frames, 0)
        self.assertGreater(policy.worst_projection_rad, 0.0)

    def test_a_wildly_wrong_output_raises_the_alarm(self) -> None:
        policy = self._policy(-9.0)

        self._act(policy)

        self.assertGreater(policy.worst_projection_rad, PROJECTION_ALARM_RAD)
        self.assertTrue(policy.projection_alarming)

    def test_an_in_range_output_is_not_recorded_as_projected(self) -> None:
        policy = self._policy(0.3)

        self._act(policy)

        self.assertEqual(policy.projected_frames, 0)


if __name__ == "__main__":
    unittest.main()
