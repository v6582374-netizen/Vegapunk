from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from vegapunk.embodied.admission import (
    STAGE_HARDWARE_SUPERVISED,
    STAGE_POLICY_EVALUATION,
    STAGE_SHADOW_MODE,
)
from vegapunk.embodied.safety import (
    ABORT_ENVELOPE_VIOLATION,
    ABORT_HUMAN_STOP,
)
from vegapunk.embodied.trajectory import (
    OUTCOME_ABORTED,
    OUTCOME_FAILED_VERIFICATION,
    OUTCOME_REFUSED,
    OUTCOME_SUCCEEDED,
    LabelConfirmation,
    RunClearance,
    TrajectoryLedger,
    TrajectoryRecord,
)

_NOW = datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)
_SKILL = "press_physical_button@1"
_EMBODIMENT = "e0f1a2b3c4d5e6f7"
_POLICY = "aabbccddeeff0011"
_SCOPE = (_SKILL, _EMBODIMENT, _POLICY)


def _record(run_id: str, **overrides: object) -> TrajectoryRecord:
    fields: dict[str, object] = {
        "run_id": run_id,
        "stage": STAGE_HARDWARE_SUPERVISED,
        "skill_version_id": _SKILL,
        "contract_digest": "1122334455667788",
        "selection_digest": "99aabbccddeeff00",
        "embodiment_digest": _EMBODIMENT,
        "policy_digest": _POLICY,
        "outcome": OUTCOME_SUCCEEDED,
        "started_at": _NOW,
        "observations": 120,
        "duration_s": 4.0,
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


class TrajectoryRecordTest(unittest.TestCase):
    def test_an_aborted_run_must_name_its_cause(self) -> None:
        with self.assertRaises(ValueError):
            _record("r1", outcome=OUTCOME_ABORTED, stream_complete=False)

    def test_a_non_aborted_run_cannot_carry_an_abort_cause(self) -> None:
        with self.assertRaises(ValueError):
            _record("r1", abort_cause=ABORT_HUMAN_STOP)

    def test_a_refusal_must_record_why(self) -> None:
        with self.assertRaises(ValueError):
            _record("r1", outcome=OUTCOME_REFUSED, observations=0, findings=())

    def test_a_refusal_cannot_report_runtime_observations(self) -> None:
        with self.assertRaises(ValueError):
            _record(
                "r1",
                outcome=OUTCOME_REFUSED,
                observations=4,
                findings=("no approval",),
            )

    def test_success_requires_a_complete_observation_stream(self) -> None:
        with self.assertRaises(ValueError):
            _record("r1", stream_complete=False)

    def test_only_envelope_causes_count_as_safety_violations(self) -> None:
        human = _record(
            "r1",
            outcome=OUTCOME_ABORTED,
            abort_cause=ABORT_HUMAN_STOP,
            stream_complete=False,
        )
        envelope = _record(
            "r2",
            outcome=OUTCOME_ABORTED,
            abort_cause=ABORT_ENVELOPE_VIOLATION,
            stream_complete=False,
        )

        self.assertFalse(human.is_safety_violation)
        self.assertTrue(envelope.is_safety_violation)

    def test_every_abort_is_a_hard_failure_including_a_human_stop(
        self,
    ) -> None:
        record = _record(
            "r1",
            outcome=OUTCOME_ABORTED,
            abort_cause=ABORT_HUMAN_STOP,
            stream_complete=False,
        )

        self.assertTrue(record.is_hard_failure)

    def test_a_refused_run_is_not_an_attempt(self) -> None:
        record = _record(
            "r1",
            outcome=OUTCOME_REFUSED,
            observations=0,
            stream_complete=False,
            findings=("admission blocked",),
        )

        self.assertFalse(record.is_attempt)


class QuarantineTest(unittest.TestCase):
    def test_an_uncleared_abort_quarantines_the_configuration(self) -> None:
        ledger = TrajectoryLedger()
        ledger.record(
            _record(
                "r1",
                outcome=OUTCOME_ABORTED,
                abort_cause=ABORT_ENVELOPE_VIOLATION,
                stream_complete=False,
            )
        )

        blocking = ledger.quarantine(_SCOPE)

        self.assertIsNotNone(blocking)
        self.assertIn("r1", str(blocking))

    def test_a_human_clearance_lifts_the_quarantine(self) -> None:
        ledger = TrajectoryLedger()
        ledger.record(
            _record(
                "r1",
                outcome=OUTCOME_ABORTED,
                abort_cause=ABORT_ENVELOPE_VIOLATION,
                stream_complete=False,
            )
        )

        ledger.clear(
            RunClearance(
                run_id="r1",
                reviewer="lab_owner",
                statement="Re-tuned the force limit and re-ran validation.",
                cleared_at=_NOW + timedelta(hours=1),
            )
        )

        self.assertIsNone(ledger.quarantine(_SCOPE))

    def test_a_refusal_does_not_hide_the_preceding_abort(self) -> None:
        ledger = TrajectoryLedger()
        ledger.record(
            _record(
                "r1",
                outcome=OUTCOME_ABORTED,
                abort_cause=ABORT_ENVELOPE_VIOLATION,
                stream_complete=False,
            )
        )
        ledger.record(
            _record(
                "r2",
                outcome=OUTCOME_REFUSED,
                observations=0,
                stream_complete=False,
                findings=("quarantined",),
            )
        )

        self.assertIsNotNone(ledger.quarantine(_SCOPE))

    def test_a_quarantine_is_scoped_to_its_configuration(self) -> None:
        ledger = TrajectoryLedger()
        ledger.record(
            _record(
                "r1",
                outcome=OUTCOME_ABORTED,
                abort_cause=ABORT_ENVELOPE_VIOLATION,
                stream_complete=False,
            )
        )

        other = (_SKILL, "ffffffffffffffff", _POLICY)

        self.assertIsNone(ledger.quarantine(other))

    def test_clearing_a_run_that_did_not_fail_is_rejected(self) -> None:
        ledger = TrajectoryLedger()
        ledger.record(_record("r1"))

        with self.assertRaises(ValueError):
            ledger.clear(
                RunClearance(
                    run_id="r1",
                    reviewer="lab_owner",
                    statement="Nothing to clear.",
                    cleared_at=_NOW,
                )
            )

    def test_a_trajectory_is_written_once(self) -> None:
        ledger = TrajectoryLedger()
        ledger.record(_record("r1"))

        with self.assertRaises(ValueError):
            ledger.record(_record("r1", duration_s=9.0))


class DerivedEvidenceTest(unittest.TestCase):
    def test_evidence_counts_only_attempts_at_the_named_stage(self) -> None:
        ledger = TrajectoryLedger()
        ledger.record(_record("r1"))
        ledger.record(_record("r2", stage=STAGE_SHADOW_MODE))
        ledger.record(
            _record(
                "r3",
                outcome=OUTCOME_REFUSED,
                observations=0,
                stream_complete=False,
                findings=("no approval",),
            )
        )

        evidence = ledger.derive_evidence(
            _SCOPE, STAGE_HARDWARE_SUPERVISED, recorded_at=_NOW
        )

        self.assertEqual(evidence.attempts, 1)
        self.assertEqual(evidence.successes, 1)

    def test_a_safety_abort_surfaces_in_derived_evidence(self) -> None:
        ledger = TrajectoryLedger()
        ledger.record(_record("r1"))
        ledger.record(
            _record(
                "r2",
                outcome=OUTCOME_ABORTED,
                abort_cause=ABORT_ENVELOPE_VIOLATION,
                stream_complete=False,
            )
        )

        evidence = ledger.derive_evidence(
            _SCOPE, STAGE_HARDWARE_SUPERVISED, recorded_at=_NOW
        )

        self.assertEqual(evidence.attempts, 2)
        self.assertEqual(evidence.successes, 1)
        self.assertEqual(evidence.safety_violations, 1)


class TrainingManifestTest(unittest.TestCase):
    def test_a_confirmed_hardware_success_is_eligible(self) -> None:
        ledger = TrajectoryLedger()
        ledger.record(_record("r1"))
        ledger.confirm_label(_label("r1"))

        manifest = ledger.training_manifest(_SCOPE)

        self.assertEqual(manifest.run_ids, ("r1",))
        self.assertEqual(manifest.success_count, 1)
        self.assertEqual(manifest.excluded, ())

    def test_a_confirmed_failure_is_kept_as_training_evidence(self) -> None:
        ledger = TrajectoryLedger()
        ledger.record(
            _record("r1", outcome=OUTCOME_FAILED_VERIFICATION)
        )
        ledger.confirm_label(_label("r1"))

        manifest = ledger.training_manifest(_SCOPE)

        self.assertEqual(manifest.run_ids, ("r1",))
        self.assertEqual(manifest.failure_count, 1)

    def test_an_unconfirmed_success_is_excluded(self) -> None:
        ledger = TrajectoryLedger()
        ledger.record(_record("r1"))

        manifest = ledger.training_manifest(_SCOPE)

        self.assertEqual(manifest.run_ids, ())
        self.assertIn("human", manifest.excluded[0][1])

    def test_benchmark_stage_runs_are_excluded_from_hardware_data(
        self,
    ) -> None:
        ledger = TrajectoryLedger()
        ledger.record(_record("r1", stage=STAGE_POLICY_EVALUATION))
        ledger.confirm_label(_label("r1"))

        manifest = ledger.training_manifest(_SCOPE)

        self.assertEqual(manifest.run_ids, ())
        self.assertIn("real-robot", manifest.excluded[0][1])

    def test_an_unverified_embodiment_disqualifies_a_trajectory(self) -> None:
        ledger = TrajectoryLedger()
        ledger.record(_record("r1", embodiment_verified=False))
        ledger.confirm_label(_label("r1"))

        manifest = ledger.training_manifest(_SCOPE)

        self.assertEqual(manifest.run_ids, ())
        self.assertIn("embodiment", manifest.excluded[0][1])

    def test_an_incomplete_stream_disqualifies_a_trajectory(self) -> None:
        ledger = TrajectoryLedger()
        ledger.record(
            _record(
                "r1",
                outcome=OUTCOME_ABORTED,
                abort_cause=ABORT_HUMAN_STOP,
                stream_complete=False,
            )
        )
        ledger.confirm_label(_label("r1"))

        manifest = ledger.training_manifest(_SCOPE)

        self.assertEqual(manifest.run_ids, ())
        self.assertIn("stream", manifest.excluded[0][1])

    def test_a_refused_run_cannot_be_label_confirmed(self) -> None:
        ledger = TrajectoryLedger()
        ledger.record(
            _record(
                "r1",
                outcome=OUTCOME_REFUSED,
                observations=0,
                stream_complete=False,
                findings=("no approval",),
            )
        )

        with self.assertRaises(ValueError):
            ledger.confirm_label(_label("r1"))

    def test_the_manifest_digest_changes_when_its_membership_changes(
        self,
    ) -> None:
        ledger = TrajectoryLedger()
        ledger.record(_record("r1"))
        ledger.confirm_label(_label("r1"))
        first = ledger.training_manifest(_SCOPE).digest

        ledger.record(_record("r2"))
        ledger.confirm_label(_label("r2"))

        self.assertNotEqual(first, ledger.training_manifest(_SCOPE).digest)


if __name__ == "__main__":
    unittest.main()
