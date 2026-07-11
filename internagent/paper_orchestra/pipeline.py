from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Callable

from internagent.mas.models.base_model import BaseModel

from .candidate_selection import RANDOM_SELECTION_METHODS, RANDOM_TIE_METHOD
from .checkpoint import DossierCheckpoint
from .data_types import DossierStageError, PipelineResult
from .methods.agents.content_refinement_agent import ContentRefinementAgent
from .methods.agents.literature_review_agent import LiteratureReviewAgent
from .methods.agents.outline_agent import OutlineAgent
from .methods.agents.section_writing_agent import SectionWritingAgent
from .raw_materials import RAW_MATERIAL_PATHS
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
    raw_materials_dir: Path,
    template_dir: Path,
    candidate_selection: dict[str, Any],
    paper_title: str,
    paper_date: str | None = None,
    model: BaseModel,
    max_content_refinement_iterations: int,
    max_format_correction_iterations: int,
    layout_review_enabled: bool,
    compile_document: Callable[..., Path] = compile_latex,
    extract_text: Callable[[Path], str] = extract_pdf_text,
    render_pages: Callable[[Path, Path], list[Path]] = render_pdf_pages,
    checkpoint: DossierCheckpoint | None = None,
) -> PipelineResult:
    """Run the migrated PaperOrchestra writing and review architecture."""
    workspace = run_dir / "latex_writeup"
    guidelines_path = workspace / "guidelines.md"
    template_path = workspace / "template.tex"

    async def prepare_workspace() -> None:
        preflight_tex_toolchain()
        shutil.copytree(template_dir, workspace, dirs_exist_ok=True)
        shutil.copy2(
            raw_materials_dir / RAW_MATERIAL_PATHS["references"],
            workspace / "references.bib",
        )
        raw_figures = raw_materials_dir / RAW_MATERIAL_PATHS["figures_info"].parent
        if raw_figures.is_dir():
            shutil.copytree(raw_figures, workspace / "figures", dirs_exist_ok=True)

    await _run_stage(
        checkpoint,
        "prepare_latex_workspace",
        prepare_workspace,
        outputs=_relative_outputs(run_dir, template_path, guidelines_path),
    )

    idea_path = raw_materials_dir / RAW_MATERIAL_PATHS["idea"]
    experimental_log_path = raw_materials_dir / RAW_MATERIAL_PATHS["experimental_log"]
    citation_map_path = raw_materials_dir / RAW_MATERIAL_PATHS["citation_map"]
    figures_info_path = raw_materials_dir / RAW_MATERIAL_PATHS["figures_info"]
    logs_dir = workspace / "logs"

    outline_path = run_dir / "outline.json"
    outline_agent = OutlineAgent(model=model)

    async def generate_outline() -> None:
        await outline_agent.run(
            idea_file=idea_path,
            experimental_log_file=experimental_log_path,
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

    literature_path = workspace / "literature_draft.tex"
    literature_agent = LiteratureReviewAgent(model=model)

    async def write_literature() -> None:
        await literature_agent.run(
            outline_path=outline_path,
            idea_path=idea_path,
            experimental_log_path=experimental_log_path,
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
            idea_path=idea_path,
            experimental_log_path=experimental_log_path,
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

    initial_pdf_path = workspace / "initial_draft.pdf"

    async def compile_initial() -> None:
        compile_document(
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
            experimental_log_path=experimental_log_path,
            citation_map_path=citation_map_path,
            guidelines_path=guidelines_path,
            paper_title=paper_title,
            paper_date=paper_date,
            work_dir=refinement_dir,
            max_iterations=max_content_refinement_iterations,
            compile_work_dir=workspace,
            compile_document=compile_document,
            extract_text=extract_text,
        )
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
    accepted_tex_path = refinement_tex_path
    accepted_pdf_path = refinement_pdf_path
    accepted_latex = accepted_tex_path.read_text(encoding="utf-8").rstrip("\n")
    citation_map = _read_json_object(citation_map_path)
    layout_dir = workspace / "layout_review"
    layout_tex_path = layout_dir / "accepted.tex"
    layout_pdf_path = layout_dir / "accepted.pdf"
    layout_warnings_path = layout_dir / "warnings.json"

    async def review_layout() -> None:
        layout_dir.mkdir(parents=True, exist_ok=True)
        layout_warnings: list[str] = []
        layout_latex = accepted_latex
        layout_pdf = accepted_pdf_path
        layout_source_tex = accepted_tex_path
        if layout_review_enabled:
            screenshots_dir = workspace / "pdf_screenshots" / "layout_v0"
            image_paths = render_pages(layout_pdf, screenshots_dir)
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
                    corrected_tex_path = workspace / "formatted_candidate_v1.tex"
                    corrected_pdf_path = workspace / "formatted_candidate_v1.pdf"
                    corrected_tex_path.write_text(layout_latex + "\n", encoding="utf-8")
                    compile_document(
                        work_dir=workspace,
                        tex_path=corrected_tex_path,
                        output_pdf=corrected_pdf_path,
                        log_path=logs_dir / "compile_formatted_candidate_v1.log",
                        stage="review_layout_and_optionally_correct",
                        timeout=120,
                    )
                    layout_source_tex = corrected_tex_path
                    layout_pdf = corrected_pdf_path
                    corrected_images = render_pages(
                        layout_pdf,
                        workspace / "pdf_screenshots" / "layout_v1",
                    )
                    residual_review = await refinement_agent.review_layout(
                        image_paths=corrected_images,
                        guidelines=guidelines_path.read_text(encoding="utf-8"),
                    )
                    _write_json(layout_dir / "review_v1.json", residual_review)
                    if _has_layout_issues(residual_review):
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
            run_dir,
            layout_tex_path,
            layout_pdf_path,
            layout_warnings_path,
        ),
    )
    accepted_tex_path = layout_tex_path
    accepted_pdf_path = layout_pdf_path
    accepted_latex = accepted_tex_path.read_text(encoding="utf-8").rstrip("\n")
    warnings_data = json.loads(layout_warnings_path.read_text(encoding="utf-8"))
    warnings = [warning for warning in warnings_data if isinstance(warning, str)]

    final_tex_path = run_dir / FINAL_TEX_RELATIVE_PATH
    final_tex_path.write_text(accepted_latex + "\n", encoding="utf-8")
    final_pdf_path = run_dir / FINAL_PDF_RELATIVE_PATH

    async def compile_final() -> None:
        final_tex_path.write_text(accepted_latex + "\n", encoding="utf-8")
        compile_document(
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
            validate_narrative_contract(accepted_latex, paper_title, paper_date)
            validate_citation_keys(accepted_latex, set(citation_map))
            validate_candidate_disclosures(accepted_latex, candidate_selection)
        except ValueError as error:
            raise DossierStageError(
                stage="validate_final_outputs_and_disclosures",
                code="required_disclosure_missing",
                message=str(error),
            ) from error
        if not final_tex_path.stat().st_size or not final_pdf_path.stat().st_size:
            raise DossierStageError(
                stage="validate_final_outputs_and_disclosures",
                code="final_output_missing",
                message="final LaTeX and PDF must both be non-empty",
            )
        try:
            final_pdf_text = extract_text(final_pdf_path)
        except Exception as error:
            raise DossierStageError(
                stage="validate_final_outputs_and_disclosures",
                code="final_pdf_invalid",
                message=f"final PDF cannot be opened and read: {error}",
            ) from error
        if not final_pdf_text.strip():
            raise DossierStageError(
                stage="validate_final_outputs_and_disclosures",
                code="final_pdf_invalid",
                message="final PDF contains no extractable text",
            )

    await _run_stage(
        checkpoint,
        "validate_final_outputs_and_disclosures",
        validate_final,
    )
    return PipelineResult(
        final_tex=final_tex_path,
        final_pdf=final_pdf_path,
        warnings=tuple(warnings),
    )


def _has_layout_issues(review: dict[str, Any]) -> bool:
    figure_tables = review.get("figure_and_tables", {})
    for details in figure_tables.values():
        if isinstance(details, dict):
            issue = details.get("detected_issue")
            if isinstance(issue, str) and issue.strip().casefold() not in {"", "none"}:
                return True
    for item in review.get("other_issues", []):
        issue = item.get("detected_issue") if isinstance(item, dict) else item
        if isinstance(issue, str) and issue.strip().casefold() not in {"", "none"}:
            return True
    return False


def validate_candidate_disclosures(
    latex: str, selection: dict[str, Any]
) -> None:
    """Require every exceptional candidate-selection fact in Research Process."""
    match = re.search(
        r"\\section\{研究过程\}(.*?)(?=\\section\{|\\end\{document\}|$)",
        latex,
        flags=re.DOTALL,
    )
    process = (match.group(1) if match else "").replace(r"\_", "_")
    if r"\subsection{候选选择}" not in process:
        raise ValueError("研究过程缺少候选选择小节")
    candidate_round = selection.get("paper_candidate_round", {})
    skipped_rounds = candidate_round.get("skipped_later_rounds", [])
    if skipped_rounds and (
        "回退" not in process
        or "无成功" not in process
        or any(str(number) not in process for number in skipped_rounds)
        or str(candidate_round.get("round")) not in process
    ):
        raise ValueError("研究过程缺少回退轮次或较新轮次无成功候选的披露")
    criterion = selection.get("criterion", {})
    if criterion.get("source") == "model_inference":
        primary_metric = criterion.get("primary_metric")
        direction = criterion.get("optimization_direction")
        direction_terms = {
            "minimize": ("minimize", "最小化"),
            "maximize": ("maximize", "最大化"),
        }.get(direction, (str(direction),))
        if (
            "模型的主观判断" not in process
            or not isinstance(primary_metric, str)
            or primary_metric not in process
            or not any(term in process for term in direction_terms)
        ):
            raise ValueError("研究过程缺少模型推断的主指标或优化方向披露")
        source_paths = criterion.get("source_paths", [])
        if any(
            not isinstance(source_path, str) or source_path not in process
            for source_path in source_paths
        ):
            raise ValueError("研究过程缺少模型判断的来源文本披露")
        compared = [
            (item.get("idea_name"), item.get("primary_metric_value"))
            for item in selection.get("successful_candidates", [])
            if item.get("primary_metric_value") is not None
        ]
        if any(
            not isinstance(name, str)
            or name not in process
            or str(value) not in process
            for name, value in compared
        ):
            raise ValueError("研究过程缺少模型判断所用的候选指标值")
    excluded = [
        (item.get("idea_name"), item.get("exclusion_reason"))
        for item in selection.get("successful_candidates", [])
        if item.get("exclusion_reason")
    ]
    if any(
        not isinstance(name, str)
        or name not in process
        or not isinstance(reason, str)
        or reason not in process
        for name, reason in excluded
    ):
        raise ValueError("研究过程缺少被排除候选或其指标排除原因")
    if selection.get("selection_method") in RANDOM_SELECTION_METHODS:
        pool_names = [item.get("idea_name") for item in selection.get("fallback_pool", [])]
        fallback_reason = selection.get("fallback_reason")
        selected_name = selection.get("selected_candidate", {}).get("idea_name")
        missing_tie = (
            selection.get("selection_method") == RANDOM_TIE_METHOD
            and "并列" not in process
        )
        if (
            "随机" not in process
            or missing_tie
            or not isinstance(fallback_reason, str)
            or fallback_reason not in process
            or any(name and name not in process for name in pool_names)
            or not isinstance(selected_name, str)
            or selected_name not in process
        ):
            raise ValueError("研究过程缺少随机候选池、选中者、并列事实或触发原因")


def _read_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain an object")
    return data


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


async def _run_stage(
    checkpoint: DossierCheckpoint | None,
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
