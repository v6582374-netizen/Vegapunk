from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CurrentValidRun:
    path: Path
    final_info: dict[str, Any]


def find_current_valid_run(candidate_dir: Path) -> CurrentValidRun | None:
    """Return the highest numbered run with readable, non-empty final_info.json."""
    numbered_runs: list[tuple[int, Path]] = []
    for child in candidate_dir.iterdir():
        match = re.fullmatch(r"run_(\d+)", child.name)
        if child.is_dir() and match:
            numbered_runs.append((int(match.group(1)), child))
    for _, run_dir in sorted(numbered_runs, reverse=True):
        try:
            with (run_dir / "final_info.json").open("r", encoding="utf-8") as file:
                final_info = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
        if isinstance(final_info, dict) and final_info:
            return CurrentValidRun(path=run_dir, final_info=final_info)
    return None
