"""Append-only capture of observable Discovery activity."""

from __future__ import annotations

import logging
import sys
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from functools import wraps
from pathlib import Path
from threading import Lock
from typing import Any, Iterator, TextIO

import yaml


DRAFT_BLOCK_DELIMITER = "<!-- draft-block -->"
_APPEND_LOCK = Lock()
_ACTIVE_DRAFT_LOCK = Lock()
_active_draft: "ResearchDraft | None" = None
_capture_streams: tuple["_DraftStream", "_DraftStream"] | None = None
_capture_original_streams: tuple[TextIO, TextIO] | None = None
_capture_log_handler: "_DraftLogHandler | None" = None


@dataclass(frozen=True)
class ResearchDraft:
    """The launch-local raw Markdown record consumed by PaperOrchestra."""

    launch_dir: Path
    path: Path

    @classmethod
    def open(cls, launch_dir: Path) -> "ResearchDraft":
        launch_root = launch_dir.resolve()
        manuscript_dir = launch_root / "manuscript"
        manuscript_dir.mkdir(parents=True, exist_ok=True)
        path = manuscript_dir / "draft.md"
        path.touch(exist_ok=True)
        return cls(launch_dir=launch_root, path=path)

    def append(self, content: Any) -> None:
        """Append one raw block without interpreting or rewriting its content."""

        rendered = _render_observable(content)
        with _APPEND_LOCK:
            has_history = self.path.stat().st_size > 0
            with self.path.open("a", encoding="utf-8") as draft_file:
                if has_history:
                    draft_file.write(DRAFT_BLOCK_DELIMITER + "\n")
                draft_file.write(rendered)
                if not rendered.endswith("\n"):
                    draft_file.write("\n")

    @contextmanager
    def activate(self) -> Iterator["ResearchDraft"]:
        """Route observable runtime events to this Draft for one scope."""

        start_research_draft_capture(self)
        try:
            yield self
        finally:
            stop_research_draft_capture(self)


def record_research_event(content: Any) -> None:
    """Append to the active Draft, or do nothing outside Discovery capture."""

    with _ACTIVE_DRAFT_LOCK:
        draft = _active_draft
    if draft is not None:
        draft.append(content)


def start_research_draft_capture(draft: ResearchDraft) -> None:
    """Activate one launch Draft until explicit handoff or process cleanup."""

    global _active_draft, _capture_streams, _capture_original_streams
    global _capture_log_handler
    with _ACTIVE_DRAFT_LOCK:
        if _active_draft is not None:
            if _active_draft is draft:
                return
            raise RuntimeError("A different Research Draft is already active")
        _active_draft = draft
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        streams = (
            _DraftStream(original_stdout, draft),
            _DraftStream(original_stderr, draft),
        )
        handler = _DraftLogHandler(draft)
        logging.getLogger().addHandler(handler)
        sys.stdout, sys.stderr = streams
        _capture_original_streams = (original_stdout, original_stderr)
        _capture_streams = streams
        _capture_log_handler = handler


def stop_research_draft_capture(draft: ResearchDraft | None = None) -> None:
    """Stop capture without rewriting or finalizing the Research Draft."""

    global _active_draft, _capture_streams, _capture_original_streams
    global _capture_log_handler
    with _ACTIVE_DRAFT_LOCK:
        if draft is not None and _active_draft is not draft:
            return
        streams = _capture_streams
        originals = _capture_original_streams
        handler = _capture_log_handler
        if handler is not None:
            logging.getLogger().removeHandler(handler)
        if streams is not None:
            streams[0].finish()
            streams[1].finish()
        if originals is not None:
            sys.stdout, sys.stderr = originals
        _active_draft = None
        _capture_streams = None
        _capture_original_streams = None
        _capture_log_handler = None


def attach_research_draft_hook(agent: Any) -> Any:
    """Append one asynchronous Agent task's input and terminal outcome."""

    if getattr(agent, "_research_draft_hook_attached", False):
        return agent
    execute = agent.execute

    @wraps(execute)
    async def execute_with_capture(*args: Any, **kwargs: Any) -> Any:
        record_research_event({"args": args, "kwargs": kwargs})
        try:
            output = await execute(*args, **kwargs)
        except Exception:
            record_research_event(traceback.format_exc())
            raise
        record_research_event(output)
        return output

    agent.execute = execute_with_capture
    agent._research_draft_hook_attached = True
    return agent


def attach_sync_research_draft_hook(agent: Any) -> Any:
    """Append one synchronous Agent task's input and terminal outcome."""

    if getattr(agent, "_research_draft_hook_attached", False):
        return agent
    execute = agent.execute

    @wraps(execute)
    def execute_with_capture(*args: Any, **kwargs: Any) -> Any:
        record_research_event({"args": args, "kwargs": kwargs})
        try:
            output = execute(*args, **kwargs)
        except Exception:
            record_research_event(traceback.format_exc())
            raise
        record_research_event(output)
        return output

    agent.execute = execute_with_capture
    agent._research_draft_hook_attached = True
    return agent


class _DraftLogHandler(logging.Handler):
    def __init__(self, draft: ResearchDraft) -> None:
        super().__init__()
        self._draft = draft

    def emit(self, record: logging.LogRecord) -> None:
        self._draft.append(record.getMessage())


class _DraftStream:
    def __init__(self, target: TextIO, draft: ResearchDraft) -> None:
        self._target = target
        self._draft = draft
        self._buffer = ""
        self._lock = Lock()

    def write(self, text: str) -> int:
        written = self._target.write(text)
        with self._lock:
            self._buffer += text
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                if line:
                    self._draft.append(line)
        return written

    def flush(self) -> None:
        self._target.flush()
        with self._lock:
            self._flush_buffer()

    def finish(self) -> None:
        with self._lock:
            self._flush_buffer()
        self._target.flush()

    def _flush_buffer(self) -> None:
        if self._buffer:
            self._draft.append(self._buffer)
            self._buffer = ""

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)


def _render_observable(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, BaseException):
        return "".join(traceback.format_exception(value))
    plain = _to_plain_data(value)
    if isinstance(plain, str):
        return plain
    return yaml.safe_dump(
        plain,
        allow_unicode=True,
        sort_keys=False,
        width=4096,
    )


def _to_plain_data(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return _to_plain_data(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _to_plain_data(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {
            str(key): _to_plain_data(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_to_plain_data(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _to_plain_data(to_dict())
        except Exception:
            pass
    return str(value)
