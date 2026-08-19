from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from vegapunk.embodied.admission import (
    STAGE_HARDWARE_SUPERVISED,
    STAGE_OFFLINE_REPLAY,
    STAGE_POLICY_EVALUATION,
    STAGE_SHADOW_MODE,
    EvidenceRecord,
    HumanApproval,
    evaluate_admission,
)
from vegapunk.embodied.safety import ABORT_ENVELOPE_VIOLATION
from vegapunk.embodied.store import (
    ADMISSION_FILE,
    CLEARANCE_FILE,
    DEFAULT_LEDGER_ROOT,
    LABEL_FILE,
    TRAJECTORY_FILE,
    LedgerStore,
    PersistentAdmissionLedger,
    PersistentTrajectoryLedger,
    decode_clearance,
    decode_evidence,
    decode_label,
    decode_trajectory,
    encode_clearance,
    encode_evidence,
    encode_label,
    encode_trajectory,
)
from vegapunk.embodied.trajectory import (
    OUTCOME_ABORTED,
    OUTCOME_REFUSED,
    OUTCOME_SUCCEEDED,
    LabelConfirmation,
    RunClearance,
    TrajectoryRecord,
)

_NOW = datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)
_SKILL = "press_physical_button@1"
_EMBODIMENT = "e0f1a2b3c4d5e6f7"
_POLICY = "aabbccddeeff0011"
_SCOPE = (_SKILL, _EMBODIMENT, _POLICY)


def _evidence(stage: str, **overrides: object) -> EvidenceRecord:
    fields: dict[str, object] = {
        "stage": stage,
        "skill_version_id": _SKILL,
        "embodiment_digest": _EMBODIMENT,
        "policy_digest": _POLICY,
        "attempts": 20,
        "successes": 19,
        "safety_violations": 0,
        "recorded_at": _NOW - timedelta(days=1, microseconds=7),
        "notes": "seeded by the simulation campaign",
    }
    fields.update(overrides)
    return EvidenceRecord(**fields)  # type: ignore[arg-type]


def _trajectory(run_id: str, **overrides: object) -> TrajectoryRecord:
    fields: dict[str, object] = {
        "run_id": run_id,
        "stage": STAGE_SHADOW_MODE,
        "skill_version_id": _SKILL,
        "contract_digest": "1122334455667788",
        "selection_digest": "99aabbccddeeff00",
        "embodiment_digest": _EMBODIMENT,
        "policy_digest": _POLICY,
        "outcome": OUTCOME_SUCCEEDED,
        "started_at": _NOW + timedelta(seconds=1, microseconds=250),
        "observations": 120,
        "duration_s": 4.25,
        "detail": "reached the goal pose within tolerance",
        "stream_complete": True,
        "embodiment_verified": True,
    }
    fields.update(overrides)
    return TrajectoryRecord(**fields)  # type: ignore[arg-type]


def _label(run_id: str) -> LabelConfirmation:
    return LabelConfirmation(
        run_id=run_id,
        reviewer="lab_owner",
        statement="Reviewed the video and agree with the recorded outcome.",
        confirmed_at=_NOW + timedelta(minutes=5),
    )


def _clearance(run_id: str) -> RunClearance:
    return RunClearance(
        run_id=run_id,
        reviewer="lab_owner",
        statement="Re-taped the cable that tripped the envelope check.",
        cleared_at=_NOW + timedelta(minutes=30),
    )


class DefaultRootTest(unittest.TestCase):
    def test_the_default_root_is_hidden_and_relative(self) -> None:
        self.assertEqual(DEFAULT_LEDGER_ROOT, Path(".vegapunk/embodied"))
        self.assertFalse(DEFAULT_LEDGER_ROOT.is_absolute())


class CodecTest(unittest.TestCase):
    def test_every_record_kind_survives_its_own_codec(self) -> None:
        evidence = _evidence(STAGE_OFFLINE_REPLAY)
        trajectory = _trajectory(
            "r1",
            outcome=OUTCOME_REFUSED,
            observations=0,
            stream_complete=False,
            findings=("stage shadow_mode has no evidence", "no approval"),
        )
        label = _label("r1")
        clearance = _clearance("r1")

        self.assertEqual(
            decode_evidence(encode_evidence(evidence)), evidence
        )
        self.assertEqual(
            decode_trajectory(encode_trajectory(trajectory)), trajectory
        )
        self.assertEqual(decode_label(encode_label(label)), label)
        self.assertEqual(
            decode_clearance(encode_clearance(clearance)), clearance
        )

    def test_a_missing_policy_digest_stays_missing(self) -> None:
        evidence = _evidence(STAGE_POLICY_EVALUATION, policy_digest=None)

        replayed = decode_evidence(encode_evidence(evidence))

        self.assertIsNone(replayed.policy_digest)
        self.assertEqual(replayed, evidence)

    def test_findings_come_back_as_a_tuple(self) -> None:
        trajectory = _trajectory(
            "r1",
            outcome=OUTCOME_REFUSED,
            observations=0,
            stream_complete=False,
            findings=("one", "two"),
        )

        replayed = decode_trajectory(encode_trajectory(trajectory))

        self.assertIsInstance(replayed.findings, tuple)
        self.assertEqual(replayed.findings, ("one", "two"))


class AdmissionReplayTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name) / "ledgers"
        self.addCleanup(self._tmp.cleanup)

    def test_a_missing_root_is_created(self) -> None:
        self.assertFalse(self.root.exists())

        ledger = PersistentAdmissionLedger(self.root)

        self.assertTrue(self.root.is_dir())
        self.assertEqual(ledger.root, self.root)
        self.assertEqual(ledger.records(), ())

    def test_the_whole_record_tuple_survives_a_replay(self) -> None:
        written = (
            _evidence(STAGE_POLICY_EVALUATION),
            _evidence(STAGE_OFFLINE_REPLAY, policy_digest=None),
            _evidence(
                STAGE_SHADOW_MODE,
                attempts=3,
                successes=1,
                safety_violations=2,
                notes="",
            ),
        )
        first = PersistentAdmissionLedger(self.root)
        for evidence in written:
            first.record(evidence)

        replayed = PersistentAdmissionLedger(self.root)

        self.assertEqual(replayed.records(), written)
        self.assertEqual(replayed.records(), first.records())

    def test_a_replayed_ledger_keeps_the_pinned_evidence_digest(self) -> None:
        first = PersistentAdmissionLedger(self.root)
        first.record(_evidence(STAGE_POLICY_EVALUATION))
        first.record(_evidence(STAGE_OFFLINE_REPLAY))
        first.record(_evidence(STAGE_SHADOW_MODE))
        before = first.evidence_digest(*_SCOPE)
        approval = HumanApproval(
            skill_version_id=_SKILL,
            embodiment_digest=_EMBODIMENT,
            policy_digest=_POLICY,
            approver="lab_owner",
            statement="Reviewed the three stages of recorded evidence.",
            approved_at=_NOW,
            evidence_digest=before,
        )

        replayed = PersistentAdmissionLedger(self.root)

        self.assertEqual(replayed.evidence_digest(*_SCOPE), before)
        decision = evaluate_admission(
            replayed,
            _SKILL,
            _EMBODIMENT,
            _POLICY,
            STAGE_HARDWARE_SUPERVISED,
            approval,
            _NOW + timedelta(hours=1),
        )
        self.assertEqual(decision.blocking_reasons, ())
        self.assertTrue(decision.admitted)

    def test_the_digest_is_scoped_after_a_replay(self) -> None:
        first = PersistentAdmissionLedger(self.root)
        first.record(_evidence(STAGE_POLICY_EVALUATION))
        first.record(
            _evidence(STAGE_POLICY_EVALUATION, skill_version_id="other@1")
        )
        before = first.evidence_digest(*_SCOPE)

        replayed = PersistentAdmissionLedger(self.root)

        self.assertEqual(replayed.evidence_digest(*_SCOPE), before)
        self.assertEqual(len(replayed.scoped_records(*_SCOPE)), 1)

    def test_appending_is_one_flushed_line_per_record(self) -> None:
        ledger = PersistentAdmissionLedger(self.root)
        ledger.record(_evidence(STAGE_POLICY_EVALUATION))
        ledger.record(_evidence(STAGE_OFFLINE_REPLAY))

        text = (self.root / ADMISSION_FILE).read_text(encoding="utf-8")

        self.assertEqual(len(text.splitlines()), 2)
        self.assertTrue(text.endswith("\n"))

    def test_a_second_session_appends_instead_of_rewriting(self) -> None:
        PersistentAdmissionLedger(self.root).record(
            _evidence(STAGE_POLICY_EVALUATION)
        )
        second = PersistentAdmissionLedger(self.root)
        second.record(_evidence(STAGE_OFFLINE_REPLAY))

        third = PersistentAdmissionLedger(self.root)

        self.assertEqual(
            tuple(record.stage for record in third.records()),
            (STAGE_POLICY_EVALUATION, STAGE_OFFLINE_REPLAY),
        )

    def test_a_truncated_trailing_line_stops_the_replay(self) -> None:
        ledger = PersistentAdmissionLedger(self.root)
        ledger.record(_evidence(STAGE_POLICY_EVALUATION))
        ledger.record(_evidence(STAGE_OFFLINE_REPLAY))
        path = self.root / ADMISSION_FILE
        with path.open("a", encoding="utf-8") as handle:
            handle.write('{"stage": "offline_replay", "attempt')

        with self.assertRaises(ValueError) as caught:
            PersistentAdmissionLedger(self.root)

        message = str(caught.exception)
        self.assertIn(ADMISSION_FILE, message)
        self.assertIn("line 3", message)

    def test_a_record_the_ledger_would_reject_stops_the_replay(self) -> None:
        PersistentAdmissionLedger(self.root).record(
            _evidence(STAGE_POLICY_EVALUATION)
        )
        path = self.root / ADMISSION_FILE
        row = encode_evidence(_evidence(STAGE_OFFLINE_REPLAY))
        row["stage"] = "invented_stage"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")

        with self.assertRaises(ValueError) as caught:
            PersistentAdmissionLedger(self.root)

        self.assertIn("line 2", str(caught.exception))

    def test_a_blank_line_is_corruption_not_whitespace(self) -> None:
        path = self.root / ADMISSION_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        row = json.dumps(encode_evidence(_evidence(STAGE_POLICY_EVALUATION)))
        path.write_text(f"{row}\n\n{row}\n", encoding="utf-8")

        with self.assertRaises(ValueError) as caught:
            PersistentAdmissionLedger(self.root)

        self.assertIn("line 2", str(caught.exception))


class TrajectoryReplayTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name) / "ledgers"
        self.addCleanup(self._tmp.cleanup)

    def test_the_whole_record_tuple_survives_a_replay(self) -> None:
        written = (
            _trajectory("r1"),
            _trajectory(
                "r2",
                outcome=OUTCOME_ABORTED,
                abort_cause=ABORT_ENVELOPE_VIOLATION,
                stream_complete=False,
                policy_digest=None,
                findings=("left the declared envelope",),
            ),
            _trajectory(
                "r3",
                outcome=OUTCOME_REFUSED,
                observations=0,
                stream_complete=False,
                findings=("quarantined by run 'r2'",),
            ),
        )
        first = PersistentTrajectoryLedger(self.root)
        for trajectory in written:
            first.record(trajectory)

        replayed = PersistentTrajectoryLedger(self.root)

        self.assertEqual(replayed.records(), written)

    def test_write_order_is_preserved(self) -> None:
        first = PersistentTrajectoryLedger(self.root)
        for index in range(5):
            first.record(_trajectory(f"r{index}"))

        replayed = PersistentTrajectoryLedger(self.root)

        self.assertEqual(
            tuple(record.run_id for record in replayed.records()),
            tuple(f"r{index}" for index in range(5)),
        )

    def test_labels_and_clearances_survive_and_still_bind(self) -> None:
        first = PersistentTrajectoryLedger(self.root)
        first.record(_trajectory("r1"))
        first.record(
            _trajectory(
                "r2",
                outcome=OUTCOME_ABORTED,
                abort_cause=ABORT_ENVELOPE_VIOLATION,
                stream_complete=False,
            )
        )
        first.confirm_label(_label("r1"))
        first.clear(_clearance("r2"))
        before = first.training_manifest(_SCOPE)

        replayed = PersistentTrajectoryLedger(self.root)

        self.assertIsNone(replayed.quarantine(_SCOPE))
        self.assertEqual(replayed.training_manifest(_SCOPE), before)
        self.assertEqual(before.run_ids, ("r1",))

    def test_an_uncleared_abort_stays_quarantined_after_a_replay(self) -> None:
        PersistentTrajectoryLedger(self.root).record(
            _trajectory(
                "r1",
                outcome=OUTCOME_ABORTED,
                abort_cause=ABORT_ENVELOPE_VIOLATION,
                stream_complete=False,
            )
        )

        replayed = PersistentTrajectoryLedger(self.root)

        quarantine = replayed.quarantine(_SCOPE)
        self.assertIsNotNone(quarantine)
        self.assertIn("r1", str(quarantine))

    def test_derived_evidence_matches_across_a_replay(self) -> None:
        first = PersistentTrajectoryLedger(self.root)
        first.record(_trajectory("r1"))
        first.record(
            _trajectory(
                "r2",
                outcome=OUTCOME_ABORTED,
                abort_cause=ABORT_ENVELOPE_VIOLATION,
                stream_complete=False,
            )
        )
        before = first.derive_evidence(_SCOPE, STAGE_SHADOW_MODE, _NOW)

        replayed = PersistentTrajectoryLedger(self.root)

        self.assertEqual(
            replayed.derive_evidence(_SCOPE, STAGE_SHADOW_MODE, _NOW), before
        )

    def test_a_label_for_an_unknown_run_stops_the_replay(self) -> None:
        PersistentTrajectoryLedger(self.root).record(_trajectory("r1"))
        with (self.root / LABEL_FILE).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(encode_label(_label("ghost"))) + "\n")

        with self.assertRaises(ValueError) as caught:
            PersistentTrajectoryLedger(self.root)

        message = str(caught.exception)
        self.assertIn(LABEL_FILE, message)
        self.assertIn("line 1", message)

    def test_a_clearance_for_a_healthy_run_stops_the_replay(self) -> None:
        PersistentTrajectoryLedger(self.root).record(_trajectory("r1"))
        path = self.root / CLEARANCE_FILE
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(encode_clearance(_clearance("r1"))) + "\n")

        with self.assertRaises(ValueError) as caught:
            PersistentTrajectoryLedger(self.root)

        self.assertIn(CLEARANCE_FILE, str(caught.exception))

    def test_a_duplicate_run_stops_the_replay(self) -> None:
        first = PersistentTrajectoryLedger(self.root)
        first.record(_trajectory("r1"))
        path = self.root / TRAJECTORY_FILE
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(encode_trajectory(_trajectory("r1"))) + "\n"
            )

        with self.assertRaises(ValueError) as caught:
            PersistentTrajectoryLedger(self.root)

        self.assertIn("line 2", str(caught.exception))

    def test_a_rejected_record_never_reaches_the_file(self) -> None:
        ledger = PersistentTrajectoryLedger(self.root)
        ledger.record(_trajectory("r1"))

        with self.assertRaises(ValueError):
            ledger.record(_trajectory("r1"))

        path = self.root / TRAJECTORY_FILE
        self.assertEqual(
            len(path.read_text(encoding="utf-8").splitlines()), 1
        )
        replayed = PersistentTrajectoryLedger(self.root)
        self.assertEqual(len(replayed.records()), 1)


class LedgerStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name) / "nested" / "ledgers"
        self.addCleanup(self._tmp.cleanup)

    def test_a_store_creates_its_root(self) -> None:
        store = LedgerStore(root=self.root)

        self.assertTrue(self.root.is_dir())
        self.assertEqual(store.admission().root, self.root)
        self.assertEqual(store.trajectories().root, self.root)

    def test_the_two_ledgers_do_not_share_a_file(self) -> None:
        store = LedgerStore(root=self.root)
        store.admission().record(_evidence(STAGE_POLICY_EVALUATION))
        store.trajectories().record(_trajectory("r1"))

        admission = self.root / ADMISSION_FILE
        trajectories = self.root / TRAJECTORY_FILE

        self.assertEqual(
            len(admission.read_text(encoding="utf-8").splitlines()), 1
        )
        self.assertEqual(
            len(trajectories.read_text(encoding="utf-8").splitlines()), 1
        )
        self.assertEqual(len(store.admission().records()), 1)
        self.assertEqual(len(store.trajectories().records()), 1)

    def test_a_reopened_store_sees_both_ledgers(self) -> None:
        store = LedgerStore(root=self.root)
        store.admission().record(_evidence(STAGE_POLICY_EVALUATION))
        store.trajectories().record(_trajectory("r1"))

        reopened = LedgerStore(root=self.root)

        self.assertEqual(len(reopened.admission().records()), 1)
        self.assertEqual(len(reopened.trajectories().records()), 1)

    def test_an_artifact_round_trips_as_readable_json(self) -> None:
        store = LedgerStore(root=self.root)
        payload = {"scope": list(_SCOPE), "run_ids": ["r1", "r2"]}

        path = store.write_artifact("manifest.json", payload)

        self.assertEqual(path, self.root / "manifest.json")
        self.assertIn("\n  ", path.read_text(encoding="utf-8"))
        self.assertEqual(store.read_artifact("manifest.json"), payload)

    def test_rewriting_an_artifact_leaves_no_temporary_file(self) -> None:
        store = LedgerStore(root=self.root)
        store.write_artifact("manifest.json", {"total": 1})

        store.write_artifact("manifest.json", {"total": 2})

        self.assertEqual(store.read_artifact("manifest.json"), {"total": 2})
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_an_artifact_cannot_overwrite_a_ledger(self) -> None:
        store = LedgerStore(root=self.root)

        for name in (ADMISSION_FILE, TRAJECTORY_FILE, LABEL_FILE):
            with self.assertRaises(ValueError):
                store.write_artifact(name, {"total": 0})

    def test_an_artifact_cannot_escape_the_root(self) -> None:
        store = LedgerStore(root=self.root)

        for name in ("../escaped.json", "nested/inner.json", " "):
            with self.assertRaises(ValueError):
                store.write_artifact(name, {"total": 0})


if __name__ == "__main__":
    unittest.main()
