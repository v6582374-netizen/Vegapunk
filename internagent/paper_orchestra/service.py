from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any, Iterator

from .artifact_linker import link_selected_artifacts
from .candidate_selection import load_candidate_selection, select_candidate
from .checkpoint import DossierCheckpoint
from .config import load_paper_config
from .data_types import (
    DossierError,
    DossierRunResult,
    DossierStageError,
    LinkedArtifacts,
)
from .pipeline import (
    FINAL_PDF_RELATIVE_PATH,
    FINAL_TEX_RELATIVE_PATH,
    run_writing_pipeline,
)
from .raw_materials import (
    RAW_MATERIAL_CHECKPOINT_OUTPUTS,
    prepare_raw_materials,
    validate_raw_materials,
)
from .utils.pdf_utils import is_openable_pdf


DOSSIER_STAGE_IDS = (
    "validate_launch",
    "terminal_candidate_selection",
    "link_selected_artifacts",
    "prepare_raw_materials",
    "prepare_latex_workspace",
    "generate_outline",
    "write_introduction_and_related_work",
    "write_remaining_sections",
    "compile_initial_draft",
    "refine_content",
    "review_layout_and_optionally_correct",
    "compile_final",
    "validate_final_outputs_and_disclosures",
)


async def run_dossier(
    *,
    launch_dir: Path,
    internagent_config: dict[str, Any],
    paper_config_path: Path,
    dossier_run_id: str = "primary",
) -> DossierRunResult:
    launch_dir = launch_dir.resolve()
    run_dir = launch_dir / "dossier_runs" / dossier_run_id
    try:
        paper_config = load_paper_config(paper_config_path)
    except DossierStageError as error:
        return _failed_result(dossier_run_id, run_dir, error.error)
    if not paper_config.enabled:
        return DossierRunResult(
            dossier_run_id=dossier_run_id,
            status="succeeded",
            run_dir=run_dir,
            final_pdf=None,
            final_tex=None,
            warnings=("dossier_disabled_by_config",),
            error=None,
        )
    try:
        _validate_run_id(dossier_run_id)
    except DossierStageError as error:
        return _failed_result(dossier_run_id, run_dir, error.error)

    existing = _existing_success_result(launch_dir, run_dir, dossier_run_id)
    if existing is not None:
        return existing

    checkpoint: DossierCheckpoint | None = None
    try:
        with _writer_lock(run_dir):
            checkpoint = DossierCheckpoint.open(
                run_dir=run_dir,
                dossier_run_id=dossier_run_id,
                launch_id=launch_dir.name,
                resolved_config=paper_config.to_dict(),
                model_identity=_model_identity(internagent_config),
                stage_ids=DOSSIER_STAGE_IDS,
            )
            if checkpoint.stage_succeeded("prepare_raw_materials"):
                try:
                    validate_raw_materials(run_dir / "raw_materials")
                except DossierStageError:
                    checkpoint.reset_from_stage("prepare_raw_materials")
            if checkpoint.stage_succeeded(
                "compile_final"
            ) and not _final_outputs_are_valid(
                run_dir, manifest=checkpoint.manifest
            ):
                checkpoint.reset_from_stage("compile_final")
            summary_holder: dict[str, Any] = {}

            async def validate_launch() -> None:
                summary_holder.update(_validate_launch(launch_dir, run_dir))

            await checkpoint.run_stage("validate_launch", validate_launch)
            if not summary_holder:
                summary_holder.update(_read_json_object(launch_dir / "discovery_summary.json"))

            model: Any | None = None

            def get_model() -> Any:
                nonlocal model
                if model is None:
                    from internagent.mas.models.model_factory import ModelFactory

                    model = ModelFactory.create_model_for_agent(
                        "paper_orchestra",
                        {
                            "model_provider": "openai",
                            "temperature": 0,
                            "_global_config": internagent_config,
                        },
                    )
                return model

            async def choose_candidate() -> None:
                try:
                    await select_candidate(
                        launch_dir=launch_dir,
                        run_dir=run_dir,
                        model=None,
                    )
                except DossierStageError as error:
                    if error.code != "criterion_inference_requires_model":
                        raise
                    await select_candidate(
                        launch_dir=launch_dir,
                        run_dir=run_dir,
                        model=get_model(),
                    )

            await checkpoint.run_stage(
                "terminal_candidate_selection",
                choose_candidate,
                outputs=("candidate_selection.json",),
                immutable_outputs=True,
            )
            selection = load_candidate_selection(
                launch_dir=launch_dir, run_dir=run_dir
            )

            linked_holder: list[LinkedArtifacts] = []

            async def link_artifacts() -> None:
                linked_holder.append(
                    link_selected_artifacts(
                        launch_dir=launch_dir,
                        selection=selection,
                    )
                )

            await checkpoint.run_stage("link_selected_artifacts", link_artifacts)
            linked = linked_holder[0] if linked_holder else link_selected_artifacts(
                launch_dir=launch_dir,
                selection=selection,
            )

            raw_materials_dir = run_dir / "raw_materials"

            async def render_materials() -> None:
                prepare_raw_materials(linked=linked, output_dir=raw_materials_dir)

            await checkpoint.run_stage(
                "prepare_raw_materials",
                render_materials,
                outputs=RAW_MATERIAL_CHECKPOINT_OUTPUTS,
            )

            shared_model = get_model()
            bind_checkpoint = getattr(
                shared_model, "bind_response_checkpoint", None
            )
            checkpoint_context = (
                bind_checkpoint(checkpoint)
                if callable(bind_checkpoint)
                else nullcontext()
            )
            with checkpoint_context:
                pipeline_result = await run_writing_pipeline(
                    run_dir=run_dir,
                    raw_materials_dir=raw_materials_dir,
                    template_dir=paper_config.template_dir,
                    candidate_selection=selection,
                    paper_title=linked.selected_method["title"],
                    paper_date=str(checkpoint.manifest["created_at"])[:10],
                    model=shared_model,
                    max_content_refinement_iterations=(
                        paper_config.max_content_refinement_iterations
                    ),
                    max_format_correction_iterations=(
                        paper_config.max_format_correction_iterations
                    ),
                    layout_review_enabled=paper_config.layout_review_enabled,
                    checkpoint=checkpoint,
                )
            checkpoint.complete(
                final_pdf=FINAL_PDF_RELATIVE_PATH.as_posix(),
                final_tex=FINAL_TEX_RELATIVE_PATH.as_posix(),
                warnings=pipeline_result.warnings,
            )
            return DossierRunResult(
                dossier_run_id=dossier_run_id,
                status="succeeded",
                run_dir=run_dir,
                final_pdf=pipeline_result.final_pdf,
                final_tex=pipeline_result.final_tex,
                warnings=pipeline_result.warnings,
                error=None,
            )
    except DossierStageError as error:
        if checkpoint is not None and checkpoint.manifest.get("status") != "failed":
            checkpoint.fail(error)
        return _failed_result(dossier_run_id, run_dir, error.error)
    except Exception as error:
        dossier_error = DossierError(
            stage="dossier_service",
            code="unexpected_dossier_error",
            message=str(error),
            log_path=None,
        )
        if checkpoint is not None:
            checkpoint.fail(
                DossierStageError(
                    stage=dossier_error.stage,
                    code=dossier_error.code,
                    message=dossier_error.message,
                )
            )
        return _failed_result(dossier_run_id, run_dir, dossier_error)


def _validate_launch(launch_dir: Path, run_dir: Path) -> dict[str, Any]:
    if not launch_dir.is_dir():
        _input_error(f"Discovery Launch directory does not exist: {launch_dir}")
    summary = _read_json_object(launch_dir / "discovery_summary.json")
    if summary.get("mode") != "experiment":
        _input_error("Dossier generation requires an experiment-mode Discovery Launch")
    rounds = summary.get("rounds")
    if not isinstance(rounds, list) or not rounds:
        _input_error("discovery_summary.json must contain non-empty rounds")
    for round_data in rounds:
        if not isinstance(round_data, dict):
            _input_error("each Discovery Round must be an object")
        if isinstance(round_data.get("round"), bool) or not isinstance(
            round_data.get("round"), int
        ):
            _input_error("each Discovery Round must have an integer round")
        if not isinstance(round_data.get("session_id"), str) or not round_data[
            "session_id"
        ]:
            _input_error("each Discovery Round must have a session_id")
        results = round_data.get("results")
        if not isinstance(results, list):
            _input_error("each Discovery Round must have a results list")
        for result in results:
            if not isinstance(result, dict) or not isinstance(result.get("success"), bool):
                _input_error("each result must have a boolean success field")
            if not isinstance(result.get("idea_name"), str) or not result["idea_name"]:
                _input_error("each result must have a non-empty idea_name")
            if result["success"] and (
                not isinstance(result.get("folder_name"), str)
                or not result["folder_name"]
            ):
                _input_error("each successful result must have a folder_name")
    launch_root = launch_dir.resolve()
    if not run_dir.resolve().is_relative_to(launch_root / "dossier_runs"):
        _input_error("Dossier Run directory escapes the Discovery Launch")
    return summary


def _validate_run_id(dossier_run_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", dossier_run_id):
        raise DossierStageError(
            stage="validate_launch",
            code="invalid_dossier_run_id",
            message="Dossier Run ID contains unsafe path characters",
        )


def _model_identity(config: dict[str, Any]) -> dict[str, Any]:
    models = config.get("models", {}) if isinstance(config, dict) else {}
    models = models if isinstance(models, dict) else {}
    provider = models.get("default_provider", "openai")
    provider_config = models.get(provider, {})
    provider_config = provider_config if isinstance(provider_config, dict) else {}
    return {"provider": provider, "name": provider_config.get("model_name")}


def _existing_success_result(
    launch_dir: Path, run_dir: Path, dossier_run_id: str
) -> DossierRunResult | None:
    manifest_path = run_dir / "dossier_run.json"
    if not manifest_path.is_file():
        return None
    manifest = _read_json_object(manifest_path)
    if manifest.get("status") != "succeeded":
        return None
    if not DossierCheckpoint.recorded_outputs_are_valid(
        run_dir=run_dir, manifest=manifest
    ):
        return None
    try:
        validate_raw_materials(run_dir / "raw_materials")
    except DossierStageError:
        return None
    try:
        load_candidate_selection(launch_dir=launch_dir, run_dir=run_dir)
    except (DossierStageError, OSError, ValueError, json.JSONDecodeError):
        return None
    final_pdf = run_dir / FINAL_PDF_RELATIVE_PATH
    final_tex = run_dir / FINAL_TEX_RELATIVE_PATH
    if not _final_outputs_are_valid(run_dir, manifest=manifest):
        return None
    return DossierRunResult(
        dossier_run_id=dossier_run_id,
        status="succeeded",
        run_dir=run_dir,
        final_pdf=final_pdf,
        final_tex=final_tex,
        warnings=tuple(manifest.get("warnings", [])),
        error=None,
    )


def _final_outputs_are_valid(
    run_dir: Path, *, manifest: dict[str, Any] | None = None
) -> bool:
    final_pdf = run_dir / FINAL_PDF_RELATIVE_PATH
    final_tex = run_dir / FINAL_TEX_RELATIVE_PATH
    try:
        tex_is_valid = final_tex.is_file() and bool(
            final_tex.read_text(encoding="utf-8").strip()
        )
    except OSError:
        return False
    if not tex_is_valid or not is_openable_pdf(final_pdf):
        return False
    if manifest is not None and manifest.get("status") == "succeeded":
        return DossierCheckpoint.final_outputs_match(
            run_dir=run_dir, manifest=manifest
        )
    return True


@contextmanager
def _writer_lock(run_dir: Path) -> Iterator[None]:
    run_dir.mkdir(parents=True, exist_ok=True)
    lock_path = run_dir / ".writer.lock"
    if lock_path.exists() and not _lock_owner_is_alive(lock_path):
        lock_path.unlink(missing_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise DossierStageError(
            stage="dossier_service",
            code="concurrent_dossier_writer",
            message=f"another writer already owns Dossier Run {run_dir.name}",
        ) from error
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.close(descriptor)
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _lock_owner_is_alive(lock_path: Path) -> bool:
    try:
        pid = int(lock_path.read_text(encoding="ascii").strip())
        os.kill(pid, 0)
    except (ValueError, OSError):
        return False
    return True


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        _input_error(f"cannot read {path.name}: {error}")
    if not isinstance(data, dict):
        _input_error(f"{path.name} must contain a JSON object")
    return data


def _input_error(message: str) -> None:
    raise DossierStageError(
        stage="validate_launch",
        code="invalid_discovery_launch",
        message=message,
    )


def _failed_result(
    dossier_run_id: str, run_dir: Path, error: DossierError
) -> DossierRunResult:
    return DossierRunResult(
        dossier_run_id=dossier_run_id,
        status="failed",
        run_dir=run_dir,
        final_pdf=None,
        final_tex=None,
        warnings=(),
        error=error,
    )
