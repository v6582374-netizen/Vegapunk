"""PaperOrchestra content/layout refinement adapted to InternAgent BaseModel."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Callable

from internagent.mas.models.base_model import BaseModel
from internagent.mas.models.runtime import (
    ImageContent,
    Message,
    ModelRunRequest,
    ReasoningConfig,
    TextContent,
)

from ...autoraters.agent_review import REVIEW_AXES, review_paper
from ...data_types import DossierStageError, RefinementResult
from ...utils.common_utils import (
    scientific_content_fingerprint,
    validate_citation_keys,
    validate_narrative_contract,
)
from ...utils.content_parsing_utils import extract_fenced_content, extract_json_response
from ...utils.pdf_utils import compile_latex, extract_pdf_text
from ..prompts.content_refinement_agent import (
    CONTENT_REFINEMENT_PROMPT,
    LAYOUT_REVIEW_PROMPT,
)


class ContentRefinementAgent:
    def __init__(self, *, model: BaseModel) -> None:
        self.model = model

    async def refine_content(
        self,
        *,
        initial_tex_path: Path,
        initial_pdf_path: Path,
        experimental_log_path: Path,
        citation_map_path: Path,
        guidelines_path: Path,
        paper_title: str,
        paper_date: str | None = None,
        work_dir: Path,
        max_iterations: int,
        compile_work_dir: Path | None = None,
        compile_document: Callable[..., Path] = compile_latex,
        extract_text: Callable[[Path], str] = extract_pdf_text,
    ) -> RefinementResult:
        work_dir.mkdir(parents=True, exist_ok=True)
        compile_work_dir = compile_work_dir or work_dir
        reviews_dir = work_dir / "peer_reviews"
        logs_dir = work_dir / "logs"
        reviews_dir.mkdir(exist_ok=True)
        citation_map = json.loads(citation_map_path.read_text(encoding="utf-8"))
        if not isinstance(citation_map, dict):
            raise DossierStageError(
                stage="refine_content",
                code="invalid_input",
                message="citation_map.json must contain an object",
            )
        experimental_log = experimental_log_path.read_text(encoding="utf-8")
        guidelines = guidelines_path.read_text(encoding="utf-8")
        current_tex_path = initial_tex_path
        current_pdf_path = initial_pdf_path
        current_latex = current_tex_path.read_text(encoding="utf-8").rstrip("\n")
        current_review = await review_paper(
            model=self.model,
            latex=current_latex,
            pdf_text=extract_text(current_pdf_path),
            experimental_log=experimental_log,
            citation_map=citation_map,
        )
        _write_json(reviews_dir / "review_v0.json", current_review)
        worklog: list[dict[str, Any]] = []

        for iteration in range(1, max_iterations + 1):
            payload = {
                "reviewer_feedback": current_review,
                "guidelines.md": guidelines,
                "experimental_log.md": experimental_log,
                "citation_map.json": citation_map,
                "paper.tex": current_latex,
            }
            response = await self.model.generate(
                prompt=json.dumps(payload, ensure_ascii=False, sort_keys=True),
                system_prompt=CONTENT_REFINEMENT_PROMPT,
                temperature=0,
                agent_role="paper_orchestra_content_refiner",
                reasoning=ReasoningConfig(mode="pro"),
                background=True,
            )
            try:
                candidate_latex = extract_fenced_content(response, "latex")
                validate_narrative_contract(candidate_latex, paper_title, paper_date)
                validate_citation_keys(candidate_latex, set(citation_map))
            except ValueError as error:
                raise DossierStageError(
                    stage="refine_content",
                    code="invalid_model_output",
                    message=str(error),
                ) from error

            candidate_tex_path = compile_work_dir / f"refined_paper_v{iteration}.tex"
            candidate_pdf_path = compile_work_dir / f"refined_paper_v{iteration}.pdf"
            candidate_tex_path.write_text(candidate_latex + "\n", encoding="utf-8")
            compile_document(
                work_dir=compile_work_dir,
                tex_path=candidate_tex_path,
                output_pdf=candidate_pdf_path,
                log_path=logs_dir / f"compile_v{iteration}.log",
                stage="refine_content",
                timeout=120,
            )
            candidate_review = await review_paper(
                model=self.model,
                latex=candidate_latex,
                pdf_text=extract_text(candidate_pdf_path),
                experimental_log=experimental_log,
                citation_map=citation_map,
            )
            _write_json(reviews_dir / f"review_v{iteration}.json", candidate_review)
            degraded_axes = _degraded_axes(current_review, candidate_review)
            accepted = not degraded_axes
            worklog.append(
                {
                    "iteration": iteration,
                    "accepted": accepted,
                    "degraded_axes": degraded_axes,
                    "overall_before": current_review["Overall"],
                    "overall_after": candidate_review["Overall"],
                }
            )
            _write_json(work_dir / "content_refinement_worklog.json", worklog)
            if not accepted:
                break
            current_tex_path = candidate_tex_path
            current_pdf_path = candidate_pdf_path
            current_latex = candidate_latex
            current_review = candidate_review

        return RefinementResult(
            tex_path=current_tex_path,
            pdf_path=current_pdf_path,
            review=current_review,
        )

    async def review_layout(
        self, *, image_paths: list[Path], guidelines: str
    ) -> dict[str, Any]:
        content = [TextContent(text=f"Guidelines:\n{guidelines}")]
        for image_path in image_paths:
            encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
            content.append(
                ImageContent(
                    image_url=f"data:image/png;base64,{encoded}",
                    detail="original",
                )
            )
        response = await self.model.run(
            ModelRunRequest(
                instructions=LAYOUT_REVIEW_PROMPT,
                input=(Message(role="user", content=tuple(content)),),
                response_format="json_object",
                temperature=0,
                reasoning=ReasoningConfig(mode="pro"),
                prompt_cache_key=self.model.make_prompt_cache_key(
                    agent_role="paper_orchestra_layout_review",
                    stable_prefix=LAYOUT_REVIEW_PROMPT,
                ),
            )
        )
        try:
            review = extract_json_response(response)
        except (ValueError, TypeError) as error:
            raise DossierStageError(
                stage="review_layout_and_optionally_correct",
                code="layout_review_failed",
                message=str(error),
            ) from error
        if not isinstance(review.get("figure_and_tables"), dict) or not isinstance(
            review.get("other_issues"), list
        ):
            raise DossierStageError(
                stage="review_layout_and_optionally_correct",
                code="layout_review_failed",
                message="layout review returned an invalid JSON shape",
            )
        return review

    async def correct_layout(
        self,
        *,
        latex: str,
        layout_review: dict[str, Any],
        guidelines: str,
        paper_title: str,
        paper_date: str | None = None,
        citation_map: dict[str, Any],
    ) -> str:
        payload = {
            "layout_review": layout_review,
            "guidelines.md": guidelines,
            "paper.tex": latex,
        }
        response = await self.model.generate(
            prompt=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            system_prompt=(
                "Fix only the reported LaTeX layout and spacing issues. Do not change "
                "scientific content, claims, data, citations, title, or authorship. "
                "Return the complete LaTeX in a latex code block."
            ),
            temperature=0,
            agent_role="paper_orchestra_layout_corrector",
        )
        try:
            corrected = extract_fenced_content(response, "latex")
            validate_narrative_contract(corrected, paper_title, paper_date)
            validate_citation_keys(corrected, set(citation_map))
            if scientific_content_fingerprint(
                corrected
            ) != scientific_content_fingerprint(latex):
                raise ValueError("layout correction changed scientific content")
        except ValueError as error:
            raise DossierStageError(
                stage="review_layout_and_optionally_correct",
                code="invalid_model_output",
                message=str(error),
            ) from error
        return corrected


def _degraded_axes(
    previous: dict[str, Any], candidate: dict[str, Any]
) -> list[str]:
    quality_axes = [axis for axis in REVIEW_AXES if axis != "Confidence"]
    return [
        axis
        for axis in quality_axes
        if float(candidate[axis]) < float(previous[axis])
    ]


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
