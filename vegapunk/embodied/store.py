"""Durable ledgers: evidence that outlives the process that recorded it.

The admission ladder and the trajectory ledger are the only places where the
right to move a robot is written down, and both of them lived in a Python
list. That is not a storage detail. Evidence accumulates across days, runs,
and reviewers, so a ledger that dies with its interpreter cannot hold a
multi-stage ladder at all: every restart rewinds the record to zero attempts,
and a configuration that was never validated becomes indistinguishable from
one whose validation was forgotten.

This module refuses three things.

It refuses to reformat what it stores. A ``HumanApproval`` is pinned to the
digest of the exact evidence set an approver reviewed, and that digest is
computed from record fields in the order they were recorded. Persistence
therefore writes one record per line in write order and reads it back through
the same encoding the digest is built from, so a replay cannot reorder,
re-time, or round a value and thereby withdraw an approval nobody revisited --
or, worse, silently keep one that no longer covers the evidence.

It refuses to skip a line it cannot read. A half-written trailing line is
exactly what a crash leaves behind, and the tempting behaviour -- ignore it,
carry on -- converts lost evidence into a higher success rate and a dropped
safety violation into admission. A malformed line names its file and line
number and stops the replay, because a ledger that will not open is a problem
someone fixes, while a ledger quietly missing an abort is one nobody sees.

It refuses to interpret. There is no schema version, no migration, no index,
no lock and no database. The record types own their invariants and the ledgers
own their semantics; this module owns bytes appended to one file per record
kind and never rewritten. Human-readable artifacts are the single exception
and are replaced atomically rather than edited, so a reader never observes
half of one.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, TypeVar

from vegapunk.embodied.admission import AdmissionLedger, EvidenceRecord
from vegapunk.embodied.trajectory import (
    LabelConfirmation,
    RunClearance,
    TrajectoryLedger,
    TrajectoryRecord,
)

DEFAULT_LEDGER_ROOT = Path(".vegapunk/embodied")
"""Where ledgers live when the caller expresses no preference.

Relative to the working directory and hidden by a leading dot: the evidence
for a checkout belongs beside that checkout, and must never be mistaken for
source that a tool would reformat.
"""

ADMISSION_FILE = "admission.jsonl"
TRAJECTORY_FILE = "trajectories.jsonl"
LABEL_FILE = "labels.jsonl"
CLEARANCE_FILE = "clearances.jsonl"

_LEDGER_FILES = frozenset(
    {ADMISSION_FILE, TRAJECTORY_FILE, LABEL_FILE, CLEARANCE_FILE}
)
"""One file per record kind, so no two ledgers share an append target.

Kinds are separated rather than tagged in a single stream because a reader of
one kind then cannot be confused by another, and a corrupt trajectory line
cannot make admission evidence unreadable.
"""

_ENCODING = "utf-8"

_RecordT = TypeVar("_RecordT")


def _corruption(path: Path, number: int, detail: str) -> str:
    return (
        f"{path} line {number} is not a readable ledger record ({detail}); "
        "the replay stops here rather than dropping evidence"
    )


def _append(path: Path, payload: dict[str, object]) -> None:
    """Add one record as one line, on disk before the call returns."""
    line = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with path.open("a", encoding=_ENCODING) as handle:
        handle.write(line + "\n")
        handle.flush()


def _rows(path: Path) -> list[tuple[int, dict[str, object]]]:
    if not path.exists():
        return []

    rows: list[tuple[int, dict[str, object]]] = []
    with path.open("r", encoding=_ENCODING) as handle:
        for number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                raise ValueError(
                    _corruption(path, number, "the line carries no record")
                )
            try:
                row = json.loads(text)
            except json.JSONDecodeError as error:
                raise ValueError(
                    _corruption(path, number, str(error))
                ) from error
            if not isinstance(row, dict):
                raise ValueError(
                    _corruption(path, number, "expected a JSON object")
                )
            rows.append((number, row))
    return rows


def _replay(
    path: Path,
    decode: Callable[[dict[str, object]], _RecordT],
    accept: Callable[[_RecordT], object],
) -> None:
    """Re-apply a file through the ledger's own admission of records.

    Replay goes through the ledger API rather than into its private lists, so
    a file cannot install a state the ledger would have rejected in life.
    """
    for number, row in _rows(path):
        try:
            record = decode(row)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(_corruption(path, number, str(error))) from error
        try:
            accept(record)
        except (KeyError, ValueError) as error:
            raise ValueError(_corruption(path, number, str(error))) from error


def _text(row: dict[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise ValueError(f"field {key!r} is not a string")
    return value


def _optional_text(row: dict[str, object], key: str) -> Optional[str]:
    value = row[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"field {key!r} is neither a string nor null")
    return value


def _count(row: dict[str, object], key: str) -> int:
    value = row[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"field {key!r} is not an integer")
    return value


def _number(row: dict[str, object], key: str) -> float:
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"field {key!r} is not a number")
    return float(value)


def _flag(row: dict[str, object], key: str) -> bool:
    value = row[key]
    if not isinstance(value, bool):
        raise ValueError(f"field {key!r} is not a boolean")
    return value


def _moment(row: dict[str, object], key: str) -> datetime:
    return datetime.fromisoformat(_text(row, key))


def _texts(row: dict[str, object], key: str) -> tuple[str, ...]:
    value = row[key]
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise ValueError(f"field {key!r} is not a list of strings")
    return tuple(str(item) for item in value)


def encode_evidence(record: EvidenceRecord) -> dict[str, object]:
    """Encode evidence exactly as its digest sees it.

    The digest hashes ``as_evidence()``; storing anything else would let a
    replayed ledger disagree with the approval pinned to it.
    """
    return dict(record.as_evidence())


def decode_evidence(row: dict[str, object]) -> EvidenceRecord:
    return EvidenceRecord(
        stage=_text(row, "stage"),
        skill_version_id=_text(row, "skill_version_id"),
        embodiment_digest=_text(row, "embodiment_digest"),
        policy_digest=_optional_text(row, "policy_digest"),
        attempts=_count(row, "attempts"),
        successes=_count(row, "successes"),
        safety_violations=_count(row, "safety_violations"),
        recorded_at=_moment(row, "recorded_at"),
        notes=_text(row, "notes"),
    )


def encode_trajectory(record: TrajectoryRecord) -> dict[str, object]:
    """Encode a trajectory as its identity plus the parts nothing hashes.

    ``identity()`` is the digest-bearing view and is reused verbatim;
    ``detail`` and ``findings`` are narrative, but they are the only record of
    why a run was refused, so they are stored too.
    """
    payload = dict(record.identity())
    payload["detail"] = record.detail
    payload["findings"] = list(record.findings)
    return payload


def decode_trajectory(row: dict[str, object]) -> TrajectoryRecord:
    return TrajectoryRecord(
        run_id=_text(row, "run_id"),
        stage=_text(row, "stage"),
        skill_version_id=_text(row, "skill_version_id"),
        contract_digest=_text(row, "contract_digest"),
        selection_digest=_text(row, "selection_digest"),
        embodiment_digest=_text(row, "embodiment_digest"),
        policy_digest=_optional_text(row, "policy_digest"),
        outcome=_text(row, "outcome"),
        started_at=_moment(row, "started_at"),
        observations=_count(row, "observations"),
        duration_s=_number(row, "duration_s"),
        abort_cause=_optional_text(row, "abort_cause"),
        detail=_text(row, "detail"),
        stream_complete=_flag(row, "stream_complete"),
        embodiment_verified=_flag(row, "embodiment_verified"),
        findings=_texts(row, "findings"),
    )


def encode_label(record: LabelConfirmation) -> dict[str, object]:
    return {
        "run_id": record.run_id,
        "reviewer": record.reviewer,
        "statement": record.statement,
        "confirmed_at": record.confirmed_at.isoformat(),
    }


def decode_label(row: dict[str, object]) -> LabelConfirmation:
    return LabelConfirmation(
        run_id=_text(row, "run_id"),
        reviewer=_text(row, "reviewer"),
        statement=_text(row, "statement"),
        confirmed_at=_moment(row, "confirmed_at"),
    )


def encode_clearance(record: RunClearance) -> dict[str, object]:
    return {
        "run_id": record.run_id,
        "reviewer": record.reviewer,
        "statement": record.statement,
        "cleared_at": record.cleared_at.isoformat(),
    }


def decode_clearance(row: dict[str, object]) -> RunClearance:
    return RunClearance(
        run_id=_text(row, "run_id"),
        reviewer=_text(row, "reviewer"),
        statement=_text(row, "statement"),
        cleared_at=_moment(row, "cleared_at"),
    )


class PersistentAdmissionLedger(AdmissionLedger):
    """An ``AdmissionLedger`` that remembers across processes.

    Construction replays the file, so the ledger a second process opens holds
    the evidence the first one recorded, in the order it was recorded, and
    reports the same evidence digest.
    """

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._path = self._root / ADMISSION_FILE
        _replay(self._path, decode_evidence, super().record)

    @property
    def root(self) -> Path:
        return self._root

    def record(self, evidence: EvidenceRecord) -> EvidenceRecord:
        """Accept evidence in memory first, then commit the line.

        A record the ledger would reject must never reach the file: the file
        is replayed through the same acceptance, so a rejected line would make
        the ledger permanently unopenable.
        """
        recorded = super().record(evidence)
        _append(self._path, encode_evidence(recorded))
        return recorded


class PersistentTrajectoryLedger(TrajectoryLedger):
    """A ``TrajectoryLedger`` that remembers across processes.

    Runs, labels and clearances are separate files replayed in that order,
    because a label or a clearance names a run and the ledger refuses to
    attach either to a run it has not seen. Order is a consequence of the
    invariant, not of the file layout.
    """

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._trajectories = self._root / TRAJECTORY_FILE
        self._labels_path = self._root / LABEL_FILE
        self._clearances_path = self._root / CLEARANCE_FILE
        _replay(self._trajectories, decode_trajectory, super().record)
        _replay(self._labels_path, decode_label, super().confirm_label)
        _replay(self._clearances_path, decode_clearance, super().clear)

    @property
    def root(self) -> Path:
        return self._root

    def record(self, trajectory: TrajectoryRecord) -> TrajectoryRecord:
        recorded = super().record(trajectory)
        _append(self._trajectories, encode_trajectory(recorded))
        return recorded

    def confirm_label(self, confirmation: LabelConfirmation) -> None:
        super().confirm_label(confirmation)
        _append(self._labels_path, encode_label(confirmation))

    def clear(self, clearance: RunClearance) -> None:
        super().clear(clearance)
        _append(self._clearances_path, encode_clearance(clearance))


@dataclass(frozen=True)
class LedgerStore:
    """One directory holding one installation's durable record."""

    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root))
        self.root.mkdir(parents=True, exist_ok=True)

    def admission(self) -> PersistentAdmissionLedger:
        return PersistentAdmissionLedger(self.root)

    def trajectories(self) -> PersistentTrajectoryLedger:
        return PersistentTrajectoryLedger(self.root)

    def write_artifact(self, name: str, payload: object) -> Path:
        """Publish something for a human to read, all at once.

        Indented rather than compact because the only reason to write an
        artifact is that a person will open it, and replaced through a
        temporary file because a reader who catches a partial write would
        report a shorter result than actually happened.
        """
        path = self._artifact_path(name)
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        staged = path.with_name(path.name + ".tmp")
        staged.write_text(text, encoding=_ENCODING)
        os.replace(staged, path)
        return path

    def read_artifact(self, name: str) -> object:
        path = self._artifact_path(name)
        return json.loads(path.read_text(encoding=_ENCODING))

    def _artifact_path(self, name: str) -> Path:
        if not name.strip():
            raise ValueError("an artifact must be named")
        if "/" in name or "\\" in name or name in {".", ".."}:
            raise ValueError(
                f"artifact name {name!r} must be a plain file name inside "
                "the ledger root"
            )
        if name in _LEDGER_FILES:
            raise ValueError(
                f"artifact name {name!r} is a ledger file; an artifact is "
                "rewritten in place and would destroy recorded evidence"
            )
        return self.root / name
