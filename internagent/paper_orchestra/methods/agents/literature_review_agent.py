"""PaperOrchestra literature writer adapted to approved InternAgent citations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from internagent.mas.models.base_model import BaseModel
from internagent.mas.models.runtime import ReasoningConfig

from ...data_types import DossierStageError
from ...utils.common_utils import validate_citation_keys
from ...utils.content_parsing_utils import extract_fenced_content
from ..prompts.literature_review_agent import LITERATURE_SYSTEM_PROMPT


class LiteratureReviewAgent:
    def __init__(self, *, model: BaseModel) -> None:
        self.model = model

    async def run(
        self,
        *,
        outline_path: Path,
        idea_path: Path,
        experimental_log_path: Path,
        template_path: Path,
        citation_map_path: Path,
        guidelines_path: Path,
        output_path: Path,
    ) -> str:
        citation_map = _read_json_object(citation_map_path)
        payload = {
            "intro_related_work_plan": _read_json_object(outline_path).get(
                "intro_related_work_plan", {}
            ),
            "idea.md": idea_path.read_text(encoding="utf-8"),
            "experimental_log.md": experimental_log_path.read_text(encoding="utf-8"),
            "template.tex": template_path.read_text(encoding="utf-8"),
            "citation_map.json": citation_map,
            "guidelines.md": guidelines_path.read_text(encoding="utf-8"),
        }
        response = await self.model.generate(
            prompt=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            system_prompt=LITERATURE_SYSTEM_PROMPT,
            temperature=0,
            agent_role="paper_orchestra_literature_writer",
            reasoning=ReasoningConfig(mode="pro"),
            background=True,
        )
        try:
            latex = extract_fenced_content(response, "latex")
        except ValueError as error:
            _fail(str(error))
        if "\\documentclass" not in latex:
            _fail("LiteratureReviewAgent did not return a complete LaTeX document")
        try:
            validate_citation_keys(latex, set(citation_map))
        except ValueError as error:
            _fail(str(error))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(latex + "\n", encoding="utf-8")
        return latex


def _read_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        _fail(f"{path.name} must contain a JSON object")
    return data


def _fail(message: str) -> None:
    raise DossierStageError(
        stage="write_introduction_and_related_work",
        code="invalid_model_output",
        message=message,
    )
