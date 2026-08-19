from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from vegapunk.operation.episode import (
    JUDGED_BY_EYE,
    JUDGED_BY_MASS,
    TERMINATION_COMPLETED,
    TERMINATION_HELD,
    TRANSFER_FULL,
    TRANSFER_NONE,
    TRANSFER_PARTIAL,
    CameraCalibration,
    EpisodeOutcome,
    EpisodeRecord,
    EpisodeWriter,
    Frame,
    HumanTestimony,
    ResetRecord,
    SafetyEvent,
)
from vegapunk.operation.target import HAND_OPEN, STAND_BODY, WholeBodyTarget
from vegapunk.operation.tracker import TrackerState
from vegapunk.operation.witness import LID_CLOSED, LID_INDETERMINATE, LID_OPEN

_NOW = 1_000_000_000
_AT = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def _cameras() -> tuple[CameraCalibration, ...]:
    return (
        CameraCalibration(
            identity="head", width=640, height=480, fps=30.0, mounted_on="torso"
        ),
        CameraCalibration(
            identity="left_wrist",
            width=640,
            height=480,
            fps=30.0,
            mounted_on="left_wrist",
        ),
    )


def _reset(**overrides: object) -> ResetRecord:
    fields: dict[str, object] = {
        "performed_by": "Wen",
        "performed_at": _AT,
        "cup_volume_ml": 50.0,
        "lid_closed": True,
        "vessel_restored": True,
        "floor_and_tether_restored": True,
    }
    fields.update(overrides)
    return ResetRecord(**fields)  # type: ignore[arg-type]


def _record(**overrides: object) -> EpisodeRecord:
    fields: dict[str, object] = {
        "episode_id": "episode_0001",
        "configuration_digest": "cfg-abc",
        "started_at": _AT,
        "cameras": _cameras(),
        "witness_identity": "instrument_reported_lid",
        "reset": _reset(),
        "operator": "Wen",
    }
    fields.update(overrides)
    return EpisodeRecord(**fields)  # type: ignore[arg-type]


def _state() -> TrackerState:
    return TrackerState(
        sequence=1, state_time_ns=_NOW, body=(0.0,) * 34,
        left_hand=HAND_OPEN, right_hand=HAND_OPEN,
    )


def _target(sequence: int = 1) -> WholeBodyTarget:
    return WholeBodyTarget(
        sequence=sequence,
        source_time_ns=_NOW,
        valid_until_ns=_NOW + 60_000_000,
        body=STAND_BODY,
        left_hand=HAND_OPEN,
        right_hand=HAND_OPEN,
    )


def _frame(index: int = 0, **overrides: object) -> Frame:
    fields: dict[str, object] = {
        "index": index,
        "time_ns": _NOW + index,
        "images": {"head": f"head/{index:05d}.jpg"},
        "state": _state(),
        "target": _target(index + 1),
        "lid": LID_CLOSED,
        "monitor_decision": "pass",
    }
    fields.update(overrides)
    return Frame(**fields)  # type: ignore[arg-type]


def _outcome(**overrides: object) -> EpisodeOutcome:
    fields: dict[str, object] = {
        "transfer": TRANSFER_FULL,
        "judged_by": "Wen",
        "judged_at": _AT,
        "lid_closed_at_end": True,
        "termination": TERMINATION_COMPLETED,
    }
    fields.update(overrides)
    return EpisodeOutcome(**fields)  # type: ignore[arg-type]


class FrameTest(unittest.TestCase):
    def test_a_frame_records_the_witness_value_even_when_indeterminate(self) -> None:
        frame = _frame(lid=LID_INDETERMINATE)

        self.assertEqual(frame.lid, LID_INDETERMINATE)

    def test_a_blank_lid_field_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            _frame(lid="  ")

        self.assertIn("never consulted", str(caught.exception))

    def test_a_frame_with_no_image_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            _frame(images={})

    def test_the_payload_carries_the_applied_target_alignment(self) -> None:
        payload = _frame().as_payload()

        self.assertIn("state", payload)
        self.assertIn("applied_target_sequence", payload["state"])
        self.assertEqual(payload["target"]["sequence"], 1)


class CameraCalibrationTest(unittest.TestCase):
    def test_a_camera_must_say_what_it_is_mounted_on(self) -> None:
        with self.assertRaises(ValueError) as caught:
            CameraCalibration(
                identity="head", width=640, height=480, fps=30.0, mounted_on=" "
            )

        self.assertIn("not interchangeable", str(caught.exception))


class ResetTest(unittest.TestCase):
    def test_a_reset_is_performed_by_a_named_human(self) -> None:
        with self.assertRaises(ValueError):
            _reset(performed_by="")

    def test_an_unrestored_tether_makes_the_reset_incomplete(self) -> None:
        self.assertFalse(_reset(floor_and_tether_restored=False).complete)


class OutcomeTest(unittest.TestCase):
    def test_a_human_eye_judgement_is_a_complete_outcome(self) -> None:
        """No balance required. The label answers one three-way question."""
        outcome = _outcome()

        self.assertEqual(outcome.method, JUDGED_BY_EYE)
        self.assertFalse(outcome.weighed)
        self.assertIsNone(outcome.within_resolution)
        self.assertEqual(outcome.transfer, TRANSFER_FULL)

    def test_an_outcome_must_name_its_judge(self) -> None:
        with self.assertRaisesRegex(ValueError, "names the human"):
            _outcome(judged_by="   ")

    def test_claiming_mass_without_a_resolution_is_refused(self) -> None:
        """Only a label that claims to be a measurement must behave like one."""
        with self.assertRaisesRegex(ValueError, "not a measurement"):
            _outcome(method=JUDGED_BY_MASS, delivered_mass_g=48.2)

    def test_claiming_mass_without_a_mass_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "delivered_mass_g"):
            _outcome(method=JUDGED_BY_MASS, balance_resolution_g=0.1)

    def test_a_mass_below_the_balance_resolution_is_flagged(self) -> None:
        outcome = _outcome(
            method=JUDGED_BY_MASS,
            delivered_mass_g=0.05,
            balance_resolution_g=0.1,
        )

        self.assertTrue(outcome.weighed)
        self.assertFalse(outcome.within_resolution)

    def test_a_weighed_pour_above_resolution_is_trusted(self) -> None:
        outcome = _outcome(
            method=JUDGED_BY_MASS,
            delivered_mass_g=48.2,
            balance_resolution_g=0.1,
        )

        self.assertTrue(outcome.within_resolution)

    def test_only_the_three_measured_bands_exist(self) -> None:
        for band in (TRANSFER_FULL, TRANSFER_PARTIAL, TRANSFER_NONE):
            self.assertEqual(_outcome(transfer=band).transfer, band)
        with self.assertRaises(ValueError):
            _outcome(transfer="probably_fine")


class TestimonyTest(unittest.TestCase):
    def test_testimony_is_its_own_type_and_carries_no_verdict_field(self) -> None:
        testimony = HumanTestimony(
            witnessed_by="Wen", recorded_at=_AT, account="the pour looked clean"
        )
        payload = testimony.as_payload()

        self.assertEqual(set(payload), {"witnessed_by", "recorded_at", "account"})
        self.assertNotIn("transfer", payload)


class TrainabilityTest(unittest.TestCase):
    def test_an_unjudged_episode_is_not_training_data(self) -> None:
        trainable, reason = _record(frame_count=10).trainable()

        self.assertFalse(trainable)
        self.assertIn("nobody judged", reason)

    def test_an_incomplete_reset_disqualifies_the_episode(self) -> None:
        record = _record(
            frame_count=10,
            outcome=_outcome(),
            reset=_reset(vessel_restored=False),
        )

        trainable, reason = record.trainable()

        self.assertFalse(trainable)
        self.assertIn("starting state is unknown", reason)

    def test_a_failed_pour_is_excluded_by_label_and_kept(self) -> None:
        record = _record(
            frame_count=10,
            outcome=_outcome(transfer=TRANSFER_NONE),
        )

        trainable, reason = record.trainable()

        self.assertFalse(trainable)
        self.assertIn("rather than deleted", reason)

    def test_a_measured_reset_complete_episode_is_trainable(self) -> None:
        record = _record(frame_count=10, outcome=_outcome())

        trainable, reason = record.trainable()

        self.assertTrue(trainable)
        self.assertEqual(reason, "")

    def test_an_episode_must_name_its_configuration_and_witness(self) -> None:
        with self.assertRaises(ValueError):
            _record(configuration_digest=" ")
        with self.assertRaises(ValueError):
            _record(witness_identity="")


class WriterTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_frames_events_and_manifest_are_all_written(self) -> None:
        writer = EpisodeWriter(self.root, _record())
        writer.append(_frame(0))
        writer.append(_frame(1))
        writer.note(SafetyEvent(time_ns=_NOW, kind="hold_lid_not_open", detail="closed"))
        writer.complete(_outcome())

        names = sorted(path.name for path in writer.directory.iterdir())
        self.assertEqual(names, ["events.jsonl", "frames.jsonl", "manifest.json"])

    def test_the_manifest_carries_a_digest_of_what_it_recorded(self) -> None:
        writer = EpisodeWriter(self.root, _record())
        writer.append(_frame(0))
        writer.complete(_outcome())

        payload = json.loads((writer.directory / "manifest.json").read_text())
        self.assertIn("record_digest", payload)
        self.assertEqual(payload["frame_count"], 1)

    def test_a_hold_is_visible_in_the_sealed_record(self) -> None:
        writer = EpisodeWriter(self.root, _record())
        writer.note(
            SafetyEvent(time_ns=_NOW, kind="hold_lid_not_open", detail="lid closed")
        )
        record = writer.complete(
            _outcome(transfer=TRANSFER_NONE, termination=TERMINATION_HELD)
        )

        self.assertTrue(record.held)

    def test_a_frame_appended_after_completion_is_refused(self) -> None:
        writer = EpisodeWriter(self.root, _record())
        writer.complete(_outcome())

        with self.assertRaises(RuntimeError) as caught:
            writer.append(_frame(0))

        self.assertIn("what the measurement refers to", str(caught.exception))

    def test_written_frames_replay_in_order(self) -> None:
        writer = EpisodeWriter(self.root, _record())
        for index in range(4):
            writer.append(_frame(index))

        replayed = [frame["index"] for frame in writer.frames()]
        self.assertEqual(replayed, [0, 1, 2, 3])

    def test_an_unreadable_frame_stops_the_replay_rather_than_being_skipped(
        self,
    ) -> None:
        writer = EpisodeWriter(self.root, _record())
        writer.append(_frame(0))
        with (writer.directory / "frames.jsonl").open("a", encoding="utf-8") as handle:
            handle.write("{not json\n")

        with self.assertRaises(ValueError) as caught:
            list(writer.frames())

        self.assertIn("quietly shortened episode", str(caught.exception))

    def test_testimony_lands_in_the_manifest_but_not_in_the_outcome(self) -> None:
        writer = EpisodeWriter(self.root, _record())
        writer.testify(
            HumanTestimony(witnessed_by="Wen", recorded_at=_AT, account="looked fine")
        )
        record = writer.complete(_outcome())

        self.assertEqual(len(record.testimony), 1)
        self.assertNotIn("looked fine", json.dumps(dict(record.outcome.as_payload())))


if __name__ == "__main__":
    unittest.main()
