"""Process entry for a real Web Discovery Launch.

This module is deliberately a thin adapter.  It prepares the private filesystem
shape required by the existing ``launch_discovery.py`` command, starts that
command in experiment/Codex mode, streams its output into the Launch console,
and projects the process outcome back into the sidecar lifecycle store.
"""

from __future__ import annotations

import argparse
import base64
import copy
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


def _materialize_task(
    launch_dir: Path,
    input_snapshot: dict[str, Any],
) -> Path:
    execution_root = launch_dir / ".execution"
    task_dir = execution_root / "task"
    task_dir.mkdir(parents=True, exist_ok=True)
    if (task_dir / "task_info.json").is_file():
        return task_dir

    execution_input = input_snapshot.get("execution_input") or {}
    sources = input_snapshot.get("sources") or []
    data_dir = task_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    data_manifest: list[dict[str, str]] = []

    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            continue
        filename = str(source.get("filename") or f"source-{index}")
        encoded = source.get("content_base64")
        if not isinstance(encoded, str):
            continue
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
    checklist = [
        {"type": "text", "weight": 1.0, "content": str(constraint)}
        for constraint in constraints
        if str(constraint).strip()
    ]
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

    model_id = configuration_snapshot.get("model_id")
    if isinstance(model_id, str) and model_id.strip():
        config.setdefault("experiment", {})["model"] = model_id
    settings = configuration_snapshot.get("settings")
    if isinstance(settings, dict):
        config["discovery_model_settings"] = copy.deepcopy(settings)
    config["experiment"] = dict(config.get("experiment") or {})
    config["experiment"]["mode"] = "experiment"
    config["experiment"]["backend"] = "codex"

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
        task_dir = _materialize_task(launch_dir, input_snapshot)
        config_path = _materialize_config(
            repository_root, launch_dir, configuration_snapshot
        )

        store.worker_started(launch_dir.name, attempt_id, os.getpid())
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

        environment = os.environ.copy()
        python_path = [
            str(repository_root),
            str(repository_root / "desktop" / "openworker" / "upstream"),
        ]
        existing_python_path = environment.get("PYTHONPATH")
        if existing_python_path:
            python_path.append(existing_python_path)
        environment["PYTHONPATH"] = os.pathsep.join(python_path)

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
        choices=["codex"],
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
