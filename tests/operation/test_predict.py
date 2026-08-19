from __future__ import annotations

import unittest

from vegapunk.operation.campaign import (
    CalibrationScore,
    Condition,
    EpisodeEvidence,
    Prediction,
)
from vegapunk.operation.predict import (
    CalibrationPolicy,
    Forecast,
    TabularPredictiveNode,
    score_predictions,
)
from vegapunk.operation.trace import (
    OUTCOME_FAILED,
    OUTCOME_INDETERMINATE,
    OUTCOME_SUCCEEDED,
)


def _condition(pose: str = "a4") -> Condition:
    return Condition.of(cup_pose=pose)


def _evidence(
    condition: Condition, outcome: str, episode_id: str = "ep-1"
) -> EpisodeEvidence:
    return EpisodeEvidence(
        episode_id=episode_id,
        plan_id="batch-1",
        generation_id="gen-1",
        condition=condition,
        execution="completed" if outcome == OUTCOME_SUCCEEDED else "completed",
        outcome=outcome,
        outcome_detail="",
        reset_confirmed=True,
        reset_witnessed=True,
        witness_identity="bench_camera",
    )


def _prediction(condition: Condition, outcome: str) -> Prediction:
    return Prediction(
        plan_id="batch-1",
        condition=condition,
        outcome=outcome,
        confidence=0.9,
        node_version="tabular-1",
    )


class ForecastTest(unittest.TestCase):
    def test_a_forecast_states_its_uncertainty(self) -> None:
        forecast = Forecast(outcome=OUTCOME_SUCCEEDED, confidence=0.75)
        self.assertAlmostEqual(forecast.uncertainty, 0.25)

    def test_a_forecast_confidence_is_bounded(self) -> None:
        with self.assertRaises(ValueError):
            Forecast(outcome=OUTCOME_SUCCEEDED, confidence=1.5)


class TabularNodeTest(unittest.TestCase):
    def test_an_unseen_condition_is_an_honest_dont_know(self) -> None:
        node = TabularPredictiveNode()
        forecast = node.forecast(_condition("never-tried"))
        self.assertEqual(forecast.outcome, OUTCOME_INDETERMINATE)
        self.assertEqual(forecast.confidence, 0.0)

    def test_the_table_forecasts_the_majority_observed_outcome(self) -> None:
        node = TabularPredictiveNode()
        pose = _condition("a4")
        node.record(pose, OUTCOME_SUCCEEDED)
        node.record(pose, OUTCOME_SUCCEEDED)
        node.record(pose, OUTCOME_FAILED)

        forecast = node.forecast(pose)
        self.assertEqual(forecast.outcome, OUTCOME_SUCCEEDED)
        self.assertAlmostEqual(forecast.confidence, 2 / 3)
        self.assertGreater(forecast.uncertainty, 0.0)

    def test_the_node_cannot_adjudicate_or_publish(self) -> None:
        node = TabularPredictiveNode()
        for forbidden in ("adjudicate", "publish", "execute"):
            self.assertFalse(hasattr(node, forbidden))


class ScoringTest(unittest.TestCase):
    def test_predictions_are_scored_one_outcome_against_one_outcome(self) -> None:
        pose_a, pose_b = _condition("a"), _condition("b")
        predictions = (
            _prediction(pose_a, OUTCOME_SUCCEEDED),
            _prediction(pose_b, OUTCOME_FAILED),
        )
        evidence = (
            _evidence(pose_a, OUTCOME_SUCCEEDED, "ep-1"),
            _evidence(pose_b, OUTCOME_SUCCEEDED, "ep-2"),
        )
        score = score_predictions(
            predictions, evidence, node_version="tabular-1"
        )
        self.assertEqual(score.scored, 2)
        self.assertEqual(score.matched, 1)
        self.assertAlmostEqual(score.accuracy, 0.5)

    def test_an_episode_without_a_prediction_is_not_scored(self) -> None:
        score = score_predictions(
            (), (_evidence(_condition("a"), OUTCOME_FAILED),),
            node_version="tabular-1",
        )
        self.assertEqual(score.scored, 0)
        self.assertIsNone(score.accuracy)


class CalibrationGovernanceTest(unittest.TestCase):
    def test_an_unscored_node_cannot_reduce_the_real_budget(self) -> None:
        policy = CalibrationPolicy(min_scored=4, min_accuracy=0.75)
        allowed, why = policy.may_reduce_real_budget(
            CalibrationScore(node_version="tabular-1", scored=0, matched=0)
        )
        self.assertFalse(allowed)
        self.assertIn("scored", why)

    def test_an_inaccurate_node_cannot_reduce_the_real_budget(self) -> None:
        policy = CalibrationPolicy(min_scored=4, min_accuracy=0.75)
        allowed, why = policy.may_reduce_real_budget(
            CalibrationScore(node_version="tabular-1", scored=10, matched=5)
        )
        self.assertFalse(allowed)
        self.assertIn("accuracy", why)

    def test_a_calibrated_node_earns_the_reduction(self) -> None:
        policy = CalibrationPolicy(min_scored=4, min_accuracy=0.75)
        allowed, _ = policy.may_reduce_real_budget(
            CalibrationScore(node_version="tabular-1", scored=10, matched=9)
        )
        self.assertTrue(allowed)


if __name__ == "__main__":
    unittest.main()
