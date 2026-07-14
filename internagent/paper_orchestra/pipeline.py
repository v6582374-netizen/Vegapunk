from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

from internagent.mas.models.base_model import BaseModel

from .checkpoint import PaperOrchestraCheckpoint
from .data_types import PaperOrchestraStageError, PipelineResult
from .methods.agents.content_refinement_agent import ContentRefinementAgent
from .methods.agents.literature_review_agent import LiteratureReviewAgent
from .methods.agents.outline_agent import OutlineAgent
from .methods.agents.plotting_agent import PlottingAgent
from .methods.agents.section_writing_agent import SectionWritingAgent
from .utils.common_utils import validate_citation_keys, validate_narrative_contract
from .utils.pdf_utils import (
    compile_latex,
    extract_pdf_text,
    preflight_tex_toolchain,
    render_pdf_pages,
)


FINAL_TEX_RELATIVE_PATH = Path("latex_writeup/final_refined_paper.tex")
FINAL_PDF_RELATIVE_PATH = Path("final_paper.pdf")


async def run_writing_pipeline(
    *,
    run_dir: Path,
    materials_path: Path,
    evidence_dir: Path,
    template_dir: Path,
    candidate_selection: dict[str, Any] | None,
    model: BaseModel,
    image_generator: Any | None,
    plotting_max_critic_rounds: int,
    max_content_refinement_iterations: int,
    max_format_correction_iterations: int,
    layout_review_enabled: bool,
    paper_date: str | None = None,
    compile_document: Callable[..., Path] = compile_latex,
    extract_text: Callable[[Path], str] = extract_pdf_text,
    render_pages: Callable[[Path, Path], list[Path]] = render_pdf_pages,
    checkpoint: PaperOrchestraCheckpoint | None = None,
) -> PipelineResult:
    """Construct, illustrate, review, and compile one publication Paper."""

    workspace = run_dir / "latex_writeup"
    template_path = template_dir / "template.tex"
    guidelines_path = template_dir / "guidelines.md"
    citation_map_path = evidence_dir / "citation_map.json"
    evidence_figures_dir = evidence_dir / "figures"
    figures_dir = workspace / "figures"
    figures_info_path = figures_dir / "info.json"
    logs_dir = workspace / "logs"

    async def prepare_workspace() -> None:
        preflight_tex_toolchain()
        workspace.mkdir(parents=True, exist_ok=True)
        shutil.copy2(evidence_dir / "references.bib", workspace / "references.bib")
        if evidence_figures_dir.is_dir():
            shutil.copytree(evidence_figures_dir, figures_dir, dirs_exist_ok=True)
        figures_dir.mkdir(parents=True, exist_ok=True)
        if not figures_info_path.is_file():
            figures_info_path.write_text("[]\n", encoding="utf-8")

    await _run_stage(
        checkpoint,
        "prepare_latex_workspace",
        prepare_workspace,
        outputs=_relative_outputs(
            run_dir,
            workspace / "references.bib",
            figures_info_path,
        ),
    )

    outline_path = run_dir / "outline.json"
    outline_agent = OutlineAgent(model=model)

    async def generate_outline() -> None:
        await outline_agent.run(
            materials_path=materials_path,
            latex_template_file=template_path,
            guidelines_file=guidelines_path,
            candidate_selection=candidate_selection,
            output_path=outline_path,
        )

    await _run_stage(
        checkpoint,
        "generate_outline",
        generate_outline,
        outputs=_relative_outputs(run_dir, outline_path),
    )
    outline = _read_json_object(outline_path)
    paper_title = outline.get("paper_title")
    if not isinstance(paper_title, str) or not paper_title.strip():
        raise PaperOrchestraStageError(
            stage="generate_outline",
            code="invalid_model_output",
            message="outline.json contains no paper_title",
        )

    plotting_agent = PlottingAgent(
        model=model,
        image_generator=image_generator,
        max_critic_rounds=plotting_max_critic_rounds,
    )

    async def generate_figures() -> None:
        await plotting_agent.run(
            outline_path=outline_path,
            materials_path=materials_path,
            figures_dir=figures_dir,
            existing_info_path=figures_info_path,
        )

    await _run_stage(
        checkpoint,
        "generate_figures",
        generate_figures,
        outputs=_relative_outputs(run_dir, figures_info_path),
    )

    literature_path = workspace / "literature_draft.tex"
    literature_agent = LiteratureReviewAgent(model=model)

    async def write_literature() -> None:
        await literature_agent.run(
            outline_path=outline_path,
            materials_path=materials_path,
            template_path=template_path,
            citation_map_path=citation_map_path,
            guidelines_path=guidelines_path,
            output_path=literature_path,
        )

    await _run_stage(
        checkpoint,
        "write_introduction_and_related_work",
        write_literature,
        outputs=_relative_outputs(run_dir, literature_path),
    )

    raw_draft_path = workspace / "raw_draft_paper.tex"
    section_agent = SectionWritingAgent(model=model)

    async def write_sections() -> None:
        await section_agent.run(
            outline_path=outline_path,
            template_path=literature_path,
            materials_path=materials_path,
            citation_map_path=citation_map_path,
            figures_info_path=figures_info_path,
            guidelines_path=guidelines_path,
            candidate_selection=candidate_selection,
            paper_title=paper_title,
            paper_date=paper_date,
            output_path=raw_draft_path,
        )

    await _run_stage(
        checkpoint,
        "write_remaining_sections",
        write_sections,
        outputs=_relative_outputs(run_dir, raw_draft_path),
    )

    def compile_with_template(**kwargs: Any) -> Path:
        return compile_document(template_dir=template_dir, **kwargs)

    initial_pdf_path = workspace / "initial_draft.pdf"

    async def compile_initial() -> None:
        compile_with_template(
            work_dir=workspace,
            tex_path=raw_draft_path,
            output_pdf=initial_pdf_path,
            log_path=logs_dir / "compile_initial_draft.log",
            stage="compile_initial_draft",
            timeout=120,
        )

    await _run_stage(
        checkpoint,
        "compile_initial_draft",
        compile_initial,
        outputs=_relative_outputs(run_dir, initial_pdf_path),
    )

    refinement_agent = ContentRefinementAgent(model=model)
    refinement_dir = workspace / "content_refinement"
    refinement_tex_path = refinement_dir / "accepted.tex"
    refinement_pdf_path = refinement_dir / "accepted.pdf"
    refinement_review_path = refinement_dir / "accepted_review.json"

    async def refine_content() -> None:
        refinement = await refinement_agent.refine_content(
            initial_tex_path=raw_draft_path,
            initial_pdf_path=initial_pdf_path,
            materials_path=materials_path,
            citation_map_path=citation_map_path,
            guidelines_path=guidelines_path,
            paper_title=paper_title,
            paper_date=paper_date,
            work_dir=refinement_dir,
            max_iterations=max_content_refinement_iterations,
            compile_work_dir=workspace,
            compile_document=compile_with_template,
            extract_text=extract_text,
        )
        refinement_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(refinement.tex_path, refinement_tex_path)
        shutil.copy2(refinement.pdf_path, refinement_pdf_path)
        _write_json(refinement_review_path, refinement.review)

    await _run_stage(
        checkpoint,
        "refine_content",
        refine_content,
        outputs=_relative_outputs(
            run_dir,
            refinement_tex_path,
            refinement_pdf_path,
            refinement_review_path,
        ),
    )

    accepted_latex = refinement_tex_path.read_text(encoding="utf-8").rstrip("\n")
    citation_map = _read_json_object(citation_map_path)
    layout_dir = workspace / "layout_review"
    layout_tex_path = layout_dir / "accepted.tex"
    layout_pdf_path = layout_dir / "accepted.pdf"
    layout_warnings_path = layout_dir / "warnings.json"

    async def review_layout() -> None:
        layout_dir.mkdir(parents=True, exist_ok=True)
        layout_warnings: list[str] = []
        layout_latex = accepted_latex
        layout_pdf = refinement_pdf_path
        layout_source_tex = refinement_tex_path
        if layout_review_enabled:
            image_paths = render_pages(
                layout_pdf, workspace / "pdf_screenshots" / "layout_v0"
            )
            layout_review = await refinement_agent.review_layout(
                image_paths=image_paths,
                guidelines=guidelines_path.read_text(encoding="utf-8"),
            )
            _write_json(layout_dir / "review_v0.json", layout_review)
            if _has_layout_issues(layout_review):
                if max_format_correction_iterations > 0:
                    layout_latex = await refinement_agent.correct_layout(
                        latex=layout_latex,
                        layout_review=layout_review,
                        guidelines=guidelines_path.read_text(encoding="utf-8"),
                        paper_title=paper_title,
                        paper_date=paper_date,
                        citation_map=citation_map,
                    )
                    corrected_tex = workspace / "formatted_candidate_v1.tex"
                    corrected_pdf = workspace / "formatted_candidate_v1.pdf"
                    corrected_tex.write_text(layout_latex + "\n", encoding="utf-8")
                    compile_with_template(
                        work_dir=workspace,
                        tex_path=corrected_tex,
                        output_pdf=corrected_pdf,
                        log_path=logs_dir / "compile_formatted_candidate_v1.log",
                        stage="review_layout_and_optionally_correct",
                        timeout=120,
                    )
                    layout_source_tex = corrected_tex
                    layout_pdf = corrected_pdf
                    residual = await refinement_agent.review_layout(
                        image_paths=render_pages(
                            layout_pdf,
                            workspace / "pdf_screenshots" / "layout_v1",
                        ),
                        guidelines=guidelines_path.read_text(encoding="utf-8"),
                    )
                    _write_json(layout_dir / "review_v1.json", residual)
                    if _has_layout_issues(residual):
                        layout_warnings.append("layout_review_has_residual_issues")
                else:
                    layout_warnings.append("layout_review_has_residual_issues")
        else:
            layout_warnings.append("layout_review_disabled_by_config")
        shutil.copy2(layout_source_tex, layout_tex_path)
        shutil.copy2(layout_pdf, layout_pdf_path)
        _write_json(layout_warnings_path, layout_warnings)

    await _run_stage(
        checkpoint,
        "review_layout_and_optionally_correct",
        review_layout,
        outputs=_relative_outputs(
            run_dir, layout_tex_path, layout_pdf_path, layout_warnings_path
        ),
    )

    final_tex_path = run_dir / FINAL_TEX_RELATIVE_PATH
    final_pdf_path = run_dir / FINAL_PDF_RELATIVE_PATH
    final_latex = layout_tex_path.read_text(encoding="utf-8").rstrip("\n")

    async def compile_final() -> None:
        final_tex_path.write_text(final_latex + "\n", encoding="utf-8")
        compile_with_template(
            work_dir=workspace,
            tex_path=final_tex_path,
            output_pdf=final_pdf_path,
            log_path=logs_dir / "compile_final.log",
            stage="compile_final",
            timeout=120,
        )

    await _run_stage(
        checkpoint,
        "compile_final",
        compile_final,
        outputs=_relative_outputs(run_dir, final_tex_path, final_pdf_path),
    )

    async def validate_final() -> None:
        try:
            validate_narrative_contract(final_latex, paper_title, paper_date)
            validate_citation_keys(final_latex, set(citation_map))
        except ValueError as error:
            raise PaperOrchestraStageError(
                stage="validate_final_outputs",
                code="invalid_final_paper",
                message=str(error),
            ) from error
        if not extract_text(final_pdf_path).strip():
            raise PaperOrchestraStageError(
                stage="validate_final_outputs",
                code="final_pdf_invalid",
                message="final PDF contains no extractable text",
            )

    await _run_stage(checkpoint, "validate_final_outputs", validate_final)
    warnings = [
        warning
        for warning in json.loads(layout_warnings_path.read_text(encoding="utf-8"))
        if isinstance(warning, str)
    ]
    return PipelineResult(
        final_tex=final_tex_path,
        final_pdf=final_pdf_path,
        warnings=tuple(warnings),
    )


def _has_layout_issues(review: dict[str, Any]) -> bool:
    for details in review.get("figure_and_tables", {}).values():
        if isinstance(details, dict):
            issue = details.get("detected_issue")
            if isinstance(issue, str) and issue.strip().casefold() not in {"", "none"}:
                return True
    for item in review.get("other_issues", []):
        issue = item.get("detected_issue") if isinstance(item, dict) else item
        if isinstance(issue, str) and issue.strip().casefold() not in {"", "none"}:
            return True
    return False


def _read_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain an object")
    return data


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


async def _run_stage(
    checkpoint: PaperOrchestraCheckpoint | None,
    stage_id: str,
    operation: Callable[[], Any],
    *,
    outputs: tuple[str, ...] = (),
) -> Any:
    if checkpoint is None:
        result = operation()
        if hasattr(result, "__await__"):
            return await result
        return result
    return await checkpoint.run_stage(stage_id, operation, outputs=outputs)


def _relative_outputs(run_dir: Path, *paths: Path) -> tuple[str, ...]:
    return tuple(path.relative_to(run_dir).as_posix() for path in paths)
