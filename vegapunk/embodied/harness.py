"""The composition: a complaint becomes a ranked set of measured adaptations.

Every other module in this package is a part. This one is the assembly that
makes the parts a system, and it exists because the seams they were built
against do not meet on their own: ``search`` knows how to explore typed
candidates but not what a robot is, ``campaign`` knows how to turn varied runs
into evidence but not what an adaptation is, and ``objective`` knows how to
score a distribution but not how to obtain one.

The path it composes is the whole product:

``intake``      a person's complaint becomes a routed, refusable brief
``adaptation``  the brief's route becomes a typed candidate space
``regime``      each attempt becomes a different world, not a replay
``campaign``    varied runs under one candidate become one distribution
``objective``   that distribution becomes one robustness-weighted score
``search``      those scores become a ranked lineage of candidates
``store``       the ranking outlives the process that produced it

Three refusals, and the first one is the reason this module is not a script.

It refuses to let one candidate's runs become another's evidence. The admission
ledger accumulates by configuration, deliberately: evidence about a robot is
cumulative and a fresh process must not rewind it. But a search evaluates
hundreds of candidates against the *same* configuration, so a shared ledger
would let candidate 200 inherit candidate 3's abort, and one early safety
violation would disqualify every candidate that followed it. Each evaluation
therefore gets its own ledger pair, and nothing the search collects is written
into the ladder's ledger at all. That is not an optimisation. A candidate is a
proposal, and the ladder is a record of what has been validated; a search that
filed its exploration as validation evidence would let a scoreboard admit
hardware.

It refuses to search a path the brief did not open. ``intake`` routes a
complaint to one of five paths and only two of them are things a machine may
explore unattended. A harness that searched anyway would be answering a
question nobody asked, and doing it with the authority of a measurement.

It refuses to rank a candidate the objective disqualified. Disqualification is
not a low score; it is the absence of a score, and the search's ordering
already treats it that way. This module's job is to not undo that by reporting
a ranking that reads as a recommendation.

What it does not do, and must not: it never touches hardware. The evaluator
drives a ``PerturbableRobot``, which a real G1 structurally is not, so the
worst outcome of a runaway search is wasted CPU. Promotion to hardware stays
where it was: a named human, a fresh approval, one run at a time.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping, Optional, Protocol, Sequence

from vegapunk.embodied.adaptation import (
    AdaptationCandidate,
    AdaptationSpace,
    GoalActionSource,
    AdaptedJointRuntime,
    DEFAULT_ADAPTATION_SPACE,
)
from vegapunk.embodied.admission import (
    MINIMUM_STAGE_ATTEMPTS,
    STAGE_POLICY_EVALUATION,
    AdmissionLedger,
)
from vegapunk.embodied.campaign import (
    CampaignReport,
    RegimeEnvironment,
    RegimeSchedule,
    SimulationCampaign,
)
from vegapunk.embodied.embodiment import EmbodimentProfile
from vegapunk.embodied.fidelity import SimulatedConfiguration
from vegapunk.embodied.intake import (
    AUTOMATABLE_PATHS,
    AdaptationBrief,
)
from vegapunk.embodied.loop import ExecutionLoop, SkillRuntime
from vegapunk.embodied.objective import CandidateScore, RobustnessObjective
from vegapunk.embodied.regime import DEFAULT_CONTACT_REGIME, Regime, RegimeSample
from vegapunk.embodied.runtime import (
    CommandRateCalibration,
    JointPoseGoal,
    RobotInterface,
)
from vegapunk.embodied.safety import SafetyEnvelope, SafetySupervisor
from vegapunk.embodied.search import AdaptationSearch, SearchReport
from vegapunk.embodied.skill import PhysicalSkill, SkillRegistry, SkillSelection
from vegapunk.embodied.trajectory import TrajectoryLedger

HALTED_NOT_SEARCHABLE = "brief_refused_the_search"
HALTED_COMPLETED = "completed"

SIMULATED_SEARCH_STAGE = STAGE_POLICY_EVALUATION
"""The one ladder stage a search may run its candidates at.

It is the ladder's first rung, and it has to be, for a reason that is easy to
get wrong. Each evaluation gets a fresh pair of ledgers so that candidates
cannot contaminate one another, and the ladder requires every stage before the
target to already carry evidence. A search aimed at any later rung would
therefore be refused on its first attempt in every evaluation -- correctly,
because in a ledger that starts empty no earlier stage has been earned.

The tempting repair is to seed the earlier stage so the search can proceed.
That would forge exactly the record the ladder exists to protect, and it would
do it hundreds of times per investigation. So the search stays at the first
rung, where a candidate is measured on its own merits and nothing needs to be
invented, and climbing the ladder remains what it was: a deliberate act
performed once per configuration, with the evidence that was actually earned.
"""

DEFAULT_SEARCH_BUDGET = 24
"""How many candidates one investigation evaluates by default.

Chosen to be a number of *campaigns*, not a number of guesses: at ten attempts
each this is 240 governed runs, which is minutes of simulation and enough for
the ranking to be about the objective rather than about the seed. It is a
default rather than a constant because the right budget is a property of how
much a laboratory wants to spend, which is not a fact this module owns.
"""


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


class PerturbableRobot(Protocol):
    """A robot whose world and initial pose can both be chosen.

    The type is the safety property. A real G1 cannot be teleported and cannot
    have its friction rebuilt, so hardware cannot satisfy this protocol, and an
    unattended search therefore cannot reach it however wrong its objective is.
    """

    def reset(
        self,
        joint_offsets_rad: Optional[Sequence[float]] = None,
        sample: Optional[RegimeSample] = None,
    ) -> None:
        """Return to the start pose, in the world ``sample`` describes."""

    def read_state(self) -> object:
        """Report the measured state."""

    def command_joint_positions(self, positions_rad: Sequence[float]) -> None:
        """Command one joint-space waypoint."""

    def hold(self) -> None:
        """Stop and hold."""

    @property
    def is_real_robot(self) -> bool:
        """Whether this is physical hardware. Must be False here."""

    @property
    def joint_names(self) -> tuple[str, ...]:
        """The joints this robot controls."""

    @property
    def control_frequency_hz(self) -> float:
        """The cadence setpoints are consumed at."""


@dataclass(frozen=True)
class EvaluationRecord:
    """One candidate, the campaign it earned, and the score that resulted.

    Kept because a ranking without its evidence is an opinion. The campaign
    report carries every attempt and every finding, so a reviewer can ask why
    a candidate scored what it did without re-running it.
    """

    candidate_digest: str
    score: CandidateScore
    campaign: CampaignReport

    def as_contract(self) -> dict[str, object]:
        return {
            "candidate_digest": self.candidate_digest,
            "score": self.score.digest(),
            "attempts": self.score.attempts,
            "successes": self.score.successes,
            "regime_success_rate": round(self.score.regime_success_rate, 6),
            "sensitivity": round(self.score.sensitivity, 6),
            "disqualified": self.score.disqualified,
            "halted": self.campaign.halted,
        }


class CampaignEvaluator:
    """Turns one typed candidate into one measured score, via real runs.

    This is the seam ``search`` was built against, and the only place where an
    adaptation stops being a proposal and becomes a measurement. It owns one
    decision worth stating: every evaluation is scoped to its own pair of
    ledgers, so the distribution a candidate is scored on contains that
    candidate's runs and nothing else.
    """

    def __init__(
        self,
        robot: PerturbableRobot,
        skill: PhysicalSkill,
        embodiment: EmbodimentProfile,
        configuration: SimulatedConfiguration,
        goal: JointPoseGoal,
        command_rate: CommandRateCalibration,
        envelope: SafetyEnvelope,
        regime: Regime = DEFAULT_CONTACT_REGIME,
        objective: Optional[RobustnessObjective] = None,
        attempts: int = MINIMUM_STAGE_ATTEMPTS,
        stage: str = SIMULATED_SEARCH_STAGE,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if robot.is_real_robot:
            raise ValueError(
                "refusing to build a search evaluator around real hardware: "
                "an unattended loop that can command a physical robot is the "
                "one thing this profile exists to prevent"
            )
        if attempts < 1:
            raise ValueError("an evaluation needs at least one attempt")
        self._robot = robot
        self._skill = skill
        self._embodiment = embodiment
        self._configuration = configuration
        self._goal = goal
        self._command_rate = command_rate
        self._envelope = envelope
        self._regime = regime
        self._objective = objective or RobustnessObjective()
        self._attempts = int(attempts)
        self._stage = stage
        self._clock = clock or _utc_now
        self._records: list[EvaluationRecord] = []

    @property
    def records(self) -> tuple[EvaluationRecord, ...]:
        """Every evaluation this evaluator performed, in order."""
        return tuple(self._records)

    def evaluate(self, candidate: AdaptationCandidate) -> CandidateScore:
        """Run one candidate across the regime and score what happened."""
        digest = candidate.digest()

        # A fresh ladder per candidate. See the module docstring: sharing one
        # would let an early abort disqualify every later candidate, and would
        # file exploration as validation.
        admission = AdmissionLedger()
        trajectories = TrajectoryLedger()
        registry = SkillRegistry()
        registry.register(self._skill)
        selection = registry.select(self._skill.skill_id, {})

        loop = ExecutionLoop(
            registry=registry,
            embodiment=self._embodiment,
            supervisor=SafetySupervisor(self._envelope),
            admission=admission,
            trajectories=trajectories,
        )

        driven: list[AdaptedJointRuntime] = []

        def runtime_factory() -> SkillRuntime:
            runtime = AdaptedJointRuntime(
                robot=self._robot,
                source=GoalActionSource(self._goal),
                candidate=candidate,
                goal=self._goal,
                command_rate=self._command_rate,
                envelope=self._envelope,
                clock=self._robot_clock(),
            )
            driven.append(runtime)
            return runtime

        campaign = SimulationCampaign(
            loop=loop,
            admission=admission,
            trajectories=trajectories,
            clock=self._clock,
            stage=self._stage,
        )
        report = campaign.run(
            campaign_id=f"search-{digest}",
            selection=selection,
            environment=RegimeEnvironment(
                robot=self._robot,
                runtime_factory=runtime_factory,
                configuration=self._configuration,
            ),
            schedule=RegimeSchedule(
                regime=self._regime,
                joint_count=len(self._robot.joint_names),
            ),
            planned_attempts=self._attempts,
        )

        score = self._objective.score(
            digest, (report,), progress=_progress_of(driven)
        )
        self._records.append(
            EvaluationRecord(
                candidate_digest=digest, score=score, campaign=report
            )
        )
        return score

    def _robot_clock(self) -> Optional[Callable[[], float]]:
        """The simulation's own clock, when it has one.

        A simulated run must be timed by simulated seconds. Timing it by the
        wall clock would make the safety supervisor's duration limit a fact
        about this workstation's load, so a slow machine would abort runs a
        fast one passed.
        """
        clock = getattr(self._robot, "clock", None)
        return clock if callable(clock) else None


@dataclass(frozen=True)
class InvestigationReport:
    """What one complaint produced: a route, a ranking, and its refusals."""

    brief: AdaptationBrief
    search: Optional[SearchReport]
    evaluations: tuple[EvaluationRecord, ...]
    halted: str
    halt_detail: str = ""

    @property
    def completed(self) -> bool:
        return self.halted == HALTED_COMPLETED

    @property
    def best(self) -> Optional[EvaluationRecord]:
        """The highest-ranked candidate that was not disqualified."""
        if self.search is None or self.search.best is None:
            return None
        digest = self.search.best.candidate.digest()
        for record in self.evaluations:
            if record.candidate_digest == digest:
                return record
        return None

    @property
    def improved(self) -> bool:
        """Whether the search beat the do-nothing baseline.

        The only question a reviewer actually has. A ranking whose winner is
        the identity candidate is a real and useful answer -- the adaptation
        layer is not where this problem lives -- and it must not be reported
        as an improvement.
        """
        return (
            self.search is not None
            and self.search.improved_over_baseline()
        )

    def as_contract(self) -> dict[str, object]:
        return {
            "pain_point": self.brief.pain_point.digest(),
            "symptom": self.brief.symptom,
            "routed_path": self.brief.routed_path,
            "objective": self.brief.objective_statement,
            "searchable": self.brief.searchable,
            "refusal": self.brief.refusal,
            "unknowns": list(self.brief.unknowns),
            "halted": self.halted,
            "halt_detail": self.halt_detail,
            "improved_over_baseline": self.improved,
            "evaluations": [
                record.as_contract() for record in self.evaluations
            ],
            "search": (
                None if self.search is None else self.search.as_contract()
            ),
        }


def investigate(
    brief: AdaptationBrief,
    evaluator: CampaignEvaluator,
    space: AdaptationSpace = DEFAULT_ADAPTATION_SPACE,
    budget: int = DEFAULT_SEARCH_BUDGET,
    seed: int = 0,
) -> InvestigationReport:
    """Search for an adaptation that answers one brief, or refuse to.

    The refusal is the first thing checked and the most important thing here.
    ``intake`` already decided whether this complaint is something a machine
    may explore; this function's contribution is to honour that decision
    rather than re-derive it, so there is exactly one place in the system where
    a route becomes permission.
    """
    if not brief.searchable or brief.routed_path not in AUTOMATABLE_PATHS:
        return InvestigationReport(
            brief=brief,
            search=None,
            evaluations=(),
            halted=HALTED_NOT_SEARCHABLE,
            halt_detail=(
                brief.refusal
                or f"the {brief.routed_path!r} path is not searchable "
                "unattended"
            ),
        )

    search = AdaptationSearch(
        space=space, evaluator=evaluator, seed=seed
    )
    report = search.run(budget)
    return InvestigationReport(
        brief=brief,
        search=report,
        evaluations=evaluator.records,
        halted=HALTED_COMPLETED,
        halt_detail=report.halt_detail,
    )


def _progress_of(runtimes: Sequence[object]) -> Optional[float]:
    """How far this candidate closed the gap it set out to close, in [0, 1].

    Averaged over the runs, and reported only when every run could say. A
    fraction rather than an absolute residual because the runs span a regime:
    each attempt starts from its own perturbed pose, so the same 0.05 rad
    residual is most of the way on one attempt and barely started on another,
    and averaging raw residuals would rank a candidate by which worlds it drew.

    ``None`` when nothing measured, which the objective reads as "no progress
    information" rather than as "no progress". The distinction matters: a
    candidate whose runs were all refused has no proximity, and crediting it
    with zero would be a measurement it never earned.
    """
    fractions: list[float] = []
    for runtime in runtimes:
        residual = getattr(runtime, "residual_rad", None)
        initial = getattr(runtime, "initial_residual_rad", None)
        if residual is None or initial is None or initial <= 0.0:
            continue
        closed = (initial - float(residual)) / initial
        fractions.append(min(1.0, max(0.0, closed)))
    if not fractions:
        return None
    return sum(fractions) / len(fractions)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
