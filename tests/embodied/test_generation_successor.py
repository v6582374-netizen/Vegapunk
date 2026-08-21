from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from vegapunk.embodied.act_candidate import (
    ACTPolicyEngineer,
    ACTTrainer,
    ACTTrainingRecipe,
    EndToEndACTCandidate,
    EpisodeSplit,
)
from vegapunk.embodied.embodiment import EmbodimentProfile
from vegapunk.embodied.episode import (
    EpisodeTrainingManifest,
    TimeSynchronization,
    TrainingEpisode,
)
from vegapunk.embodied.generation_next import (
    CONTROL_ACTION_PROTOCOL,
    CONTROL_SAFETY_ENVELOPE,
    CONTROL_SKILL,
    GATE_CONTRACT_VALIDATION,
    GATE_OFFLINE_REPLAY,
    GenerationApprovalLedger,
    GenerationSuccessor,
    HumanGenerationApproval,
)
from vegapunk.embodied.generation_result import (
    CHANGE_TRAINING,
    FAILURE_POLICY_CAPACITY,
    SOURCE_HARDWARE_PILOT,
    SOURCE_ISAAC_LAB,
    SOURCE_MUJOCO,
    SOURCE_OBSERVATION_SHADOW,
    SOURCE_QUALIFIED_REPLAY,
    BoundedChange,
    BoundedWorkOrder,
    GateEvidenceReference,
    GenerationResultLedger,
    SealedGenerationResult,
)
from vegapunk.embodied.promotion import (
    GOLDEN_EMBODIMENT,
    GOLDEN_INSTRUMENT_OPERATION_LOOP,
    GOLDEN_PROMOTION_CONFIGURATION,
    GOLDEN_SKILL_ID,
    GoldenSkillRevision,
    PromotionConfiguration,
)
from vegapunk.embodied.skill import SKILL_KIND_DETERMINISTIC, PhysicalSkill
from vegapunk.operation.episode import (
    TERMINATION_COMPLETED,
    TRANSFER_FULL,
    CameraCalibration,
    EpisodeOutcome,
    EpisodeRecord,
    Frame,
    HumanTestimony,
    ResetRecord,
)
from vegapunk.operation.target import HAND_OPEN, STAND_BODY, WholeBodyTarget
from vegapunk.operation.tracker import TrackerState
from vegapunk.operation.witness import LID_CLOSED

AT = datetime(2026, 8, 21, 20, 0, tzinfo=timezone.utc)
NOW = 5_000_000_000


class _TestHumanApprovalAuthority:
    def proof_for(
        self, *, order_id: str, candidate_digest: str, approved_by: str
    ) -> str:
        return f"reviewed:{order_id}:{candidate_digest}:{approved_by}"

    def verifies(self, approval: HumanGenerationApproval) -> bool:
        return approval.approval_proof == self.proof_for(
            order_id=approval.work_order_id,
            candidate_digest=approval.candidate_digest,
            approved_by=approval.approved_by,
        )


def _skill(*, revision: int = 1) -> GoldenSkillRevision:
    return GoldenSkillRevision(
        skill=PhysicalSkill(
            skill_id=GOLDEN_SKILL_ID,
            revision=revision,
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


def _episode(
    episode_id: str,
    *,
    skill: GoldenSkillRevision,
    embodiment: EmbodimentProfile,
    configuration: PromotionConfiguration,
) -> TrainingEpisode:
    target = WholeBodyTarget(
        sequence=1,
        source_time_ns=NOW,
        valid_until_ns=NOW + 100_000_000,
        body=STAND_BODY,
        left_hand=HAND_OPEN,
        right_hand=HAND_OPEN,
    )
    return TrainingEpisode(
        record=EpisodeRecord(
            episode_id=episode_id,
            configuration_digest=configuration.digest(),
            started_at=AT,
            cameras=(CameraCalibration("head", 640, 480, 30.0, "torso"),),
            witness_identity="lid-limit-switch",
            reset=ResetRecord("bench_operator", AT, True, True, True),
            frame_count=1,
            outcome=EpisodeOutcome(
                transfer=TRANSFER_FULL,
                judged_by="outcome_judge",
                judged_at=AT,
                lid_closed_at_end=True,
                termination=TERMINATION_COMPLETED,
            ),
            testimony=(
                HumanTestimony("bench_operator", AT, "cup returned to the bench"),
            ),
            operator="campaign_operator",
        ),
        skill=skill,
        embodiment=embodiment,
        configuration=configuration,
        synchronization=TimeSynchronization(
            "ptp-bench-001",
            AT,
            "camera-ptp",
            "target-bridge-monotonic",
            "lid-switch-monotonic",
            2_000_000,
        ),
        frames=(
            Frame(
                index=0,
                time_ns=NOW,
                images={"head": "head/00000.jpg"},
                state=TrackerState(
                    sequence=1,
                    state_time_ns=NOW,
                    body=(0.0,) * 34,
                    left_hand=HAND_OPEN,
                    right_hand=HAND_OPEN,
                    applied_target_sequence=1,
                ),
                target=target,
                lid=LID_CLOSED,
                monitor_decision="pass",
            ),
        ),
    )


def _act_candidate(
    candidate_id: str,
    *,
    skill: GoldenSkillRevision | None = None,
    embodiment: EmbodimentProfile = GOLDEN_EMBODIMENT,
    configuration: PromotionConfiguration = GOLDEN_PROMOTION_CONFIGURATION,
) -> EndToEndACTCandidate:
    skill = _skill() if skill is None else skill
    train, validation, held_out = (
        _episode(
            "episode-train",
            skill=skill,
            embodiment=embodiment,
            configuration=configuration,
        ),
        _episode(
            "episode-validation",
            skill=skill,
            embodiment=embodiment,
            configuration=configuration,
        ),
        _episode(
            "episode-held-out",
            skill=skill,
            embodiment=embodiment,
            configuration=configuration,
        ),
    )
    manifest = EpisodeTrainingManifest((train, validation, held_out))
    recipe = ACTTrainingRecipe(
        "act-golden-v1",
        2,
        1,
        50.0,
        configuration.observation_schema_digest,
        configuration.action_protocol_digest,
    )
    split = EpisodeSplit(
        (train.record.episode_id,),
        (validation.record.episode_id,),
        (held_out.record.episode_id,),
    )
    trainer = ACTTrainer()
    checkpoint = trainer.fit(manifest, split, recipe, candidate_id)
    output = trainer.evaluate(
        checkpoint,
        (held_out,),
        recipe,
        {held_out.record.episode_id: 12.5},
    )
    return ACTPolicyEngineer().package(manifest, split, recipe, output)


def _result(candidate: EndToEndACTCandidate) -> SealedGenerationResult:
    digest = candidate.bundle.digest()
    return SealedGenerationResult(
        generation_id="generation-001",
        candidate=candidate.bundle,
        gate_evidence=(
            GateEvidenceReference("offline_replay", SOURCE_QUALIFIED_REPLAY, "replay-001", digest),
            GateEvidenceReference("isaac_lab", SOURCE_ISAAC_LAB, "isaac-001", digest),
            GateEvidenceReference("mujoco", SOURCE_MUJOCO, "mujoco-001", digest),
            GateEvidenceReference(
                "observation_shadow", SOURCE_OBSERVATION_SHADOW, "shadow-001", digest
            ),
            GateEvidenceReference(
                "hardware_pilot", SOURCE_HARDWARE_PILOT, "pilot-001", digest
            ),
        ),
        sealed_at=AT,
    )


def _order(
    result: SealedGenerationResult,
    *,
    order_id: str = "order-001",
    changed_variable: str = "ACT context window",
    unchanged_controls: tuple[str, ...] = (
        CONTROL_SKILL,
        CONTROL_ACTION_PROTOCOL,
        CONTROL_SAFETY_ENVELOPE,
    ),
) -> BoundedWorkOrder:
    return BoundedWorkOrder(
        order_id=order_id,
        result_digest=result.digest(),
        failure_class=FAILURE_POLICY_CAPACITY,
        change=BoundedChange(
            kind=CHANGE_TRAINING,
            target=changed_variable,
            proposal="Increase from 16 to 32 frames.",
            bound="No more than 32 frames.",
        ),
        evidence_basis=(result.gate_evidence[-2], result.gate_evidence[-1]),
        unchanged_controls=unchanged_controls,
        next_required_gate="offline_replay",
        proposed_at=AT + timedelta(seconds=1),
    )


def _sealed_order(
    ledger: GenerationResultLedger,
    result: SealedGenerationResult,
    *,
    order_id: str = "order-001",
    changed_variable: str = "ACT context window",
    unchanged_controls: tuple[str, ...] = (
        CONTROL_SKILL,
        CONTROL_ACTION_PROTOCOL,
        CONTROL_SAFETY_ENVELOPE,
    ),
) -> BoundedWorkOrder:
    for evidence in result.gate_evidence:
        ledger.record_gate_evidence(evidence)
    ledger.seal(result)
    order = _order(
        result,
        order_id=order_id,
        changed_variable=changed_variable,
        unchanged_controls=unchanged_controls,
    )
    return ledger.propose(order)


class GenerationSuccessorAcceptanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parent = _act_candidate("act-candidate-001")
        self.next = _act_candidate("act-candidate-002")
        self.result = _result(self.parent)
        self.ledger = GenerationResultLedger()
        self.order = _sealed_order(self.ledger, self.result)
        self.approvals = GenerationApprovalLedger()
        self.authority = _TestHumanApprovalAuthority()
        self.successor = GenerationSuccessor(self.authority)

    def _approval(
        self,
        candidate: EndToEndACTCandidate | None = None,
        *,
        order: BoundedWorkOrder | None = None,
        approvals: GenerationApprovalLedger | None = None,
    ) -> HumanGenerationApproval:
        approved = self.next if candidate is None else candidate
        approved_order = self.order if order is None else order
        approval_ledger = self.approvals if approvals is None else approvals
        approval = HumanGenerationApproval(
            work_order_id=approved_order.order_id,
            candidate_digest=approved.bundle.digest(),
            approved_by="skill_owner",
            approved_at=AT + timedelta(seconds=2),
            approval_proof=self.authority.proof_for(
                order_id=approved_order.order_id,
                candidate_digest=approved.bundle.digest(),
                approved_by="skill_owner",
            ),
        )
        return approval_ledger.record(approval)

    def test_named_human_creates_n_plus_one_from_a_sealed_order_and_act_candidate(self) -> None:
        next_generation = self.successor.create_next(
            generation_id="generation-002",
            ledger=self.ledger,
            approval_ledger=self.approvals,
            source_configuration=GOLDEN_PROMOTION_CONFIGURATION,
            configuration=GOLDEN_PROMOTION_CONFIGURATION,
            work_order=self.order,
            candidate=self.next,
            approval=self._approval(),
        )

        self.assertEqual(next_generation.source_generation_id, self.result.generation_id)
        self.assertEqual(next_generation.work_order, self.order)
        self.assertEqual(next_generation.changed_variable, "ACT context window")
        self.assertEqual(next_generation.unchanged_controls, self.order.unchanged_controls)
        self.assertEqual(next_generation.changed_critical_identities, ("policy",))
        self.assertEqual(next_generation.invalidated_gate_evidence, self.result.gate_evidence)
        self.assertEqual(next_generation.entry_gates, (GATE_CONTRACT_VALIDATION, GATE_OFFLINE_REPLAY))
        self.assertFalse(hasattr(next_generation, "hardware_authority"))
        self.assertIs(self.ledger.result_for(self.result.digest()), self.result)
        self.assertIs(self.ledger.work_order_for(self.order.order_id), self.order)

    def test_unapproved_order_or_mismatched_candidate_cannot_create_n_plus_one(self) -> None:
        successor = self.successor
        with self.assertRaisesRegex(ValueError, "human approval"):
            successor.create_next(
                generation_id="generation-002",
                ledger=self.ledger,
                approval_ledger=self.approvals,
                source_configuration=GOLDEN_PROMOTION_CONFIGURATION,
                configuration=GOLDEN_PROMOTION_CONFIGURATION,
                work_order=self.order,
                candidate=self.next,
                approval=replace(self._approval(), candidate_digest="other-candidate"),
            )
        with self.assertRaisesRegex(ValueError, "sealed Work Order"):
            successor.create_next(
                generation_id="generation-002",
                ledger=GenerationResultLedger(),
                approval_ledger=self.approvals,
                source_configuration=GOLDEN_PROMOTION_CONFIGURATION,
                configuration=GOLDEN_PROMOTION_CONFIGURATION,
                work_order=self.order,
                candidate=self.next,
                approval=self._approval(),
            )
        with self.assertRaisesRegex(ValueError, "recorded human approval"):
            successor.create_next(
                generation_id="generation-002",
                ledger=self.ledger,
                approval_ledger=self.approvals,
                source_configuration=GOLDEN_PROMOTION_CONFIGURATION,
                configuration=GOLDEN_PROMOTION_CONFIGURATION,
                work_order=self.order,
                candidate=self.next,
                approval=replace(
                    self._approval(), approved_at=AT + timedelta(seconds=3)
                ),
            )
        with self.assertRaisesRegex(ValueError, "verified human approval"):
            unverified_ledger = GenerationApprovalLedger()
            unverified_approval = replace(self._approval(), approval_proof="not-human")
            unverified_ledger.record(unverified_approval)
            successor.create_next(
                generation_id="generation-002",
                ledger=self.ledger,
                approval_ledger=unverified_ledger,
                source_configuration=GOLDEN_PROMOTION_CONFIGURATION,
                configuration=GOLDEN_PROMOTION_CONFIGURATION,
                work_order=self.order,
                candidate=self.next,
                approval=unverified_approval,
            )
        with self.assertRaisesRegex(ValueError, "configuration"):
            mismatched_configuration = replace(
                GOLDEN_PROMOTION_CONFIGURATION,
                configuration_id="golden-bench-mismatch-v2",
            )
            successor.create_next(
                generation_id="generation-002",
                ledger=self.ledger,
                approval_ledger=self.approvals,
                source_configuration=GOLDEN_PROMOTION_CONFIGURATION,
                configuration=mismatched_configuration,
                work_order=self.order,
                candidate=self.next,
                approval=self._approval(),
            )
        with self.assertRaisesRegex(ValueError, "sealed bundle"):
            replace(
                self.next,
                bundle=replace(self.next.bundle, policy_artifact_digest="other-policy"),
            )

    def test_every_critical_identity_change_invalidates_prior_gate_evidence(self) -> None:
        skill_candidate = _act_candidate(
            "act-candidate-skill", skill=_skill(revision=2)
        )
        with self.assertRaisesRegex(ValueError, "changed controls unchanged"):
            self.successor.create_next(
                generation_id="generation-002-skill",
                ledger=self.ledger,
                approval_ledger=self.approvals,
                source_configuration=GOLDEN_PROMOTION_CONFIGURATION,
                configuration=GOLDEN_PROMOTION_CONFIGURATION,
                work_order=self.order,
                candidate=skill_candidate,
                approval=self._approval(skill_candidate),
            )
        changed_configurations = (
            (
                "policy",
                self.next,
                GOLDEN_PROMOTION_CONFIGURATION,
                (CONTROL_SKILL, CONTROL_ACTION_PROTOCOL, CONTROL_SAFETY_ENVELOPE),
            ),
            (
                "skill",
                skill_candidate,
                GOLDEN_PROMOTION_CONFIGURATION,
                (CONTROL_ACTION_PROTOCOL, CONTROL_SAFETY_ENVELOPE),
            ),
            (
                "independent_witness",
                _act_candidate(
                    "act-candidate-witness",
                    configuration=replace(
                        GOLDEN_PROMOTION_CONFIGURATION,
                        configuration_id="golden-bench-witness-v2",
                        independent_witness_digest="lid-and-volume-witness-v2",
                    ),
                ),
                replace(
                    GOLDEN_PROMOTION_CONFIGURATION,
                    configuration_id="golden-bench-witness-v2",
                    independent_witness_digest="lid-and-volume-witness-v2",
                ),
                (CONTROL_SKILL, CONTROL_ACTION_PROTOCOL, CONTROL_SAFETY_ENVELOPE),
            ),
            (
                "action_protocol",
                _act_candidate(
                    "act-candidate-action",
                    configuration=replace(
                        GOLDEN_PROMOTION_CONFIGURATION,
                        configuration_id="golden-bench-action-v2",
                        action_protocol_digest="joint-whole-body-target-v2",
                    ),
                ),
                replace(
                    GOLDEN_PROMOTION_CONFIGURATION,
                    configuration_id="golden-bench-action-v2",
                    action_protocol_digest="joint-whole-body-target-v2",
                ),
                (CONTROL_SKILL, CONTROL_SAFETY_ENVELOPE),
            ),
            (
                "embodiment",
                _act_candidate(
                    "act-candidate-embodiment",
                    embodiment=replace(GOLDEN_EMBODIMENT, control_frequency_hz=25.0),
                    configuration=replace(
                        GOLDEN_PROMOTION_CONFIGURATION,
                        configuration_id="golden-bench-embodiment-v2",
                        embodiment_digest=replace(
                            GOLDEN_EMBODIMENT, control_frequency_hz=25.0
                        ).digest(),
                    ),
                ),
                replace(
                    GOLDEN_PROMOTION_CONFIGURATION,
                    configuration_id="golden-bench-embodiment-v2",
                    embodiment_digest=replace(
                        GOLDEN_EMBODIMENT, control_frequency_hz=25.0
                    ).digest(),
                ),
                (CONTROL_SKILL, CONTROL_ACTION_PROTOCOL, CONTROL_SAFETY_ENVELOPE),
            ),
            (
                "critical_calibration",
                _act_candidate(
                    "act-candidate-calibration",
                    configuration=replace(
                        GOLDEN_PROMOTION_CONFIGURATION,
                        configuration_id="golden-bench-calibration-v2",
                        calibration_digest="golden-bench-calibration-v2",
                    ),
                ),
                replace(
                    GOLDEN_PROMOTION_CONFIGURATION,
                    configuration_id="golden-bench-calibration-v2",
                    calibration_digest="golden-bench-calibration-v2",
                ),
                (CONTROL_SKILL, CONTROL_ACTION_PROTOCOL, CONTROL_SAFETY_ENVELOPE),
            ),
        )

        for identity, candidate, configuration, unchanged_controls in changed_configurations:
            with self.subTest(identity=identity):
                ledger = GenerationResultLedger()
                order = _sealed_order(
                    ledger,
                    self.result,
                    order_id=f"order-{identity}",
                    changed_variable=identity,
                    unchanged_controls=unchanged_controls,
                )
                approvals = GenerationApprovalLedger()
                next_generation = self.successor.create_next(
                    generation_id=f"generation-002-{identity}",
                    ledger=ledger,
                    approval_ledger=approvals,
                    source_configuration=GOLDEN_PROMOTION_CONFIGURATION,
                    configuration=configuration,
                    work_order=order,
                    candidate=candidate,
                    approval=self._approval(candidate, order=order, approvals=approvals),
                )

                self.assertIn(identity, next_generation.changed_critical_identities)
                self.assertEqual(
                    next_generation.invalidated_gate_evidence, self.result.gate_evidence
                )
                self.assertEqual(next_generation.entry_gates, (GATE_CONTRACT_VALIDATION, GATE_OFFLINE_REPLAY))


if __name__ == "__main__":
    unittest.main()
