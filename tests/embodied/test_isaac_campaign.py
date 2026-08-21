from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone

from vegapunk.embodied.episode import InitialStateEnvelope, QualifiedReplay
from vegapunk.embodied.isaac import (
    GOLDEN_ISAAC_SCENE,
    ISAAC_LAB_SOURCE,
    ISAAC_LAB_VERSION,
    VERDICT_FAILED,
    VERDICT_SUCCEEDED,
    IsaacLabEpisode,
    IsaacRuntimeProvenance,
)
from vegapunk.embodied.isaac_campaign import (
    CALIBRATED_FACT,
    ISAAC_ATTEMPT_HARD_FAILURE,
    ISAAC_ATTEMPT_INDETERMINATE,
    ISAAC_ATTEMPT_SAFETY_VIOLATION,
    ISAAC_ATTEMPT_SUCCEEDED,
    PERTURBATION_CAMERA_CALIBRATION,
    PERTURBATION_FRICTION,
    PERTURBATION_LATENCY,
    PERTURBATION_LIGHTING,
    PERTURBATION_MASS,
    PERTURBATION_OBJECT_INITIAL_STATE,
    PERTURBATION_SENSOR_NOISE,
    UNVERIFIED_PERTURBATION_AXIS,
    IsaacCampaignCondition,
    IsaacCampaignEvidenceLedger,
    IsaacCampaignPlan,
    IsaacCampaignResult,
    IsaacGatePolicy,
    IsaacPerturbation,
    execute_isaac_campaign,
    promote_through_isaac_gate,
)
from vegapunk.embodied.promotion import (
    GATE_ISAAC_LAB,
    GOLDEN_EMBODIMENT,
    GOLDEN_INSTRUMENT_OPERATION_LOOP,
    GOLDEN_PROMOTION_CONFIGURATION,
    GOLDEN_SKILL_ID,
    PROMOTION_GATE_ORDER,
    CampaignPlan,
    CandidateBundle,
    GoldenSkillRevision,
    PromotionLedger,
    PromotionSubmission,
    SealedRejection,
)
from vegapunk.embodied.skill import SKILL_KIND_DETERMINISTIC, PhysicalSkill
from vegapunk.operation.target import HAND_OPEN, STAND_BODY, WholeBodyTarget

AT = datetime(2026, 8, 21, 15, 0, tzinfo=timezone.utc)


def _skill() -> GoldenSkillRevision:
    return GoldenSkillRevision(
        skill=PhysicalSkill(
            skill_id=GOLDEN_SKILL_ID,
            revision=1,
            kind=SKILL_KIND_DETERMINISTIC,
            summary="Open, transfer, and restore the instrument.",
            parameters=(),
            preconditions=("instrument_closed",),
            postconditions=("instrument_closed", "transfer_complete"),
            abort_conditions=("safety_stop",),
            max_duration_s=90.0,
            reviewed_by="skill_owner",
        ),
        operation_loop=GOLDEN_INSTRUMENT_OPERATION_LOOP,
    )


def _submission() -> PromotionSubmission:
    skill = _skill()
    candidate = CandidateBundle(
        candidate_id="candidate-isaac-campaign-001",
        policy_artifact_digest="policy-artifact-001",
        data_manifest_digest="training-manifest-001",
        training_recipe_digest="recipe-001",
        observation_schema_digest=GOLDEN_PROMOTION_CONFIGURATION.observation_schema_digest,
        action_schema_digest=GOLDEN_PROMOTION_CONFIGURATION.action_protocol_digest,
        skill_revision_id=skill.version_id,
        skill_revision_digest=skill.digest(),
        embodiment_digest=GOLDEN_EMBODIMENT.digest(),
        configuration_digest=GOLDEN_PROMOTION_CONFIGURATION.digest(),
    )
    return PromotionSubmission(
        skill=skill,
        candidate=candidate,
        embodiment=GOLDEN_EMBODIMENT,
        configuration=GOLDEN_PROMOTION_CONFIGURATION,
        plan=CampaignPlan(
            campaign_id="isaac-campaign-promotion-001",
            skill_revision_id=skill.version_id,
            candidate_digest=candidate.digest(),
            embodiment_digest=GOLDEN_EMBODIMENT.digest(),
            configuration_digest=GOLDEN_PROMOTION_CONFIGURATION.digest(),
            ordered_gates=PROMOTION_GATE_ORDER,
            hardware_attempts=1,
            prepared_by="campaign_owner",
        ),
    )


def _replay(target_count: int = 1) -> QualifiedReplay:
    targets = tuple(
        WholeBodyTarget(
            sequence=index,
            source_time_ns=2_000_000_000 + index,
            valid_until_ns=2_100_000_000 + index,
            body=STAND_BODY,
            left_hand=HAND_OPEN,
            right_hand=HAND_OPEN,
        )
        for index in range(1, target_count + 1)
    )
    return QualifiedReplay(
        source_episode_id="episode-isaac-campaign-001",
        source_episode_digest="episode-digest-001",
        control_frequency_hz=GOLDEN_EMBODIMENT.control_frequency_hz,
        initial_state_envelope=InitialStateEnvelope(
            source_episode_id="episode-isaac-campaign-001",
            configuration_digest=GOLDEN_PROMOTION_CONFIGURATION.digest(),
            reset_digest="reset-digest-001",
            first_observation_digest="first-observation-digest-001",
        ),
        artifact_digest="artifact-digest-001",
        targets=targets,
    )


def _perturbations() -> tuple[IsaacPerturbation, ...]:
    return (
        IsaacPerturbation(
            PERTURBATION_OBJECT_INITIAL_STATE,
            CALIBRATED_FACT,
            {
                "x_m": 0.0,
                "y_m": 0.0,
                "z_m": 0.0,
                "roll_rad": 0.0,
                "pitch_rad": 0.0,
                "yaw_rad": 0.0,
            },
            "m",
        ),
        IsaacPerturbation(
            PERTURBATION_FRICTION,
            UNVERIFIED_PERTURBATION_AXIS,
            {"coefficient": 0.6},
            "cof",
        ),
        IsaacPerturbation(
            PERTURBATION_MASS,
            UNVERIFIED_PERTURBATION_AXIS,
            {"mass_kg": 0.2},
            "kg",
        ),
        IsaacPerturbation(
            PERTURBATION_LIGHTING,
            UNVERIFIED_PERTURBATION_AXIS,
            {"illuminance_lux": 750.0},
            "lux",
        ),
        IsaacPerturbation(
            PERTURBATION_CAMERA_CALIBRATION,
            CALIBRATED_FACT,
            {
                "fx_px": 530.0,
                "fy_px": 530.0,
                "cx_px": 320.0,
                "cy_px": 240.0,
                "x_m": 0.0,
                "y_m": 0.0,
                "z_m": 0.0,
                "roll_rad": 0.0,
                "pitch_rad": 0.0,
                "yaw_rad": 0.0,
            },
            "camera_calibration",
        ),
        IsaacPerturbation(
            PERTURBATION_SENSOR_NOISE,
            UNVERIFIED_PERTURBATION_AXIS,
            {"standard_deviation": 0.01},
            "ratio",
        ),
        IsaacPerturbation(
            PERTURBATION_LATENCY,
            UNVERIFIED_PERTURBATION_AXIS,
            {"delay_ms": 30.0},
            "ms",
        ),
    )


def _plan(candidate: CandidateBundle, replay: QualifiedReplay) -> IsaacCampaignPlan:
    return IsaacCampaignPlan(
        campaign_id="isaac-robustness-001",
        candidate_digest=candidate.digest(),
        replay_digest=replay.digest(),
        conditions=(
            IsaacCampaignCondition("condition-a", 101, _perturbations()),
            IsaacCampaignCondition(
                "condition-b",
                102,
                tuple(
                    replace(
                        item,
                        value={
                            component: value + 0.01
                            for component, value in item.value.items()
                        },
                    )
                    for item in _perturbations()
                ),
            ),
        ),
    )


class _IsaacCampaignHost:
    @property
    def provenance(self) -> IsaacRuntimeProvenance:
        return IsaacRuntimeProvenance(
            source=ISAAC_LAB_SOURCE,
            simulator_version=ISAAC_LAB_VERSION,
            admission_capable=True,
        )

    def __init__(
        self,
        verdicts: tuple[str, ...],
        *,
        applied_condition_digest: str | None = None,
        target_sequences: tuple[int, ...] | None = None,
    ) -> None:
        self._verdicts = iter(verdicts)
        self._applied_condition_digest = applied_condition_digest
        self._target_sequences = target_sequences
        self.seen: list[tuple[str, int]] = []

    def run(self, replay, *, condition, seed):
        self.seen.append((condition.condition_id, seed))
        verdict = next(self._verdicts)
        target_sequences = self._target_sequences or tuple(
            target.sequence for target in replay.targets
        )
        return IsaacCampaignResult(
            trajectory=IsaacLabEpisode(
                source=ISAAC_LAB_SOURCE,
                simulator_version=ISAAC_LAB_VERSION,
                scene_digest=GOLDEN_ISAAC_SCENE.digest(),
                replay_digest=replay.digest(),
                seed=seed,
                target_sequences=target_sequences,
                policy_camera_observations=(GOLDEN_ISAAC_SCENE.policy_camera_key,),
                observed_contacts=GOLDEN_ISAAC_SCENE.required_contacts,
                witness_value="closed",
                witness_age_ns=0,
                verdict=VERDICT_SUCCEEDED
                if verdict == ISAAC_ATTEMPT_SUCCEEDED
                else VERDICT_FAILED,
                trace_digest=f"trace-{condition.condition_id}",
            ),
            applied_condition_digest=(
                self._applied_condition_digest or condition.digest()
            ),
            executed_target_sequences=target_sequences,
            verdict=verdict,
            detail=f"{verdict} under {condition.condition_id}",
        )


class IsaacCampaignAcceptanceTest(unittest.TestCase):
    def test_pre_registered_conditions_cover_every_axis_and_keep_each_seed(
        self,
    ) -> None:
        submission = _submission()
        candidate = submission.candidate
        assert candidate is not None

        plan = _plan(candidate, _replay())

        self.assertEqual(
            set(plan.conditions[0].parameter_names),
            {
                PERTURBATION_OBJECT_INITIAL_STATE,
                PERTURBATION_FRICTION,
                PERTURBATION_MASS,
                PERTURBATION_LIGHTING,
                PERTURBATION_CAMERA_CALIBRATION,
                PERTURBATION_SENSOR_NOISE,
                PERTURBATION_LATENCY,
            },
        )
        self.assertEqual(plan.conditions[0].seed, 101)
        self.assertNotEqual(plan.conditions[0].digest(), plan.conditions[1].digest())
        self.assertEqual(
            plan.conditions[0].perturbations[0].classification, CALIBRATED_FACT
        )
        self.assertEqual(
            plan.conditions[0].perturbations[1].classification,
            UNVERIFIED_PERTURBATION_AXIS,
        )

    def test_each_attempt_seals_its_seed_condition_trajectory_and_verdict(self) -> None:
        submission = _submission()
        candidate = submission.candidate
        assert candidate is not None
        host = _IsaacCampaignHost((ISAAC_ATTEMPT_SUCCEEDED, ISAAC_ATTEMPT_SUCCEEDED))
        ledger = IsaacCampaignEvidenceLedger()
        replay = _replay()

        evidence = execute_isaac_campaign(
            _plan(candidate, replay),
            candidate=candidate,
            replay=replay,
            runtime=host,
            ledger=ledger,
            now=AT,
        )

        self.assertEqual(host.seen, [("condition-a", 101), ("condition-b", 102)])
        self.assertEqual(
            tuple(attempt.seed for attempt in evidence.attempts), (101, 102)
        )
        self.assertEqual(
            tuple(attempt.condition_id for attempt in evidence.attempts),
            ("condition-a", "condition-b"),
        )
        self.assertTrue(
            all(attempt.trajectory.trace_digest for attempt in evidence.attempts)
        )
        self.assertTrue(
            all(
                attempt.verdict == ISAAC_ATTEMPT_SUCCEEDED
                for attempt in evidence.attempts
            )
        )
        self.assertEqual(ledger.evidence_for(evidence.digest()), evidence)

    def test_policy_refuses_every_non_success_category_even_when_success_rate_is_high(
        self,
    ) -> None:
        submission = _submission()
        candidate = submission.candidate
        assert candidate is not None
        policy = IsaacGatePolicy(min_success_rate=0.5)
        replay = _replay()

        for verdict, expected_reason in (
            (ISAAC_ATTEMPT_SAFETY_VIOLATION, "safety violation"),
            (ISAAC_ATTEMPT_HARD_FAILURE, "hard failure"),
            (ISAAC_ATTEMPT_INDETERMINATE, "indeterminate"),
        ):
            with self.subTest(verdict=verdict):
                ledger = IsaacCampaignEvidenceLedger()
                evidence = execute_isaac_campaign(
                    _plan(candidate, replay),
                    candidate=candidate,
                    replay=replay,
                    runtime=_IsaacCampaignHost((ISAAC_ATTEMPT_SUCCEEDED, verdict)),
                    ledger=ledger,
                    now=AT,
                )

                decision = ledger.decide(evidence, policy)

                self.assertFalse(decision.admitted)
                self.assertIn(expected_reason, " ".join(decision.blocking_reasons))

    def test_the_host_receipt_must_prove_the_registered_condition_and_replay(
        self,
    ) -> None:
        submission = _submission()
        candidate = submission.candidate
        assert candidate is not None
        replay = _replay(target_count=2)
        campaign = _plan(candidate, replay)

        with self.assertRaisesRegex(ValueError, "condition receipt"):
            execute_isaac_campaign(
                campaign,
                candidate=candidate,
                replay=replay,
                runtime=_IsaacCampaignHost(
                    (ISAAC_ATTEMPT_SUCCEEDED, ISAAC_ATTEMPT_SUCCEEDED),
                    applied_condition_digest="other-condition",
                ),
                ledger=IsaacCampaignEvidenceLedger(),
                now=AT,
            )

        with self.assertRaisesRegex(ValueError, "consume the Qualified Replay"):
            execute_isaac_campaign(
                campaign,
                candidate=candidate,
                replay=replay,
                runtime=_IsaacCampaignHost(
                    (ISAAC_ATTEMPT_SUCCEEDED, ISAAC_ATTEMPT_SUCCEEDED),
                    target_sequences=(1,),
                ),
                ledger=IsaacCampaignEvidenceLedger(),
                now=AT,
            )

    def test_failed_isaac_gate_seals_the_promotion_and_never_calls_later_hardware(
        self,
    ) -> None:
        submission = _submission()
        candidate = submission.candidate
        assert candidate is not None
        hardware_stages: list[PromotionSubmission] = []
        replay = _replay()

        result = promote_through_isaac_gate(
            submission,
            campaign=_plan(candidate, replay),
            replay=replay,
            runtime=_IsaacCampaignHost(
                (ISAAC_ATTEMPT_SUCCEEDED, ISAAC_ATTEMPT_SAFETY_VIOLATION)
            ),
            evidence_ledger=IsaacCampaignEvidenceLedger(),
            gate_policy=IsaacGatePolicy(min_success_rate=0.5),
            promotion_ledger=PromotionLedger(),
            execute_later=hardware_stages.append,
            now=AT,
        )

        self.assertIsInstance(result, SealedRejection)
        assert isinstance(result, SealedRejection)
        self.assertEqual(result.failed_gate, GATE_ISAAC_LAB)
        self.assertIn("safety violation", " ".join(result.reasons))
        self.assertEqual(hardware_stages, [])

    def test_an_admitted_isaac_gate_reaches_the_next_stage(self) -> None:
        submission = _submission()
        candidate = submission.candidate
        assert candidate is not None
        replay = _replay()
        hardware_stages: list[PromotionSubmission] = []

        result = promote_through_isaac_gate(
            submission,
            campaign=_plan(candidate, replay),
            replay=replay,
            runtime=_IsaacCampaignHost(
                (ISAAC_ATTEMPT_SUCCEEDED, ISAAC_ATTEMPT_SUCCEEDED)
            ),
            evidence_ledger=IsaacCampaignEvidenceLedger(),
            gate_policy=IsaacGatePolicy(min_success_rate=1.0),
            promotion_ledger=PromotionLedger(),
            execute_later=hardware_stages.append,
            now=AT,
        )

        self.assertIsNone(result)
        self.assertEqual(hardware_stages, [submission])


if __name__ == "__main__":
    unittest.main()
