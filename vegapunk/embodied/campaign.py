"""The inner iteration loop: repeated simulated runs become admission evidence.

The admission ladder demands evidence before a person stands next to a moving
robot, and ``simulation.py`` can produce a run. Nothing yet turns runs into a
stage's worth of evidence. This module is that missing connection, and it is
deliberately a driver rather than a judge: it decides *what to attempt next*
and never what an attempt proved.

Every governance question is delegated. ``ExecutionLoop`` decides whether an
attempt may start and whether it succeeded. ``TrajectoryLedger.derive_evidence``
counts the outcomes, so the campaign cannot report a success rate that
disagrees with the recorded runs. ``evaluate_admission`` decides whether the
next stage is now open. A campaign that tallied its own results would be the
one component able to overstate its own evidence, so it does not tally.

Five refusals:

- It refuses to iterate in an environment that misrepresents the configuration
  its evidence is scoped to. Ten runs in a simulator stepping at the wrong
  cadence are ten measurements of a different servo, and the ladder would count
  them, because a digest hashes what a human declared. It asks the loop for a
  fidelity assessment before the first attempt.
- It refuses to drive a real robot. A campaign may only target a stage whose
  runs are simulated. Iterating unattended is precisely what must not happen
  once the motion is physical: ``shadow_mode`` and ``hardware_supervised``
  advance one human-approved run at a time, by hand.
- It refuses to repeat an identical run. A deterministic simulator started from
  the same state produces the same trajectory, so ten replays are one attempt
  reported as ten. Each attempt therefore gets a bounded, seeded, reproducible
  initial-condition offset, and a schedule that cannot vary anything is
  rejected at construction.
- It refuses to continue past an abort. The abort quarantines the configuration
  until a named human clears it, so every later attempt would be refused and
  the campaign would quietly report a short evidence set as if it had finished.
  It halts and names the blocking run instead.
- It refuses to continue past a refusal. A refusal is not an attempt: it says
  the configuration cannot run at all. Repeating it nine more times produces no
  evidence and buries the reason in noise.

Recording evidence withdraws any human approval pinned to the previous evidence
set, by design: an approver reviewed what was known then, and this campaign has
changed it.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Protocol, Sequence

from vegapunk.embodied.admission import (
    ADMISSION_STAGE_ORDER,
    STAGE_OFFLINE_REPLAY,
    STAGE_POLICY_EVALUATION,
    AdmissionLedger,
    EvidenceRecord,
    evaluate_admission,
)
from vegapunk.embodied.fidelity import (
    FidelityAssessment,
    SimulatedConfiguration,
)
from vegapunk.embodied.loop import ExecutionLoop, SkillRuntime
from vegapunk.embodied.runtime import ResettableRobot
from vegapunk.embodied.skill import SkillSelection
from vegapunk.embodied.trajectory import (
    OUTCOME_ABORTED,
    OUTCOME_REFUSED,
    OUTCOME_SUCCEEDED,
    TrajectoryLedger,
)

SIMULATED_STAGES = (STAGE_POLICY_EVALUATION, STAGE_OFFLINE_REPLAY)

HALTED_COMPLETED = "completed"
HALTED_REFUSED = "refused"
HALTED_ABORTED = "aborted"

_DEFAULT_MAX_OFFSET_RAD = 0.05


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class AttemptVariation:
    """One reproducible initial condition for one attempt.

    The offsets are what makes an attempt a separate measurement rather than a
    replay. They are recorded per attempt so a reviewer can confirm the run set
    actually differed, and they are derived from a seed so a campaign that
    found a failure can be run again exactly.
    """

    index: int
    seed: int
    joint_offsets_rad: tuple[float, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "joint_offsets_rad",
            tuple(float(value) for value in self.joint_offsets_rad),
        )
        if self.index < 0:
            raise ValueError("an attempt index cannot be negative")
        if not self.joint_offsets_rad:
            raise ValueError(
                f"variation {self.index} declares no joint offsets, so it "
                "cannot distinguish this attempt from a replay"
            )

    def digest(self) -> str:
        return _digest(
            {
                "seed": self.seed,
                "joint_offsets_rad": [
                    round(value, 9) for value in self.joint_offsets_rad
                ],
            }
        )


class VariationSchedule:
    """Bounded, seeded initial-condition offsets, one per attempt.

    The bound is a safety statement as much as a statistical one. An offset
    large enough to start the robot somewhere the skill was never reviewed for
    would make a failure a fact about the perturbation rather than about the
    skill, so the magnitude stays small and is declared.
    """

    def __init__(
        self,
        joint_count: int,
        max_offset_rad: float = _DEFAULT_MAX_OFFSET_RAD,
        seed: int = 0,
    ) -> None:
        if joint_count <= 0:
            raise ValueError("joint_count must be positive")
        if max_offset_rad <= 0:
            raise ValueError(
                "max_offset_rad must be positive; a schedule that cannot vary "
                "the initial condition would report one replayed run as many "
                "independent attempts"
            )
        self._joint_count = int(joint_count)
        self._max_offset_rad = float(max_offset_rad)
        self._seed = int(seed)

    @property
    def joint_count(self) -> int:
        return self._joint_count

    @property
    def max_offset_rad(self) -> float:
        return self._max_offset_rad

    def variation(self, index: int) -> AttemptVariation:
        """Derive attempt ``index``'s offsets from the schedule's seed."""
        if index < 0:
            raise ValueError("an attempt index cannot be negative")
        seed = self._seed + index
        generator = random.Random(f"{self._seed}:{index}")
        offsets = tuple(
            generator.uniform(-self._max_offset_rad, self._max_offset_rad)
            for _ in range(self._joint_count)
        )
        return AttemptVariation(
            index=index, seed=seed, joint_offsets_rad=offsets
        )


class CampaignEnvironment(Protocol):
    """The seam between the campaign and whatever it iterates.

    One call per attempt returns a runtime that has never moved, positioned at
    the requested initial condition. A fresh runtime per attempt is required,
    not preferred: motion state carried across attempts would make the second
    run a continuation of the first, and the success rate a fiction.

    ``configuration`` is what the environment says it is. It is part of this
    seam rather than an argument to ``run`` because only the environment knows
    its own cadence and joints, and a campaign that accepted a description from
    its caller would let the caller describe an environment they never built.
    """

    @property
    def configuration(self) -> SimulatedConfiguration:
        """The facts this environment's evidence would be scoped to."""

    def prepare(self, variation: AttemptVariation) -> SkillRuntime:
        """Reset to ``variation``'s initial condition and return a runtime."""


@dataclass(frozen=True)
class AttemptRecord:
    """What one attempt in the campaign did, and which run it wrote."""

    index: int
    run_id: str
    outcome: str
    variation_digest: str
    findings: tuple[str, ...] = ()
    abort_cause: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))


@dataclass(frozen=True)
class CampaignReport:
    """What a campaign attempted, what it recorded, and what it opened.

    ``evidence`` is derived from every recorded run for this configuration at
    this stage, not only this campaign's runs. Evidence about a configuration
    is cumulative; a campaign is just the occasion on which more of it was
    collected.
    """

    campaign_id: str
    stage: str
    scope: tuple[str, str, Optional[str]]
    planned_attempts: int
    attempts: tuple[AttemptRecord, ...]
    evidence: EvidenceRecord
    fidelity: FidelityAssessment
    halted: str
    halt_detail: str
    next_stage: Optional[str]
    next_stage_admitted: bool
    next_stage_blocking_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempts", tuple(self.attempts))
        object.__setattr__(
            self,
            "next_stage_blocking_reasons",
            tuple(self.next_stage_blocking_reasons),
        )

    @property
    def executed_attempts(self) -> int:
        """Runs that actually moved. A refusal never started."""
        return sum(
            1
            for attempt in self.attempts
            if attempt.outcome != OUTCOME_REFUSED
        )

    @property
    def successes(self) -> int:
        return sum(
            1
            for attempt in self.attempts
            if attempt.outcome == OUTCOME_SUCCEEDED
        )

    @property
    def completed(self) -> bool:
        """Whether the campaign ran its full plan rather than halting."""
        return self.halted == HALTED_COMPLETED


class SimulationCampaign:
    """Iterates one selection in simulation until it has a stage's evidence.

    The campaign owns the iteration and nothing else. It chooses the initial
    condition, asks the governed loop for one run, and stops when the run set
    is complete or when continuing would be dishonest.
    """

    def __init__(
        self,
        loop: ExecutionLoop,
        admission: AdmissionLedger,
        trajectories: TrajectoryLedger,
        clock: Callable[[], datetime],
        stage: str = STAGE_OFFLINE_REPLAY,
    ) -> None:
        if stage not in SIMULATED_STAGES:
            raise ValueError(
                f"a campaign cannot target stage {stage!r}: only "
                f"{list(SIMULATED_STAGES)!r} are simulated. A stage whose runs "
                "move a real robot advances one human-approved run at a time, "
                "not by unattended iteration"
            )
        self._loop = loop
        self._admission = admission
        self._trajectories = trajectories
        self._clock = clock
        self._stage = stage

    @property
    def stage(self) -> str:
        return self._stage

    def run(
        self,
        campaign_id: str,
        selection: SkillSelection,
        environment: CampaignEnvironment,
        schedule: VariationSchedule,
        planned_attempts: int,
    ) -> CampaignReport:
        """Attempt ``planned_attempts`` varied runs, then record the evidence."""
        if not campaign_id:
            raise ValueError("a campaign requires a campaign_id")
        if planned_attempts < 1:
            raise ValueError("planned_attempts must be at least 1")

        # Asked before the first attempt, and raised rather than recorded. A
        # misrepresenting environment produces no evidence at all, so there is
        # nothing to write down: recording it as a refused run would put a
        # number about the wrong configuration into this scope's ledger, which
        # is the exact confusion the assessment exists to prevent.
        fidelity = self._loop.assess_environment(
            selection, environment.configuration
        )
        if not fidelity.represents:
            raise ValueError(
                f"environment {fidelity.environment_id!r} does not represent "
                "the embodiment this campaign's evidence would be scoped to, "
                "so iterating in it would accumulate evidence about a "
                "different configuration: "
                + "; ".join(fidelity.findings)
            )

        attempts: list[AttemptRecord] = []
        halted = HALTED_COMPLETED
        halt_detail = (
            f"ran all {planned_attempts} planned attempts"
        )
        scope: Optional[tuple[str, str, Optional[str]]] = None

        for index in range(planned_attempts):
            variation = schedule.variation(index)
            runtime = environment.prepare(variation)
            run_id = f"{campaign_id}-{index:03d}"

            report = self._loop.run(
                selection=selection,
                runtime=runtime,
                run_id=run_id,
                stage=self._stage,
                now=self._clock(),
            )
            trajectory = report.trajectory
            scope = trajectory.scope_key()
            attempts.append(
                AttemptRecord(
                    index=index,
                    run_id=run_id,
                    outcome=trajectory.outcome,
                    variation_digest=variation.digest(),
                    findings=trajectory.findings,
                    abort_cause=trajectory.abort_cause,
                )
            )

            if trajectory.outcome == OUTCOME_REFUSED:
                halted = HALTED_REFUSED
                halt_detail = (
                    f"run {run_id!r} was refused before it moved, so no later "
                    "attempt can produce evidence either: "
                    + "; ".join(trajectory.findings)
                )
                break

            if trajectory.outcome == OUTCOME_ABORTED:
                halted = HALTED_ABORTED
                halt_detail = (
                    f"run {run_id!r} aborted with cause "
                    f"{trajectory.abort_cause!r}; this configuration is "
                    "quarantined until a named human clears that run"
                )
                break

        assert scope is not None
        recorded_at = self._clock()
        evidence = self._admission.record(
            self._trajectories.derive_evidence(
                scope=scope,
                stage=self._stage,
                recorded_at=recorded_at,
                notes=(
                    f"campaign {campaign_id} in environment "
                    f"{fidelity.environment_id!r} "
                    f"(fidelity {fidelity.digest()}): {halt_detail}"
                ),
            )
        )

        next_stage = self._next_stage()
        decision = evaluate_admission(
            ledger=self._admission,
            skill_version_id=scope[0],
            embodiment_digest=scope[1],
            policy_digest=scope[2],
            target_stage=next_stage,
            approval=None,
            now=recorded_at,
        )
        blocking_reasons = decision.blocking_reasons
        next_stage_admitted = decision.admitted

        # A quarantine outranks the evidence arithmetic. A human stop is not a
        # safety violation and barely moves a success rate, so an eleventh run
        # that someone aborted still satisfies the thresholds -- while the loop
        # would refuse every subsequent run for this configuration. Reporting
        # the next stage as open would be the one dishonest line in the report.
        quarantine = self._trajectories.quarantine(scope)
        if quarantine is not None:
            blocking_reasons = blocking_reasons + (quarantine,)
            next_stage_admitted = False

        return CampaignReport(
            campaign_id=campaign_id,
            stage=self._stage,
            scope=scope,
            planned_attempts=planned_attempts,
            attempts=tuple(attempts),
            evidence=evidence,
            fidelity=fidelity,
            halted=halted,
            halt_detail=halt_detail,
            next_stage=next_stage,
            next_stage_admitted=next_stage_admitted,
            next_stage_blocking_reasons=blocking_reasons,
        )

    def _next_stage(self) -> str:
        return ADMISSION_STAGE_ORDER[
            ADMISSION_STAGE_ORDER.index(self._stage) + 1
        ]


class SimulatedCampaignEnvironment:
    """Prepares one simulated attempt: displace, then hand over a new runtime.

    A fresh ``DeterministicJointRuntime`` per attempt is not a precaution, it is
    what the runtime demands: it refuses to run twice, so that no attempt can
    inherit the previous one's motion state. The robot itself is reused because
    it owns the MuJoCo model and GL context, and it is reset before every
    attempt.
    """

    def __init__(
        self,
        robot: ResettableRobot,
        runtime_factory: Callable[[], SkillRuntime],
        configuration: SimulatedConfiguration,
    ) -> None:
        if configuration.is_real_robot:
            raise ValueError(
                f"environment {configuration.environment_id!r} describes "
                "itself as a real robot; this class resets to a chosen initial "
                "condition, which no physical robot can do, so the description "
                "is wrong about one of the two"
            )
        self._robot = robot
        self._runtime_factory = runtime_factory
        self._configuration = configuration

    @property
    def configuration(self) -> SimulatedConfiguration:
        return self._configuration

    def prepare(self, variation: AttemptVariation) -> SkillRuntime:
        self._robot.reset(joint_offsets_rad=variation.joint_offsets_rad)
        return self._runtime_factory()
