from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import cast

from vegapunk.embodied.episode import InitialStateEnvelope, QualifiedReplay
from vegapunk.embodied.isaac import (
    GOLDEN_ISAAC_SCENE,
    ISAAC_LAB_SOURCE,
    ISAAC_LAB_VERSION,
    VERDICT_SUCCEEDED,
    IsaacLabEpisode,
)
from vegapunk.embodied.isaac_campaign import (
    ISAAC_ATTEMPT_SUCCEEDED,
    IsaacCampaignAttempt,
    IsaacCampaignEvidence,
    IsaacCampaignEvidenceLedger,
    IsaacGatePolicy,
)
from vegapunk.embodied.mujoco import (
    MUJOCO_SOURCE,
    MUJOCO_VERSION,
    MujocoAdapter,
    MujocoControlPolicy,
    MujocoControlSurface,
    MujocoEvidenceLedger,
    MujocoRun,
    MujocoRuntimeProvenance,
    MujocoValidationCase,
    MujocoValidationEvidence,
    MujocoValidationPlan,
    SimulatorDisagreementPolicy,
    execute_mujoco_validation,
    promote_through_mujoco_gate,
)
from vegapunk.embodied.promotion import (
    GATE_MUJOCO,
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

AT = datetime(2026, 8, 21, 16, 0, tzinfo=timezone.utc)


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
        candidate_id="candidate-mujoco-001",
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
            campaign_id="mujoco-gate-001",
            skill_revision_id=skill.version_id,
            candidate_digest=candidate.digest(),
            embodiment_digest=GOLDEN_EMBODIMENT.digest(),
            configuration_digest=GOLDEN_PROMOTION_CONFIGURATION.digest(),
            ordered_gates=PROMOTION_GATE_ORDER,
            hardware_attempts=1,
            prepared_by="campaign_owner",
        ),
    )


def _replay() -> QualifiedReplay:
    targets = tuple(
        WholeBodyTarget(
            sequence=index,
            source_time_ns=2_000_000_000 + index,
            valid_until_ns=2_100_000_000 + index,
            body=STAND_BODY,
            left_hand=HAND_OPEN,
            right_hand=HAND_OPEN,
        )
        for index in (1, 2)
    )
    return QualifiedReplay(
        source_episode_id="episode-mujoco-001",
        source_episode_digest="episode-digest-001",
        control_frequency_hz=GOLDEN_EMBODIMENT.control_frequency_hz,
        initial_state_envelope=InitialStateEnvelope(
            source_episode_id="episode-mujoco-001",
            configuration_digest=GOLDEN_PROMOTION_CONFIGURATION.digest(),
            reset_digest="reset-digest-001",
            first_observation_digest="first-observation-digest-001",
        ),
        artifact_digest="artifact-digest-001",
        targets=targets,
    )


def _isaac_evidence(
    candidate: CandidateBundle,
    replay: QualifiedReplay,
) -> IsaacCampaignEvidence:
    attempts = tuple(
        IsaacCampaignAttempt(
            attempt_id=f"isaac-{seed}",
            candidate_digest=candidate.digest(),
            replay_digest=replay.digest(),
            seed=seed,
            condition_id=f"condition-{seed}",
            condition_digest=f"condition-digest-{seed}",
            trajectory=IsaacLabEpisode(
                source=ISAAC_LAB_SOURCE,
                simulator_version=ISAAC_LAB_VERSION,
                scene_digest=GOLDEN_ISAAC_SCENE.digest(),
                replay_digest=replay.digest(),
                seed=seed,
                target_sequences=tuple(target.sequence for target in replay.targets),
                policy_camera_observations=(GOLDEN_ISAAC_SCENE.policy_camera_key,),
                observed_contacts=GOLDEN_ISAAC_SCENE.required_contacts,
                witness_value="closed",
                witness_age_ns=0,
                verdict=VERDICT_SUCCEEDED,
                trace_digest=f"isaac-trace-{seed}",
            ),
            verdict=ISAAC_ATTEMPT_SUCCEEDED,
            detail="Isaac contract succeeded",
        )
        for seed in (101, 102)
    )
    return IsaacCampaignEvidence(
        campaign_digest="isaac-campaign-digest",
        campaign_id="isaac-campaign-001",
        candidate_digest=candidate.digest(),
        replay_digest=replay.digest(),
        source=ISAAC_LAB_SOURCE,
        simulator_version=ISAAC_LAB_VERSION,
        scene_digest=GOLDEN_ISAAC_SCENE.digest(),
        attempts=attempts,
        recorded_at=AT,
    )


def _surface(skill: GoldenSkillRevision) -> MujocoControlSurface:
    return MujocoControlSurface(
        surface_id="mujoco-g1-control-v1",
        robot_model="unitree_g1",
        controlled_joint_count=29,
        control_frequency_hz=GOLDEN_EMBODIMENT.control_frequency_hz,
        skill_revision_digest=skill.digest(),
        observation_schema_digest=GOLDEN_PROMOTION_CONFIGURATION.observation_schema_digest,
        action_schema_digest=GOLDEN_PROMOTION_CONFIGURATION.action_protocol_digest,
    )


def _plan(
    submission: PromotionSubmission,
    replay: QualifiedReplay,
    isaac_evidence: IsaacCampaignEvidence,
) -> MujocoValidationPlan:
    candidate = submission.candidate
    skill = submission.skill
    assert candidate is not None
    assert skill is not None
    return MujocoValidationPlan(
        validation_id="mujoco-cross-check-001",
        candidate_digest=candidate.digest(),
        skill_revision_digest=skill.digest(),
        replay_digest=replay.digest(),
        isaac_evidence_digest=isaac_evidence.digest(),
        cases=tuple(
            MujocoValidationCase(
                isaac_attempt_id=attempt.attempt_id,
                seed=attempt.seed,
                fault_injected=attempt.seed == 102,
            )
            for attempt in isaac_evidence.attempts
        ),
        control_policy=MujocoControlPolicy(
            max_joint_step_rad=0.2,
            max_latency_steps=2,
            require_fault_hold=True,
        ),
        disagreement_policy=SimulatorDisagreementPolicy(max_outcome_disagreements=0),
    )


class _MujocoHost:
    @property
    def provenance(self) -> MujocoRuntimeProvenance:
        return MujocoRuntimeProvenance(
            source=MUJOCO_SOURCE,
            simulator_version=MUJOCO_VERSION,
            admission_capable=True,
        )

    def __init__(
        self,
        *,
        completed: bool = True,
        contact_anomaly: bool = False,
        fault_held: bool = True,
    ) -> None:
        self.completed = completed
        self.contact_anomaly = contact_anomaly
        self.fault_held = fault_held
        self.seen: list[tuple[int, tuple[int, ...], bool]] = []

    def run(self, surface, targets, *, seed, fault_injected):
        del surface
        sequences = tuple(target.sequence for target in targets)
        self.seen.append((seed, sequences, fault_injected))
        return MujocoRun(
            target_sequences=sequences,
            max_joint_step_rad=0.1,
            joint_boundary_violation=False,
            contact_anomaly=self.contact_anomaly,
            observed_latency_steps=1,
            fault_detected=fault_injected,
            fault_held=self.fault_held,
            completed=self.completed,
        )


class MujocoCrossValidationAcceptanceTest(unittest.TestCase):
    def test_the_control_surface_excludes_a_second_visual_scene(self) -> None:
        surface = _surface(_skill())

        self.assertEqual(surface.robot_model, "unitree_g1")
        self.assertFalse(surface.includes_visual_scene)
        self.assertEqual(surface.controlled_joint_count, 29)

    def test_the_same_frozen_targets_produce_comparable_contract_outcomes(self) -> None:
        submission = _submission()
        candidate = submission.candidate
        assert candidate is not None
        replay = _replay()
        isaac_evidence = _isaac_evidence(candidate, replay)
        isaac_ledger = IsaacCampaignEvidenceLedger()
        isaac_ledger.seal(isaac_evidence)
        host = _MujocoHost()
        ledger = MujocoEvidenceLedger()

        evidence = execute_mujoco_validation(
            _plan(submission, replay, isaac_evidence),
            candidate=candidate,
            skill_revision_digest=_skill().digest(),
            replay=replay,
            isaac_evidence=isaac_evidence,
            isaac_ledger=isaac_ledger,
            isaac_policy=IsaacGatePolicy(min_success_rate=1.0),
            adapter=MujocoAdapter(_surface(_skill()), host),
            ledger=ledger,
            now=AT,
        )

        self.assertEqual(host.seen, [(101, (1, 2), False), (102, (1, 2), True)])
        self.assertTrue(all(attempt.episode.succeeded for attempt in evidence.attempts))
        self.assertTrue(ledger.decide(evidence).admitted)

    def test_a_pre_registered_disagreement_rule_rejects_and_stops_shadow_or_hardware(
        self,
    ) -> None:
        submission = _submission()
        candidate = submission.candidate
        assert candidate is not None
        replay = _replay()
        isaac_evidence = _isaac_evidence(candidate, replay)
        isaac_ledger = IsaacCampaignEvidenceLedger()
        isaac_ledger.seal(isaac_evidence)
        later_stages: list[PromotionSubmission] = []

        result = promote_through_mujoco_gate(
            submission,
            plan=_plan(submission, replay, isaac_evidence),
            replay=replay,
            isaac_evidence=isaac_evidence,
            isaac_ledger=isaac_ledger,
            isaac_policy=IsaacGatePolicy(min_success_rate=1.0),
            adapter=MujocoAdapter(
                _surface(_skill()), _MujocoHost(contact_anomaly=True)
            ),
            evidence_ledger=MujocoEvidenceLedger(),
            promotion_ledger=PromotionLedger(),
            execute_later=later_stages.append,
            now=AT,
        )

        self.assertIsInstance(result, SealedRejection)
        assert isinstance(result, SealedRejection)
        self.assertEqual(result.failed_gate, GATE_MUJOCO)
        self.assertIn("disagree", " ".join(result.reasons).lower())
        self.assertEqual(later_stages, [])

    def test_the_registered_fault_case_must_detect_and_hold_the_fault(self) -> None:
        submission = _submission()
        candidate = submission.candidate
        assert candidate is not None
        replay = _replay()
        isaac_evidence = _isaac_evidence(candidate, replay)
        isaac_ledger = IsaacCampaignEvidenceLedger()
        isaac_ledger.seal(isaac_evidence)

        evidence = execute_mujoco_validation(
            _plan(submission, replay, isaac_evidence),
            candidate=candidate,
            skill_revision_digest=_skill().digest(),
            replay=replay,
            isaac_evidence=isaac_evidence,
            isaac_ledger=isaac_ledger,
            isaac_policy=IsaacGatePolicy(min_success_rate=1.0),
            adapter=MujocoAdapter(_surface(_skill()), _MujocoHost(fault_held=False)),
            ledger=MujocoEvidenceLedger(),
            now=AT,
        )

        self.assertFalse(evidence.attempts[1].episode.succeeded)
        self.assertIn("did not hold", " ".join(evidence.attempts[1].episode.findings))

    def test_mujoco_evidence_cannot_be_relabelled_as_isaac_or_real(self) -> None:
        with self.assertRaisesRegex(ValueError, "simulator-scoped"):
            MujocoRuntimeProvenance(
                source=ISAAC_LAB_SOURCE,
                simulator_version=MUJOCO_VERSION,
                admission_capable=True,
            )

        submission = _submission()
        candidate = submission.candidate
        assert candidate is not None
        with self.assertRaisesRegex(TypeError, "MuJoCo evidence only"):
            MujocoEvidenceLedger().seal(
                cast(MujocoValidationEvidence, _isaac_evidence(candidate, _replay()))
            )


if __name__ == "__main__":
    unittest.main()
