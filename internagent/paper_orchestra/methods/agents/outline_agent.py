"""Adapted from PaperOrchestra's OutlineAgent for InternAgent BaseModel."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from internagent.mas.models.base_model import BaseModel
from internagent.mas.models.runtime import ReasoningConfig

from ...data_types import DossierStageError
from ..prompts.outline_agent import OUTLINE_SYSTEM_PROMPT


class OutlineAgent:
    def __init__(self, *, model: BaseModel) -> None:
        self.model = model

    async def run(
        self,
        *,
        idea_file: Path,
        experimental_log_file: Path,
        latex_template_file: Path,
        guidelines_file: Path,
        candidate_selection: dict[str, Any],
        output_path: Path,
    ) -> dict[str, Any]:
        payload = {
            "idea.md": idea_file.read_text(encoding="utf-8"),
            "experimental_log.md": experimental_log_file.read_text(encoding="utf-8"),
            "template.tex": latex_template_file.read_text(encoding="utf-8"),
            "guidelines.md": guidelines_file.read_text(encoding="utf-8"),
            "candidate_selection.json": candidate_selection,
        }
        schema = {
            "type": "object",
            "properties": {
                "intro_related_work_plan": {"type": "object"},
                "section_plan": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["intro_related_work_plan", "section_plan"],
            "additionalProperties": False,
        }
        outline = await self.model.generate_json(
            prompt=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            schema=schema,
            system_prompt=OUTLINE_SYSTEM_PROMPT,
            temperature=0,
            agent_role="paper_orchestra_outline",
            reasoning=ReasoningConfig(mode="pro"),
            background=True,
            checkpoint_key="generate_outline",
        )
        if (
            not isinstance(outline, dict)
            or not isinstance(outline.get("intro_related_work_plan"), dict)
            or not isinstance(outline.get("section_plan"), list)
        ):
            raise DossierStageError(
                stage="generate_outline",
                code="invalid_model_output",
                message="OutlineAgent returned an invalid outline",
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(outline, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return outline
