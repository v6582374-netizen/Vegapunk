"""The experiment's memory: generations, plans, predictions, results, orders.

The loop's honesty does not live in its algorithms; it lives in what may be
written down, when, and by whom. This module owns those records and the ledger
that governs them. Everything here is append-only: a record is created whole,
sealed by being accepted, and never edited afterwards. Where the lower layers
refuse a bad frame, this layer refuses a bad *history*.

``Condition``          one point in the condition space, hashable and named
``BenchConfiguration`` the frozen physical arrangement a generation freezes
``Generation``         one frozen bench; evidence never crosses its boundary
``BatchPlan``          the pre-registration: sealed before the first episode
``Prediction``         what the predictive node staked, before reality answered
``EpisodeEvidence``    what one episode amounts to, with every distinction kept
``CalibrationScore``   how the node's predictions fared against real anchors
``BatchResult``        one batch, sealed, with plan and prediction side by side
``ReliabilityEnvelope`` where the frozen policy works, with provenance
``WorkOrder``          the loop's one output it cannot execute itself
``Campaign``           the ledger, and the rules for what it accepts

Two rules do most of the work
-----------------------------
**Pre-registration before execution.** A plan is sealed before its first
episode, and the next plan can only be sealed after the prior sealed plan has
a result. Without that ordering, "the loop adapted to evidence" is
after-the-fact narration; with it, the claim is auditable history.

**Samples never pool across generations.** A generation is one frozen bench --
fixture, object, witness pose and calibration, lighting, policy identity,
invocation protocol. An environment change reshapes the field being measured,
so confirming a work order seals the old generation and opens a new one, and
``envelope`` will only ever aggregate inside one. Old evidence stays readable
forever; it just stops being current.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from vegapunk.operation.trace import (
    OUTCOME_SUCCEEDED,
    TRACE_OUTCOMES,
)

SOURCE_REAL = "real"
SOURCE_PREDICTED = "predicted"

_SOURCES = frozenset({SOURCE_REAL, SOURCE_PREDICTED})

EXECUTION_COMPLETED = "completed"
EXECUTION_HELD = "held"
EXECUTION_FAULT = "fault"

_EXECUTIONS = frozenset({EXECUTION_COMPLETED, EXECUTION_HELD, EXECUTION_FAULT})

STOP_COMPLETED = "completed"
STOP_CIRCUIT_BREAKER = "stopped_circuit_breaker"
STOP_AWAITING_HUMAN = "stopped_awaiting_human"

_STOPS = frozenset({STOP_COMPLETED, STOP_CIRCUIT_BREAKER, STOP_AWAITING_HUMAN})


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Condition:
    """One point in the condition space: named axes, hashable values.

    Hashable because the whole loop is a search over these points -- the
    designer counts failures per condition, the node keeps a table keyed by
    condition, the envelope has one cell per condition -- and a point that
    cannot be a dictionary key cannot be searched over.
    """

    axes: tuple[tuple[str, object], ...]

    def __post_init__(self) -> None:
        if not self.axes:
            raise ValueError("a condition with no axes describes nothing")
        for name, value in self.axes:
            if not str(name).strip():
                raise ValueError("every condition axis must be named")
            if not isinstance(value, (str, int, float, bool)):
                raise ValueError(
                    f"axis {name!r} carries an unhashable value {value!r}"
                )
        object.__setattr__(self, "axes", tuple(sorted(self.axes)))

    @classmethod
    def of(cls, **axes: object) -> "Condition":
        return cls(axes=tuple(sorted(axes.items())))

    @property
    def label(self) -> str:
        return " ".join(f"{name}={value}" for name, value in self.axes)


@dataclass(frozen=True)
class BenchConfiguration:
    """The physical arrangement one generation freezes, named field by field.

    Everything that would make two episodes incomparable if it silently
    changed. The digest is what a Generation is created from, so a fixture
    swap cannot leave prior samples looking current.
    """

    fixture: str
    object_identity: str
    witness_pose_digest: str
    lighting_protocol: str
    policy_identity: str
    invocation_protocol: str

    def __post_init__(self) -> None:
        for label in (
            "fixture",
            "object_identity",
            "witness_pose_digest",
            "lighting_protocol",
            "policy_identity",
            "invocation_protocol",
        ):
            if not getattr(self, label).strip():
                raise ValueError(
                    f"a bench configuration must state its {label}; an "
                    "unstated arrangement cannot be frozen"
                )

    def digest(self) -> str:
        return _digest(
            {
                "fixture": self.fixture,
                "object_identity": self.object_identity,
                "witness_pose_digest": self.witness_pose_digest,
                "lighting_protocol": self.lighting_protocol,
                "policy_identity": self.policy_identity,
                "invocation_protocol": self.invocation_protocol,
            }
        )


@dataclass(frozen=True)
class Generation:
    """One frozen bench configuration. Batches accumulate inside it.

    ``work_order_id`` is empty only for the founding generation: every later
    one exists because a named human confirmed a specific work order, and the
    link is what makes "the bench changed" an auditable event rather than a
    quiet afternoon with an allen key.
    """

    generation_id: str
    configuration: BenchConfiguration
    opened_by: str
    opened_at: datetime
    work_order_id: str = ""
    predecessor_id: str = ""

    def __post_init__(self) -> None:
        if not self.generation_id.strip():
            raise ValueError("a generation must be identifiable")
        if not self.opened_by.strip():
            raise ValueError("a generation is opened by a named human")


@dataclass(frozen=True)
class BatchPlan:
    """The pre-registration. Immutable; results attach to it, never edit it.

    ``real_conditions`` are the points the real bench will visit;
    ``predicted_conditions`` are handed to imagination only, and only a
    calibrated node earns them (the loop enforces that, because the plan
    cannot see the node's score). ``real_anchor_count`` can never be zero:
    a batch with no real episode yields no conclusion, whatever was imagined.
    """

    plan_id: str
    generation_id: str
    objective: str
    real_conditions: tuple[Condition, ...]
    predicted_conditions: tuple[Condition, ...]
    real_anchor_count: int
    predictive_node_version: str
    confidence_threshold: float
    selection_rationale: str
    expected_outcome: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise ValueError("a plan must be identifiable")
        if not self.generation_id.strip():
            raise ValueError("a plan belongs to exactly one generation")
        if not self.objective.strip():
            raise ValueError("a plan states its research objective")
        if not self.real_conditions:
            raise ValueError(
                "a plan with no real conditions is a purely imagined batch, "
                "which yields no conclusion"
            )
        if self.real_anchor_count < 1:
            raise ValueError(
                "real anchors are mandatory in every batch; a plan may not "
                "allocate zero"
            )
        if self.real_anchor_count > len(self.real_conditions):
            raise ValueError(
                f"the plan allocates {self.real_anchor_count} anchors but "
                f"only {len(self.real_conditions)} real conditions"
            )
        if not self.predictive_node_version.strip():
            raise ValueError(
                "a plan names the predictive-node version it was designed "
                "against"
            )
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be within [0, 1]")
        if not self.selection_rationale.strip():
            raise ValueError("a plan states why these conditions were chosen")
        if not self.expected_outcome.strip():
            raise ValueError(
                "a plan pre-registers its expected outcome; without it, "
                "adaptation is after-the-fact narration"
            )
        object.__setattr__(
            self, "real_conditions", tuple(self.real_conditions)
        )
        object.__setattr__(
            self, "predicted_conditions", tuple(self.predicted_conditions)
        )


@dataclass(frozen=True)
class Prediction:
    """What the node staked on one condition, recorded before reality answered.

    ``confidence`` is the node's own stated belief and is the one place in
    this package a probability is welcome; ``uncertainty`` is its complement,
    kept explicit because a node that cannot say how unsure it is cannot be
    scored for saying so.
    """

    plan_id: str
    condition: Condition
    outcome: str
    confidence: float
    node_version: str
    predicted_observations: tuple[str, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise ValueError("a prediction belongs to a plan")
        if self.outcome not in TRACE_OUTCOMES:
            raise ValueError(
                f"a predicted outcome must be one of {sorted(TRACE_OUTCOMES)}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        if not self.node_version.strip():
            raise ValueError("a prediction names the node version that made it")
        object.__setattr__(
            self, "predicted_observations", tuple(self.predicted_observations)
        )

    @property
    def uncertainty(self) -> float:
        return 1.0 - self.confidence


@dataclass(frozen=True)
class EpisodeEvidence:
    """What one episode amounts to, with every distinction kept.

    ``execution`` (did the run complete, hold, or fault) and ``outcome`` (what
    the witnessed trace adjudicated) are separate axes on purpose: a held run
    with a beautiful trace is still a held run, and collapsing the two is how
    a failure gets laundered into a clean success rate.
    """

    episode_id: str
    plan_id: str
    generation_id: str
    condition: Condition
    execution: str
    outcome: str
    outcome_detail: str
    reset_confirmed: bool
    reset_witnessed: bool
    witness_identity: str
    source: str = SOURCE_REAL

    def __post_init__(self) -> None:
        if not self.episode_id.strip():
            raise ValueError("evidence names its episode")
        if self.execution not in _EXECUTIONS:
            raise ValueError(
                f"execution must be one of {sorted(_EXECUTIONS)}, got "
                f"{self.execution!r}"
            )
        if self.outcome not in TRACE_OUTCOMES:
            raise ValueError(
                f"outcome must be one of {sorted(TRACE_OUTCOMES)}, got "
                f"{self.outcome!r}"
            )
        if self.source not in _SOURCES:
            raise ValueError(
                f"source must be one of {sorted(_SOURCES)}, got "
                f"{self.source!r}"
            )
        if (
            self.execution != EXECUTION_COMPLETED
            and self.outcome == OUTCOME_SUCCEEDED
        ):
            raise ValueError(
                f"an episode whose execution was {self.execution!r} cannot "
                "carry a succeeded outcome; a held or faulted run is never a "
                "completed success"
            )

    @property
    def success(self) -> bool:
        """True only for a real, completed, trace-adjudicated success."""
        return (
            self.source == SOURCE_REAL
            and self.execution == EXECUTION_COMPLETED
            and self.outcome == OUTCOME_SUCCEEDED
        )


@dataclass(frozen=True)
class CalibrationScore:
    """How one node version's predictions fared against real anchors."""

    node_version: str
    scored: int
    matched: int

    def __post_init__(self) -> None:
        if not self.node_version.strip():
            raise ValueError("a score names the node version it scores")
        if self.scored < 0 or self.matched < 0 or self.matched > self.scored:
            raise ValueError(
                f"{self.matched} matches out of {self.scored} scored is not "
                "a possible score"
            )

    @property
    def accuracy(self) -> Optional[float]:
        """``None`` when nothing was scored; unscored is not the same as wrong."""
        if self.scored == 0:
            return None
        return self.matched / self.scored


@dataclass(frozen=True)
class BatchResult:
    """One batch, sealed, with predictions and reality side by side.

    ``anchored`` is stored rather than derived at read time so that an
    unanchored batch is visibly marked in the record itself; its consistency
    with the episode list is checked here so it cannot be marked falsely.
    """

    plan_id: str
    generation_id: str
    episodes: tuple[EpisodeEvidence, ...]
    predictions: tuple[Prediction, ...]
    calibration: CalibrationScore
    stop: str
    stop_detail: str
    anchored: bool
    sealed_at: datetime

    def __post_init__(self) -> None:
        if self.stop not in _STOPS:
            raise ValueError(
                f"stop must be one of {sorted(_STOPS)}, got {self.stop!r}"
            )
        object.__setattr__(self, "episodes", tuple(self.episodes))
        object.__setattr__(self, "predictions", tuple(self.predictions))
        real = any(
            episode.source == SOURCE_REAL for episode in self.episodes
        )
        if self.anchored != real:
            raise ValueError(
                "anchored must state whether any real episode ran; the flag "
                "and the episode list disagree"
            )

    @property
    def success_count(self) -> int:
        return sum(1 for episode in self.episodes if episode.success)


@dataclass(frozen=True)
class EnvelopeCell:
    """One condition's evidence inside one generation."""

    condition: Condition
    samples: int
    successes: int

    def __post_init__(self) -> None:
        if self.samples <= 0:
            raise ValueError("a cell exists only where evidence exists")
        if not 0 <= self.successes <= self.samples:
            raise ValueError(
                f"{self.successes} successes in {self.samples} samples is "
                "not possible"
            )

    @property
    def rate(self) -> float:
        return self.successes / self.samples

    @property
    def interval(self) -> tuple[float, float]:
        """The 95% Wilson score interval: the uncertainty a small n carries.

        Chosen over the normal approximation because envelope cells routinely
        hold single-digit samples, exactly where the normal interval lies.
        """
        z = 1.959964
        n = float(self.samples)
        p = self.rate
        denominator = 1.0 + z * z / n
        centre = (p + z * z / (2.0 * n)) / denominator
        margin = (
            z
            * ((p * (1.0 - p) / n + z * z / (4.0 * n * n)) ** 0.5)
            / denominator
        )
        return (max(0.0, centre - margin), min(1.0, centre + margin))


@dataclass(frozen=True)
class ReliabilityEnvelope:
    """Where the frozen policy works, with the provenance that makes it usable.

    Not "85%" but: this generation, this policy, this witness, these
    conditions, this many samples, this interval. The scalar without the
    provenance is the legend this loop exists to replace.
    """

    generation_id: str
    policy_identity: str
    witness_identity: str
    cells: tuple[EnvelopeCell, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "cells", tuple(self.cells))

    @property
    def sample_count(self) -> int:
        return sum(cell.samples for cell in self.cells)

    @property
    def success_count(self) -> int:
        return sum(cell.successes for cell in self.cells)

    def reliable_cells(self, at: float) -> tuple[EnvelopeCell, ...]:
        return tuple(cell for cell in self.cells if cell.rate >= at)


@dataclass(frozen=True)
class WorkOrder:
    """A proposed physical change, staking the gain it predicts.

    The expected gain is the generation-level pre-registration: install the
    change, run the new generation's first batch, and a wrong work order is
    wrong in the open. An order that stakes nothing is a wish, not a
    hypothesis, and is refused at construction.
    """

    order_id: str
    generation_id: str
    proposed_change: str
    expected_gain: str
    cost_risk: str
    motivating_evidence: tuple[str, ...]
    proposed_at: datetime

    def __post_init__(self) -> None:
        if not self.order_id.strip():
            raise ValueError("a work order must be identifiable")
        if not self.generation_id.strip():
            raise ValueError("a work order names the generation it came from")
        if not self.proposed_change.strip():
            raise ValueError("a work order proposes a concrete change")
        if not self.expected_gain.strip():
            raise ValueError(
                "a work order must stake its expected gain; an unstaked "
                "change is not a falsifiable experiment"
            )
        if not self.cost_risk.strip():
            raise ValueError("a work order states its cost and risk")
        object.__setattr__(
            self, "motivating_evidence", tuple(self.motivating_evidence)
        )


@dataclass(frozen=True)
class WorkOrderConfirmation:
    """A named human's statement that the physical change was executed."""

    order_id: str
    confirmed_by: str
    confirmed_at: datetime
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.confirmed_by.strip():
            raise ValueError("a work order is confirmed by a named human")


@dataclass(frozen=True)
class GenerationSeal:
    """The record that a generation stopped counting as current evidence."""

    generation_id: str
    sealed_by: str
    sealed_at: datetime
    work_order_id: str


@dataclass(frozen=True)
class EffectivenessReport:
    """The two curves, kept apart. Merging them is the lie this type prevents.

    ``within_generation`` is success per batch on a fixed bench -- optimising
    the use of a fixed field, which has a ceiling. ``across_generations`` is
    the reliable-cell count per generation -- environment shaping changing the
    field itself, which is the stronger claim.
    """

    within_generation: tuple[tuple[str, tuple[float, ...]], ...]
    across_generations: tuple[tuple[str, int], ...]


class Campaign:
    """The append-only ledger, and the rules for what it accepts.

    Deterministic code with no opinion about robots: it accepts or refuses
    records. Every refusal here is one way a history could have been faked --
    a plan registered after its episodes, a result for a plan nobody sealed,
    a generation opened without a confirmed work order, samples pooled across
    benches -- made structurally impossible instead of procedurally forbidden.
    """

    def __init__(
        self, *, clock: Optional[Callable[[], datetime]] = None
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._generations: list[Generation] = []
        self._seals: dict[str, GenerationSeal] = {}
        self._plans: list[BatchPlan] = []
        self._predictions: list[Prediction] = []
        self._results: dict[str, BatchResult] = {}
        self._orders: dict[str, WorkOrder] = {}
        self._confirmations: dict[str, WorkOrderConfirmation] = {}

    # -- generations --------------------------------------------------------

    def open_founding_generation(
        self, configuration: BenchConfiguration, *, opened_by: str
    ) -> Generation:
        """Open the first generation. Every later one needs a work order."""
        if self._generations:
            raise ValueError(
                "a generation already exists; a new one is opened only by "
                "confirming a work order, so the bench change is on record"
            )
        return self._open(
            configuration, opened_by=opened_by, work_order_id="",
            predecessor_id="",
        )

    def _open(
        self,
        configuration: BenchConfiguration,
        *,
        opened_by: str,
        work_order_id: str,
        predecessor_id: str,
    ) -> Generation:
        generation = Generation(
            generation_id=(
                f"gen-{len(self._generations) + 1}-{configuration.digest()}"
            ),
            configuration=configuration,
            opened_by=opened_by,
            opened_at=self._clock(),
            work_order_id=work_order_id,
            predecessor_id=predecessor_id,
        )
        self._generations.append(generation)
        return generation

    @property
    def current_generation(self) -> Generation:
        if not self._generations:
            raise LookupError("no generation has been opened")
        return self._generations[-1]

    def generation_sealed(self, generation_id: str) -> bool:
        return generation_id in self._seals

    def generations(self) -> tuple[Generation, ...]:
        return tuple(self._generations)

    def _generation(self, generation_id: str) -> Generation:
        for generation in self._generations:
            if generation.generation_id == generation_id:
                return generation
        raise LookupError(f"no generation {generation_id!r} exists")

    # -- plans ---------------------------------------------------------------

    def seal_plan(self, plan: BatchPlan) -> None:
        """Accept a plan as pre-registered. Refused if history forbids it."""
        current = self.current_generation
        if plan.generation_id != current.generation_id:
            raise ValueError(
                f"plan {plan.plan_id!r} targets generation "
                f"{plan.generation_id!r} but the current open generation is "
                f"{current.generation_id!r}; sealed generations accept no "
                "new plans"
            )
        if any(existing.plan_id == plan.plan_id for existing in self._plans):
            raise ValueError(f"plan {plan.plan_id!r} is already sealed")
        unresolved = [
            existing.plan_id
            for existing in self._plans
            if existing.plan_id not in self._results
        ]
        if unresolved:
            raise ValueError(
                f"plan(s) {unresolved} have no sealed result yet; the next "
                "batch may only change after the prior result exists"
            )
        self._plans.append(plan)

    def plan_sealed(self, plan_id: str) -> bool:
        return any(plan.plan_id == plan_id for plan in self._plans)

    def plans(self) -> tuple[BatchPlan, ...]:
        return tuple(self._plans)

    # -- predictions ---------------------------------------------------------

    def record_predictions(self, predictions: Sequence[Prediction]) -> None:
        """Record what the node staked. Only before the plan has a result."""
        for prediction in predictions:
            if not self.plan_sealed(prediction.plan_id):
                raise ValueError(
                    f"prediction targets unsealed plan "
                    f"{prediction.plan_id!r}; predictions are pre-registered "
                    "against a sealed plan"
                )
            if prediction.plan_id in self._results:
                raise ValueError(
                    f"plan {prediction.plan_id!r} already has a result; a "
                    "prediction recorded afterwards is not a prediction"
                )
        self._predictions.extend(predictions)

    def predictions_for(self, plan_id: str) -> tuple[Prediction, ...]:
        return tuple(
            prediction
            for prediction in self._predictions
            if prediction.plan_id == plan_id
        )

    # -- results -------------------------------------------------------------

    def record_result(self, result: BatchResult) -> None:
        if not self.plan_sealed(result.plan_id):
            raise ValueError(
                f"result targets plan {result.plan_id!r}, which was never "
                "sealed; a result without a pre-registered plan is not "
                "evidence"
            )
        if result.plan_id in self._results:
            raise ValueError(
                f"plan {result.plan_id!r} already has a sealed result; "
                "results are never rewritten"
            )
        self._results[result.plan_id] = result

    def result_for(self, plan_id: str) -> Optional[BatchResult]:
        return self._results.get(plan_id)

    def results(self) -> tuple[BatchResult, ...]:
        return tuple(
            self._results[plan.plan_id]
            for plan in self._plans
            if plan.plan_id in self._results
        )

    # -- work orders ----------------------------------------------------------

    def propose_work_order(self, order: WorkOrder) -> None:
        if order.order_id in self._orders:
            raise ValueError(f"work order {order.order_id!r} already exists")
        self._orders[order.order_id] = order

    def confirm_work_order(
        self,
        order_id: str,
        *,
        confirmed_by: str,
        new_configuration: BenchConfiguration,
    ) -> Generation:
        """A named human confirms the change: seal the old bench, open the new.

        This is the loop's one generation-switching path, and it is
        irreversible in the same sense the pour was: the retired evidence
        cannot be made current again. Hence the named human, recorded.
        """
        order = self._orders.get(order_id)
        if order is None:
            raise ValueError(
                f"no work order {order_id!r} was proposed; an unproposed "
                "change cannot open a generation"
            )
        if order_id in self._confirmations:
            raise ValueError(
                f"work order {order_id!r} was already confirmed; a bench is "
                "not rebuilt twice under one order"
            )
        confirmation = WorkOrderConfirmation(
            order_id=order_id,
            confirmed_by=confirmed_by,
            confirmed_at=self._clock(),
        )
        previous = self.current_generation
        self._confirmations[order_id] = confirmation
        self._seals[previous.generation_id] = GenerationSeal(
            generation_id=previous.generation_id,
            sealed_by=confirmed_by,
            sealed_at=confirmation.confirmed_at,
            work_order_id=order_id,
        )
        return self._open(
            new_configuration,
            opened_by=confirmed_by,
            work_order_id=order_id,
            predecessor_id=previous.generation_id,
        )

    def work_orders(self) -> tuple[WorkOrder, ...]:
        return tuple(self._orders.values())

    def confirmation_for(
        self, order_id: str
    ) -> Optional[WorkOrderConfirmation]:
        return self._confirmations.get(order_id)

    # -- analysis --------------------------------------------------------------

    def _evidence_in(
        self, generation_id: str
    ) -> tuple[EpisodeEvidence, ...]:
        return tuple(
            episode
            for result in self.results()
            if result.generation_id == generation_id
            for episode in result.episodes
            if episode.source == SOURCE_REAL
        )

    def envelope(
        self, generation_id: Optional[str] = None
    ) -> ReliabilityEnvelope:
        """The reliability envelope of exactly one generation. Never pooled."""
        generation = self._generation(
            generation_id
            if generation_id is not None
            else self.current_generation.generation_id
        )
        by_condition: dict[Condition, list[EpisodeEvidence]] = {}
        witnesses: set[str] = set()
        for episode in self._evidence_in(generation.generation_id):
            by_condition.setdefault(episode.condition, []).append(episode)
            if episode.witness_identity.strip():
                witnesses.add(episode.witness_identity)
        cells = tuple(
            EnvelopeCell(
                condition=condition,
                samples=len(episodes),
                successes=sum(1 for episode in episodes if episode.success),
            )
            for condition, episodes in sorted(
                by_condition.items(), key=lambda item: item[0].label
            )
        )
        return ReliabilityEnvelope(
            generation_id=generation.generation_id,
            policy_identity=generation.configuration.policy_identity,
            witness_identity=",".join(sorted(witnesses)),
            cells=cells,
        )

    def calibration(self, node_version: str) -> CalibrationScore:
        """The node's accumulated score across every sealed result."""
        scored = 0
        matched = 0
        for result in self.results():
            if result.calibration.node_version != node_version:
                continue
            scored += result.calibration.scored
            matched += result.calibration.matched
        return CalibrationScore(
            node_version=node_version, scored=scored, matched=matched
        )

    def effectiveness(self, *, reliable_at: float = 0.8) -> EffectivenessReport:
        """The two curves. They are never merged into one plot."""
        within: list[tuple[str, tuple[float, ...]]] = []
        across: list[tuple[str, int]] = []
        for generation in self._generations:
            rates: list[float] = []
            for result in self.results():
                if result.generation_id != generation.generation_id:
                    continue
                real = [
                    episode
                    for episode in result.episodes
                    if episode.source == SOURCE_REAL
                ]
                rates.append(
                    sum(1 for episode in real if episode.success) / len(real)
                    if real
                    else 0.0
                )
            within.append((generation.generation_id, tuple(rates)))
            envelope = self.envelope(generation.generation_id)
            across.append(
                (
                    generation.generation_id,
                    len(envelope.reliable_cells(reliable_at)),
                )
            )
        return EffectivenessReport(
            within_generation=tuple(within),
            across_generations=tuple(across),
        )
