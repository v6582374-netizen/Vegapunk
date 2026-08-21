"""Freeze a Golden Generation episode into training and replay evidence.

The operation layer owns live capture and target validity.  This module adds
only the Generation provenance that turns that capture into training material:
which Golden Skill and bench produced it, how its clocks were aligned, and why
it is or is not eligible for training and replay.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from vegapunk.embodied.embodiment import EmbodimentProfile
from vegapunk.embodied.promotion import (
    GOLDEN_INSTRUMENT_OPERATION_LOOP,
    GOLDEN_SKILL_ID,
    GoldenSkillRevision,
    PromotionConfiguration,
)
from vegapunk.operation.episode import EpisodeRecord, Frame
from vegapunk.operation.target import WholeBodyTarget
from vegapunk.operation.witness import LID_CLOSED, LID_INDETERMINATE, LID_OPEN


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class TimeSynchronization:
    """The named alignment between observation, target, and witness clocks."""

    synchronization_id: str
    synchronized_at: datetime
    observation_clock: str
    target_clock: str
    witness_clock: str
    max_skew_ns: int

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.synchronization_id,
                self.observation_clock,
                self.target_clock,
                self.witness_clock,
            )
        ):
            raise ValueError("time synchronization names every participating clock")
        if self.max_skew_ns <= 0:
            raise ValueError("time synchronization must state a positive skew bound")

    def as_payload(self) -> dict[str, object]:
        return {
            "synchronization_id": self.synchronization_id,
            "synchronized_at": self.synchronized_at.isoformat(),
            "observation_clock": self.observation_clock,
            "target_clock": self.target_clock,
            "witness_clock": self.witness_clock,
            "max_skew_ns": self.max_skew_ns,
        }

    def digest(self) -> str:
        return _digest(self.as_payload())


@dataclass(frozen=True)
class Intervention:
    """A human or safety-system act that interrupted normal autonomy."""

    time_ns: int
    performed_by: str
    detail: str

    def __post_init__(self) -> None:
        if self.time_ns <= 0:
            raise ValueError("an intervention must carry its time")
        if not self.performed_by.strip() or not self.detail.strip():
            raise ValueError("an intervention names its actor and what changed")

    def as_payload(self) -> dict[str, object]:
        return {
            "time_ns": self.time_ns,
            "performed_by": self.performed_by,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AbortRecord:
    """A named abort fact, distinct from outcome and intervention."""

    time_ns: int
    requested_by: str
    reason: str

    def __post_init__(self) -> None:
        if self.time_ns <= 0:
            raise ValueError("an abort must carry its time")
        if not self.requested_by.strip() or not self.reason.strip():
            raise ValueError("an abort names its requester and reason")

    def as_payload(self) -> dict[str, object]:
        return {
            "time_ns": self.time_ns,
            "requested_by": self.requested_by,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class TrainingEpisode:
    """One provenance-complete Golden Generation episode.

    The operation record remains the source for observations, targets, witness
    readings, testimony, reset, and outcome.  This frozen envelope prevents
    any of those facts from being detached from the skill and bench that made
    them meaningful.
    """

    record: EpisodeRecord
    skill: GoldenSkillRevision
    embodiment: EmbodimentProfile
    configuration: PromotionConfiguration
    synchronization: TimeSynchronization
    frames: tuple[Frame, ...]
    interventions: tuple[Intervention, ...] = ()
    aborts: tuple[AbortRecord, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "frames", tuple(self.frames))
        object.__setattr__(self, "interventions", tuple(self.interventions))
        object.__setattr__(self, "aborts", tuple(self.aborts))

        if self.skill.skill.skill_id != GOLDEN_SKILL_ID:
            raise ValueError("a Training Episode must bind the Golden Skill")
        if self.skill.operation_loop != GOLDEN_INSTRUMENT_OPERATION_LOOP:
            raise ValueError("a Training Episode requires the complete Golden loop")
        if self.configuration.embodiment_digest != self.embodiment.digest():
            raise ValueError("the episode configuration names another embodiment")
        if self.record.configuration_digest != self.configuration.digest():
            raise ValueError("the operation record names another configuration")
        if self.record.reset.performed_at > self.record.started_at:
            raise ValueError("the named Reset Record must exist before the episode")
        if not self.frames:
            raise ValueError("a Training Episode requires synchronized observations")
        if self.record.frame_count != len(self.frames):
            raise ValueError("the operation record frame count must match its capture")
        for expected_index, frame in enumerate(self.frames):
            if not isinstance(frame, Frame):
                raise TypeError("a Training Episode records Frame values only")
            if frame.index != expected_index:
                raise ValueError("episode observations must preserve their complete order")
            if not isinstance(frame.target, WholeBodyTarget):
                raise TypeError("replay targets must pass the WholeBodyTarget contract")
            if frame.lid not in {LID_OPEN, LID_CLOSED, LID_INDETERMINATE}:
                raise ValueError("every frame records an Independent Witness fact")
            if frame.state.applied_target_sequence != frame.target.sequence:
                raise ValueError(
                    "every observation must name the WholeBodyTarget applied to it"
                )
            synchronized_times = (
                frame.time_ns,
                frame.state.state_time_ns,
                frame.target.source_time_ns,
            )
            if (
                max(synchronized_times) - min(synchronized_times)
                > self.synchronization.max_skew_ns
            ):
                raise ValueError(
                    "observation, Independent Witness, state, and target exceed "
                    "the declared synchronization bound"
                )
            camera_ids = {camera.identity for camera in self.record.cameras}
            if set(frame.images) != camera_ids:
                raise ValueError(
                    "every frame must carry exactly the observations named by "
                    "the record"
                )
        sequences = tuple(frame.target.sequence for frame in self.frames)
        if sequences != tuple(sorted(sequences)) or len(set(sequences)) != len(sequences):
            raise ValueError("episode targets must preserve strict target ordering")
        if not all(isinstance(item, Intervention) for item in self.interventions):
            raise TypeError("interventions must remain explicit Intervention facts")
        if not all(isinstance(item, AbortRecord) for item in self.aborts):
            raise TypeError("aborts must remain explicit AbortRecord facts")

    def as_payload(self) -> dict[str, object]:
        return {
            "record": dict(self.record.as_payload()),
            "skill_revision": self.skill.digest(),
            "embodiment": self.embodiment.digest(),
            "configuration": self.configuration.digest(),
            "time_synchronization": self.synchronization.as_payload(),
            "frames": [dict(frame.as_payload()) for frame in self.frames],
            "interventions": [item.as_payload() for item in self.interventions],
            "aborts": [item.as_payload() for item in self.aborts],
        }

    def digest(self) -> str:
        return _digest(self.as_payload())

    def artifact_digest(self) -> str:
        """The immutable capture artifact identity used by qualified replay."""
        return _digest({"training_episode": self.digest(), "frames": len(self.frames)})

    def eligibility(self) -> tuple[bool, str]:
        """Whether this exact episode may become training or replay material."""
        eligible, reason = self.record.trainable()
        reasons = [] if eligible else [reason]
        if self.interventions:
            reasons.append(
                "intervention was recorded; retain it but do not imitate it"
            )
        if self.aborts:
            reasons.append("abort was recorded; retain it but do not replay it")
        if any(frame.lid == LID_INDETERMINATE for frame in self.frames):
            reasons.append("indeterminate Independent Witness reading was recorded")
        return not reasons, "; ".join(reasons)


@dataclass(frozen=True)
class EpisodeTrainingManifest:
    """The full training decision: eligible episodes and every exclusion."""

    episodes: tuple[TrainingEpisode, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "episodes", tuple(self.episodes))
        identifiers = tuple(episode.record.episode_id for episode in self.episodes)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("a Training Manifest cannot contain an episode twice")

    @property
    def eligible_episode_ids(self) -> tuple[str, ...]:
        return tuple(
            episode.record.episode_id
            for episode in self.episodes
            if episode.eligibility()[0]
        )

    @property
    def excluded_episode_reasons(self) -> Mapping[str, str]:
        return MappingProxyType(
            {
                episode.record.episode_id: reason
                for episode in self.episodes
                for eligible, reason in (episode.eligibility(),)
                if not eligible
            }
        )

    def as_payload(self) -> dict[str, object]:
        return {
            "eligible_episodes": list(self.eligible_episode_ids),
            "excluded_episodes": dict(self.excluded_episode_reasons),
            "episode_digests": {
                episode.record.episode_id: episode.digest() for episode in self.episodes
            },
        }

    def digest(self) -> str:
        return _digest(self.as_payload())


@dataclass(frozen=True)
class InitialStateEnvelope:
    """The reset and first synchronized observation a replay must start from."""

    source_episode_id: str
    configuration_digest: str
    reset_digest: str
    first_observation_digest: str

    @classmethod
    def from_episode(cls, episode: TrainingEpisode) -> InitialStateEnvelope:
        return cls(
            source_episode_id=episode.record.episode_id,
            configuration_digest=episode.configuration.digest(),
            reset_digest=_digest(dict(episode.record.reset.as_payload())),
            first_observation_digest=_digest(dict(episode.frames[0].as_payload())),
        )

    def as_payload(self) -> dict[str, str]:
        return {
            "source_episode_id": self.source_episode_id,
            "configuration_digest": self.configuration_digest,
            "reset_digest": self.reset_digest,
            "first_observation_digest": self.first_observation_digest,
        }

    def digest(self) -> str:
        return _digest(self.as_payload())


@dataclass(frozen=True)
class QualifiedReplay:
    """A replayable training artifact whose actions remain WholeBodyTargets."""

    source_episode_id: str
    source_episode_digest: str
    control_frequency_hz: float
    initial_state_envelope: InitialStateEnvelope
    artifact_digest: str
    targets: tuple[WholeBodyTarget, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "targets", tuple(self.targets))
        if not self.source_episode_id.strip() or not self.source_episode_digest.strip():
            raise ValueError("a Qualified Replay binds its source episode")
        if self.control_frequency_hz <= 0:
            raise ValueError("a Qualified Replay states a positive control frequency")
        if not self.artifact_digest.strip():
            raise ValueError("a Qualified Replay binds its capture artifact")
        if not self.targets:
            raise ValueError("a Qualified Replay requires WholeBodyTargets")
        if not all(isinstance(target, WholeBodyTarget) for target in self.targets):
            raise TypeError("a replay cannot introduce a direct-command path")
        sequences = tuple(target.sequence for target in self.targets)
        if sequences != tuple(sorted(sequences)) or len(set(sequences)) != len(sequences):
            raise ValueError("replay targets must retain strict WholeBodyTarget order")

    def digest(self) -> str:
        return _digest(
            {
                "source_episode_id": self.source_episode_id,
                "source_episode_digest": self.source_episode_digest,
                "control_frequency_hz": self.control_frequency_hz,
                "initial_state_envelope": self.initial_state_envelope.digest(),
                "artifact_digest": self.artifact_digest,
                "target_sequences": [target.sequence for target in self.targets],
            }
        )


def freeze_qualified_replay(episode: TrainingEpisode) -> QualifiedReplay:
    """Freeze an eligible capture without creating another actuator interface."""
    eligible, reason = episode.eligibility()
    if not eligible:
        raise ValueError(f"episode is not qualified for replay: {reason}")
    return QualifiedReplay(
        source_episode_id=episode.record.episode_id,
        source_episode_digest=episode.digest(),
        control_frequency_hz=episode.embodiment.control_frequency_hz,
        initial_state_envelope=InitialStateEnvelope.from_episode(episode),
        artifact_digest=episode.artifact_digest(),
        targets=tuple(frame.target for frame in episode.frames),
    )
