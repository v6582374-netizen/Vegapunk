"""Evidence-grounded figure generation, visual critique, and correction."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from json_repair import repair_json

from internagent.mas.models.runtime import (
    ImageContent,
    Message,
    ModelRunRequest,
    ReasoningConfig,
    TextContent,
)

from ...data_types import PaperOrchestraStageError
from ...utils.content_parsing_utils import extract_fenced_content


PlotRenderer = Callable[[str, Path], None]


class PlottingAgent:
    def __init__(
        self,
        *,
        model: Any,
        image_generator: Any | None,
        max_critic_rounds: int,
        plot_renderer: PlotRenderer | None = None,
    ) -> None:
        self.model = model
        self.image_generator = image_generator
        self.max_critic_rounds = max_critic_rounds
        self.plot_renderer = plot_renderer or render_plot_code

    async def run(
        self,
        *,
        outline_path: Path,
        materials_path: Path,
        figures_dir: Path,
        existing_info_path: Path | None = None,
    ) -> Path:
        outline = _read_json(outline_path, dict)
        plans = outline.get("plotting_plan", [])
        if not isinstance(plans, list):
            _fail("outline plotting_plan must be an array")
        figures_dir.mkdir(parents=True, exist_ok=True)
        figures = _load_existing(existing_info_path)
        materials = materials_path.read_text(encoding="utf-8")
        for plan in plans:
            if not isinstance(plan, dict):
                _fail("each plotting plan must be an object")
            figures.append(
                await self._generate_one(
                    plan=plan,
                    materials=materials,
                    figures_dir=figures_dir,
                )
            )
        info_path = figures_dir / "info.json"
        info_path.write_text(
            json.dumps(figures, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return info_path

    async def _generate_one(
        self, *, plan: dict[str, Any], materials: str, figures_dir: Path
    ) -> dict[str, str]:
        figure_id = _safe_figure_id(plan.get("figure_id"))
        plot_type = str(plan.get("plot_type", "diagram")).casefold()
        plot_type = "plot" if plot_type in {"plot", "chart", "statistical_plot"} else "diagram"
        aspect_ratio = str(plan.get("aspect_ratio") or "16:9")
        description = await self._initial_description(
            plot_type=plot_type, plan=plan, materials=materials
        )
        image_path = figures_dir / f"{figure_id}.png"
        await self._render(
            plot_type=plot_type,
            description=description,
            materials=materials,
            aspect_ratio=aspect_ratio,
            output_path=image_path,
        )
        for round_index in range(1, self.max_critic_rounds + 1):
            revised, needs_change = await self._critique(
                plan=plan,
                description=description,
                materials=materials,
                image_path=image_path,
                round_index=round_index,
            )
            if not needs_change:
                break
            description = revised
            await self._render(
                plot_type=plot_type,
                description=description,
                materials=materials,
                aspect_ratio=aspect_ratio,
                output_path=image_path,
            )
        caption = await self.model.generate(
            prompt=json.dumps(
                {"plan": plan, "final_figure_description": description},
                ensure_ascii=False,
            ),
            system_prompt=(
                "Write one precise academic figure caption grounded only in the "
                "supplied plan and description. Do not add measurements."
            ),
            temperature=0,
            agent_role="paper_orchestra_figure_caption",
        )
        return {
            "name": image_path.name,
            "caption": caption.strip(),
            "source": "generated",
        }

    async def _initial_description(
        self, *, plot_type: str, plan: dict[str, Any], materials: str
    ) -> str:
        if plot_type == "plot":
            return str(plan.get("objective") or plan.get("title") or "")
        return (
            await self.model.generate(
                prompt=json.dumps(
                    {"plan": plan, "paper_materials.md": materials},
                    ensure_ascii=False,
                ),
                system_prompt=(
                    "Describe a precise publication-quality method or architecture "
                    "diagram using only the established method in the supplied material. "
                    "Do not invent modules, results, or citations."
                ),
                temperature=0,
                agent_role="paper_orchestra_diagram_description",
            )
        ).strip()

    async def _render(
        self,
        *,
        plot_type: str,
        description: str,
        materials: str,
        aspect_ratio: str,
        output_path: Path,
    ) -> None:
        if plot_type == "plot":
            response = await self.model.generate(
                prompt=json.dumps(
                    {
                        "paper_materials.md": materials,
                        "visual_intent": description,
                        "output_path": str(output_path),
                    },
                    ensure_ascii=False,
                ),
                system_prompt=(
                    "Return only Python code in a ```python block. Use matplotlib or "
                    "seaborn to plot only recorded data, label axes precisely, and save "
                    "the final figure to PLOT_OUTPUT_PATH. Never invent or interpolate data."
                ),
                temperature=0,
                agent_role="paper_orchestra_statistical_plot",
            )
            try:
                code = extract_fenced_content(response, "python")
            except ValueError as error:
                _fail(str(error))
            self.plot_renderer(code, output_path)
        else:
            if self.image_generator is None:
                _fail("method diagram requested without an image generator")
            image = await self.image_generator.generate(
                prompt=description, aspect_ratio=aspect_ratio
            )
            output_path.write_bytes(image)
        if not output_path.is_file() or output_path.stat().st_size == 0:
            _fail(f"figure generation produced no image: {output_path.name}")

    async def _critique(
        self,
        *,
        plan: dict[str, Any],
        description: str,
        materials: str,
        image_path: Path,
        round_index: int,
    ) -> tuple[str, bool]:
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        request = ModelRunRequest(
            instructions=(
                "Critique this academic figure for factual fidelity, legibility, visual "
                "hierarchy, labels, and correspondence to the supplied evidence. Return "
                "JSON with critic_suggestions and revised_description. If no correction "
                "is needed, critic_suggestions must be 'No changes needed.'."
            ),
            input=(
                Message(
                    role="user",
                    content=(
                        TextContent(
                            text=json.dumps(
                                {
                                    "plan": plan,
                                    "description": description,
                                    "paper_materials.md": materials,
                                },
                                ensure_ascii=False,
                            )
                        ),
                        ImageContent(
                            image_url=f"data:image/png;base64,{encoded}",
                            detail="original",
                        ),
                    ),
                ),
            ),
            response_format="json_object",
            temperature=0,
            reasoning=ReasoningConfig(mode="pro"),
            checkpoint_key=f"critique_figure_{_safe_figure_id(plan.get('figure_id'))}_{round_index}",
        )
        response = await self.model.run(request)
        try:
            critique = json.loads(repair_json(response.text))
        except (json.JSONDecodeError, TypeError) as error:
            _fail(f"invalid figure critique: {error}")
        suggestions = str(critique.get("critic_suggestions", "")).strip()
        revised = str(critique.get("revised_description", description)).strip()
        return revised or description, suggestions != "No changes needed."


def render_plot_code(code: str, output_path: Path) -> None:
    script_path = output_path.with_suffix(".plot.py")
    script_path.write_text(
        "import os\nPLOT_OUTPUT_PATH = os.environ['PLOT_OUTPUT_PATH']\n"
        + code
        + "\nimport matplotlib.pyplot as plt\n"
        + "\nif not os.path.exists(PLOT_OUTPUT_PATH): plt.savefig(PLOT_OUTPUT_PATH, bbox_inches='tight')\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PLOT_OUTPUT_PATH"] = str(output_path)
    completed = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=output_path.parent,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        _fail(
            "plot code failed: "
            + (completed.stderr.strip() or completed.stdout.strip())
        )


def _load_existing(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.is_file():
        return []
    data = _read_json(path, list)
    return [item for item in data if isinstance(item, dict)]


def _read_json(path: Path, expected_type: type) -> Any:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        _fail(f"cannot read {path.name}: {error}")
    if not isinstance(data, expected_type):
        _fail(f"{path.name} has an invalid JSON shape")
    return data


def _safe_figure_id(value: Any) -> str:
    identifier = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "figure")).strip("_")
    return identifier or "figure"


def _fail(message: str) -> None:
    raise PaperOrchestraStageError(
        stage="generate_figures",
        code="figure_generation_failed",
        message=message,
    )
