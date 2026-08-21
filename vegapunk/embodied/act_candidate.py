"""Train, evaluate, and package one end-to-end ACT Candidate."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from vegapunk.embodied.episode import EpisodeTrainingManifest, TrainingEpisode
from vegapunk.embodied.promotion import CandidateBundle
from vegapunk.operation.episode import TRANSFER_FULL, Frame
from vegapunk.operation.policy import ActionChunk
from vegapunk.operation.target import ROOT_YAW_RATE, WholeBodyTarget

ACT_MODEL_FAMILY = "action_chunking_transformer"
_ACT_TRAINING_SEAL = object()
_ACT_CANDIDATE_SEAL = object()


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]


@dataclass(frozen=True)
class ACTTrainingRecipe:
    """The frozen ACT settings and I/O contracts for one training run."""

    recipe_id: str
    context_frames: int
    action_chunk_size: int
    max_latency_ms: float
    observation_schema_digest: str
    action_schema_digest: str

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.recipe_id,
                self.observation_schema_digest,
                self.action_schema_digest,
            )
        ):
            raise ValueError("an ACT recipe names its identity and I/O contracts")
        if self.context_frames <= 0 or self.action_chunk_size <= 0:
            raise ValueError("an ACT recipe uses positive context and chunk sizes")
        if self.max_latency_ms <= 0:
            raise ValueError("an ACT recipe sets a positive latency bound")

    def digest(self) -> str:
        return _digest(
            {
                "recipe_id": self.recipe_id,
                "context_frames": self.context_frames,
                "action_chunk_size": self.action_chunk_size,
                "max_latency_ms": self.max_latency_ms,
                "observation_schema_digest": self.observation_schema_digest,
                "action_schema_digest": self.action_schema_digest,
            }
        )

@dataclass(frozen=True)
class EpisodeSplit:
    """Whole Episode identities for the training, validation, and test splits."""

    training_episode_ids: tuple[str, ...]
    validation_episode_ids: tuple[str, ...]
    test_episode_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "training_episode_ids",
            "validation_episode_ids",
            "test_episode_ids",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        identifiers = (
            self.training_episode_ids
            + self.validation_episode_ids
            + self.test_episode_ids
        )
        if (
            not self.training_episode_ids
            or not self.validation_episode_ids
            or not all(self.training_episode_ids)
            or not all(self.validation_episode_ids)
        ):
            raise ValueError("ACT training and validation each need complete Episodes")
        if not self.test_episode_ids:
            raise ValueError("ACT evaluation needs held-out complete Episodes")
        if not all(identifier.strip() for identifier in identifiers):
            raise ValueError("an Episode split names every complete Episode")
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("one Episode cannot be split across ACT datasets")


@dataclass(frozen=True)
class ACTObservationContext:
    """A bounded window of frozen ACT observations at one action position.

    The simplified trainer learns a yaw-rate response from the feedback angular
    velocity and from camera-reference associations.  Both are native parts of
    the frozen observation schema, rather than anonymous numeric features.
    """

    angular_velocity_rps: tuple[float, ...]
    image_reference_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "angular_velocity_rps", tuple(self.angular_velocity_rps))
        if len(self.angular_velocity_rps) != 3 or not all(
            math.isfinite(value) for value in self.angular_velocity_rps
        ):
            raise ValueError("an ACT observation context records angular velocity in rad/s")
        if not self.image_reference_digest.strip():
            raise ValueError("an ACT observation context identifies its camera references")

    @classmethod
    def from_frames(cls, frames: tuple[Frame, ...]) -> ACTObservationContext:
        if not frames:
            raise ValueError("an ACT observation context needs at least one frame")
        image_references = tuple(
            tuple(sorted(frame.images.items())) for frame in frames
        )
        return cls(
            angular_velocity_rps=tuple(
                sum(frame.state.angular_velocity[index] for frame in frames) / len(frames)
                for index in range(3)
            ),
            image_reference_digest=_digest(image_references),
        )

    @classmethod
    def learned_from(
        cls, contexts: tuple[ACTObservationContext, ...]
    ) -> ACTObservationContext:
        if not contexts:
            raise ValueError("ACT training needs observation contexts")
        return cls(
            angular_velocity_rps=tuple(
                sum(context.angular_velocity_rps[index] for context in contexts)
                / len(contexts)
                for index in range(3)
            ),
            image_reference_digest=_digest(
                tuple(context.image_reference_digest for context in contexts)
            ),
        )

    def yaw_rate_offset_from(
        self,
        learned_context: ACTObservationContext,
        visual_responses: tuple[ACTVisualActionResponse, ...],
    ) -> float:
        """Return the learned yaw-rate response for this observation window."""
        visual_offset = next(
            (
                response.root_yaw_rate_offset_rps
                for response in visual_responses
                if response.image_reference_digest == self.image_reference_digest
            ),
            0.0,
        )
        return (
            self.angular_velocity_rps[2] - learned_context.angular_velocity_rps[2]
        ) + visual_offset


@dataclass(frozen=True)
class ACTVisualActionResponse:
    """A visual observation association learned from complete training Episodes."""

    image_reference_digest: str
    root_yaw_rate_offset_rps: float

    def __post_init__(self) -> None:
        if not self.image_reference_digest.strip() or not math.isfinite(
            self.root_yaw_rate_offset_rps
        ):
            raise ValueError("an ACT visual response names a finite yaw-rate offset")


@dataclass(frozen=True)
class ACTCheckpoint:
    """An ACT-trained action-chunk artifact derived from complete Episodes."""

    candidate_id: str
    training_manifest_digest: str
    training_recipe_digest: str
    training_episode_ids: tuple[str, ...]
    action_templates: tuple[WholeBodyTarget, ...]
    context_frames: int
    observation_contexts: tuple[ACTObservationContext, ...]
    visual_responses: tuple[tuple[ACTVisualActionResponse, ...], ...]
    training_projection_clamps: tuple[str, ...]
    _act_training_seal: object = field(
        default=None, repr=False, compare=False, hash=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "training_episode_ids", tuple(self.training_episode_ids))
        object.__setattr__(self, "action_templates", tuple(self.action_templates))
        object.__setattr__(
            self, "observation_contexts", tuple(self.observation_contexts)
        )
        object.__setattr__(
            self,
            "visual_responses",
            tuple(tuple(responses) for responses in self.visual_responses),
        )
        object.__setattr__(
            self, "training_projection_clamps", tuple(self.training_projection_clamps)
        )
        if self._act_training_seal is not _ACT_TRAINING_SEAL:
            raise ValueError("an ACT checkpoint must be issued by ACTTrainer")
        if not all(
            value.strip()
            for value in (
                self.candidate_id,
                self.training_manifest_digest,
                self.training_recipe_digest,
            )
        ):
            raise ValueError("an ACT checkpoint names its Candidate and inputs")
        if not self.training_episode_ids or not self.action_templates:
            raise ValueError("an ACT checkpoint retains complete training actions")
        if (
            self.context_frames <= 0
            or len(self.observation_contexts) != len(self.action_templates)
            or len(self.visual_responses) != len(self.action_templates)
        ):
            raise ValueError("an ACT checkpoint retains its observation context")

    def digest(self) -> str:
        return _digest(
            {
                "model_family": ACT_MODEL_FAMILY,
                "candidate_id": self.candidate_id,
                "training_manifest_digest": self.training_manifest_digest,
                "training_recipe_digest": self.training_recipe_digest,
                "training_episode_ids": list(self.training_episode_ids),
                "action_templates": [dict(item.as_payload()) for item in self.action_templates],
                "context_frames": self.context_frames,
                "observation_contexts": [
                    {
                        "angular_velocity_rps": list(context.angular_velocity_rps),
                        "image_reference_digest": context.image_reference_digest,
                    }
                    for context in self.observation_contexts
                ],
                "visual_responses": [
                    [
                        {
                            "image_reference_digest": response.image_reference_digest,
                            "root_yaw_rate_offset_rps": response.root_yaw_rate_offset_rps,
                        }
                        for response in responses
                    ]
                    for responses in self.visual_responses
                ],
                "training_projection_clamps": list(self.training_projection_clamps),
            }
        )

    @property
    def projection_clamps(self) -> tuple[str, ...]:
        return self.training_projection_clamps

    def action_chunks_for(
        self, episode: TrainingEpisode, chunk_size: int
    ) -> tuple[ActionChunk, ...]:
        if len(self.action_templates) != len(episode.frames):
            return ()
        targets = tuple(
            WholeBodyTarget(
                sequence=frame.target.sequence,
                source_time_ns=frame.time_ns,
                valid_until_ns=frame.time_ns
                + (template.valid_until_ns - template.source_time_ns),
                body=template.body[:ROOT_YAW_RATE]
                + (
                    template.body[ROOT_YAW_RATE]
                    + ACTObservationContext.from_frames(
                        episode.frames[
                            max(0, index - self.context_frames + 1) : index + 1
                        ]
                    ).yaw_rate_offset_from(
                        self.observation_contexts[index], self.visual_responses[index]
                    ),
                )
                + template.body[ROOT_YAW_RATE + 1 :],
                left_hand=template.left_hand,
                right_hand=template.right_hand,
            )
            for index, (frame, template) in enumerate(
                zip(episode.frames, self.action_templates, strict=True)
            )
        )
        return tuple(
            ActionChunk(first_tick=index, frames=targets[index : index + chunk_size])
            for index in range(0, len(targets), chunk_size)
        )


@dataclass(frozen=True)
class ACTTrainingOutput:
    """The learned checkpoint and its held-out ACT action chunks."""

    candidate_id: str
    checkpoint_digest: str
    checkpoint: ACTCheckpoint
    held_out_chunks: Mapping[str, tuple[ActionChunk, ...]]
    held_out_latency_ms: Mapping[str, float]
    training_manifest_digest: str
    training_recipe_digest: str
    training_episode_ids: tuple[str, ...]
    _act_training_seal: object = field(
        default=None, repr=False, compare=False, hash=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "training_episode_ids", tuple(self.training_episode_ids))
        if self._act_training_seal is not _ACT_TRAINING_SEAL:
            raise ValueError("an ACT output must be issued by ACTTrainer")
        if not isinstance(self.checkpoint, ACTCheckpoint):
            raise TypeError("an ACT output retains its ACTCheckpoint")
        if not all(
            value.strip()
            for value in (
                self.candidate_id,
                self.checkpoint_digest,
                self.training_manifest_digest,
                self.training_recipe_digest,
            )
        ):
            raise ValueError("an ACT output names its Candidate, checkpoint, and inputs")
        if not self.training_episode_ids or not all(self.training_episode_ids):
            raise ValueError("an ACT output names its complete training Episodes")
        if (
            self.candidate_id != self.checkpoint.candidate_id
            or self.checkpoint_digest != self.checkpoint.digest()
            or self.training_manifest_digest
            != self.checkpoint.training_manifest_digest
            or self.training_recipe_digest != self.checkpoint.training_recipe_digest
            or self.training_episode_ids != self.checkpoint.training_episode_ids
        ):
            raise ValueError("an ACT output cannot replace checkpoint provenance")
        chunks = {
            episode_id: tuple(value)
            for episode_id, value in self.held_out_chunks.items()
        }
        latency = dict(self.held_out_latency_ms)
        if set(chunks) != set(latency):
            raise ValueError("ACT evaluation names chunks and latency for the same Episodes")
        if not all(episode_id.strip() for episode_id in chunks):
            raise ValueError("ACT evaluation names every held-out Episode")
        if not all(
            isinstance(chunk, ActionChunk)
            for episode_chunks in chunks.values()
            for chunk in episode_chunks
        ):
            raise TypeError("ACT output contains ActionChunk values only")
        if not all(value >= 0 for value in latency.values()):
            raise ValueError("ACT evaluation latency cannot be negative")
        object.__setattr__(self, "held_out_chunks", MappingProxyType(chunks))
        object.__setattr__(self, "held_out_latency_ms", MappingProxyType(latency))

    @property
    def model_family(self) -> str:
        return ACT_MODEL_FAMILY


@dataclass(frozen=True)
class OfflineEpisodeMetric:
    """Offline evidence for one held-out complete Episode."""

    episode_id: str
    decoding_passed: bool
    temporal_passed: bool
    dimension_passed: bool
    action_dimensions: tuple[int, ...]
    chunk_continuity_passed: bool
    projection_passed: bool
    projection_clamps: tuple[str, ...]
    latency_ms: float
    latency_within_bound: bool
    held_out_outcome: str
    candidate_outcome_passed: bool


@dataclass(frozen=True)
class ACTOfflineEvaluation:
    """The complete offline record attached to an end-to-end Candidate."""

    episode_metrics: tuple[OfflineEpisodeMetric, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "episode_metrics", tuple(self.episode_metrics))
        if not self.episode_metrics:
            raise ValueError("ACT offline evaluation needs held-out Episode metrics")

    @property
    def held_out_success_rate(self) -> float:
        return sum(
            metric.candidate_outcome_passed
            for metric in self.episode_metrics
        ) / len(self.episode_metrics)


@dataclass(frozen=True)
class EndToEndACTCandidate:
    """A candidate with no authority beyond its immutable offline record."""

    bundle: CandidateBundle
    recipe: ACTTrainingRecipe
    split: EpisodeSplit
    training_output: ACTTrainingOutput
    evaluation: ACTOfflineEvaluation
    _issued_bundle_digest: str = field(default="", repr=False, compare=False)
    _act_candidate_seal: object = field(
        default=None, repr=False, compare=False, hash=False
    )

    def __post_init__(self) -> None:
        if self._act_candidate_seal is not _ACT_CANDIDATE_SEAL:
            raise ValueError("an end-to-end ACT Candidate must be issued by ACTPolicyEngineer")
        if (
            self._issued_bundle_digest != self.bundle.digest()
            or self.bundle.candidate_id != self.training_output.candidate_id
            or self.bundle.policy_artifact_digest != self.training_output.checkpoint_digest
            or self.bundle.data_manifest_digest
            != self.training_output.training_manifest_digest
            or self.bundle.training_recipe_digest
            != self.training_output.training_recipe_digest
            or self.bundle.observation_schema_digest != self.recipe.observation_schema_digest
            or self.bundle.action_schema_digest != self.recipe.action_schema_digest
        ):
            raise ValueError("an end-to-end ACT Candidate cannot replace its sealed bundle")


class ACTTrainer:
    """The only issuer of an ACT-trained checkpoint artifact."""

    def fit(
        self,
        manifest: EpisodeTrainingManifest,
        split: EpisodeSplit,
        recipe: ACTTrainingRecipe,
        candidate_id: str,
    ) -> ACTCheckpoint:
        episodes = _validated_episodes(manifest, split, recipe)
        training_episodes = episodes[: len(split.training_episode_ids)]
        action_templates = _learn_action_templates(training_episodes)
        return ACTCheckpoint(
            candidate_id=candidate_id,
            training_manifest_digest=manifest.digest(),
            training_recipe_digest=recipe.digest(),
            training_episode_ids=split.training_episode_ids,
            action_templates=action_templates,
            context_frames=recipe.context_frames,
            observation_contexts=tuple(
                ACTObservationContext.learned_from(
                    tuple(
                        ACTObservationContext.from_frames(
                            episode.frames[
                                max(0, index - recipe.context_frames + 1) : index + 1
                            ]
                        )
                        for episode in training_episodes
                    )
                )
                for index in range(len(training_episodes[0].frames))
            ),
            visual_responses=_learn_visual_responses(
                training_episodes, action_templates, recipe.context_frames
            ),
            training_projection_clamps=tuple(
                clamp
                for episode in training_episodes
                for frame in episode.frames
                for clamp in frame.target.clamped
            ),
            _act_training_seal=_ACT_TRAINING_SEAL,
        )

    def evaluate(
        self,
        checkpoint: ACTCheckpoint,
        held_out_episodes: tuple[TrainingEpisode, ...],
        recipe: ACTTrainingRecipe,
        held_out_latency_ms: Mapping[str, float],
    ) -> ACTTrainingOutput:
        if not isinstance(checkpoint, ACTCheckpoint):
            raise TypeError("ACTTrainer evaluates an ACTCheckpoint")
        episodes = tuple(held_out_episodes)
        chunks = {
            episode.record.episode_id: checkpoint.action_chunks_for(
                episode, recipe.action_chunk_size
            )
            for episode in episodes
        }
        return ACTTrainingOutput(
            candidate_id=checkpoint.candidate_id,
            checkpoint_digest=checkpoint.digest(),
            checkpoint=checkpoint,
            held_out_chunks=chunks,
            held_out_latency_ms=held_out_latency_ms,
            training_manifest_digest=checkpoint.training_manifest_digest,
            training_recipe_digest=checkpoint.training_recipe_digest,
            training_episode_ids=checkpoint.training_episode_ids,
            _act_training_seal=_ACT_TRAINING_SEAL,
        )


class ACTPolicyEngineer:
    """Evaluates and packages an ACT Candidate without granting execution authority."""

    def package(
        self,
        manifest: EpisodeTrainingManifest,
        split: EpisodeSplit,
        recipe: ACTTrainingRecipe,
        output: ACTTrainingOutput,
    ) -> EndToEndACTCandidate:
        if not isinstance(output, ACTTrainingOutput):
            raise TypeError("ACT packaging needs an ACTTrainingOutput")
        episodes = _validated_episodes(manifest, split, recipe)
        eligible = {episode.record.episode_id: episode for episode in episodes}
        if set(output.held_out_chunks) != set(split.test_episode_ids):
            raise ValueError("ACT output evaluates exactly the held-out Episode split")
        if output.training_manifest_digest != manifest.digest():
            raise ValueError("an ACT output names another frozen Training Manifest")
        if output.training_recipe_digest != recipe.digest():
            raise ValueError("an ACT output names another frozen ACT recipe")
        if output.training_episode_ids != split.training_episode_ids:
            raise ValueError("an ACT output names another complete Episode training split")

        reference = episodes[0]

        evaluation = ACTOfflineEvaluation(
            tuple(
                _evaluate_episode(eligible[episode_id], recipe, output)
                for episode_id in split.test_episode_ids
            )
        )
        bundle = CandidateBundle(
                candidate_id=output.candidate_id,
                policy_artifact_digest=output.checkpoint_digest,
                data_manifest_digest=manifest.digest(),
                training_recipe_digest=recipe.digest(),
                observation_schema_digest=recipe.observation_schema_digest,
                action_schema_digest=recipe.action_schema_digest,
                skill_revision_id=reference.skill.version_id,
                skill_revision_digest=reference.skill.digest(),
                embodiment_digest=reference.embodiment.digest(),
                configuration_digest=reference.configuration.digest(),
            )
        return EndToEndACTCandidate(
            bundle=bundle,
            recipe=recipe,
            split=split,
            training_output=output,
            evaluation=evaluation,
            _issued_bundle_digest=bundle.digest(),
            _act_candidate_seal=_ACT_CANDIDATE_SEAL,
        )


def _same_contract(left: TrainingEpisode, right: TrainingEpisode) -> bool:
    return (
        left.skill.digest() == right.skill.digest()
        and left.embodiment.digest() == right.embodiment.digest()
        and left.configuration.digest() == right.configuration.digest()
    )


def _validated_episodes(
    manifest: EpisodeTrainingManifest,
    split: EpisodeSplit,
    recipe: ACTTrainingRecipe,
) -> tuple[TrainingEpisode, ...]:
    if not isinstance(manifest, EpisodeTrainingManifest):
        raise TypeError("ACT training needs a frozen EpisodeTrainingManifest")
    if not isinstance(split, EpisodeSplit):
        raise TypeError("ACT training needs an EpisodeSplit")
    if not isinstance(recipe, ACTTrainingRecipe):
        raise TypeError("ACT training needs an ACTTrainingRecipe")
    eligible = {
        episode.record.episode_id: episode
        for episode in manifest.episodes
        if episode.eligibility()[0]
    }
    split_ids = (
        split.training_episode_ids
        + split.validation_episode_ids
        + split.test_episode_ids
    )
    if set(split_ids) != set(eligible):
        raise ValueError("ACT splits contain every and only eligible complete Episodes")
    episodes = tuple(eligible[episode_id] for episode_id in split_ids)
    reference = episodes[0]
    if any(not _same_contract(reference, episode) for episode in episodes[1:]):
        raise ValueError("ACT training cannot mix Episode contracts")
    if (
        recipe.observation_schema_digest
        != reference.configuration.observation_schema_digest
        or recipe.action_schema_digest != reference.configuration.action_protocol_digest
    ):
        raise ValueError("ACT recipe must use frozen observation and action contracts")
    return episodes


def _learn_action_templates(
    episodes: tuple[TrainingEpisode, ...],
) -> tuple[WholeBodyTarget, ...]:
    frame_counts = {len(episode.frames) for episode in episodes}
    if len(frame_counts) != 1:
        raise ValueError("ACT training needs aligned complete Golden Skill Episodes")
    return tuple(
        WholeBodyTarget(
            sequence=frames[0].target.sequence,
            source_time_ns=frames[0].target.source_time_ns,
            valid_until_ns=frames[0].target.valid_until_ns,
            body=tuple(
                sum(target.body[index] for target in (frame.target for frame in frames))
                / len(frames)
                for index in range(len(frames[0].target.body))
            ),
            left_hand=tuple(
                sum(
                    target.left_hand[index] for target in (frame.target for frame in frames)
                )
                / len(frames)
                for index in range(len(frames[0].target.left_hand))
            ),
            right_hand=tuple(
                sum(
                    target.right_hand[index]
                    for target in (frame.target for frame in frames)
                )
                / len(frames)
                for index in range(len(frames[0].target.right_hand))
            ),
        )
        for frames in zip(*(episode.frames for episode in episodes), strict=True)
    )


def _learn_visual_responses(
    episodes: tuple[TrainingEpisode, ...],
    action_templates: tuple[WholeBodyTarget, ...],
    context_frames: int,
) -> tuple[tuple[ACTVisualActionResponse, ...], ...]:
    """Learn image-reference to yaw-rate residuals for each ACT action position."""
    responses = []
    for index, template in enumerate(action_templates):
        targets_by_image: dict[str, list[float]] = {}
        for episode in episodes:
            context = ACTObservationContext.from_frames(
                episode.frames[max(0, index - context_frames + 1) : index + 1]
            )
            targets_by_image.setdefault(context.image_reference_digest, []).append(
                episode.frames[index].target.body[ROOT_YAW_RATE]
            )
        responses.append(
            tuple(
                ACTVisualActionResponse(
                    image_reference_digest=digest,
                    root_yaw_rate_offset_rps=sum(targets) / len(targets)
                    - template.body[ROOT_YAW_RATE],
                )
                for digest, targets in sorted(targets_by_image.items())
            )
        )
    return tuple(responses)


def _evaluate_episode(
    episode: TrainingEpisode,
    recipe: ACTTrainingRecipe,
    output: ACTTrainingOutput,
) -> OfflineEpisodeMetric:
    chunks = output.held_out_chunks[episode.record.episode_id]
    targets = tuple(target for chunk in chunks for target in chunk.frames)
    decoding_passed = bool(targets) and all(
        isinstance(target, WholeBodyTarget) for target in targets
    )
    chunk_continuity_passed = _has_continuous_chunks(
        chunks, len(episode.frames), recipe.action_chunk_size
    )
    temporal_passed = decoding_passed and len(targets) == len(episode.frames) and all(
        abs(target.source_time_ns - frame.time_ns)
        <= episode.synchronization.max_skew_ns
        for target, frame in zip(targets, episode.frames, strict=True)
    )
    action_dimensions = tuple(
        len(target.body) for target in targets if isinstance(target, WholeBodyTarget)
    )
    dimension_passed = decoding_passed and len(targets) == len(episode.frames) and all(
        dimension == len(frame.target.body)
        for dimension, frame in zip(action_dimensions, episode.frames, strict=True)
    )
    projection_clamps = output.checkpoint.projection_clamps + tuple(
        clamp
        for target in targets
        if isinstance(target, WholeBodyTarget)
        for clamp in target.clamped
    )
    projection_passed = decoding_passed and not projection_clamps
    latency_ms = output.held_out_latency_ms[episode.record.episode_id]
    latency_within_bound = latency_ms <= recipe.max_latency_ms
    outcome = episode.record.outcome
    assert outcome is not None
    return OfflineEpisodeMetric(
        episode_id=episode.record.episode_id,
        decoding_passed=decoding_passed,
        temporal_passed=temporal_passed,
        dimension_passed=dimension_passed,
        action_dimensions=action_dimensions,
        chunk_continuity_passed=chunk_continuity_passed,
        projection_passed=projection_passed,
        projection_clamps=projection_clamps,
        latency_ms=latency_ms,
        latency_within_bound=latency_within_bound,
        held_out_outcome=outcome.transfer,
        candidate_outcome_passed=(
            decoding_passed
            and temporal_passed
            and dimension_passed
            and chunk_continuity_passed
            and projection_passed
            and latency_within_bound
            and outcome.transfer == TRANSFER_FULL
        ),
    )


def _has_continuous_chunks(
    chunks: tuple[ActionChunk, ...], expected_frames: int, chunk_size: int
) -> bool:
    expected_tick = 0
    for index, chunk in enumerate(chunks):
        if chunk.first_tick != expected_tick or len(chunk.frames) > chunk_size:
            return False
        if index < len(chunks) - 1 and len(chunk.frames) != chunk_size:
            return False
        expected_tick = chunk.last_tick + 1
    return expected_tick == expected_frames
