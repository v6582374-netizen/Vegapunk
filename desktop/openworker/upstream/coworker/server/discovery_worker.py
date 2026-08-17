"""Process entry for a real Web Discovery Launch.

This module is deliberately a thin adapter.  It prepares the private filesystem
shape required by the existing ``launch_discovery.py`` command, starts that
command in experiment mode with the selected coding-agent backend, streams its
output into the Launch console,
and projects the process outcome back into the sidecar lifecycle store.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import io
import json
import os
import shutil
import selectors
import signal
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import yaml


SUPPORTED_TASK_TYPES = frozenset({"auto", "sci"})
DEFAULT_TASK_TYPE = "sci"


def _repository_root(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return Path(__file__).resolve().parents[5]


def _safe_child(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise ValueError(f"archive member escapes launch task root: {relative}")
    return candidate


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _deep_merge(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def _task_type(input_snapshot: dict[str, Any]) -> str:
    """Return the immutable task type for one Web Launch.

    Early Web revisions predate the explicit field and were materialized as
    scientific tasks.  Keep that behavior for resumability, but reject an
    explicit unknown value instead of silently taking a different branch.
    """

    execution_input = input_snapshot.get("execution_input") or {}
    raw = (
        execution_input.get("task_type")
        if isinstance(execution_input, dict)
        else None
    )
    if raw is None:
        return DEFAULT_TASK_TYPE
    if not isinstance(raw, str) or raw.strip().lower() not in SUPPORTED_TASK_TYPES:
        supported = ", ".join(sorted(SUPPORTED_TASK_TYPES))
        raise ValueError(f"task_type must be one of: {supported}")
    return raw.strip().lower()


def _canonical_catalog_model_id(model_id: str, catalog: dict[str, Any]) -> str:
    """Convert the Desktop picker spelling to one declared catalog identity.

    The Desktop picker uses ``provider:model`` while the in-process Runtime uses
    the explicit ``provider/model`` identity.  This is a representation bridge,
    not an alias: the resulting identity must already exist in the catalog.
    """

    selected = model_id.strip()
    if "/" in selected:
        canonical_id = selected
    elif ":" in selected:
        provider, model = selected.split(":", 1)
        canonical_id = f"{provider}/{model}"
    else:
        models = catalog.get("models")
        candidates = [
            str(canonical_id)
            for canonical_id, definition in (models.items() if isinstance(models, dict) else [])
            if isinstance(definition, dict) and definition.get("model") == selected
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"Discovery model {model_id!r} must use provider/model or provider:model"
            )
        canonical_id = candidates[0]

    models = catalog.get("models")
    if not isinstance(models, dict) or canonical_id not in models:
        raise ValueError(
            f"Discovery model {model_id!r} is not declared in the model catalog"
        )
    return canonical_id


def _catalog_binding_for_provider(
    catalog: dict[str, Any], provider: str, capability: str
) -> str | None:
    models = catalog.get("models")
    if not isinstance(models, dict):
        return None
    for canonical_id, definition in models.items():
        if not isinstance(definition, dict):
            continue
        if str(definition.get("provider")) != provider:
            continue
        capabilities = definition.get("capabilities") or []
        if capability in capabilities:
            return str(canonical_id)
    return None


def _materialize_task(
    launch_dir: Path,
    input_snapshot: dict[str, Any],
    discovery_root: Path | None = None,
) -> Path:
    execution_root = launch_dir / ".execution"
    task_dir = execution_root / "task"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_type = _task_type(input_snapshot)
    marker = task_dir / ("prompt.json" if task_type == "auto" else "task_info.json")
    if marker.is_file():
        return task_dir

    execution_input = input_snapshot.get("execution_input") or {}
    if not isinstance(execution_input, dict):
        execution_input = {}
    sources = input_snapshot.get("sources") or []
    data_dir = task_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    data_manifest: list[dict[str, str]] = []

    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            continue
        filename = str(source.get("filename") or f"source-{index}")
        content_ref = source.get("content_ref")
        if isinstance(content_ref, str):
            if discovery_root is None:
                raise ValueError("source content store is unavailable")
            digest = content_ref.removeprefix("sha256:")
            if (
                len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
                or digest != str(source.get("sha256") or "")
            ):
                raise ValueError("source content reference is invalid")
            source_path = (discovery_root / "sources" / digest).resolve()
            source_root = (discovery_root / "sources").resolve()
            if source_path.parent != source_root:
                raise ValueError("source content reference escapes source store")
            content = source_path.read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError("source content digest does not match its manifest")
        else:
            encoded = source.get("content_base64")
            if not isinstance(encoded, str):
                raise ValueError(f"source content is missing: {filename}")
            content = base64.b64decode(encoded, validate=True)
        extension = str(source.get("extension") or Path(filename).suffix).lower()
        if extension == ".zip":
            # A Preparation ZIP is an optional baseline/code package, not a new
            # Run-time input.  Its safe extraction happens once inside this
            # private task workspace and is never exposed as a Web concept.
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                for member in archive.infolist():
                    member_name = member.filename.replace("\\", "/")
                    if member_name.startswith("/"):
                        raise ValueError("archive member must be relative")
                    target = _safe_child(task_dir, member_name)
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.read(member))
            data_manifest.append(
                {"name": filename, "description": "baseline code package"}
            )
            continue

        safe_name = Path(filename).name or f"source-{index}"
        destination = data_dir / f"{index:03d}-{safe_name}"
        destination.write_bytes(content)
        data_manifest.append(
            {
                "name": destination.relative_to(task_dir).as_posix(),
                "description": "Preparation source material",
            }
        )

    constraints = execution_input.get("constraints") or []
    if not isinstance(constraints, list):
        constraints = []
    normalized_constraints = [
        str(constraint) for constraint in constraints if str(constraint).strip()
    ]
    checklist = [
        {"type": "text", "weight": 1.0, "content": str(constraint)}
        for constraint in normalized_constraints
        if str(constraint).strip()
    ]

    if task_type == "auto":
        # Auto tasks use the original repository-shaped contract: a prompt file
        # is the type marker and the optional ZIP source has already been
        # extracted into this private task directory.
        _write_json(
            task_dir / "prompt.json",
            {
                "task_description": str(execution_input.get("task_description") or ""),
                "domain": str(execution_input.get("domain") or ""),
                "background": str(execution_input.get("background") or ""),
                "constraints": normalized_constraints,
                "task_type": "auto",
            },
        )
        return task_dir

    (task_dir / "target_study").mkdir(parents=True, exist_ok=True)
    _write_json(
        task_dir / "task_info.json",
        {
            "task": (
                str(execution_input.get("task_description") or "")
                + (
                    "\n\n## Background\n"
                    + str(execution_input.get("background") or "")
                    if str(execution_input.get("background") or "").strip()
                    else ""
                )
            ),
            "data": data_manifest,
            "background": str(execution_input.get("background") or ""),
            "domain": str(execution_input.get("domain") or ""),
        },
    )
    # ``normalize_sci_task`` accepts the historical list form.  Keep that exact
    # shape instead of introducing a second runtime schema.
    _write_json(task_dir / "target_study" / "checklist.json", checklist)
    (task_dir / "related_work").mkdir(parents=True, exist_ok=True)
    return task_dir


def _materialize_config(
    repository_root: Path,
    launch_dir: Path,
    configuration_snapshot: dict[str, Any],
    exp_backend: str | None = None,
) -> Path:
    default_path = repository_root / "config" / "default_config.yaml"
    try:
        config = yaml.safe_load(default_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        config = {}
    if not isinstance(config, dict):
        config = {}

    preferences = configuration_snapshot.get("discovery_launch_preferences")
    if isinstance(preferences, dict):
        for key in ("workflow", "agents", "experiment"):
            value = preferences.get(key)
            if isinstance(value, dict):
                target = config.setdefault(key, {})
                if isinstance(target, dict):
                    _deep_merge(target, value)
        if isinstance(preferences.get("skip_idea_generation"), bool):
            config["skip_idea_generation"] = preferences["skip_idea_generation"]
        if exp_backend is None:
            exp_backend = preferences.get("backend")

    if "external_data" in configuration_snapshot:
        external_data = configuration_snapshot.get("external_data")
        # The registry is launch-owned metadata. Lists are replaced rather than
        # merged so an edited Settings catalog cannot leak into an older Launch.
        config["external_data"] = (
            copy.deepcopy(external_data)
            if isinstance(external_data, dict)
            else {"api_registry": []}
        )
    else:
        # Historical Web Launches predate the External data snapshot seam. Do not
        # let today's default catalog silently change what a Resume can execute.
        config["external_data"] = {"api_registry": []}

    model_id = configuration_snapshot.get("model_id")
    if isinstance(model_id, str) and model_id.strip():
        config.setdefault("experiment", {})["model"] = model_id

    # Freeze the catalog used by this Launch. On Resume, reuse the launch-owned
    # copy even if the editable global catalog has changed or disappeared.
    launch_catalog_path = launch_dir / ".execution" / "model_catalog.yaml"
    catalog_is_frozen = launch_catalog_path.is_file()
    catalog_path = launch_catalog_path
    if launch_catalog_path.is_file():
        try:
            catalog = yaml.safe_load(launch_catalog_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as error:
            raise ValueError(
                f"Unable to read frozen model catalog {launch_catalog_path}: {error}"
            ) from error
    else:
        raw_catalog_path = config.get("model_catalog_path") or "config/model_catalog.yaml"
        catalog_path = Path(str(raw_catalog_path)).expanduser()
        if not catalog_path.is_absolute():
            catalog_path = repository_root / catalog_path
        try:
            catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as error:
            raise ValueError(f"Unable to read model catalog {catalog_path}: {error}") from error
    if not isinstance(catalog, dict):
        raise ValueError(f"Model catalog {catalog_path} must be a mapping")
    if isinstance(model_id, str) and model_id.strip():
        try:
            active_text_model = _canonical_catalog_model_id(model_id, catalog)
        except ValueError:
            if catalog_is_frozen:
                raise
            # A pre-catalog Launch may carry an older provider/model spelling.
            # Preserve that immutable launch configuration instead of making a
            # historical Resume depend on today's catalog entries.
        else:
            catalog["active_text_model"] = active_text_model
            active_provider = active_text_model.split("/", 1)[0]
            capability_models = catalog.get("capability_models")
            if isinstance(capability_models, dict):
                image_model = _catalog_binding_for_provider(
                    catalog, active_provider, "image_generation"
                )
                if image_model is None:
                    raise ValueError(
                        f"Model catalog has no {active_provider!r} image_generation binding"
                    )
                capability_models["image_generation"] = image_model
    launch_catalog_path.parent.mkdir(parents=True, exist_ok=True)
    launch_catalog_path.write_text(
        yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    config["model_catalog_path"] = str(launch_catalog_path)
    settings = configuration_snapshot.get("settings")
    if isinstance(settings, dict):
        config["discovery_model_settings"] = copy.deepcopy(settings)
    config["experiment"] = dict(config.get("experiment") or {})
    config["experiment"]["mode"] = "experiment"
    # The backend belongs to the immutable Launch snapshot.  The worker receives
    # it from the sidecar command as well, so a resumed Launch cannot observe later
    # Settings edits or fall back to a different tool.
    selected_backend = exp_backend or "codex"
    if selected_backend not in {"codex", "qwen_code", "openhands"}:
        raise ValueError(f"Unsupported Discovery backend: {selected_backend}")
    config["experiment"]["backend"] = selected_backend

    config_path = launch_dir / ".execution" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return config_path


def _seed_ideas(launch_dir: Path, input_snapshot: dict[str, Any]) -> Path:
    execution_input = input_snapshot.get("execution_input") or {}
    ideas_path = launch_dir / ".execution" / "ideas.json"
    idea = {
        "name": "saved-discovery-input",
        "title": str(execution_input.get("task_description") or "Discovery task"),
        "description": str(execution_input.get("background") or ""),
        "method": "Use the saved Preparation sources and constraints.",
    }
    ideas_path.parent.mkdir(parents=True, exist_ok=True)
    ideas_path.write_text(json.dumps([idea], ensure_ascii=False, indent=2), encoding="utf-8")
    return ideas_path


def _append_log(log_path: Path, line: str) -> None:
    with log_path.open("a", encoding="utf-8") as log:
        log.write(line.rstrip("\n") + "\n")


_TERMINAL_ERROR_PREFIXES = (
    "Fatal error:",
    "Idea generation failed:",
    "Report generation failed:",
    "Experiment execution failed:",
    "Error in session:",
)


def _terminal_error_from_log(log_path: Path) -> str | None:
    """Recover a bounded domain error after the child exits without a summary.

    ``launch_discovery.py`` has a few legacy ``sys.exit(1)`` paths, so the worker
    cannot rely on a single structured return channel yet.  Only well-known error
    prefixes are promoted from a bounded log tail; arbitrary traceback lines and
    unstructured stdout never become lifecycle state.
    """
    try:
        with log_path.open("rb") as stream:
            size = stream.seek(0, os.SEEK_END)
            stream.seek(max(0, size - 128 * 1024))
            payload = stream.read()
    except OSError:
        return None

    for raw_line in reversed(payload.decode("utf-8", errors="replace").splitlines()):
        line = raw_line.strip()
        for prefix in _TERMINAL_ERROR_PREFIXES:
            marker = line.find(prefix)
            if marker < 0:
                continue
            detail = line[marker:]
            return detail if len(detail) <= 512 else f"{detail[:509]}..."
    return None


def _project_artifacts(launch_dir: Path, returncode: int) -> None:
    artifacts_root = launch_dir / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    excluded_files = {
        "runner.log",
        "runner.json",
        "record.json",
        "input_snapshot.json",
        "launch_configuration.json",
        "checkpoint.json",
        "events.jsonl",
    }
    excluded_dirs = {"artifacts", ".execution"}

    for source in sorted(launch_dir.rglob("*")):
        if not source.is_file() or source.is_symlink():
            continue
        relative = source.relative_to(launch_dir)
        if relative.parts and relative.parts[0] in excluded_dirs:
            continue
        if source.name in excluded_files:
            continue
        destination = artifacts_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    _write_json(
        artifacts_root / "web-worker.json",
        {"runner": "launch_discovery.py", "returncode": returncode},
    )


def _paper_status(launch_dir: Path) -> dict[str, Any] | None:
    paper_dir = launch_dir / "paper_orchestra_runs" / "paper"
    if not paper_dir.exists():
        return None
    final_tex = paper_dir / "content_refinement_workdir" / "final_refined_paper.tex"
    final_pdf = paper_dir / "final_paper.pdf"
    try:
        tex_valid = final_tex.is_file() and bool(
            final_tex.read_text(encoding="utf-8").strip()
        )
        pdf = final_pdf.read_bytes()
        pdf_valid = (
            len(pdf) > 8 and pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF")
        )
    except (OSError, UnicodeError):
        tex_valid = False
        pdf_valid = False
    if tex_valid and pdf_valid:
        return {"state": "completed", "run_dir": "paper_orchestra_runs/paper"}
    return {
        "state": "failed",
        "run_dir": "paper_orchestra_runs/paper",
        "error": "PaperOrchestra did not produce a complete final TeX/PDF pair",
    }


def _paper_status_from_log(launch_dir: Path) -> dict[str, Any] | None:
    try:
        log = (launch_dir / "runner.log").read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return None
    if "paperorchestra failed" not in log.lower():
        return None
    return {
        "state": "failed",
        "run_dir": "paper_orchestra_runs/paper",
        "error": (
            "PaperOrchestra reported a terminal failure; Discovery artifacts were "
            "preserved"
        ),
    }


def run(
    *,
    launcher_entry: Path,
    launch_dir: Path,
    discovery_root: Path,
    attempt_id: str,
    repository_root: Path,
    mode: str,
    exp_backend: str,
    resume: bool,
    secret_store: Any | None = None,
) -> int:
    # Import after the parent has supplied PYTHONPATH.  This keeps the worker
    # executable as a plain Python entry while preserving the sidecar package seam.
    from coworker.server.discovery_launch import DiscoveryLaunchStore

    launch_dir = launch_dir.resolve()
    log_path = launch_dir / "runner.log"
    store = DiscoveryLaunchStore(
        discovery_root,
        runner_mode="real",
        repository_root=repository_root,
    )
    child: subprocess.Popen[str] | None = None
    stopping = False
    selector: selectors.BaseSelector | None = None
    try:
        input_snapshot = json.loads(
            (launch_dir / "input_snapshot.json").read_text(encoding="utf-8")
        )
        configuration_snapshot = json.loads(
            (launch_dir / "launch_configuration.json").read_text(encoding="utf-8")
        )
        task_dir = _materialize_task(launch_dir, input_snapshot, discovery_root)
        launch_catalog_path = launch_dir / ".execution" / "model_catalog.yaml"
        catalog_was_frozen = launch_catalog_path.is_file()
        config_path = _materialize_config(
            repository_root, launch_dir, configuration_snapshot, exp_backend
        )
        from coworker.server.discovery_runtime import (
            apply_provider_overrides,
            prepare_launch_environment,
        )

        # This is the admission seam for the production launcher.  Resolve every
        # Provider bound by the frozen catalog and every launch-owned external-data
        # entry, inject credentials only into the child environment, and freeze
        # non-sensitive endpoint overrides before the Launch is projected as running.
        prepared_environment = prepare_launch_environment(
            launch_dir / ".execution" / "model_catalog.yaml",
            secret_store=secret_store,
            external_data=configuration_snapshot.get("external_data"),
            exp_backend=exp_backend,
        )
        if not catalog_was_frozen:
            apply_provider_overrides(
                launch_catalog_path,
                prepared_environment.provider_overrides,
            )

        command = [
            sys.executable,
            str(launcher_entry),
            "--task",
            str(task_dir),
            "--launch_dir",
            str(launch_dir),
            "--config",
            str(config_path),
            "--mode",
            mode,
            "--exp_backend",
            exp_backend,
        ]
        command.extend(["--task_type", _task_type(input_snapshot)])
        preferences = configuration_snapshot.get("discovery_launch_preferences") or {}
        if isinstance(preferences, dict) and preferences.get("skip_idea_generation"):
            command.extend(
                [
                    "--skip_idea_generation",
                    "--idea_path",
                    str(_seed_ideas(launch_dir, input_snapshot)),
                ]
            )
        if resume:
            command.extend(["--resume", str(launch_dir)])

        environment = prepared_environment.environment
        python_path = [
            str(repository_root),
            str(repository_root / "desktop" / "openworker" / "upstream"),
        ]
        existing_python_path = environment.get("PYTHONPATH")
        if existing_python_path:
            python_path.append(existing_python_path)
        environment["PYTHONPATH"] = os.pathsep.join(python_path)

        # Only now is the attempt trusted enough to become visible as running.
        store.worker_started(launch_dir.name, attempt_id, os.getpid())
        _append_log(log_path, f"web-worker: starting {' '.join(command)}")
        child = subprocess.Popen(
            command,
            cwd=str(repository_root),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        if child.stdout is not None:
            selector = selectors.DefaultSelector()
            selector.register(child.stdout, selectors.EVENT_READ)
        while child.poll() is None:
            try:
                current = store.status(launch_dir.name)
                if current.get("state") == "stopping" and child.poll() is None:
                    stopping = True
                    os.killpg(child.pid, signal.SIGTERM)
            except (KeyError, OSError, ProcessLookupError):
                pass

            ready = selector.select(timeout=0.1) if selector is not None else []
            for _key, _mask in ready:
                line = child.stdout.readline() if child.stdout is not None else ""
                if not line:
                    continue
                _append_log(log_path, line)
                lowered = line.lower()
                if (
                    "paperorchestra" in lowered
                    or "all discovery rounds completed" in lowered
                ):
                    store.worker_stage(launch_dir.name, attempt_id, "finalizing", 3)
                elif (
                    "starting discovery round" in lowered
                    or "experiment execution" in lowered
                ):
                    store.worker_stage(launch_dir.name, attempt_id, "research", 2)

        if child.stdout is not None:
            for line in child.stdout:
                _append_log(log_path, line)
        if selector is not None:
            selector.close()
            selector = None

        returncode = child.wait()
        if stopping:
            store.worker_finish(
                launch_dir.name,
                attempt_id,
                succeeded=False,
                stopped=True,
                error="graceful stop",
            )
            return 0

        summary_exists = (launch_dir / "discovery_summary.json").is_file()
        succeeded = returncode == 0 and summary_exists
        paper_status = _paper_status(launch_dir) if summary_exists else None
        if summary_exists and paper_status is None:
            paper_status = _paper_status_from_log(launch_dir)
        _project_artifacts(launch_dir, returncode)
        error = None
        if not succeeded:
            error = _terminal_error_from_log(log_path)
            if error is None:
                error = (
                    f"production Discovery launcher exited with code {returncode}"
                    if returncode != 0
                    else "production Discovery launcher exited without discovery_summary.json"
                )
        store.worker_finish(
            launch_dir.name,
            attempt_id,
            succeeded=succeeded,
            error=error,
            paper_orchestra=paper_status,
        )
        return 0 if succeeded else 1
    except Exception as error:
        _append_log(log_path, f"web-worker: {type(error).__name__}: {error}")
        try:
            if child is not None and child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
        if selector is not None:
            selector.close()
        store.worker_finish(
            launch_dir.name,
            attempt_id,
            succeeded=False,
            error=str(error),
        )
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one real Web Discovery Launch")
    parser.add_argument("launcher_entry")
    parser.add_argument(
        "--launch-dir", "--launch_dir", dest="launch_dir", required=True
    )
    parser.add_argument("--discovery-root", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--repository-root", default=None)
    parser.add_argument("--mode", choices=["experiment"], default="experiment")
    parser.add_argument(
        "--exp-backend",
        "--exp_backend",
        dest="exp_backend",
        choices=["codex", "qwen_code", "openhands"],
        default="codex",
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    repository_root = _repository_root(args.repository_root)
    return run(
        launcher_entry=Path(args.launcher_entry).expanduser().resolve(),
        launch_dir=Path(args.launch_dir).expanduser().resolve(),
        discovery_root=Path(args.discovery_root).expanduser().resolve(),
        attempt_id=args.attempt_id,
        repository_root=repository_root,
        mode=args.mode,
        exp_backend=args.exp_backend,
        resume=args.resume,
    )


if __name__ == "__main__":  # pragma: no cover - exercised in the worker process
    raise SystemExit(main())
