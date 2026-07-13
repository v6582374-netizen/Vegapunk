"""PaperOrchestra Agent Review adapted to InternAgent BaseModel."""

from __future__ import annotations

import json
from numbers import Real
from typing import Any

from internagent.mas.models.base_model import BaseModel
from internagent.mas.models.runtime import ReasoningConfig

from ..data_types import DossierStageError


REVIEW_AXES = (
    "Originality",
    "Quality",
    "Clarity",
    "Significance",
    "Soundness",
    "Presentation",
    "Contribution",
    "Overall",
    "Confidence",
)


async def review_paper(
    *,
    model: BaseModel,
    latex: str,
    pdf_text: str,
    experimental_log: str,
    citation_map: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "paper.tex": latex,
        "paper.pdf.txt": pdf_text,
        "experimental_log.md": experimental_log,
        "citation_map.json": citation_map,
    }
    properties: dict[str, Any] = {
        "Strengths": {"type": "array", "items": {"type": "string"}},
        "Weaknesses": {"type": "array", "items": {"type": "string"}},
        "Questions": {"type": "array", "items": {"type": "string"}},
    }
    properties.update(
        {axis: {"type": "number", "minimum": 0, "maximum": 10} for axis in REVIEW_AXES}
    )
    schema = {
        "type": "object",
        "properties": properties,
        "required": ["Strengths", "Weaknesses", "Questions", *REVIEW_AXES],
        "additionalProperties": False,
    }
    review = await model.generate_json(
        prompt=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        schema=schema,
        system_prompt=(
            "Review this Research Dossier only against its supplied evidence. "
            "Do not request or assume unrecorded experiments, facts, or citations."
        ),
        temperature=0,
        agent_role="paper_orchestra_peer_review",
        reasoning=ReasoningConfig(mode="pro"),
    )
    if not isinstance(review, dict) or any(
        isinstance(review.get(axis), bool)
        or not isinstance(review.get(axis), Real)
        for axis in REVIEW_AXES
    ):
        raise DossierStageError(
            stage="refine_content",
            code="invalid_model_output",
            message="Agent Review returned an invalid structured review",
        )
    return review
