"""PaperOrchestra SectionWritingAgent adapted to InternAgent BaseModel."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from internagent.mas.models.base_model import BaseModel
from internagent.mas.models.runtime import ReasoningConfig

from ...data_types import DossierStageError
from ...utils.common_utils import (
    validate_citation_keys,
    validate_narrative_contract,
)
from ...utils.content_parsing_utils import extract_fenced_content
from ..prompts.section_writing_agent import SECTION_WRITING_SYSTEM_PROMPT


class SectionWritingAgent:
    def __init__(self, *, model: BaseModel) -> None:
        self.model = model

    async def run(
        self,
        *,
        outline_path: Path,
        template_path: Path,
        idea_path: Path,
        experimental_log_path: Path,
        citation_map_path: Path,
        figures_info_path: Path,
        guidelines_path: Path,
        candidate_selection: dict[str, Any],
        paper_title: str,
        paper_date: str | None = None,
        output_path: Path,
    ) -> str:
        citation_map = _read_json(citation_map_path, dict)
        figures_info = _read_json(figures_info_path, list)
        payload = {
            "outline.json": _read_json(outline_path, dict),
            "template.tex": template_path.read_text(encoding="utf-8"),
            "idea.md": idea_path.read_text(encoding="utf-8"),
            "experimental_log.md": experimental_log_path.read_text(encoding="utf-8"),
            "citation_map.json": citation_map,
            "figures/info.json": figures_info,
            "guidelines.md": guidelines_path.read_text(encoding="utf-8"),
            "candidate_selection.json": candidate_selection,
            "authoritative_title": paper_title,
            "authoritative_date": paper_date,
        }
        response = await self.model.generate(
            prompt=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            system_prompt=SECTION_WRITING_SYSTEM_PROMPT,
            temperature=0,
            agent_role="paper_orchestra_section_writer",
            reasoning=ReasoningConfig(mode="pro"),
            background=True,
            checkpoint_key="write_remaining_sections",
        )
        try:
            latex = extract_fenced_content(response, "latex")
            validate_narrative_contract(latex, paper_title, paper_date)
            validate_citation_keys(latex, set(citation_map))
            _validate_figures(latex, figures_info)
        except ValueError as error:
            raise DossierStageError(
                stage="write_remaining_sections",
                code="invalid_model_output",
                message=str(error),
            ) from error
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(latex + "\n", encoding="utf-8")
        return latex


def _read_json(path: Path, expected_type: type) -> Any:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, expected_type):
        raise DossierStageError(
            stage="write_remaining_sections",
            code="invalid_input",
            message=f"{path.name} has an invalid JSON shape",
        )
    return data


def _validate_figures(latex: str, figures_info: list[Any]) -> None:
    approved = {
        item["name"]
        for item in figures_info
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    used = {
        Path(match).name
        for match in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", latex)
    }
    unknown = sorted(used - approved)
    if unknown:
        raise ValueError(f"LaTeX contains unapproved figures: {', '.join(unknown)}")
