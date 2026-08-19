"""The Batch Designer: what to try next, said out loud before trying it.

This is the loop's "task planning and experiment design" stage, and its first
implementation is deliberately humble: a fixed condition table with a small
set of adaptive rules -- spend more where the last batch failed, prioritise
the reliability boundary, let a calibrated node take some conditions into
imagination, and propose a work order where a condition keeps failing. That
is already a loop that changes its plan on evidence, and it is honest about
how little it knows. A cleverer planner replaces this one behind the same
seam without the loop changing.

``Proposal``           one stated action, in one of the four classes
``RefusedCondition``   a candidate that failed the constraint check, on record
``BatchDesign``        the designer's whole output: plan, proposals, orders
``TableBatchDesigner`` the first implementation

The four classes
----------------
The action space settled for this harness is everything except the weights:
condition variation, invocation variation, data acquisition, and environment
work orders. Every proposal states its class because the classes have
different costs to the truth: a condition change moves within the measured
field, while an environment change reshapes the field and retires its
evidence -- and a designer that blurred that line could farm the stronger
curve by relabelling the weaker action.

Two output paths, structurally split
------------------------------------
Conditions the loop executes itself. A work order it cannot execute -- the
loop has no hands -- so the order goes to a named human staking its expected
gain, and confirming it opens a new generation. The split is in the types,
not in a convention.

If a language model is ever used to draft proposals, it drafts between
batches only; this deterministic designer and the campaign's constraint
checks decide admissibility, and nothing drafted can reach a robot directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from vegapunk.operation.campaign import (
    BatchPlan,
    BatchResult,
    CalibrationScore,
    Condition,
    Generation,
    ReliabilityEnvelope,
    WorkOrder,
)
from vegapunk.operation.predict import CalibrationPolicy

CLASS_CONDITION = "condition_variation"
CLASS_INVOCATION = "invocation_variation"
CLASS_DATA = "data_acquisition"
CLASS_ENVIRONMENT = "environment_work_order"

PROPOSAL_CLASSES = frozenset(
    {CLASS_CONDITION, CLASS_INVOCATION, CLASS_DATA, CLASS_ENVIRONMENT}
)

DEFAULT_EPISODES_PER_BATCH = 6
DEFAULT_REPEATED_FAILURE_THRESHOLD = 3
"""Failures at one condition, with no success ever, before the bench itself
is suspected rather than the condition."""


@dataclass(frozen=True)
class Proposal:
    """One stated action. The class and the rationale are not optional."""

    action_class: str
    rationale: str
    condition: Optional[Condition] = None
    work_order_id: str = ""

    def __post_init__(self) -> None:
        if self.action_class not in PROPOSAL_CLASSES:
            raise ValueError(
                f"a proposal's class must be one of "
                f"{sorted(PROPOSAL_CLASSES)}, got {self.action_class!r}"
            )
        if not self.rationale.strip():
            raise ValueError(
                "a proposal without a rationale cannot be argued with, which "
                "is the point of having one"
            )


@dataclass(frozen=True)
class RefusedCondition:
    """A candidate the constraint check refused, kept on record.

    Recorded rather than quietly dropped, because a designer whose refusals
    are invisible cannot be audited for what it declined to try.
    """

    condition: Condition
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("a refusal states why")


@dataclass(frozen=True)
class BatchDesign:
    """Everything one design pass produced."""

    plan: BatchPlan
    proposals: tuple[Proposal, ...]
    refused: tuple[RefusedCondition, ...]
    work_orders: tuple[WorkOrder, ...]


class TableBatchDesigner:
    """A fixed table with adaptive rules. Deterministic; no model, no language.

    ``admissible`` is the constraint check: a candidate must pass the same
    envelope discipline the monitor enforces on frames, and one that does not
    is recorded as refused. The default admits everything, which is correct
    for a table that was written by the person who owns the bench.
    """

    def __init__(
        self,
        *,
        table: Sequence[Condition],
        objective: str,
        episodes_per_batch: int = DEFAULT_EPISODES_PER_BATCH,
        calibration_policy: Optional[CalibrationPolicy] = None,
        admissible: Optional[Callable[[Condition], tuple[bool, str]]] = None,
        repeated_failure_threshold: int = DEFAULT_REPEATED_FAILURE_THRESHOLD,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if not table:
            raise ValueError("a designer needs at least one candidate condition")
        if not objective.strip():
            raise ValueError("a designer states the objective it designs for")
        if episodes_per_batch < 1:
            raise ValueError("a batch has at least one episode")
        if repeated_failure_threshold < 1:
            raise ValueError("the failure threshold must be positive")
        self._table = tuple(table)
        self._objective = objective
        self._episodes_per_batch = episodes_per_batch
        self._calibration_policy = calibration_policy or CalibrationPolicy()
        self._admissible = admissible or (lambda condition: (True, ""))
        self._repeated_failure_threshold = repeated_failure_threshold
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def design(
        self,
        *,
        plan_id: str,
        generation: Generation,
        envelope: ReliabilityEnvelope,
        prior_results: Sequence[BatchResult],
        calibration: CalibrationScore,
    ) -> BatchDesign:
        """Read what is known and emit the next pre-registrable batch."""
        admitted, refused = self._check_constraints()
        if not admitted:
            raise ValueError(
                "every candidate condition was refused by the constraint "
                "check; there is nothing admissible to plan"
            )

        stats = self._stats(envelope, generation, prior_results)
        last_failures = self._last_batch_failures(generation, prior_results)
        weights = {
            condition: self._weight(
                stats.get(condition, (0, 0)), last_failures.get(condition, 0)
            )
            for condition in admitted
        }
        allocation = self._allocate(weights)
        real, predicted, budget_rationale = self._split(
            allocation, calibration
        )
        work_orders = self._work_orders(
            plan_id, generation, stats, prior_results
        )
        proposals = self._proposals(
            real + predicted, stats, last_failures, work_orders
        )

        plan = BatchPlan(
            plan_id=plan_id,
            generation_id=generation.generation_id,
            objective=self._objective,
            real_conditions=real,
            predicted_conditions=predicted,
            real_anchor_count=len(real),
            predictive_node_version=calibration.node_version,
            confidence_threshold=self._calibration_policy.min_accuracy,
            selection_rationale=(
                "weighted toward last-batch failures, reliability boundaries "
                f"and unexplored cells; {budget_rationale}"
            ),
            expected_outcome=self._expected_outcome(real + predicted, stats),
            created_at=self._clock(),
        )
        return BatchDesign(
            plan=plan,
            proposals=proposals,
            refused=refused,
            work_orders=work_orders,
        )

    # -- rules ----------------------------------------------------------------

    def _check_constraints(
        self,
    ) -> tuple[tuple[Condition, ...], tuple[RefusedCondition, ...]]:
        admitted: list[Condition] = []
        refused: list[RefusedCondition] = []
        for condition in self._table:
            passes, reason = self._admissible(condition)
            if passes:
                admitted.append(condition)
            else:
                refused.append(
                    RefusedCondition(condition=condition, reason=reason)
                )
        return tuple(admitted), tuple(refused)

    @staticmethod
    def _stats(
        envelope: ReliabilityEnvelope,
        generation: Generation,
        prior_results: Sequence[BatchResult],
    ) -> dict[Condition, tuple[int, int]]:
        """(samples, successes) per condition, current generation only."""
        if envelope.generation_id == generation.generation_id:
            return {
                cell.condition: (cell.samples, cell.successes)
                for cell in envelope.cells
            }
        # The caller handed an envelope from another generation; recompute
        # from results rather than pool across benches.
        stats: dict[Condition, list[int]] = {}
        for result in prior_results:
            if result.generation_id != generation.generation_id:
                continue
            for episode in result.episodes:
                entry = stats.setdefault(episode.condition, [0, 0])
                entry[0] += 1
                entry[1] += 1 if episode.success else 0
        return {
            condition: (samples, successes)
            for condition, (samples, successes) in stats.items()
        }

    @staticmethod
    def _last_batch_failures(
        generation: Generation, prior_results: Sequence[BatchResult]
    ) -> dict[Condition, int]:
        for result in reversed(prior_results):
            if result.generation_id == generation.generation_id:
                failures: dict[Condition, int] = {}
                for episode in result.episodes:
                    if not episode.success:
                        failures[episode.condition] = (
                            failures.get(episode.condition, 0) + 1
                        )
                return failures
        return {}

    @staticmethod
    def _weight(stat: tuple[int, int], last_failures: int) -> int:
        samples, successes = stat
        if samples == 0:
            weight = 2  # unexplored: worth a look
        else:
            rate = successes / samples
            weight = 1
            if 0.0 < rate < 1.0:
                weight += 2  # a reliability boundary: information lives here
            elif rate == 0.0:
                weight += 1  # failing region: map its edge
        return weight + 2 * last_failures

    def _allocate(
        self, weights: dict[Condition, int]
    ) -> tuple[Condition, ...]:
        """Weighted round-robin: repeats buy depth, the cycle keeps coverage."""
        ordered = sorted(
            weights, key=lambda condition: (-weights[condition], condition.label)
        )
        remaining = dict(weights)
        allocation: list[Condition] = []
        while len(allocation) < self._episodes_per_batch:
            progressed = False
            for condition in ordered:
                if len(allocation) == self._episodes_per_batch:
                    break
                if remaining[condition] > 0:
                    allocation.append(condition)
                    remaining[condition] -= 1
                    progressed = True
            if not progressed:
                for condition in ordered:
                    if len(allocation) == self._episodes_per_batch:
                        break
                    allocation.append(condition)
        return tuple(allocation)

    def _split(
        self,
        allocation: tuple[Condition, ...],
        calibration: CalibrationScore,
    ) -> tuple[tuple[Condition, ...], tuple[Condition, ...], str]:
        allowed, why = self._calibration_policy.may_reduce_real_budget(
            calibration
        )
        if not allowed:
            return allocation, (), (
                f"every episode runs on the real bench: {why}"
            )
        keep_real = max(1, (len(allocation) + 1) // 2)
        return (
            allocation[:keep_real],
            allocation[keep_real:],
            f"half the budget handed to the predictive node: {why}",
        )

    def _work_orders(
        self,
        plan_id: str,
        generation: Generation,
        stats: dict[Condition, tuple[int, int]],
        prior_results: Sequence[BatchResult],
    ) -> tuple[WorkOrder, ...]:
        orders: list[WorkOrder] = []
        for condition, (samples, successes) in sorted(
            stats.items(), key=lambda item: item[0].label
        ):
            failures = samples - successes
            if successes > 0 or failures < self._repeated_failure_threshold:
                continue
            evidence = tuple(
                episode.episode_id
                for result in prior_results
                if result.generation_id == generation.generation_id
                for episode in result.episodes
                if episode.condition == condition and not episode.success
            )
            orders.append(
                WorkOrder(
                    order_id=f"wo-{plan_id}-{len(orders) + 1}",
                    generation_id=generation.generation_id,
                    proposed_change=(
                        f"add a fixture constraining {condition.label} so the "
                        "policy meets it in a repeatable pose"
                    ),
                    expected_gain=(
                        f"the cell at {condition.label} moves from "
                        f"0/{samples} to a reliable cell, growing the "
                        "envelope by one condition"
                    ),
                    cost_risk=(
                        "a bench fixture and a re-run of the first batch of "
                        "the new generation; no new risk to the robot"
                    ),
                    motivating_evidence=evidence,
                    proposed_at=self._clock(),
                )
            )
        return tuple(orders)

    def _proposals(
        self,
        allocation: tuple[Condition, ...],
        stats: dict[Condition, tuple[int, int]],
        last_failures: dict[Condition, int],
        work_orders: tuple[WorkOrder, ...],
    ) -> tuple[Proposal, ...]:
        proposals: list[Proposal] = []
        unexplored: list[Condition] = []
        seen: set[Condition] = set()
        for condition in allocation:
            if condition in seen:
                continue
            seen.add(condition)
            samples, successes = stats.get(condition, (0, 0))
            if samples == 0:
                unexplored.append(condition)
                rationale = f"no evidence yet at {condition.label}"
            elif last_failures.get(condition):
                rationale = (
                    f"{last_failures[condition]} failure(s) at "
                    f"{condition.label} in the last batch; spend where it "
                    "failed"
                )
            else:
                rationale = (
                    f"{successes}/{samples} at {condition.label}; keep the "
                    "estimate honest"
                )
            proposals.append(
                Proposal(
                    action_class=CLASS_CONDITION,
                    rationale=rationale,
                    condition=condition,
                )
            )
        if unexplored:
            proposals.append(
                Proposal(
                    action_class=CLASS_DATA,
                    rationale=(
                        "these cells are starved of evidence: "
                        + ", ".join(c.label for c in unexplored)
                    ),
                )
            )
        for order in work_orders:
            proposals.append(
                Proposal(
                    action_class=CLASS_ENVIRONMENT,
                    rationale=(
                        f"{order.proposed_change}; expected gain: "
                        f"{order.expected_gain}"
                    ),
                    work_order_id=order.order_id,
                )
            )
        return tuple(proposals)

    @staticmethod
    def _expected_outcome(
        allocation: tuple[Condition, ...],
        stats: dict[Condition, tuple[int, int]],
    ) -> str:
        parts: list[str] = []
        for condition in dict.fromkeys(allocation):
            samples, successes = stats.get(condition, (0, 0))
            if samples == 0:
                parts.append(f"{condition.label}: unknown, expect to learn")
            else:
                parts.append(
                    f"{condition.label}: expect ~{successes}/{samples} "
                    "observed rate to hold"
                )
        return "; ".join(parts)
