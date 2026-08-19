"""What the search is allowed to change, and what it may never touch.

The harness exists to find an adaptation that makes a robot able to do
something it currently cannot. The object it iterates is deliberately not the
policy's weights. It is the layer between whatever authors an action and the
robot that executes it: coordinate convention, gain, bias, rate shaping,
latency lead, deadband, settling behaviour. That choice is not a convenience.
Fine-tuning weights on top of a broken interface bakes the interface bug into a
checkpoint permanently, and the resulting artefact cannot be reviewed, reverted
or attributed; a seven-number adaptation can be printed in a report, diffed
against the identity, and undone by deleting a row.

This module therefore refuses four things.

An adaptation cannot contain a knob the executor does not implement.
``AdaptationSpace.admit`` rejects an unrecognised gene name outright instead of
clamping or dropping it, because a silently discarded knob means the proposer
and the executor disagree about what was searched, and the result would be
attributed to a candidate that never ran.

An adaptation cannot lack a defined no-op. ``identity()`` is the exact
do-nothing setting -- every gene at its neutral value -- and a gene whose
declared range excludes its own neutral value is rejected when the space is
built. Without an exact identity there is no control condition, and every
measurement becomes a comparison against an unknown baseline.

An adaptation cannot widen a safety limit. ``GENE_RATE_LIMIT_SCALE`` may only
tighten the calibrated per-step bound: the effective scale is capped at 1.0 in
the runtime regardless of what the candidate says, so a hostile or corrupted
candidate cannot buy success by commanding faster motion than the calibration
admitted. The setpoint leash and the goal tolerance floor are enforced the same
way. A candidate is a hypothesis about the interface, never a request for
authority.

An adaptation cannot be a range without a reason. Every gene carries the
rationale that makes its bounds defensible, because a bound nobody can justify
is the mechanism by which a search escapes the regime its evidence covers.

``ActionSource`` is the seam that makes all of this apply to more than a
controller. A replayed trajectory, a scripted move and a VLA all propose joint
targets, and none of them needs to know an adaptation exists.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import deque
import random
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import (
    Callable,
    Mapping,
    Optional,
    Protocol,
    Sequence,
)

from vegapunk.embodied.loop import RuntimeStep
from vegapunk.embodied.runtime import (
    CommandRateCalibration,
    JointPoseGoal,
    RobotInterface,
    RobotState,
    bounded_waypoint,
)
from vegapunk.embodied.safety import (
    AbortDirective,
    Observation,
    SafetyEnvelope,
)
from vegapunk.embodied.skill import SkillSelection

ORIGIN_ROOT = "root"
ORIGIN_MUTATION = "mutation"
ORIGIN_PROPOSAL = "proposal"

ADAPTATION_ORIGINS = (ORIGIN_ROOT, ORIGIN_MUTATION, ORIGIN_PROPOSAL)

_VALUE_PRECISION = 9
"""Decimal places a candidate's values are digested at.

Nine places is far below the resolution of any actuator this harness commands,
so two candidates that differ only below it produce an identical command
stream. Rounding before hashing makes them one experiment rather than two,
which is what stops a mutation that moved nothing from being reported as a new
measurement.
"""

_MIN_EFFECTIVE_RATE_SCALE = 1e-3
"""The floor a hostile rate-limit scale is pulled up to.

A non-positive step bound is not a tighter limit, it is undefined arithmetic:
the waypoint rule would invert and command motion away from the target. The
floor keeps the command meaningful, and a candidate throttled this hard simply
fails to arrive and is scored for failing.
"""

_MAX_EFFECTIVE_SMOOTHING = 0.99
"""The ceiling an out-of-range smoothing weight is pulled down to.

The weight sits on the previous setpoint, so at 1.0 the filter ignores its
input entirely and the runtime would command the start pose forever while
reporting healthy steps. Above 1.0 the recursion diverges. Either way the
number has stopped describing a low-pass filter, so it is clamped rather than
executed.
"""


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class AdaptationGene:
    """One knob the search may turn, and the range it may turn it within.

    ``rationale`` is a required field rather than a comment because the bounds
    are the only thing keeping the search inside the regime its evidence was
    collected in. A range nobody can defend is a licence to report a result
    obtained somewhere else.
    """

    name: str
    low: float
    high: float
    unit: str
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "low", float(self.low))
        object.__setattr__(self, "high", float(self.high))
        if not self.name:
            raise ValueError("a gene requires a name")
        if not self.unit:
            raise ValueError(
                f"gene {self.name!r} declares no unit; a bare number cannot "
                "be checked against a physical limit"
            )
        if not self.rationale:
            raise ValueError(
                f"gene {self.name!r} declares no rationale for its range, so "
                "nothing states why a result found inside it is defensible"
            )
        if not math.isfinite(self.low) or not math.isfinite(self.high):
            raise ValueError(f"gene {self.name!r} has a non-finite bound")
        if self.low > self.high:
            raise ValueError(
                f"gene {self.name!r} declares low {self.low} above high "
                f"{self.high}"
            )

    def clamp(self, value: float) -> float:
        """Pull a value into the declared range."""
        return min(self.high, max(self.low, float(value)))

    def sample(self, generator: random.Random) -> float:
        """Draw one value uniformly from the declared range."""
        return generator.uniform(self.low, self.high)

    def digest(self) -> str:
        return _digest(
            {
                "name": self.name,
                "low": round(self.low, _VALUE_PRECISION),
                "high": round(self.high, _VALUE_PRECISION),
                "unit": self.unit,
            }
        )


GENE_GAIN_SCALE = AdaptationGene(
    name="gain_scale",
    low=0.5,
    high=1.5,
    unit="dimensionless",
    rationale=(
        "Multiplies the commanded displacement from the measured position, so "
        "it is the knob that corrects an interface that under- or overshoots "
        "its own targets. Above 1.5 the correction stops being a frame fix "
        "and becomes a proportional gain the servo was never tuned for, which "
        "shows up as oscillation the step bound hides rather than removes. "
        "Below 0.5 no move completes inside a skill's declared duration, so "
        "the run measures the time limit instead of the adaptation."
    ),
)

GENE_BIAS_RAD = AdaptationGene(
    name="bias_rad",
    low=-0.15,
    high=0.15,
    unit="rad",
    rationale=(
        "A constant joint-space offset added to every target: the shape a "
        "zero-point or frame-convention error actually takes. About 8.6 "
        "degrees is enough to correct a mis-declared home pose or a sign "
        "convention on a single joint, and small enough that the corrected "
        "goal stays in the neighbourhood the skill was reviewed for. A larger "
        "bias moves the robot somewhere nobody approved, so a success there "
        "would be evidence about a different action."
    ),
)

GENE_RATE_LIMIT_SCALE = AdaptationGene(
    name="rate_limit_scale",
    low=0.25,
    high=1.0,
    unit="dimensionless",
    rationale=(
        "Scales the per-step bound derived from the command-rate "
        "calibration. The high bound is exactly 1.0 and not a rounding "
        "choice: the calibrated bound is the measured peak that fits the "
        "envelope, so anything above 1.0 is a safety change wearing the "
        "costume of a tuning parameter. The runtime caps the effective value "
        "at 1.0 independently of this range. The low bound admits a "
        "quarter-rate approach, four times the nominal duration, which is "
        "about as slow as a move can be and still finish inside a reviewed "
        "time limit."
    ),
)

GENE_SMOOTHING_ALPHA = AdaptationGene(
    name="smoothing_alpha",
    low=0.0,
    high=0.8,
    unit="dimensionless",
    rationale=(
        "First-order low-pass on the setpoint, weighting the previous "
        "setpoint against the newly commanded one; 0 is no filtering, which "
        "is why it is the neutral value. At 0.8 the setpoint reaches about "
        "two thirds of a step change in five control periods, already a "
        "visible softening of the approach. Past that the lag exceeds the "
        "leash the calibration measured, so the filter would be fighting the "
        "runaway protection rather than shaping the motion."
    ),
)

GENE_LATENCY_COMPENSATION_STEPS = AdaptationGene(
    name="latency_compensation_steps",
    low=0.0,
    high=3.0,
    unit="control_periods",
    rationale=(
        "Leads the setpoint along the direction of travel to counteract the "
        "delay between commanding a joint and the joint answering. Measured "
        "in control periods rather than seconds because that is the unit the "
        "delay is actually quantised in. Three periods is 100ms at 30Hz, the "
        "order of an SDK round trip plus servo lag on this class of robot. "
        "Leading further commands a position the robot has no reason to be "
        "near, and the calibrated leash clamps it back anyway, so a wider "
        "range would only spend search budget on values that cannot act."
    ),
)

GENE_DEADBAND_RAD = AdaptationGene(
    name="deadband_rad",
    low=0.0,
    high=0.02,
    unit="rad",
    rationale=(
        "Suppresses commands smaller than itself, which is how a real "
        "interface stops dithering around a target it cannot resolve. The "
        "ceiling is twice the default goal tolerance: at that size the "
        "deadband can forbid the final approach the goal is verified on, so "
        "the search is able to discover that failure and be scored for it, "
        "while a wider range would fill the budget with candidates that "
        "cannot move at all."
    ),
)

GENE_SETTLE_GAIN = AdaptationGene(
    name="settle_gain",
    low=0.25,
    high=2.0,
    unit="dimensionless",
    rationale=(
        "Scales the approach gain once the joint is inside the goal's "
        "tolerance band, where the remaining displacement is by definition "
        "smaller than the tolerance. That is why this range is wider than "
        "the main gain's: doubling a sub-tolerance error cannot produce a "
        "large command, and the step bound still applies. It exists because "
        "the last few milliradians are where a servo's droop lives, and a "
        "joint that stalls just outside tolerance fails a goal it physically "
        "reached."
    ),
)

GENE_NEUTRAL_VALUES: Mapping[str, float] = MappingProxyType(
    {
        GENE_GAIN_SCALE.name: 1.0,
        GENE_BIAS_RAD.name: 0.0,
        GENE_RATE_LIMIT_SCALE.name: 1.0,
        GENE_SMOOTHING_ALPHA.name: 0.0,
        GENE_LATENCY_COMPENSATION_STEPS.name: 0.0,
        GENE_DEADBAND_RAD.name: 0.0,
        GENE_SETTLE_GAIN.name: 1.0,
    }
)
"""Each gene's exact no-op, declared here rather than inferred from a range.

A neutral value is a claim about the executor -- that this number changes
nothing -- so it cannot be derived from the bounds, and a gene with no entry
here has no defined identity. ``AdaptationSpace`` refuses such a gene, which
forecloses the case where a knob is added to the search before anyone has
stated what leaving it alone means.
"""


def neutral_value(name: str) -> float:
    """The declared no-op for one gene, or a refusal."""
    try:
        return GENE_NEUTRAL_VALUES[name]
    except KeyError as error:
        raise KeyError(
            f"gene {name!r} declares no neutral value, so this space has no "
            "identity candidate and no control condition to measure against"
        ) from error


@dataclass(frozen=True)
class AdaptationCandidate:
    """One complete setting of every knob, and where it came from.

    The digest covers the values alone. Two candidates with identical values
    are the same experiment however they were proposed, so they collide on
    purpose: a scoreboard keyed by digest then cannot record one adaptation
    twice under two lineages. ``origin`` and ``parent_digest`` are carried for
    the reviewer, not for identity.
    """

    values: Mapping[str, float]
    origin: str
    parent_digest: Optional[str] = None

    def __post_init__(self) -> None:
        coerced = {
            str(name): float(value)
            for name, value in dict(self.values).items()
        }
        for name, value in coerced.items():
            if not math.isfinite(value):
                raise ValueError(
                    f"gene {name!r} was given the non-finite value {value}; "
                    "such a candidate cannot be commanded or reproduced"
                )
        object.__setattr__(self, "values", MappingProxyType(coerced))
        if self.origin not in ADAPTATION_ORIGINS:
            raise ValueError(
                f"unknown candidate origin {self.origin!r}; expected one of "
                f"{list(ADAPTATION_ORIGINS)!r}"
            )
        if self.origin == ORIGIN_MUTATION and not self.parent_digest:
            raise ValueError(
                "a mutation without a parent digest has no lineage, so its "
                "result cannot be attributed to the change that produced it"
            )

    def digest(self) -> str:
        return _digest(
            {
                name: round(value, _VALUE_PRECISION)
                for name, value in sorted(self.values.items())
            }
        )

    def value(self, name: str) -> float:
        try:
            return self.values[name]
        except KeyError as error:
            raise KeyError(
                f"candidate {self.digest()} carries no value for gene "
                f"{name!r}; it was built for a different space and running it "
                "would measure an adaptation nobody proposed"
            ) from error

    def as_contract(self) -> dict[str, object]:
        """The recordable form: what ran, and what it descended from."""
        return {
            "digest": self.digest(),
            "origin": self.origin,
            "parent_digest": self.parent_digest,
            "values": {
                name: round(value, _VALUE_PRECISION)
                for name, value in sorted(self.values.items())
            },
        }


class AdaptationSpace:
    """The declared set of knobs, and the only source of valid candidates.

    Every candidate the search runs comes from here, so the space is where the
    agreement between proposer and executor is enforced. It is enforced by
    refusal rather than by correction: an unknown gene name is an error, not a
    value to discard.
    """

    def __init__(self, genes: Sequence[AdaptationGene]) -> None:
        if not genes:
            raise ValueError(
                "an adaptation space with no genes cannot express a change, "
                "so a search over it would report the identity as progress"
            )
        by_name: dict[str, AdaptationGene] = {}
        for gene in genes:
            if gene.name in by_name:
                raise ValueError(
                    f"gene {gene.name!r} is declared twice; the second "
                    "declaration would silently decide the range"
                )
            neutral = neutral_value(gene.name)
            if not gene.low <= neutral <= gene.high:
                raise ValueError(
                    f"gene {gene.name!r} declares the range "
                    f"[{gene.low}, {gene.high}] which excludes its neutral "
                    f"value {neutral}; the identity candidate would then be a "
                    "change, and every measurement would be compared against "
                    "an adaptation nobody chose"
                )
            by_name[gene.name] = gene
        self._genes = tuple(by_name[name] for name in by_name)

    @property
    def genes(self) -> tuple[AdaptationGene, ...]:
        return self._genes

    def gene(self, name: str) -> AdaptationGene:
        for gene in self._genes:
            if gene.name == name:
                return gene
        raise KeyError(
            f"gene {name!r} is not part of this adaptation space; the "
            "executor implements no such knob"
        )

    def identity(self) -> AdaptationCandidate:
        """The exact do-nothing adaptation: the control condition."""
        return AdaptationCandidate(
            values={
                gene.name: neutral_value(gene.name)
                for gene in self._genes
            },
            origin=ORIGIN_ROOT,
        )

    def mutate(
        self,
        parent: AdaptationCandidate,
        generator: random.Random,
        scale: float = 0.25,
    ) -> AdaptationCandidate:
        """A neighbour of ``parent``: every gene nudged, then clamped.

        Every gene moves, not one. An interface fault is usually a
        conjunction -- a gain error together with the bias it was hiding --
        and a search that can only turn one knob at a time cannot cross the
        valley between two knobs that are only jointly correct. The step stays
        small so a child is still a neighbour of its parent, and lineage is
        carried in ``parent_digest`` rather than in a claim about which single
        knob moved.
        """
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError(
                "a mutation scale must be positive; a scale of zero returns "
                "the parent and would report one measurement as two"
            )
        if scale > 1.0:
            raise ValueError(
                "a mutation scale above 1.0 draws a child from the whole "
                "range rather than from the parent's neighbourhood, which "
                "makes the recorded lineage a fiction; use admit() for an "
                "unrelated proposal"
            )
        self._require_exact_genes(parent.values)
        values: dict[str, float] = {}
        for gene in self._genes:
            # Two standard deviations of the drawn step span a quarter of the
            # range at the default scale, so a child stays close enough that
            # its score says something about its parent.
            sigma = scale * (gene.high - gene.low) / 4.0
            drawn = parent.value(gene.name) + generator.gauss(0.0, sigma)
            values[gene.name] = gene.clamp(drawn)
        return AdaptationCandidate(
            values=values,
            origin=ORIGIN_MUTATION,
            parent_digest=parent.digest(),
        )

    def admit(self, values: Mapping[str, float]) -> AdaptationCandidate:
        """Accept an outside proposal, clamped, or refuse it entirely.

        Out-of-range values are clamped because a proposer asking for slightly
        more gain than the range allows still means something the executor can
        run. An unrecognised name means nothing the executor can run, and
        dropping it would attribute the result to a candidate that was never
        commanded, so it is refused.
        """
        self._require_exact_genes(values)
        return AdaptationCandidate(
            values={
                gene.name: gene.clamp(values[gene.name])
                for gene in self._genes
            },
            origin=ORIGIN_PROPOSAL,
        )

    def digest(self) -> str:
        return _digest([gene.digest() for gene in self._genes])

    def _require_exact_genes(self, values: Mapping[str, float]) -> None:
        declared = {gene.name for gene in self._genes}
        offered = set(values)
        unknown = sorted(offered - declared)
        if unknown:
            raise KeyError(
                f"unknown gene(s) {unknown!r} in this proposal; the executor "
                "implements no such knob, and clamping or dropping it would "
                "attribute the run's result to a candidate that never ran"
            )
        missing = sorted(declared - offered)
        if missing:
            raise KeyError(
                f"gene(s) {missing!r} are missing from this proposal; a "
                "candidate with an unspecified knob would be completed by "
                "whatever the runtime happened to default to"
            )


DEFAULT_ADAPTATION_SPACE = AdaptationSpace(
    (
        GENE_GAIN_SCALE,
        GENE_BIAS_RAD,
        GENE_RATE_LIMIT_SCALE,
        GENE_SMOOTHING_ALPHA,
        GENE_LATENCY_COMPENSATION_STEPS,
        GENE_DEADBAND_RAD,
        GENE_SETTLE_GAIN,
    )
)
"""The seven knobs Version 1 searches over.

All seven are properties of the interface, none is a property of the task, and
that is the whole selection criterion: an adaptation that encodes something
about one goal pose would not transfer, and a search over it would be
overfitting with extra steps.
"""


class ActionSource(Protocol):
    """Whatever proposes joint targets: a controller, a replay, a VLA.

    The adaptation applies to this seam, which is why the same candidate can
    be evaluated against a scripted move and against a policy. A source
    proposes where it wants the joints to be; it never decides how fast they
    get there.
    """

    def reset(self) -> None:
        """Discard any state carried from a previous run."""

    def propose(
        self, state: RobotState, elapsed_s: float
    ) -> Sequence[float]:
        """Propose the joint positions this instant is aiming at."""

    def finished(self, state: RobotState) -> bool:
        """Whether this source considers its action complete."""


class GoalActionSource:
    """The trivial source: hold the goal pose up as the target, forever.

    It makes the harness runnable with no policy present, which matters more
    than its simplicity suggests: it is the control condition. A candidate's
    score is only interpretable against the same candidate driving this
    source, because anything a learned policy contributes is then held fixed
    at nothing.
    """

    def __init__(self, goal: JointPoseGoal) -> None:
        self._goal = goal

    @property
    def goal(self) -> JointPoseGoal:
        return self._goal

    def reset(self) -> None:
        """Nothing to discard: this source is memoryless by construction."""

    def propose(
        self, state: RobotState, elapsed_s: float
    ) -> Sequence[float]:
        return self._goal.target_joint_positions_rad

    def finished(self, state: RobotState) -> bool:
        return self._goal.reached(state.joint_positions_rad)


STALL_TOLERANCE_FRACTION = 1.0
"""Net movement below this multiple of the goal tolerance is not progress.

The first version of this check compared *consecutive* measurements against a
fixed 1e-5 rad epsilon, measured on a noiseless robot. Under a regime that
perturbs sensors it never fired once: the default contact regime reports up to
0.002 rad of sensor noise, so consecutive readings differ by ~0.006 rad --
167 times the epsilon -- and a robot standing perfectly still looked like one
travelling briskly. Every converged-but-wrong run therefore burned its whole
step budget and was aborted for a time limit, which is a safety violation, and
the search abandoned exactly the faults it exists to find.

Two changes make it survive noise. The comparison is *net displacement across a
window* rather than per-step delta, because sensor noise is zero-mean and
cancels over a window while real motion accumulates. And the threshold is the
goal's own tolerance rather than a constant, because tolerance is by definition
the resolution at which this goal is worth arguing about: an arm that has not
moved a tolerance's worth in half a second is not approaching anything. It
scales with the goal instead of having to be re-measured per skill.

This holds only while the window's noise floor stays below the tolerance. On
the default regime that margin is roughly 2x (0.0085 rad of 3-sigma noise
against a 0.02 rad tolerance). A noisier robot or a tighter goal would need a
longer window, and the honest failure mode is declaring a stall while still
crawling -- which reports a completed run with an unmet postcondition, not a
false success.
"""

STALL_STEPS = 25
"""How many still periods make a stall rather than a slow moment.

Half a second at 50Hz. Long enough that a joint reversing direction or crossing
a momentary zero is not mistaken for a stopped one, short enough that a run
which has genuinely converged short of its goal is reported as such instead of
being left to expire against the supervisor's clock.
"""


class AdaptedJointRuntime:
    """Drives a robot from an ``ActionSource`` through one candidate.

    Interchangeable with ``DeterministicJointRuntime`` from the loop's point of
    view, deliberately: the loop's guarantees must not depend on whether an
    adaptation is in force. Same single-use discipline, same postcondition
    honesty, same calibrated step bound. With the identity candidate and a
    ``GoalActionSource`` it commands exactly the same setpoints the
    deterministic runtime does, which is what makes the identity a usable
    baseline rather than an approximation of one.

    The candidate shapes the target. It never shapes the bound: the effective
    per-step limit is the calibrated one scaled by at most 1.0, and the
    setpoint leash stays as measured. An adaptation that could loosen either
    would be able to buy a success with authority it was never granted, and
    the resulting evidence would be about a robot nobody admitted.
    """

    def __init__(
        self,
        robot: RobotInterface,
        source: ActionSource,
        candidate: AdaptationCandidate,
        goal: JointPoseGoal,
        command_rate: CommandRateCalibration,
        envelope: SafetyEnvelope,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if not command_rate.fits_within(envelope):
            raise ValueError(
                f"commanding {command_rate.commanded_rate_rps} rad/s at "
                f"{command_rate.control_frequency_hz}Hz was measured on "
                f"{command_rate.measured_on} to peak at "
                f"{command_rate.peak_joint_velocity_rps:.4f} rad/s, above the "
                f"envelope limit {envelope.max_joint_velocity_rps} rad/s; no "
                "adaptation can make that admissible, so it is refused "
                "before anything moves"
            )
        tolerance_floor = command_rate.minimum_goal_tolerance_rad
        if goal.tolerance_rad < tolerance_floor:
            raise ValueError(
                f"goal for {goal.skill_version_id!r} declares a tolerance of "
                f"{goal.tolerance_rad} rad, tighter than the "
                f"{tolerance_floor:.4f} rad floor implied by the "
                f"{command_rate.settled_error_rad:.4f} rad resting error "
                f"measured on {command_rate.measured_on}; every candidate "
                "would fail verification for a robot that arrived, and the "
                "search would be scoring the tolerance"
            )

        self._robot = robot
        self._source = source
        self._candidate = candidate
        self._goal = goal
        self._command_rate = command_rate
        self._frequency_hz = command_rate.control_frequency_hz
        self._max_lead_rad = command_rate.max_lead_rad
        self._clock = clock if clock is not None else time.monotonic

        # Read once, at construction, so a candidate cannot be re-interpreted
        # partway through a motion.
        self._rate_scale = _effective_rate_scale(candidate)
        self._max_step_rad = command_rate.max_step_rad * self._rate_scale
        self._gain_scale = candidate.value(GENE_GAIN_SCALE.name)
        self._bias_rad = candidate.value(GENE_BIAS_RAD.name)
        self._alpha = _effective_smoothing(candidate)
        self._lead_steps = max(
            0.0, candidate.value(GENE_LATENCY_COMPENSATION_STEPS.name)
        )
        self._deadband_rad = max(0.0, candidate.value(GENE_DEADBAND_RAD.name))
        self._settle_gain = candidate.value(GENE_SETTLE_GAIN.name)

        self._started_at: Optional[float] = None
        self._setpoint: Optional[tuple[float, ...]] = None
        self._aborted = False
        self._finished = False
        self._reached = False
        self._stalled = False
        self._window: deque[tuple[float, ...]] = deque(maxlen=STALL_STEPS + 1)
        self._initial_residual_rad: Optional[float] = None
        self._stall_threshold_rad = goal.tolerance_rad * STALL_TOLERANCE_FRACTION

    @property
    def candidate(self) -> AdaptationCandidate:
        """The adaptation this run is a measurement of."""
        return self._candidate

    @property
    def goal(self) -> JointPoseGoal:
        return self._goal

    @property
    def max_step_rad(self) -> float:
        """The largest joint change this run will ever command in one step."""
        return self._max_step_rad

    @property
    def max_lead_rad(self) -> float:
        """How far ahead of measurement a setpoint may sit. Not adaptable."""
        return self._max_lead_rad

    @property
    def command_rate(self) -> CommandRateCalibration:
        """The measurement this runtime's bound rests on."""
        return self._command_rate

    def goal_for(self, selection: SkillSelection) -> JointPoseGoal:
        """Confirm the selection is the one this runtime was built for."""
        if selection.skill_version_id != self._goal.skill_version_id:
            raise KeyError(
                f"this runtime carries the goal for "
                f"{self._goal.skill_version_id!r} and was asked to run "
                f"{selection.skill_version_id!r}; it will not improvise a "
                "physical target for an unrecognised request"
            )
        return self._goal

    def required_duration_s(self, selection: SkillSelection) -> float:
        """Estimate the move's duration under this candidate.

        The smoothing weight is applied to the estimate, not ignored: a
        first-order filter approaches the commanded rate asymptotically, so a
        smoothed candidate needs proportionally more periods to cover the same
        distance. Leaving it out would report a duration only the identity can
        achieve, and a caller checking a skill's time limit would clear a run
        that cannot finish.
        """
        goal = self.goal_for(selection)
        positions = self._robot.read_state().joint_positions_rad
        self._require_matching_width(positions)
        largest = max(
            (
                abs(target + self._bias_rad - current)
                for current, target in zip(
                    positions, goal.target_joint_positions_rad
                )
            ),
            default=0.0,
        )
        if largest <= goal.tolerance_rad:
            return 0.0
        steps = math.ceil(
            largest / (self._max_step_rad * (1.0 - self._alpha))
        )
        # Plus the stall window. This method answers "how long until this
        # runtime can report a verdict", not "how long should the motion take",
        # and the two differ by exactly the evidence a stalled run needs.
        #
        # The distinction is load-bearing rather than pedantic. The caller uses
        # this to size a step budget, and a budget that covered only the ideal
        # motion would expire while a short-settling run was still accumulating
        # the still steps that prove it settled. The supervisor would then abort
        # for a time limit -- a safety violation, which quarantines the
        # configuration -- when the truthful outcome was a completed motion that
        # missed its goal. That mislabelling is the difference between a
        # candidate the search can rank and a candidate that halts the campaign,
        # so an adaptation with a real interface fault would be reported as a
        # broken envelope and the search would abandon the one case it exists to
        # investigate.
        return (steps + STALL_STEPS) / self._frequency_hz

    def observe(self) -> Observation:
        return self._observation(self._robot.read_state())

    def start(self, selection: SkillSelection) -> None:
        if self._started_at is not None:
            raise RuntimeError(
                "this runtime already ran a skill; construct a new one per "
                "candidate evaluation so motion state cannot leak between "
                "the runs a score is averaged over"
            )
        self.goal_for(selection)
        state = self._robot.read_state()
        self._require_matching_width(state.joint_positions_rad)
        self._source.reset()
        # The ramp and the low-pass share one state, seeded from where the
        # robot actually is. Every later setpoint is integrated from this one,
        # so the commanded rate stays a property of the command.
        self._setpoint = tuple(state.joint_positions_rad)
        self._started_at = self._clock()
        if self._initial_residual_rad is None:
            measured = self._robot.read_state().joint_positions_rad
            self._initial_residual_rad = max(
                (
                    abs(target - current)
                    for current, target in zip(
                        measured, self._goal.target_joint_positions_rad
                    )
                ),
                default=0.0,
            )

    def step(self) -> RuntimeStep:
        if self._started_at is None or self._setpoint is None:
            raise RuntimeError("step() was called before start()")
        if self._aborted:
            raise RuntimeError(
                "this runtime was aborted and will not command motion again"
            )
        if self._finished:
            raise RuntimeError(
                "this runtime already reported completion; it will not "
                "command further motion"
            )

        measured = self._robot.read_state().joint_positions_rad
        self._require_matching_width(measured)
        target = self._shaped_target(measured)
        # The candidate shapes the target; the calibration alone decides how
        # far one period may travel. Rate limiting therefore sits between the
        # two, and everything downstream of it can only command less motion.
        limited = bounded_waypoint(
            self._setpoint,
            measured,
            target,
            self._max_step_rad,
            self._max_lead_rad,
        )
        waypoint = self._shaped_stream(measured, limited)
        self._setpoint = waypoint
        self._robot.command_joint_positions(waypoint)

        state = self._robot.read_state()
        self._require_matching_width(state.joint_positions_rad)
        self._reached = self._goal.reached(state.joint_positions_rad)
        # The source may declare itself done while the goal is unmet. That is
        # a completed motion with a failed verification, and reporting it as
        # anything else would hide the most informative outcome the harness
        # can produce.
        # A converged-but-wrong motion is the most informative thing this
        # harness produces, and it has to be reported as a finished motion to
        # be reported at all. Left to run, a robot that has stopped short of
        # its goal keeps being stepped until the supervisor's duration guard
        # fires, and that abort is classified as a safety violation: it
        # quarantines the configuration and truncates the campaign to one
        # attempt. So a systematic interface fault -- the exact fault this
        # search exists to correct -- would arrive at the objective wearing
        # the costume of a broken envelope, and be disqualified instead of
        # ranked. Nothing was breached; the arm settled in the wrong place.
        # Detecting that here turns it into a completed run with an unmet
        # postcondition, which the loop already knows how to record and the
        # objective already knows how to rank.
        # Net displacement across the window, not per-step delta: sensor noise
        # is zero-mean and cancels over the window, while real motion adds up.
        self._window.append(state.joint_positions_rad)
        self._stalled = False
        if len(self._window) == self._window.maxlen:
            oldest = self._window[0]
            travelled = max(
                (
                    abs(now - before)
                    for now, before in zip(state.joint_positions_rad, oldest)
                ),
                default=0.0,
            )
            self._stalled = travelled <= self._stall_threshold_rad

        complete = (
            self._reached or self._source.finished(state) or self._stalled
        )
        if complete:
            self._finished = True
        return RuntimeStep(
            observation=self._observation(state), complete=complete
        )

    def abort(self, directive: AbortDirective) -> None:
        self._aborted = True
        self._robot.hold()

    @property
    def residual_rad(self) -> Optional[float]:
        """How far the worst joint still is from the goal, if a run happened.

        The one number that distinguishes a near miss from an inert robot, and
        the reason it is exposed at all: a postcondition is a boolean, so a run
        that stopped a hair short and a run that never moved report identically.
        On a flat success surface -- every candidate failing -- that boolean
        gives a search nothing to descend, and UCT degenerates into a random
        walk over a plateau.

        It is deliberately not a success criterion. Verification stays boolean
        and stays with the postconditions; this is a *diagnostic* that lets an
        objective award bounded partial credit for getting closer, so the search
        has a gradient to follow toward the region where successes exist.

        ``None`` before the first step: a run that never observed anything has
        no residual, and reporting zero would read as a robot already at its
        goal.
        """
        if not self._window:
            return None
        latest = self._window[-1]
        return max(
            (
                abs(target - current)
                for current, target in zip(
                    latest, self._goal.target_joint_positions_rad
                )
            ),
            default=0.0,
        )

    @property
    def initial_residual_rad(self) -> Optional[float]:
        """The same gap measured before the motion started.

        Progress is only interpretable as a fraction of the distance the run
        set out to cover; the same 0.1 rad residual is near-total failure on a
        0.12 rad move and a rounding error on a 2 rad one.
        """
        return self._initial_residual_rad

    def postconditions(self) -> Mapping[str, bool]:
        """Report only what reaching the goal pose demonstrates."""
        if self._started_at is None:
            return {}
        reached = self._reached and not self._aborted
        return {condition: reached for condition in self._goal.satisfies}

    def _shaped_target(
        self, measured: Sequence[float]
    ) -> tuple[float, ...]:
        """Apply the candidate to what the source proposed.

        Ordering matters and is not arbitrary. The bias corrects the target
        before anything measures error against it, because a bias applied
        afterwards would be a bias on the command rather than on the frame.
        Gain and lead then act on that error, so they shape an approach to a
        corrected target rather than to a wrong one.

        This is where the candidate's account of *where to go* ends. Smoothing
        and the deadband describe the setpoint stream instead, and they are
        applied in ``_shaped_stream`` after the rate limit for that reason.
        """
        assert self._setpoint is not None
        proposed = tuple(
            float(value)
            for value in self._source.propose(
                self._robot.read_state(), self._elapsed_s()
            )
        )
        self._require_matching_width(proposed)

        tolerance = self._goal.tolerance_rad
        shaped: list[float] = []
        for previous, current, raw in zip(
            self._setpoint, measured, proposed
        ):
            error = (raw + self._bias_rad) - current
            gain = self._gain_scale
            if abs(error) <= tolerance:
                gain *= self._settle_gain
            commanded = current + gain * error
            if self._lead_steps and error:
                lead = self._lead_steps * self._max_step_rad
                commanded += lead if error > 0 else -lead
            shaped.append(commanded)
        return tuple(shaped)

    def _shaped_stream(
        self, measured: Sequence[float], limited: Sequence[float]
    ) -> tuple[float, ...]:
        """Soften and suppress the already-bounded setpoint increment.

        Smoothing and the deadband act here, downstream of the rate limit,
        because each is a statement about the setpoint stream rather than
        about where the motion is headed. Applied to the target they would be
        invisible for most of a move: any target further away than one
        period's travel saturates the limiter, and a filtered saturated target
        is still saturated, so a candidate would be scored for a knob that
        never acted. Downstream both can only ever remove motion, which is the
        same reason the calibrated step bound survives them untouched.
        """
        assert self._setpoint is not None
        shaped: list[float] = []
        for previous, current, bounded in zip(
            self._setpoint, measured, limited
        ):
            increment = (bounded - previous) * (1.0 - self._alpha)
            if abs(increment) < self._deadband_rad:
                increment = 0.0
            # The leash is re-applied rather than inherited from the bounded
            # waypoint: the robot has moved since the previous setpoint was
            # authored, and a suppressed increment must not leave the stream
            # stranded outside what the calibration measured.
            shaped.append(
                min(
                    max(previous + increment, current - self._max_lead_rad),
                    current + self._max_lead_rad,
                )
            )
        return tuple(shaped)

    def _observation(self, state: RobotState) -> Observation:
        return Observation(
            elapsed_s=self._elapsed_s(),
            age_s=state.age_s,
            joint_velocity_rps=state.joint_velocity_rps,
            end_effector_force_n=state.end_effector_force_n,
            end_effector_position_m=state.end_effector_position_m,
            guardian_present=state.guardian_present,
            estop_engaged=state.estop_engaged,
            estop_reachable=state.estop_reachable,
            workspace_clear=state.workspace_clear,
        )

    def _elapsed_s(self) -> float:
        if self._started_at is None:
            return 0.0
        return max(0.0, self._clock() - self._started_at)

    def _require_matching_width(self, positions_rad: Sequence[float]) -> None:
        expected = len(self._goal.target_joint_positions_rad)
        if len(positions_rad) != expected:
            raise ValueError(
                f"goal for {self._goal.skill_version_id!r} targets "
                f"{expected} joints but {len(positions_rad)} were reported; "
                "an adaptation cannot be applied across a width mismatch"
            )


def _effective_rate_scale(candidate: AdaptationCandidate) -> float:
    """The rate scale as it will actually be applied.

    Capped at 1.0 here rather than trusted from the gene's range, because the
    range belongs to whichever space proposed the candidate and this bound
    belongs to the envelope. A candidate constructed by hand, deserialised
    from an old record, or proposed by a component with a wider space can all
    ask for more than the calibration measured; none of them gets it.
    """
    requested = candidate.value(GENE_RATE_LIMIT_SCALE.name)
    return min(1.0, max(_MIN_EFFECTIVE_RATE_SCALE, requested))


def _effective_smoothing(candidate: AdaptationCandidate) -> float:
    """The smoothing weight as it will actually be applied."""
    requested = candidate.value(GENE_SMOOTHING_ALPHA.name)
    return min(_MAX_EFFECTIVE_SMOOTHING, max(0.0, requested))
