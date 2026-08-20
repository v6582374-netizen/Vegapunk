from __future__ import annotations

import unittest
from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from typing import cast

from vegapunk.embodied.embodiment import EmbodimentProfile
from vegapunk.embodied.promotion import (
    GOLDEN_EMBODIMENT,
    GOLDEN_INSTRUMENT_OPERATION_LOOP,
    GOLDEN_PROMOTION_CONFIGURATION,
    GOLDEN_SKILL_ID,
    PROMOTION_GATE_ORDER,
    CampaignPlan,
    CandidateBundle,
    GoldenSkillRevision,
    InstrumentOperationLoop,
    PromotionLedger,
    PromotionSubmission,
    SealedRejection,
    promote_generation,
)
from vegapunk.embodied.skill import SKILL_KIND_DETERMINISTIC, PhysicalSkill

NOW = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)


def _record_execution(
    executions: list[PromotionSubmission],
) -> Callable[[PromotionSubmission], None]:
    def execute(accepted: PromotionSubmission) -> None:
        executions.append(accepted)

    return execute


def _skill() -> GoldenSkillRevision:
    skill = PhysicalSkill(
        skill_id=GOLDEN_SKILL_ID,
        revision=1,
        kind=SKILL_KIND_DETERMINISTIC,
        summary="Open the lid, transfer with the cup, and restore the bench.",
        parameters=(),
        preconditions=("instrument_closed", "cup_at_home"),
        postconditions=(
            "instrument_closed",
            "cup_at_home",
            "transfer_complete",
        ),
        abort_conditions=("witness_indeterminate", "safety_stop"),
        max_duration_s=90.0,
        reviewed_by="skill_owner",
        policy=None,
    )
    return GoldenSkillRevision(
        skill=skill,
        operation_loop=GOLDEN_INSTRUMENT_OPERATION_LOOP,
    )


def _embodiment() -> EmbodimentProfile:
    return GOLDEN_EMBODIMENT


def _submission() -> PromotionSubmission:
    skill = _skill()
    embodiment = _embodiment()
    configuration = GOLDEN_PROMOTION_CONFIGURATION
    candidate = CandidateBundle(
        candidate_id="act-baseline-v1",
        policy_artifact_digest="act-checkpoint-sha256",
        data_manifest_digest="training-manifest-sha256",
        training_recipe_digest="act-recipe-sha256",
        observation_schema_digest="golden-observation-v1",
        action_schema_digest=configuration.action_protocol_digest,
        skill_revision_id=skill.version_id,
        skill_revision_digest=skill.digest(),
        embodiment_digest=embodiment.digest(),
        configuration_digest=configuration.digest(),
    )
    plan = CampaignPlan(
        campaign_id="generation-1-pilot",
        skill_revision_id=skill.version_id,
        candidate_digest=candidate.digest(),
        embodiment_digest=embodiment.digest(),
        configuration_digest=configuration.digest(),
        ordered_gates=PROMOTION_GATE_ORDER,
        hardware_attempts=5,
        prepared_by="campaign_owner",
    )
    return PromotionSubmission(
        skill=skill,
        candidate=candidate,
        embodiment=embodiment,
        configuration=configuration,
        plan=plan,
    )


class GenerationPromotionAcceptanceTest(unittest.TestCase):
    def test_a_complete_golden_skill_submission_reaches_execution(self) -> None:
        submission = _submission()
        events: list[str] = []
        expected = object()

        def execute(accepted: PromotionSubmission) -> object:
            events.append("execution")
            assert accepted.skill is not None
            self.assertEqual(
                accepted.skill.operation_loop,
                GOLDEN_INSTRUMENT_OPERATION_LOOP,
            )
            return expected

        result = promote_generation(
            submission,
            ledger=PromotionLedger(),
            execute=execute,
            now=NOW,
        )

        self.assertIs(result, expected)
        self.assertEqual(events, ["execution"])

    def test_any_missing_frozen_input_is_sealed_before_execution(self) -> None:
        cases = (
            ("skill", "skill_revision"),
            ("candidate", "candidate_bundle"),
            ("embodiment", "embodiment"),
            ("configuration", "configuration"),
            ("plan", "campaign_plan"),
        )
        for field_name, identity_name in cases:
            with self.subTest(field_name=field_name):
                submission = replace(_submission(), **{field_name: None})
                executions: list[PromotionSubmission] = []
                ledger = PromotionLedger()

                result = promote_generation(
                    submission,
                    ledger=ledger,
                    execute=_record_execution(executions),
                    now=NOW,
                )

                self.assertIsInstance(result, SealedRejection)
                assert isinstance(result, SealedRejection)
                self.assertEqual(executions, [])
                self.assertEqual(result.failed_gate, "contract_validation")
                self.assertEqual(
                    result.input_identities[identity_name], "missing"
                )
                self.assertEqual(ledger.rejections(), (result,))

    def test_a_candidate_for_another_skill_revision_is_sealed(self) -> None:
        submission = _submission()
        candidate = submission.candidate
        assert candidate is not None
        mismatched = replace(
            submission,
            candidate=replace(
                candidate,
                skill_revision_id="golden_instrument_operation_loop@2",
            ),
        )
        executions: list[PromotionSubmission] = []

        result = promote_generation(
            mismatched,
            ledger=PromotionLedger(),
            execute=lambda accepted: executions.append(accepted),
            now=NOW,
        )

        self.assertIsInstance(result, SealedRejection)
        assert isinstance(result, SealedRejection)
        self.assertEqual(executions, [])
        self.assertIn("skill revision", " ".join(result.reasons).lower())

    def test_conflicting_input_identities_are_sealed(self) -> None:
        submission = _submission()
        skill = submission.skill
        candidate = submission.candidate
        embodiment = submission.embodiment
        configuration = submission.configuration
        plan = submission.plan
        assert skill is not None
        assert candidate is not None
        assert embodiment is not None
        assert configuration is not None
        assert plan is not None

        cases = (
            replace(
                submission,
                candidate=replace(candidate, skill_revision_digest="other-skill"),
            ),
            replace(
                submission,
                candidate=replace(candidate, embodiment_digest="other-robot"),
            ),
            replace(
                submission,
                candidate=replace(candidate, configuration_digest="other-config"),
            ),
            replace(
                submission,
                configuration=replace(
                    configuration, embodiment_digest="other-robot"
                ),
            ),
            replace(
                submission,
                plan=replace(plan, skill_revision_id="other-skill@1"),
            ),
            replace(
                submission,
                plan=replace(plan, candidate_digest="other-candidate"),
            ),
            replace(
                submission,
                plan=replace(plan, embodiment_digest="other-robot"),
            ),
            replace(
                submission,
                plan=replace(plan, configuration_digest="other-config"),
            ),
        )

        for conflicting in cases:
            with self.subTest(promotion_digest=conflicting.digest()):
                executions: list[PromotionSubmission] = []
                result = promote_generation(
                    conflicting,
                    ledger=PromotionLedger(),
                    execute=_record_execution(executions),
                    now=NOW,
                )

                self.assertIsInstance(result, SealedRejection)
                assert isinstance(result, SealedRejection)
                self.assertEqual(executions, [])
                self.assertTrue(result.reasons)

    def test_the_campaign_plan_cannot_skip_or_reorder_gates(self) -> None:
        submission = _submission()
        plan = submission.plan
        assert plan is not None
        invalid_orders = (
            PROMOTION_GATE_ORDER[1:],
            (
                PROMOTION_GATE_ORDER[0],
                PROMOTION_GATE_ORDER[2],
                PROMOTION_GATE_ORDER[1],
                *PROMOTION_GATE_ORDER[3:],
            ),
        )

        for order in invalid_orders:
            with self.subTest(order=order):
                executions: list[PromotionSubmission] = []
                result = promote_generation(
                    replace(submission, plan=replace(plan, ordered_gates=order)),
                    ledger=PromotionLedger(),
                    execute=_record_execution(executions),
                    now=NOW,
                )

                self.assertIsInstance(result, SealedRejection)
                assert isinstance(result, SealedRejection)
                self.assertEqual(executions, [])
                self.assertIn("gate order", " ".join(result.reasons).lower())

    def test_incomplete_or_incompatible_contracts_are_sealed(self) -> None:
        submission = _submission()
        candidate = submission.candidate
        embodiment = submission.embodiment
        configuration = submission.configuration
        plan = submission.plan
        assert candidate is not None
        assert embodiment is not None
        assert configuration is not None
        assert plan is not None

        cases = (
            replace(
                submission,
                embodiment=replace(
                    embodiment, unverified_fields=("camera_map",)
                ),
            ),
            replace(
                submission,
                candidate=replace(candidate, policy_artifact_digest=""),
            ),
            replace(
                submission,
                candidate=replace(
                    candidate, observation_schema_digest="other-observation"
                ),
            ),
            replace(
                submission,
                candidate=replace(candidate, action_schema_digest="joint-v0"),
            ),
            replace(
                submission,
                configuration=replace(
                    configuration, independent_witness_digest=""
                ),
            ),
            replace(
                submission,
                plan=replace(plan, hardware_attempts=0),
            ),
            replace(
                submission,
                plan=replace(plan, prepared_by=""),
            ),
        )

        for invalid in cases:
            with self.subTest(promotion_digest=invalid.digest()):
                executions: list[PromotionSubmission] = []
                result = promote_generation(
                    invalid,
                    ledger=PromotionLedger(),
                    execute=_record_execution(executions),
                    now=NOW,
                )

                self.assertIsInstance(result, SealedRejection)
                assert isinstance(result, SealedRejection)
                self.assertEqual(executions, [])
                self.assertTrue(result.reasons)

    def test_a_self_consistent_but_different_bench_is_still_sealed(self) -> None:
        submission = _submission()
        candidate = submission.candidate
        embodiment = submission.embodiment
        configuration = submission.configuration
        plan = submission.plan
        assert candidate is not None
        assert embodiment is not None
        assert configuration is not None
        assert plan is not None

        other_embodiment = replace(embodiment, robot_model="unitree_g1_lab_copy")
        other_configuration = replace(
            configuration,
            configuration_id="other-bench-v1",
            embodiment_digest=other_embodiment.digest(),
        )
        other_candidate = replace(
            candidate,
            embodiment_digest=other_embodiment.digest(),
            configuration_digest=other_configuration.digest(),
        )
        other_plan = replace(
            plan,
            candidate_digest=other_candidate.digest(),
            embodiment_digest=other_embodiment.digest(),
            configuration_digest=other_configuration.digest(),
        )
        executions: list[PromotionSubmission] = []

        result = promote_generation(
            replace(
                submission,
                candidate=other_candidate,
                embodiment=other_embodiment,
                configuration=other_configuration,
                plan=other_plan,
            ),
            ledger=PromotionLedger(),
            execute=_record_execution(executions),
            now=NOW,
        )

        self.assertIsInstance(result, SealedRejection)
        self.assertEqual(executions, [])

    def test_partial_or_reordered_segments_cannot_claim_task_success(self) -> None:
        submission = _submission()
        skill = submission.skill
        assert skill is not None
        invalid_loops = (
            GOLDEN_INSTRUMENT_OPERATION_LOOP.steps[:3],
            (
                GOLDEN_INSTRUMENT_OPERATION_LOOP.steps[1],
                GOLDEN_INSTRUMENT_OPERATION_LOOP.steps[0],
                *GOLDEN_INSTRUMENT_OPERATION_LOOP.steps[2:],
            ),
        )

        for operation_steps in invalid_loops:
            with self.subTest(operation_steps=operation_steps):
                executions: list[PromotionSubmission] = []
                result = promote_generation(
                    replace(
                        submission,
                        skill=replace(
                            skill,
                            operation_loop=InstrumentOperationLoop(
                                steps=operation_steps
                            ),
                        ),
                    ),
                    ledger=PromotionLedger(),
                    execute=_record_execution(executions),
                    now=NOW,
                )

                self.assertIsInstance(result, SealedRejection)
                assert isinstance(result, SealedRejection)
                self.assertEqual(executions, [])
                self.assertIn(
                    "complete ordered instrument operation loop",
                    " ".join(result.reasons).lower(),
                )

    def test_equivalent_frozen_inputs_have_stable_identities(self) -> None:
        first = _submission()
        second = _submission()

        first_identities = promote_generation(
            first,
            ledger=PromotionLedger(),
            execute=lambda accepted: dict(accepted.identities()),
            now=NOW,
        )
        second_identities = promote_generation(
            second,
            ledger=PromotionLedger(),
            execute=lambda accepted: dict(accepted.identities()),
            now=NOW,
        )

        self.assertEqual(first.digest(), second.digest())
        self.assertEqual(first_identities, second_identities)
        assert isinstance(first_identities, dict)
        self.assertNotIn("missing", first_identities.values())

    def test_a_sealed_rejection_cannot_be_rewritten_by_a_later_result(
        self,
    ) -> None:
        submission = replace(_submission(), candidate=None)
        ledger = PromotionLedger()

        first = promote_generation(
            submission,
            ledger=ledger,
            execute=lambda accepted: "unexpected",
            now=NOW,
        )
        later_executions: list[PromotionSubmission] = []
        second = promote_generation(
            submission,
            ledger=ledger,
            execute=lambda accepted: later_executions.append(accepted),
            now=NOW.replace(hour=11),
        )

        self.assertIsInstance(first, SealedRejection)
        assert isinstance(first, SealedRejection)
        self.assertIs(second, first)
        self.assertEqual(later_executions, [])
        self.assertEqual(ledger.rejections(), (first,))
        with self.assertRaises(FrozenInstanceError):
            first.failed_gate = "hardware_pilot"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            cast(dict[str, str], first.input_identities)[
                "candidate_bundle"
            ] = "late-success"


if __name__ == "__main__":
    unittest.main()
