"""FastAPI application factory for the Admin Console."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from admin_console.launches import scan_launches
from admin_console.queue import LaunchQueue, UnknownTaskError

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG_PATHS = [
    REPOSITORY_ROOT / "config" / "default_config.yaml",
    REPOSITORY_ROOT / "config" / "model_catalog.yaml",
    REPOSITORY_ROOT / "config" / "paper_orchestra.yaml",
]

# The real launcher tolerates an empty --resume directory (it scans and
# resumes from round zero), which lets the queue own the launch directory
# it snapshots into. The backend choice moves to the Run Parameter
# Registry in a later slice.
DEFAULT_RUNNER_COMMAND = [
    sys.executable,
    str(REPOSITORY_ROOT / "launch_discovery.py"),
    "--task",
    "{task_dir}",
    "--resume",
    "{launch_dir}",
    "--exp_backend",
    "claudecode",
]


class QueueSubmission(BaseModel):
    task: str


def create_app(
    results_root: Path | None = None,
    tasks_root: Path | None = None,
    config_paths: list[Path] | None = None,
    runner_command: list[str] | None = None,
) -> FastAPI:
    resolved_results_root = results_root or (REPOSITORY_ROOT / "results")
    tasks_root_resolved = tasks_root or (REPOSITORY_ROOT / "tasks")
    queue = LaunchQueue(
        results_root=resolved_results_root,
        tasks_root=tasks_root_resolved,
        config_paths=config_paths or DEFAULT_CONFIG_PATHS,
        runner_command=runner_command or DEFAULT_RUNNER_COMMAND,
    )

    app = FastAPI(title="InternAgent Admin Console")

    @app.get("/api/launches")
    def list_launches() -> dict:
        launches = scan_launches(resolved_results_root)
        return {"launches": [launch.to_dict() for launch in launches]}

    @app.get("/api/tasks")
    def list_tasks() -> dict:
        tasks_root = tasks_root_resolved
        names = sorted(
            path.name
            for path in tasks_root.iterdir()
            if path.is_dir() and ((path / "prompt.json").is_file() or (path / "task_info.json").is_file())
        ) if tasks_root.is_dir() else []
        return {"tasks": names}

    @app.get("/api/queue")
    def list_queue() -> dict:
        return {"entries": [entry.to_dict() for entry in queue.entries()]}

    @app.post("/api/queue", status_code=201)
    def submit_launch(submission: QueueSubmission) -> dict:
        try:
            entry = queue.submit(submission.task)
        except UnknownTaskError:
            raise HTTPException(status_code=404, detail=f"unknown task: {submission.task}")
        return entry.to_dict()

    @app.delete("/api/queue/{queue_id}")
    def cancel_queued(queue_id: str) -> dict:
        try:
            entry = queue.cancel(queue_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown queue entry: {queue_id}")
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error))
        return entry.to_dict()

    return app
