from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any, Iterator

from .candidate_selection import select_candidate
from .checkpoint import PaperOrchestraCheckpoint
from .config import load_paper_config
from .data_types import (
    PaperOrchestraError,
    PaperOrchestraRunResult,
    PaperOrchestraStageError,
)
from .evidence import prepare_launch_evidence
from .image_generation import EnvironmentImageGenerator
from .material_ingestion import ingest_research_draft
from .pipeline import (
    FINAL_PDF_RELATIVE_PATH,
    FINAL_TEX_RELATIVE_PATH,
    run_writing_pipeline,
)
from .utils.pdf_utils import is_openable_pdf


PAPER_ORCHESTRA_STAGE_IDS = (
    "validate_launch",
    "optional_candidate_selection",
    "ingest_research_draft",
    "prepare_launch_evidence",
    "prepare_latex_workspace",
    "generate_outline",
    "generate_figures",
    "write_introduction_and_related_work",
    "write_remaining_sections",
    "compile_initial_draft",
    "refine_content",
    "review_layout_and_optionally_correct",
    "compile_final",
    "validate_final_outputs",
)


async def run_paper_orchestra(
    *,
    launch_dir: Path,
    internagent_config: dict[str, Any],
    paper_config_path: Path,
    paper_orchestra_run_id: str | None = None,
) -> PaperOrchestraRunResult:
    """Start or resume the PaperOrchestra Run for the current Draft Handoff."""

    launch_dir = launch_dir.resolve()
    try:
        summary = _validate_launch(launch_dir)
        run_id = paper_orchestra_run_id or _automatic_run_id(summary)
        _validate_run_id(run_id)
        paper_config = load_paper_config(paper_config_path)
    except PaperOrchestraStageError as error:
        run_id = paper_orchestra_run_id or "unresolved"
        return _error_result(
            run_id,
            launch_dir / "paper_orchestra_runs" / run_id,
            error.error,
        )

    run_dir = launch_dir / "paper_orchestra_runs" / run_id
    existing = _existing_result(run_dir, run_id)
    if existing is not None:
        return existing

    try:
        with _writer_lock(run_dir):
            checkpoint = PaperOrchestraCheckpoint.open(
                run_dir=run_dir,
                paper_orchestra_run_id=run_id,
                launch_id=launch_dir.name,
                resolved_config=paper_config.to_dict(),
                model_identity=_model_identity(internagent_config),
                stage_ids=PAPER_ORCHESTRA_STAGE_IDS,
            )

            async def validate_launch_stage() -> None:
                _validate_launch(launch_dir)

            await checkpoint.run_stage("validate_launch", validate_launch_stage)

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

            selection_holder: dict[str, Any] = {}

            async def choose_candidate_when_available() -> None:
                try:
                    selection_holder.update(
                        await _select_candidate_with_model_fallback(
                            launch_dir=launch_dir,
                            run_dir=run_dir,
                            get_model=get_model,
                        )
                    )
                except Exception:
                    # Terminal Candidate Selection is useful context, not a
                    # prerequisite for constructing a paper from the Draft.
                    # Keep cancellation signals (BaseException subclasses)
                    # intact while treating every ordinary selection failure
                    # as an unavailable optional input.
                    return

            selection_path = run_dir / "candidate_selection.json"
            await checkpoint.run_stage(
                "optional_candidate_selection", choose_candidate_when_available
            )
            selection = (
                _read_json_object(selection_path)
                if selection_path.is_file()
                else selection_holder or None
            )

            shared_model = get_model()
            bind_checkpoint = getattr(shared_model, "bind_response_checkpoint", None)
            checkpoint_context = (
                bind_checkpoint(checkpoint)
                if callable(bind_checkpoint)
                else nullcontext()
            )
            with checkpoint_context:
                materials_path = run_dir / "working_materials" / "paper_materials.md"

                async def ingest() -> None:
                    await ingest_research_draft(
                        draft_path=launch_dir / "manuscript" / "draft.md",
                        launch_dir=launch_dir,
                        output_dir=run_dir / "working_materials",
                        model=shared_model,
                        max_batch_chars=paper_config.draft_batch_max_chars,
                    )

                await checkpoint.run_stage(
                    "ingest_research_draft",
                    ingest,
                    outputs=("working_materials/paper_materials.md",),
                )

                evidence_dir = run_dir / "evidence"

                async def prepare_evidence() -> None:
                    prepare_launch_evidence(
                        launch_dir=launch_dir, output_dir=evidence_dir
                    )

                await checkpoint.run_stage(
                    "prepare_launch_evidence",
                    prepare_evidence,
                    outputs=(
                        "evidence/references.bib",
                        "evidence/citation_map.json",
                        "evidence/figures/info.json",
                    ),
                )

                image_generator = EnvironmentImageGenerator(
                    config=paper_config.image_generation
                )
                pipeline_result = await run_writing_pipeline(
                    run_dir=run_dir,
                    materials_path=materials_path,
                    evidence_dir=evidence_dir,
                    template_dir=paper_config.template_dir,
                    candidate_selection=selection,
                    paper_date=str(checkpoint.manifest["created_at"])[:10],
                    model=shared_model,
                    image_generator=image_generator,
                    plotting_max_critic_rounds=paper_config.plotting_max_critic_rounds,
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
            return PaperOrchestraRunResult(
                paper_orchestra_run_id=run_id,
                run_dir=run_dir,
                final_pdf=pipeline_result.final_pdf,
                final_tex=pipeline_result.final_tex,
                warnings=pipeline_result.warnings,
                error=None,
            )
    except PaperOrchestraStageError as error:
        return _error_result(run_id, run_dir, error.error)
    except Exception as error:
        return _error_result(
            run_id,
            run_dir,
            PaperOrchestraError(
                stage="paper_orchestra_service",
                code="unexpected_paper_orchestra_error",
                message=str(error),
            ),
        )


async def _select_candidate_with_model_fallback(
    *, launch_dir: Path, run_dir: Path, get_model: Any
) -> dict[str, Any]:
    try:
        return await select_candidate(
            launch_dir=launch_dir, run_dir=run_dir, model=None
        )
    except PaperOrchestraStageError as error:
        if error.code != "criterion_inference_requires_model":
            raise
    return await select_candidate(
        launch_dir=launch_dir, run_dir=run_dir, model=get_model()
    )


def _validate_launch(launch_dir: Path) -> dict[str, Any]:
    if not launch_dir.is_dir():
        _input_error(f"Discovery Launch directory does not exist: {launch_dir}")
    draft_path = launch_dir / "manuscript" / "draft.md"
    if not draft_path.is_file():
        _input_error(f"Research Draft does not exist: {draft_path}")
    summary = _read_json_object(launch_dir / "discovery_summary.json")
    rounds = summary.get("rounds")
    if not isinstance(rounds, list) or not rounds:
        _input_error("discovery_summary.json must contain non-empty rounds")
    return summary


def _automatic_run_id(summary: dict[str, Any]) -> str:
    rounds = summary.get("rounds", [])
    completed = [
        item.get("round")
        for item in rounds
        if isinstance(item, dict)
        and isinstance(item.get("round"), int)
        and not isinstance(item.get("round"), bool)
    ]
    if not completed:
        _input_error("Discovery Launch contains no completed round number")
    return f"round_{max(completed):04d}"


def _validate_run_id(run_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run_id):
        raise PaperOrchestraStageError(
            stage="validate_launch",
            code="invalid_paper_orchestra_run_id",
            message="PaperOrchestra Run ID contains unsafe path characters",
        )


def _existing_result(
    run_dir: Path, run_id: str
) -> PaperOrchestraRunResult | None:
    manifest_path = run_dir / "paper_orchestra_run.json"
    if not manifest_path.is_file():
        return None
    manifest = _read_json_object(manifest_path)
    if not PaperOrchestraCheckpoint.recorded_outputs_are_valid(
        run_dir=run_dir, manifest=manifest
    ):
        return None
    if not PaperOrchestraCheckpoint.final_outputs_match(
        run_dir=run_dir, manifest=manifest
    ):
        return None
    final_pdf = run_dir / FINAL_PDF_RELATIVE_PATH
    final_tex = run_dir / FINAL_TEX_RELATIVE_PATH
    if not _final_outputs_are_valid(run_dir):
        return None
    return PaperOrchestraRunResult(
        paper_orchestra_run_id=run_id,
        run_dir=run_dir,
        final_pdf=final_pdf,
        final_tex=final_tex,
        warnings=tuple(manifest.get("warnings", [])),
        error=None,
    )


def _final_outputs_are_valid(run_dir: Path) -> bool:
    final_pdf = run_dir / FINAL_PDF_RELATIVE_PATH
    final_tex = run_dir / FINAL_TEX_RELATIVE_PATH
    try:
        return (
            final_tex.is_file()
            and bool(final_tex.read_text(encoding="utf-8").strip())
            and is_openable_pdf(final_pdf)
        )
    except OSError:
        return False


@contextmanager
def _writer_lock(run_dir: Path) -> Iterator[None]:
    run_dir.mkdir(parents=True, exist_ok=True)
    lock_path = run_dir / ".writer.lock"
    if lock_path.exists() and not _lock_owner_is_alive(lock_path):
        lock_path.unlink(missing_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise PaperOrchestraStageError(
            stage="paper_orchestra_service",
            code="concurrent_paper_orchestra_writer",
            message=f"another writer already owns PaperOrchestra Run {run_dir.name}",
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


def _model_identity(config: dict[str, Any]) -> dict[str, Any]:
    models = config.get("models", {}) if isinstance(config, dict) else {}
    models = models if isinstance(models, dict) else {}
    provider = models.get("default_provider", "openai")
    provider_config = models.get(provider, {})
    provider_config = provider_config if isinstance(provider_config, dict) else {}
    return {"provider": provider, "name": provider_config.get("model_name")}


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


def _error_result(
    run_id: str, run_dir: Path, error: PaperOrchestraError
) -> PaperOrchestraRunResult:
    return PaperOrchestraRunResult(
        paper_orchestra_run_id=run_id,
        run_dir=run_dir,
        final_pdf=None,
        final_tex=None,
        warnings=(),
        error=error,
    )
