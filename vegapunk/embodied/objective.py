"""What makes one adaptation better than another, and what it will not reward.

A search is only as honest as the number it maximises. The obvious number --
how often the robot succeeded -- is the one thing this module will not
optimise, because a candidate can raise it by getting very good at the
corner of the distribution that happens to be sampled most, and a harness
that rewarded that would reliably deliver an adaptation that works in the
laboratory and nowhere else. Overfitting an interface fix is not a training
pathology here; it is the default outcome of scoring the mean.

So the score is a blend weighted towards the worst bucket of the sampled
regime. A candidate that is uniformly mediocre outranks a candidate that is
excellent in one bucket and poor in another, even when the second has the
better average. That ordering is the anti-overfitting argument in one
inequality, and it is asserted by test rather than described in prose.

Three refusals sit above the arithmetic.

A candidate that broke an envelope or was aborted is not a candidate with a
lower score. It is disqualified: ``as_metric`` reports ``WorstMetricValue``, so
no accumulation of successes anywhere else in the distribution can rank it
against a candidate that stayed inside its limits. Trading safety for success
rate is not a trade this objective can express.

A candidate measured fewer than ``minimum_attempts`` times is disqualified the
same way. An under-measured candidate with a lucky run would otherwise outrank
a thoroughly measured one, and the search would converge on whichever candidate
was evaluated least.

Nothing here computes anything from a simulator, reads anything from disk, or
tallies an outcome of its own. The trajectory ledger is the authority on what
happened: this module reads ``CampaignReport.attempts``, each
``AttemptRecord.outcome``, and the report's ledger-derived ``evidence``, and it
has no other source. A scorer that could recount successes would be the one
component able to disagree with the record of the runs it is scoring.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from vegapunk.embodied.admission import MINIMUM_STAGE_ATTEMPTS
from vegapunk.embodied.campaign import (
    HALTED_ABORTED,
    AttemptRecord,
    CampaignReport,
)
from vegapunk.embodied.trajectory import (
    OUTCOME_ABORTED,
    OUTCOME_REFUSED,
    OUTCOME_SUCCEEDED,
)
from vegapunk.mcts_node import MetricValue, WorstMetricValue

NOMINAL_BUCKET = "nominal"

BUCKET_SIDE_LOW = "low"
BUCKET_SIDE_HIGH = "high"

DISQUALIFIED_SCORE = float("-inf")
"""The score of a candidate that is not eligible to be ranked at all.

Negative infinity rather than zero, and the distinction is the point. Zero is a
real result -- a candidate that never succeeded -- and a disqualified candidate
must not be comparable to it, because a safety violation is a statement about
what the candidate is allowed to be, not about how well it performed.
"""

DEFAULT_SENSITIVITY_PENALTY = 0.75
"""How much a spread between buckets costs, per unit of spread.

The score reduces to ``0.25 * regime_rate + 0.75 * worst_bucket_rate``, so the
choice is really a weighting between the average and the worst case, and both
sides of 0.75 are excluded for a reason.

It is above 0.5 because at or below 0.5 a candidate can profit from becoming
more brittle: improving one bucket by a given amount while losing the same
amount in its worst bucket would raise the score, and the search would be paid
to specialise. Above 0.5 that trade always loses, which is the property that
makes the objective robustness-seeking rather than merely robustness-aware.

It is below 1.0 because at 1.0 the score is exactly the worst bucket's rate
and the rest of the distribution stops existing. A candidate whose worst
bucket sits at zero would then be indistinguishable from one that also fails
everywhere else, and the search would have no gradient to follow out of that
plateau -- which is where every early candidate starts.
"""

MAXIMUM_PROGRESS_CREDIT = 0.05
"""The most a candidate that never succeeded may earn for getting closer.

This exists because a binary objective is flat, and a flat objective is not an
objective at all. On the first real interface fault put through the harness,
twenty candidates were evaluated, every one scored exactly 0.000, and the fix
was inside the search space the whole time: with no gradient, UCT degenerates
into a random walk and the search cannot find what it can represent.

The credit is strictly a tie-breaker among failures, and the bound is what
makes that claim provable rather than hopeful. A candidate that succeeds even
once in the minimum ten attempts scores at least 0.1, and this credit is capped
at 0.05, so no amount of near-missing can ever outrank a single real success.
Progress therefore orders the plateau without ever being mistaken for a result.

It is applied only when ``successes == 0``. A candidate that sometimes works is
already ordered by how often it works, and adding distance credit on top would
let a candidate that succeeds rarely but misses narrowly outrank one that
succeeds more often -- ranking the objective's own proxy above the objective.
"""

MINIMUM_BUCKET_ATTEMPTS = 2
"""How many attempts a bucket needs before it may be called the worst.

One attempt is a coin flip reported as a rate. Letting a single failure define
the worst bucket would hand the score to sampling noise, and the search would
chase whichever bucket happened to be visited once. A bucket below this
floor is still reported as under-measured rather than quietly dropped.
"""


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class BucketOutcome:
    """One slice of the sampled regime, and how the candidate fared in it.

    A bucket is a claim about a region of the distribution, so it carries its
    own attempt count: a rate without the count behind it cannot be told apart
    from noise, and the worst-bucket rule depends on that difference.
    """

    label: str
    attempts: int
    successes: int

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("a bucket requires a label")
        if self.attempts < 0 or self.successes < 0:
            raise ValueError("attempts and successes cannot be negative")
        if self.successes > self.attempts:
            raise ValueError(
                f"bucket {self.label!r} records {self.successes} successes "
                f"for {self.attempts} attempts"
            )

    @property
    def success_rate(self) -> float:
        if self.attempts == 0:
            return 0.0
        return self.successes / self.attempts


@dataclass(frozen=True)
class CandidateScore:
    """What one candidate's recorded runs amount to, and why.

    ``findings`` carries every reason the score is what it is, in the same
    register the rest of the profile uses: a disqualification that could not be
    explained would be indistinguishable from a bug in the scorer.
    """

    candidate_digest: str
    attempts: int
    successes: int
    regime_success_rate: float
    worst_bucket: Optional[BucketOutcome]
    sensitivity: float
    safety_violations: int
    aborted: bool
    score: float
    findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))

    @property
    def disqualified(self) -> bool:
        """Whether this candidate may be ranked at all."""
        return self.score == DISQUALIFIED_SCORE

    def as_metric(self) -> MetricValue:
        """The comparable form the search ranks candidates by.

        A disqualified candidate returns ``WorstMetricValue``, which compares
        worse than every valid value regardless of magnitude. That is the only
        way to express "not a candidate" in a scalar objective: a very negative
        number is still a number a sufficiently lucky rival could fail to beat.
        """
        if self.disqualified:
            return WorstMetricValue()
        return MetricValue(self.score, maximize=True)

    def digest(self) -> str:
        return _digest(
            {
                "candidate_digest": self.candidate_digest,
                "attempts": self.attempts,
                "successes": self.successes,
                "regime_success_rate": round(self.regime_success_rate, 9),
                "worst_bucket": (
                    None
                    if self.worst_bucket is None
                    else {
                        "label": self.worst_bucket.label,
                        "attempts": self.worst_bucket.attempts,
                        "successes": self.worst_bucket.successes,
                    }
                ),
                "sensitivity": round(self.sensitivity, 9),
                "safety_violations": self.safety_violations,
                "aborted": self.aborted,
                "score": (
                    "disqualified"
                    if self.score == DISQUALIFIED_SCORE
                    else round(self.score, 9)
                ),
            }
        )


class RobustnessObjective:
    """Turns recorded campaigns into one comparable, robustness-weighted score.

    It is a pure function of the reports it is handed. That is a design
    constraint rather than an implementation detail: the objective is the last
    place a result could be improved by looking somewhere the evidence scope
    does not cover, so it is given no way to look.
    """

    def __init__(
        self,
        sensitivity_penalty: float = DEFAULT_SENSITIVITY_PENALTY,
        minimum_attempts: int = MINIMUM_STAGE_ATTEMPTS,
    ) -> None:
        if sensitivity_penalty < 0:
            raise ValueError(
                "a negative sensitivity penalty would pay the search to be "
                "brittle, which is the exact failure this objective exists "
                "to prevent"
            )
        if minimum_attempts < 1:
            raise ValueError(
                "a candidate with no executed attempts is unmeasured, so a "
                "minimum below one would let the search rank a candidate that "
                "never ran"
            )
        self._penalty = float(sensitivity_penalty)
        self._minimum_attempts = int(minimum_attempts)

    @property
    def sensitivity_penalty(self) -> float:
        return self._penalty

    @property
    def minimum_attempts(self) -> int:
        return self._minimum_attempts

    def score(
        self,
        candidate_digest: str,
        reports: Sequence[CampaignReport],
        progress: Optional[float] = None,
    ) -> CandidateScore:
        """Score one candidate from the campaigns that ran it.

        ``reports`` are the campaigns whose runs were driven by this
        candidate. The caller asserts that correspondence; nothing here can
        verify it, because a report records a configuration and a stage rather
        than an adaptation. The candidate digest is therefore carried through
        verbatim, so a mis-attributed score is at least traceable to the
        caller that attributed it.
        """
        findings: list[str] = []
        executed: list[AttemptRecord] = []
        safety_violations = 0
        aborted = False

        for report in reports:
            for record in report.attempts:
                # A refusal never moved the robot, so counting it as a failure
                # would score the configuration's admissibility as if it were
                # the candidate's performance.
                if record.outcome == OUTCOME_REFUSED:
                    continue
                executed.append(record)
                if record.outcome == OUTCOME_ABORTED:
                    aborted = True
            if report.halted == HALTED_ABORTED:
                aborted = True
            # The ledger's own count, not a recount of the records above: the
            # supervisor may have stopped a run for a violation the outcome
            # string does not name.
            safety_violations += report.evidence.safety_violations

        attempts = len(executed)
        successes = sum(
            1 for record in executed if record.outcome == OUTCOME_SUCCEEDED
        )
        regime_rate = successes / attempts if attempts else 0.0

        buckets, bucket_findings = self._buckets(executed)
        findings.extend(bucket_findings)
        worst = self._worst_bucket(buckets)
        sensitivity = (
            max(0.0, regime_rate - worst.success_rate)
            if worst is not None
            else 0.0
        )

        disqualified = False
        if safety_violations > 0:
            disqualified = True
            findings.append(
                f"{safety_violations} safety violation(s) are recorded "
                "against these runs; a candidate that broke an envelope is "
                "disqualified rather than ranked lower"
            )
        if aborted:
            disqualified = True
            findings.append(
                "at least one attempt was aborted; the configuration is "
                "quarantined, so this candidate is disqualified rather than "
                "ranked on the runs that preceded the abort"
            )
        if attempts < self._minimum_attempts:
            disqualified = True
            findings.append(
                f"{attempts} executed attempt(s) is below the "
                f"{self._minimum_attempts} this objective requires; an "
                "under-measured candidate must never outrank a measured one"
            )

        if disqualified:
            score = DISQUALIFIED_SCORE
        else:
            score = regime_rate - self._penalty * sensitivity
            # Only on the plateau, and only ever by less than one success.
            if successes == 0 and progress is not None:
                credit = min(1.0, max(0.0, float(progress)))
                score += credit * MAXIMUM_PROGRESS_CREDIT
                findings.append(
                    f"no attempt succeeded; ranked by proximity alone "
                    f"(progress {credit:.3f} -> "
                    f"{credit * MAXIMUM_PROGRESS_CREDIT:+.4f}), which cannot "
                    "outrank a single real success"
                )
        return CandidateScore(
            candidate_digest=candidate_digest,
            attempts=attempts,
            successes=successes,
            regime_success_rate=regime_rate,
            worst_bucket=worst,
            sensitivity=sensitivity,
            safety_violations=safety_violations,
            aborted=aborted,
            score=score,
            findings=tuple(findings),
        )

    def _buckets(
        self, executed: Sequence[AttemptRecord]
    ) -> tuple[tuple[BucketOutcome, ...], tuple[str, ...]]:
        """Split the executed attempts into the regions they sampled.

        Each regime axis is split at the midpoint of the span actually sampled,
        and the midpoint comes from the attempts in hand rather than from the
        axis's declared bounds. That is deliberate: a declared bound the
        campaign never approached would put every attempt on one side and
        report a sensitivity of zero for a distribution that was never
        explored. The midpoint of what was sampled always divides the evidence
        that exists.
        """
        samples: dict[int, Mapping[str, float]] = {}
        unsampled: list[AttemptRecord] = []
        for index, record in enumerate(executed):
            values = _regime_values(record)
            if values is None:
                unsampled.append(record)
            else:
                samples[index] = values

        if not samples:
            if not executed:
                return (), ()
            return (
                (
                    BucketOutcome(
                        label=NOMINAL_BUCKET,
                        attempts=len(executed),
                        successes=sum(
                            1
                            for record in executed
                            if record.outcome == OUTCOME_SUCCEEDED
                        ),
                    ),
                ),
                (),
            )

        findings: list[str] = []
        if unsampled:
            findings.append(
                f"{len(unsampled)} attempt(s) carry no regime sample and are "
                "pooled into the nominal bucket; they cannot testify about "
                "any axis"
            )

        axes = sorted({axis for values in samples.values() for axis in values})
        buckets: list[BucketOutcome] = []
        for axis in axes:
            spread = [
                values[axis] for values in samples.values() if axis in values
            ]
            midpoint = (min(spread) + max(spread)) / 2.0
            sides: dict[str, list[AttemptRecord]] = {
                BUCKET_SIDE_LOW: [],
                BUCKET_SIDE_HIGH: [],
            }
            for index, values in samples.items():
                if axis not in values:
                    continue
                side = (
                    BUCKET_SIDE_HIGH
                    if values[axis] >= midpoint
                    else BUCKET_SIDE_LOW
                )
                sides[side].append(executed[index])
            for side, records in sides.items():
                if not records:
                    continue
                buckets.append(
                    BucketOutcome(
                        label=f"{axis}:{side}",
                        attempts=len(records),
                        successes=sum(
                            1
                            for record in records
                            if record.outcome == OUTCOME_SUCCEEDED
                        ),
                    )
                )

        if unsampled:
            buckets.append(
                BucketOutcome(
                    label=NOMINAL_BUCKET,
                    attempts=len(unsampled),
                    successes=sum(
                        1
                        for record in unsampled
                        if record.outcome == OUTCOME_SUCCEEDED
                    ),
                )
            )
        return tuple(buckets), tuple(findings)

    def _worst_bucket(
        self, buckets: Sequence[BucketOutcome]
    ) -> Optional[BucketOutcome]:
        """The bucket the score is weighted towards, or nothing to weigh.

        Only buckets with enough attempts to mean something are eligible. When
        none qualify the candidate is left with no worst bucket and a
        sensitivity of zero, which is honest: the sampling was too thin to say
        the candidate is brittle, and the minimum-attempts rule is what stops
        that from being mistaken for evidence of robustness.
        """
        eligible = [
            bucket
            for bucket in buckets
            if bucket.attempts >= MINIMUM_BUCKET_ATTEMPTS
        ]
        if not eligible:
            return None
        return min(
            eligible,
            key=lambda bucket: (
                bucket.success_rate,
                -bucket.attempts,
                bucket.label,
            ),
        )


def _regime_values(record: AttemptRecord) -> Optional[Mapping[str, float]]:
    """The regime sample behind one attempt, if one was recorded.

    Read through ``getattr`` rather than by attribute access because the regime
    sample is attached by ``vegapunk.embodied.regime``, and this objective must
    score the campaigns that exist today as well as the ones that will carry a
    sample. An attempt with no sample is not an error: it is an attempt from
    the nominal regime, and treating it as a missing axis reading would invent
    a bucket the campaign never ran.
    """
    sample = getattr(record, "sample", None)
    if sample is None:
        variation = getattr(record, "variation", None)
        sample = getattr(variation, "sample", None)
    if sample is None:
        return None
    values = getattr(sample, "values", None)
    if not values:
        return None
    return {str(axis): float(value) for axis, value in values.items()}
