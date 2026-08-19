from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from vegapunk.operation.bridge import MotionGrant, TargetBridge
from vegapunk.operation.episode import (
    TERMINATION_COMPLETED,
    TERMINATION_HELD,
    TRANSFER_FULL,
    CameraCalibration,
    EpisodeOutcome,
    EpisodeRecord,
    EpisodeWriter,
    ResetRecord,
)
from vegapunk.operation.monitor import HOLD_LID_NOT_OPEN, InstrumentMonitor, PourPosture
from vegapunk.operation.policy import (
    ActionChunk,
    Observation,
    PolicyServer,
    ReplayFastPolicy,
)
from vegapunk.operation.session import (
    COMPLETED,
    HELD,
    HOLD_MONITOR_VETO,
    HOLD_OPERATOR,
    HOLD_STARVED,
    RUNNING,
    OperationSession,
)
from vegapunk.operation.target import (
    HAND_CLOSED,
    HAND_OPEN,
    STAND_BODY,
    WholeBodyTarget,
)
from vegapunk.operation.tracker import TrackerState
from vegapunk.operation.witness import IndependentWitness, SwitchWitness

_NOW = 1_700_000_000_000_000_000
_PERIOD_NS = 20_000_000
_DIGEST = "config-a"

_ROLL_INDEX = 6 + 26  # right_wrist_roll_joint


class _Transport:
    def __init__(self) -> None:
        self.committed: list[WholeBodyTarget] = []

    def commit(self, target: WholeBodyTarget) -> None:
        self.committed.append(target)

    def read_state(self):
        return None


def _state() -> TrackerState:
    return TrackerState(
        sequence=1,
        state_time_ns=_NOW,
        body=tuple([0.0] * 34),
        left_hand=HAND_OPEN,
        right_hand=HAND_OPEN,
    )


def _observation(tick: int) -> Observation:
    return Observation(
        time_ns=_NOW + tick * _PERIOD_NS,
        images={"head": f"head/{tick}.jpg", "left_wrist": f"lw/{tick}.jpg"},
        state=_state(),
    )


def _frame(**overrides: object) -> WholeBodyTarget:
    body = list(STAND_BODY)
    for index, value in overrides.pop("body_overrides", {}).items():  # type: ignore[union-attr]
        body[index] = value
    fields: dict[str, object] = {
        "sequence": 1,
        "source_time_ns": _NOW,
        "valid_until_ns": _NOW + 10 * _PERIOD_NS,
        "body": tuple(body),
        "left_hand": HAND_OPEN,
        "right_hand": HAND_OPEN,
    }
    fields.update(overrides)
    return WholeBodyTarget(**fields)  # type: ignore[arg-type]


def _pour_frame() -> WholeBodyTarget:
    return _frame(
        body_overrides={_ROLL_INDEX: 1.2},
        right_hand=HAND_CLOSED,
    )


def _reset() -> ResetRecord:
    return ResetRecord(
        performed_by="Wei",
        performed_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        cup_volume_ml=50.0,
        lid_closed=True,
        vessel_restored=True,
        floor_and_tether_restored=True,
    )


def _record(episode_id: str = "ep-1") -> EpisodeRecord:
    return EpisodeRecord(
        episode_id=episode_id,
        configuration_digest=_DIGEST,
        started_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        cameras=(
            CameraCalibration(
                identity="head",
                width=640,
                height=480,
                fps=30.0,
                mounted_on="head",
            ),
        ),
        witness_identity="instrument_reported_lid",
        reset=_reset(),
        operator="Wei",
    )


def _grant() -> MotionGrant:
    return MotionGrant(
        authorized_by="Wei",
        statement="supervised instrument loop, guardian at the stop",
        granted_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        configuration_digest=_DIGEST,
    )


class _FixedPolicy:
    """A fast policy that serves one frame per tick, forever."""

    def __init__(self, frame: WholeBodyTarget) -> None:
        self._frame = frame

    def act(self, observation: Observation, intent, first_tick: int) -> ActionChunk:
        frames = tuple(
            WholeBodyTarget(
                sequence=first_tick + offset,
                source_time_ns=observation.time_ns + offset * _PERIOD_NS,
                valid_until_ns=observation.time_ns + (offset + 4) * _PERIOD_NS,
                body=self._frame.body,
                left_hand=self._frame.left_hand,
                right_hand=self._frame.right_hand,
            )
            for offset in range(8)
        )
        return ActionChunk(first_tick=first_tick, frames=frames)


class _Harness:
    def __init__(self, tmp: Path, *, lid_open: bool, policy) -> None:
        self.transport = _Transport()
        self.bridge = TargetBridge(
            self.transport,
            _DIGEST,
            grant=_grant(),
            clock_ns=lambda: _NOW,
        )
        self.witness = IndependentWitness(
            SwitchWitness(lambda: lid_open, clock_ns=lambda: _NOW),
            clock_ns=lambda: _NOW,
            dwell_s=0.0,
        )
        self.monitor = InstrumentMonitor(self.witness)
        self.writer = EpisodeWriter(tmp, _record())
        self.session = OperationSession(
            policy=PolicyServer(policy, clock_ns=lambda: _NOW),
            monitor=self.monitor,
            bridge=self.bridge,
            writer=self.writer,
            clock_ns=lambda: _NOW,
        )


class NominalRunTest(unittest.TestCase):
    def test_a_walking_run_publishes_every_tick_and_records_every_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = _Harness(
                Path(tmp), lid_open=True, policy=_FixedPolicy(_frame())
            )

            for tick in range(20):
                result = harness.session.step(_observation(tick))
                self.assertTrue(result.running, result.detail)

            self.assertEqual(harness.session.tick_count, 20)
            self.assertEqual(len(harness.transport.committed), 20)
            self.assertEqual(harness.writer.frame_count, 20)

    def test_the_recorded_frame_is_the_frame_the_robot_received(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = _Harness(
                Path(tmp), lid_open=True, policy=_FixedPolicy(_frame())
            )

            harness.session.step(_observation(0))

            written = list(harness.writer.frames())
            self.assertEqual(len(written), 1)
            self.assertEqual(
                written[0]["target"]["body"],
                list(harness.transport.committed[0].body),
            )


class MonitorVetoTest(unittest.TestCase):
    def test_a_pour_into_a_closed_lid_is_never_published(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = _Harness(
                Path(tmp), lid_open=False, policy=_FixedPolicy(_pour_frame())
            )

            result = harness.session.step(_observation(0))

            self.assertEqual(result.state, HELD)
            self.assertEqual(result.monitor_decision, HOLD_LID_NOT_OPEN)
            # The only frame that reached the transport is the hold.
            self.assertEqual(len(harness.transport.committed), 1)
            self.assertTrue(harness.transport.committed[0].is_stationary())

    def test_a_pour_into_an_open_lid_proceeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = _Harness(
                Path(tmp), lid_open=True, policy=_FixedPolicy(_pour_frame())
            )

            result = harness.session.step(_observation(0))

            self.assertTrue(result.running)
            self.assertEqual(result.lid, "open")

    def test_a_veto_records_the_safety_event_and_the_held_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = _Harness(
                Path(tmp), lid_open=False, policy=_FixedPolicy(_pour_frame())
            )

            harness.session.step(_observation(0))

            record = harness.session.record
            self.assertTrue(record.held)
            self.assertEqual(
                [event.kind for event in record.safety_events],
                [HOLD_MONITOR_VETO],
            )
            written = list(harness.writer.frames())
            self.assertEqual(len(written), 1)
            self.assertTrue(written[0]["holding"])


class HoldIsTerminalTest(unittest.TestCase):
    def test_a_held_session_refuses_every_later_tick(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = _Harness(
                Path(tmp), lid_open=False, policy=_FixedPolicy(_pour_frame())
            )

            harness.session.step(_observation(0))
            committed = len(harness.transport.committed)

            for tick in range(1, 5):
                result = harness.session.step(_observation(tick))
                self.assertEqual(result.state, HELD)

            self.assertEqual(len(harness.transport.committed), committed)

    def test_the_bridge_latch_survives_the_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = _Harness(
                Path(tmp), lid_open=False, policy=_FixedPolicy(_pour_frame())
            )

            harness.session.step(_observation(0))

            self.assertTrue(harness.bridge.latched)
            self.assertIn("lid", harness.bridge.latch_reason)


class StarvationTest(unittest.TestCase):
    def test_a_policy_that_runs_out_holds_rather_than_raising(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = _Harness(
                Path(tmp),
                lid_open=True,
                policy=ReplayFastPolicy([_frame()], chunk_periods=1),
            )

            first = harness.session.step(_observation(0))
            self.assertTrue(first.running)

            second = harness.session.step(_observation(1))
            self.assertEqual(second.state, HELD)
            self.assertEqual(
                [event.kind for event in harness.session.record.safety_events],
                [HOLD_STARVED],
            )

    def test_the_starved_hold_is_a_published_stand_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = _Harness(
                Path(tmp),
                lid_open=True,
                policy=ReplayFastPolicy([_frame()], chunk_periods=1),
            )

            harness.session.step(_observation(0))
            harness.session.step(_observation(1))

            self.assertTrue(harness.transport.committed[-1].is_stationary())


class OperatorStopTest(unittest.TestCase):
    def test_an_operator_stop_holds_and_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = _Harness(
                Path(tmp), lid_open=True, policy=_FixedPolicy(_frame())
            )
            harness.session.step(_observation(0))

            result = harness.session.operator_stop("cup looked wrong")

            self.assertEqual(result.state, HELD)
            self.assertEqual(
                [event.kind for event in harness.session.record.safety_events],
                [HOLD_OPERATOR],
            )

    def test_an_operator_stop_must_say_why(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = _Harness(
                Path(tmp), lid_open=True, policy=_FixedPolicy(_frame())
            )

            with self.assertRaises(ValueError):
                harness.session.operator_stop("   ")


class TerminationHonestyTest(unittest.TestCase):
    def _sealed_outcome(self, termination: str) -> EpisodeOutcome:
        return EpisodeOutcome(
            transfer=TRANSFER_FULL,
            judged_by="Wei",
            judged_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
            lid_closed_at_end=True,
            termination=termination,
        )

    def test_a_held_run_cannot_be_sealed_as_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = _Harness(
                Path(tmp), lid_open=False, policy=_FixedPolicy(_pour_frame())
            )
            harness.session.step(_observation(0))

            with self.assertRaises(ValueError):
                harness.session.finish(self._sealed_outcome(TERMINATION_COMPLETED))

    def test_a_run_that_never_held_cannot_be_sealed_as_held(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = _Harness(
                Path(tmp), lid_open=True, policy=_FixedPolicy(_frame())
            )
            harness.session.step(_observation(0))

            with self.assertRaises(ValueError):
                harness.session.finish(self._sealed_outcome(TERMINATION_HELD))

    def test_a_completed_run_seals_and_becomes_trainable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = _Harness(
                Path(tmp), lid_open=True, policy=_FixedPolicy(_frame())
            )
            for tick in range(5):
                harness.session.step(_observation(tick))

            record = harness.session.finish(self._sealed_outcome(TERMINATION_COMPLETED))

            self.assertEqual(harness.session.state, COMPLETED)
            trainable, why = record.trainable()
            self.assertTrue(trainable, why)

    def test_a_held_run_seals_as_held_and_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = _Harness(
                Path(tmp), lid_open=False, policy=_FixedPolicy(_pour_frame())
            )
            harness.session.step(_observation(0))

            record = harness.session.finish(self._sealed_outcome(TERMINATION_HELD))

            self.assertEqual(record.outcome.termination, TERMINATION_HELD)
            self.assertTrue(record.held)


if __name__ == "__main__":
    unittest.main()
