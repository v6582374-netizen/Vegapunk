from __future__ import annotations

import unittest
from datetime import datetime, timezone

from vegapunk.operation.campaign import (
    EXECUTION_COMPLETED,
    EXECUTION_HELD,
    STOP_AWAITING_HUMAN,
    STOP_CIRCUIT_BREAKER,
    STOP_COMPLETED,
    BatchPlan,
    BenchConfiguration,
    Campaign,
    Condition,
)
from vegapunk.operation.design import TableBatchDesigner
from vegapunk.operation.loop import (
    CircuitBreaker,
    EpisodeRun,
    ExperimentLoop,
)
from vegapunk.operation.predict import CalibrationPolicy, TabularPredictiveNode
from vegapunk.operation.trace import (
    OUTCOME_FAILED,
    OUTCOME_SUCCEEDED,
    REQUIRED_TRACE,
    FACT_DEFINITE,
    ResetVerdict,
    TraceFact,
)

_AT = datetime(2026, 8, 19, tzinfo=timezone.utc)
_NOW = 1_700_000_000_000_000_000

_POSE_A = Condition.of(cup_pose="a")
_POSE_B = Condition.of(cup_pose="b")


def _full_trace() -> tuple[TraceFact, ...]:
    return tuple(
        TraceFact(
            predicate=predicate,
            verdict=FACT_DEFINITE,
            channel="bench_camera",
            observed_at_ns=_NOW + index,
            fresh=True,
        )
        for index, predicate in enumerate(REQUIRED_TRACE)
    )


class _Executor:
    """Scripted per-condition runs; records what it was asked to do."""

    def __init__(self, script) -> None:
        self._script = script
        self.calls: list[Condition] = []
        self.sealed_at_execution: list[bool] = []
        self.campaign: Campaign | None = None
        self.plan_ids: list[str] = []
        self._count = 0

    def execute(self, condition: Condition, plan: BatchPlan) -> EpisodeRun:
        self.calls.append(condition)
        self.plan_ids.append(plan.plan_id)
        if self.campaign is not None:
            self.sealed_at_execution.append(
                self.campaign.plan_sealed(plan.plan_id)
            )
        self._count += 1
        outcome = self._script(condition)
        if isinstance(outcome, Exception):
            raise outcome
        execution, trace = outcome
        return EpisodeRun(
            episode_id=f"ep-{self._count}",
            execution=execution,
            trace=trace,
            witness_identity="bench_camera",
        )


class _ResetWitness:
    def __init__(self, confirmed: bool = True) -> None:
        self.confirmed = confirmed
        self.verifications = 0

    @property
    def identity(self) -> str:
        return "bench_camera_reset"

    def verify(self) -> ResetVerdict:
        self.verifications += 1
        return ResetVerdict(
            confirmed=self.confirmed,
            channel=self.identity,
            observed_at_ns=_NOW,
            detail="" if self.confirmed else "cup pose unknown",
        )


class _CountingNode(TabularPredictiveNode):
    def __init__(self) -> None:
        super().__init__()
        self.forecasts = 0

    def forecast(self, condition: Condition):
        self.forecasts += 1
        return super().forecast(condition)


def _campaign() -> tuple[Campaign, str]:
    campaign = Campaign(clock=lambda: _AT)
    generation = campaign.open_founding_generation(
        BenchConfiguration(
            fixture="bare bench",
            object_identity="red cup",
            witness_pose_digest="pose-1",
            lighting_protocol="overhead",
            policy_identity="policy-v1",
            invocation_protocol="chunk8",
        ),
        opened_by="Wei",
    )
    return campaign, generation.generation_id


def _plan(
    plan_id: str,
    generation_id: str,
    conditions: tuple[Condition, ...],
    *,
    predicted: tuple[Condition, ...] = (),
) -> BatchPlan:
    return BatchPlan(
        plan_id=plan_id,
        generation_id=generation_id,
        objective="map the envelope",
        real_conditions=conditions,
        predicted_conditions=predicted,
        real_anchor_count=1,
        predictive_node_version="tabular-1",
        confidence_threshold=0.7,
        selection_rationale="test",
        expected_outcome="the loop is under test, not the policy",
        created_at=_AT,
    )


def _loop(campaign: Campaign, executor, reset=None, node=None, breaker=None):
    return ExperimentLoop(
        campaign=campaign,
        executor=executor,
        reset_witness=reset or _ResetWitness(),
        node=node or _CountingNode(),
        calibration_policy=CalibrationPolicy(min_scored=4, min_accuracy=0.75),
        breaker=breaker or CircuitBreaker(),
        clock=lambda: _AT,
    )


class WholeBatchTest(unittest.TestCase):
    def test_an_all_failure_batch_is_a_passing_loop(self) -> None:
        # The first milestone: every episode fails (the policy stood still),
        # yet every verdict, reset and record is present and sealed.
        campaign, generation_id = _campaign()
        executor = _Executor(lambda c: (EXECUTION_COMPLETED, ()))
        executor.campaign = campaign
        node = _CountingNode()
        loop = _loop(campaign, executor, node=node)

        result = loop.run_batch(_plan("batch-1", generation_id, (_POSE_A, _POSE_B)))

        self.assertEqual(result.stop, STOP_COMPLETED)
        self.assertEqual(len(result.episodes), 2)
        self.assertTrue(
            all(e.outcome == OUTCOME_FAILED for e in result.episodes)
        )
        self.assertTrue(result.anchored)
        self.assertIs(campaign.result_for("batch-1"), result)
        # The plan was sealed before any episode ran.
        self.assertEqual(executor.sealed_at_execution, [True, True])
        # The node was invoked and scored.
        self.assertEqual(node.forecasts, 2)
        self.assertEqual(len(campaign.predictions_for("batch-1")), 2)
        self.assertEqual(result.calibration.scored, 2)

    def test_a_witnessed_full_trace_is_a_success(self) -> None:
        campaign, generation_id = _campaign()
        executor = _Executor(lambda c: (EXECUTION_COMPLETED, _full_trace()))
        loop = _loop(campaign, executor)

        result = loop.run_batch(_plan("batch-1", generation_id, (_POSE_A,)))
        self.assertEqual(result.episodes[0].outcome, OUTCOME_SUCCEEDED)
        self.assertEqual(result.success_count, 1)

    def test_a_held_episode_is_never_a_completed_success(self) -> None:
        campaign, generation_id = _campaign()
        executor = _Executor(lambda c: (EXECUTION_HELD, _full_trace()))
        loop = _loop(
            campaign, executor, breaker=CircuitBreaker(max_consecutive_holds=5)
        )

        result = loop.run_batch(_plan("batch-1", generation_id, (_POSE_A,)))
        episode = result.episodes[0]
        self.assertEqual(episode.execution, EXECUTION_HELD)
        self.assertNotEqual(episode.outcome, OUTCOME_SUCCEEDED)
        self.assertFalse(episode.success)

    def test_a_faulting_executor_becomes_a_recorded_fault(self) -> None:
        campaign, generation_id = _campaign()
        executor = _Executor(lambda c: RuntimeError("transport died"))
        loop = _loop(
            campaign, executor, breaker=CircuitBreaker(max_consecutive_holds=5)
        )

        result = loop.run_batch(_plan("batch-1", generation_id, (_POSE_A,)))
        self.assertEqual(result.episodes[0].execution, "fault")
        self.assertIn("transport died", result.episodes[0].outcome_detail)


class ResetRuleTest(unittest.TestCase):
    def test_an_unconfirmed_reset_stops_the_batch_awaiting_a_human(self) -> None:
        campaign, generation_id = _campaign()
        executor = _Executor(lambda c: (EXECUTION_COMPLETED, _full_trace()))
        loop = _loop(campaign, executor, reset=_ResetWitness(confirmed=False))

        result = loop.run_batch(_plan("batch-1", generation_id, (_POSE_A, _POSE_B)))

        self.assertEqual(result.stop, STOP_AWAITING_HUMAN)
        self.assertEqual(result.episodes, ())
        self.assertFalse(result.anchored)
        self.assertEqual(executor.calls, [])  # nothing ran from an unknown state


class CircuitBreakerTest(unittest.TestCase):
    def test_consecutive_holds_trip_the_breaker(self) -> None:
        campaign, generation_id = _campaign()
        executor = _Executor(lambda c: (EXECUTION_HELD, ()))
        loop = _loop(
            campaign, executor, breaker=CircuitBreaker(max_consecutive_holds=2)
        )

        result = loop.run_batch(
            _plan("batch-1", generation_id, (_POSE_A, _POSE_B, _POSE_A, _POSE_B))
        )
        self.assertEqual(result.stop, STOP_CIRCUIT_BREAKER)
        self.assertEqual(len(result.episodes), 2)
        self.assertIn("hold", result.stop_detail)

    def test_repeated_equivalent_failures_trip_the_breaker(self) -> None:
        campaign, generation_id = _campaign()
        executor = _Executor(lambda c: (EXECUTION_COMPLETED, ()))
        loop = _loop(
            campaign,
            executor,
            breaker=CircuitBreaker(
                max_consecutive_holds=99, max_equivalent_failures=2
            ),
        )

        result = loop.run_batch(
            _plan("batch-1", generation_id, (_POSE_A, _POSE_A, _POSE_A))
        )
        self.assertEqual(result.stop, STOP_CIRCUIT_BREAKER)
        self.assertEqual(len(result.episodes), 2)


class PredictionAuthorityTest(unittest.TestCase):
    def test_an_uncalibrated_node_cannot_buy_imagined_episodes(self) -> None:
        campaign, generation_id = _campaign()
        executor = _Executor(lambda c: (EXECUTION_COMPLETED, ()))
        loop = _loop(campaign, executor)

        with self.assertRaises(ValueError):
            loop.run_batch(
                _plan(
                    "batch-1",
                    generation_id,
                    (_POSE_A,),
                    predicted=(_POSE_B,),
                )
            )

    def test_predictions_never_become_episode_evidence(self) -> None:
        campaign, generation_id = _campaign()
        # Earn calibration first: two batches of scored real anchors.
        executor = _Executor(lambda c: (EXECUTION_COMPLETED, ()))
        node = _CountingNode()
        loop = _loop(campaign, executor, node=node)
        for index, plan_id in enumerate(("batch-1", "batch-2")):
            for condition in (_POSE_A, _POSE_B):
                node.record(condition, OUTCOME_FAILED)
            loop.run_batch(
                _plan(plan_id, generation_id, (_POSE_A, _POSE_B))
            )
        self.assertTrue(
            CalibrationPolicy(min_scored=4, min_accuracy=0.75)
            .may_reduce_real_budget(campaign.calibration("tabular-1"))[0]
        )

        result = loop.run_batch(
            _plan(
                "batch-3", generation_id, (_POSE_A,), predicted=(_POSE_B,)
            )
        )
        self.assertEqual(len(result.episodes), 1)  # only the real anchor
        self.assertEqual(result.episodes[0].condition, _POSE_A)
        self.assertEqual(len(result.predictions), 2)  # both were staked


class CampaignRunTest(unittest.TestCase):
    def test_the_next_plan_changes_on_evidence_and_orders_reach_the_ledger(
        self,
    ) -> None:
        campaign, _ = _campaign()
        executor = _Executor(
            lambda c: (
                EXECUTION_COMPLETED,
                _full_trace() if c == _POSE_B else (),
            )
        )
        designer = TableBatchDesigner(
            table=(_POSE_A, _POSE_B),
            objective="map the envelope",
            episodes_per_batch=4,
            calibration_policy=CalibrationPolicy(min_scored=99),
            repeated_failure_threshold=2,
            clock=lambda: _AT,
        )
        loop = _loop(
            campaign,
            executor,
            breaker=CircuitBreaker(max_consecutive_holds=9, max_equivalent_failures=9),
        )

        results = loop.run_campaign(
            designer, plan_ids=("batch-1", "batch-2", "batch-3")
        )

        self.assertEqual(len(results), 3)
        plans = campaign.plans()
        self.assertNotEqual(
            plans[0].real_conditions, plans[1].real_conditions
        )
        spent_on_a = sum(
            1 for c in plans[1].real_conditions if c == _POSE_A
        )
        spent_on_b = sum(
            1 for c in plans[1].real_conditions if c == _POSE_B
        )
        self.assertGreater(spent_on_a, spent_on_b)
        # Repeated failures at pose a eventually reach the ledger as an order.
        self.assertTrue(campaign.work_orders())
        self.assertTrue(
            all(campaign.result_for(p.plan_id) for p in plans)
        )


if __name__ == "__main__":
    unittest.main()
