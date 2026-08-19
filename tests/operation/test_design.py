from __future__ import annotations

import unittest
from datetime import datetime, timezone

from vegapunk.operation.campaign import (
    STOP_COMPLETED,
    BatchResult,
    BenchConfiguration,
    CalibrationScore,
    Campaign,
    Condition,
    EpisodeEvidence,
)
from vegapunk.operation.design import (
    CLASS_CONDITION,
    CLASS_DATA,
    CLASS_ENVIRONMENT,
    PROPOSAL_CLASSES,
    Proposal,
    TableBatchDesigner,
)
from vegapunk.operation.predict import CalibrationPolicy
from vegapunk.operation.trace import OUTCOME_FAILED, OUTCOME_SUCCEEDED

_AT = datetime(2026, 8, 19, tzinfo=timezone.utc)

_POSE_A = Condition.of(cup_pose="a")
_POSE_B = Condition.of(cup_pose="b")


def _campaign() -> Campaign:
    campaign = Campaign(clock=lambda: _AT)
    campaign.open_founding_generation(
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
    return campaign


def _designer(**overrides: object) -> TableBatchDesigner:
    fields: dict[str, object] = {
        "table": (_POSE_A, _POSE_B),
        "episodes_per_batch": 4,
        "objective": "map the cup-pose envelope of policy-v1",
        "calibration_policy": CalibrationPolicy(min_scored=4, min_accuracy=0.75),
        "repeated_failure_threshold": 3,
        "clock": lambda: _AT,
    }
    fields.update(overrides)
    return TableBatchDesigner(**fields)  # type: ignore[arg-type]


def _evidence(
    plan_id: str,
    generation_id: str,
    condition: Condition,
    outcome: str,
    episode_id: str,
) -> EpisodeEvidence:
    return EpisodeEvidence(
        episode_id=episode_id,
        plan_id=plan_id,
        generation_id=generation_id,
        condition=condition,
        execution="completed",
        outcome=outcome,
        outcome_detail="",
        reset_confirmed=True,
        reset_witnessed=True,
        witness_identity="bench_camera",
    )


def _record_batch(
    campaign: Campaign,
    designer: TableBatchDesigner,
    plan_id: str,
    outcomes: dict[Condition, str],
) -> None:
    generation = campaign.current_generation
    design = designer.design(
        plan_id=plan_id,
        generation=generation,
        envelope=campaign.envelope(),
        prior_results=campaign.results(),
        calibration=campaign.calibration("tabular-1"),
    )
    campaign.seal_plan(design.plan)
    episodes = tuple(
        _evidence(
            plan_id,
            generation.generation_id,
            condition,
            outcomes[condition],
            f"{plan_id}-ep-{index}",
        )
        for index, condition in enumerate(design.plan.real_conditions)
    )
    campaign.record_result(
        BatchResult(
            plan_id=plan_id,
            generation_id=generation.generation_id,
            episodes=episodes,
            predictions=(),
            calibration=CalibrationScore(
                node_version="tabular-1", scored=0, matched=0
            ),
            stop=STOP_COMPLETED,
            stop_detail="",
            anchored=True,
            sealed_at=_AT,
        )
    )


class ProposalTest(unittest.TestCase):
    def test_every_proposal_states_its_class_and_rationale(self) -> None:
        with self.assertRaises(ValueError):
            Proposal(action_class="vibes", rationale="because")
        with self.assertRaises(ValueError):
            Proposal(action_class=CLASS_CONDITION, rationale="  ")
        self.assertIn(CLASS_ENVIRONMENT, PROPOSAL_CLASSES)


class FirstBatchTest(unittest.TestCase):
    def test_the_first_plan_spreads_across_the_table(self) -> None:
        campaign = _campaign()
        designer = _designer()
        design = designer.design(
            plan_id="batch-1",
            generation=campaign.current_generation,
            envelope=campaign.envelope(),
            prior_results=(),
            calibration=campaign.calibration("tabular-1"),
        )
        chosen = set(design.plan.real_conditions)
        self.assertEqual(chosen, {_POSE_A, _POSE_B})
        self.assertGreaterEqual(design.plan.real_anchor_count, 1)
        # An uncalibrated node buys no imagined episodes.
        self.assertEqual(design.plan.predicted_conditions, ())
        for proposal in design.proposals:
            self.assertIn(proposal.action_class, PROPOSAL_CLASSES)
            self.assertTrue(proposal.rationale.strip())
        # Unexplored conditions are named as a data need.
        self.assertTrue(
            any(p.action_class == CLASS_DATA for p in design.proposals)
        )


class AdaptationTest(unittest.TestCase):
    def test_the_next_plan_spends_more_where_the_last_batch_failed(self) -> None:
        campaign = _campaign()
        designer = _designer()
        _record_batch(
            campaign,
            designer,
            "batch-1",
            {_POSE_A: OUTCOME_FAILED, _POSE_B: OUTCOME_SUCCEEDED},
        )

        design = designer.design(
            plan_id="batch-2",
            generation=campaign.current_generation,
            envelope=campaign.envelope(),
            prior_results=campaign.results(),
            calibration=campaign.calibration("tabular-1"),
        )
        allocation = design.plan.real_conditions + design.plan.predicted_conditions
        spent_on_a = sum(1 for c in allocation if c == _POSE_A)
        spent_on_b = sum(1 for c in allocation if c == _POSE_B)
        self.assertGreater(spent_on_a, spent_on_b)
        self.assertNotEqual(
            design.plan.real_conditions,
            campaign.plans()[0].real_conditions,
        )

    def test_repeated_equivalent_failures_emit_a_work_order(self) -> None:
        campaign = _campaign()
        designer = _designer(repeated_failure_threshold=2)
        _record_batch(
            campaign, designer, "batch-1",
            {_POSE_A: OUTCOME_FAILED, _POSE_B: OUTCOME_SUCCEEDED},
        )
        _record_batch(
            campaign, designer, "batch-2",
            {_POSE_A: OUTCOME_FAILED, _POSE_B: OUTCOME_SUCCEEDED},
        )

        design = designer.design(
            plan_id="batch-3",
            generation=campaign.current_generation,
            envelope=campaign.envelope(),
            prior_results=campaign.results(),
            calibration=campaign.calibration("tabular-1"),
        )
        self.assertEqual(len(design.work_orders), 1)
        order = design.work_orders[0]
        self.assertTrue(order.expected_gain.strip())
        self.assertIn("cup_pose=a", order.proposed_change)
        self.assertTrue(
            any(
                p.action_class == CLASS_ENVIRONMENT for p in design.proposals
            )
        )


class CalibrationBudgetTest(unittest.TestCase):
    def test_a_calibrated_node_earns_imagined_episodes(self) -> None:
        campaign = _campaign()
        designer = _designer()
        design = designer.design(
            plan_id="batch-2",
            generation=campaign.current_generation,
            envelope=campaign.envelope(),
            prior_results=(),
            calibration=CalibrationScore(
                node_version="tabular-1", scored=10, matched=9
            ),
        )
        self.assertGreater(len(design.plan.predicted_conditions), 0)
        self.assertGreaterEqual(len(design.plan.real_conditions), 1)


class ConstraintTest(unittest.TestCase):
    def test_a_refused_condition_is_recorded_rather_than_dropped(self) -> None:
        campaign = _campaign()

        def admissible(condition: Condition) -> tuple[bool, str]:
            if condition == _POSE_B:
                return False, "outside the monitor's target envelope"
            return True, ""

        designer = _designer(admissible=admissible)
        design = designer.design(
            plan_id="batch-1",
            generation=campaign.current_generation,
            envelope=campaign.envelope(),
            prior_results=(),
            calibration=campaign.calibration("tabular-1"),
        )
        self.assertNotIn(_POSE_B, design.plan.real_conditions)
        self.assertEqual(len(design.refused), 1)
        self.assertEqual(design.refused[0].condition, _POSE_B)
        self.assertIn("envelope", design.refused[0].reason)


if __name__ == "__main__":
    unittest.main()
