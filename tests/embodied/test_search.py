"""What a search over typed candidates may conclude, and what it must not do.

Every fake here is deliberate: the search under test must not be able to tell
that an evaluation would normally be a simulated campaign, so the evaluator is
a plain object and the candidate is a number with a digest.
"""

from __future__ import annotations

import ast
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from vegapunk.embodied.search import (
    DEFAULT_EXPLORATION_CONSTANT,
    HALTED_EVALUATOR_FAILED,
    HALTED_SPACE_EXHAUSTED,
    AdaptationSearch,
    CandidateNode,
    SearchReport,
)
from vegapunk.mcts_node import MetricValue, WorstMetricValue


@dataclass(frozen=True)
class FakeCandidate:
    """Stands in for an AdaptationCandidate: a typed value with a digest."""

    gain: float

    def digest(self) -> str:
        return f"cand-{self.gain:+.6f}"


@dataclass(frozen=True)
class FakeScore:
    """Stands in for CandidateScore, including its own disqualification."""

    score: float
    safety_violations: int = 0
    aborted: bool = False
    candidate_digest: str = ""

    def as_metric(self) -> MetricValue:
        if self.safety_violations or self.aborted:
            return WorstMetricValue(maximize=True)
        return MetricValue(value=self.score, maximize=True)


class FakeSpace:
    """Stands in for AdaptationSpace over a single scalar parameter."""

    def __init__(self) -> None:
        self.mutations = 0

    def identity(self) -> FakeCandidate:
        return FakeCandidate(gain=0.0)

    def mutate(
        self, parent: FakeCandidate, generator, scale: float
    ) -> FakeCandidate:
        self.mutations += 1
        step = generator.uniform(-scale, scale)
        return FakeCandidate(gain=parent.gain + step)


class CountingEvaluator:
    """Records every candidate it was asked about, in order."""

    def __init__(self, scorer=None) -> None:
        self.calls: list[FakeCandidate] = []
        self._scorer = scorer or (lambda candidate: candidate.gain)

    @property
    def count(self) -> int:
        return len(self.calls)

    def digests(self) -> list[str]:
        return [candidate.digest() for candidate in self.calls]

    def evaluate(self, candidate: FakeCandidate) -> FakeScore:
        self.calls.append(candidate)
        result = self._scorer(candidate)
        if isinstance(result, FakeScore):
            return result
        return FakeScore(
            score=float(result), candidate_digest=candidate.digest()
        )


class ViolatingEvaluator(CountingEvaluator):
    """Every candidate but the identity records a safety violation."""

    def evaluate(self, candidate: FakeCandidate) -> FakeScore:
        self.calls.append(candidate)
        if candidate.gain == 0.0:
            return FakeScore(score=0.5, candidate_digest=candidate.digest())
        return FakeScore(
            score=9.9,  # a high score that must not rescue a violation
            safety_violations=1,
            candidate_digest=candidate.digest(),
        )


class ExplodingEvaluator(CountingEvaluator):
    """Fails on the nth evaluation, the way a crashed campaign would."""

    def __init__(self, fail_on: int) -> None:
        super().__init__()
        self._fail_on = fail_on

    def evaluate(self, candidate: FakeCandidate) -> FakeScore:
        if self.count + 1 == self._fail_on:
            raise RuntimeError("the simulator died mid-campaign")
        return super().evaluate(candidate)


def _search(evaluator, **overrides) -> AdaptationSearch:
    options: dict[str, object] = {
        "exploration_constant": DEFAULT_EXPLORATION_CONSTANT,
        "mutation_scale": 0.25,
        "branching": 3,
        "max_depth": 4,
        "seed": 7,
    }
    options.update(overrides)
    return AdaptationSearch(FakeSpace(), evaluator, **options)


class BaselineIsMeasuredFirstTests(unittest.TestCase):
    """An improvement measured against no control is a claim about nothing."""

    def test_the_root_is_the_identity_adaptation(self) -> None:
        evaluator = CountingEvaluator()
        report = _search(evaluator).run(budget=5)
        self.assertIsNotNone(report.baseline)
        assert report.baseline is not None
        self.assertEqual(report.baseline.candidate, FakeCandidate(gain=0.0))
        self.assertEqual(report.baseline.depth, 0)

    def test_the_identity_is_evaluated_before_any_mutation(self) -> None:
        evaluator = CountingEvaluator()
        _search(evaluator).run(budget=4)
        self.assertEqual(evaluator.calls[0], FakeCandidate(gain=0.0))

    def test_a_single_evaluation_budget_buys_only_the_control(self) -> None:
        evaluator = CountingEvaluator()
        space = FakeSpace()
        report = AdaptationSearch(space, evaluator, seed=1).run(budget=1)
        self.assertEqual(evaluator.count, 1)
        self.assertEqual(space.mutations, 0)
        self.assertEqual(report.evaluated, 1)
        self.assertIs(report.best, report.baseline)

    def test_improvement_is_measured_against_the_control(self) -> None:
        # Every mutation scores worse than the identity, so the honest
        # answer is that the search found nothing.
        evaluator = CountingEvaluator(
            scorer=lambda candidate: 1.0 if candidate.gain == 0.0 else -1.0
        )
        report = _search(evaluator).run(budget=6)
        self.assertIs(report.best, report.baseline)
        self.assertFalse(report.improved_over_baseline())

    def test_a_strictly_better_candidate_is_an_improvement(self) -> None:
        evaluator = CountingEvaluator(
            scorer=lambda candidate: abs(candidate.gain)
        )
        report = _search(evaluator).run(budget=6)
        self.assertTrue(report.improved_over_baseline())
        assert report.best is not None
        self.assertIsNot(report.best, report.baseline)

    def test_tying_the_control_is_not_an_improvement(self) -> None:
        evaluator = CountingEvaluator(scorer=lambda candidate: 0.5)
        report = _search(evaluator).run(budget=6)
        self.assertFalse(report.improved_over_baseline())


class DisqualifiedCandidatesAreNeverExpandedTests(unittest.TestCase):
    """A violation rules out a region, so its neighbourhood is not searched."""

    def test_no_child_is_generated_from_a_safety_violation(self) -> None:
        evaluator = ViolatingEvaluator()
        search = _search(evaluator)
        report = search.run(budget=12)
        for node in report.ranking:
            score = node.score
            assert isinstance(score, FakeScore)
            if score.safety_violations:
                self.assertEqual(
                    node.children,
                    [],
                    f"{node.digest()} violated safety and was still expanded",
                )

    def test_a_violating_branch_exhausts_the_space(self) -> None:
        evaluator = ViolatingEvaluator()
        report = _search(evaluator).run(budget=50)
        # The root may hold `branching` children; each is disqualified on
        # arrival, so nothing deeper can ever be proposed.
        self.assertEqual(report.evaluated, 4)
        self.assertEqual(report.halted, HALTED_SPACE_EXHAUSTED)

    def test_a_high_score_does_not_rescue_a_violation(self) -> None:
        evaluator = ViolatingEvaluator()
        report = _search(evaluator).run(budget=8)
        self.assertIs(report.best, report.baseline)
        self.assertFalse(report.improved_over_baseline())

    def test_an_aborted_candidate_is_disqualified_too(self) -> None:
        evaluator = CountingEvaluator(
            scorer=lambda candidate: FakeScore(score=0.9, aborted=True)
            if candidate.gain != 0.0
            else FakeScore(score=0.1)
        )
        report = _search(evaluator).run(budget=10)
        for node in report.ranking:
            if node is report.baseline:
                continue
            self.assertTrue(node.disqualified)
            self.assertEqual(node.children, [])

    def test_a_disqualified_node_is_marked_exhausted(self) -> None:
        evaluator = ViolatingEvaluator()
        report = _search(evaluator).run(budget=6)
        violating = [
            node
            for node in report.ranking
            if node.disqualified
        ]
        self.assertTrue(violating)
        for node in violating:
            self.assertTrue(node.exhausted)


class RewardFollowsMeasuredRobustnessTests(unittest.TestCase):
    """Exploitation must track the scalar score, not a crash signal."""

    def test_a_better_score_accumulates_a_larger_reward(self) -> None:
        weak = CandidateNode(candidate=FakeCandidate(0.1))
        strong = CandidateNode(candidate=FakeCandidate(0.2))
        AdaptationSearch(
            FakeSpace(), CountingEvaluator(scorer=lambda c: 0.0)
        )  # construction must not evaluate anything
        weak_search = _search(CountingEvaluator(scorer=lambda c: -2.0))
        strong_search = _search(CountingEvaluator(scorer=lambda c: 2.0))
        weak_search._evaluate(weak)
        strong_search._evaluate(strong)
        self.assertGreater(strong.total_reward, weak.total_reward)

    def test_a_disqualified_candidate_takes_the_minimum_reward(self) -> None:
        node = CandidateNode(candidate=FakeCandidate(0.3))
        search = _search(
            CountingEvaluator(
                scorer=lambda c: FakeScore(score=99.0, safety_violations=2)
            )
        )
        search._evaluate(node)
        self.assertEqual(node.total_reward, 0.0)
        self.assertTrue(node.metric is not None and node.metric.is_worst)

    def test_reward_is_bounded_so_the_uct_constant_stays_meaningful(
        self,
    ) -> None:
        for value in (-1e6, -1.0, 0.0, 1.0, 1e6):
            with self.subTest(value=value):
                node = CandidateNode(candidate=FakeCandidate(0.0))
                search = _search(CountingEvaluator(scorer=lambda c: value))
                search._evaluate(node)
                self.assertGreaterEqual(node.total_reward, 0.0)
                self.assertLessEqual(node.total_reward, 1.0)

    def test_a_poor_candidate_still_outranks_a_violation(self) -> None:
        poor = CandidateNode(candidate=FakeCandidate(0.1))
        unsafe = CandidateNode(candidate=FakeCandidate(0.2))
        _search(CountingEvaluator(scorer=lambda c: -1e6))._evaluate(poor)
        _search(
            CountingEvaluator(
                scorer=lambda c: FakeScore(score=1e6, safety_violations=1)
            )
        )._evaluate(unsafe)
        self.assertGreater(poor.total_reward, unsafe.total_reward)

    def test_an_unvisited_node_is_preferred_over_any_measured_one(
        self,
    ) -> None:
        measured = CandidateNode(candidate=FakeCandidate(0.0), visits=3,
                                 total_reward=3.0)
        unvisited = CandidateNode(candidate=FakeCandidate(0.1))
        self.assertEqual(unvisited.uct_value(), float("inf"))
        self.assertLess(measured.uct_value(), unvisited.uct_value())


class BudgetIsAHardCapTests(unittest.TestCase):
    """Evaluation is the expensive thing, so it is what gets counted."""

    def test_evaluate_is_called_at_most_budget_times(self) -> None:
        for budget in (1, 2, 3, 5, 9):
            with self.subTest(budget=budget):
                evaluator = CountingEvaluator()
                report = _search(evaluator).run(budget=budget)
                self.assertLessEqual(evaluator.count, budget)
                self.assertEqual(report.evaluated, evaluator.count)

    def test_the_root_is_counted_against_the_budget(self) -> None:
        evaluator = CountingEvaluator()
        _search(evaluator).run(budget=3)
        self.assertEqual(evaluator.count, 3)
        self.assertEqual(evaluator.calls[0], FakeCandidate(gain=0.0))

    def test_a_zero_budget_is_refused_rather_than_returning_nothing(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            _search(CountingEvaluator()).run(budget=0)


class DeterminismTests(unittest.TestCase):
    """A finding that cannot be replayed cannot be re-examined."""

    def test_two_runs_with_one_seed_visit_identical_candidates(self) -> None:
        first = CountingEvaluator()
        second = CountingEvaluator()
        AdaptationSearch(FakeSpace(), first, seed=11).run(budget=9)
        AdaptationSearch(FakeSpace(), second, seed=11).run(budget=9)
        self.assertEqual(first.digests(), second.digests())

    def test_the_reported_ranking_is_identical_across_runs(self) -> None:
        first = AdaptationSearch(
            FakeSpace(), CountingEvaluator(), seed=11
        ).run(budget=9)
        second = AdaptationSearch(
            FakeSpace(), CountingEvaluator(), seed=11
        ).run(budget=9)
        self.assertEqual(
            [node.digest() for node in first.ranking],
            [node.digest() for node in second.ranking],
        )

    def test_a_different_seed_explores_different_candidates(self) -> None:
        first = CountingEvaluator()
        second = CountingEvaluator()
        AdaptationSearch(FakeSpace(), first, seed=11).run(budget=9)
        AdaptationSearch(FakeSpace(), second, seed=12).run(budget=9)
        self.assertNotEqual(first.digests(), second.digests())


class EvaluatorFailureIsNotACandidateVerdictTests(unittest.TestCase):
    """A crashed campaign says nothing about the candidate it crashed on."""

    def test_a_failure_halts_cleanly_and_keeps_what_was_paid_for(
        self,
    ) -> None:
        evaluator = ExplodingEvaluator(fail_on=4)
        report = _search(evaluator).run(budget=10)
        self.assertEqual(report.halted, HALTED_EVALUATOR_FAILED)
        self.assertEqual(report.evaluated, 3)
        self.assertEqual(len(report.ranking), 3)

    def test_the_failure_is_named_in_the_halt_detail(self) -> None:
        report = _search(ExplodingEvaluator(fail_on=2)).run(budget=10)
        self.assertIn("RuntimeError", report.halt_detail)
        self.assertIn("simulator died", report.halt_detail)

    def test_the_baseline_survives_a_later_failure(self) -> None:
        report = _search(ExplodingEvaluator(fail_on=3)).run(budget=10)
        self.assertIsNotNone(report.baseline)
        assert report.baseline is not None
        self.assertEqual(report.baseline.candidate, FakeCandidate(gain=0.0))

    def test_a_failed_candidate_is_not_left_in_the_tree(self) -> None:
        report = _search(ExplodingEvaluator(fail_on=3)).run(budget=10)
        for node in report.ranking:
            self.assertIsNotNone(node.metric)

    def test_a_failed_baseline_reports_no_best_and_no_control(self) -> None:
        report = _search(ExplodingEvaluator(fail_on=1)).run(budget=10)
        self.assertEqual(report.halted, HALTED_EVALUATOR_FAILED)
        self.assertEqual(report.evaluated, 0)
        self.assertIsNone(report.best)
        self.assertIsNone(report.baseline)
        self.assertFalse(report.improved_over_baseline())


class RankingTests(unittest.TestCase):
    """Order by measured metric, with everything ruled out at the end."""

    def test_better_metrics_come_first(self) -> None:
        evaluator = CountingEvaluator(
            scorer=lambda candidate: abs(candidate.gain)
        )
        report = _search(evaluator).run(budget=8)
        values = [
            node.metric.value
            for node in report.ranking
            if node.metric is not None and not node.metric.is_worst
        ]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_disqualified_candidates_come_last_whatever_their_score(
        self,
    ) -> None:
        # The identity scores poorly and every mutation scores far better
        # while violating safety. Sign of the mutation step is left out of
        # it deliberately: a test that needed the generator to land on a
        # particular side would be asserting the seed, not the ordering.
        evaluator = ViolatingEvaluator()
        report = _search(evaluator).run(budget=10)
        flags = [node.disqualified for node in report.ranking]
        self.assertEqual(flags, sorted(flags))
        self.assertTrue(any(flags), "expected some disqualified candidates")
        self.assertFalse(
            report.ranking[0].disqualified,
            "a 9.9 with a violation outranked a clean 0.5",
        )

    def test_equal_metrics_keep_their_evaluation_order(self) -> None:
        evaluator = CountingEvaluator(scorer=lambda candidate: 0.5)
        report = _search(evaluator).run(budget=7)
        self.assertEqual(
            [node.digest() for node in report.ranking],
            evaluator.digests(),
        )

    def test_the_best_node_heads_the_ranking(self) -> None:
        evaluator = CountingEvaluator(
            scorer=lambda candidate: abs(candidate.gain)
        )
        report = _search(evaluator).run(budget=8)
        self.assertIs(report.best, report.ranking[0])

    def test_the_contract_reports_the_control_beside_the_winner(self) -> None:
        evaluator = CountingEvaluator(
            scorer=lambda candidate: abs(candidate.gain)
        )
        report = _search(evaluator).run(budget=6)
        contract = report.as_contract()
        assert report.baseline is not None and report.best is not None
        self.assertEqual(
            contract["baseline_digest"], report.baseline.digest()
        )
        self.assertEqual(contract["best_digest"], report.best.digest())
        self.assertTrue(contract["improved_over_baseline"])
        self.assertEqual(contract["evaluated"], 6)
        self.assertEqual(len(contract["ranking"]), 6)


class SearchDecidesNothingElseTests(unittest.TestCase):
    """The module may not touch disk, a model, or a thread."""

    _FORBIDDEN = {
        "os",
        "os.path",
        "pathlib",
        "shutil",
        "tempfile",
        "threading",
        "asyncio",
        "concurrent",
        "concurrent.futures",
        "subprocess",
        "socket",
        "requests",
        "httpx",
        "openai",
    }

    def _imports(self) -> set[str]:
        source = Path("vegapunk/embodied/search.py").read_text()
        tree = ast.parse(source)
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        return names

    def test_the_module_imports_nothing_that_could_do_io(self) -> None:
        offending = self._imports() & self._FORBIDDEN
        self.assertEqual(offending, set())

    def test_the_module_does_not_reach_into_the_harness_governance(
        self,
    ) -> None:
        # It must not be able to read admission evidence or count successes;
        # those judgements belong to the ladder and the trajectory ledger.
        governance = {
            "vegapunk.embodied.admission",
            "vegapunk.embodied.trajectory",
            "vegapunk.embodied.safety",
            "vegapunk.embodied.campaign",
            "vegapunk.mas.models.unified_runtime",
            "vegapunk.prompt_library",
        }
        self.assertEqual(self._imports() & governance, set())

    def test_a_search_writes_no_file(self) -> None:
        before = set(Path("vegapunk/embodied").iterdir())
        _search(CountingEvaluator()).run(budget=6)
        self.assertEqual(set(Path("vegapunk/embodied").iterdir()), before)


class ConstructionRefusalsTests(unittest.TestCase):
    """A search configured to measure nothing is refused up front."""

    def test_branching_below_one_cannot_search(self) -> None:
        with self.assertRaises(ValueError):
            _search(CountingEvaluator(), branching=0)

    def test_zero_depth_cannot_search(self) -> None:
        with self.assertRaises(ValueError):
            _search(CountingEvaluator(), max_depth=0)

    def test_a_zero_mutation_step_only_remeasures_the_parent(self) -> None:
        with self.assertRaises(ValueError):
            _search(CountingEvaluator(), mutation_scale=0.0)


class ReportIsAValueTests(unittest.TestCase):
    """A report is the record of what was asked, so it does not move."""

    def test_the_report_is_frozen(self) -> None:
        report = _search(CountingEvaluator()).run(budget=3)
        with self.assertRaises(Exception):
            report.evaluated = 99  # type: ignore[misc]

    def test_an_empty_report_answers_the_improvement_question_safely(
        self,
    ) -> None:
        report = SearchReport(
            evaluated=0,
            best=None,
            baseline=None,
            ranking=(),
            halted=HALTED_EVALUATOR_FAILED,
        )
        self.assertFalse(report.improved_over_baseline())


if __name__ == "__main__":
    unittest.main()
