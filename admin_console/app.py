"""FastAPI application factory for the Admin Console."""

from __future__ import annotations

import sys
from pathlib import Path

import json

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ValidationError

from admin_console.artifacts import (
    ArtifactPathError,
    artifact_tree,
    guess_media_type,
    resolve_artifact,
    resolve_launch_dir,
)
from admin_console.launches import scan_launches
from admin_console.live import count_rounds, infer_stage, recent_artifacts, stream_log
from admin_console.structured_views import (
    ExperimentRunPathError,
    build_experiment_run_detail,
    build_timeline,
)
from admin_console.parameters import (
    load_values,
    parameter_catalog,
    save_values,
    validate_values,
)
from admin_console.queue import LaunchQueue, UnknownTaskError
from admin_console.tasks import (
    TaskExistsError,
    TaskNameError,
    create_task,
    list_tasks as list_task_summaries,
    write_upload_to_temp,
)
from admin_console.model_catalog import (
    load_catalog,
    save_catalog,
    validate_catalog,
)
from internagent.prompt_library import (
    DEFAULT_LIBRARY_ROOT,
    PromptLibrary,
    UnknownPromptError,
)

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


class PromptUpdate(BaseModel):
    text: str


def create_app(
    results_root: Path | None = None,
    tasks_root: Path | None = None,
    config_paths: list[Path] | None = None,
    runner_command: list[str] | None = None,
    main_config_path: Path | None = None,
    prompt_library_root: Path | None = None,
    model_catalog_path: Path | None = None,
) -> FastAPI:
    resolved_results_root = results_root or (REPOSITORY_ROOT / "results")
    resolved_tasks_root = tasks_root or (REPOSITORY_ROOT / "tasks")
    resolved_main_config = main_config_path or DEFAULT_CONFIG_PATHS[0]
    resolved_prompt_root = prompt_library_root or DEFAULT_LIBRARY_ROOT
    resolved_catalog_path = model_catalog_path or DEFAULT_CONFIG_PATHS[1]
    prompt_library = PromptLibrary(resolved_prompt_root)
    queue = LaunchQueue(
        results_root=resolved_results_root,
        tasks_root=resolved_tasks_root,
        config_paths=config_paths or DEFAULT_CONFIG_PATHS,
        runner_command=runner_command or DEFAULT_RUNNER_COMMAND,
        prompt_library_root=resolved_prompt_root,
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
        return {"tasks": list_task_summaries(resolved_tasks_root)}

    @app.post("/api/tasks", status_code=201)
    async def create_task_endpoint(
        name: str = Form(...),
        system: str = Form(...),
        task_description: str = Form(...),
        domain: str = Form(...),
        background: str = Form(...),
        constraints: str = Form("[]"),
        baseline_code: UploadFile | None = File(None),
    ) -> dict:
        try:
            parsed_constraints = json.loads(constraints)
            if not isinstance(parsed_constraints, list):
                raise ValueError("constraints must be a JSON list")
        except (json.JSONDecodeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=f"invalid constraints: {error}")

        zip_path = None
        try:
            if baseline_code is not None and baseline_code.filename:
                zip_path = write_upload_to_temp(await baseline_code.read())
            summary = create_task(
                tasks_root=resolved_tasks_root,
                name=name,
                system=system,
                task_description=task_description,
                domain=domain,
                background=background,
                constraints=[str(item) for item in parsed_constraints],
                baseline_zip=zip_path,
            )
        except TaskNameError as error:
            raise HTTPException(status_code=400, detail=str(error))
        except TaskExistsError:
            raise HTTPException(status_code=409, detail=f"task already exists: {name}")
        finally:
            if zip_path is not None:
                zip_path.unlink(missing_ok=True)
        return summary

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

    @app.get("/api/prompts")
    def list_prompts() -> dict:
        return {
            "prompts": [
                {**entry.to_dict(), "text": prompt_library.get(entry.id)}
                for entry in prompt_library.list()
            ]
        }

    @app.get("/api/prompts/{prompt_id}")
    def get_prompt(prompt_id: str) -> dict:
        try:
            entry = prompt_library.get_entry(prompt_id)
            return {**entry.to_dict(), "text": prompt_library.get(prompt_id)}
        except UnknownPromptError:
            raise HTTPException(status_code=404, detail=f"unknown prompt: {prompt_id}")

    @app.put("/api/prompts/{prompt_id}")
    def put_prompt(prompt_id: str, update: PromptUpdate) -> dict:
        try:
            entry = prompt_library.save(prompt_id, update.text)
        except UnknownPromptError:
            raise HTTPException(status_code=404, detail=f"unknown prompt: {prompt_id}")
        return {**entry.to_dict(), "text": prompt_library.get(prompt_id)}

    @app.get("/api/model-catalog")
    def get_model_catalog() -> dict:
        return load_catalog(resolved_catalog_path)

    @app.put("/api/model-catalog")
    def put_model_catalog(values: dict) -> dict:
        try:
            document = validate_catalog(values)
        except ValidationError as error:
            raise HTTPException(
                status_code=422,
                detail=json.loads(error.json()),
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
        save_catalog(resolved_catalog_path, document)
        return load_catalog(resolved_catalog_path)

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

    @app.get("/api/launches/{launch_id:path}/timeline")
    def launch_timeline(launch_id: str) -> dict:
        return build_timeline(_launch_dir_or_404(launch_id))

    @app.get("/api/launches/{launch_id:path}/experiment-run")
    def experiment_run_detail(launch_id: str, path: str) -> dict:
        launch_dir = _launch_dir_or_404(launch_id)
        try:
            return build_experiment_run_detail(launch_dir, path)
        except ExperimentRunPathError as error:
            raise HTTPException(status_code=400, detail=str(error))

    @app.get("/api/launches/{launch_id:path}/status")
    def launch_status(launch_id: str) -> dict:
        launch_dir = _launch_dir_or_404(launch_id)
        state = queue.state_for_launch(launch_id)
        if state is None:
            state = next(
                (l.state for l in scan_launches(resolved_results_root) if l.id == launch_id),
                "unknown",
            )
        return {
            "state": state,
            "stage": infer_stage(launch_dir),
            "rounds": count_rounds(launch_dir),
            "recent_artifacts": recent_artifacts(launch_dir),
        }

    @app.get("/api/launches/{launch_id:path}/logs/stream")
    def launch_log_stream(launch_id: str, file: str = "runner.log") -> StreamingResponse:
        launch_dir = _launch_dir_or_404(launch_id)
        try:
            log_path = resolve_artifact(launch_dir, file)
        except ArtifactPathError:
            raise HTTPException(status_code=400, detail=f"path escapes launch directory: {file}")

        def is_running() -> bool:
            return queue.state_for_launch(launch_id) == "running"

        return StreamingResponse(
            stream_log(log_path, is_running), media_type="text/event-stream"
        )

    @app.delete("/api/queue/{queue_id}")
    def cancel_queued(queue_id: str) -> dict:
        try:
            entry = queue.cancel(queue_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown queue entry: {queue_id}")
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error))
        return entry.to_dict()

    def _stop(queue_id: str, force: bool) -> dict:
        try:
            entry = queue.stop(queue_id, force=force)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown queue entry: {queue_id}")
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error))
        return entry.to_dict()

    @app.post("/api/queue/{queue_id}/stop")
    def graceful_stop(queue_id: str) -> dict:
        return _stop(queue_id, force=False)

    @app.post("/api/queue/{queue_id}/kill")
    def force_kill(queue_id: str) -> dict:
        return _stop(queue_id, force=True)

    @app.post("/api/launches/{launch_id:path}/resume", status_code=201)
    def resume_launch(launch_id: str) -> dict:
        # Launch Resume is defined for aborted Launches only (CONTEXT.md).
        _launch_dir_or_404(launch_id)
        state = queue.state_for_launch(launch_id)
        if state != "aborted":
            raise HTTPException(
                status_code=409,
                detail=f"only aborted launches can be resumed, state is {state}",
            )
        task = launch_id.split("/", 1)[0]
        try:
            entry = queue.submit(task, launch_id=launch_id)
        except UnknownTaskError:
            raise HTTPException(status_code=404, detail=f"unknown task for launch: {launch_id}")
        return entry.to_dict()

    return app
