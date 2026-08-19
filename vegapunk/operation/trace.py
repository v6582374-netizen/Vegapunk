"""The Operation Trace Witness: the whole visible operation, judged from outside.

The Independent Witness supplies one bit -- is the lid open -- because one bit
is all the pour gate ever needed. The experiment loop needs more: it must tell
a completed reversible operation apart from a robot that stood still while the
lid stayed closed. A terminal closed lid is the *starting* state; treating it
as success would score "did nothing" as the best possible policy.

So this module witnesses the whole externally visible trace and adjudicates it
as a pure reduction. Three parts:

``TraceFact``             one externally observed predicate, with provenance
``OperationTraceWitness`` the append-only trace, and nothing else
``adjudicate``            the pure reduction from trace + reset to an outcome

And one more fact the trace cannot carry, because it is about the episode
*boundary* rather than its interior:

``ResetVerdict``          whether the world was back at the start, and who says
``ResetWitness``          the seam whatever establishes that fact fills

What the witness may not do
---------------------------
It observes, records, and is read. It has no method that emits a policy
command, selects a task phase, or advances anything -- the absence is the
design, exactly as with the Instrument Monitor one layer down. A witness that
sequenced the policy would be a hidden state machine, and the continuous
behaviour under study could never appear.

No probabilities here
---------------------
A fact's verdict is ``definite`` or ``indeterminate``, never a confidence.
Probabilistic belief belongs to the predictive node, which is allowed to be
wrong and is scored for it. The adjudicator is an authority, and an authority
that hedges cannot be audited: either the cup was seen returning home, fresh,
on a named channel, or the episode is not a success.

Why success is the ordered trace and nothing less
-------------------------------------------------
The reversible task is: lid closed and cup home, lid opens, cup lifts, cup
reaches the tilt region, cup returns home, lid closes. Every predicate must be
witnessed definite and fresh, in that order, over a confirmed reset. A missing
predicate fails; a predicate witnessed only stale or indeterminate holds the
verdict at indeterminate -- unusable evidence is never promoted to either side,
the same rule the lid witness applies one layer down.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

FACT_DEFINITE = "definite"
FACT_INDETERMINATE = "indeterminate"

_FACT_VERDICTS = frozenset({FACT_DEFINITE, FACT_INDETERMINATE})

PREDICATE_INITIAL_LID_CLOSED = "initial_lid_closed"
PREDICATE_LID_OPENED = "lid_opened"
PREDICATE_CUP_LIFTED = "cup_lifted"
PREDICATE_CUP_TILTED = "cup_reached_tilt_region"
PREDICATE_CUP_RETURNED = "cup_returned_home"
PREDICATE_FINAL_LID_CLOSED = "final_lid_closed"

REQUIRED_TRACE = (
    PREDICATE_INITIAL_LID_CLOSED,
    PREDICATE_LID_OPENED,
    PREDICATE_CUP_LIFTED,
    PREDICATE_CUP_TILTED,
    PREDICATE_CUP_RETURNED,
    PREDICATE_FINAL_LID_CLOSED,
)
"""The ordered predicates a successful reversible operation must exhibit.

"Pour" on this bench is a visible tilt gesture only. There is no liquid, no
mass, and no claim of material transfer anywhere in this trace.
"""

OUTCOME_SUCCEEDED = "succeeded"
OUTCOME_FAILED = "failed"
OUTCOME_INDETERMINATE = "indeterminate"

TRACE_OUTCOMES = frozenset(
    {OUTCOME_SUCCEEDED, OUTCOME_FAILED, OUTCOME_INDETERMINATE}
)


@dataclass(frozen=True)
class TraceFact:
    """One externally observed predicate, with the provenance to audit it.

    ``fresh`` is decided by whatever channel adapter produced the fact, against
    its own freshness bound, because the bound belongs to the sensor and not to
    the reduction. A stale fact is still recorded -- the record is honest about
    what was seen -- but ``adjudicate`` will never let it establish anything.
    """

    predicate: str
    verdict: str
    channel: str
    observed_at_ns: int
    fresh: bool
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.predicate.strip():
            raise ValueError("a fact must name the predicate it observes")
        if self.verdict not in _FACT_VERDICTS:
            raise ValueError(
                f"a fact's verdict must be one of {sorted(_FACT_VERDICTS)}, "
                f"got {self.verdict!r}"
            )
        if not self.channel.strip():
            raise ValueError("a fact must name the channel that observed it")
        if self.observed_at_ns <= 0:
            raise ValueError("a fact must carry when it was observed")

    @property
    def usable(self) -> bool:
        """Whether adjudication may rely on this fact."""
        return self.verdict == FACT_DEFINITE and self.fresh


class OperationTraceWitness:
    """The append-only trace of one episode, and nothing else.

    Observation is the only verb. There is deliberately no method here that
    could emit a command, choose a phase, or tell the policy anything at all.
    """

    def __init__(self, *, identity: str) -> None:
        if not identity.strip():
            raise ValueError("a trace witness must be identifiable")
        self._identity = identity
        self._trace: list[TraceFact] = []

    @property
    def identity(self) -> str:
        return self._identity

    @property
    def trace(self) -> tuple[TraceFact, ...]:
        return tuple(self._trace)

    def observe(self, fact: TraceFact) -> None:
        """Append one fact. Time may not run backwards inside one trace.

        An out-of-order append is refused rather than re-sorted, because a
        trace whose order was repaired after the fact is a trace whose order
        cannot be trusted as evidence of sequence.
        """
        if self._trace and fact.observed_at_ns < self._trace[-1].observed_at_ns:
            raise ValueError(
                f"fact {fact.predicate!r} at {fact.observed_at_ns} arrives "
                f"before the trace's last observation at "
                f"{self._trace[-1].observed_at_ns}; a trace is ordered or it "
                "is not a trace"
            )
        self._trace.append(fact)


@dataclass(frozen=True)
class ResetVerdict:
    """Whether the world was back at the episode's starting state, and who says.

    ``attested_by`` separates the two kinds of reset evidence without letting
    them blur: empty means the fact was witnessed by an external channel, the
    only kind an autonomous batch may run on; a name means a human attested it,
    which is admissible evidence but must stay visibly different in the record.
    """

    confirmed: bool
    channel: str
    observed_at_ns: int
    detail: str = ""
    attested_by: str = ""

    def __post_init__(self) -> None:
        if not self.channel.strip():
            raise ValueError("a reset verdict must name its channel")
        if self.observed_at_ns <= 0:
            raise ValueError("a reset verdict must carry when it was observed")

    @property
    def witnessed(self) -> bool:
        """True when the reset was established by a channel, not a person."""
        return not self.attested_by.strip()


class ResetWitness(Protocol):
    """Whatever establishes the start state from external evidence.

    The reversible task is supposed to put the cup back and close the lid; the
    harness never assumes that it did. This seam exists so a fixed bench camera
    can fill it on hardware and a deterministic stub can fill it in tests, with
    the loop's stopping rule identical in both rooms.
    """

    @property
    def identity(self) -> str:
        """A stable name for this channel, recorded with every episode."""

    def verify(self) -> ResetVerdict:
        """Establish the start state now, or say that it cannot be."""


@dataclass(frozen=True)
class TraceAdjudication:
    """What one episode's trace amounts to, as evidence."""

    outcome: str
    detail: str
    witnessed: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        return self.outcome == OUTCOME_SUCCEEDED


def adjudicate(
    trace: Sequence[TraceFact], *, reset: ResetVerdict
) -> TraceAdjudication:
    """Reduce one trace plus its reset to an outcome. Pure; no side effects.

    The only successful outcome is the full ``REQUIRED_TRACE`` witnessed in
    order by usable facts over a confirmed reset. An unusable fact -- stale or
    indeterminate -- never establishes its predicate and never fails it: if no
    usable fact for that predicate ever arrives, the outcome is indeterminate.
    A predicate with no fact at all fails, which is what makes a no-op run
    ending at a closed lid a failure rather than a success.
    """
    if not reset.confirmed:
        return TraceAdjudication(
            OUTCOME_INDETERMINATE,
            "the reset was not confirmed, so the episode ran from an unknown "
            f"starting state: {reset.detail or 'no detail'}",
        )

    witnessed: list[str] = []
    index = 0
    blocked_by_unusable: dict[int, TraceFact] = {}
    for fact in trace:
        if index == len(REQUIRED_TRACE):
            break
        if fact.predicate != REQUIRED_TRACE[index]:
            continue
        if fact.usable:
            witnessed.append(fact.predicate)
            index += 1
        else:
            blocked_by_unusable[index] = fact

    if index == len(REQUIRED_TRACE):
        return TraceAdjudication(
            OUTCOME_SUCCEEDED,
            "the full required trace was witnessed in order over a confirmed "
            "reset",
            witnessed=tuple(witnessed),
        )

    missing = REQUIRED_TRACE[index]
    if index in blocked_by_unusable:
        blocker = blocked_by_unusable[index]
        why = (
            "indeterminate"
            if blocker.verdict == FACT_INDETERMINATE
            else "stale"
        )
        return TraceAdjudication(
            OUTCOME_INDETERMINATE,
            f"required predicate {missing!r} was only witnessed {why} on "
            f"channel {blocker.channel!r}; unusable evidence is never "
            "promoted to a verdict",
            witnessed=tuple(witnessed),
        )
    return TraceAdjudication(
        OUTCOME_FAILED,
        f"the required witnessed trace is absent: {missing!r} was never "
        f"established after {witnessed[-1] if witnessed else 'the start'}",
        witnessed=tuple(witnessed),
    )
