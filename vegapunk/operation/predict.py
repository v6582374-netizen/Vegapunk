"""The Predictive Node: the imagined bench, and the credibility it must earn.

The condition field is continuous and every real point costs a robot, so the
loop carries a cheap probe: something that, given a candidate condition, says
what the witness would probably see. That is the node. It is mandatory in the
first loop -- not decoration added later -- because a loop that never predicts
can never be shown to have predicted wrongly, and unfalsifiable machinery is
exactly what this harness exists to avoid.

``Forecast``             what the node stakes on one condition
``PredictiveNode``       the seam any implementation fills
``TabularPredictiveNode`` the first rung: a table of observed outcomes
``score_predictions``    one outcome against one outcome, per real anchor
``CalibrationPolicy``    the rule by which credibility buys anything

Two prohibitions are absolute
-----------------------------
The node never judges an episode -- the witness does -- and it never publishes
a target to the real robot. Both are structural: nothing here can reach the
bridge or the adjudicator, and a ``Forecast`` is not an ``EpisodeEvidence``
and cannot become one.

Ranking, never levels
---------------------
A predictive model's ranking of conditions transfers to reality far better
than its absolute numbers do, so the node's authority is exactly that: it may
say "here is better than there" and be scored for it; it may never state an
unverified real success rate as fact. Its confidence is a stake, not a claim.

The ladder
----------
The interface is fixed; the rung is expected to change. The first rung is a
table of observed outcomes, honest to the point of bluntness: an unseen
condition is an explicit don't-know at zero confidence, which under the
calibration policy forces the real bench to answer. A fitted surface or a
learned generative bench replaces the table behind the same seam, and is
measured against the same experiment history.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from vegapunk.operation.campaign import (
    SOURCE_REAL,
    CalibrationScore,
    Condition,
    EpisodeEvidence,
    Prediction,
)
from vegapunk.operation.trace import OUTCOME_INDETERMINATE, TRACE_OUTCOMES

DEFAULT_MIN_SCORED = 10
"""Real anchors a node must have been scored on before its word buys budget."""

DEFAULT_MIN_ACCURACY = 0.8
"""How often those predictions must have matched reality."""


@dataclass(frozen=True)
class Forecast:
    """What the node stakes on one condition, before reality answers.

    ``uncertainty`` is required to exist rather than inferred by the reader:
    a node that will not say how unsure it is cannot be held to having said
    so.
    """

    outcome: str
    confidence: float
    predicted_observations: tuple[str, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        if self.outcome not in TRACE_OUTCOMES:
            raise ValueError(
                f"a forecast outcome must be one of {sorted(TRACE_OUTCOMES)}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        object.__setattr__(
            self, "predicted_observations", tuple(self.predicted_observations)
        )

    @property
    def uncertainty(self) -> float:
        return 1.0 - self.confidence


class PredictiveNode(Protocol):
    """Whatever fills the imagined-bench seam.

    A calibrated simulator, a digital twin, a learned world--action model, or
    the first-rung table below: all answer the same question the same way, so
    improved prediction technology is measured against the same history.
    """

    @property
    def version(self) -> str:
        """A stable name for this implementation and its state."""

    def forecast(self, condition: Condition) -> Forecast:
        """Stake a predicted witness outcome on one condition."""


class TabularPredictiveNode:
    """The first rung of the ladder: a table of observed outcomes.

    ``record`` is how reality reaches the table -- real, adjudicated outcomes
    only, fed between batches. The table forecasts the majority outcome it
    has seen with frequency as confidence, and answers an honest don't-know
    for anything it has not seen. That zero-confidence answer is what makes
    the first rung safe: under the calibration policy it can never talk the
    designer out of a real run.
    """

    def __init__(self, *, version: str = "tabular-1") -> None:
        if not version.strip():
            raise ValueError("a node must be versioned to be scored")
        self._version = version
        self._observed: dict[Condition, dict[str, int]] = {}

    @property
    def version(self) -> str:
        return self._version

    def record(self, condition: Condition, outcome: str) -> None:
        """Feed one real observed outcome into the table."""
        if outcome not in TRACE_OUTCOMES:
            raise ValueError(
                f"an observed outcome must be one of {sorted(TRACE_OUTCOMES)}"
            )
        counts = self._observed.setdefault(condition, {})
        counts[outcome] = counts.get(outcome, 0) + 1

    def forecast(self, condition: Condition) -> Forecast:
        counts = self._observed.get(condition)
        if not counts:
            return Forecast(
                outcome=OUTCOME_INDETERMINATE,
                confidence=0.0,
                detail=f"no outcome has been observed at {condition.label}",
            )
        total = sum(counts.values())
        outcome, seen = max(counts.items(), key=lambda item: item[1])
        return Forecast(
            outcome=outcome,
            confidence=seen / total,
            detail=f"{seen} of {total} observed episodes at "
            f"{condition.label} ended {outcome}",
        )


def score_predictions(
    predictions: Sequence[Prediction],
    evidence: Sequence[EpisodeEvidence],
    *,
    node_version: str,
) -> CalibrationScore:
    """Score one batch: each real anchor against the prediction it answers.

    One outcome against one outcome, nothing softer. A real episode with no
    prediction is not scored -- the node did not speak, so it is neither
    right nor wrong -- and a prediction whose condition never ran on the real
    bench is not scored either, because imagination cannot grade itself.
    """
    staked = {
        prediction.condition: prediction.outcome for prediction in predictions
    }
    scored = 0
    matched = 0
    for episode in evidence:
        if episode.source != SOURCE_REAL:
            continue
        if episode.condition not in staked:
            continue
        scored += 1
        if staked[episode.condition] == episode.outcome:
            matched += 1
    return CalibrationScore(
        node_version=node_version, scored=scored, matched=matched
    )


@dataclass(frozen=True)
class CalibrationPolicy:
    """The recorded rule by which a node's word buys real-bench budget.

    Credibility is earned by calibration, never granted by model branding.
    A node that has not been scored enough, or scored badly, forces every
    planned condition onto the real bench; it never allows a purely imagined
    conclusion. The thresholds live in a record rather than in code comments
    so the rule in force during a batch is part of that batch's history.
    """

    min_scored: int = DEFAULT_MIN_SCORED
    min_accuracy: float = DEFAULT_MIN_ACCURACY

    def __post_init__(self) -> None:
        if self.min_scored < 1:
            raise ValueError(
                "a policy that requires no scored predictions grants "
                "credibility for free"
            )
        if not 0.0 < self.min_accuracy <= 1.0:
            raise ValueError("min_accuracy must be within (0, 1]")

    def may_reduce_real_budget(
        self, score: CalibrationScore
    ) -> tuple[bool, str]:
        """Whether this score has earned any reduction of real runs, and why."""
        if score.scored < self.min_scored:
            return (
                False,
                f"the node has been scored on {score.scored} real anchors, "
                f"below the {self.min_scored} this policy requires; an "
                "unscored imagination buys nothing",
            )
        accuracy = score.accuracy or 0.0
        if accuracy < self.min_accuracy:
            return (
                False,
                f"the node's accuracy is {accuracy:.2f}, below the "
                f"{self.min_accuracy:.2f} this policy requires",
            )
        return (
            True,
            f"accuracy {accuracy:.2f} over {score.scored} scored anchors "
            "meets this policy",
        )
