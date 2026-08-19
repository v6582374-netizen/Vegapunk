from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Mapping, Optional

from vegapunk.embodied.admission import (
    STAGE_HARDWARE_SUPERVISED,
    STAGE_OFFLINE_REPLAY,
    STAGE_POLICY_EVALUATION,
    STAGE_SHADOW_MODE,
    AdmissionLedger,
    EvidenceRecord,
    HumanApproval,
)
from vegapunk.embodied.embodiment import (
    ACTION_SPACE_EE_6D,
    UNIFOLM_VLA_BASE_G1_EE6D,
    EmbodimentProfile,
)
from vegapunk.embodied.loop import ExecutionLoop, RuntimeStep
from vegapunk.embodied.safety import (
    ABORT_ENVELOPE_VIOLATION,
    ABORT_HUMAN_STOP,
    ABORT_TIME_LIMIT,
    AbortDirective,
    Observation,
    SafetyEnvelope,
    SafetySupervisor,
)
from vegapunk.embodied.skill import (
    SKILL_KIND_DETERMINISTIC,
    SKILL_KIND_VLA,
    ParameterSpec,
    PhysicalSkill,
    SkillRegistry,
    SkillSelection,
)
from vegapunk.embodied.trajectory import (
    OUTCOME_ABORTED,
    OUTCOME_FAILED_VERIFICATION,
    OUTCOME_REFUSED,
    OUTCOME_SUCCEEDED,
    RunClearance,
    TrajectoryLedger,
)

_NOW = datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)

_EMBODIMENT = EmbodimentProfile(
    robot_model="unitree_g1",
    arm_dof=7,
    end_effector="dex1_1",
    camera_map={"observation.images.top": "head_rgb"},
    control_frequency_hz=30.0,
    control_authority="arm_and_gripper",
    state_dim=23,
    action_dim=23,
    onboard_image_service=True,
    action_space=ACTION_SPACE_EE_6D,
)

_ENVELOPE = SafetyEnvelope(
    max_duration_s=20.0,
    max_joint_velocity_rps=1.5,
    max_end_effector_force_n=20.0,
    workspace_bounds_m=((-0.5, 0.5), (-0.4, 0.4), (0.0, 1.2)),
    max_observation_age_s=0.2,
)

_SKILL = PhysicalSkill(
    skill_id="press_physical_button",
    revision=1,
    kind=SKILL_KIND_VLA,
    summary="Press a fixed laboratory button with the Dex1-1 gripper.",
    parameters=(ParameterSpec(name="approach_speed", minimum=0.05, maximum=0.3),),
    preconditions=("workspace_clear", "guardian_present"),
    postconditions=("button_pressed",),
    abort_conditions=("force_exceeded",),
    max_duration_s=6.0,
    reviewed_by="lab_owner",
    policy=UNIFOLM_VLA_BASE_G1_EE6D,
)

_POLICY_DIGEST = UNIFOLM_VLA_BASE_G1_EE6D.digest()


def _observation(**overrides: object) -> Observation:
    fields: dict[str, object] = {
        "elapsed_s": 0.0,
        "age_s": 0.05,
        "joint_velocity_rps": (0.0, 0.0),
        "end_effector_force_n": 1.0,
        "end_effector_position_m": (0.1, 0.0, 0.8),
        "guardian_present": True,
        "estop_engaged": False,
        "estop_reachable": True,
        "workspace_clear": True,
    }
    fields.update(overrides)
    return Observation(**fields)  # type: ignore[arg-type]


class FakeRuntime:
    """A runtime whose whole behaviour is declared up front by the test."""

    def __init__(
        self,
        steps: tuple[RuntimeStep, ...],
        postconditions: Mapping[str, bool],
        rest: Optional[Observation] = None,
        frozen_clock: bool = False,
    ) -> None:
        self._steps = list(steps)
        self._postconditions = dict(postconditions)
        self._rest = rest if rest is not None else _observation()
        self._frozen_clock = frozen_clock
        self.started_with: Optional[SkillSelection] = None
        self.aborted_with: Optional[AbortDirective] = None
        self.step_calls = 0

    def observe(self) -> Observation:
        return self._rest

    def start(self, selection: SkillSelection) -> None:
        self.started_with = selection

    def step(self) -> RuntimeStep:
        self.step_calls += 1
        if self._steps:
            return self._steps.pop(0)
        elapsed_s = 0.0 if self._frozen_clock else 0.1 * self.step_calls
        return RuntimeStep(observation=_observation(elapsed_s=elapsed_s))

    def abort(self, directive: AbortDirective) -> None:
        self.aborted_with = directive

    def postconditions(self) -> Mapping[str, bool]:
        return dict(self._postconditions)


def _successful_runtime(**kwargs: object) -> FakeRuntime:
    return FakeRuntime(
        steps=(
            RuntimeStep(observation=_observation(elapsed_s=0.5)),
            RuntimeStep(observation=_observation(elapsed_s=1.0), complete=True),
        ),
        postconditions={"button_pressed": True},
        **kwargs,  # type: ignore[arg-type]
    )


def _full_admission() -> AdmissionLedger:
    ledger = AdmissionLedger()
    for stage in (
        STAGE_POLICY_EVALUATION,
        STAGE_OFFLINE_REPLAY,
        STAGE_SHADOW_MODE,
    ):
        ledger.record(
            EvidenceRecord(
                stage=stage,
                skill_version_id=_SKILL.version_id,
                embodiment_digest=_EMBODIMENT.digest(),
                policy_digest=_POLICY_DIGEST,
                attempts=20,
                successes=20,
                safety_violations=0,
                recorded_at=_NOW - timedelta(days=1),
            )
        )
    return ledger


def _approval(**overrides: object) -> HumanApproval:
    fields: dict[str, object] = {
        "skill_version_id": _SKILL.version_id,
        "embodiment_digest": _EMBODIMENT.digest(),
        "policy_digest": _POLICY_DIGEST,
        "approver": "lab_owner",
        "approved_at": _NOW - timedelta(hours=1),
        "statement": "Workspace cleared, guardian present, e-stop verified.",
    }
    fields.update(overrides)
    return HumanApproval(**fields)  # type: ignore[arg-type]


def _harness(
    embodiment: EmbodimentProfile = _EMBODIMENT,
    admission: Optional[AdmissionLedger] = None,
    trajectories: Optional[TrajectoryLedger] = None,
) -> tuple[ExecutionLoop, SkillRegistry, TrajectoryLedger]:
    registry = SkillRegistry()
    registry.register(_SKILL)
    ledger = trajectories if trajectories is not None else TrajectoryLedger()
    loop = ExecutionLoop(
        registry=registry,
        embodiment=embodiment,
        supervisor=SafetySupervisor(_ENVELOPE),
        admission=admission if admission is not None else _full_admission(),
        trajectories=ledger,
    )
    return loop, registry, ledger


class AdmittedRunTest(unittest.TestCase):
    def test_a_fully_evidenced_approved_run_succeeds(self) -> None:
        loop, registry, trajectories = _harness()
        selection = registry.select(
            "press_physical_button", {"approach_speed": 0.1}
        )
        runtime = _successful_runtime()

        report = loop.run(
            selection=selection,
            runtime=runtime,
            run_id="r1",
            stage=STAGE_HARDWARE_SUPERVISED,
            now=_NOW,
            approval=_approval(),
        )

        self.assertTrue(report.succeeded)
        self.assertEqual(runtime.started_with, selection)
        self.assertIsNone(runtime.aborted_with)
        self.assertEqual(trajectories.get("r1").outcome, OUTCOME_SUCCEEDED)

    def test_the_trajectory_pins_the_exact_configuration_that_ran(
        self,
    ) -> None:
        loop, registry, _ = _harness()
        selection = registry.select(
            "press_physical_button", {"approach_speed": 0.1}
        )

        report = loop.run(
            selection=selection,
            runtime=_successful_runtime(),
            run_id="r1",
            stage=STAGE_HARDWARE_SUPERVISED,
            now=_NOW,
            approval=_approval(),
        )

        trajectory = report.trajectory
        self.assertEqual(trajectory.skill_version_id, _SKILL.version_id)
        self.assertEqual(trajectory.embodiment_digest, _EMBODIMENT.digest())
        self.assertEqual(trajectory.policy_digest, _POLICY_DIGEST)
        self.assertEqual(
            trajectory.selection_digest, selection.selection_digest()
        )


class RefusalTest(unittest.TestCase):
    def _refusal(self, **run_kwargs: object) -> tuple[str, ...]:
        loop, registry, _ = _harness(
            **{  # type: ignore[arg-type]
                key: value
                for key, value in run_kwargs.items()
                if key in {"embodiment", "admission", "trajectories"}
            }
        )
        selection = registry.select(
            "press_physical_button", {"approach_speed": 0.1}
        )
        report = loop.run(
            selection=selection,
            runtime=_successful_runtime(
                **(
                    {"rest": run_kwargs["rest"]}  # type: ignore[dict-item]
                    if "rest" in run_kwargs
                    else {}
                )
            ),
            run_id="r1",
            stage=run_kwargs.get("stage", STAGE_HARDWARE_SUPERVISED),  # type: ignore[arg-type]
            now=_NOW,
            approval=run_kwargs.get("approval", _approval()),  # type: ignore[arg-type]
        )
        self.assertEqual(report.outcome, OUTCOME_REFUSED)
        return report.trajectory.findings

    def test_hardware_execution_without_approval_is_refused(self) -> None:
        findings = self._refusal(approval=None)

        self.assertTrue(
            any("human approval" in finding for finding in findings)
        )

    def test_missing_stage_evidence_is_refused(self) -> None:
        findings = self._refusal(admission=AdmissionLedger())

        self.assertTrue(
            any(STAGE_SHADOW_MODE in finding for finding in findings)
        )

    def test_an_incompatible_embodiment_is_refused(self) -> None:
        findings = self._refusal(
            embodiment=EmbodimentProfile(
                robot_model="unitree_g1",
                arm_dof=7,
                end_effector="three_finger_hand",
                camera_map={"observation.images.top": "head_rgb"},
                control_frequency_hz=30.0,
                control_authority="arm_and_gripper",
                state_dim=16,
                action_dim=16,
                onboard_image_service=True,
            ),
            admission=AdmissionLedger(),
        )

        self.assertTrue(
            any("end_effector" in finding for finding in findings)
        )

    def test_a_failed_precondition_refuses_before_any_motion(self) -> None:
        loop, registry, _ = _harness()
        selection = registry.select(
            "press_physical_button", {"approach_speed": 0.1}
        )
        runtime = _successful_runtime(rest=_observation(workspace_clear=False))

        report = loop.run(
            selection=selection,
            runtime=runtime,
            run_id="r1",
            stage=STAGE_HARDWARE_SUPERVISED,
            now=_NOW,
            approval=_approval(),
        )

        self.assertEqual(report.outcome, OUTCOME_REFUSED)
        self.assertIsNone(runtime.started_with)
        self.assertTrue(
            any(
                "workspace_clear" in finding
                for finding in report.trajectory.findings
            )
        )

    def test_a_stale_contract_binding_is_refused(self) -> None:
        loop, _, _ = _harness()
        stale = SkillSelection(
            skill_version_id=_SKILL.version_id,
            contract_digest="0000000000000000",
            arguments={"approach_speed": 0.1},
        )
        runtime = _successful_runtime()

        report = loop.run(
            selection=stale,
            runtime=runtime,
            run_id="r1",
            stage=STAGE_HARDWARE_SUPERVISED,
            now=_NOW,
            approval=_approval(),
        )

        self.assertEqual(report.outcome, OUTCOME_REFUSED)
        self.assertIsNone(runtime.started_with)
        self.assertTrue(
            any(
                "contract" in finding
                for finding in report.trajectory.findings
            )
        )

    def test_a_refusal_records_every_reason_not_only_the_first(self) -> None:
        findings = self._refusal(approval=None, admission=AdmissionLedger())

        self.assertGreater(len(findings), 1)

    def test_a_refusal_leaves_a_trajectory_record(self) -> None:
        loop, registry, trajectories = _harness(admission=AdmissionLedger())
        selection = registry.select(
            "press_physical_button", {"approach_speed": 0.1}
        )

        loop.run(
            selection=selection,
            runtime=_successful_runtime(),
            run_id="r1",
            stage=STAGE_HARDWARE_SUPERVISED,
            now=_NOW,
            approval=_approval(),
        )

        self.assertEqual(trajectories.get("r1").outcome, OUTCOME_REFUSED)


class AbortAuthorityTest(unittest.TestCase):
    def _run_with_steps(
        self, steps: tuple[RuntimeStep, ...]
    ) -> tuple[object, FakeRuntime]:
        loop, registry, _ = _harness()
        selection = registry.select(
            "press_physical_button", {"approach_speed": 0.1}
        )
        runtime = FakeRuntime(
            steps=steps, postconditions={"button_pressed": True}
        )
        report = loop.run(
            selection=selection,
            runtime=runtime,
            run_id="r1",
            stage=STAGE_HARDWARE_SUPERVISED,
            now=_NOW,
            approval=_approval(),
        )
        return report, runtime

    def test_a_human_stop_mid_run_aborts_and_is_obeyed(self) -> None:
        report, runtime = self._run_with_steps(
            (
                RuntimeStep(observation=_observation(elapsed_s=0.5)),
                RuntimeStep(
                    observation=_observation(elapsed_s=1.0, estop_engaged=True)
                ),
                RuntimeStep(
                    observation=_observation(elapsed_s=1.5), complete=True
                ),
            )
        )

        self.assertEqual(report.outcome, OUTCOME_ABORTED)
        self.assertEqual(report.trajectory.abort_cause, ABORT_HUMAN_STOP)
        self.assertIsNotNone(runtime.aborted_with)
        self.assertEqual(runtime.step_calls, 2)

    def test_an_envelope_violation_aborts_before_advancing_again(self) -> None:
        report, runtime = self._run_with_steps(
            (
                RuntimeStep(
                    observation=_observation(
                        elapsed_s=0.5, end_effector_force_n=50.0
                    )
                ),
                RuntimeStep(
                    observation=_observation(elapsed_s=1.0), complete=True
                ),
            )
        )

        self.assertEqual(
            report.trajectory.abort_cause, ABORT_ENVELOPE_VIOLATION
        )
        self.assertEqual(runtime.step_calls, 1)

    def test_the_skill_duration_tightens_the_envelope_for_this_run(
        self,
    ) -> None:
        report, _ = self._run_with_steps(
            (
                RuntimeStep(observation=_observation(elapsed_s=7.0)),
                RuntimeStep(
                    observation=_observation(elapsed_s=7.5), complete=True
                ),
            )
        )

        self.assertEqual(report.outcome, OUTCOME_ABORTED)
        self.assertEqual(report.trajectory.abort_cause, ABORT_TIME_LIMIT)

    def test_an_abort_outranks_a_runtime_claiming_it_finished(self) -> None:
        """A violation in the same step as a completion claim still aborts.

        Otherwise a runtime could launder any violation by reporting the
        motion as done in the same breath.
        """
        report, runtime = self._run_with_steps(
            (
                RuntimeStep(
                    observation=_observation(
                        elapsed_s=1.0, estop_engaged=True
                    ),
                    complete=True,
                ),
            )
        )

        self.assertEqual(report.outcome, OUTCOME_ABORTED)
        self.assertEqual(report.trajectory.abort_cause, ABORT_HUMAN_STOP)
        self.assertIsNotNone(runtime.aborted_with)

    def test_a_stuck_runtime_clock_cannot_extend_a_run_forever(self) -> None:
        """The loop bounds motion even when the runtime's clock lies.

        Every supervisor time check reads ``elapsed_s`` from the runtime, so a
        frozen clock defeats all of them. The loop's own control-step budget is
        the only thing left, which is why it exists.
        """
        loop, registry, _ = _harness()
        selection = registry.select(
            "press_physical_button", {"approach_speed": 0.1}
        )
        runtime = FakeRuntime(
            steps=(),
            postconditions={"button_pressed": True},
            frozen_clock=True,
        )

        report = loop.run(
            selection=selection,
            runtime=runtime,
            run_id="r1",
            stage=STAGE_HARDWARE_SUPERVISED,
            now=_NOW,
            approval=_approval(),
        )

        self.assertEqual(report.outcome, OUTCOME_ABORTED)
        self.assertEqual(report.trajectory.abort_cause, ABORT_TIME_LIMIT)
        self.assertIsNotNone(runtime.aborted_with)
        self.assertLessEqual(runtime.step_calls, int(6.0 * 30.0 * 2))
        self.assertIn("control-step budget", report.trajectory.detail)


class VerificationTest(unittest.TestCase):
    def _verify(self, postconditions: Mapping[str, bool]) -> object:
        loop, registry, _ = _harness()
        selection = registry.select(
            "press_physical_button", {"approach_speed": 0.1}
        )
        runtime = FakeRuntime(
            steps=(
                RuntimeStep(
                    observation=_observation(elapsed_s=1.0), complete=True
                ),
            ),
            postconditions=postconditions,
        )
        return loop.run(
            selection=selection,
            runtime=runtime,
            run_id="r1",
            stage=STAGE_HARDWARE_SUPERVISED,
            now=_NOW,
            approval=_approval(),
        )

    def test_an_unmet_postcondition_is_a_failed_verification(self) -> None:
        report = self._verify({"button_pressed": False})

        self.assertEqual(report.outcome, OUTCOME_FAILED_VERIFICATION)  # type: ignore[attr-defined]

    def test_an_unmeasured_postcondition_cannot_pass_as_success(self) -> None:
        report = self._verify({})

        self.assertEqual(report.outcome, OUTCOME_FAILED_VERIFICATION)  # type: ignore[attr-defined]
        self.assertTrue(
            any(
                "not measured" in finding
                for finding in report.trajectory.findings  # type: ignore[attr-defined]
            )
        )

    def test_a_failed_verification_is_not_a_hard_failure(self) -> None:
        report = self._verify({"button_pressed": False})

        self.assertFalse(report.trajectory.is_hard_failure)  # type: ignore[attr-defined]


class QuarantineEnforcementTest(unittest.TestCase):
    def _abort_then_retry(
        self, clearance: Optional[RunClearance] = None
    ) -> object:
        trajectories = TrajectoryLedger()
        loop, registry, _ = _harness(trajectories=trajectories)
        selection = registry.select(
            "press_physical_button", {"approach_speed": 0.1}
        )

        loop.run(
            selection=selection,
            runtime=FakeRuntime(
                steps=(
                    RuntimeStep(
                        observation=_observation(
                            elapsed_s=0.5, end_effector_force_n=50.0
                        )
                    ),
                ),
                postconditions={"button_pressed": True},
            ),
            run_id="r1",
            stage=STAGE_HARDWARE_SUPERVISED,
            now=_NOW,
            approval=_approval(),
        )

        if clearance is not None:
            trajectories.clear(clearance)

        return loop.run(
            selection=selection,
            runtime=_successful_runtime(),
            run_id="r2",
            stage=STAGE_HARDWARE_SUPERVISED,
            now=_NOW + timedelta(minutes=1),
            approval=_approval(),
        )

    def test_an_abort_blocks_the_next_attempt_on_that_configuration(
        self,
    ) -> None:
        report = self._abort_then_retry()

        self.assertEqual(report.outcome, OUTCOME_REFUSED)  # type: ignore[attr-defined]
        self.assertTrue(
            any(
                "clearance" in finding
                for finding in report.trajectory.findings  # type: ignore[attr-defined]
            )
        )

    def test_a_human_clearance_allows_the_next_attempt(self) -> None:
        report = self._abort_then_retry(
            clearance=RunClearance(
                run_id="r1",
                reviewer="lab_owner",
                statement="Force limit re-tuned; validation re-run in shadow.",
                cleared_at=_NOW + timedelta(seconds=30),
            )
        )

        self.assertEqual(report.outcome, OUTCOME_SUCCEEDED)  # type: ignore[attr-defined]


class DeterministicSkillTest(unittest.TestCase):
    def test_a_deterministic_skill_runs_without_a_policy(self) -> None:
        skill = PhysicalSkill(
            skill_id="home_arm",
            revision=1,
            kind=SKILL_KIND_DETERMINISTIC,
            summary="Return the arm to its home pose.",
            parameters=(),
            preconditions=("workspace_clear",),
            postconditions=("at_home_pose",),
            abort_conditions=("force_exceeded",),
            max_duration_s=5.0,
            reviewed_by="lab_owner",
        )
        registry = SkillRegistry()
        registry.register(skill)
        admission = AdmissionLedger()
        for stage in (
            STAGE_POLICY_EVALUATION,
            STAGE_OFFLINE_REPLAY,
            STAGE_SHADOW_MODE,
        ):
            admission.record(
                EvidenceRecord(
                    stage=stage,
                    skill_version_id=skill.version_id,
                    embodiment_digest=_EMBODIMENT.digest(),
                    policy_digest=None,
                    attempts=20,
                    successes=20,
                    safety_violations=0,
                    recorded_at=_NOW - timedelta(days=1),
                )
            )
        loop = ExecutionLoop(
            registry=registry,
            embodiment=_EMBODIMENT,
            supervisor=SafetySupervisor(_ENVELOPE),
            admission=admission,
            trajectories=TrajectoryLedger(),
        )

        report = loop.run(
            selection=registry.select("home_arm", {}),
            runtime=FakeRuntime(
                steps=(
                    RuntimeStep(
                        observation=_observation(elapsed_s=1.0), complete=True
                    ),
                ),
                postconditions={"at_home_pose": True},
            ),
            run_id="r1",
            stage=STAGE_HARDWARE_SUPERVISED,
            now=_NOW,
            approval=_approval(
                skill_version_id=skill.version_id, policy_digest=None
            ),
        )

        self.assertTrue(report.succeeded)
        self.assertIsNone(report.trajectory.policy_digest)


if __name__ == "__main__":
    unittest.main()
