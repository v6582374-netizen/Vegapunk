"""The end-to-end software dry run.

One complete batch from pre-registration through result analysis, using the
real policy server, target bridge, episode writer, operation session and
experiment loop -- with deterministic witness adapters standing in for the
bench camera. No robot is involved, and nothing here claims one was: this
proves the loop's plumbing and record-keeping, while hardware tests remain
the only proof of physical behaviour.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from vegapunk.operation.bridge import MotionGrant, TargetBridge
from vegapunk.operation.campaign import (
    BatchPlan,
    BenchConfiguration,
    Campaign,
    Condition,
)
from vegapunk.operation.episode import (
    CameraCalibration,
    EpisodeRecord,
    EpisodeWriter,
    ResetRecord,
)
from vegapunk.operation.loop import (
    CircuitBreaker,
    ExperimentLoop,
    SessionEpisode,
    SessionEpisodeExecutor,
)
from vegapunk.operation.monitor import InstrumentMonitor
from vegapunk.operation.policy import (
    ActionChunk,
    Observation,
    PolicyServer,
)
from vegapunk.operation.predict import CalibrationPolicy, TabularPredictiveNode
from vegapunk.operation.session import OperationSession
from vegapunk.operation.target import HAND_OPEN, STAND_BODY, WholeBodyTarget
from vegapunk.operation.tracker import TrackerState
from vegapunk.operation.trace import (
    FACT_DEFINITE,
    OUTCOME_FAILED,
    OUTCOME_SUCCEEDED,
    REQUIRED_TRACE,
    ResetVerdict,
    TraceFact,
)
from vegapunk.operation.witness import IndependentWitness, SwitchWitness

_AT = datetime(2026, 8, 19, tzinfo=timezone.utc)
_NOW = 1_700_000_000_000_000_000
_PERIOD_NS = 20_000_000
_DIGEST = "dry-run-bench"
_TICKS = 10

_POSE_GOOD = Condition.of(cup_pose="recess")
_POSE_BAD = Condition.of(cup_pose="table_edge")


class _Transport:
    def __init__(self) -> None:
        self.committed: list[WholeBodyTarget] = []

    def commit(self, target: WholeBodyTarget) -> None:
        self.committed.append(target)

    def read_state(self):
        return None


class _StandPolicy:
    """A fast policy that stands still, forever. The loop is under test."""

    def act(self, observation: Observation, intent, first_tick: int) -> ActionChunk:
        frames = tuple(
            WholeBodyTarget(
                sequence=first_tick + offset,
                source_time_ns=observation.time_ns + offset * _PERIOD_NS,
                valid_until_ns=observation.time_ns + (offset + 4) * _PERIOD_NS,
                body=STAND_BODY,
                left_hand=HAND_OPEN,
                right_hand=HAND_OPEN,
            )
            for offset in range(8)
        )
        return ActionChunk(first_tick=first_tick, frames=frames)


class _BenchCameraAdapter:
    """The deterministic stand-in for the fixed bench camera.

    It answers two questions the loop asks of the real camera: the reset
    verdict before each episode and the operation trace after it.
    """

    def __init__(self) -> None:
        self.identity = "bench_camera"

    def verify(self) -> ResetVerdict:
        return ResetVerdict(
            confirmed=True,
            channel=self.identity,
            observed_at_ns=_NOW,
            detail="lid closed, cup at home",
        )

    def trace_for(self, condition: Condition) -> tuple[TraceFact, ...]:
        if condition == _POSE_GOOD:
            predicates = REQUIRED_TRACE
        else:
            # The policy never reached the instrument: only the lid facts.
            predicates = (REQUIRED_TRACE[0], REQUIRED_TRACE[-1])
        return tuple(
            TraceFact(
                predicate=predicate,
                verdict=FACT_DEFINITE,
                channel=self.identity,
                observed_at_ns=_NOW + index,
                fresh=True,
            )
            for index, predicate in enumerate(predicates)
        )


def _observation(tick: int) -> Observation:
    return Observation(
        time_ns=_NOW + tick * _PERIOD_NS,
        images={"head": f"head/{tick}.jpg"},
        state=TrackerState(
            sequence=1,
            state_time_ns=_NOW,
            body=tuple([0.0] * 34),
            left_hand=HAND_OPEN,
            right_hand=HAND_OPEN,
        ),
    )


class DryRunTest(unittest.TestCase):
    def test_a_complete_batch_without_a_robot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            camera = _BenchCameraAdapter()
            writers: list[EpisodeWriter] = []
            episode_counter = {"n": 0}

            def factory(
                condition: Condition, plan: BatchPlan
            ) -> SessionEpisode:
                episode_counter["n"] += 1
                episode_id = f"dry-ep-{episode_counter['n']}"
                writer = EpisodeWriter(
                    root,
                    EpisodeRecord(
                        episode_id=episode_id,
                        configuration_digest=_DIGEST,
                        started_at=_AT,
                        cameras=(
                            CameraCalibration(
                                identity="head",
                                width=640,
                                height=480,
                                fps=30.0,
                                mounted_on="head",
                            ),
                        ),
                        witness_identity=camera.identity,
                        reset=ResetRecord(
                            performed_by="reversible core",
                            performed_at=_AT,
                            lid_closed=True,
                            vessel_restored=True,
                            floor_and_tether_restored=True,
                        ),
                        operator="Wei",
                    ),
                )
                writers.append(writer)
                session = OperationSession(
                    policy=PolicyServer(_StandPolicy(), clock_ns=lambda: _NOW),
                    monitor=InstrumentMonitor(
                        IndependentWitness(
                            SwitchWitness(lambda: False, clock_ns=lambda: _NOW),
                            clock_ns=lambda: _NOW,
                            dwell_s=0.0,
                        )
                    ),
                    bridge=TargetBridge(
                        _Transport(),
                        _DIGEST,
                        grant=MotionGrant(
                            authorized_by="Wei",
                            statement="software dry run, no robot attached",
                            granted_at=_AT,
                            configuration_digest=_DIGEST,
                        ),
                        clock_ns=lambda: _NOW,
                    ),
                    writer=writer,
                    clock_ns=lambda: _NOW,
                )
                return SessionEpisode(
                    session=session,
                    observe=_observation,
                    ticks=_TICKS,
                    trace=lambda: camera.trace_for(condition),
                    witness_identity=camera.identity,
                )

            campaign = Campaign(clock=lambda: _AT)
            generation = campaign.open_founding_generation(
                BenchConfiguration(
                    fixture="bare bench",
                    object_identity="red cup",
                    witness_pose_digest="pose-1",
                    lighting_protocol="overhead",
                    policy_identity="stand-policy-v0",
                    invocation_protocol="chunk8",
                ),
                opened_by="Wei",
            )
            node = TabularPredictiveNode()
            loop = ExperimentLoop(
                campaign=campaign,
                executor=SessionEpisodeExecutor(factory),
                reset_witness=camera,
                node=node,
                calibration_policy=CalibrationPolicy(),
                breaker=CircuitBreaker(
                    max_consecutive_holds=3, max_equivalent_failures=3
                ),
                clock=lambda: _AT,
            )

            plan = BatchPlan(
                plan_id="dry-batch-1",
                generation_id=generation.generation_id,
                objective="prove the loop closes without a robot",
                real_conditions=(_POSE_GOOD, _POSE_BAD),
                predicted_conditions=(),
                real_anchor_count=1,
                predictive_node_version=node.version,
                confidence_threshold=0.8,
                selection_rationale="one witnessed success, one no-op failure",
                expected_outcome=(
                    "recess pose completes the trace; table-edge pose fails "
                    "with only the lid facts"
                ),
                created_at=_AT,
            )

            result = loop.run_batch(plan)

            # Pre-registration through result analysis, all sealed and linked.
            self.assertTrue(campaign.plan_sealed("dry-batch-1"))
            self.assertEqual(len(campaign.predictions_for("dry-batch-1")), 2)
            self.assertIs(campaign.result_for("dry-batch-1"), result)
            self.assertTrue(result.anchored)

            by_condition = {e.condition: e for e in result.episodes}
            self.assertEqual(
                by_condition[_POSE_GOOD].outcome, OUTCOME_SUCCEEDED
            )
            self.assertEqual(by_condition[_POSE_BAD].outcome, OUTCOME_FAILED)

            # The real episode writer captured every tick of both episodes.
            self.assertEqual(len(writers), 2)
            for writer in writers:
                self.assertEqual(writer.frame_count, _TICKS)
                self.assertTrue((writer.directory / "frames.jsonl").exists())

            # Analysis reads back from the same ledger.
            envelope = campaign.envelope()
            self.assertEqual(envelope.sample_count, 2)
            self.assertEqual(envelope.success_count, 1)
            self.assertEqual(envelope.witness_identity, "bench_camera")
            report = campaign.effectiveness(reliable_at=0.9)
            self.assertEqual(
                report.within_generation,
                ((generation.generation_id, (0.5,)),),
            )
            self.assertEqual(
                report.across_generations, ((generation.generation_id, 1),)
            )


if __name__ == "__main__":
    unittest.main()
