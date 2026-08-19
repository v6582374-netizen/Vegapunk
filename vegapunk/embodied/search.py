"""What a tree search over adaptations is allowed to conclude, and what it
is not allowed to touch.

The repository already contains an AI-Scientist search. That machinery
searches by letting a language model edit files inside a copied directory and
reads its reward out of ``run_1/final_info.json``, which makes two
assumptions this harness cannot make: that a candidate is a directory, and
that failure means a crash. A typed interface candidate is neither. It is a
value, it is scored by a physics campaign rather than by a process exit, and
its interesting failures are the ones where nothing crashes at all -- a
mis-scaled command that completes every run and satisfies no postcondition.
A reward that collapses to a small set of integers cannot distinguish those
from success, so exploitation would be driven by noise.

This module is therefore a small search and nothing else. It decides what to
try next. Its refusals are all of the same kind: it refuses to be the
component that also decides whether a candidate was good.

It refuses to run without a control. The root is ``space.identity()`` -- the
no-op adaptation -- and it is evaluated first, unconditionally, before any
mutation is proposed. An improvement measured against no baseline is a claim
about nothing, and the failure is not detectable afterwards: a search with no
control reports its best candidate exactly as confidently whether or not the
untouched system already did better.

It refuses to grow a subtree from a candidate that recorded a safety
violation or was aborted. Such a candidate is disqualified, not merely poor,
and mutating it spends the budget exploring neighbourhoods of a region that
was already ruled out -- while producing children whose parent's own score
was never valid.

It refuses to exceed its evaluation budget, counting the root. Evaluation is
a campaign of simulated runs; it is the only expensive thing here, so the
budget is a cap on evaluations rather than on iterations or on wall time.

It refuses to be non-reproducible. Every mutation draws from one seeded
generator, so two runs with the same seed visit the same candidates in the
same order. A search that cannot be replayed cannot have its finding
re-examined, which means it cannot be trusted with a physical conclusion.

It refuses to interpret an evaluator failure as a bad candidate. An exception
halts the search with the partial ranking intact, because the evaluations
already paid for are the expensive artifact and a crashed campaign says
nothing about the candidate it crashed on.

What it never does: no filesystem, no model calls, no threads. It does not
judge safety, does not count successes, does not decide what a score means.
Ordering is delegated to ``MetricValue``, disqualification to
``CandidateScore``, and candidate structure to ``AdaptationSpace``.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from typing import Optional, Protocol

from vegapunk.mcts_node import MetricValue, WorstMetricValue

DEFAULT_EXPLORATION_CONSTANT = 1.414
"""sqrt(2), the standard UCT1 constant for rewards normalised to [0, 1].

Rewards here are normalised (see ``_reward``), so the textbook value applies
rather than a tuned one. Tuning it would require more search runs than a
physics campaign can afford, and an untuned standard value is honest about
that.
"""

DEFAULT_MUTATION_SCALE = 0.25
"""A quarter of the space's per-parameter range for one mutation step.

Chosen against the two failure modes rather than by sweeping: too small and
the search spends its whole budget inside the noise floor of a campaign, so
every child is indistinguishable from its parent; too large and each child is
an unrelated point, which makes the tree a random sample and the parent
statistics meaningless. A quarter-range step is large enough to move a
measured score and small enough that a child remains a neighbour of the
parent that justified it.
"""

DEFAULT_BRANCHING = 3
DEFAULT_MAX_DEPTH = 4

HALTED_BUDGET_EXHAUSTED = "budget_exhausted"
HALTED_SPACE_EXHAUSTED = "space_exhausted"
HALTED_EVALUATOR_FAILED = "evaluator_failed"

_MINIMUM_REWARD = 0.0
_MAXIMUM_REWARD = 1.0


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


class CandidateEvaluator(Protocol):
    """Whatever turns one candidate into one measured score.

    Deliberately the narrowest possible seam. The search must not know that
    an evaluation is a simulated campaign, how many runs it takes, or what
    disqualifies a candidate; if it knew any of that it would be able to
    shortcut it.
    """

    def evaluate(self, candidate) -> "CandidateScore":  # noqa: F821
        ...


def _metric_of(score: object) -> MetricValue:
    """Read a score's ordering, trusting the score to define its own worst.

    A score that cannot produce a metric is treated as disqualified rather
    than as unordered. The alternative -- raising -- would let a malformed
    score abort a search that has already paid for its evaluations.
    """
    as_metric = getattr(score, "as_metric", None)
    if as_metric is None:
        return WorstMetricValue(maximize=True)
    metric = as_metric()
    if not isinstance(metric, MetricValue):
        return WorstMetricValue(maximize=True)
    return metric


def _is_disqualified(score: object, metric: MetricValue) -> bool:
    """Disqualification is the score's judgement, read three ways.

    ``WorstMetricValue`` is the contracted signal, but a violation or an abort
    is checked directly as well: a score that reported a safety violation and
    still returned an orderable metric must not become the parent of a
    subtree, and the search is not the component that gets to argue about
    which of the two fields is authoritative.
    """
    if metric.is_worst:
        return True
    if int(getattr(score, "safety_violations", 0) or 0) > 0:
        return True
    return bool(getattr(score, "aborted", False))


@dataclass
class CandidateNode:
    """One evaluated candidate and its accumulated search statistics.

    The only mutable value in this module, and mutable by necessity: UCT is
    defined by backpropagation, so a node's visit count and reward total are
    revised by every descendant evaluated after it. Freezing the node would
    mean rebuilding the path to the root on each visit and losing object
    identity, which the parent links and the ranking both rely on.

    Everything a reviewer would need to trust afterwards is immutable
    anyway: the candidate, the score, and the metric are values assigned once.
    """

    candidate: object
    parent: Optional["CandidateNode"] = None
    children: list["CandidateNode"] = field(default_factory=list)
    score: Optional[object] = None
    metric: Optional[MetricValue] = None
    visits: int = 0
    total_reward: float = 0.0
    depth: int = 0
    exhausted: bool = False

    def uct_value(
        self,
        exploration_constant: float = DEFAULT_EXPLORATION_CONSTANT,
    ) -> float:
        """UCT1, matching the arithmetic already used in ``mcts_node``.

        An unvisited node returns infinity so that anything measured once
        outranks everything measured never; without it a search could settle
        on its first lucky child and never look at a sibling.
        """
        if self.visits == 0:
            return float("inf")
        parent_visits = self.parent.visits if self.parent else 0
        exploitation = self.total_reward / self.visits
        exploration = exploration_constant * (
            math.log(parent_visits + 1) / (self.visits + 1e-8)
        ) ** 0.5
        return exploitation + exploration

    def update(self, reward: float) -> None:
        self.visits += 1
        self.total_reward += reward

    def digest(self) -> str:
        """Identify the candidate, not the search state.

        Two runs of the same search must produce equal digests in equal
        order, which they cannot do if visit counts are hashed in.
        """
        candidate_digest = getattr(self.candidate, "digest", None)
        if callable(candidate_digest):
            return str(candidate_digest())
        return _digest(repr(self.candidate))

    @property
    def disqualified(self) -> bool:
        return self.metric is None or self.metric.is_worst

    def path_to_root(self) -> tuple["CandidateNode", ...]:
        path: list[CandidateNode] = []
        node: Optional[CandidateNode] = self
        while node is not None:
            path.append(node)
            node = node.parent
        return tuple(path)


@dataclass(frozen=True)
class SearchReport:
    """What the search evaluated, in what order it would be preferred.

    Frozen, and it carries the baseline as a node rather than as a number:
    the comparison a reader will make is between two measured candidates, and
    a report that stated only an improvement percentage would be unfalsifiable
    from its own contents.
    """

    evaluated: int
    best: Optional[CandidateNode]
    baseline: Optional[CandidateNode]
    ranking: tuple[CandidateNode, ...]
    halted: str
    halt_detail: str = ""

    def improved_over_baseline(self) -> bool:
        """Strictly better than the measured no-op, or it did not improve.

        Equality is not improvement. A candidate that merely ties the
        identity adaptation has bought nothing and costs a component that
        someone has to maintain.
        """
        if self.best is None or self.baseline is None:
            return False
        if self.best is self.baseline:
            return False
        if self.best.metric is None or self.baseline.metric is None:
            return False
        return bool(self.best.metric > self.baseline.metric)

    def as_contract(self) -> dict[str, object]:
        return {
            "evaluated": self.evaluated,
            "halted": self.halted,
            "halt_detail": self.halt_detail,
            "baseline_digest": (
                self.baseline.digest() if self.baseline else None
            ),
            "baseline_score": (
                None
                if self.baseline is None or self.baseline.metric is None
                else self.baseline.metric.value
            ),
            "best_digest": self.best.digest() if self.best else None,
            "best_score": (
                None
                if self.best is None or self.best.metric is None
                else self.best.metric.value
            ),
            "improved_over_baseline": self.improved_over_baseline(),
            "ranking": [
                {
                    "candidate_digest": node.digest(),
                    "depth": node.depth,
                    "visits": node.visits,
                    "score": (
                        None if node.metric is None else node.metric.value
                    ),
                    "disqualified": node.disqualified,
                }
                for node in self.ranking
            ],
        }


class AdaptationSearch:
    """A seeded tree search over typed candidates with an injected evaluator.

    Holds no state a caller could inspect mid-run and writes nothing. One
    instance is one search; ``run`` may be called again to search the same
    space from a fresh tree with the same seed, which is what makes the
    determinism claim checkable.
    """

    def __init__(
        self,
        space,
        evaluator: CandidateEvaluator,
        *,
        exploration_constant: float = DEFAULT_EXPLORATION_CONSTANT,
        mutation_scale: float = DEFAULT_MUTATION_SCALE,
        branching: int = DEFAULT_BRANCHING,
        max_depth: int = DEFAULT_MAX_DEPTH,
        seed: int = 0,
    ) -> None:
        if branching < 1:
            raise ValueError(
                "branching must be at least 1; a search that cannot expand "
                "measures the identity adaptation and calls it a search"
            )
        if max_depth < 1:
            raise ValueError("max_depth must be at least 1")
        if mutation_scale <= 0.0:
            raise ValueError(
                "mutation_scale must be positive; a zero step re-measures "
                "the parent and reports the campaign's noise as a finding"
            )
        self._space = space
        self._evaluator = evaluator
        self._exploration_constant = exploration_constant
        self._mutation_scale = mutation_scale
        self._branching = branching
        self._max_depth = max_depth
        self._seed = seed

    def run(self, budget: int) -> SearchReport:
        """Evaluate at most ``budget`` candidates, root included."""
        if budget < 1:
            raise ValueError(
                "a search needs at least one evaluation to measure its own "
                "baseline"
            )

        generator = random.Random(self._seed)
        evaluated: list[CandidateNode] = []

        root = CandidateNode(candidate=self._space.identity(), depth=0)
        try:
            self._evaluate(root)
        except Exception as error:  # noqa: BLE001 - reported, never raised
            return SearchReport(
                evaluated=0,
                best=None,
                baseline=None,
                ranking=(),
                halted=HALTED_EVALUATOR_FAILED,
                halt_detail=(
                    "the baseline evaluation failed, so nothing in this "
                    f"search has a control to compare against: "
                    f"{type(error).__name__}: {error}"
                ),
            )
        evaluated.append(root)

        halted = HALTED_BUDGET_EXHAUSTED
        halt_detail = f"spent the full budget of {budget} evaluations"

        while len(evaluated) < budget:
            node = self._select(root)
            if node is None:
                halted = HALTED_SPACE_EXHAUSTED
                halt_detail = (
                    "every branch is exhausted or at max depth "
                    f"{self._max_depth}, so no untried candidate remains "
                    f"after {len(evaluated)} evaluations"
                )
                break

            child = CandidateNode(
                candidate=self._space.mutate(
                    node.candidate, generator, self._mutation_scale
                ),
                parent=node,
                depth=node.depth + 1,
            )
            node.children.append(child)

            try:
                self._evaluate(child)
            except Exception as error:  # noqa: BLE001 - reported, never raised
                node.children.remove(child)
                halted = HALTED_EVALUATOR_FAILED
                halt_detail = (
                    f"evaluation {len(evaluated) + 1} raised "
                    f"{type(error).__name__}: {error}; the "
                    f"{len(evaluated)} evaluations already paid for are "
                    "reported below"
                )
                break

            evaluated.append(child)
            self._mark_exhaustion(child)

        ranking = self._rank(evaluated)
        best = ranking[0] if ranking and not ranking[0].disqualified else None
        if best is None and not root.disqualified:
            best = root
        return SearchReport(
            evaluated=len(evaluated),
            best=best,
            baseline=root,
            ranking=ranking,
            halted=halted,
            halt_detail=halt_detail,
        )

    def _evaluate(self, node: CandidateNode) -> None:
        """Score one node and backpropagate, in that order.

        The reward is derived from the scalar score rather than from a
        pass/fail signal, so exploitation follows measured robustness. A
        disqualified candidate receives the minimum reward, which pushes the
        search away from its whole branch instead of merely away from it.
        """
        score = self._evaluator.evaluate(node.candidate)
        metric = _metric_of(score)
        node.score = score
        node.metric = metric
        if _is_disqualified(score, metric):
            node.metric = WorstMetricValue(maximize=metric.maximize)
            # The root is exempt for the reason ``_expandable`` states: a
            # disqualified identity is the premise of the investigation, not a
            # barren branch. Latching exhaustion here would close the search
            # before ``_expandable`` was ever consulted.
            if node.parent is not None:
                node.exhausted = True
            reward = _MINIMUM_REWARD
        else:
            reward = _reward(metric)
        for ancestor in node.path_to_root():
            ancestor.update(reward)

    def _select(self, root: CandidateNode) -> Optional[CandidateNode]:
        """Walk to the best expandable node by UCT, or report none exists."""
        best: Optional[CandidateNode] = None
        best_value = -float("inf")
        for node in _walk(root):
            if not self._expandable(node):
                continue
            value = node.uct_value(self._exploration_constant)
            if value > best_value:
                best = node
                best_value = value
        return best

    def _expandable(self, node: CandidateNode) -> bool:
        """Whether this node may still be mutated.

        Disqualification closes a branch, with one deliberate exception: the
        root. The asymmetry is the difference between two claims that look
        alike and are not.

        A disqualified *child* is local evidence that its neighbourhood breaks
        an envelope, and spending the remaining budget mutating candidates
        already rejected buys nothing. Closing that branch is honest resource
        allocation.

        A disqualified *root* is the premise of the investigation. The root is
        the identity adaptation -- the system exactly as it is today -- and a
        complaint that reached this search says that system does not work. So
        the root failing is the expected case, not a barren region: treating it
        as one would abandon the search precisely when a genuine fault exists
        and search is the only thing that could find the fix. The first version
        of this method did exactly that, and reported ``space_exhausted`` after
        a single evaluation on every real interface fault.

        The root therefore stays expandable while it has branches left. Budget
        still bounds the search, and a space where nothing is admissible spends
        that budget and reports an empty ranking, which is the correct answer
        rather than an early one.
        """
        if node.exhausted:
            return False
        if node.depth >= self._max_depth:
            return False
        if node.disqualified and node.parent is not None:
            return False
        return len(node.children) < self._branching

    def _mark_exhaustion(self, node: CandidateNode) -> None:
        """Close a branch upward once nothing below it can be expanded.

        Not an optimisation. Without it the selection loop would keep
        returning a node whose whole subtree is disqualified and the search
        would spend its remaining budget mutating candidates it already
        rejected.
        """
        current: Optional[CandidateNode] = node.parent
        while current is not None:
            if self._expandable(current):
                return
            if any(self._expandable(child) for child in _walk(current)):
                return
            current.exhausted = True
            current = current.parent

    def _rank(
        self, evaluated: list[CandidateNode]
    ) -> tuple[CandidateNode, ...]:
        """Order by metric, disqualified last, stable within equal metrics.

        Stability is what makes the determinism claim observable: two runs
        with the same seed produce the same evaluation order, so equal-scoring
        candidates must not be reordered by the sort itself.
        """
        indexed = list(enumerate(evaluated))

        def sort_key(item: tuple[int, CandidateNode]):
            index, node = item
            if node.disqualified:
                return (1, 0.0, index)
            assert node.metric is not None
            value = float(node.metric.value or 0.0)
            # Negated for maximisation so that "better" is always "earlier",
            # which keeps one comparison direction in the sort regardless of
            # the metric's own direction.
            ordered = -value if node.metric.maximize else value
            return (0, ordered, index)

        return tuple(node for _, node in sorted(indexed, key=sort_key))


def _reward(metric: MetricValue) -> float:
    """Squash a measured metric into [0, 1] for UCT exploitation.

    UCT's exploration term is calibrated for bounded rewards, so an unbounded
    score would make the constant meaningless -- one large score would pin
    exploitation and the search would stop exploring. A logistic squash keeps
    the ordering of the metric intact while bounding it, and it never
    saturates to exactly the minimum, which is reserved for disqualification.
    """
    if metric.value is None:
        return _MINIMUM_REWARD
    value = float(metric.value)
    if not metric.maximize:
        value = -value
    # Computed in the branch that does not overflow. A campaign is free to
    # report an unbounded score, and the naive logistic raises on a large
    # negative one -- which would turn "this candidate was terrible" into a
    # crashed search that discards every evaluation already paid for.
    if value >= 0.0:
        squashed = 1.0 / (1.0 + math.exp(-value))
    else:
        weight = math.exp(value)
        squashed = weight / (1.0 + weight)
    # Held strictly above the disqualification reward: a merely poor
    # candidate must still rank above one that violated safety.
    lowest_valid = 1e-6
    return max(lowest_valid, min(_MAXIMUM_REWARD, squashed))


def _walk(node: CandidateNode):
    yield node
    for child in node.children:
        yield from _walk(child)
