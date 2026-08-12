"""Native Discovery Launch lifecycle, persistence, and deterministic runner seam."""

from __future__ import annotations

import asyncio
import copy
import json
import math
import os
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable
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
# Leave enough time for a second sidecar instance to reconnect while the deterministic
# runner is observable in its active state.
FAKE_RUNNER_DELAY_SECONDS = 0.1
OBSERVATION_STAGES = ("preparing", "research", "finalizing")
ACTIVITY_LIMIT = 64
EVENT_LIMIT = 128
HISTORY_LIMIT = 64
ATTEMPT_LIMIT = 64
MILESTONE_LIMIT = 16
ARTIFACT_LIMIT = 64
SOURCE_LIMIT = 256
MAX_PUBLIC_SOURCE_BYTES = 1 << 50
PUBLIC_TEXT_LIMIT = 512
RAW_LOG_MAX_BYTES = 512 * 1024
EVENT_LOG_TAIL_BYTES = 2 * 1024 * 1024
EVENT_LINE_MAX_BYTES = 256 * 1024
# Public observations are consumed by JavaScript clients.  Keep all numeric values
# inside the JSON/IEEE-754 safe integer range and reject non-finite floats so a
# corrupted legacy record cannot expand into an enormous response or emit NaN/Inf.
PUBLIC_NUMERIC_LIMIT = (1 << 53) - 1

_PUBLIC_RECORD_FIELDS = (
    "launch_id",
    "preparation_id",
    "revision_id",
    "created_at",
    "started_at",
    "completed_at",
    "state",
    "stage",
    "round",
    "runner_pid",
    "current_attempt_id",
    "resumable",
    "stop_requested_at",
    "stopped_at",
    "stop_reason",
    "outcome",
    "error",
    "event_sequence",
    "activity_truncated_before_sequence",
)


def _new_timeline() -> dict[str, Any]:
    labels = {
        "preparing": "Prepare sources",
        "research": "Run discovery",
        "finalizing": "Finalize outputs",
    }
    return {
        "revision": 0,
        "percent": 0,
        "current_milestone_id": None,
        "milestones": [
            {
                "id": stage,
                "key": stage,
                "label": labels[stage],
                "position": position,
                "state": "pending",
                "summary": None,
                "started_at": None,
                "ended_at": None,
                "attempts": [],
            }
            for position, stage in enumerate(OBSERVATION_STAGES, start=1)
        ],
    }


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


def _sse_data(payload: str) -> str:
    """Frame one raw-log payload without losing embedded line breaks."""
    return "".join(f"data: {line}\n" for line in payload.split("\n")) + "\n"


def _bounded_text(value: Any, limit: int = 160) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 3]}..."


def _public_scalar(value: Any, *, limit: int = PUBLIC_TEXT_LIMIT) -> str | int | float | bool | None:
    """Return a scalar bounded enough for a public observation payload."""
    if isinstance(value, str):
        return value if len(value) <= limit else f"{value[: limit - 3]}..."
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value if abs(value) <= PUBLIC_NUMERIC_LIMIT else None
    if isinstance(value, float):
        return value if math.isfinite(value) and abs(value) <= PUBLIC_NUMERIC_LIMIT else None
    return None


def _public_external_data_snapshot(value: Any) -> dict[str, Any] | None:
    """Whitelist launch-owned external-data metadata for public observations."""

    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {}
    registry = value.get("api_registry")
    if isinstance(registry, list):
        entries: list[dict[str, str]] = []
        for item in registry[:32]:
            if not isinstance(item, dict):
                continue
            entry: dict[str, str] = {}
            for key in ("api_id", "source", "description", "official_docs_url"):
                scalar = _public_scalar(item.get(key), limit=512)
                if isinstance(scalar, str) and scalar.strip():
                    entry[key] = scalar
            if entry:
                entries.append(entry)
        result["api_registry"] = entries
    statuses = value.get("provider_status")
    if isinstance(statuses, dict):
        result["provider_status"] = {
            str(key): str(status)
            for key, status in list(statuses.items())[:32]
            if isinstance(key, str) and isinstance(status, str)
        }
    return result or None


def _compact_idempotency_result(result: dict[str, Any]) -> dict[str, Any]:
    """Keep only durable identity metadata for an idempotent request.

    The HTTP response may contain the complete Preparation/history snapshot, but
    retaining that snapshot once per idempotency key makes the sidecar's in-memory
    index grow quadratically as history grows.  Replays rebuild the public snapshot
    from the current store and pin the selected Launch in ``_replayed_result``.
    """
    compact: dict[str, Any] = {}
    launch_id = result.get("launch_id")
    if isinstance(launch_id, str) and 0 < len(launch_id) <= 256:
        compact["launch_id"] = launch_id
    state = result.get("state")
    if isinstance(state, str) and state in (
        ACTIVE_LAUNCH_STATES
        | TERMINAL_LAUNCH_STATES
        | frozenset({"awaiting_review"})
    ):
        compact["state"] = state
    # Keep a tiny bounded Launch fallback so a stale idempotency index cannot
    # accidentally replay the currently active (unrelated) Launch.  This is
    # deliberately not the full response snapshot and therefore remains O(n) in
    # the number of idempotency keys rather than O(n²) in history size.
    raw_launch = result.get("launch")
    if (
        isinstance(raw_launch, dict)
        and isinstance(compact.get("launch_id"), str)
        and raw_launch.get("launch_id") == compact["launch_id"]
    ):
        launch: dict[str, Any] = {}
        for key in (
            "launch_id",
            "preparation_id",
            "revision_id",
            "created_at",
            "started_at",
            "completed_at",
            "state",
            "stage",
            "round",
            "resumable",
            "stop_requested_at",
            "stopped_at",
            "stop_reason",
            "outcome",
            "error",
        ):
            if key not in raw_launch:
                continue
            value = _public_scalar(raw_launch[key])
            if value is not None:
                launch[key] = value
        summary = _public_input_summary(
            raw_launch.get("input_summary"),
            fallback_preparation_id=raw_launch.get("preparation_id"),
            fallback_revision_id=raw_launch.get("revision_id"),
        )
        if summary is not None:
            launch["input_summary"] = summary
            title = summary.get("title")
            if isinstance(title, str) and title:
                launch["title"] = title
        if launch:
            compact["launch"] = launch
    return compact


def _public_input_summary(
    input_snapshot: dict[str, Any] | None,
    *,
    fallback_preparation_id: str | None = None,
    fallback_revision_id: str | None = None,
) -> dict[str, Any] | None:
    """Project the immutable run input into bounded metadata for UI observations.

    ``input_snapshot.json`` remains a private worker input. This function deliberately
    reads only the identity, source manifest, and a bounded task label; it never copies
    research text or source bytes into a public response.
    """
    if not isinstance(input_snapshot, dict):
        return None
    safe_fallback_preparation_id = (
        _public_scalar(fallback_preparation_id, limit=128)
        if isinstance(fallback_preparation_id, str)
        else None
    )
    safe_fallback_revision_id = (
        _public_scalar(fallback_revision_id, limit=128)
        if isinstance(fallback_revision_id, str)
        else None
    )
    raw_sources = input_snapshot.get("sources")
    sources: list[dict[str, Any]] = []
    source_count = 0
    source_bytes = 0
    if isinstance(raw_sources, list):
        source_count = len(raw_sources)
        for source in raw_sources[:SOURCE_LIMIT]:
            if not isinstance(source, dict):
                continue
            manifest: dict[str, Any] = {}
            for key in ("source_id", "filename", "extension", "size", "sha256"):
                if key not in source:
                    continue
                candidate = source[key]
                if key == "sha256":
                    if (
                        isinstance(candidate, str)
                        and len(candidate) == 64
                        and all(character in "0123456789abcdef" for character in candidate)
                    ):
                        manifest[key] = candidate
                elif key == "size":
                    if (
                        isinstance(candidate, int)
                        and not isinstance(candidate, bool)
                        and 0 <= candidate <= MAX_PUBLIC_SOURCE_BYTES
                    ):
                        manifest[key] = candidate
                else:
                    limit = 32 if key == "extension" else 256
                    bounded = _public_scalar(candidate, limit=limit)
                    if bounded is not None:
                        manifest[key] = bounded
            if manifest:
                sources.append(manifest)
                size = manifest.get("size")
                if isinstance(size, int) and not isinstance(size, bool):
                    source_bytes = min(MAX_PUBLIC_SOURCE_BYTES, source_bytes + size)
    execution_input = input_snapshot.get("execution_input")
    task_description = (
        execution_input.get("task_description")
        if isinstance(execution_input, dict)
        else input_snapshot.get("title")
        if isinstance(input_snapshot.get("title"), str)
        else None
    )
    task_type = (
        execution_input.get("task_type")
        if isinstance(execution_input, dict)
        else input_snapshot.get("task_type")
    )
    summary: dict[str, Any] = {
        "preparation_id": (
            _public_scalar(input_snapshot.get("preparation_id"), limit=128)
            if isinstance(input_snapshot.get("preparation_id"), str)
            else safe_fallback_preparation_id
        ),
        "revision_id": (
            _public_scalar(input_snapshot.get("revision_id"), limit=128)
            if isinstance(input_snapshot.get("revision_id"), str)
            else safe_fallback_revision_id
        ),
        "preparation_fingerprint": (
            _public_scalar(input_snapshot.get("preparation_fingerprint"), limit=128)
            if isinstance(input_snapshot.get("preparation_fingerprint"), str)
            else None
        ),
        "source_count": source_count,
        "source_bytes": source_bytes,
        "sources": sources,
    }
    if source_count > SOURCE_LIMIT:
        summary["sources_truncated"] = True
    title = _bounded_text(task_description)
    if title:
        summary["title"] = title
    if task_type in {"auto", "sci"}:
        summary["task_type"] = task_type
    return summary


class DiscoveryLaunchStore:
    """Own one durable active Launch slot and its lifecycle state machine.

    The deterministic runner remains available for the native test seam, while the Web
    mode starts one isolated worker process that invokes the production launcher. Both
    modes share the same durable boundaries: immutable snapshots, a checkpoint, an
    append-only raw log, and one or more execution attempts. A POSIX lock serializes
    admission and lifecycle writes across sidecar instances, while the per-attempt
    runner marker lets a restarted sidecar observe a still-live worker without starting
    another one.
    """

    def __init__(
        self,
        discovery_root: str | Path,
        *,
        runner_mode: str = "fake",
        repository_root: str | Path | None = None,
    ):
        if runner_mode not in {"fake", "real"}:
            raise ValueError("runner_mode must be 'fake' or 'real'")
        self._root = Path(discovery_root)
        self._launches_root = self._root / "launches"
        self._index_path = self._launches_root / "index.json"
        self._lock_path = self._launches_root / ".lock"
        self._lock = threading.RLock()
        self._records: dict[str, dict[str, Any]] = {}
        self._active_launch_id: str | None = None
        self._history_ids: list[str] = []
        self._idempotency: dict[str, dict[str, Any]] = {}
        self._runner_mode = runner_mode
        self._repository_root = Path(
            repository_root
            or os.environ.get(
                "VEGAPUNK_REPOSITORY_ROOT", Path(__file__).resolve().parents[5]
            )
        ).expanduser().resolve()
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

    def status(self, launch_id: str) -> dict[str, Any]:
        """Return the server-authoritative Runtime Desk observation for one Launch."""
        if self._lock_owned():
            return self._status_unlocked(launch_id)
        with self._transaction():
            self._load_from_disk()
            if self._reconcile_locked():
                self._persist_index()
            return self._status_unlocked(launch_id)

    def events(self, launch_id: str, after: int = 0) -> dict[str, Any]:
        """Return structured durable events after an increasing per-Launch cursor."""
        if self._lock_owned():
            return self._events_unlocked(launch_id, after)
        with self._transaction():
            self._load_from_disk()
            if self._reconcile_locked():
                self._persist_index()
            return self._events_unlocked(launch_id, after)

    async def stream_log(
        self, launch_id: str, poll_interval: float = 0.05
    ) -> AsyncIterator[str]:
        """Replay one Launch's merged runner.log, then follow it while active."""
        position = 0
        pending = ""
        log_path = self.log_path(launch_id)
        while True:
            record = self.get(launch_id)
            active = record["state"] in ACTIVE_LAUNCH_STATES
            if log_path.is_file():
                with log_path.open("r", encoding="utf-8", errors="replace") as stream:
                    if position == 0:
                        try:
                            size = log_path.stat().st_size
                        except OSError:
                            size = 0
                        if size > RAW_LOG_MAX_BYTES:
                            position = size - RAW_LOG_MAX_BYTES
                            stream.seek(position)
                            stream.readline()
                            yield _sse_data(
                                "[raw log truncated to the most recent 512 KiB]\n"
                            )
                        else:
                            stream.seek(position)
                    else:
                        stream.seek(position)
                    chunk = stream.read()
                    position = stream.tell()
                pending += chunk
                complete_lines = pending.split("\n")
                pending = complete_lines.pop() or ""
                for line in complete_lines:
                    yield _sse_data(f"{line}\n")
            if not active:
                if pending:
                    yield _sse_data(pending)
                return
            await asyncio.sleep(poll_interval)

    def log_path(self, launch_id: str) -> Path:
        """Return the selected Launch's only Raw Discovery Console source."""
        if self._lock_owned():
            self._record_or_raise_locked(launch_id)
        else:
            with self._transaction():
                self._load_from_disk()
                if self._reconcile_locked():
                    self._persist_index()
                self._record_or_raise_locked(launch_id)
        return self._launches_root / launch_id / "runner.log"

    def artifacts_root(self, launch_id: str) -> Path:
        """Return the selected Launch's dedicated artifact root after identity validation."""
        if self._lock_owned():
            self._record_or_raise_locked(launch_id)
        else:
            with self._transaction():
                self._load_from_disk()
                if self._reconcile_locked():
                    self._persist_index()
                self._record_or_raise_locked(launch_id)
        return self._launches_root / launch_id / "artifacts"

    def replay_idempotent(
        self,
        idempotency_key: str,
        request_fingerprint: str,
        response_builder: Callable[[], dict[str, Any]] | None = None,
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
            return self._replayed_result(previous["result"], response_builder)

    def _replayed_result(
        self,
        result: dict[str, Any],
        response_builder: Callable[[], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Replay idempotency metadata without replaying a historical raw snapshot."""
        replay: dict[str, Any] = {}
        for key in ("launch_id", "state"):
            if key not in result:
                continue
            value = _public_scalar(result[key], limit=256)
            if value is not None:
                replay[key] = value
        launch_id = replay.get("launch_id")
        record = self._records.get(launch_id) if isinstance(launch_id, str) else None
        launch: dict[str, Any] | None = None
        if record is not None:
            launch = self._public_record(record)
        else:
            stored_launch = result.get("launch")
            if (
                isinstance(stored_launch, dict)
                and isinstance(launch_id, str)
                and stored_launch.get("launch_id") == launch_id
            ):
                # The fallback was sanitized before persistence, but project it
                # once more so hand-edited/legacy indexes cannot inject fields.
                launch = self._public_record(stored_launch)
        replay["launch"] = copy.deepcopy(launch) if launch is not None else None
        if launch is not None:
            replay["state"] = launch.get("state", replay.get("state"))
        # Durable/in-memory idempotency entries intentionally contain no snapshot.
        # Callers that need the full facade response provide a builder; a low-level
        # replay without one returns only the bounded Launch metadata.
        snapshot = response_builder() if response_builder is not None else None
        # A replay is scoped to the Launch identified by the idempotency key.  The
        # normal facade snapshot is intentionally global and may have no active
        # Launch after the original run completed (or may already describe a newer
        # Launch), so returning it verbatim would make a retry point at the wrong
        # task.  Keep the global preparation/history context, but pin the selected
        # Launch into ``current_launch`` and remove its duplicate history entry.
        if isinstance(snapshot, dict):
            # Always replace the builder's global current_launch.  If the durable
            # record is gone and no bounded fallback exists, returning the current
            # unrelated Launch would be a correctness and security bug.
            snapshot["current_launch"] = copy.deepcopy(launch) if launch is not None else None
            history = snapshot.get("history")
            if isinstance(history, list):
                snapshot["history"] = [
                    item
                    for item in history
                    if not isinstance(item, dict)
                    or item.get("launch_id") != launch_id
                ]
        if isinstance(snapshot, dict):
            replay["snapshot"] = snapshot
        return replay

    def admit(
        self,
        *,
        request_fingerprint: str,
        idempotency_key: str,
        input_snapshot: dict[str, Any],
        configuration_snapshot: dict[str, Any],
        response_builder: Callable[[], dict[str, Any]],
        input_snapshot_factory: Callable[[], dict[str, Any]] | None = None,
        input_snapshot_cleanup: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Reserve the active slot, persist snapshots, and start one execution attempt."""
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
                return self._replayed_result(previous["result"], response_builder)

            self._raise_if_active_locked()
            return self._admit_locked(
                request_fingerprint=request_fingerprint,
                idempotency_key=idempotency_key,
                input_snapshot=input_snapshot,
                configuration_snapshot=configuration_snapshot,
                response_builder=response_builder,
                input_snapshot_factory=input_snapshot_factory,
                input_snapshot_cleanup=input_snapshot_cleanup,
            )

    def _admit_locked(
        self,
        *,
        request_fingerprint: str,
        idempotency_key: str,
        input_snapshot: dict[str, Any],
        configuration_snapshot: dict[str, Any],
        response_builder: Callable[[], dict[str, Any]],
        input_snapshot_factory: Callable[[], dict[str, Any]] | None,
        input_snapshot_cleanup: Callable[[], None] | None,
    ) -> dict[str, Any]:
        """Create a new Launch while the caller holds the shared transaction lock."""
        record_persisted = False
        try:
            if input_snapshot_factory is not None:
                # Materialize private source blobs only after the shared admission
                # lock confirms that this request owns the active Launch slot. This
                # avoids cross-sidecar races where a rejected request cleans up a
                # blob another request is about to reference.
                input_snapshot = input_snapshot_factory()
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
                "paper_orchestra": None,
                "event_sequence": 0,
                "timeline": _new_timeline(),
                "activity": [],
                "activity_truncated_before_sequence": 0,
                # The worker reads the private input_snapshot.json. Keep only a
                # bounded manifest in the lifecycle record so status/history cannot
                # accidentally duplicate source bytes.
                "input_summary": _public_input_summary(
                    input_snapshot,
                    fallback_preparation_id=input_snapshot.get("preparation_id"),
                    fallback_revision_id=input_snapshot.get("revision_id"),
                ),
                "launch_configuration_snapshot": copy.deepcopy(
                    configuration_snapshot
                ),
            }
            self._records[launch_id] = record
            self._active_launch_id = launch_id
            self._emit_event_locked(
                record,
                "work.state.updated",
                {"state": "starting", "stage": "admission", "round": 0},
                activity_text="Launch admitted and awaiting runner startup",
            )
            self._write_runner_marker(record, "starting")
            self._persist_record(record)
            record_persisted = True

            result = {
                "launch_id": launch_id,
                "state": "starting",
                "launch": self._public_record(record),
                "snapshot": response_builder(),
            }
            self._idempotency[idempotency_key] = {
                "request_fingerprint": request_fingerprint,
                "result": _compact_idempotency_result(result),
            }
            self._persist_index()
            self._start_runner_locked(record, attempt_id)
            if record["state"] != "starting":
                result["state"] = record["state"]
                result["launch"] = self._public_record(record)
                result["snapshot"] = response_builder()
                self._idempotency[idempotency_key]["result"] = _compact_idempotency_result(
                    result
                )
                self._persist_index()
            return result
        except Exception:
            if not record_persisted and input_snapshot_cleanup is not None:
                input_snapshot_cleanup()
            raise

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
                self._emit_event_locked(
                    record,
                    "work.state.updated",
                    {"state": "stopping", "stage": record["stage"], "round": record["round"]},
                    activity_text="Graceful Stop requested",
                )
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
                return self._replayed_result(previous["result"], response_builder)

            record = self._record_or_raise_locked(launch_id)
            if record["state"] not in {"stopped", "interrupted"}:
                raise LaunchStateConflict(
                    f"Resume is unavailable while Launch is {record['state']}"
                )
            if not record.get("resumable"):
                raise LaunchStateConflict(
                    "Launch does not have a reconciled checkpoint that can be resumed"
                )
            configuration = record.get("launch_configuration_snapshot") or {}
            preferences = configuration.get("discovery_launch_preferences") or {}
            snapshot_backend = preferences.get("backend", "codex")
            if snapshot_backend not in {"codex", "qwen_code", "openhands"}:
                raise LaunchStateConflict(
                    "Launch uses a removed Discovery backend and cannot be resumed"
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
            record["paper_orchestra"] = None
            record["completed_at"] = None
            record["runner_pid"] = os.getpid()
            record["adoption_nonce"] = adoption_nonce
            record["stop_requested_at"] = None
            record["stopped_at"] = None
            record["stop_reason"] = None
            self._active_launch_id = launch_id
            self._history_ids = [item for item in self._history_ids if item != launch_id]
            self._ensure_observation_state(record)
            self._emit_event_locked(
                record,
                "work.state.updated",
                {"state": "starting", "stage": "resuming", "round": record["round"]},
                activity_text="Launch resume admitted as a new execution attempt",
            )
            self._write_runner_marker(record, "starting")
            self._persist_record(record)

            result = {
                "launch_id": launch_id,
                "state": "starting",
                "launch": self._public_record(record),
                "snapshot": response_builder(),
            }
            self._idempotency[idempotency_key] = {
                "request_fingerprint": request_fingerprint,
                "result": _compact_idempotency_result(result),
            }
            self._persist_index()
            self._start_runner_locked(record, attempt_id, resume=True)
            if record["state"] != "starting":
                result["state"] = record["state"]
                result["launch"] = self._public_record(record)
                result["snapshot"] = response_builder()
                self._idempotency[idempotency_key]["result"] = _compact_idempotency_result(
                    result
                )
                self._persist_index()
            return result

    def _start_runner_locked(
        self,
        record: dict[str, Any],
        attempt_id: str,
        *,
        resume: bool = False,
    ) -> None:
        if self._runner_mode == "real":
            self._start_real_worker_locked(record, attempt_id, resume=resume)
            return
        worker = threading.Thread(
            target=self._run_fake,
            args=(record["launch_id"], attempt_id),
            name=f"discovery-launch-{record['launch_id']}",
            daemon=True,
        )
        worker.start()

    def _start_real_worker_locked(
        self,
        record: dict[str, Any],
        attempt_id: str,
        *,
        resume: bool,
    ) -> None:
        """Start the one Web worker that invokes the production launcher.

        The worker owns the subprocess and finalizes the durable Launch record.  The
        sidecar only persists its PID/attempt marker here; it never imports Discovery,
        Experiment, or PaperOrchestra internals into the request-serving process.
        """

        worker_entry = Path(__file__).with_name("discovery_worker.py")
        launcher_entry = self._repository_root / "launch_discovery.py"
        configuration = record.get("launch_configuration_snapshot") or {}
        preferences = configuration.get("discovery_launch_preferences") or {}
        exp_backend = preferences.get("backend", "codex")
        if exp_backend not in {"codex", "qwen_code", "openhands"}:
            # A pre-setting snapshot may omit the field and therefore defaults to
            # Codex.  A snapshot containing a removed identity is terminal instead
            # of being silently migrated to another coding-agent tool.
            attempt = self._attempt_or_raise(record, attempt_id)
            self._finish_failed_locked(
                record,
                attempt,
                f"Unsupported Discovery backend in Launch snapshot: {exp_backend}",
            )
            self._persist_record(record)
            self._persist_index()
            return
        command = [
            sys.executable,
            str(worker_entry),
            str(launcher_entry),
            "--launch_dir",
            str(self._launches_root / record["launch_id"]),
            "--discovery-root",
            str(self._root),
            "--attempt-id",
            attempt_id,
            "--repository-root",
            str(self._repository_root),
            "--mode",
            "experiment",
            "--exp_backend",
            exp_backend,
        ]
        if resume:
            command.append("--resume")

        environment = os.environ.copy()
        python_path = [
            str(self._repository_root),
            str(self._repository_root / "desktop" / "openworker" / "upstream"),
        ]
        existing_python_path = environment.get("PYTHONPATH")
        if existing_python_path:
            python_path.append(existing_python_path)
        environment["PYTHONPATH"] = os.pathsep.join(python_path)

        try:
            process = subprocess.Popen(
                command,
                cwd=str(self._repository_root),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as error:
            attempt = self._attempt_or_raise(record, attempt_id)
            self._finish_failed_locked(
                record, attempt, f"Unable to start Discovery worker: {error}"
            )
            return

        record["runner_pid"] = process.pid
        self._write_runner_marker(record, "starting")
        self._persist_record(record)
        self._persist_index()

    def worker_started(
        self, launch_id: str, attempt_id: str, pid: int | None = None
    ) -> None:
        """Mark a real worker as running after it has claimed its attempt."""

        with self._transaction():
            self._load_from_disk()
            record = self._record_or_raise_locked(launch_id)
            if record.get("current_attempt_id") != attempt_id:
                return
            attempt = self._attempt_or_raise(record, attempt_id)
            if record.get("state") != "starting":
                return
            if pid is not None:
                record["runner_pid"] = pid
            record["state"] = "running"
            record["stage"] = "preparing"
            record["started_at"] = record.get("started_at") or _now()
            attempt["started_at"] = attempt.get("started_at") or _now()
            attempt["state"] = "running"
            self._ensure_observation_state(record)
            self._emit_event_locked(
                record,
                "work.state.updated",
                {
                    "state": "running",
                    "stage": "preparing",
                    "round": int(record.get("round", 0) or 0),
                },
                activity_text="Discovery worker is running the production launcher",
            )
            self._activate_stage_locked(
                record, attempt, "preparing", int(record.get("round", 0) or 0) or 1
            )
            self._write_runner_marker(record, "running")
            self._persist_record(record)
            self._persist_index()

    def worker_stage(
        self,
        launch_id: str,
        attempt_id: str,
        stage: str,
        round_number: int,
    ) -> None:
        """Project coarse production progress into the existing observation timeline."""

        with self._transaction():
            self._load_from_disk()
            record = self._record_or_raise_locked(launch_id)
            if record.get("current_attempt_id") != attempt_id:
                return
            if record.get("state") not in ACTIVE_LAUNCH_STATES:
                return
            attempt = self._attempt_or_raise(record, attempt_id)
            record["round"] = max(
                int(record.get("round", 0) or 0), int(round_number)
            )
            self._activate_stage_locked(record, attempt, stage, int(round_number))
            self._write_checkpoint_locked(
                record, attempt, stage, int(round_number), "production-launcher"
            )
            self._write_runner_marker(record, "running")
            self._persist_record(record)
            self._persist_index()

    def worker_finish(
        self,
        launch_id: str,
        attempt_id: str,
        *,
        succeeded: bool,
        stopped: bool = False,
        error: str | None = None,
        paper_orchestra: dict[str, Any] | None = None,
    ) -> None:
        """Finalize a worker-owned attempt without executing workflow internals here."""

        with self._transaction():
            self._load_from_disk()
            record = self._records.get(launch_id)
            if record is None or record.get("current_attempt_id") != attempt_id:
                return
            # A restarted sidecar may already have reconciled this attempt as
            # interrupted (or another supervisor may have finalized it).  A stale
            # worker must not resurrect a terminal Launch after that decision.
            if record.get("state") in TERMINAL_LAUNCH_STATES:
                return
            attempt = self._attempt_or_raise(record, attempt_id)
            if stopped or record.get("state") == "stopping":
                self._finish_stopped_locked(
                    record, attempt, error or "graceful stop"
                )
                return
            if succeeded:
                self._finish_completed_real_locked(
                    record, attempt, paper_orchestra=paper_orchestra
                )
            else:
                self._finish_failed_locked(
                    record, attempt, error or "Discovery worker failed"
                )

    def _finish_completed_real_locked(
        self,
        record: dict[str, Any],
        attempt: dict[str, Any],
        *,
        paper_orchestra: dict[str, Any] | None = None,
    ) -> None:
        self._ensure_observation_state(record)
        finished_at = _now()
        record["state"] = "completed"
        record["stage"] = "completed"
        record["completed_at"] = finished_at
        record["outcome"] = "completed"
        record["runner_pid"] = None
        record["resumable"] = False
        if paper_orchestra is not None:
            record["paper_orchestra"] = copy.deepcopy(paper_orchestra)
        attempt["finished_at"] = finished_at
        attempt["state"] = "completed"
        self._finish_timeline_locked(record, "completed", finished_at)
        if paper_orchestra and paper_orchestra.get("state") == "failed":
            self._emit_event_locked(
                record,
                "work.state.updated",
                {"state": "completed", "stage": "completed", "round": record["round"]},
                level="warning",
                activity_text=(
                    "Discovery completed; PaperOrchestra failed and its error was "
                    "kept separate from the Discovery outcome"
                ),
            )
        else:
            self._emit_event_locked(
                record,
                "work.state.updated",
                {"state": "completed", "stage": "completed", "round": record["round"]},
                activity_text="Discovery and automatic PaperOrchestra completed",
            )
        self._close_active_locked(record)

    def _run_fake(self, launch_id: str, attempt_id: str) -> None:
        stages = OBSERVATION_STAGES
        try:
            with self._transaction():
                self._load_from_disk()
                record = self._record_or_raise_locked(launch_id)
                attempt = self._attempt_or_raise(record, attempt_id)
                self._ensure_observation_state(record)
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
                self._emit_event_locked(
                    record,
                    "work.state.updated",
                    {"state": "running", "stage": stages[0], "round": 0},
                    activity_text="Discovery runner is running",
                )
                self._activate_stage_locked(record, attempt, stages[0], 1)
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
                    self._activate_stage_locked(record, attempt, stage, round_number)
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
        self._ensure_observation_state(record)
        finished_at = _now()
        self._write_fake_artifacts(record)
        record["state"] = "completed"
        record["stage"] = "completed"
        record["completed_at"] = finished_at
        record["outcome"] = "completed"
        record["runner_pid"] = None
        record["resumable"] = False
        attempt["finished_at"] = finished_at
        attempt["state"] = "completed"
        self._finish_timeline_locked(record, "completed", finished_at)
        self._emit_event_locked(
            record,
            "work.state.updated",
            {"state": "completed", "stage": "completed", "round": record["round"]},
            activity_text="Discovery Launch completed",
        )
        self._close_active_locked(record)

    def _write_fake_artifacts(self, record: dict[str, Any]) -> None:
        """Create deterministic researcher-facing outputs for the native fake-runner seam."""
        root = self._launches_root / record["launch_id"] / "artifacts"
        root.mkdir(parents=True, exist_ok=True)
        (root / "report.md").write_text(
            f"# Discovery report\n\nLaunch `{record['launch_id']}` completed.\n",
            encoding="utf-8",
        )
        _atomic_write_json(
            root / "summary.json",
            {
                "launch_id": record["launch_id"],
                "state": "completed",
                "rounds": record.get("round", 0),
            },
        )

    def _finish_failed_locked(
        self, record: dict[str, Any], attempt: dict[str, Any], error: str
    ) -> None:
        self._ensure_observation_state(record)
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
        self._finish_timeline_locked(record, "failed", finished_at)
        self._emit_event_locked(
            record,
            "work.state.updated",
            {"state": "failed", "stage": "failed", "round": record["round"]},
            level="error",
            activity_text=record["error"],
        )
        self._close_active_locked(record)

    def _finish_stopped_locked(
        self, record: dict[str, Any], attempt: dict[str, Any], reason: str
    ) -> None:
        self._ensure_observation_state(record)
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
        self._finish_timeline_locked(record, "stopped", finished_at)
        self._emit_event_locked(
            record,
            "work.state.updated",
            {"state": "stopped", "stage": "stopped", "round": record["round"]},
            activity_text="Discovery Launch stopped at a durable checkpoint",
        )
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
        self._ensure_observation_state(record)
        self._finish_timeline_locked(record, "interrupted", _now())
        self._emit_event_locked(
            record,
            "work.state.updated",
            {"state": "interrupted", "stage": "interrupted", "round": record["round"]},
            level="warning",
            activity_text="Runner interruption reconciled; explicit Resume is required",
        )
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

    def _ensure_observation_state(self, record: dict[str, Any]) -> None:
        event_sequence = record.get("event_sequence")
        if not isinstance(event_sequence, int) or isinstance(event_sequence, bool):
            # Only legacy records without the persisted cursor need an event-log
            # recovery scan.  Normal status/snapshot reads must not reread the
            # complete append-only log on every request.
            record["event_sequence"] = self._latest_persisted_event_sequence(
                record["launch_id"]
            )
        timeline = record.get("timeline")
        if not isinstance(timeline, dict) or not isinstance(timeline.get("milestones"), list):
            record["timeline"] = _new_timeline()
        if not isinstance(record.get("activity"), list):
            record["activity"] = []
        if not isinstance(record.get("activity_truncated_before_sequence"), int):
            record["activity_truncated_before_sequence"] = 0

    def _latest_persisted_event_sequence(self, launch_id: str) -> int:
        event_path = self._launches_root / launch_id / "events.jsonl"
        latest = 0
        for line in self._event_tail_lines(event_path):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            sequence = event.get("sequence") if isinstance(event, dict) else None
            if isinstance(sequence, int):
                latest = max(latest, sequence)
        return latest

    @staticmethod
    def _event_tail_lines(event_path: Path) -> list[str]:
        """Read only a bounded tail of the append-only event log.

        Event polling is on the UI hot path. Never materialize an unbounded historical
        ``events.jsonl`` file, and never let one malformed giant line allocate without
        a limit. If the cursor is older than the retained tail, callers report the
        returned oldest sequence as the truncation boundary.
        """
        try:
            size = event_path.stat().st_size
        except OSError:
            return []
        start = max(0, size - EVENT_LOG_TAIL_BYTES)
        try:
            with event_path.open("rb") as stream:
                if start:
                    stream.seek(start)
                    # Start at a complete line. ``readline(limit)`` is deliberately
                    # bounded; a malformed line is skipped in bounded chunks.
                    while True:
                        fragment = stream.readline(EVENT_LINE_MAX_BYTES + 1)
                        if not fragment or fragment.endswith(b"\n"):
                            break
                payload = stream.read(EVENT_LOG_TAIL_BYTES)
        except OSError:
            return []
        lines: list[str] = []
        for raw_line in payload.splitlines():
            if len(raw_line) > EVENT_LINE_MAX_BYTES:
                continue
            try:
                lines.append(raw_line.decode("utf-8"))
            except UnicodeDecodeError:
                continue
        return lines

    def _activate_stage_locked(
        self,
        record: dict[str, Any],
        attempt: dict[str, Any],
        stage: str,
        round_number: int,
    ) -> None:
        self._ensure_observation_state(record)
        if stage not in OBSERVATION_STAGES:
            return
        timeline = record["timeline"]
        milestones = timeline["milestones"]
        index = OBSERVATION_STAGES.index(stage)
        milestone = milestones[index]
        if (
            timeline.get("current_milestone_id") == stage
            and milestone.get("state") == "active"
        ):
            return

        now = _now()
        for prior in milestones[:index]:
            if prior.get("state") == "active":
                prior["state"] = "completed"
                prior["ended_at"] = now
                attempts = prior.get("attempts", [])
                if attempts and attempts[-1].get("state") == "active":
                    attempts[-1]["state"] = "completed"
                    attempts[-1]["ended_at"] = now

        previous_state = milestone.get("state")
        if previous_state in {"completed", "stopped", "interrupted", "failed"}:
            number = len(milestone.get("attempts", [])) + 1
            milestone.setdefault("attempts", []).append(
                {
                    "number": number,
                    "state": "active",
                    "started_at": now,
                    "ended_at": None,
                    "summary": None,
                }
            )
        elif not milestone.get("attempts"):
            milestone["attempts"] = [
                {
                    "number": 1,
                    "state": "active",
                    "started_at": now,
                    "ended_at": None,
                    "summary": None,
                }
            ]
        else:
            milestone["attempts"][-1].update(
                {"state": "active", "started_at": now, "ended_at": None}
            )
        milestone["state"] = "active"
        milestone["started_at"] = milestone.get("started_at") or now
        milestone["ended_at"] = None
        milestone["summary"] = f"Round {round_number}"
        timeline["current_milestone_id"] = stage
        timeline["revision"] = int(timeline.get("revision", 0)) + 1
        timeline["percent"] = int(
            sum(item.get("state") == "completed" for item in milestones)
            * 100
            / len(milestones)
        )
        record["stage"] = stage
        self._emit_event_locked(
            record,
            "progress.milestone.updated",
            {"milestone": copy.deepcopy(milestone), "timeline": copy.deepcopy(timeline)},
            milestone_id=stage,
            activity_text=f"Stage {milestone['label']} started at round {round_number}",
        )

    def _finish_timeline_locked(
        self, record: dict[str, Any], state: str, ended_at: str
    ) -> None:
        self._ensure_observation_state(record)
        timeline = record["timeline"]
        milestones = timeline["milestones"]
        current_id = timeline.get("current_milestone_id")
        current = next(
            (item for item in milestones if item.get("id") == current_id), None
        )
        if current is not None and current.get("state") == "active":
            current["state"] = state
            current["ended_at"] = ended_at
            attempts = current.get("attempts", [])
            if attempts and attempts[-1].get("state") == "active":
                attempts[-1]["state"] = state
                attempts[-1]["ended_at"] = ended_at
        if state == "completed":
            for milestone in milestones:
                milestone["state"] = "completed"
                milestone["ended_at"] = milestone.get("ended_at") or ended_at
                attempts = milestone.get("attempts", [])
                if attempts and attempts[-1].get("state") == "active":
                    attempts[-1]["state"] = "completed"
                    attempts[-1]["ended_at"] = ended_at
            timeline["current_milestone_id"] = None
        timeline["revision"] = int(timeline.get("revision", 0)) + 1
        timeline["percent"] = int(
            sum(item.get("state") == "completed" for item in milestones)
            * 100
            / len(milestones)
        )
        self._emit_event_locked(
            record,
            "progress.milestone.updated",
            {"timeline": copy.deepcopy(timeline)},
            milestone_id=current_id,
        )

    def _emit_event_locked(
        self,
        record: dict[str, Any],
        event_type: str,
        data: dict[str, Any],
        *,
        level: str = "info",
        milestone_id: str | None = None,
        activity_text: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_observation_state(record)
        sequence = int(record.get("event_sequence", 0)) + 1
        occurred_at = _now()
        event = {
            "sequence": sequence,
            "occurred_at": occurred_at,
            "type": event_type,
            "data": copy.deepcopy(data),
        }
        event_path = self._launches_root / record["launch_id"] / "events.jsonl"
        event_path.parent.mkdir(parents=True, exist_ok=True)
        with event_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        record["event_sequence"] = sequence
        if activity_text:
            activity = {
                "sequence": sequence,
                "occurred_at": occurred_at,
                "level": level,
                "milestone_id": milestone_id,
                "text": activity_text,
            }
            record["activity"].append(activity)
            if len(record["activity"]) > ACTIVITY_LIMIT:
                record["activity_truncated_before_sequence"] = record["activity"][
                    -ACTIVITY_LIMIT
                ]["sequence"] - 1
                record["activity"] = record["activity"][-ACTIVITY_LIMIT:]
        return event

    def _status_unlocked(self, launch_id: str) -> dict[str, Any]:
        record = self._record_or_raise_locked(launch_id)
        self._ensure_observation_state(record)
        public_launch = self._public_record(record)
        activity = self._public_activity(record["activity"])
        public_round = public_launch.get("round", 0)
        if not isinstance(public_round, int) or isinstance(public_round, bool):
            public_round = 0
        public_event_sequence = public_launch.get("event_sequence", 0)
        if not isinstance(public_event_sequence, int) or isinstance(public_event_sequence, bool):
            public_event_sequence = 0
        public_truncated_before = public_launch.get(
            "activity_truncated_before_sequence", 0
        )
        if not isinstance(public_truncated_before, int) or isinstance(
            public_truncated_before, bool
        ):
            public_truncated_before = 0
        return {
            "launch": public_launch,
            "state": public_launch.get("state"),
            "stage": public_launch.get("stage"),
            "round": public_round,
            "checkpoint": self._public_checkpoint(record.get("checkpoint")),
            "timeline": self._public_timeline(record.get("timeline")),
            "activity": {
                "oldest_sequence": activity[0].get("sequence") if activity else None,
                "newest_sequence": activity[-1].get("sequence") if activity else None,
                "truncated_before_sequence": public_truncated_before,
                "items": activity,
            },
            "allowed_actions": self._allowed_actions(record),
            "produced_outputs": self._produced_outputs(launch_id),
            "latest_event_sequence": public_event_sequence,
        }

    def _events_unlocked(self, launch_id: str, after: int) -> dict[str, Any]:
        record = self._record_or_raise_locked(launch_id)
        self._ensure_observation_state(record)
        event_path = self._launches_root / launch_id / "events.jsonl"
        events: list[dict[str, Any]] = []
        for line in self._event_tail_lines(event_path):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            sequence = _public_scalar(event.get("sequence", 0))
            if not isinstance(sequence, int) or isinstance(sequence, bool):
                continue
            if sequence > after:
                projected = self._public_event(event)
                if projected is not None:
                    events.append(projected)
        if len(events) > EVENT_LIMIT:
            events = events[-EVENT_LIMIT:]
        all_sequences = [event["sequence"] for event in events if "sequence" in event]
        latest_sequence = _public_scalar(record.get("event_sequence", 0))
        if not isinstance(latest_sequence, int) or isinstance(latest_sequence, bool):
            latest_sequence = 0
        return {
            "launch_id": launch_id,
            "events": events,
            "oldest_sequence": min(all_sequences) if all_sequences else None,
            "latest_sequence": latest_sequence,
            "truncated_before_sequence": (
                (min(all_sequences) - 1) if all_sequences else 0
            ),
        }

    def _produced_outputs(self, launch_id: str) -> list[dict[str, str]]:
        root = self._launches_root / launch_id / "artifacts"
        if not root.is_dir():
            return []
        outputs: list[dict[str, str]] = []
        for path in root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                outputs.append({"path": path.relative_to(root).as_posix(), "label": path.name})
                if len(outputs) >= ARTIFACT_LIMIT:
                    break
        return outputs

    @staticmethod
    def _allowed_actions(record: dict[str, Any]) -> list[str]:
        state = record.get("state")
        if state in {"starting", "running"}:
            return ["stop"]
        if state in {"stopped", "interrupted"} and record.get("resumable"):
            return ["resume"]
        return []

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
        del self._history_ids[HISTORY_LIMIT:]

    def _snapshot_unlocked(self) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        active = self._records.get(self._active_launch_id or "")
        history = [
            self._public_record(self._records[launch_id])
            for launch_id in self._history_ids[:HISTORY_LIMIT]
            if launch_id in self._records
        ]
        return (
            self._public_record(active) if active is not None else None,
            history,
        )

    @staticmethod
    def _public_checkpoint(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        checkpoint = {
            key: _public_scalar(value[key])
            for key in (
                "checkpoint_id",
                "seam",
                "attempt_id",
                "stage",
                "round",
                "reason",
                "created_at",
            )
            if key in value
            and _public_scalar(value[key]) is not None
        }
        raw_artifacts = value.get("artifacts")
        if isinstance(raw_artifacts, list):
            checkpoint["artifacts"] = [
                {
                    key: _public_scalar(item[key])
                    for key in ("path", "label", "detail")
                    if key in item and _public_scalar(item[key]) is not None
                }
                for item in raw_artifacts[-ARTIFACT_LIMIT:]
                if isinstance(item, dict)
            ]
        return checkpoint

    @staticmethod
    def _public_timeline(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return _new_timeline()
        timeline: dict[str, Any] = {}
        for key in ("revision", "percent"):
            candidate = _public_scalar(value.get(key))
            if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                timeline[key] = candidate
        current = value.get("current_milestone_id")
        timeline["current_milestone_id"] = _public_scalar(current, limit=128) if isinstance(current, str) else None
        milestones: list[dict[str, Any]] = []
        raw_milestones = value.get("milestones")
        if isinstance(raw_milestones, list):
            for milestone in raw_milestones[:MILESTONE_LIMIT]:
                if not isinstance(milestone, dict):
                    continue
                projected = {
                    key: _public_scalar(milestone[key])
                    for key in (
                        "id",
                        "key",
                        "label",
                        "position",
                        "state",
                        "summary",
                        "started_at",
                        "ended_at",
                    )
                    if key in milestone
                    and _public_scalar(milestone[key]) is not None
                }
                attempts = milestone.get("attempts")
                if isinstance(attempts, list):
                    projected["attempts"] = [
                        {
                            key: _public_scalar(attempt[key])
                            for key in ("number", "state", "started_at", "ended_at", "summary")
                            if key in attempt
                            and _public_scalar(attempt[key]) is not None
                        }
                        for attempt in attempts[-ATTEMPT_LIMIT:]
                        if isinstance(attempt, dict)
                    ]
                milestones.append(projected)
        timeline["milestones"] = milestones
        return timeline

    @staticmethod
    def _public_activity(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [
            {
                key: _public_scalar(item[key])
                for key in ("sequence", "occurred_at", "level", "milestone_id", "text")
                if key in item and _public_scalar(item[key]) is not None
            }
            for item in value[-ACTIVITY_LIMIT:]
            if isinstance(item, dict)
        ]

    @staticmethod
    def _public_paper_status(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        return {
            key: _public_scalar(value[key])
            for key in ("state", "run_dir", "error")
            if key in value and _public_scalar(value[key]) is not None
        }

    def _public_event(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        sequence = _public_scalar(value.get("sequence"))
        occurred_at = value.get("occurred_at")
        event_type = value.get("type")
        if not isinstance(sequence, int) or isinstance(sequence, bool):
            return None
        safe_occurred_at = _public_scalar(occurred_at)
        safe_event_type = _public_scalar(event_type)
        if not isinstance(safe_occurred_at, str) or not isinstance(safe_event_type, str):
            return None
        raw_data = value.get("data")
        data: dict[str, Any] = {}
        if isinstance(raw_data, dict):
            for key in ("state", "stage", "round"):
                candidate = raw_data.get(key)
                projected = _public_scalar(candidate)
                if projected is not None:
                    data[key] = projected
            if isinstance(raw_data.get("timeline"), dict):
                data["timeline"] = self._public_timeline(raw_data["timeline"])
            if isinstance(raw_data.get("milestone"), dict):
                projected = self._public_timeline(
                    {"milestones": [raw_data["milestone"]]}
                )["milestones"]
                if projected:
                    data["milestone"] = projected[0]
            if isinstance(raw_data.get("checkpoint"), dict):
                checkpoint = self._public_checkpoint(raw_data["checkpoint"])
                if checkpoint is not None:
                    data["checkpoint"] = checkpoint
        return {
            "sequence": sequence,
            "occurred_at": safe_occurred_at,
            "type": safe_event_type,
            "data": data,
        }

    def _public_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Return a bounded public projection, never a copy of the raw record.

        Older records contain a complete ``input_snapshot`` for worker compatibility.
        The explicit whitelist below is important: copying the old record first would
        still allocate and serialize every historical Base64 source even if the field
        were deleted afterwards.
        """
        public: dict[str, Any] = {}
        for key in _PUBLIC_RECORD_FIELDS:
            if key not in record:
                continue
            value = record[key]
            if value is None:
                public[key] = None
            else:
                projected = _public_scalar(value)
                if projected is not None:
                    public[key] = projected
        if isinstance(record.get("attempts"), list):
            public["attempts"] = [
                {
                    key: _public_scalar(attempt[key])
                    for key in (
                        "attempt_id",
                        "started_at",
                        "finished_at",
                        "state",
                        "resume_from_round",
                    )
                    if key in attempt
                    and _public_scalar(attempt[key]) is not None
                }
                for attempt in record["attempts"][-ATTEMPT_LIMIT:]
                if isinstance(attempt, dict)
            ]
        public["checkpoint"] = self._public_checkpoint(record.get("checkpoint"))
        public["timeline"] = self._public_timeline(record.get("timeline"))
        public["activity"] = self._public_activity(record.get("activity"))
        paper_status = self._public_paper_status(record.get("paper_orchestra"))
        if paper_status is not None:
            public["paper_orchestra"] = paper_status
        # Re-project even an already stored summary.  Older/corrupt records may
        # contain untrusted keys such as ``content_base64`` inside the summary;
        # treating it as public data would bypass the whitelist above.
        input_summary = _public_input_summary(
            record.get("input_snapshot")
            if isinstance(record.get("input_snapshot"), dict)
            else record.get("input_summary"),
            fallback_preparation_id=record.get("preparation_id"),
            fallback_revision_id=record.get("revision_id"),
        )
        if input_summary is not None:
            public["input_summary"] = copy.deepcopy(input_summary)
            title = input_summary.get("title")
            if isinstance(title, str) and title:
                public["title"] = title

        configuration = record.get("launch_configuration_snapshot")
        if isinstance(configuration, dict):
            model_id = configuration.get("model_id")
            preferences = configuration.get("discovery_launch_preferences")
            backend = (
                preferences.get("backend", "codex")
                if isinstance(preferences, dict)
                else "codex"
            )
            public["configuration_snapshot"] = {
                "model_id": _public_scalar(model_id, limit=256)
                if isinstance(model_id, str)
                else None,
                "backend": backend
                if backend in {"codex", "qwen_code", "openhands"}
                else "codex",
            }
            external_data = _public_external_data_snapshot(configuration.get("external_data"))
            if external_data is not None:
                public["configuration_snapshot"]["external_data"] = external_data
        return public

    def _persist_record(self, record: dict[str, Any]) -> None:
        launch_dir = self._launches_root / record["launch_id"]
        _atomic_write_json(launch_dir / "record.json", record)

    def _persist_index(self) -> None:
        compact_idempotency: dict[str, dict[str, Any]] = {}
        for key, value in self._idempotency.items():
            if not isinstance(value, dict):
                continue
            result = value.get("result")
            if not isinstance(result, dict):
                continue
            compact_idempotency[key] = {
                "request_fingerprint": value.get("request_fingerprint"),
                # The full response snapshot is intentionally not durable here:
                # it repeats Preparation/history for every idempotency key.
                "result": _compact_idempotency_result(result),
            }
        _atomic_write_json(
            self._index_path,
            {
                "schema_version": 2,
                "active_launch_id": self._active_launch_id,
                "history_ids": self._history_ids,
                "launch_ids": list(self._records),
                "idempotency": compact_idempotency,
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
        migrated_record_ids: list[str] = []
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
                # Pre-fix records duplicated the complete source-bearing input
                # snapshot in record.json. Keep a bounded manifest in memory while
                # leaving input_snapshot.json intact for an in-flight legacy worker.
                legacy_input = record.get("input_snapshot")
                if isinstance(legacy_input, dict):
                    record.setdefault(
                        "input_summary",
                        _public_input_summary(
                            legacy_input,
                            fallback_preparation_id=record.get("preparation_id"),
                            fallback_revision_id=record.get("revision_id"),
                        ),
                    )
                    record.pop("input_snapshot", None)
                    migrated_record_ids.append(launch_id)
                self._ensure_observation_state(record)
                records[launch_id] = record
        self._records = records
        self._history_ids = [
            launch_id
            for launch_id in index.get("history_ids", [])
            if launch_id in self._records
        ][:HISTORY_LIMIT]
        active_id = index.get("active_launch_id")
        self._active_launch_id = active_id if active_id in self._records else None
        raw_idempotency = index.get("idempotency", {})
        idempotency_changed = False
        normalized_idempotency: dict[str, dict[str, Any]] = {}
        if isinstance(raw_idempotency, dict):
            for key, value in raw_idempotency.items():
                if (
                    not isinstance(key, str)
                    or not isinstance(value, dict)
                    or not isinstance(value.get("request_fingerprint"), str)
                    or not isinstance(value.get("result"), dict)
                ):
                    continue
                result = value["result"]
                normalized_result = _compact_idempotency_result(result)
                if normalized_result != result:
                    idempotency_changed = True
                normalized_idempotency[key] = {
                    "request_fingerprint": value["request_fingerprint"],
                    "result": normalized_result,
                }
        self._idempotency = normalized_idempotency
        for launch_id in migrated_record_ids:
            record = self._records.get(launch_id)
            if record is not None:
                try:
                    self._persist_record(record)
                except OSError:
                    # Public reads must remain available on a read-only legacy
                    # state directory; migration is best-effort and can retry on
                    # the next lifecycle write.
                    pass
        if migrated_record_ids or idempotency_changed:
            try:
                self._persist_index()
            except OSError:
                pass

    def _lock_owned(self) -> bool:
        owned = getattr(self._lock, "_is_owned", None)
        return bool(owned and owned())
