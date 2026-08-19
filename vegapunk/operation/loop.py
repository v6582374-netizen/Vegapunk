"""The Experiment Loop: the one seam that owns "next episode" and "next batch".

Everything below this module knows how to run, judge, record or refuse one
episode. Nothing below it knows that another episode follows. This module owns
that knowledge -- the batch, the campaign, the stopping rules -- and nothing
else: it holds no robot joints, produces no 50 Hz ticks, publishes no targets,
and cannot reach the bridge at all. It calls an executor that runs one whole
episode through the existing session chain and hands back what happened.

One batch, in order:

seal the plan -> stake predictions -> per episode: witness the reset, execute,
adjudicate the trace -> score the predictions -> seal the result

``EpisodeRun``             what one executed episode came back as
``EpisodeExecutor``        the seam a real or fake execution path fills
``SessionEpisodeExecutor`` the real one: a fresh OperationSession per episode
``CircuitBreaker``         when a batch stops sampling and starts repeating
``ExperimentLoop``         the composition

What the loop may not do
------------------------
It may not run an episode before the plan is sealed, or from an unconfirmed
reset. It may not turn a held run into a success, a prediction into evidence,
or an unanchored batch into a conclusion. It may not retry forever: the
breaker stops a batch that is chasing a defect rather than sampling an
envelope, and records why it stopped. And it may not clear anything -- a
batch stopped awaiting a human stays stopped until a human acts, exactly as a
latched hold does one layer down.

Sessions are consumed, never reused
-----------------------------------
The executor creates a fresh ``OperationSession`` per episode through a
factory boundary. A held session is over; the next episode is a new session
under a new record, so no run can continue under a record that already
describes a different run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol, Sequence

from vegapunk.operation.campaign import (
    EXECUTION_COMPLETED,
    EXECUTION_FAULT,
    EXECUTION_HELD,
    SOURCE_REAL,
    STOP_AWAITING_HUMAN,
    STOP_CIRCUIT_BREAKER,
    STOP_COMPLETED,
    BatchPlan,
    BatchResult,
    Campaign,
    Condition,
    EpisodeEvidence,
    Prediction,
)
from vegapunk.operation.design import TableBatchDesigner
from vegapunk.operation.policy import Observation
from vegapunk.operation.predict import (
    CalibrationPolicy,
    PredictiveNode,
    score_predictions,
)
from vegapunk.operation.session import OperationSession
from vegapunk.operation.trace import (
    OUTCOME_INDETERMINATE,
    OUTCOME_SUCCEEDED,
    ResetWitness,
    TraceFact,
    adjudicate,
)

_EXECUTIONS = frozenset(
    {EXECUTION_COMPLETED, EXECUTION_HELD, EXECUTION_FAULT}
)


@dataclass(frozen=True)
class EpisodeRun:
    """What one executed episode came back as: an identity, a fate, a trace."""

    episode_id: str
    execution: str
    trace: tuple[TraceFact, ...]
    witness_identity: str = ""
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.episode_id.strip():
            raise ValueError("an episode run names its episode")
        if self.execution not in _EXECUTIONS:
            raise ValueError(
                f"execution must be one of {sorted(_EXECUTIONS)}, got "
                f"{self.execution!r}"
            )
        object.__setattr__(self, "trace", tuple(self.trace))


class EpisodeExecutor(Protocol):
    """Whatever runs one whole episode and reports back.

    On hardware this is a fresh session driven through the policy server,
    bridge and tracker; in tests it is a deterministic fake. The loop cannot
    tell the difference, which is the point: the loop's rules are proven
    without a robot, and the robot never meets an unproven rule.
    """

    def execute(self, condition: Condition, plan: BatchPlan) -> EpisodeRun:
        """Run one episode under the given condition. May raise; the loop
        records a raise as a fault rather than dying with it."""


@dataclass(frozen=True)
class SessionEpisode:
    """One episode's ingredients, produced fresh by a factory.

    ``observe`` supplies the per-tick observation; ``trace`` is read after the
    run from whatever bench witness adapter watched it. The session is
    single-use by its own contract.
    """

    session: OperationSession
    observe: Callable[[int], Observation]
    ticks: int
    trace: Callable[[], Sequence[TraceFact]]
    witness_identity: str = ""

    def __post_init__(self) -> None:
        if self.ticks < 1:
            raise ValueError("an episode runs at least one tick")


class SessionEpisodeExecutor:
    """The real execution path: one fresh ``OperationSession`` per episode.

    The factory boundary is what keeps the loop honest about sessions: this
    executor never restarts a held session, because it never holds one -- it
    asks the factory for a new composition every time, and the old one is
    sealed history. Ticks are driven here, below the loop, so the loop's
    interface stays free of control-time concepts.
    """

    def __init__(
        self, factory: Callable[[Condition, BatchPlan], SessionEpisode]
    ) -> None:
        self._factory = factory

    def execute(self, condition: Condition, plan: BatchPlan) -> EpisodeRun:
        episode = self._factory(condition, plan)
        execution = EXECUTION_COMPLETED
        detail = ""
        try:
            for tick in range(episode.ticks):
                result = episode.session.step(episode.observe(tick))
                if not result.running:
                    execution = EXECUTION_HELD
                    detail = result.detail
                    break
        except Exception as exc:  # the chain below runs external code
            execution = EXECUTION_FAULT
            detail = f"{type(exc).__name__}: {exc}"
        try:
            trace = tuple(episode.trace())
        except Exception as exc:
            trace = ()
            detail = (detail + "; " if detail else "") + (
                f"trace collection failed: {type(exc).__name__}: {exc}"
            )
        return EpisodeRun(
            episode_id=episode.session.record.episode_id,
            execution=execution,
            trace=trace,
            witness_identity=episode.witness_identity,
            detail=detail,
        )


@dataclass(frozen=True)
class CircuitBreaker:
    """When a batch stops sampling an envelope and starts chasing a defect.

    Consecutive holds or faults mean something in the room is wrong, not that
    the condition is hard; equivalent failures repeating at one condition mean
    the batch has learned what it is going to learn there. Either way the
    batch stops and says why, because a loop that can retry forever can
    manufacture any dataset it likes out of one unknown state.
    """

    max_consecutive_holds: int = 2
    max_equivalent_failures: int = 3

    def __post_init__(self) -> None:
        if self.max_consecutive_holds < 1:
            raise ValueError("the hold limit must be positive")
        if self.max_equivalent_failures < 1:
            raise ValueError("the failure limit must be positive")


class ExperimentLoop:
    """The composition: a whole batch or campaign, and only that.

    Deterministic code. No language model participates here, and none can:
    the loop's inputs are sealed records and its outputs are sealed records,
    with the one motor path buried behind the executor seam.
    """

    def __init__(
        self,
        *,
        campaign: Campaign,
        executor: EpisodeExecutor,
        reset_witness: ResetWitness,
        node: PredictiveNode,
        calibration_policy: Optional[CalibrationPolicy] = None,
        breaker: Optional[CircuitBreaker] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._campaign = campaign
        self._executor = executor
        self._reset_witness = reset_witness
        self._node = node
        self._calibration_policy = calibration_policy or CalibrationPolicy()
        self._breaker = breaker or CircuitBreaker()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run_batch(self, plan: BatchPlan) -> BatchResult:
        """Run one declared batch to a sealed result. The only public verb.

        Sealing the plan is the first act, before any prediction or episode,
        so nothing that happens later can reshape what was claimed. A plan
        that hands conditions to imagination is honoured only if the node's
        accumulated calibration has earned it; otherwise the batch refuses to
        start rather than quietly running fewer real episodes.
        """
        if not self._campaign.plan_sealed(plan.plan_id):
            self._campaign.seal_plan(plan)

        if plan.predicted_conditions:
            earned, why = self._calibration_policy.may_reduce_real_budget(
                self._campaign.calibration(plan.predictive_node_version)
            )
            if not earned:
                raise ValueError(
                    f"plan {plan.plan_id!r} hands "
                    f"{len(plan.predicted_conditions)} condition(s) to the "
                    f"predictive node, which has not earned them: {why}"
                )

        predictions = self._stake_predictions(plan)
        episodes, stop, stop_detail = self._run_episodes(plan)
        result = BatchResult(
            plan_id=plan.plan_id,
            generation_id=plan.generation_id,
            episodes=tuple(episodes),
            predictions=predictions,
            calibration=score_predictions(
                predictions, episodes, node_version=self._node.version
            ),
            stop=stop,
            stop_detail=stop_detail,
            anchored=any(
                episode.source == SOURCE_REAL for episode in episodes
            ),
            sealed_at=self._clock(),
        )
        self._campaign.record_result(result)
        return result

    def run_campaign(
        self, designer: TableBatchDesigner, *, plan_ids: Sequence[str]
    ) -> tuple[BatchResult, ...]:
        """Design, pre-register and run several batches in one generation.

        Work orders the designer emits are proposed to the ledger and then
        wait: only a named human confirming one opens a new generation, so
        the campaign keeps running on the current bench until someone acts.
        A batch stopped awaiting a human stops the campaign for the same
        reason it stopped the batch.
        """
        results: list[BatchResult] = []
        for plan_id in plan_ids:
            generation = self._campaign.current_generation
            design = designer.design(
                plan_id=plan_id,
                generation=generation,
                envelope=self._campaign.envelope(),
                prior_results=self._campaign.results(),
                calibration=self._campaign.calibration(self._node.version),
            )
            for order in design.work_orders:
                self._campaign.propose_work_order(order)
            self._campaign.seal_plan(design.plan)
            result = self.run_batch(design.plan)
            results.append(result)
            if result.stop == STOP_AWAITING_HUMAN:
                break
        return tuple(results)

    # -- one batch, step by step ------------------------------------------------

    def _stake_predictions(self, plan: BatchPlan) -> tuple[Prediction, ...]:
        """Invoke the node on every planned condition, before any episode.

        Mandatory in every batch: a loop that only predicts when convenient
        cannot accumulate the calibration record its authority rule needs.
        """
        staked: list[Prediction] = []
        for condition in dict.fromkeys(
            plan.real_conditions + plan.predicted_conditions
        ):
            forecast = self._node.forecast(condition)
            staked.append(
                Prediction(
                    plan_id=plan.plan_id,
                    condition=condition,
                    outcome=forecast.outcome,
                    confidence=forecast.confidence,
                    node_version=self._node.version,
                    predicted_observations=forecast.predicted_observations,
                    detail=forecast.detail,
                )
            )
        predictions = tuple(staked)
        self._campaign.record_predictions(predictions)
        return predictions

    def _run_episodes(
        self, plan: BatchPlan
    ) -> tuple[list[EpisodeEvidence], str, str]:
        episodes: list[EpisodeEvidence] = []
        consecutive_holds = 0
        equivalent_failures: dict[tuple[Condition, str], int] = {}

        for index, condition in enumerate(plan.real_conditions):
            reset = self._reset_witness.verify()
            if not reset.confirmed:
                return episodes, STOP_AWAITING_HUMAN, (
                    "the reset could not be confirmed before episode "
                    f"{index}: {reset.detail or 'no detail'}; an episode is "
                    "never run from an unknown state"
                )

            try:
                run = self._executor.execute(condition, plan)
            except Exception as exc:
                run = EpisodeRun(
                    episode_id=f"{plan.plan_id}-fault-{index}",
                    execution=EXECUTION_FAULT,
                    trace=(),
                    detail=f"{type(exc).__name__}: {exc}",
                )

            verdict = adjudicate(run.trace, reset=reset)
            outcome, outcome_detail = verdict.outcome, verdict.detail
            if (
                run.execution != EXECUTION_COMPLETED
                and outcome == OUTCOME_SUCCEEDED
            ):
                outcome = OUTCOME_INDETERMINATE
                outcome_detail = (
                    "the witnessed trace was complete but the session ended "
                    f"{run.execution}; a run that did not complete is never "
                    "a completed success"
                )
            if run.detail:
                outcome_detail = (
                    f"{outcome_detail} [{run.detail}]"
                    if outcome_detail
                    else run.detail
                )

            episodes.append(
                EpisodeEvidence(
                    episode_id=run.episode_id,
                    plan_id=plan.plan_id,
                    generation_id=plan.generation_id,
                    condition=condition,
                    execution=run.execution,
                    outcome=outcome,
                    outcome_detail=outcome_detail,
                    reset_confirmed=True,
                    reset_witnessed=reset.witnessed,
                    witness_identity=run.witness_identity
                    or (run.trace[0].channel if run.trace else ""),
                    source=SOURCE_REAL,
                )
            )

            if run.execution in (EXECUTION_HELD, EXECUTION_FAULT):
                consecutive_holds += 1
                if consecutive_holds >= self._breaker.max_consecutive_holds:
                    return episodes, STOP_CIRCUIT_BREAKER, (
                        f"{consecutive_holds} consecutive hold/fault "
                        "episodes; the batch is chasing a defect, not "
                        "sampling an envelope"
                    )
            else:
                consecutive_holds = 0

            if not episodes[-1].success:
                key = (condition, outcome)
                equivalent_failures[key] = equivalent_failures.get(key, 0) + 1
                if (
                    equivalent_failures[key]
                    >= self._breaker.max_equivalent_failures
                ):
                    return episodes, STOP_CIRCUIT_BREAKER, (
                        f"{equivalent_failures[key]} equivalent "
                        f"{outcome} episodes at {condition.label}; repeating "
                        "them buys no information"
                    )

        return episodes, STOP_COMPLETED, ""
