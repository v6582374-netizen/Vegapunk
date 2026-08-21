"""Run a frozen Candidate against live observations without an execution path.

Observation Shadow is deliberately a one-way membrane.  It receives the same
``Observation`` value a policy receives in deployment and materializes the same
``WholeBodyTarget`` value the deployment boundary validates.  Its only output,
however, is sealed evidence.  This module has no authority, bridge, or
transport dependency, so a compliant target remains an observed prediction.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter_ns
from typing import Protocol

from vegapunk.embodied.promotion import CandidateBundle
from vegapunk.operation.policy import DEFAULT_INTENT_MAX_AGE_S, Observation
from vegapunk.operation.target import WholeBodyTarget

COMPLIANT_OUTPUT = "compliant_output"
INFERENCE_FAILURE = "inference_failure"
STALE_INTENT = "stale_intent"
STARVATION = "starvation"
PROJECTION = "projection"
INVALID_TARGET = "invalid_target"

SHADOW_EVIDENCE_SOURCE = "real_observation_shadow"


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _image_reference_digest(reference: object) -> str:
    """Identify an image reference without copying its camera payload."""
    if isinstance(reference, bytes):
        return hashlib.sha256(reference).hexdigest()[:16]
    if isinstance(reference, (str, int, float, bool, type(None))):
        return _digest(reference)
    declared_digest = getattr(reference, "digest", None)
    if isinstance(declared_digest, str) and declared_digest.strip():
        return _digest({"declared_digest": declared_digest})
    return _digest(
        {
            "type": f"{type(reference).__module__}.{type(reference).__qualname__}",
            "representation": repr(reference),
        }
    )


@dataclass(frozen=True)
class CandidateOutput:
    """Raw Candidate output, converted through the deployment target contract.

    Keeping the raw representation at this boundary matters: malformed output
    must be observed as evidence rather than being impossible to represent in a
    test harness.  ``WholeBodyTarget`` remains the one constructor that decides
    its shape and executable envelope.
    """

    sequence: int
    source_time_ns: int
    valid_until_ns: int
    body: Sequence[float]
    left_hand: Sequence[float]
    right_hand: Sequence[float]
    intent_produced_at_ns: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "body", tuple(self.body))
        object.__setattr__(self, "left_hand", tuple(self.left_hand))
        object.__setattr__(self, "right_hand", tuple(self.right_hand))


class ShadowCandidateRuntime(Protocol):
    """The executable half of the exact Candidate artifact under observation."""

    policy_artifact_digest: str
    observation_schema_digest: str
    action_schema_digest: str

    def infer(
        self, observation: Observation
    ) -> CandidateOutput | WholeBodyTarget | None:
        """Produce one target prediction, or ``None`` when the policy starves."""


@dataclass(frozen=True)
class ObservationReceipt:
    """A stable audit handle for one live policy observation.

    Images in ``Observation`` are deliberately references rather than pixels.
    The receipt therefore retains their stream topology and a digest of the
    synchronized tracker state, which makes the observed input distribution
    measurable without copying camera data into an evidence ledger.
    """

    time_ns: int
    image_streams: tuple[str, ...]
    image_reference_digests: tuple[tuple[str, str], ...]
    tracker_sequence: int
    tracker_state_time_ns: int
    tracker_state_digest: str

    @classmethod
    def from_observation(cls, observation: Observation) -> ObservationReceipt:
        state = observation.state
        return cls(
            time_ns=observation.time_ns,
            image_streams=tuple(sorted(observation.images)),
            image_reference_digests=tuple(
                (stream, _image_reference_digest(reference))
                for stream, reference in sorted(observation.images.items())
            ),
            tracker_sequence=state.sequence,
            tracker_state_time_ns=state.state_time_ns,
            tracker_state_digest=_digest(
                {
                    "body": list(state.body),
                    "left_hand": list(state.left_hand),
                    "right_hand": list(state.right_hand),
                    "applied_target_sequence": state.applied_target_sequence,
                }
            ),
        )

    def as_payload(self) -> dict[str, object]:
        return {
            "time_ns": self.time_ns,
            "image_streams": list(self.image_streams),
            "image_reference_digests": dict(self.image_reference_digests),
            "tracker_sequence": self.tracker_sequence,
            "tracker_state_time_ns": self.tracker_state_time_ns,
            "tracker_state_digest": self.tracker_state_digest,
        }


@dataclass(frozen=True)
class ShadowAttempt:
    """One observed inference, never an execution attempt or task verdict."""

    observation_time_ns: int
    observation_receipt: ObservationReceipt
    outcome: str
    inference_latency_ns: int
    target: WholeBodyTarget | None
    detail: str = ""

    def __post_init__(self) -> None:
        if self.observation_time_ns <= 0:
            raise ValueError("a Shadow attempt names a live observation timestamp")
        if self.observation_receipt.time_ns != self.observation_time_ns:
            raise ValueError("a Shadow attempt receipt names its observation")
        if self.outcome not in {
            COMPLIANT_OUTPUT,
            INFERENCE_FAILURE,
            STALE_INTENT,
            STARVATION,
            PROJECTION,
            INVALID_TARGET,
        }:
            raise ValueError(f"unknown Shadow outcome {self.outcome!r}")
        if self.inference_latency_ns < 0:
            raise ValueError("inference latency cannot be negative")

    @property
    def has_compliant_output(self) -> bool:
        """Whether the output was contract-compliant, not whether a task worked."""
        return self.outcome == COMPLIANT_OUTPUT

    def as_payload(self) -> dict[str, object]:
        return {
            "observation_time_ns": self.observation_time_ns,
            "observation_receipt": self.observation_receipt.as_payload(),
            "outcome": self.outcome,
            "inference_latency_ns": self.inference_latency_ns,
            "target": None if self.target is None else self.target.as_payload(),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class PerceptionDistribution:
    """The observation coverage that a sealed Shadow run can establish."""

    observation_count: int
    image_streams: tuple[str, ...]
    distinct_image_references: int
    tracker_state_time_range_ns: tuple[int, int]


@dataclass(frozen=True)
class ShadowEvidence:
    """Sealed evidence about output compliance on live observations only."""

    candidate_digest: str
    policy_artifact_digest: str
    observation_schema_digest: str
    attempts: tuple[ShadowAttempt, ...]
    recorded_at: datetime
    source: str = SHADOW_EVIDENCE_SOURCE

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempts", tuple(self.attempts))
        if not all(
            value.strip()
            for value in (
                self.candidate_digest,
                self.policy_artifact_digest,
                self.observation_schema_digest,
            )
        ):
            raise ValueError("Shadow evidence names its frozen Candidate and schema")
        if self.source != SHADOW_EVIDENCE_SOURCE:
            raise ValueError("Shadow evidence is scoped to real observations only")
        if not self.attempts:
            raise ValueError("Shadow evidence needs at least one observed inference")
        if not all(isinstance(attempt, ShadowAttempt) for attempt in self.attempts):
            raise TypeError("Shadow evidence contains Shadow attempts only")

    @property
    def compliant_output_count(self) -> int:
        return sum(attempt.has_compliant_output for attempt in self.attempts)

    @property
    def perception_distribution(self) -> PerceptionDistribution:
        """The real observation coverage represented by this sealed evidence."""
        return PerceptionDistribution(
            observation_count=len(self.attempts),
            image_streams=tuple(
                sorted(
                    {
                        stream
                        for attempt in self.attempts
                        for stream in attempt.observation_receipt.image_streams
                    }
                )
            ),
            distinct_image_references=len(
                {
                    digest
                    for attempt in self.attempts
                    for _, digest in attempt.observation_receipt.image_reference_digests
                }
            ),
            tracker_state_time_range_ns=(
                min(
                    attempt.observation_receipt.tracker_state_time_ns
                    for attempt in self.attempts
                ),
                max(
                    attempt.observation_receipt.tracker_state_time_ns
                    for attempt in self.attempts
                ),
            ),
        )

    @property
    def conclusion(self) -> str:
        """The strongest statement this evidence is allowed to make."""
        return (
            "compliant candidate output on real observations; does not prove "
            "task execution success"
        )

    def as_payload(self) -> dict[str, object]:
        return {
            "candidate_digest": self.candidate_digest,
            "policy_artifact_digest": self.policy_artifact_digest,
            "observation_schema_digest": self.observation_schema_digest,
            "attempts": [attempt.as_payload() for attempt in self.attempts],
            "recorded_at": self.recorded_at.isoformat(),
            "source": self.source,
        }

    def digest(self) -> str:
        return _digest(self.as_payload())


class ShadowEvidenceLedger:
    """Append-only, Shadow-only evidence; it cannot amend execution records."""

    def __init__(self) -> None:
        self._evidence: dict[str, ShadowEvidence] = {}

    def seal(self, evidence: ShadowEvidence) -> ShadowEvidence:
        if not isinstance(evidence, ShadowEvidence):
            raise TypeError("the Shadow ledger accepts Shadow evidence only")
        return self._evidence.setdefault(evidence.digest(), evidence)

    def evidence_for(self, digest: str) -> ShadowEvidence | None:
        return self._evidence.get(digest)

    def evidence(self) -> tuple[ShadowEvidence, ...]:
        return tuple(self._evidence.values())


class ObservationShadow:
    """Evaluate the pinned Candidate over live observations and retain evidence.

    The constructor binds the runtime to the Candidate's artifact and observation
    contracts before any live frame is consumed.  Its public operations can only
    return a ``ShadowAttempt`` or sealed ``ShadowEvidence``.
    """

    def __init__(
        self,
        *,
        candidate: CandidateBundle,
        runtime: ShadowCandidateRuntime,
        ledger: ShadowEvidenceLedger,
        max_intent_age_ns: int = int(DEFAULT_INTENT_MAX_AGE_S * 1_000_000_000),
    ) -> None:
        if not isinstance(candidate, CandidateBundle):
            raise TypeError("Observation Shadow requires a frozen CandidateBundle")
        if not isinstance(ledger, ShadowEvidenceLedger):
            raise TypeError("Observation Shadow requires its own evidence ledger")
        if max_intent_age_ns < 0:
            raise ValueError("maximum intent age cannot be negative")
        missing = candidate.missing_fields()
        if missing:
            raise ValueError(
                "Observation Shadow requires a complete Candidate: "
                + ", ".join(missing)
            )
        if runtime.policy_artifact_digest != candidate.policy_artifact_digest:
            raise ValueError("Shadow runtime artifact differs from the Candidate")
        if runtime.observation_schema_digest != candidate.observation_schema_digest:
            raise ValueError(
                "Shadow runtime observation schema differs from the Candidate"
            )
        if runtime.action_schema_digest != candidate.action_schema_digest:
            raise ValueError("Shadow runtime action schema differs from the Candidate")
        self._candidate = candidate
        self._runtime = runtime
        self._ledger = ledger
        self._max_intent_age_ns = max_intent_age_ns
        self._last_sequence = -1
        self._attempts: list[ShadowAttempt] = []

    @property
    def attempts(self) -> tuple[ShadowAttempt, ...]:
        return tuple(self._attempts)

    def run(self, observation: Observation) -> ShadowAttempt:
        """Record exactly one inference against one live-format observation."""
        if not isinstance(observation, Observation):
            raise TypeError(
                "Observation Shadow accepts the deployed Observation schema"
            )

        started_ns = perf_counter_ns()
        try:
            output = self._runtime.infer(observation)
        except Exception as error:  # noqa: BLE001 - inference failure is evidence
            return self._record(
                observation,
                INFERENCE_FAILURE,
                perf_counter_ns() - started_ns,
                None,
                f"inference failed: {type(error).__name__}: {error}",
            )
        latency_ns = perf_counter_ns() - started_ns
        if output is None:
            return self._record(
                observation,
                STARVATION,
                latency_ns,
                None,
                "candidate produced no target for this observation",
            )

        try:
            target, intent_produced_at_ns, projection = self._materialize(output)
        except (TypeError, ValueError) as error:
            return self._record(
                observation,
                INVALID_TARGET,
                latency_ns,
                None,
                f"candidate output is not deployable: {error}",
            )

        if (
            intent_produced_at_ns is not None
            and observation.time_ns - intent_produced_at_ns > self._max_intent_age_ns
        ):
            return self._record(
                observation,
                STALE_INTENT,
                latency_ns,
                target,
                "candidate used an intent older than the deployment limit",
            )
        if target.sequence <= self._last_sequence:
            return self._record(
                observation,
                INVALID_TARGET,
                latency_ns,
                target,
                f"sequence {target.sequence} is not newer than {self._last_sequence}",
            )
        if target.expired_at(observation.time_ns):
            return self._record(
                observation,
                STALE_INTENT,
                latency_ns,
                target,
                f"frame {target.sequence} expired before this observation tick",
            )

        self._last_sequence = target.sequence
        if projection:
            return self._record(
                observation,
                PROJECTION,
                latency_ns,
                target,
                "candidate output was projected into the executable envelope: "
                + ", ".join(projection),
            )
        return self._record(observation, COMPLIANT_OUTPUT, latency_ns, target)

    def seal(self, recorded_at: datetime) -> ShadowEvidence:
        """Freeze the observed run in the dedicated Shadow evidence ledger."""
        return self._ledger.seal(
            ShadowEvidence(
                candidate_digest=self._candidate.digest(),
                policy_artifact_digest=self._candidate.policy_artifact_digest,
                observation_schema_digest=self._candidate.observation_schema_digest,
                attempts=self.attempts,
                recorded_at=recorded_at,
            )
        )

    def _record(
        self,
        observation: Observation,
        outcome: str,
        inference_latency_ns: int,
        target: WholeBodyTarget | None,
        detail: str = "",
    ) -> ShadowAttempt:
        attempt = ShadowAttempt(
            observation_time_ns=observation.time_ns,
            observation_receipt=ObservationReceipt.from_observation(observation),
            outcome=outcome,
            inference_latency_ns=inference_latency_ns,
            target=target,
            detail=detail,
        )
        self._attempts.append(attempt)
        return attempt

    @staticmethod
    def _materialize(
        output: CandidateOutput | WholeBodyTarget,
    ) -> tuple[WholeBodyTarget, int | None, tuple[str, ...]]:
        if isinstance(output, WholeBodyTarget):
            target = WholeBodyTarget(
                sequence=output.sequence,
                source_time_ns=output.source_time_ns,
                valid_until_ns=output.valid_until_ns,
                body=output.body,
                left_hand=output.left_hand,
                right_hand=output.right_hand,
            )
            return target, None, output.clamped
        if not isinstance(output, CandidateOutput):
            raise TypeError(
                "candidate output must be CandidateOutput, WholeBodyTarget, or None"
            )
        target = WholeBodyTarget(
            sequence=output.sequence,
            source_time_ns=output.source_time_ns,
            valid_until_ns=output.valid_until_ns,
            body=tuple(output.body),
            left_hand=tuple(output.left_hand),
            right_hand=tuple(output.right_hand),
        )
        return target, output.intent_produced_at_ns, target.clamped
