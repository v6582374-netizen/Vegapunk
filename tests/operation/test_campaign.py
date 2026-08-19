from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

from vegapunk.operation.campaign import (
    EXECUTION_COMPLETED,
    EXECUTION_HELD,
    STOP_COMPLETED,
    BatchPlan,
    BatchResult,
    BenchConfiguration,
    CalibrationScore,
    Campaign,
    Condition,
    EpisodeEvidence,
    Prediction,
    WorkOrder,
)
from vegapunk.operation.trace import (
    OUTCOME_FAILED,
    OUTCOME_INDETERMINATE,
    OUTCOME_SUCCEEDED,
)

_AT = datetime(2026, 8, 19, tzinfo=timezone.utc)


def _configuration(fixture: str = "bare bench") -> BenchConfiguration:
    return BenchConfiguration(
        fixture=fixture,
        object_identity="red cup 7cm",
        witness_pose_digest="pose-1",
        lighting_protocol="lab overhead, blinds closed",
        policy_identity="policy-v1",
        invocation_protocol="chunk8/replan160ms",
    )


def _condition(pose: str = "a4") -> Condition:
    return Condition.of(cup_pose=pose)


def _plan(
    plan_id: str,
    generation_id: str,
    *,
    conditions: tuple[Condition, ...] = (_condition(),),
    predicted: tuple[Condition, ...] = (),
) -> BatchPlan:
    return BatchPlan(
        plan_id=plan_id,
        generation_id=generation_id,
        objective="map the cup-pose envelope",
        real_conditions=conditions,
        predicted_conditions=predicted,
        real_anchor_count=1,
        predictive_node_version="tabular-1",
        confidence_threshold=0.7,
        selection_rationale="fixed table, first pass",
        expected_outcome="expect failures everywhere; the loop is under test",
        created_at=_AT,
    )


def _evidence(
    plan_id: str,
    generation_id: str,
    *,
    outcome: str = OUTCOME_SUCCEEDED,
    execution: str = EXECUTION_COMPLETED,
    condition: Condition | None = None,
    episode_id: str = "ep-1",
) -> EpisodeEvidence:
    return EpisodeEvidence(
        episode_id=episode_id,
        plan_id=plan_id,
        generation_id=generation_id,
        condition=condition or _condition(),
        execution=execution,
        outcome=outcome,
        outcome_detail="",
        reset_confirmed=True,
        reset_witnessed=True,
        witness_identity="bench_camera",
    )


def _result(
    plan_id: str,
    generation_id: str,
    episodes: tuple[EpisodeEvidence, ...],
) -> BatchResult:
    return BatchResult(
        plan_id=plan_id,
        generation_id=generation_id,
        episodes=episodes,
        predictions=(),
        calibration=CalibrationScore(
            node_version="tabular-1", scored=len(episodes), matched=0
        ),
        stop=STOP_COMPLETED,
        stop_detail="",
        anchored=bool(episodes),
        sealed_at=_AT,
    )


def _campaign() -> tuple[Campaign, str]:
    campaign = Campaign(clock=lambda: _AT)
    generation = campaign.open_founding_generation(
        _configuration(), opened_by="Wei"
    )
    return campaign, generation.generation_id


class PlanRulesTest(unittest.TestCase):
    def test_a_plan_is_immutable(self) -> None:
        campaign, generation_id = _campaign()
        plan = _plan("batch-1", generation_id)
        campaign.seal_plan(plan)
        with self.assertRaises(FrozenInstanceError):
            plan.objective = "something else"  # type: ignore[misc]

    def test_real_anchors_are_mandatory(self) -> None:
        with self.assertRaises(ValueError):
            BatchPlan(
                plan_id="batch-1",
                generation_id="gen-1",
                objective="x",
                real_conditions=(_condition(),),
                predicted_conditions=(),
                real_anchor_count=0,
                predictive_node_version="tabular-1",
                confidence_threshold=0.7,
                selection_rationale="r",
                expected_outcome="e",
                created_at=_AT,
            )

    def test_the_next_plan_needs_a_sealed_prior_result(self) -> None:
        campaign, generation_id = _campaign()
        campaign.seal_plan(_plan("batch-1", generation_id))

        with self.assertRaises(ValueError):
            campaign.seal_plan(_plan("batch-2", generation_id))

        campaign.record_result(
            _result("batch-1", generation_id, (_evidence("batch-1", generation_id),))
        )
        campaign.seal_plan(_plan("batch-2", generation_id))  # now allowed

    def test_a_result_attaches_to_a_sealed_plan_and_never_rewrites_it(self) -> None:
        campaign, generation_id = _campaign()
        with self.assertRaises(ValueError):
            campaign.record_result(
                _result("ghost", generation_id, (_evidence("ghost", generation_id),))
            )
        campaign.seal_plan(_plan("batch-1", generation_id))
        campaign.record_result(
            _result("batch-1", generation_id, (_evidence("batch-1", generation_id),))
        )
        with self.assertRaises(ValueError):
            campaign.record_result(
                _result("batch-1", generation_id, ())
            )


class EvidenceFactsTest(unittest.TestCase):
    def test_held_failed_indeterminate_and_completed_stay_distinct(self) -> None:
        held = _evidence("p", "g", execution=EXECUTION_HELD, outcome=OUTCOME_INDETERMINATE)
        failed = _evidence("p", "g", outcome=OUTCOME_FAILED)
        succeeded = _evidence("p", "g")
        self.assertFalse(held.success)
        self.assertFalse(failed.success)
        self.assertTrue(succeeded.success)

    def test_a_held_execution_can_never_be_a_success(self) -> None:
        with self.assertRaises(ValueError):
            _evidence("p", "g", execution=EXECUTION_HELD, outcome=OUTCOME_SUCCEEDED)

    def test_a_predicted_episode_can_never_be_a_success(self) -> None:
        evidence = EpisodeEvidence(
            episode_id="imagined-1",
            plan_id="p",
            generation_id="g",
            condition=_condition(),
            execution=EXECUTION_COMPLETED,
            outcome=OUTCOME_SUCCEEDED,
            outcome_detail="",
            reset_confirmed=True,
            reset_witnessed=True,
            witness_identity="imagined",
            source="predicted",
        )
        self.assertFalse(evidence.success)


class GenerationIsolationTest(unittest.TestCase):
    def test_identical_episodes_in_different_generations_never_pool(self) -> None:
        campaign, first_generation = _campaign()
        campaign.seal_plan(_plan("batch-1", first_generation))
        campaign.record_result(
            _result(
                "batch-1",
                first_generation,
                (_evidence("batch-1", first_generation, outcome=OUTCOME_FAILED),),
            )
        )

        campaign.propose_work_order(
            WorkOrder(
                order_id="wo-1",
                generation_id=first_generation,
                proposed_change="add a locating recess at the cup home",
                expected_gain="cup-pose envelope grows from 0 to 2 reliable cells",
                cost_risk="one 3d print, no risk to the robot",
                motivating_evidence=("batch-1",),
                proposed_at=_AT,
            )
        )
        second = campaign.confirm_work_order(
            "wo-1",
            confirmed_by="Wei",
            new_configuration=_configuration("recess fixture v1"),
        )

        campaign.seal_plan(_plan("batch-2", second.generation_id))
        campaign.record_result(
            _result(
                "batch-2",
                second.generation_id,
                (_evidence("batch-2", second.generation_id),),
            )
        )

        current = campaign.envelope()
        self.assertEqual(current.generation_id, second.generation_id)
        self.assertEqual(current.sample_count, 1)
        self.assertEqual(current.success_count, 1)

        historical = campaign.envelope(first_generation)
        self.assertEqual(historical.sample_count, 1)
        self.assertEqual(historical.success_count, 0)

        # History stays queryable after sealing.
        self.assertTrue(campaign.generation_sealed(first_generation))
        self.assertEqual(len(campaign.results()), 2)

    def test_a_plan_for_a_sealed_generation_is_refused(self) -> None:
        campaign, first_generation = _campaign()
        campaign.propose_work_order(
            WorkOrder(
                order_id="wo-1",
                generation_id=first_generation,
                proposed_change="recess",
                expected_gain="two more reliable cells",
                cost_risk="low",
                motivating_evidence=(),
                proposed_at=_AT,
            )
        )
        campaign.confirm_work_order(
            "wo-1", confirmed_by="Wei", new_configuration=_configuration("recess")
        )
        with self.assertRaises(ValueError):
            campaign.seal_plan(_plan("late", first_generation))


class WorkOrderLifecycleTest(unittest.TestCase):
    def test_a_work_order_must_stake_its_expected_gain(self) -> None:
        with self.assertRaises(ValueError):
            WorkOrder(
                order_id="wo-1",
                generation_id="gen-1",
                proposed_change="recess",
                expected_gain="  ",
                cost_risk="low",
                motivating_evidence=(),
                proposed_at=_AT,
            )

    def test_an_unconfirmed_work_order_cannot_open_a_generation(self) -> None:
        campaign, _ = _campaign()
        with self.assertRaises(ValueError):
            campaign.open_founding_generation(
                _configuration("second bench"), opened_by="Wei"
            )
        with self.assertRaises(ValueError):
            campaign.confirm_work_order(
                "never-proposed",
                confirmed_by="Wei",
                new_configuration=_configuration("x"),
            )

    def test_confirmation_needs_a_named_human(self) -> None:
        campaign, generation_id = _campaign()
        campaign.propose_work_order(
            WorkOrder(
                order_id="wo-1",
                generation_id=generation_id,
                proposed_change="recess",
                expected_gain="growth",
                cost_risk="low",
                motivating_evidence=(),
                proposed_at=_AT,
            )
        )
        with self.assertRaises(ValueError):
            campaign.confirm_work_order(
                "wo-1", confirmed_by="  ", new_configuration=_configuration("x")
            )

    def test_confirmation_seals_the_old_generation_and_opens_a_new_one(self) -> None:
        campaign, first_generation = _campaign()
        campaign.propose_work_order(
            WorkOrder(
                order_id="wo-1",
                generation_id=first_generation,
                proposed_change="recess",
                expected_gain="growth",
                cost_risk="low",
                motivating_evidence=(),
                proposed_at=_AT,
            )
        )
        second = campaign.confirm_work_order(
            "wo-1", confirmed_by="Wei", new_configuration=_configuration("recess")
        )

        self.assertTrue(campaign.generation_sealed(first_generation))
        self.assertFalse(campaign.generation_sealed(second.generation_id))
        self.assertEqual(second.work_order_id, "wo-1")
        self.assertEqual(second.predecessor_id, first_generation)
        confirmation = campaign.confirmation_for("wo-1")
        self.assertIsNotNone(confirmation)
        self.assertEqual(confirmation.confirmed_by, "Wei")
        with self.assertRaises(ValueError):
            campaign.confirm_work_order(
                "wo-1", confirmed_by="Wei", new_configuration=_configuration("y")
            )


class EffectivenessTest(unittest.TestCase):
    def test_the_two_curves_are_reported_separately(self) -> None:
        campaign, first_generation = _campaign()
        campaign.seal_plan(_plan("batch-1", first_generation))
        campaign.record_result(
            _result(
                "batch-1",
                first_generation,
                (
                    _evidence("batch-1", first_generation, outcome=OUTCOME_FAILED,
                              episode_id="ep-1"),
                    _evidence("batch-1", first_generation, episode_id="ep-2"),
                ),
            )
        )

        report = campaign.effectiveness(reliable_at=0.4)
        self.assertEqual(len(report.within_generation), 1)
        generation_id, rates = report.within_generation[0]
        self.assertEqual(generation_id, first_generation)
        self.assertEqual(rates, (0.5,))
        self.assertEqual(report.across_generations, ((first_generation, 1),))
        self.assertFalse(hasattr(report, "merged"))


if __name__ == "__main__":
    unittest.main()
