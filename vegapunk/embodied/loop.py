"""The governed execution loop: the only path from a selection to motion.

Every other module in this profile states a rule. This one is the single place
those rules are applied, in a fixed order, with no way around them:

``quarantine`` -> ``compatibility`` -> ``admission`` -> ``preflight`` ->
``supervised motion`` -> ``postcondition verification`` -> ``trajectory``

The order is the design. Cheap, deterministic refusals come first so that a
configuration which can never be admitted is rejected before a person is asked
to stand next to a moving robot. Human approval is checked before preflight
because approval is about the configuration, while preflight is about this
moment.

The loop never decides safety itself. It asks the ``SafetySupervisor`` after
every single observation and obeys the first directive it gets; motion cannot
continue through an unanswered check because the check happens before the next
advance, not after it. Equally, the loop never decides success: a postcondition
the runtime cannot report is a failed verification, not a pass, so a blind
sensor cannot be mistaken for a working skill.

Every exit writes exactly one trajectory record, including a refusal. A run
that was prevented is information about the system and is kept.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Optional, Protocol

from vegapunk.embodied.admission import (
    AdmissionLedger,
    HumanApproval,
    evaluate_admission,
)
from vegapunk.embodied.embodiment import (
    EmbodimentProfile,
    assess_policy_compatibility,
)
from vegapunk.embodied.safety import (
    ABORT_TIME_LIMIT,
    AbortDirective,
    Observation,
    SafetySupervisor,
)
from vegapunk.embodied.skill import SkillRegistry, SkillSelection
from vegapunk.embodied.trajectory import (
    OUTCOME_ABORTED,
    OUTCOME_FAILED_VERIFICATION,
    OUTCOME_REFUSED,
    OUTCOME_SUCCEEDED,
    TrajectoryLedger,
    TrajectoryRecord,
)

_STEP_BUDGET_MARGIN = 2.0


@dataclass(frozen=True)
class RuntimeStep:
    """One observation from the runtime, and whether the motion is finished.

    ``complete`` is the runtime's claim that the macro action ran to its
    designed end. It is a claim about motion only; whether the action worked is
    decided afterwards from postconditions.
    """

    observation: Observation
    complete: bool = False


class SkillRuntime(Protocol):
    """The actuation boundary: whatever actually moves the robot.

    A deterministic controller and a VLA policy runner both sit behind this
    protocol, which is why the loop's guarantees do not depend on which one is
    in use. Implementations are expected to be honest and unclever: report the
    observation, report completion, stop when told.
    """

    def observe(self) -> Observation:
        """Report the current state without commanding any motion.

        Preflight needs to look before anything moves, so observing is a
        separate capability from advancing.
        """

    def start(self, selection: SkillSelection) -> None:
        """Begin the bound macro action."""

    def step(self) -> RuntimeStep:
        """Advance one control step and report the resulting observation."""

    def abort(self, directive: AbortDirective) -> None:
        """Stop immediately because the supervisor said so."""

    def postconditions(self) -> Mapping[str, bool]:
        """Report the measured truth of each declared postcondition."""


@dataclass(frozen=True)
class RunReport:
    """What one governed attempt did, and the record it left behind."""

    trajectory: TrajectoryRecord
    abort: Optional[AbortDirective] = None

    @property
    def outcome(self) -> str:
        return self.trajectory.outcome

    @property
    def succeeded(self) -> bool:
        return self.trajectory.outcome == OUTCOME_SUCCEEDED


class ExecutionLoop:
    """Runs registered skills under supervision, and records what happened."""

    def __init__(
        self,
        registry: SkillRegistry,
        embodiment: EmbodimentProfile,
        supervisor: SafetySupervisor,
        admission: AdmissionLedger,
        trajectories: TrajectoryLedger,
    ) -> None:
        self._registry = registry
        self._embodiment = embodiment
        self._supervisor = supervisor
        self._admission = admission
        self._trajectories = trajectories

    def run(
        self,
        selection: SkillSelection,
        runtime: SkillRuntime,
        run_id: str,
        stage: str,
        now: datetime,
        approval: Optional[HumanApproval] = None,
    ) -> RunReport:
        """Execute one selection at one stage, or refuse it and say why."""
        skill_id, _, revision = selection.skill_version_id.rpartition("@")
        skill = self._registry.get(skill_id, int(revision))

        if skill.contract_digest() != selection.contract_digest:
            return self._refuse(
                selection,
                run_id,
                stage,
                now,
                None,
                (
                    "the selection was bound to a different contract than the "
                    "registered skill revision; re-bind against the current "
                    "contract",
                ),
            )

        policy_digest = None if skill.policy is None else skill.policy.digest()
        scope = (
            selection.skill_version_id,
            self._embodiment.digest(),
            policy_digest,
        )

        findings: list[str] = []

        quarantine = self._trajectories.quarantine(scope)
        if quarantine is not None:
            findings.append(quarantine)

        compatibility = assess_policy_compatibility(
            self._embodiment, skill.policy
        )
        findings.extend(compatibility.findings)

        decision = evaluate_admission(
            ledger=self._admission,
            skill_version_id=selection.skill_version_id,
            embodiment_digest=self._embodiment.digest(),
            policy_digest=policy_digest,
            target_stage=stage,
            approval=approval,
            now=now,
        )
        findings.extend(decision.blocking_reasons)

        if findings:
            return self._refuse(
                selection, run_id, stage, now, policy_digest, tuple(findings)
            )

        supervisor = self._supervisor.with_advice(
            {
                "max_duration_s": min(
                    self._supervisor.envelope.max_duration_s,
                    skill.max_duration_s,
                )
            }
        )

        preflight = supervisor.preflight(
            runtime.observe(), skill.preconditions
        )
        if not preflight.passed:
            return self._refuse(
                selection,
                run_id,
                stage,
                now,
                policy_digest,
                preflight.failures,
            )

        return self._execute(
            selection=selection,
            runtime=runtime,
            supervisor=supervisor,
            run_id=run_id,
            stage=stage,
            now=now,
            policy_digest=policy_digest,
            postconditions=skill.postconditions,
            step_budget=self._step_budget(supervisor.envelope.max_duration_s),
        )

    def _step_budget(self, max_duration_s: float) -> int:
        """Bound the loop independently of the runtime's own reporting.

        The supervisor's time limit relies on the runtime reporting elapsed
        time honestly. A runtime whose clock is stuck would otherwise spin
        forever, so the loop derives its own control-step ceiling from the
        embodiment's declared frequency.
        """
        steps = max_duration_s * self._embodiment.control_frequency_hz
        return max(1, int(steps * _STEP_BUDGET_MARGIN))

    def _execute(
        self,
        selection: SkillSelection,
        runtime: SkillRuntime,
        supervisor: SafetySupervisor,
        run_id: str,
        stage: str,
        now: datetime,
        policy_digest: Optional[str],
        postconditions: tuple[str, ...],
        step_budget: int,
    ) -> RunReport:
        runtime.start(selection)

        observations = 0
        duration_s = 0.0
        complete = False

        while observations < step_budget:
            step = runtime.step()
            observations += 1
            duration_s = step.observation.elapsed_s

            directive = supervisor.evaluate(step.observation)
            if directive is not None:
                runtime.abort(directive)
                return self._record(
                    RunReport(
                        trajectory=TrajectoryRecord(
                            run_id=run_id,
                            stage=stage,
                            skill_version_id=selection.skill_version_id,
                            contract_digest=selection.contract_digest,
                            selection_digest=selection.selection_digest(),
                            embodiment_digest=self._embodiment.digest(),
                            policy_digest=policy_digest,
                            outcome=OUTCOME_ABORTED,
                            started_at=now,
                            observations=observations,
                            duration_s=duration_s,
                            abort_cause=directive.cause,
                            detail=directive.detail,
                            stream_complete=False,
                            embodiment_verified=self._embodiment.fully_verified,
                        ),
                        abort=directive,
                    )
                )

            if step.complete:
                complete = True
                break

        if not complete:
            directive = AbortDirective(
                cause=ABORT_TIME_LIMIT,
                detail=(
                    f"the runtime did not complete within its {step_budget} "
                    "control-step budget"
                ),
            )
            runtime.abort(directive)
            return self._record(
                RunReport(
                    trajectory=TrajectoryRecord(
                        run_id=run_id,
                        stage=stage,
                        skill_version_id=selection.skill_version_id,
                        contract_digest=selection.contract_digest,
                        selection_digest=selection.selection_digest(),
                        embodiment_digest=self._embodiment.digest(),
                        policy_digest=policy_digest,
                        outcome=OUTCOME_ABORTED,
                        started_at=now,
                        observations=observations,
                        duration_s=duration_s,
                        abort_cause=directive.cause,
                        detail=directive.detail,
                        stream_complete=False,
                        embodiment_verified=self._embodiment.fully_verified,
                    ),
                    abort=directive,
                )
            )

        unmet = self._unmet_postconditions(
            runtime.postconditions(), postconditions
        )
        outcome = (
            OUTCOME_SUCCEEDED if not unmet else OUTCOME_FAILED_VERIFICATION
        )
        return self._record(
            RunReport(
                trajectory=TrajectoryRecord(
                    run_id=run_id,
                    stage=stage,
                    skill_version_id=selection.skill_version_id,
                    contract_digest=selection.contract_digest,
                    selection_digest=selection.selection_digest(),
                    embodiment_digest=self._embodiment.digest(),
                    policy_digest=policy_digest,
                    outcome=outcome,
                    started_at=now,
                    observations=observations,
                    duration_s=duration_s,
                    stream_complete=True,
                    embodiment_verified=self._embodiment.fully_verified,
                    findings=unmet,
                )
            )
        )

    @staticmethod
    def _unmet_postconditions(
        measured: Mapping[str, bool], declared: tuple[str, ...]
    ) -> tuple[str, ...]:
        unmet: list[str] = []
        for condition in declared:
            if condition not in measured:
                unmet.append(
                    f"postcondition {condition!r} was not measured, so "
                    "success cannot be claimed"
                )
            elif not measured[condition]:
                unmet.append(f"postcondition {condition!r} does not hold")
        return tuple(unmet)

    def _refuse(
        self,
        selection: SkillSelection,
        run_id: str,
        stage: str,
        now: datetime,
        policy_digest: Optional[str],
        findings: tuple[str, ...],
    ) -> RunReport:
        return self._record(
            RunReport(
                trajectory=TrajectoryRecord(
                    run_id=run_id,
                    stage=stage,
                    skill_version_id=selection.skill_version_id,
                    contract_digest=selection.contract_digest,
                    selection_digest=selection.selection_digest(),
                    embodiment_digest=self._embodiment.digest(),
                    policy_digest=policy_digest,
                    outcome=OUTCOME_REFUSED,
                    started_at=now,
                    embodiment_verified=self._embodiment.fully_verified,
                    findings=findings,
                )
            )
        )

    def _record(self, report: RunReport) -> RunReport:
        self._trajectories.record(report.trajectory)
        return report
