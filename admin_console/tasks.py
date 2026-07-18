"""Task Authoring Form: create and list research tasks for the Admin Console.

A task is a directory under the tasks root with a prompt.json (auto) or
task_info.json (sci). Baseline code is optional; without it the task can
only take the report path, not the experiment path.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

_TASK_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class TaskNameError(Exception):
    pass


class TaskExistsError(Exception):
    pass


def has_baseline_code(task_dir: Path) -> bool:
    return (task_dir / "code").is_dir() or (task_dir / "experiment.py").is_file()


def path_mode_for(task_dir: Path) -> str:
    return "experiment" if has_baseline_code(task_dir) else "report"


def list_tasks(tasks_root: Path) -> list[dict]:
    if not tasks_root.is_dir():
        return []
    tasks: list[dict] = []
    for path in sorted(tasks_root.iterdir(), key=lambda p: p.name):
        if not path.is_dir():
            continue
        if not ((path / "prompt.json").is_file() or (path / "task_info.json").is_file()):
            continue
        tasks.append(
            {
                "name": path.name,
                "has_baseline_code": has_baseline_code(path),
                "path_mode": path_mode_for(path),
                "kind": "sci" if (path / "task_info.json").is_file() else "auto",
            }
        )
    return tasks


def create_task(
    tasks_root: Path,
    name: str,
    system: str,
    task_description: str,
    domain: str,
    background: str,
    constraints: list[str],
    baseline_zip: Path | None = None,
) -> dict:
    if not _TASK_NAME_PATTERN.match(name):
        raise TaskNameError(
            "task name must start with a letter and contain only letters, digits, _ or -"
        )
    task_dir = tasks_root / name
    if task_dir.exists():
        raise TaskExistsError(name)

    task_dir.mkdir(parents=True)
    prompt = {
        "system": system,
        "task_description": task_description,
        "domain": domain,
        "background": background,
        "constraints": constraints,
    }
    (task_dir / "prompt.json").write_text(json.dumps(prompt, indent=2, ensure_ascii=False))

    if baseline_zip is not None:
        _extract_baseline(baseline_zip, task_dir)

    return {
        "name": name,
        "has_baseline_code": has_baseline_code(task_dir),
        "path_mode": path_mode_for(task_dir),
        "kind": "auto",
    }


def _extract_baseline(zip_path: Path, task_dir: Path) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            # Reject absolute paths and path traversal inside the zip.
            target = (task_dir / member).resolve()
            try:
                target.relative_to(task_dir.resolve())
            except ValueError as error:
                raise TaskNameError(f"zip entry escapes task directory: {member}") from error
        archive.extractall(task_dir)

    # Flatten a single top-level directory if the zip wraps everything in one folder
    # that is not an expected task layout root (code/, launcher.sh at top).
    children = [child for child in task_dir.iterdir() if child.name != "prompt.json"]
    if (
        len(children) == 1
        and children[0].is_dir()
        and children[0].name not in {"code", "run_0"}
        and not (task_dir / "launcher.sh").exists()
        and not (task_dir / "experiment.py").exists()
    ):
        wrapper = children[0]
        for item in wrapper.iterdir():
            shutil.move(str(item), str(task_dir / item.name))
        wrapper.rmdir()


def write_upload_to_temp(upload_bytes: bytes, suffix: str = ".zip") -> Path:
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    handle.write(upload_bytes)
    handle.close()
    return Path(handle.name)
