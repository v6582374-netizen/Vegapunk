"""Native Discovery Launch lifecycle, persistence, and deterministic runner seam."""

from __future__ import annotations

import copy
import json
import os
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - the native desktop target is POSIX.
    fcntl = None


ACTIVE_LAUNCH_STATES = frozenset({"starting", "running", "stopping"})
TERMINAL_LAUNCH_STATES = frozenset({"stopped", "interrupted", "completed", "failed"})
FAKE_RUNNER_DELAY_SECONDS = 0.05


class LaunchValidationError(ValueError):
    """Raised when a Launch request does not identify an eligible revision."""


class ActiveLaunchConflict(RuntimeError):
    """Raised when the single active Launch slot is already owned."""


class IdempotencyConflict(RuntimeError):
    """Raised when one idempotency key is reused for a different request."""


class LaunchStateConflict(RuntimeError):
    """Raised when a lifecycle action is not valid for the current Launch state."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        with temporary.open("r+", encoding="utf-8") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class DiscoveryLaunchStore:
    """Own one durable active Launch slot and its lifecycle state machine.

    The fake runner is deliberately small, but it follows the same durable boundaries as the
    native runner: each Launch owns immutable snapshots, a checkpoint, an append-only raw log,
    and one or more execution attempts. A POSIX lock serializes admission and lifecycle writes
    across sidecar instances, while the per-attempt runner marker lets a restarted sidecar adopt a
    still-live runner without starting another one.
    """

    def __init__(self, discovery_root: str | Path):
        self._root = Path(discovery_root)
        self._launches_root = self._root / "launches"
        self._index_path = self._launches_root / "index.json"
        self._lock_path = self._launches_root / ".lock"
        self._lock = threading.RLock()
        self._records: dict[str, dict[str, Any]] = {}
        self._active_launch_id: str | None = None
        self._history_ids: list[str] = []
        self._idempotency: dict[str, dict[str, Any]] = {}
        with self._transaction():
            self._load_from_disk()
            if self._reconcile_locked():
                self._persist_index()

    @contextmanager
    def _transaction(self):
        with self._lock:
            self._launches_root.mkdir(parents=True, exist_ok=True)
            handle = self._lock_path.open("a+", encoding="utf-8")
            try:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()

    def snapshot(self) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        if self._lock_owned():
            return self._snapshot_unlocked()
        with self._transaction():
            self._load_from_disk()
            if self._reconcile_locked():
                self._persist_index()
            return self._snapshot_unlocked()

    def get(self, launch_id: str) -> dict[str, Any]:
        if self._lock_owned():
            record = self._records.get(launch_id)
            if record is None:
                raise KeyError(launch_id)
            return self._public_record(record)
        with self._transaction():
            self._load_from_disk()
            if self._reconcile_locked():
                self._persist_index()
            record = self._records.get(launch_id)
            if record is None:
                raise KeyError(launch_id)
            return self._public_record(record)

    def replay_idempotent(
        self, idempotency_key: str, request_fingerprint: str
    ) -> dict[str, Any] | None:
        with self._transaction():
            self._load_from_disk()
            if self._reconcile_locked():
                self._persist_index()
            previous = self._idempotency.get(idempotency_key)
            if previous is None:
                return None
            if previous["request_fingerprint"] != request_fingerprint:
                raise IdempotencyConflict(
                    "Idempotency-Key was already used for a different Launch request"
                )
            return copy.deepcopy(previous["result"])

    def admit(
        self,
        *,
        request_fingerprint: str,
        idempotency_key: str,
        input_snapshot: dict[str, Any],
        configuration_snapshot: dict[str, Any],
        response_builder: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        """Reserve the active slot, persist snapshots, and start one fake execution attempt."""
        with self._transaction():
            self._load_from_disk()
            if self._reconcile_locked():
                self._persist_index()
            previous = self._idempotency.get(idempotency_key)
            if previous is not None:
                if previous["request_fingerprint"] != request_fingerprint:
                    raise IdempotencyConflict(
                        "Idempotency-Key was already used for a different Launch request"
                    )
                return copy.deepcopy(previous["result"])

            self._raise_if_active_locked()
            launch_id = f"launch-{uuid.uuid4().hex}"
            launch_dir = self._launches_root / launch_id
            launch_dir.mkdir(parents=True, exist_ok=False)
            _atomic_write_json(launch_dir / "input_snapshot.json", input_snapshot)
            _atomic_write_json(
                launch_dir / "launch_configuration.json", configuration_snapshot
            )
            (launch_dir / "runner.log").write_text("", encoding="utf-8")

            attempt_id = f"attempt-{uuid.uuid4().hex}"
            adoption_nonce = uuid.uuid4().hex
            record = {
                "launch_id": launch_id,
                "preparation_id": input_snapshot["preparation_id"],
                "revision_id": input_snapshot["revision_id"],
                "created_at": _now(),
                "started_at": None,
                "completed_at": None,
                "state": "starting",
                "stage": "admission",
                "round": 0,
                "attempts": [self._new_attempt(attempt_id, adoption_nonce)],
                "current_attempt_id": attempt_id,
                "runner_pid": os.getpid(),
                "adoption_nonce": adoption_nonce,
                "checkpoint": None,
                "resumable": False,
                "stop_requested_at": None,
                "stopped_at": None,
                "stop_reason": None,
                "outcome": None,
                "error": None,
                "input_snapshot": copy.deepcopy(input_snapshot),
                "launch_configuration_snapshot": copy.deepcopy(
                    configuration_snapshot
                ),
            }
            self._records[launch_id] = record
            self._active_launch_id = launch_id
            self._write_runner_marker(record, "starting")
            self._persist_record(record)

            result = {
                "launch_id": launch_id,
                "state": "starting",
                "snapshot": response_builder(),
            }
            self._idempotency[idempotency_key] = {
                "request_fingerprint": request_fingerprint,
                "result": copy.deepcopy(result),
            }
            self._persist_index()
            worker = threading.Thread(
                target=self._run_fake,
                args=(launch_id, attempt_id),
                name=f"discovery-launch-{launch_id}",
                daemon=True,
            )
            worker.start()
            return result

    def stop(self, launch_id: str) -> dict[str, Any]:
        with self._transaction():
            self._load_from_disk()
            if self._reconcile_locked():
                self._persist_index()
            record = self._record_or_raise_locked(launch_id)
            state = record["state"]
            if state in {"starting", "running"}:
                record["state"] = "stopping"
                record["stop_requested_at"] = _now()
                record["stop_reason"] = "researcher requested graceful stop"
                self._persist_record(record)
                self._persist_index()
            elif state not in {"stopping", "stopped"}:
                raise LaunchStateConflict(
                    f"Stop is unavailable while Launch is {state}"
                )
            return self._public_record(record)

    def resume(
        self,
        launch_id: str,
        *,
        request_fingerprint: str,
        idempotency_key: str,
        response_builder: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        with self._transaction():
            self._load_from_disk()
            if self._reconcile_locked():
                self._persist_index()
            previous = self._idempotency.get(idempotency_key)
            if previous is not None:
                if previous["request_fingerprint"] != request_fingerprint:
                    raise IdempotencyConflict(
                        "Idempotency-Key was already used for a different Launch request"
                    )
                return copy.deepcopy(previous["result"])

            record = self._record_or_raise_locked(launch_id)
            if record["state"] not in {"stopped", "interrupted"}:
                raise LaunchStateConflict(
                    f"Resume is unavailable while Launch is {record['state']}"
                )
            if not record.get("resumable"):
                raise LaunchStateConflict(
                    "Launch does not have a reconciled checkpoint that can be resumed"
                )
            self._raise_if_active_locked()

            checkpoint = record.get("checkpoint") or {}
            attempt_id = f"attempt-{uuid.uuid4().hex}"
            adoption_nonce = uuid.uuid4().hex
            attempt = self._new_attempt(attempt_id, adoption_nonce)
            attempt["resume_from_round"] = int(checkpoint.get("round", 0) or 0)
            record["attempts"].append(attempt)
            record["current_attempt_id"] = attempt_id
            record["state"] = "starting"
            record["stage"] = "resuming"
            record["outcome"] = None
            record["error"] = None
            record["completed_at"] = None
            record["runner_pid"] = os.getpid()
            record["adoption_nonce"] = adoption_nonce
            record["stop_requested_at"] = None
            record["stopped_at"] = None
            record["stop_reason"] = None
            self._active_launch_id = launch_id
            self._history_ids = [item for item in self._history_ids if item != launch_id]
            self._write_runner_marker(record, "starting")
            self._persist_record(record)

            result = {
                "launch_id": launch_id,
                "state": "starting",
                "snapshot": response_builder(),
            }
            self._idempotency[idempotency_key] = {
                "request_fingerprint": request_fingerprint,
                "result": copy.deepcopy(result),
            }
            self._persist_index()
            worker = threading.Thread(
                target=self._run_fake,
                args=(launch_id, attempt_id),
                name=f"discovery-launch-{launch_id}",
                daemon=True,
            )
            worker.start()
            return result

    def _run_fake(self, launch_id: str, attempt_id: str) -> None:
        stages = ("preparing", "research", "finalizing")
        try:
            with self._transaction():
                self._load_from_disk()
                record = self._record_or_raise_locked(launch_id)
                attempt = self._attempt_or_raise(record, attempt_id)
                if record["state"] == "stopping":
                    self._write_checkpoint_locked(
                        record,
                        attempt,
                        record.get("stage", "admission"),
                        int(record.get("round", 0) or 0),
                        "stop",
                    )
                    self._finish_stopped_locked(record, attempt, "stop before runner start")
                    return
                if record["state"] != "starting":
                    return
                record["state"] = "running"
                record["stage"] = stages[0]
                record["started_at"] = record["started_at"] or _now()
                record["runner_pid"] = os.getpid()
                attempt["started_at"] = _now()
                attempt["state"] = "running"
                self._write_runner_marker(record, "running")
                self._persist_record(record)
                self._persist_index()
                start_round = int(attempt.get("resume_from_round", 0) or 0)

            if start_round >= len(stages):
                with self._transaction():
                    self._load_from_disk()
                    record = self._record_or_raise_locked(launch_id)
                    attempt = self._attempt_or_raise(record, attempt_id)
                    self._finish_completed_locked(record, attempt)
                return

            for round_number, stage in enumerate(
                stages[start_round:], start=start_round + 1
            ):
                with self._transaction():
                    self._load_from_disk()
                    record = self._record_or_raise_locked(launch_id)
                    attempt = self._attempt_or_raise(record, attempt_id)
                    if record["state"] == "stopping":
                        self._write_checkpoint_locked(
                            record, attempt, stage, round_number, "stop"
                        )
                        self._finish_stopped_locked(record, attempt, "graceful stop")
                        return
                    if record["state"] not in ACTIVE_LAUNCH_STATES:
                        return
                    record["stage"] = stage
                    record["round"] = round_number
                    self._write_checkpoint_locked(
                        record, attempt, stage, round_number, "progress"
                    )
                    self._write_runner_marker(record, "running")
                    self._persist_record(record)
                    self._persist_index()

                self._append_log(launch_id, f"fake-runner: {stage} round={round_number}")
                fail_stage = (
                    record.get("launch_configuration_snapshot", {})
                    .get("settings", {})
                    .get("__discovery_fake_failure_stage")
                )
                if fail_stage == stage:
                    raise RuntimeError(f"deterministic fake runner failed at {stage}")
                time.sleep(FAKE_RUNNER_DELAY_SECONDS)

            with self._transaction():
                self._load_from_disk()
                record = self._record_or_raise_locked(launch_id)
                attempt = self._attempt_or_raise(record, attempt_id)
                if record["state"] == "stopping":
                    self._finish_stopped_locked(record, attempt, "graceful stop")
                elif record["state"] in ACTIVE_LAUNCH_STATES:
                    self._finish_completed_locked(record, attempt)
        except (KeyError, OSError, RuntimeError, ValueError) as error:
            with self._transaction():
                self._load_from_disk()
                record = self._records.get(launch_id)
                if record is None or record.get("current_attempt_id") != attempt_id:
                    return
                attempt = self._attempt_or_raise(record, attempt_id)
                if record["state"] in ACTIVE_LAUNCH_STATES:
                    self._finish_failed_locked(record, attempt, str(error))

    def _finish_completed_locked(
        self, record: dict[str, Any], attempt: dict[str, Any]
    ) -> None:
        finished_at = _now()
        record["state"] = "completed"
        record["stage"] = "completed"
        record["completed_at"] = finished_at
        record["outcome"] = "completed"
        record["runner_pid"] = None
        record["resumable"] = False
        attempt["finished_at"] = finished_at
        attempt["state"] = "completed"
        self._close_active_locked(record)

    def _finish_failed_locked(
        self, record: dict[str, Any], attempt: dict[str, Any], error: str
    ) -> None:
        finished_at = _now()
        record["state"] = "failed"
        record["stage"] = "failed"
        record["completed_at"] = finished_at
        record["outcome"] = "failed"
        record["error"] = error or "Discovery runner failed"
        record["runner_pid"] = None
        record["resumable"] = False
        attempt["finished_at"] = finished_at
        attempt["state"] = "failed"
        self._close_active_locked(record)

    def _finish_stopped_locked(
        self, record: dict[str, Any], attempt: dict[str, Any], reason: str
    ) -> None:
        finished_at = _now()
        record["state"] = "stopped"
        record["stage"] = "stopped"
        record["stopped_at"] = finished_at
        record["stop_reason"] = reason
        record["outcome"] = "stopped"
        record["runner_pid"] = None
        record["resumable"] = True
        attempt["finished_at"] = finished_at
        attempt["state"] = "stopped"
        self._close_active_locked(record)

    def _close_active_locked(self, record: dict[str, Any]) -> None:
        self._remove_runner_marker(record["launch_id"])
        self._active_launch_id = None
        self._add_history_locked(record["launch_id"])
        self._persist_record(record)
        self._persist_index()

    def _reconcile_locked(self) -> bool:
        launch_id = self._active_launch_id
        if not launch_id:
            return False
        record = self._records.get(launch_id)
        if record is None:
            self._active_launch_id = None
            return True
        if record.get("state") not in ACTIVE_LAUNCH_STATES:
            self._active_launch_id = None
            if record.get("state") in TERMINAL_LAUNCH_STATES:
                self._add_history_locked(launch_id)
            self._persist_record(record)
            return True
        if self._runner_matches(record):
            return False

        attempt = self._attempt_or_none(record, record.get("current_attempt_id"))
        if attempt is not None:
            attempt["state"] = "interrupted"
            attempt["finished_at"] = _now()
        record["state"] = "interrupted"
        record["stage"] = "interrupted"
        record["outcome"] = "interrupted"
        record["error"] = "runner disappeared before a trusted terminal outcome"
        record["runner_pid"] = None
        record["resumable"] = bool(record.get("checkpoint"))
        self._remove_runner_marker(launch_id)
        self._active_launch_id = None
        self._add_history_locked(launch_id)
        self._persist_record(record)
        return True

    def _runner_matches(self, record: dict[str, Any]) -> bool:
        marker = self._read_runner_marker(record["launch_id"])
        if not isinstance(marker, dict):
            return False
        if marker.get("attempt_id") != record.get("current_attempt_id"):
            return False
        if marker.get("adoption_nonce") != record.get("adoption_nonce"):
            return False
        pid = marker.get("pid")
        return isinstance(pid, int) and pid == record.get("runner_pid") and self._pid_alive(pid)

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            return False
        return True

    def _write_runner_marker(self, record: dict[str, Any], status: str) -> None:
        _atomic_write_json(
            self._launches_root
            / record["launch_id"]
            / "runner.json",
            {
                "pid": record["runner_pid"],
                "attempt_id": record["current_attempt_id"],
                "adoption_nonce": record["adoption_nonce"],
                "status": status,
                "heartbeat_at": _now(),
            },
        )

    def _read_runner_marker(self, launch_id: str) -> dict[str, Any] | None:
        try:
            raw = json.loads(
                (self._launches_root / launch_id / "runner.json").read_text(
                    encoding="utf-8"
                )
            )
        except (FileNotFoundError, OSError, ValueError):
            return None
        return raw if isinstance(raw, dict) else None

    def _remove_runner_marker(self, launch_id: str) -> None:
        (self._launches_root / launch_id / "runner.json").unlink(missing_ok=True)

    def _write_checkpoint_locked(
        self,
        record: dict[str, Any],
        attempt: dict[str, Any],
        stage: str,
        round_number: int,
        reason: str,
    ) -> None:
        checkpoint = {
            "attempt_id": attempt["attempt_id"],
            "stage": stage,
            "round": round_number,
            "reason": reason,
            "created_at": _now(),
        }
        record["checkpoint"] = checkpoint
        _atomic_write_json(
            self._launches_root / record["launch_id"] / "checkpoint.json", checkpoint
        )

    def _append_log(self, launch_id: str, line: str) -> None:
        with (self._launches_root / launch_id / "runner.log").open(
            "a", encoding="utf-8"
        ) as log:
            log.write(f"{line}\n")

    def _raise_if_active_locked(self) -> None:
        active_id = self._active_launch_id
        if not active_id:
            return
        active = self._records.get(active_id)
        if active is not None and active.get("state") in ACTIVE_LAUNCH_STATES:
            raise ActiveLaunchConflict("another Discovery Launch is already active")
        self._active_launch_id = None
        if active is not None and active.get("state") in TERMINAL_LAUNCH_STATES:
            self._add_history_locked(active_id)

    def _record_or_raise_locked(self, launch_id: str) -> dict[str, Any]:
        record = self._records.get(launch_id)
        if record is None:
            raise KeyError(launch_id)
        return record

    @staticmethod
    def _new_attempt(attempt_id: str, adoption_nonce: str) -> dict[str, Any]:
        return {
            "attempt_id": attempt_id,
            "started_at": None,
            "finished_at": None,
            "state": "starting",
            "adoption_nonce": adoption_nonce,
            "resume_from_round": 0,
        }

    @staticmethod
    def _attempt_or_none(
        record: dict[str, Any], attempt_id: str | None
    ) -> dict[str, Any] | None:
        if not isinstance(attempt_id, str):
            return None
        return next(
            (attempt for attempt in record.get("attempts", []) if attempt.get("attempt_id") == attempt_id),
            None,
        )

    def _attempt_or_raise(
        self, record: dict[str, Any], attempt_id: str
    ) -> dict[str, Any]:
        attempt = self._attempt_or_none(record, attempt_id)
        if attempt is None:
            raise KeyError(attempt_id)
        return attempt

    def _add_history_locked(self, launch_id: str) -> None:
        self._history_ids = [item for item in self._history_ids if item != launch_id]
        self._history_ids.insert(0, launch_id)

    def _snapshot_unlocked(self) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        active = self._records.get(self._active_launch_id or "")
        history = [
            self._public_record(self._records[launch_id])
            for launch_id in self._history_ids
            if launch_id in self._records
        ]
        return (
            self._public_record(active) if active is not None else None,
            history,
        )

    def _public_record(self, record: dict[str, Any]) -> dict[str, Any]:
        public = copy.deepcopy(record)
        public["configuration_snapshot"] = copy.deepcopy(
            public["launch_configuration_snapshot"]
        )
        return public

    def _persist_record(self, record: dict[str, Any]) -> None:
        launch_dir = self._launches_root / record["launch_id"]
        _atomic_write_json(launch_dir / "record.json", record)

    def _persist_index(self) -> None:
        _atomic_write_json(
            self._index_path,
            {
                "schema_version": 2,
                "active_launch_id": self._active_launch_id,
                "history_ids": self._history_ids,
                "launch_ids": list(self._records),
                "idempotency": self._idempotency,
            },
        )

    def _load_from_disk(self) -> None:
        try:
            index = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            self._records = {}
            self._active_launch_id = None
            self._history_ids = []
            self._idempotency = {}
            return
        if not isinstance(index, dict):
            return

        records: dict[str, dict[str, Any]] = {}
        for launch_id in index.get("launch_ids", []):
            if not isinstance(launch_id, str):
                continue
            try:
                record = json.loads(
                    (self._launches_root / launch_id / "record.json").read_text(
                        encoding="utf-8"
                    )
                )
            except (FileNotFoundError, OSError, ValueError):
                continue
            if isinstance(record, dict) and record.get("launch_id") == launch_id:
                records[launch_id] = record
        self._records = records
        self._history_ids = [
            launch_id
            for launch_id in index.get("history_ids", [])
            if launch_id in self._records
        ]
        active_id = index.get("active_launch_id")
        self._active_launch_id = active_id if active_id in self._records else None
        raw_idempotency = index.get("idempotency", {})
        self._idempotency = (
            {
                key: value
                for key, value in raw_idempotency.items()
                if isinstance(key, str)
                and isinstance(value, dict)
                and isinstance(value.get("request_fingerprint"), str)
                and isinstance(value.get("result"), dict)
            }
            if isinstance(raw_idempotency, dict)
            else {}
        )

    def _lock_owned(self) -> bool:
        owned = getattr(self._lock, "_is_owned", None)
        return bool(owned and owned())
