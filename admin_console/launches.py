"""Scanning of historical Discovery Launches from the results directory.

A Launch lives at ``<results_root>/<task>/<YYYYMMDD_HHMMSS>_launch/``.
The skeleton derives the terminal state from persisted artifacts only
(Workflow Progress is artifact-described per ADR-0089); the Launch Queue
adds authoritative runtime states on top of this in a later slice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_LAUNCH_DIR_PATTERN = re.compile(r"^(\d{8}_\d{6})_launch$")


@dataclass(frozen=True)
class LaunchSummary:
    id: str
    task: str
    started_at: str
    state: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task": self.task,
            "started_at": self.started_at,
            "state": self.state,
        }


def _derive_state(launch_dir: Path) -> str:
    if (launch_dir / "discovery_summary.json").is_file() or (launch_dir / "manuscript").is_dir():
        return "completed"
    return "unknown"


def _parse_started_at(stamp: str) -> str:
    return datetime.strptime(stamp, "%Y%m%d_%H%M%S").isoformat()


def scan_launches(results_root: Path) -> list[LaunchSummary]:
    """Return every Launch under the results root, newest first."""
    launches: list[LaunchSummary] = []
    if not results_root.is_dir():
        return launches
    for task_dir in results_root.iterdir():
        if not task_dir.is_dir():
            continue
        for candidate in task_dir.iterdir():
            if not candidate.is_dir():
                continue
            match = _LAUNCH_DIR_PATTERN.match(candidate.name)
            if match is None:
                continue
            launches.append(
                LaunchSummary(
                    id=f"{task_dir.name}/{candidate.name}",
                    task=task_dir.name,
                    started_at=_parse_started_at(match.group(1)),
                    state=_derive_state(candidate),
                )
            )
    launches.sort(key=lambda launch: launch.started_at, reverse=True)
    return launches
