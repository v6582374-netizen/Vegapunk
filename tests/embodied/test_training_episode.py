from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone

from vegapunk.embodied.episode import (
    AbortRecord,
    EpisodeTrainingManifest,
    InitialStateEnvelope,
    Intervention,
    TimeSynchronization,
    TrainingEpisode,
    freeze_qualified_replay,
)
from vegapunk.embodied.promotion import (
    GOLDEN_EMBODIMENT,
    GOLDEN_PROMOTION_CONFIGURATION,
    GOLDEN_SKILL_ID,
    GoldenSkillRevision,
    InstrumentOperationLoop,
)
from vegapunk.embodied.skill import SKILL_KIND_DETERMINISTIC, PhysicalSkill
from vegapunk.operation.bridge import ACCEPTED, MotionGrant, TargetBridge
from vegapunk.operation.episode import (
    TERMINATION_COMPLETED,
    TRANSFER_FULL,
    TRANSFER_NONE,
    CameraCalibration,
    EpisodeOutcome,
    EpisodeRecord,
    Frame,
    HumanTestimony,
    ResetRecord,
)
from vegapunk.operation.target import HAND_OPEN, STAND_BODY, WholeBodyTarget
from vegapunk.operation.tracker import TrackerState
from vegapunk.operation.witness import LID_CLOSED, LID_INDETERMINATE

NOW = 1_000_000_000
AT = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


class _RecordingTransport:
    def __init__(self) -> None:
        self.committed: list[WholeBodyTarget] = []

    def commit(self, target: WholeBodyTarget) -> None:
        self.committed.append(target)

    def read_state(self):
        return None


def _skill() -> GoldenSkillRevision:
    return GoldenSkillRevision(
        skill=PhysicalSkill(
            skill_id=GOLDEN_SKILL_ID,
            revision=1,
            kind=SKILL_KIND_DETERMINISTIC,
            summary="Open, transfer, and restore the instrument.",
            parameters=(),
            preconditions=("instrument_closed",),
            postconditions=("instrument_closed", "transfer_complete"),
            abort_conditions=("safety_stop",),
            max_duration_s=90.0,
            reviewed_by="skill_owner",
        ),
        operation_loop=InstrumentOperationLoop(
            ("open_lid", "pick_up_cup", "tilt_cup", "return_cup", "close_lid")
        ),
    )


def _target(sequence: int = 1) -> WholeBodyTarget:
    return WholeBodyTarget(
        sequence=sequence,
        source_time_ns=NOW + sequence,
        valid_until_ns=NOW + 100_000_000 + sequence,
        body=STAND_BODY,
        left_hand=HAND_OPEN,
        right_hand=HAND_OPEN,
    )


def _frame(index: int = 0, *, lid: str = LID_CLOSED) -> Frame:
    return Frame(
        index=index,
        time_ns=NOW + index,
        images={"head": f"head/{index:05d}.jpg"},
        state=TrackerState(
            sequence=index + 1,
            state_time_ns=NOW + index,
            body=(0.0,) * 34,
            left_hand=HAND_OPEN,
            right_hand=HAND_OPEN,
            applied_target_sequence=index + 1,
        ),
        target=_target(index + 1),
        lid=lid,
        monitor_decision="pass",
    )


def _record(
    episode_id: str = "episode-001", *, transfer: str = TRANSFER_FULL
) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id=episode_id,
        configuration_digest=GOLDEN_PROMOTION_CONFIGURATION.digest(),
        started_at=AT,
        cameras=(
            CameraCalibration(
                identity="head", width=640, height=480, fps=30.0, mounted_on="torso"
            ),
        ),
        witness_identity="lid-limit-switch",
        reset=ResetRecord(
            performed_by="bench_operator",
            performed_at=AT,
            lid_closed=True,
            vessel_restored=True,
            floor_and_tether_restored=True,
        ),
        frame_count=1,
        outcome=EpisodeOutcome(
            transfer=transfer,
            judged_by="outcome_judge",
            judged_at=AT,
            lid_closed_at_end=True,
            termination=TERMINATION_COMPLETED,
        ),
        testimony=(
            HumanTestimony(
                witnessed_by="bench_operator",
                recorded_at=AT,
                account="cup remained in the gripper until return",
            ),
        ),
        operator="campaign_operator",
    )


def _sync() -> TimeSynchronization:
    return TimeSynchronization(
        synchronization_id="ptp-bench-001",
        synchronized_at=AT,
        observation_clock="camera-ptp",
        target_clock="target-bridge-monotonic",
        witness_clock="lid-switch-monotonic",
        max_skew_ns=2_000_000,
    )


def _episode(
    episode_id: str = "episode-001", *, transfer: str = TRANSFER_FULL,
    lid: str = LID_CLOSED, interventions: tuple[Intervention, ...] = (),
    aborts: tuple[AbortRecord, ...] = (), frame: Frame | None = None,
):
    return TrainingEpisode(
        record=_record(episode_id, transfer=transfer),
        skill=_skill(),
        embodiment=GOLDEN_EMBODIMENT,
        configuration=GOLDEN_PROMOTION_CONFIGURATION,
        synchronization=_sync(),
        frames=(_frame(lid=lid) if frame is None else frame,),
        interventions=interventions,
        aborts=aborts,
    )


class TrainingEpisodeAcceptanceTest(unittest.TestCase):
    def test_a_campaign_operator_captures_the_complete_frozen_episode(self) -> None:
        intervention = Intervention(
            time_ns=NOW + 2,
            performed_by="safety_operator",
            detail="held the arm clear of the vessel",
        )
        abort = AbortRecord(
            time_ns=NOW + 3,
            requested_by="campaign_operator",
            reason="restarted after the hold",
        )

        episode = _episode(
            lid=LID_INDETERMINATE,
            interventions=(intervention,),
            aborts=(abort,),
        )

        self.assertEqual(episode.record.reset.performed_by, "bench_operator")
        self.assertEqual(episode.skill.digest(), _skill().digest())
        self.assertEqual(episode.embodiment.digest(), GOLDEN_EMBODIMENT.digest())
        self.assertEqual(
            episode.configuration.digest(), GOLDEN_PROMOTION_CONFIGURATION.digest()
        )
        self.assertEqual(episode.synchronization.synchronization_id, "ptp-bench-001")
        self.assertEqual(episode.frames[0].target, _target())
        self.assertEqual(episode.frames[0].lid, LID_INDETERMINATE)
        self.assertEqual(episode.record.testimony[0].witnessed_by, "bench_operator")
        self.assertEqual(episode.interventions, (intervention,))
        self.assertEqual(episode.aborts, (abort,))
        self.assertEqual(episode.record.outcome.transfer, TRANSFER_FULL)
        with self.assertRaises(TypeError):
            episode.frames[0].images["head"] = "tampered.jpg"  # type: ignore[index]

    def test_capture_refuses_unsynchronized_or_unaligned_observation_target_pairs(self) -> None:
        frame = _frame()
        wrong_target = replace(
            frame,
            state=replace(frame.state, applied_target_sequence=99),
        )
        delayed_state = replace(
            frame,
            state=replace(frame.state, state_time_ns=NOW + 3_000_000),
        )

        with self.assertRaisesRegex(ValueError, "applied to it"):
            _episode(frame=wrong_target)
        with self.assertRaisesRegex(ValueError, "synchronization bound"):
            _episode(frame=delayed_state)

    def test_manifest_keeps_eligible_and_every_excluded_episode_with_its_reason(self) -> None:
        eligible = _episode("episode-eligible")
        failed = _episode("episode-failed", transfer=TRANSFER_NONE)
        interrupted = _episode(
            "episode-interrupted",
            interventions=(
                Intervention(NOW + 2, "safety_operator", "held at bench edge"),
            ),
            aborts=(AbortRecord(NOW + 3, "campaign_operator", "safety hold"),),
            lid=LID_INDETERMINATE,
        )

        manifest = EpisodeTrainingManifest((eligible, failed, interrupted))

        self.assertEqual(manifest.eligible_episode_ids, ("episode-eligible",))
        self.assertEqual(set(manifest.excluded_episode_reasons), {
            "episode-failed", "episode-interrupted"
        })
        self.assertIn("outcome is 'none'", manifest.excluded_episode_reasons["episode-failed"])
        reason = manifest.excluded_episode_reasons["episode-interrupted"]
        self.assertIn("intervention", reason)
        self.assertIn("abort", reason)
        self.assertIn("indeterminate", reason)

    def test_qualified_replay_is_frozen_from_an_eligible_episode_as_targets_only(self) -> None:
        episode = _episode()

        replay = freeze_qualified_replay(episode)

        self.assertEqual(replay.source_episode_id, episode.record.episode_id)
        self.assertEqual(replay.source_episode_digest, episode.digest())
        self.assertEqual(
            replay.control_frequency_hz, GOLDEN_EMBODIMENT.control_frequency_hz
        )
        self.assertEqual(replay.artifact_digest, episode.artifact_digest())
        self.assertEqual(
            replay.initial_state_envelope,
            InitialStateEnvelope.from_episode(episode),
        )
        self.assertEqual(replay.targets, (_target(),))
        self.assertTrue(all(isinstance(target, WholeBodyTarget) for target in replay.targets))
        transport = _RecordingTransport()
        bridge = TargetBridge(
            transport,
            GOLDEN_PROMOTION_CONFIGURATION.digest(),
            grant=MotionGrant(
                authorized_by="campaign_operator",
                statement="qualified replay observation check",
                granted_at=AT,
                configuration_digest=GOLDEN_PROMOTION_CONFIGURATION.digest(),
            ),
            clock_ns=lambda: NOW,
        )

        result = bridge.publish(replay.targets[0])

        self.assertEqual(result.verdict, ACCEPTED)
        self.assertEqual(transport.committed, list(replay.targets))

    def test_an_interrupted_episode_cannot_be_laundered_into_a_qualified_replay(self) -> None:
        episode = _episode(
            interventions=(
                Intervention(NOW + 2, "safety_operator", "manual hold"),
            ),
        )

        with self.assertRaisesRegex(ValueError, "intervention"):
            freeze_qualified_replay(episode)
