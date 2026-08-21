from __future__ import annotations

import unittest
from datetime import datetime, timezone

from vegapunk.embodied.act_candidate import (
    ACT_MODEL_FAMILY,
    ACTCheckpoint,
    ACTObservationContext,
    ACTPolicyEngineer,
    ACTTrainer,
    ACTTrainingOutput,
    ACTTrainingRecipe,
    EpisodeSplit,
)
from vegapunk.embodied.episode import (
    EpisodeTrainingManifest,
    TimeSynchronization,
    TrainingEpisode,
)
from vegapunk.embodied.promotion import (
    GOLDEN_EMBODIMENT,
    GOLDEN_INSTRUMENT_OPERATION_LOOP,
    GOLDEN_PROMOTION_CONFIGURATION,
    GOLDEN_SKILL_ID,
    GoldenSkillRevision,
)
from vegapunk.embodied.skill import SKILL_KIND_DETERMINISTIC, PhysicalSkill
from vegapunk.operation.episode import (
    TERMINATION_COMPLETED,
    TRANSFER_FULL,
    TRANSFER_NONE,
    CameraCalibration,
    EpisodeOutcome,
    EpisodeRecord,
    Frame,
    HumanTestimony,
    ResetRecord,
)
from vegapunk.operation.target import (
    HAND_OPEN,
    ROOT_YAW_RATE,
    STAND_BODY,
    WholeBodyTarget,
)
from vegapunk.operation.tracker import TrackerState
from vegapunk.operation.witness import LID_CLOSED

AT = datetime(2026, 8, 21, 19, 0, tzinfo=timezone.utc)
NOW = 4_000_000_000


def _skill() -> GoldenSkillRevision:
    return GoldenSkillRevision(
        skill=PhysicalSkill(
            skill_id=GOLDEN_SKILL_ID,
            revision=1,
            kind=SKILL_KIND_DETERMINISTIC,
            summary="Open, transfer, and restore the instrument.",
            parameters=(),
            preconditions=("instrument_closed",),
            postconditions=("instrument_closed", "transfer_complete"),
            abort_conditions=("safety_stop",),
            max_duration_s=90.0,
            reviewed_by="skill_owner",
        ),
        operation_loop=GOLDEN_INSTRUMENT_OPERATION_LOOP,
    )


def _target() -> WholeBodyTarget:
    return WholeBodyTarget(
        sequence=1,
        source_time_ns=NOW,
        valid_until_ns=NOW + 100_000_000,
        body=STAND_BODY,
        left_hand=HAND_OPEN,
        right_hand=HAND_OPEN,
    )


def _clamped_target() -> WholeBodyTarget:
    body = list(STAND_BODY)
    body[0] = 100.0
    return WholeBodyTarget(
        sequence=1,
        source_time_ns=NOW,
        valid_until_ns=NOW + 100_000_000,
        body=tuple(body),
        left_hand=HAND_OPEN,
        right_hand=HAND_OPEN,
    )


def _target_with_root_speed(speed_mps: float) -> WholeBodyTarget:
    body = list(STAND_BODY)
    body[0] = speed_mps
    return WholeBodyTarget(
        sequence=1,
        source_time_ns=NOW,
        valid_until_ns=NOW + 100_000_000,
        body=tuple(body),
        left_hand=HAND_OPEN,
        right_hand=HAND_OPEN,
    )


def _target_with_yaw_rate(yaw_rate_rps: float) -> WholeBodyTarget:
    body = list(STAND_BODY)
    body[ROOT_YAW_RATE] = yaw_rate_rps
    return WholeBodyTarget(
        sequence=1,
        source_time_ns=NOW,
        valid_until_ns=NOW + 100_000_000,
        body=tuple(body),
        left_hand=HAND_OPEN,
        right_hand=HAND_OPEN,
    )


def _episode(episode_id: str, *, transfer: str = TRANSFER_FULL) -> TrainingEpisode:
    return _episode_with_target(episode_id, _target(), transfer=transfer)


def _episode_with_target(
    episode_id: str,
    target: WholeBodyTarget,
    *,
    transfer: str = TRANSFER_FULL,
    state_angular_yaw_rate_rps: float = 0.0,
    image_reference: str = "head/00000.jpg",
) -> TrainingEpisode:
    return TrainingEpisode(
        record=EpisodeRecord(
            episode_id=episode_id,
            configuration_digest=GOLDEN_PROMOTION_CONFIGURATION.digest(),
            started_at=AT,
            cameras=(CameraCalibration("head", 640, 480, 30.0, "torso"),),
            witness_identity="lid-limit-switch",
            reset=ResetRecord("bench_operator", AT, True, True, True),
            frame_count=1,
            outcome=EpisodeOutcome(
                transfer=transfer,
                judged_by="outcome_judge",
                judged_at=AT,
                lid_closed_at_end=True,
                termination=TERMINATION_COMPLETED,
            ),
            testimony=(
                HumanTestimony("bench_operator", AT, "cup returned to the bench"),
            ),
            operator="campaign_operator",
        ),
        skill=_skill(),
        embodiment=GOLDEN_EMBODIMENT,
        configuration=GOLDEN_PROMOTION_CONFIGURATION,
        synchronization=TimeSynchronization(
            "ptp-bench-001",
            AT,
            "camera-ptp",
            "target-bridge-monotonic",
            "lid-switch-monotonic",
            2_000_000,
        ),
        frames=(
            Frame(
                index=0,
                time_ns=NOW,
                images={"head": image_reference},
                state=TrackerState(
                    sequence=1,
                    state_time_ns=NOW,
                    body=(0.0, 0.0, state_angular_yaw_rate_rps) + (0.0,) * 31,
                    left_hand=HAND_OPEN,
                    right_hand=HAND_OPEN,
                    applied_target_sequence=1,
                ),
                target=target,
                lid=LID_CLOSED,
                monitor_decision="pass",
            ),
        ),
    )


def _recipe() -> ACTTrainingRecipe:
    return ACTTrainingRecipe(
        "act-golden-v1",
        2,
        1,
        50.0,
        GOLDEN_PROMOTION_CONFIGURATION.observation_schema_digest,
        GOLDEN_PROMOTION_CONFIGURATION.action_protocol_digest,
    )


def _split(
    train: TrainingEpisode, validation: TrainingEpisode, held_out: TrainingEpisode
) -> EpisodeSplit:
    return EpisodeSplit(
        (train.record.episode_id,),
        (validation.record.episode_id,),
        (held_out.record.episode_id,),
    )


def _training_output(
    manifest: EpisodeTrainingManifest,
    split: EpisodeSplit,
    recipe: ACTTrainingRecipe,
    held_out_latency_ms: dict[str, float],
) -> ACTTrainingOutput:
    trainer = ACTTrainer()
    checkpoint = trainer.fit(manifest, split, recipe, "act-candidate-001")
    episodes = {episode.record.episode_id: episode for episode in manifest.episodes}
    return trainer.evaluate(
        checkpoint,
        tuple(episodes[episode_id] for episode_id in split.test_episode_ids),
        recipe,
        held_out_latency_ms,
    )


class ACTCandidateAcceptanceTest(unittest.TestCase):
    def test_policy_engineer_packages_an_end_to_end_candidate_from_eligible_episodes(
        self,
    ) -> None:
        train, validation, held_out = (
            _episode("episode-train"),
            _episode("episode-validation"),
            _episode("episode-held-out"),
        )
        manifest = EpisodeTrainingManifest((train, validation, held_out))
        recipe = _recipe()
        split = _split(train, validation, held_out)
        result = _training_output(
            manifest,
            split,
            recipe,
            {held_out.record.episode_id: 12.5},
        )

        candidate = ACTPolicyEngineer().package(
            manifest,
            split,
            recipe,
            result,
        )

        self.assertEqual(candidate.bundle.data_manifest_digest, manifest.digest())
        self.assertEqual(
            candidate.bundle.policy_artifact_digest,
            candidate.training_output.checkpoint.digest(),
        )
        self.assertEqual(candidate.bundle.skill_revision_digest, train.skill.digest())
        self.assertEqual(candidate.training_output.model_family, ACT_MODEL_FAMILY)
        self.assertEqual(candidate.evaluation.held_out_success_rate, 1.0)
        metric = candidate.evaluation.episode_metrics[0]
        self.assertTrue(metric.decoding_passed)
        self.assertTrue(metric.temporal_passed)
        self.assertTrue(metric.dimension_passed)
        self.assertEqual(metric.action_dimensions, (len(STAND_BODY),))
        self.assertTrue(metric.chunk_continuity_passed)
        self.assertTrue(metric.projection_passed)
        self.assertEqual(metric.latency_ms, 12.5)
        self.assertFalse(hasattr(candidate, "shadow_authority"))
        self.assertFalse(hasattr(candidate, "hardware_authority"))

    def test_training_accepts_every_and_only_eligible_complete_episode(self) -> None:
        train, validation, held_out = (
            _episode("episode-train"),
            _episode("episode-validation"),
            _episode("episode-held-out"),
        )
        excluded = _episode("episode-failed", transfer=TRANSFER_NONE)
        manifest = EpisodeTrainingManifest((train, validation, held_out, excluded))
        recipe = _recipe()
        split = _split(train, validation, excluded)
        with self.assertRaisesRegex(ValueError, "only eligible"):
            ACTTrainer().fit(manifest, split, recipe, "act-candidate-001")

    def test_act_checkpoint_learns_from_every_complete_training_episode(self) -> None:
        first_train = _episode_with_target(
            "episode-train-a", _target_with_root_speed(0.0)
        )
        second_train = _episode_with_target(
            "episode-train-b", _target_with_root_speed(0.2)
        )
        validation = _episode("episode-validation")
        held_out = _episode("episode-held-out")
        manifest = EpisodeTrainingManifest(
            (first_train, second_train, validation, held_out)
        )
        split = EpisodeSplit(
            (first_train.record.episode_id, second_train.record.episode_id),
            (validation.record.episode_id,),
            (held_out.record.episode_id,),
        )
        candidate = ACTPolicyEngineer().package(
            manifest,
            split,
            _recipe(),
            _training_output(
                manifest,
                split,
                _recipe(),
                {held_out.record.episode_id: 12.5},
            ),
        )

        self.assertEqual(
            candidate.training_output.checkpoint.action_templates[0].body[0], 0.1
        )

    def test_act_checkpoint_conditions_action_chunks_on_frozen_observations(self) -> None:
        train = _episode("episode-train")
        validation = _episode("episode-validation")
        held_out = _episode_with_target(
            "episode-held-out",
            _target(),
            state_angular_yaw_rate_rps=0.2,
            image_reference="head/held-out.jpg",
        )
        manifest = EpisodeTrainingManifest((train, validation, held_out))
        recipe = _recipe()
        split = _split(train, validation, held_out)
        candidate = ACTPolicyEngineer().package(
            manifest,
            split,
            recipe,
            _training_output(
                manifest,
                split,
                recipe,
                {held_out.record.episode_id: 12.5},
            ),
        )

        emitted = candidate.training_output.held_out_chunks[
            held_out.record.episode_id
        ][0].frames[0]
        template = candidate.training_output.checkpoint.action_templates[0]
        self.assertNotEqual(
            emitted.body[ROOT_YAW_RATE], template.body[ROOT_YAW_RATE]
        )

    def test_act_checkpoint_conditions_yaw_rate_on_camera_references(self) -> None:
        train_a = _episode_with_target(
            "episode-train-a",
            _target_with_yaw_rate(0.2),
            image_reference="head/scene-a.jpg",
        )
        train_b = _episode_with_target(
            "episode-train-b",
            _target_with_yaw_rate(-0.2),
            image_reference="head/scene-b.jpg",
        )
        validation = _episode("episode-validation")
        held_out_a = _episode_with_target(
            "episode-held-out-a", _target(), image_reference="head/scene-a.jpg"
        )
        held_out_b = _episode_with_target(
            "episode-held-out-b", _target(), image_reference="head/scene-b.jpg"
        )
        manifest = EpisodeTrainingManifest(
            (train_a, train_b, validation, held_out_a, held_out_b)
        )
        split = EpisodeSplit(
            (train_a.record.episode_id, train_b.record.episode_id),
            (validation.record.episode_id,),
            (held_out_a.record.episode_id, held_out_b.record.episode_id),
        )
        output = _training_output(
            manifest,
            split,
            _recipe(),
            {
                held_out_a.record.episode_id: 12.5,
                held_out_b.record.episode_id: 12.5,
            },
        )

        yaw_a = output.held_out_chunks[held_out_a.record.episode_id][0].frames[0].body[
            ROOT_YAW_RATE
        ]
        yaw_b = output.held_out_chunks[held_out_b.record.episode_id][0].frames[0].body[
            ROOT_YAW_RATE
        ]

        self.assertGreater(yaw_a, yaw_b)

    def test_offline_evaluation_records_latency_failures(self) -> None:
        train, validation, held_out = (
            _episode("episode-train"),
            _episode("episode-validation"),
            _episode("episode-held-out"),
        )
        manifest = EpisodeTrainingManifest((train, validation, held_out))
        recipe = _recipe()
        split = _split(train, validation, held_out)
        output = _training_output(
            manifest,
            split,
            recipe,
            {held_out.record.episode_id: 75.0},
        )

        candidate = ACTPolicyEngineer().package(
            manifest,
            split,
            recipe,
            output,
        )

        metric = candidate.evaluation.episode_metrics[0]
        self.assertTrue(metric.chunk_continuity_passed)
        self.assertEqual(metric.latency_ms, 75.0)
        self.assertFalse(metric.latency_within_bound)
        self.assertEqual(candidate.evaluation.held_out_success_rate, 0.0)

    def test_splits_cannot_drop_or_fragment_complete_episodes(self) -> None:
        with self.assertRaisesRegex(ValueError, "training and validation"):
            EpisodeSplit((), ("episode-validation",), ("episode-held-out",))
        with self.assertRaisesRegex(ValueError, "cannot be split"):
            EpisodeSplit(
                ("episode-train",),
                ("episode-train",),
                ("episode-held-out",),
            )

    def test_offline_evaluation_retains_projection_clamps(self) -> None:
        train, validation, held_out = (
            _episode_with_target("episode-train", _clamped_target()),
            _episode("episode-validation"),
            _episode("episode-held-out"),
        )
        manifest = EpisodeTrainingManifest((train, validation, held_out))
        recipe = _recipe()
        split = _split(train, validation, held_out)
        candidate = ACTPolicyEngineer().package(
            manifest,
            split,
            recipe,
            _training_output(
                manifest,
                split,
                recipe,
                {held_out.record.episode_id: 12.5},
            ),
        )

        metric = candidate.evaluation.episode_metrics[0]
        self.assertFalse(metric.projection_passed)
        self.assertTrue(metric.projection_clamps)
        self.assertEqual(candidate.evaluation.held_out_success_rate, 0.0)

    def test_a_segment_model_cannot_be_packaged_as_an_act_candidate(self) -> None:
        with self.assertRaisesRegex(ValueError, "issued by ACTTrainer"):
            ACTCheckpoint(
                "act-candidate-001",
                "manifest-001",
                "recipe-001",
                ("episode-train",),
                (_target(),),
                1,
                (ACTObservationContext((0.0, 0.0, 0.0), "image-reference-digest"),),
                ((),),
                (),
            )


if __name__ == "__main__":
    unittest.main()
