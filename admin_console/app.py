"""FastAPI application factory for the Admin Console."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from admin_console.artifacts import (
    ArtifactPathError,
    artifact_tree,
    guess_media_type,
    resolve_artifact,
    resolve_launch_dir,
)
from admin_console.launches import scan_launches
from admin_console.parameters import (
    load_values,
    parameter_catalog,
    save_values,
    validate_values,
)
from admin_console.queue import LaunchQueue, UnknownTaskError
from pydantic import ValidationError

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG_PATHS = [
    REPOSITORY_ROOT / "config" / "default_config.yaml",
    REPOSITORY_ROOT / "config" / "model_catalog.yaml",
    REPOSITORY_ROOT / "config" / "paper_orchestra.yaml",
]

# The real launcher tolerates an empty --resume directory (it scans and
# resumes from round zero), which lets the queue own the launch directory
# it snapshots into. --config points at the Launch Configuration Snapshot
# so the run reads only its snapshot (ADR-0157). The backend choice moves
# to the Run Parameter Registry in a later slice.
DEFAULT_RUNNER_COMMAND = [
    sys.executable,
    str(REPOSITORY_ROOT / "launch_discovery.py"),
    "--task",
    "{task_dir}",
    "--resume",
    "{launch_dir}",
    "--config",
    "{snapshot_dir}/default_config.yaml",
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
    main_config_path: Path | None = None,
) -> FastAPI:
    resolved_results_root = results_root or (REPOSITORY_ROOT / "results")
    resolved_tasks_root = tasks_root or (REPOSITORY_ROOT / "tasks")
    resolved_main_config = main_config_path or DEFAULT_CONFIG_PATHS[0]
    queue = LaunchQueue(
        results_root=resolved_results_root,
        tasks_root=resolved_tasks_root,
        config_paths=config_paths or DEFAULT_CONFIG_PATHS,
        runner_command=runner_command or DEFAULT_RUNNER_COMMAND,
    )

    app = FastAPI(title="InternAgent Admin Console")

    @app.get("/api/launches")
    def list_launches() -> dict:
        # The queue knows the authoritative state of console-started
        # Launches; artifact heuristics only cover pre-console history.
        queue_states = {
            entry.launch_id: entry.state
            for entry in queue.entries()
            if entry.launch_id is not None
        }
        launches = scan_launches(resolved_results_root)
        return {
            "launches": [
                {**launch.to_dict(), "state": queue_states.get(launch.id, launch.state)}
                for launch in launches
            ]
        }

    @app.get("/api/tasks")
    def list_tasks() -> dict:
        if not resolved_tasks_root.is_dir():
            return {"tasks": []}
        names = sorted(
            path.name
            for path in resolved_tasks_root.iterdir()
            if path.is_dir()
            and ((path / "prompt.json").is_file() or (path / "task_info.json").is_file())
        )
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

    @app.get("/api/parameters")
    def get_parameters() -> dict:
        return {"catalog": parameter_catalog(), "values": load_values(resolved_main_config)}

    @app.put("/api/parameters")
    def put_parameters(values: dict) -> dict:
        try:
            parameters = validate_values(values)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=error.errors(include_url=False))
        save_values(resolved_main_config, parameters)
        return {"values": load_values(resolved_main_config)}

    def _launch_dir_or_404(launch_id: str) -> Path:
        launch_dir = resolve_launch_dir(resolved_results_root, launch_id)
        if launch_dir is None:
            raise HTTPException(status_code=404, detail=f"unknown launch: {launch_id}")
        return launch_dir

    @app.get("/api/artifacts/{launch_id:path}/tree")
    def get_artifact_tree(launch_id: str) -> dict:
        return {"tree": artifact_tree(_launch_dir_or_404(launch_id))}

    @app.get("/api/artifacts/{launch_id:path}/file")
    def get_artifact_file(launch_id: str, path: str) -> FileResponse:
        launch_dir = _launch_dir_or_404(launch_id)
        try:
            artifact = resolve_artifact(launch_dir, path)
        except ArtifactPathError:
            raise HTTPException(status_code=400, detail=f"path escapes launch directory: {path}")
        if not artifact.is_file():
            raise HTTPException(status_code=404, detail=f"no such artifact: {path}")
        return FileResponse(artifact, media_type=guess_media_type(artifact))

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
