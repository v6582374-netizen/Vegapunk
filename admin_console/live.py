"""Live Launch View backend: status polling data and SSE log streaming.

Artifact increments are polled by the frontend through the status endpoint
(recent artifacts by modification time); only logs stream over SSE, per the
project decision to avoid WebSockets and filesystem watchers.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import AsyncIterator, Callable

_SESSION_DIR_PATTERN = re.compile(r"^session_")


def count_rounds(launch_dir: Path) -> int:
    return sum(
        1
        for child in launch_dir.iterdir()
        if child.is_dir() and _SESSION_DIR_PATTERN.match(child.name)
    )


def recent_artifacts(launch_dir: Path, limit: int = 50) -> list[dict]:
    files = [path for path in launch_dir.rglob("*") if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [
        {
            "path": str(path.relative_to(launch_dir)),
            "modified_at": path.stat().st_mtime,
            "size": path.stat().st_size,
        }
        for path in files[:limit]
    ]


async def stream_log(
    log_path: Path,
    is_running: Callable[[], bool],
    poll_interval: float = 0.2,
) -> AsyncIterator[str]:
    """Yield SSE events for each appended log line.

    Follows the file while the Launch is running; once it stops (or for a
    historical Launch), drains what exists and ends the stream.
    """
    position = 0
    while True:
        running = is_running()
        if log_path.is_file():
            with log_path.open("r", encoding="utf-8", errors="replace") as stream:
                stream.seek(position)
                chunk = stream.read()
                position = stream.tell()
            for line in chunk.splitlines():
                yield f"data: {line}\n\n"
        if not running:
            return
        await asyncio.sleep(poll_interval)
