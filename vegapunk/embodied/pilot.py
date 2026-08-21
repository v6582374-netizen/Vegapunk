"""The supervised hardware Pilot Batch, assembled around the sole Target Bridge.

This is intentionally a campaign boundary, not another controller.  Per-tick
motion remains inside :class:`OperationSession`, whose only publication route is
the Target Bridge.  The pilot adds the facts that make a real attempt usable:
an exact human approval, a new reset and usable independent witness, an explicit
intervention boundary, and a sealed record that never conflates a test double
with an operational run.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from vegapunk.embodied.episode import Intervention
from vegapunk.embodied.hardware import MotionAuthority
from vegapunk.embodied.promotion import PromotionSubmission
from vegapunk.operation.bridge import MotionGrant
from vegapunk.operation.episode import EpisodeOutcome, EpisodeRecord
from vegapunk.operation.policy import Observation
from vegapunk.operation.session import OperationSession

PILOT_SOURCE_TEST_DOUBLE = "hardware_faithful_test_double"
PILOT_SOURCE_OPERATIONAL = "supervised_operational_run"

PILOT_SUCCEEDED = "succeeded"
PILOT_FAILED = "failed"
PILOT_ABORTED = "aborted"
PILOT_INTERVENED = "intervened"
PILOT_INDETERMINATE = "indeterminate"

_SOURCES = frozenset({PILOT_SOURCE_TEST_DOUBLE, PILOT_SOURCE_OPERATIONAL})
_DISPOSITIONS = frozenset(
    {
        PILOT_SUCCEEDED,
        PILOT_FAILED,
        PILOT_ABORTED,
        PILOT_INTERVENED,
        PILOT_INDETERMINATE,
    }
)


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class HardwarePilotApproval:
    """A named human's approval of this exact Candidate and pilot campaign."""

    candidate_digest: str
    skill_revision_digest: str
    embodiment_digest: str
    configuration_digest: str
    campaign_digest: str
    approved_by: str
    approved_at: datetime
    statement: str

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.candidate_digest,
                self.skill_revision_digest,
                self.embodiment_digest,
                self.configuration_digest,
                self.campaign_digest,
                self.approved_by,
                self.statement,
            )
        ):
            raise ValueError("a hardware approval names every frozen input and human")

    def covers(self, submission: PromotionSubmission, campaign_digest: str) -> bool:
        candidate = submission.candidate
        skill = submission.skill
        embodiment = submission.embodiment
        configuration = submission.configuration
        return (
            candidate is not None
            and skill is not None
            and embodiment is not None
            and configuration is not None
            and self.candidate_digest == candidate.digest()
            and self.skill_revision_digest == skill.digest()
            and self.embodiment_digest == embodiment.digest()
            and self.configuration_digest == configuration.digest()
            and self.campaign_digest == campaign_digest
        )

    def motion_grant(self) -> MotionGrant:
        """Translate reviewed approval into the bridge's scoped human grant."""
        return MotionGrant(
            authorized_by=self.approved_by,
            configuration_digest=self.configuration_digest,
            statement=self.statement,
            granted_at=self.approved_at,
        )

    def digest(self) -> str:
        return _digest(
            {
                "candidate_digest": self.candidate_digest,
                "skill_revision_digest": self.skill_revision_digest,
                "embodiment_digest": self.embodiment_digest,
                "configuration_digest": self.configuration_digest,
                "campaign_digest": self.campaign_digest,
                "approved_by": self.approved_by,
                "approved_at": self.approved_at.isoformat(),
                "statement": self.statement,
            }
        )


@dataclass(frozen=True)
class PilotRunProvenance:
    """Distinguish CI's faithful double from a pre-registered operational run."""

    source: str
    operational_run_id: str = ""
    registration_digest: str = ""

    def __post_init__(self) -> None:
        if self.source not in _SOURCES:
            raise ValueError(f"unknown pilot source {self.source!r}")
        if self.source == PILOT_SOURCE_OPERATIONAL and (
            not self.operational_run_id.strip() or not self.registration_digest.strip()
        ):
            raise ValueError("a real pilot result names its pre-registered run")
        if self.source == PILOT_SOURCE_TEST_DOUBLE and (
            self.operational_run_id or self.registration_digest
        ):
            raise ValueError("a test double is never labelled as an operational run")


@dataclass(frozen=True)
class OperationalRunRegistration:
    operational_run_id: str
    batch_id: str
    campaign_digest: str
    approval_digest: str
    registered_by: str
    registered_at: datetime

    def digest(self) -> str:
        return _digest(
            {
                "operational_run_id": self.operational_run_id,
                "batch_id": self.batch_id,
                "campaign_digest": self.campaign_digest,
                "approval_digest": self.approval_digest,
                "registered_by": self.registered_by,
                "registered_at": self.registered_at.isoformat(),
            }
        )


OutcomeJudge = Callable[[str], EpisodeOutcome]


@dataclass(frozen=True)
class PilotEpisode:
    """One fresh real-session attempt, including its reset and witness facts."""

    episode_id: str
    session: OperationSession
    observations: tuple[Observation, ...]
    judge: OutcomeJudge
    intervention: Intervention | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observations", tuple(self.observations))
        if not self.episode_id.strip():
            raise ValueError("a pilot episode names its identity")
        if self.session.record.episode_id != self.episode_id:
            raise ValueError("a pilot session must write the planned episode identity")
        if not self.observations:
            raise ValueError("a pilot episode requires live observations")


@dataclass(frozen=True)
class PilotEpisodeEvidence:
    episode_id: str
    disposition: str
    record: EpisodeRecord
    detail: str
    intervention: Intervention | None = None

    def __post_init__(self) -> None:
        if self.disposition not in _DISPOSITIONS:
            raise ValueError(f"unknown pilot disposition {self.disposition!r}")

    def as_payload(self) -> dict[str, object]:
        return {
            "episode_id": self.episode_id,
            "disposition": self.disposition,
            "record": dict(self.record.as_payload()),
            "detail": self.detail,
            "intervention": None
            if self.intervention is None
            else self.intervention.as_payload(),
        }


@dataclass(frozen=True)
class PilotBatchEvidence:
    batch_id: str
    campaign_digest: str
    candidate_digest: str
    source: PilotRunProvenance
    episodes: tuple[PilotEpisodeEvidence, ...]
    sealed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "episodes", tuple(self.episodes))
        if not self.batch_id.strip() or not self.campaign_digest.strip():
            raise ValueError("pilot evidence names its pre-registered batch")
        if not self.episodes:
            raise ValueError("a pilot batch seals every attempted episode")

    @property
    def dispositions(self) -> tuple[str, ...]:
        return tuple(item.disposition for item in self.episodes)

    def digest(self) -> str:
        return _digest(
            {
                "batch_id": self.batch_id,
                "campaign_digest": self.campaign_digest,
                "candidate_digest": self.candidate_digest,
                "source": self.source.source,
                "operational_run_id": self.source.operational_run_id,
                "episodes": [episode.as_payload() for episode in self.episodes],
                "sealed_at": self.sealed_at.isoformat(),
            }
        )


class SupervisedPilotBatch:
    """Run a pre-registered batch; an abnormal episode stops the batch."""

    def __init__(
        self,
        *,
        submission: PromotionSubmission,
        batch_id: str,
        campaign_digest: str,
        approval: HardwarePilotApproval,
        manual_safety_authority: MotionAuthority,
        provenance: PilotRunProvenance,
        clock: Callable[[], datetime],
        operational_registration: OperationalRunRegistration | None = None,
    ) -> None:
        candidate = submission.candidate
        if candidate is None:
            raise ValueError("a hardware pilot requires a frozen Candidate")
        if not approval.covers(submission, campaign_digest):
            raise ValueError("hardware approval does not cover this exact pilot")
        if not batch_id.strip() or not campaign_digest.strip():
            raise ValueError("a pilot batch is pre-registered by identity and digest")
        skill = submission.skill
        embodiment = submission.embodiment
        assert skill is not None and embodiment is not None
        if not manual_safety_authority.covers(skill.version_id, embodiment.digest()):
            raise ValueError(
                "Manual Safety Authority does not cover this hardware pilot"
            )
        if provenance.source == PILOT_SOURCE_OPERATIONAL and (
            operational_registration is None
            or operational_registration.operational_run_id
            != provenance.operational_run_id
            or operational_registration.batch_id != batch_id
            or operational_registration.campaign_digest != campaign_digest
            or operational_registration.approval_digest != approval.digest()
            or operational_registration.digest() != provenance.registration_digest
        ):
            raise ValueError(
                "operational pilot evidence requires its pre-registered run"
            )
        self._submission = submission
        self._batch_id = batch_id
        self._campaign_digest = campaign_digest
        self._approval = approval
        self._provenance = provenance
        self._clock = clock

    def run(self, episodes: tuple[PilotEpisode, ...]) -> PilotBatchEvidence:
        """Execute fresh episodes; a hold, abort, or intervention ends the batch."""
        if not episodes:
            raise ValueError("a pilot batch has at least one pre-registered episode")
        identifiers = tuple(episode.episode_id for episode in episodes)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(
                "recovery after an intervention requires a new episode identity"
            )

        evidence: list[PilotEpisodeEvidence] = []
        for episode in episodes:
            item = self._run_episode(episode)
            evidence.append(item)
            if item.disposition in {
                PILOT_ABORTED,
                PILOT_INTERVENED,
                PILOT_INDETERMINATE,
            }:
                break
        candidate = self._submission.candidate
        assert candidate is not None
        return PilotBatchEvidence(
            batch_id=self._batch_id,
            campaign_digest=self._campaign_digest,
            candidate_digest=candidate.digest(),
            source=self._provenance,
            episodes=tuple(evidence),
            sealed_at=self._clock(),
        )

    def _run_episode(self, episode: PilotEpisode) -> PilotEpisodeEvidence:
        if not episode.session.record.reset.complete:
            return self._stop_before_motion(
                episode, PILOT_ABORTED, "the named reset was incomplete"
            )
        if (
            episode.session.record.reset.performed_at
            > episode.session.record.started_at
        ):
            return self._stop_before_motion(
                episode,
                PILOT_ABORTED,
                "the named reset was recorded after the episode start",
            )
        witness = episode.session.preflight_witness()
        if not witness.determinate:
            return self._stop_before_motion(
                episode,
                PILOT_INDETERMINATE,
                "the Independent Witness is unusable before motion: " + witness.detail,
            )

        episode.session.grant_motion_authority(self._approval.motion_grant())
        for tick, observation in enumerate(episode.observations):
            if episode.intervention is not None and tick == 0:
                stopped = episode.session.operator_stop(episode.intervention.detail)
                record = episode.session.finish(episode.judge(PILOT_INTERVENED))
                return PilotEpisodeEvidence(
                    episode_id=episode.episode_id,
                    disposition=PILOT_INTERVENED,
                    record=record,
                    detail=stopped.detail,
                    intervention=episode.intervention,
                )
            result = episode.session.step(observation)
            if not result.running:
                record = episode.session.finish(episode.judge(PILOT_ABORTED))
                return PilotEpisodeEvidence(
                    episode_id=episode.episode_id,
                    disposition=PILOT_ABORTED,
                    record=record,
                    detail=result.detail,
                )

        record = episode.session.finish(episode.judge(PILOT_SUCCEEDED))
        if record.outcome is None:
            raise AssertionError("a completed pilot episode has a measured outcome")
        disposition = (
            PILOT_SUCCEEDED
            if record.outcome.transfer == "transferred"
            else PILOT_FAILED
        )
        return PilotEpisodeEvidence(
            episode_id=episode.episode_id,
            disposition=disposition,
            record=record,
            detail=record.outcome.detail,
        )

    @staticmethod
    def _stop_before_motion(
        episode: PilotEpisode, disposition: str, detail: str
    ) -> PilotEpisodeEvidence:
        stopped = episode.session.operator_stop(detail)
        record = episode.session.finish(episode.judge(disposition))
        return PilotEpisodeEvidence(
            episode_id=episode.episode_id,
            disposition=disposition,
            record=record,
            detail=stopped.detail,
        )
