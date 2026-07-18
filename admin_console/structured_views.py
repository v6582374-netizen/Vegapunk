"""Structured navigational overlays on top of Artifact Explorer.

Launch Timeline and Experiment Run Detail expose bookmarks into on-disk
artifacts. They never replace the file tree: every file remains reachable
through the Artifact Explorer endpoints.
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from admin_console.artifacts import ArtifactPathError, resolve_artifact
from admin_console.live import infer_stage

_SESSION_DIR_PATTERN = re.compile(r"^session_")
_RUN_DIR_PATTERN = re.compile(r"^run_(\d+)$")
_LOG_PREVIEW_CHARS = 12_000


class ExperimentRunPathError(Exception):
    """The requested path is not an Experiment Run directory under the Launch."""


def build_timeline(launch_dir: Path) -> dict:
    launch_dir = launch_dir.resolve()
    rounds = [_parse_round(child) for child in _session_dirs(launch_dir)]
    if not rounds and (launch_dir / "ideas.json").is_file():
        rounds.append(_root_ideas_round(launch_dir))

    paper_path = None
    if (launch_dir / "manuscript").is_dir():
        paper_path = "manuscript"
    elif (launch_dir / "paper_orchestra_runs").is_dir():
        paper_path = "paper_orchestra_runs"

    return {
        "stage": infer_stage(launch_dir),
        "rounds": rounds,
        "paper": {"path": paper_path, "present": paper_path is not None},
    }


def build_experiment_run_detail(launch_dir: Path, relative_path: str) -> dict:
    launch_dir = launch_dir.resolve()
    try:
        run_dir = resolve_artifact(launch_dir, relative_path)
    except ArtifactPathError as error:
        raise ExperimentRunPathError(str(error)) from error
    if not run_dir.is_dir() or _RUN_DIR_PATTERN.match(run_dir.name) is None:
        raise ExperimentRunPathError(f"not an experiment run directory: {relative_path}")

    metrics_file = run_dir / "final_info.json"
    traceback_file = run_dir / "traceback.log"
    log_file = run_dir / "log.txt"
    metrics = _read_json(metrics_file)
    outcome = _run_outcome(metrics_file=metrics_file, traceback_file=traceback_file)

    log_preview_parts: list[str] = []
    log_path = None
    traceback_path = None
    if log_file.is_file():
        log_path = f"{relative_path}/log.txt"
        log_preview_parts.append(_preview_text(log_file))
    if traceback_file.is_file():
        traceback_path = f"{relative_path}/traceback.log"
        log_preview_parts.append(_preview_text(traceback_file))

    code_dir = run_dir / "code"
    code_files = []
    if code_dir.is_dir():
        for path in sorted(code_dir.rglob("*")):
            if path.is_file():
                rel = path.relative_to(launch_dir).as_posix()
                code_files.append({"path": rel, "name": path.name})

    return {
        "path": relative_path,
        "id": run_dir.name,
        "outcome": outcome,
        "metrics": metrics,
        "metrics_path": f"{relative_path}/final_info.json" if metrics_file.is_file() else None,
        "log_path": log_path,
        "traceback_path": traceback_path,
        "log_preview": "\n".join(part for part in log_preview_parts if part),
        "code_files": code_files,
        "code_diff": _code_diff_against_baseline(run_dir),
    }


def _session_dirs(launch_dir: Path) -> list[Path]:
    if not launch_dir.is_dir():
        return []
    return sorted(
        child
        for child in launch_dir.iterdir()
        if child.is_dir() and _SESSION_DIR_PATTERN.match(child.name)
    )


def _parse_round(session_dir: Path) -> dict:
    launch_dir = session_dir.parent
    relative = session_dir.relative_to(launch_dir).as_posix()
    ideas_file = session_dir / "ideas.json"
    ideas = _parse_ideas(ideas_file)
    candidates = [
        _parse_candidate(path, launch_dir) for path in _candidate_dirs(session_dir)
    ]
    return {
        "id": session_dir.name,
        "path": relative,
        "ideas_path": f"{relative}/ideas.json" if ideas_file.is_file() else None,
        "ideas": ideas,
        "candidates": candidates,
    }


def _root_ideas_round(launch_dir: Path) -> dict:
    ideas_file = launch_dir / "ideas.json"
    return {
        "id": "root",
        "path": "",
        "ideas_path": "ideas.json",
        "ideas": _parse_ideas(ideas_file),
        "candidates": [],
    }


def _parse_ideas(ideas_file: Path) -> list[dict]:
    if not ideas_file.is_file():
        return []
    payload = _read_json(ideas_file)
    if isinstance(payload, dict) and isinstance(payload.get("ideas"), list):
        items = payload["ideas"]
    elif isinstance(payload, list):
        items = payload
    else:
        return []
    ideas = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("idea") or item.get("title")
        ideas.append(
            {
                "name": name,
                "title": item.get("title"),
                "description": item.get("description"),
            }
        )
    return ideas


def _candidate_dirs(session_dir: Path) -> list[Path]:
    candidates = []
    for child in sorted(session_dir.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        if any(run.is_dir() and _RUN_DIR_PATTERN.match(run.name) for run in child.iterdir()):
            candidates.append(child)
    return candidates


def _parse_candidate(candidate_dir: Path, launch_dir: Path) -> dict:
    relative = candidate_dir.relative_to(launch_dir).as_posix()
    method_path = None
    for name in ("notes.txt", "experiment_report.txt"):
        if (candidate_dir / name).is_file():
            method_path = f"{relative}/{name}"
            break

    idea_name = _candidate_display_name(candidate_dir.name)

    runs = []
    for run_dir in sorted(
        (
            child
            for child in candidate_dir.iterdir()
            if child.is_dir() and _RUN_DIR_PATTERN.match(child.name)
        ),
        key=lambda path: int(_RUN_DIR_PATTERN.match(path.name).group(1)),  # type: ignore[union-attr]
    ):
        runs.append(_parse_run_summary(run_dir, launch_dir))

    return {
        "name": idea_name,
        "path": relative,
        "method_path": method_path,
        "runs": runs,
    }


def _candidate_display_name(directory_name: str) -> str:
    # Discovery writes "{YYYYMMDD_HHMMSS}_{IdeaName}".
    match = re.match(r"^(\d{8}_\d{6})_(.+)$", directory_name)
    if match:
        return match.group(2)
    return directory_name


def _parse_run_summary(run_dir: Path, launch_dir: Path) -> dict:
    relative = run_dir.relative_to(launch_dir).as_posix()
    metrics_file = run_dir / "final_info.json"
    traceback_file = run_dir / "traceback.log"
    metrics = _read_json(metrics_file)
    combined = None
    if isinstance(metrics, dict):
        score = metrics.get("combined_score")
        if isinstance(score, (int, float)):
            combined = float(score)
    return {
        "id": run_dir.name,
        "path": relative,
        "outcome": _run_outcome(metrics_file=metrics_file, traceback_file=traceback_file),
        "metrics_path": f"{relative}/final_info.json" if metrics_file.is_file() else None,
        "combined_score": combined,
    }


def _run_outcome(*, metrics_file: Path, traceback_file: Path) -> str:
    if metrics_file.is_file():
        return "completed"
    if traceback_file.is_file():
        return "failed"
    return "unknown"


def _code_diff_against_baseline(run_dir: Path) -> str:
    code_dir = run_dir / "code"
    if not code_dir.is_dir():
        return ""
    baseline = run_dir.parent / "run_0" / "code"
    if run_dir.name == "run_0" or not baseline.is_dir():
        baseline = run_dir.parent / "code"
    if not baseline.is_dir():
        return ""

    chunks: list[str] = []
    names = sorted(
        {
            *(path.relative_to(code_dir).as_posix() for path in code_dir.rglob("*") if path.is_file()),
            *(path.relative_to(baseline).as_posix() for path in baseline.rglob("*") if path.is_file()),
        }
    )
    for name in names:
        left = baseline / name
        right = code_dir / name
        left_lines = _read_lines(left)
        right_lines = _read_lines(right)
        if left_lines == right_lines:
            continue
        diff = difflib.unified_diff(
            left_lines,
            right_lines,
            fromfile=f"run_0/code/{name}" if (run_dir.parent / "run_0" / "code").is_dir() else f"code/{name}",
            tofile=f"{run_dir.name}/code/{name}",
            lineterm="",
        )
        chunks.append("\n".join(diff))
    return "\n".join(chunks)


def _read_json(path: Path) -> dict | list | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _preview_text(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(text) <= _LOG_PREVIEW_CHARS:
        return text
    return text[-_LOG_PREVIEW_CHARS:]
