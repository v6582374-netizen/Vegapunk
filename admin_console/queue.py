"""Launch Queue: service-wide serial execution of Discovery Launches.

Exactly one Launch runs at a time (ADR: Launch Queue term in CONTEXT.md);
submitting enqueues rather than starts. Each Launch runs as a child process
built from an injectable command template, and captures its Launch
Configuration Snapshot into its own launch directory before starting
(ADR-0157). Queue state persists to a JSON file so a service restart does
not lose it.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

SNAPSHOT_DIR_NAME = "config_snapshot"

QUEUED = "queued"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"
INTERRUPTED = "interrupted"
ABORTED = "aborted"


@dataclass
class QueueEntry:
    queue_id: str
    task: str
    state: str
    submitted_at: str
    launch_id: str | None = None
    pid: int | None = None
    stopped_how: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def copy(self) -> "QueueEntry":
        return QueueEntry(**self.to_dict())


class UnknownTaskError(Exception):
    pass


class LaunchQueue:
    def __init__(
        self,
        results_root: Path,
        tasks_root: Path,
        config_paths: list[Path],
        runner_command: list[str],
    ) -> None:
        self._results_root = results_root
        self._tasks_root = tasks_root
        self._config_paths = config_paths
        self._runner_command = runner_command
        self._state_path = results_root / "launch_queue.json"
        self._lock = threading.Condition()
        self._entries: list[QueueEntry] = []
        self._load()
        self._worker = threading.Thread(target=self._work_loop, daemon=True)
        self._worker.start()

    # ------------------------------------------------------------- public

    def submit(self, task: str, launch_id: str | None = None) -> QueueEntry:
        """Enqueue a Launch; with launch_id set, this is a Launch Resume.

        A resumed Launch reuses its directory and its original Launch
        Configuration Snapshot; it never absorbs edits made after its
        original start (ADR-0157).
        """
        if not (self._tasks_root / task).is_dir():
            raise UnknownTaskError(task)
        entry = QueueEntry(
            queue_id=uuid.uuid4().hex[:12],
            task=task,
            state=QUEUED,
            submitted_at=datetime.now().isoformat(timespec="seconds"),
            launch_id=launch_id,
        )
        with self._lock:
            self._entries.append(entry)
            self._save()
            self._lock.notify_all()
        return entry

    def stop(self, queue_id: str, force: bool = False) -> QueueEntry:
        """Stop the running Launch: graceful SIGTERM, or SIGKILL when forced.

        Graceful stop lets the runner finish its current smallest unit of
        work and persist a checkpoint; force kill may leave the workspace
        inconsistent and takes the whole process group with it.
        """
        with self._lock:
            entry = self._find(queue_id)
            if entry is None:
                raise KeyError(queue_id)
            if entry.state != RUNNING or entry.pid is None:
                raise ValueError(f"only running entries can be stopped, state is {entry.state}")
            entry.stopped_how = "force" if force else "graceful"
            self._save()
            pid = entry.pid
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            pass
        with self._lock:
            return entry.copy()

    def entries(self) -> list[QueueEntry]:
        with self._lock:
            return [entry.copy() for entry in self._entries]

    def state_for_launch(self, launch_id: str) -> str | None:
        """Authoritative state for a console-started Launch, else None."""
        with self._lock:
            for entry in self._entries:
                if entry.launch_id == launch_id:
                    return entry.state
        return None

    def cancel(self, queue_id: str) -> QueueEntry:
        with self._lock:
            entry = self._find(queue_id)
            if entry is None:
                raise KeyError(queue_id)
            if entry.state != QUEUED:
                raise ValueError(f"only queued entries can be cancelled, state is {entry.state}")
            entry.state = CANCELLED
            self._save()
            return entry.copy()

    # ------------------------------------------------------------ worker

    def _work_loop(self) -> None:
        while True:
            adopted = None
            with self._lock:
                while True:
                    adopted = self._running_entry()
                    if adopted is not None:
                        break
                    entry = self._next_queued()
                    if entry is not None:
                        break
                    self._lock.wait()
                if adopted is None:
                    entry.state = RUNNING
                    if entry.launch_id is None:
                        launch_dir = self._create_launch_dir(entry.task)
                        entry.launch_id = str(launch_dir.relative_to(self._results_root))
                    else:
                        launch_dir = self._results_root / entry.launch_id
                    self._save()
            if adopted is not None:
                self._watch_adopted_run(adopted)
            else:
                self._execute(entry, launch_dir)

    def _watch_adopted_run(self, entry: QueueEntry) -> None:
        """Track a run started by a previous service process.

        The new process is not its parent, so it can only observe liveness,
        not the exit code; when the process ends the entry becomes
        interrupted. While it lives, it holds the single running slot so the
        serial invariant survives restarts.
        """
        while _process_alive(entry.pid):
            time.sleep(0.1)
        with self._lock:
            entry.state = INTERRUPTED
            entry.pid = None
            self._save()

    def _running_entry(self) -> QueueEntry | None:
        return self._first_in_state(RUNNING)

    def _next_queued(self) -> QueueEntry | None:
        return self._first_in_state(QUEUED)

    def _first_in_state(self, state: str) -> QueueEntry | None:
        for entry in self._entries:
            if entry.state == state:
                return entry
        return None

    def _create_launch_dir(self, task: str) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        launch_dir = self._results_root / task / f"{stamp}_launch"
        suffix = 1
        while launch_dir.exists():
            launch_dir = self._results_root / task / f"{stamp}_launch_{suffix}"
            suffix += 1
        launch_dir.mkdir(parents=True)
        return launch_dir

    def _snapshot_configuration(self, launch_dir: Path) -> Path:
        snapshot_dir = launch_dir / SNAPSHOT_DIR_NAME
        if snapshot_dir.is_dir():
            # Launch Resume: the original snapshot is authoritative and
            # must not absorb later global edits.
            return snapshot_dir
        snapshot_dir.mkdir()
        for config_path in self._config_paths:
            shutil.copy2(config_path, snapshot_dir / config_path.name)
        return snapshot_dir

    def _execute(self, entry: QueueEntry, launch_dir: Path) -> None:
        snapshot_dir = self._snapshot_configuration(launch_dir)
        command = [
            part.format(
                task_dir=self._tasks_root / entry.task,
                launch_dir=launch_dir,
                snapshot_dir=snapshot_dir,
            )
            for part in self._runner_command
        ]
        with (launch_dir / "runner.log").open("ab") as log_stream:
            process = subprocess.Popen(
                command,
                stdout=log_stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        with self._lock:
            entry.pid = process.pid
            self._save()
        exit_code = process.wait()
        with self._lock:
            if entry.stopped_how is not None:
                entry.state = ABORTED
            else:
                entry.state = COMPLETED if exit_code == 0 else FAILED
            entry.pid = None
            self._save()

    # ------------------------------------------------------- persistence

    def _save(self) -> None:
        payload = {"entries": [entry.to_dict() for entry in self._entries]}
        self._state_path.write_text(json.dumps(payload, indent=2))

    def _load(self) -> None:
        if not self._state_path.is_file():
            return
        payload = json.loads(self._state_path.read_text())
        self._entries = [QueueEntry(**item) for item in payload.get("entries", [])]
        # A restart cannot reattach to a run started by a previous service
        # process; running entries whose process is gone become interrupted.
        for entry in self._entries:
            if entry.state == RUNNING and not _process_alive(entry.pid):
                entry.state = INTERRUPTED
                entry.pid = None
        self._save()

    def _find(self, queue_id: str) -> QueueEntry | None:
        for entry in self._entries:
            if entry.queue_id == queue_id:
                return entry
        return None


def _process_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
