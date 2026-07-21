"""FastAPI application factory for the Admin Console."""

from __future__ import annotations

import sys
from pathlib import Path

import json

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from admin_console.auth import AdminAuth
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
from vegapunk.prompt_library import (
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


class AdminLogin(BaseModel):
    username: str
    password: str


def create_app(
    results_root: Path | None = None,
    tasks_root: Path | None = None,
    config_paths: list[Path] | None = None,
    runner_command: list[str] | None = None,
    main_config_path: Path | None = None,
    prompt_library_root: Path | None = None,
    model_catalog_path: Path | None = None,
    auth_db_path: Path | None = None,
    admin_password: str | None = None,
    frontend_dist: Path | None = None,
) -> FastAPI:
    resolved_results_root = results_root or (REPOSITORY_ROOT / "results")
    resolved_tasks_root = tasks_root or (REPOSITORY_ROOT / "tasks")
    resolved_main_config = main_config_path or DEFAULT_CONFIG_PATHS[0]
    resolved_prompt_root = prompt_library_root or DEFAULT_LIBRARY_ROOT
    resolved_catalog_path = model_catalog_path or DEFAULT_CONFIG_PATHS[1]
    resolved_frontend_dist = frontend_dist or (REPOSITORY_ROOT / "frontend" / "dist")
    resolved_auth_db = auth_db_path or (
        resolved_results_root.parent / ".vegapunk" / "admin-auth.sqlite3"
    )
    prompt_library = PromptLibrary(resolved_prompt_root)
    auth = AdminAuth(resolved_auth_db, password=admin_password)
    queue = LaunchQueue(
        results_root=resolved_results_root,
        tasks_root=resolved_tasks_root,
        config_paths=config_paths or DEFAULT_CONFIG_PATHS,
        runner_command=runner_command or DEFAULT_RUNNER_COMMAND,
        prompt_library_root=resolved_prompt_root,
    )

    app = FastAPI(title="Vegapunk")
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "::1", "[::1]", "testserver"],
    )

    @app.middleware("http")
    async def same_origin_api_requests(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            expected_origin = str(request.base_url).rstrip("/")
            if origin.rstrip("/") != expected_origin:
                return JSONResponse(
                    {"detail": "cross-origin API requests are not allowed"},
                    status_code=403,
                )
        return await call_next(request)

    def require_admin(request: Request) -> str:
        username = auth.session_username(request.cookies.get(auth.cookie_name))
        if username is None:
            raise HTTPException(status_code=401, detail="administrator authentication required")
        return username

    admin_router = APIRouter(
        prefix="/api/admin",
        dependencies=[Depends(require_admin)],
    )

    @app.post("/api/auth/login")
    def login(credentials: AdminLogin, response: Response) -> dict:
        token = auth.login(credentials.username, credentials.password)
        if token is None:
            raise HTTPException(status_code=401, detail="invalid administrator credentials")
        response.set_cookie(
            key=auth.cookie_name,
            value=token,
            httponly=True,
            samesite="strict",
            secure=False,
            max_age=auth.absolute_seconds,
            path="/",
        )
        return {"authenticated": True, "username": credentials.username}

    @app.get("/api/auth/me")
    def current_session(request: Request) -> dict:
        username = auth.session_username(request.cookies.get(auth.cookie_name))
        if username is None:
            return {"authenticated": False}
        return {"authenticated": True, "username": username}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response) -> dict:
        auth.logout(request.cookies.get(auth.cookie_name))
        response.delete_cookie(auth.cookie_name, path="/")
        return {"authenticated": False}

    @admin_router.get("/launches")
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

    @admin_router.get("/tasks")
    def list_tasks() -> dict:
        return {"tasks": list_task_summaries(resolved_tasks_root)}

    @admin_router.post("/tasks", status_code=201)
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

    @admin_router.get("/queue")
    def list_queue() -> dict:
        return {"entries": [entry.to_dict() for entry in queue.entries()]}

    @admin_router.post("/queue", status_code=201)
    def submit_launch(submission: QueueSubmission) -> dict:
        try:
            entry = queue.submit(submission.task)
        except UnknownTaskError:
            raise HTTPException(status_code=404, detail=f"unknown task: {submission.task}")
        return entry.to_dict()

    @admin_router.get("/prompts")
    def list_prompts() -> dict:
        return {
            "prompts": [
                {**entry.to_dict(), "text": prompt_library.get(entry.id)}
                for entry in prompt_library.list()
            ]
        }

    @admin_router.get("/prompts/{prompt_id}")
    def get_prompt(prompt_id: str) -> dict:
        try:
            entry = prompt_library.get_entry(prompt_id)
            return {**entry.to_dict(), "text": prompt_library.get(prompt_id)}
        except UnknownPromptError:
            raise HTTPException(status_code=404, detail=f"unknown prompt: {prompt_id}")

    @admin_router.put("/prompts/{prompt_id}")
    def put_prompt(prompt_id: str, update: PromptUpdate) -> dict:
        try:
            entry = prompt_library.save(prompt_id, update.text)
        except UnknownPromptError:
            raise HTTPException(status_code=404, detail=f"unknown prompt: {prompt_id}")
        return {**entry.to_dict(), "text": prompt_library.get(prompt_id)}

    @admin_router.get("/model-catalog")
    def get_model_catalog() -> dict:
        return load_catalog(resolved_catalog_path)

    @admin_router.put("/model-catalog")
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

    @admin_router.get("/parameters")
    def get_parameters() -> dict:
        return {"catalog": parameter_catalog(), "values": load_values(resolved_main_config)}

    @admin_router.put("/parameters")
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

    @admin_router.get("/artifacts/{launch_id:path}/tree")
    def get_artifact_tree(launch_id: str) -> dict:
        return {"tree": artifact_tree(_launch_dir_or_404(launch_id))}

    @admin_router.get("/artifacts/{launch_id:path}/file")
    def get_artifact_file(launch_id: str, path: str) -> FileResponse:
        launch_dir = _launch_dir_or_404(launch_id)
        try:
            artifact = resolve_artifact(launch_dir, path)
        except ArtifactPathError:
            raise HTTPException(status_code=400, detail=f"path escapes launch directory: {path}")
        if not artifact.is_file():
            raise HTTPException(status_code=404, detail=f"no such artifact: {path}")
        return FileResponse(artifact, media_type=guess_media_type(artifact))

    @admin_router.get("/launches/{launch_id:path}/timeline")
    def launch_timeline(launch_id: str) -> dict:
        return build_timeline(_launch_dir_or_404(launch_id))

    @admin_router.get("/launches/{launch_id:path}/experiment-run")
    def experiment_run_detail(launch_id: str, path: str) -> dict:
        launch_dir = _launch_dir_or_404(launch_id)
        try:
            return build_experiment_run_detail(launch_dir, path)
        except ExperimentRunPathError as error:
            raise HTTPException(status_code=400, detail=str(error))

    @admin_router.get("/launches/{launch_id:path}/status")
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

    @admin_router.get("/launches/{launch_id:path}/logs/stream")
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

    @admin_router.delete("/queue/{queue_id}")
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

    @admin_router.post("/queue/{queue_id}/stop")
    def graceful_stop(queue_id: str) -> dict:
        return _stop(queue_id, force=False)

    @admin_router.post("/queue/{queue_id}/kill")
    def force_kill(queue_id: str) -> dict:
        return _stop(queue_id, force=True)

    @admin_router.post("/launches/{launch_id:path}/resume", status_code=201)
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

    app.include_router(admin_router)

    if resolved_frontend_dist.is_dir():
        assets_root = resolved_frontend_dist / "assets"
        if assets_root.is_dir():
            app.mount(
                "/assets",
                StaticFiles(directory=assets_root),
                name="frontend-assets",
            )

        index_path = resolved_frontend_dist / "index.html"

        @app.get("/{full_path:path}", include_in_schema=False)
        def frontend_entry(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="not found")
            candidate = (resolved_frontend_dist / full_path).resolve()
            try:
                candidate.relative_to(resolved_frontend_dist.resolve())
            except ValueError:
                raise HTTPException(status_code=404, detail="not found")
            if candidate.is_file():
                return FileResponse(candidate)
            if index_path.is_file():
                return FileResponse(index_path)
            raise HTTPException(status_code=404, detail="frontend entry not found")

    return app
