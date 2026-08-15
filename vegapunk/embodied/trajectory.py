"""The trajectory ledger: what a run leaves behind.

A run is worth doing twice only if what it produced is written down once. This
module owns that record. It is deliberately separate from the execution loop:
the loop decides what happens to the robot, the ledger decides what the
organisation is allowed to conclude afterwards.

Three properties matter.

Records are append-only and scoped. A trajectory names the exact skill
revision, embodiment, and policy it ran on, so a run on one configuration can
never be read as evidence for another. Human judgements about a run -- a label
confirmation, a review that lifts a quarantine -- are appended as separate
records instead of editing history.

A hard failure quarantines its configuration. An aborted run is not a retryable
hiccup: until a named human records a clearance, the loop refuses to start the
same configuration again. Automatic retry after an abort is exactly how a
one-off becomes a pattern.

Training evidence must be earned. A trajectory becomes fine-tuning data only
when its outcome label was confirmed by a human, its observation stream is
complete, its embodiment is fully verified, and it was produced on real
hardware or in shadow mode. Failures are kept: a labelled failure is data, an
unlabelled success is not.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from vegapunk.embodied.admission import (
    STAGE_HARDWARE_SUPERVISED,
    STAGE_SHADOW_MODE,
    ADMISSION_STAGE_ORDER,
    EvidenceRecord,
)
from vegapunk.embodied.safety import (
    ABORT_ENVELOPE_VIOLATION,
    ABORT_OBSERVATION_STALE,
    ABORT_TIME_LIMIT,
)

OUTCOME_REFUSED = "refused"
OUTCOME_SUCCEEDED = "succeeded"
OUTCOME_FAILED_VERIFICATION = "failed_verification"
OUTCOME_ABORTED = "aborted"

_OUTCOMES = frozenset(
    {
        OUTCOME_REFUSED,
        OUTCOME_SUCCEEDED,
        OUTCOME_FAILED_VERIFICATION,
        OUTCOME_ABORTED,
    }
)

_SAFETY_VIOLATION_CAUSES = frozenset(
    {ABORT_ENVELOPE_VIOLATION, ABORT_TIME_LIMIT, ABORT_OBSERVATION_STALE}
)

_REAL_DATA_STAGES = (STAGE_SHADOW_MODE, STAGE_HARDWARE_SUPERVISED)

Scope = tuple[str, str, Optional[str]]


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class TrajectoryRecord:
    """One completed or refused attempt, and everything it proved.

    ``findings`` carries why an attempt did not succeed: the admission or
    preflight reasons for a refusal, the unmet postconditions for a failed
    verification. ``stream_complete`` is false whenever the supervisor stopped
    watching before the motion ended, which is what disqualifies the run as
    training data no matter how it was labelled.
    """

    run_id: str
    stage: str
    skill_version_id: str
    contract_digest: str
    selection_digest: str
    embodiment_digest: str
    policy_digest: Optional[str]
    outcome: str
    started_at: datetime
    observations: int = 0
    duration_s: float = 0.0
    abort_cause: Optional[str] = None
    detail: str = ""
    stream_complete: bool = False
    embodiment_verified: bool = False
    findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))
        if not self.run_id:
            raise ValueError("a TrajectoryRecord requires a run_id")
        if self.stage not in ADMISSION_STAGE_ORDER:
            raise ValueError(f"unknown admission stage {self.stage!r}")
        if self.outcome not in _OUTCOMES:
            raise ValueError(
                f"unknown outcome {self.outcome!r}; expected one of "
                f"{sorted(_OUTCOMES)!r}"
            )
        if self.observations < 0:
            raise ValueError("observations cannot be negative")
        if self.duration_s < 0:
            raise ValueError("duration_s cannot be negative")
        if self.outcome == OUTCOME_ABORTED and not self.abort_cause:
            raise ValueError("an aborted run must record its abort cause")
        if self.outcome != OUTCOME_ABORTED and self.abort_cause:
            raise ValueError(
                f"outcome {self.outcome!r} cannot carry an abort cause"
            )
        if self.outcome == OUTCOME_REFUSED and not self.findings:
            raise ValueError(
                "a refused run must record why it was not allowed to start"
            )
        if self.outcome == OUTCOME_REFUSED and self.observations:
            raise ValueError(
                "a refused run never executed and cannot report runtime "
                "observations"
            )
        if self.outcome == OUTCOME_SUCCEEDED and not self.stream_complete:
            raise ValueError(
                "a run whose observation stream was cut short cannot be "
                "recorded as a success"
            )

    def scope_key(self) -> Scope:
        return (
            self.skill_version_id,
            self.embodiment_digest,
            self.policy_digest,
        )

    @property
    def is_attempt(self) -> bool:
        """Whether the robot actually moved, and so whether it counts."""
        return self.outcome != OUTCOME_REFUSED

    @property
    def is_hard_failure(self) -> bool:
        """Whether this outcome forbids an automatic next attempt.

        Every abort qualifies, including a human stop: a person who intervened
        is owed a review before the same configuration runs again.
        """
        return self.outcome == OUTCOME_ABORTED

    @property
    def is_safety_violation(self) -> bool:
        return self.abort_cause in _SAFETY_VIOLATION_CAUSES

    def identity(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "stage": self.stage,
            "skill_version_id": self.skill_version_id,
            "contract_digest": self.contract_digest,
            "selection_digest": self.selection_digest,
            "embodiment_digest": self.embodiment_digest,
            "policy_digest": self.policy_digest,
            "outcome": self.outcome,
            "observations": self.observations,
            "duration_s": self.duration_s,
            "abort_cause": self.abort_cause,
            "stream_complete": self.stream_complete,
            "embodiment_verified": self.embodiment_verified,
            "started_at": self.started_at.isoformat(),
        }


@dataclass(frozen=True)
class LabelConfirmation:
    """A human's confirmation that a recorded outcome is the true outcome.

    An automatic postcondition check says the sensors agreed. This says a
    person looked at the run and stands behind the label, which is the bar for
    using it as training data.
    """

    run_id: str
    reviewer: str
    statement: str
    confirmed_at: datetime

    def __post_init__(self) -> None:
        if not self.reviewer.strip():
            raise ValueError("a LabelConfirmation must name its reviewer")
        if not self.statement.strip():
            raise ValueError(
                "a LabelConfirmation must record what the reviewer verified"
            )


@dataclass(frozen=True)
class RunClearance:
    """A named human lifting the quarantine left by a hard failure."""

    run_id: str
    reviewer: str
    statement: str
    cleared_at: datetime

    def __post_init__(self) -> None:
        if not self.reviewer.strip():
            raise ValueError("a RunClearance must name its reviewer")
        if not self.statement.strip():
            raise ValueError(
                "a RunClearance must record the resolution it is based on"
            )


@dataclass(frozen=True)
class TrainingManifest:
    """The digest-identified trajectory set a fine-tuning run may cite.

    ``excluded`` keeps every rejected trajectory with its reason, so a dataset
    that is smaller than expected can be explained instead of guessed at.
    """

    scope: Scope
    digest: str
    run_ids: tuple[str, ...]
    success_count: int
    failure_count: int
    excluded: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_ids", tuple(self.run_ids))
        object.__setattr__(
            self, "excluded", tuple((run, reason) for run, reason in self.excluded)
        )

    @property
    def total(self) -> int:
        return len(self.run_ids)


class TrajectoryLedger:
    """The append-only memory of every attempt and its human review."""

    def __init__(self) -> None:
        self._records: list[TrajectoryRecord] = []
        self._labels: dict[str, LabelConfirmation] = {}
        self._clearances: dict[str, RunClearance] = {}

    def record(self, trajectory: TrajectoryRecord) -> TrajectoryRecord:
        if any(
            existing.run_id == trajectory.run_id for existing in self._records
        ):
            raise ValueError(
                f"run {trajectory.run_id!r} is already recorded; a trajectory "
                "is written once"
            )
        self._records.append(trajectory)
        return trajectory

    def records(self) -> tuple[TrajectoryRecord, ...]:
        return tuple(self._records)

    def get(self, run_id: str) -> TrajectoryRecord:
        for record in self._records:
            if record.run_id == run_id:
                return record
        raise KeyError(f"run {run_id!r} is not recorded")

    def scoped(self, scope: Scope) -> tuple[TrajectoryRecord, ...]:
        return tuple(
            record for record in self._records if record.scope_key() == scope
        )

    def confirm_label(self, confirmation: LabelConfirmation) -> None:
        """Attach a human's outcome confirmation to a recorded run."""
        record = self.get(confirmation.run_id)
        if not record.is_attempt:
            raise ValueError(
                f"run {record.run_id!r} never executed, so its outcome cannot "
                "be confirmed as an observation of the world"
            )
        self._labels[confirmation.run_id] = confirmation

    def clear(self, clearance: RunClearance) -> None:
        """Lift the quarantine a specific hard failure created."""
        record = self.get(clearance.run_id)
        if not record.is_hard_failure:
            raise ValueError(
                f"run {record.run_id!r} is not a hard failure and needs no "
                "clearance"
            )
        self._clearances[clearance.run_id] = clearance

    def quarantine(self, scope: Scope) -> Optional[str]:
        """Report the uncleared hard failure blocking this configuration."""
        for record in reversed(self.scoped(scope)):
            if not record.is_attempt:
                continue
            if not record.is_hard_failure:
                return None
            if record.run_id in self._clearances:
                return None
            return (
                f"run {record.run_id!r} aborted with cause "
                f"{record.abort_cause!r} and has no recorded human clearance"
            )
        return None

    def derive_evidence(
        self,
        scope: Scope,
        stage: str,
        recorded_at: datetime,
        notes: str = "",
    ) -> EvidenceRecord:
        """Summarise this scope's runs at one stage as admission evidence.

        Evidence is derived rather than typed in, so an abort on hardware
        withdraws admission by arithmetic instead of by someone remembering to
        file it.
        """
        if stage not in ADMISSION_STAGE_ORDER:
            raise ValueError(f"unknown admission stage {stage!r}")
        attempts = [
            record
            for record in self.scoped(scope)
            if record.stage == stage and record.is_attempt
        ]
        skill_version_id, embodiment_digest, policy_digest = scope
        return EvidenceRecord(
            stage=stage,
            skill_version_id=skill_version_id,
            embodiment_digest=embodiment_digest,
            policy_digest=policy_digest,
            attempts=len(attempts),
            successes=sum(
                1 for record in attempts if record.outcome == OUTCOME_SUCCEEDED
            ),
            safety_violations=sum(
                1 for record in attempts if record.is_safety_violation
            ),
            recorded_at=recorded_at,
            notes=notes,
        )

    def training_manifest(self, scope: Scope) -> TrainingManifest:
        """Select the trajectories a future fine-tune may legitimately use."""
        eligible: list[TrajectoryRecord] = []
        excluded: list[tuple[str, str]] = []

        for record in self.scoped(scope):
            reason = self._ineligibility(record)
            if reason is None:
                eligible.append(record)
            else:
                excluded.append((record.run_id, reason))

        payload = [
            {
                "trajectory": record.identity(),
                "reviewer": self._labels[record.run_id].reviewer,
            }
            for record in eligible
        ]
        return TrainingManifest(
            scope=scope,
            digest=_digest(payload),
            run_ids=tuple(record.run_id for record in eligible),
            success_count=sum(
                1
                for record in eligible
                if record.outcome == OUTCOME_SUCCEEDED
            ),
            failure_count=sum(
                1
                for record in eligible
                if record.outcome != OUTCOME_SUCCEEDED
            ),
            excluded=tuple(excluded),
        )

    def _ineligibility(self, record: TrajectoryRecord) -> Optional[str]:
        if not record.is_attempt:
            return "the run was refused and produced no trajectory"
        if record.stage not in _REAL_DATA_STAGES:
            return (
                f"stage {record.stage} is not real-robot data and cannot be "
                "mixed into a hardware dataset"
            )
        if not record.stream_complete:
            return "the observation stream is incomplete"
        if not record.embodiment_verified:
            return (
                "the embodiment was not fully verified, so the trajectory's "
                "physical meaning is unknown"
            )
        if record.run_id not in self._labels:
            return "no human confirmed the recorded outcome"
        return None
