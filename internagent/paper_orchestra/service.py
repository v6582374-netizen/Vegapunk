from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, TextIO

from internagent.mas.models.unified_runtime import UnifiedModelRuntime

from .candidate_selection import select_candidate
from .chinese_companion import generate_chinese_companion
from .config import PaperOrchestraConfig, load_paper_config
from .data_types import (
    PaperOrchestraError,
    PaperOrchestraRunResult,
    PaperOrchestraStageError,
)
from .utils.path_utils import resolve_launch_directory


PAPER_ORCHESTRA_RUN_ID = "paper"
FINAL_PDF_RELATIVE_PATH = Path("final_paper.pdf")
FINAL_TEX_RELATIVE_PATH = Path(
    "content_refinement_workdir/final_refined_paper.tex"
)


async def run_paper_orchestra(
    *,
    launch_dir: Path,
    internagent_config: dict[str, Any],
    paper_config_path: Path,
) -> PaperOrchestraRunResult:
    """Generate the Discovery Launch's single Paper with vendored upstream code."""

    launch_dir = launch_dir.resolve()
    run_dir = launch_dir / "paper_orchestra_runs" / PAPER_ORCHESTRA_RUN_ID
    try:
        _validate_launch(launch_dir)
        paper_config = load_paper_config(paper_config_path)
        catalog_path = _resolve_catalog_path(internagent_config)
        runtime = UnifiedModelRuntime.from_catalog_path(catalog_path)
        _validate_paper_models(runtime, paper_config)
    except PaperOrchestraStageError as error:
        return _error_result(run_dir, error.error)
    except Exception as error:
        return _error_result(
            run_dir,
            PaperOrchestraError(
                stage="paper_orchestra_adapter",
                code="invalid_model_catalog",
                message=str(error),
            ),
        )

    existing = _existing_result(run_dir)
    if existing is not None:
        return existing

    run_dir.mkdir(parents=True, exist_ok=True)
    selection = await _optional_candidate_selection(
        launch_dir=launch_dir,
        run_dir=run_dir,
        internagent_config=internagent_config,
        runtime=runtime,
    )

    try:
        candidate_dir = _selected_candidate_directory(launch_dir, selection)
        _prepare_raw_materials(
            launch_dir=launch_dir,
            candidate_dir=candidate_dir,
            raw_materials_dir=run_dir / "raw_materials",
        )
        runtime_config_path = _write_runtime_config(
            run_dir=run_dir,
            catalog_path=catalog_path,
            paper_config=paper_config,
            runtime=runtime,
        )
        completed = _run_vendored_cli(
            run_dir=run_dir,
            paper_config=paper_config,
            runtime_config_path=runtime_config_path,
        )
    except PaperOrchestraStageError as error:
        return _error_result(run_dir, error.error)
    except Exception as error:
        return _error_result(
            run_dir,
            PaperOrchestraError(
                stage="paper_orchestra_adapter",
                code="unexpected_paper_orchestra_error",
                message=str(error),
            ),
        )

    stderr_path = run_dir / "stderr.log"
    if completed.returncode != 0:
        return _error_result(
            run_dir,
            PaperOrchestraError(
                stage="vendored_paper_orchestra",
                code="upstream_process_failed",
                message=(
                    f"vendored PaperOrchestra exited with code "
                    f"{completed.returncode}: {_log_tail(stderr_path)}"
                ),
                log_path=str(stderr_path),
            ),
        )
    if not _final_outputs_are_valid(run_dir):
        return _error_result(
            run_dir,
            PaperOrchestraError(
                stage="vendored_paper_orchestra",
                code="missing_final_outputs",
                message=(
                    "vendored PaperOrchestra exited without a complete final "
                    f"TeX/PDF pair: {_log_tail(stderr_path)}"
                ),
                log_path=str(stderr_path),
            ),
        )
    try:
        await asyncio.to_thread(
            generate_chinese_companion,
            run_dir=run_dir,
            runtime=runtime,
            model_name=runtime.catalog.active_text_model,
        )
    except Exception as error:
        return _successful_result(
            run_dir,
            warnings=(f"Chinese companion generation failed: {error}",),
        )
    return _successful_result(run_dir)


def _validate_launch(launch_dir: Path) -> dict[str, Any]:
    if not launch_dir.is_dir():
        _input_error(f"Discovery Launch directory does not exist: {launch_dir}")
    _read_json_object(launch_dir / "prompt.json")
    summary = _read_json_object(launch_dir / "discovery_summary.json")
    rounds = summary.get("rounds")
    if not isinstance(rounds, list) or not rounds:
        _input_error("discovery_summary.json must contain non-empty rounds")
    return summary


async def _optional_candidate_selection(
    *,
    launch_dir: Path,
    run_dir: Path,
    internagent_config: dict[str, Any],
    runtime: UnifiedModelRuntime,
) -> dict[str, Any] | None:
    try:
        return await select_candidate(launch_dir=launch_dir, run_dir=run_dir)
    except PaperOrchestraStageError as error:
        if error.code != "criterion_inference_requires_model":
            return None
    except Exception:
        return None

    try:
        del internagent_config
        model = runtime.model_for(capability="text")
        return await select_candidate(
            launch_dir=launch_dir,
            run_dir=run_dir,
            model=model,
        )
    except Exception:
        return None


def _selected_candidate_directory(
    launch_dir: Path, selection: dict[str, Any] | None
) -> Path | None:
    if not selection:
        return None
    selected = selection.get("selected_candidate")
    if not isinstance(selected, dict):
        return None
    folder_name = selected.get("folder_name")
    if not isinstance(folder_name, str) or not folder_name:
        return None
    try:
        candidate_dir = resolve_launch_directory(launch_dir, folder_name)
    except (OSError, ValueError):
        return None
    return candidate_dir if candidate_dir.is_dir() else None


def _prepare_raw_materials(
    *, launch_dir: Path, candidate_dir: Path | None, raw_materials_dir: Path
) -> None:
    raw_materials_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = launch_dir / "prompt.json"
    idea_parts = [
        "# Paper Idea Brief",
        "",
        _render_source(
            title="Launch Prompt",
            source=prompt_path.relative_to(launch_dir),
            content=prompt_path.read_text(encoding="utf-8"),
            language="json",
        ),
    ]
    if candidate_dir is not None:
        notes_path = candidate_dir / "notes.txt"
        if notes_path.is_file():
            idea_parts.append(
                _render_source(
                    title="Selected Research Candidate Notes",
                    source=notes_path.relative_to(launch_dir),
                    content=notes_path.read_text(encoding="utf-8"),
                )
            )
    (raw_materials_dir / "idea_sparse.md").write_text(
        "\n".join(idea_parts).rstrip() + "\n",
        encoding="utf-8",
    )

    experiment_parts = ["# Experimental Record", ""]
    if candidate_dir is not None:
        narrative_path = candidate_dir / "experiment_report.txt"
        if not narrative_path.is_file():
            narrative_path = candidate_dir / "log.txt"
        if narrative_path.is_file():
            experiment_parts.append(
                _render_source(
                    title="Candidate Experiment Narrative",
                    source=narrative_path.relative_to(launch_dir),
                    content=narrative_path.read_text(encoding="utf-8"),
                )
            )

        for run_path in _numbered_run_directories(candidate_dir):
            run_parts: list[str] = []
            for relative_path, language in (
                (Path("final_info.json"), "json"),
                (Path("report/report.md"), None),
                (Path("traceback.log"), "text"),
            ):
                source_path = run_path / relative_path
                if source_path.is_file():
                    run_parts.append(
                        _render_source(
                            title=relative_path.as_posix(),
                            source=source_path.relative_to(launch_dir),
                            content=source_path.read_text(
                                encoding="utf-8", errors="replace"
                            ),
                            language=language,
                            heading_level=3,
                        )
                    )
            if run_parts:
                experiment_parts.extend([f"## {run_path.name}", "", *run_parts])

    (raw_materials_dir / "experimental_log.md").write_text(
        "\n".join(experiment_parts).rstrip() + "\n",
        encoding="utf-8",
    )


def _render_source(
    *,
    title: str,
    source: Path,
    content: str,
    language: str | None = None,
    heading_level: int = 2,
) -> str:
    parts = [f"{'#' * heading_level} {title}", "", f"Source: `{source.as_posix()}`", ""]
    if language:
        parts.extend([f"```{language}", content.rstrip(), "```", ""])
    else:
        parts.extend([content.rstrip(), ""])
    return "\n".join(parts).rstrip()


def _numbered_run_directories(candidate_dir: Path) -> list[Path]:
    numbered: list[tuple[int, Path]] = []
    for path in candidate_dir.iterdir():
        match = re.fullmatch(r"run_(\d+)", path.name)
        if path.is_dir() and match:
            numbered.append((int(match.group(1)), path))
    return [path for _, path in sorted(numbered)]


def _resolve_catalog_path(internagent_config: dict[str, Any]) -> Path:
    raw_path = internagent_config.get("model_catalog_path")
    if raw_path is None:
        raw_path = Path(__file__).resolve().parents[2] / "config" / "model_catalog.yaml"
    path = Path(str(raw_path)).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    if not path.is_file():
        _configuration_error(f"model catalog does not exist: {path}")
    return path.resolve()


def _validate_paper_models(
    runtime: UnifiedModelRuntime, paper_config: PaperOrchestraConfig
) -> None:
    del paper_config
    runtime.catalog.resolve_model(runtime.catalog.active_text_model, capability="text")
    runtime.catalog.binding_for("vision")
    runtime.catalog.binding_for("image_generation")


def _write_runtime_config(
    *,
    run_dir: Path,
    catalog_path: Path,
    paper_config: PaperOrchestraConfig,
    runtime: UnifiedModelRuntime,
) -> Path:
    runtime_config = {
        "catalog_path": str(catalog_path),
        "models": {
            "writer": runtime.catalog.active_text_model,
            "reflection": runtime.catalog.active_text_model,
            "plotting": runtime.catalog.active_text_model,
            "image": runtime.catalog.binding_for("image_generation").canonical_id,
        },
    }
    path = run_dir / "internagent_runtime.json"
    path.write_text(
        json.dumps(runtime_config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _run_vendored_cli(
    *,
    run_dir: Path,
    paper_config: PaperOrchestraConfig,
    runtime_config_path: Path,
) -> subprocess.CompletedProcess[Any]:
    runtime_config = json.loads(runtime_config_path.read_text(encoding="utf-8"))
    configured_models = runtime_config.get("models", {})
    if not isinstance(configured_models, dict):
        raise ValueError("PaperOrchestra runtime config models must be a mapping")
    writer_model = str(configured_models["writer"])
    reflection_model = str(configured_models["reflection"])
    plotting_model = str(configured_models["plotting"])
    image_model = str(configured_models["image"])
    command = [
        sys.executable,
        str(paper_config.vendor_root / "paper_writing_cli.py"),
        "--raw_materials_dir",
        str(run_dir / "raw_materials"),
        "--output_dir",
        str(run_dir),
        "--latex_template_dir",
        str(paper_config.template_dir),
        "--idea_filename",
        "idea_sparse.md",
        "--experimental_log_filename",
        "experimental_log.md",
        "--writer_model_name",
        writer_model,
        "--reflection_model_name",
        reflection_model,
        "--use_plotting",
        "true" if paper_config.use_plotting else "false",
        "--plotting_model_name",
        plotting_model,
        "--image_model_name",
        image_model,
        "--plotting_max_critic_rounds",
        str(paper_config.plotting_max_critic_rounds),
    ]
    if paper_config.research_cutoff:
        command.extend(["--research_cutoff", paper_config.research_cutoff])

    environment = os.environ.copy()
    repository_root = Path(__file__).resolve().parents[2]
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        item
        for item in (
            str(paper_config.vendor_root),
            str(repository_root),
            existing_pythonpath,
        )
        if item
    )
    environment["PAPER_ORCHESTRA_CATALOG_PATH"] = str(
        runtime_config["catalog_path"]
    )
    environment["PYTHONUNBUFFERED"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["MPLBACKEND"] = "Agg"
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    try:
        with (
            stdout_path.open("w", encoding="utf-8") as stdout_file,
            stderr_path.open("w", encoding="utf-8") as stderr_file,
        ):
            process = subprocess.Popen(
                command,
                cwd=run_dir,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            if process.stdout is None or process.stderr is None:
                raise RuntimeError(
                    "Unable to capture vendored PaperOrchestra output"
                )
            readers = (
                threading.Thread(
                    target=_tee_child_stream,
                    args=(process.stdout, stdout_file, sys.stdout),
                ),
                threading.Thread(
                    target=_tee_child_stream,
                    args=(process.stderr, stderr_file, sys.stderr),
                ),
            )
            for reader in readers:
                reader.start()
            returncode = process.wait()
            for reader in readers:
                reader.join()
            return subprocess.CompletedProcess(command, returncode)
    except OSError as error:
        raise PaperOrchestraStageError(
            stage="vendored_paper_orchestra",
            code="upstream_process_start_failed",
            message=str(error),
            log_path=str(stderr_path),
        ) from error


def _tee_child_stream(
    source: TextIO, log_file: TextIO, terminal: TextIO
) -> None:
    """Persist one child stream while forwarding it to the invoking terminal.

    A detached terminal cannot block log capture or child stream draining.
    """

    try:
        for line in source:
            log_file.write(line)
            log_file.flush()
            try:
                terminal.write(line)
                terminal.flush()
            except (OSError, ValueError):
                pass
    finally:
        source.close()


def _existing_result(run_dir: Path) -> PaperOrchestraRunResult | None:
    if not _final_outputs_are_valid(run_dir):
        return None
    return _successful_result(run_dir)


def _successful_result(
    run_dir: Path, *, warnings: tuple[str, ...] = ()
) -> PaperOrchestraRunResult:
    return PaperOrchestraRunResult(
        paper_orchestra_run_id=PAPER_ORCHESTRA_RUN_ID,
        run_dir=run_dir,
        final_pdf=run_dir / FINAL_PDF_RELATIVE_PATH,
        final_tex=run_dir / FINAL_TEX_RELATIVE_PATH,
        warnings=warnings,
        error=None,
    )


def _final_outputs_are_valid(run_dir: Path) -> bool:
    tex_path = run_dir / FINAL_TEX_RELATIVE_PATH
    pdf_path = run_dir / FINAL_PDF_RELATIVE_PATH
    try:
        tex_valid = tex_path.is_file() and bool(
            tex_path.read_text(encoding="utf-8").strip()
        )
        pdf = pdf_path.read_bytes()
    except OSError:
        return False
    return bool(
        tex_valid
        and len(pdf) > 8
        and pdf.startswith(b"%PDF-")
        and pdf.rstrip().endswith(b"%%EOF")
    )


def _log_tail(path: Path, *, line_count: int = 20) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "no stderr log available"
    tail = " | ".join(lines[-line_count:]).strip()
    return tail or "stderr was empty"


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        _input_error(f"cannot read {path.name}: {error}")
    if not isinstance(data, dict):
        _input_error(f"{path.name} must contain a JSON object")
    return data


def _input_error(message: str) -> None:
    raise PaperOrchestraStageError(
        stage="validate_launch",
        code="invalid_discovery_launch",
        message=message,
    )


def _configuration_error(message: str) -> None:
    raise PaperOrchestraStageError(
        stage="paper_orchestra_adapter",
        code="invalid_model_catalog",
        message=message,
    )


def _error_result(
    run_dir: Path, error: PaperOrchestraError
) -> PaperOrchestraRunResult:
    return PaperOrchestraRunResult(
        paper_orchestra_run_id=PAPER_ORCHESTRA_RUN_ID,
        run_dir=run_dir,
        final_pdf=None,
        final_tex=None,
        warnings=(),
        error=error,
    )
