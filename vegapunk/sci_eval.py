"""
Thin adapter over the official ResearchClawBench evaluation scorer.

All rubric, prompt construction, and per-item scoring logic lives in
rcb_evaluation (symlinked from ResearchClawBench/evaluation/).

This module only adapts the interface for Vegapunk's experiment loop:
  score_run(workspace_dir, checklist_path, model) -> scores dict
  write_final_info(run_dir, scores) -> path to final_info.json
"""
import asyncio
import base64
import os
import os.path as osp
import json
import logging
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Any

from json_repair import repair_json

from vegapunk.mas.models.runtime import (
    ImageContent,
    Message,
    ModelRunRequest,
    ReasoningConfig,
    TextContent,
)
from vegapunk.mas.models.unified_runtime import UnifiedModelRuntime
from vegapunk.rcb_evaluation.score import (
    _read_report, _find_generated_images, _score_single_item,
)
from vegapunk.rcb_evaluation.utils import safe_resolve

logger = logging.getLogger(__name__)


from vegapunk.prompt_library import prompts as _prompt_library

SCORER_SYSTEM_PROMPT = _prompt_library.get("scoring.scorer_system")


class RuntimeScoringAgent:
    """Synchronous callable expected by ResearchClawBench, backed by Responses."""

    def __init__(
        self,
        *,
        runtime: UnifiedModelRuntime | None = None,
        model_name: str | None = None,
        max_output_tokens: int = 500,
        timeout: int = 120,
    ) -> None:
        del timeout
        if runtime is None:
            raise ValueError("Sci evaluator requires the process-owned UnifiedModelRuntime")
        self.runtime = runtime
        self.model_id = model_name or self.runtime.catalog.active_text_model
        if model_name is not None and model_name != self.runtime.catalog.active_text_model:
            raise ValueError("Sci evaluator must use the Catalog active_text_model")
        self.model_id = self.runtime.catalog.resolve_model(
            self.model_id, capability="json"
        ).canonical_id
        self.vision_model_id = self.runtime.catalog.binding_for("vision").canonical_id
        self.model_name = self.runtime.catalog.resolve_model(self.model_id).model
        self.max_output_tokens = max_output_tokens

    def __call__(
        self,
        prompt: str,
        *,
        image_paths: list[str] | None = None,
        return_example: dict[str, object] | None = None,
        max_try: int = 2,
    ) -> dict[str, object] | None:
        del return_example
        del max_try
        try:
            return asyncio.run(self._run(prompt, image_paths or []))
        except Exception as error:
            logger.error("Unified Runtime scorer failed: %s", error)
            return None

    async def _run(
        self, prompt: str, image_paths: list[str]
    ) -> dict[str, object]:
        capability = "vision" if image_paths else "json"
        request_model_id = self.vision_model_id if image_paths else self.model_id
        model = self.runtime.model_for(request_model_id, capability=capability)
        content: list[TextContent | ImageContent] = [TextContent(text=prompt)]
        for raw_path in image_paths:
            path = Path(raw_path)
            mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            content.append(
                ImageContent(
                    image_url=f"data:{mime_type};base64,{encoded}",
                    detail="original",
                )
            )
        result = await model.run(
            ModelRunRequest(
                instructions=SCORER_SYSTEM_PROMPT,
                input=(Message(role="user", content=tuple(content)),),
                response_format="json_object",
                reasoning=ReasoningConfig(context="current_turn", mode="pro"),
                temperature=0,
                max_output_tokens=self.max_output_tokens,
                prompt_cache_key=model.make_prompt_cache_key(
                    agent_role="researchclawbench_scorer",
                    stable_prefix=SCORER_SYSTEM_PROMPT,
                ),
            )
        )
        try:
            parsed = json.loads(result.text)
        except json.JSONDecodeError:
            parsed = json.loads(repair_json(result.text))
        if not isinstance(parsed, dict):
            raise ValueError("scorer response must be a JSON object")
        return parsed


def _parallel_score(inputs, function, max_workers: int):
    def invoke(item):
        return function(**item)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(invoke, inputs))


def _get_env(name: str, *fallbacks: str) -> str:
    """Get env var, trying fallback names if primary is empty."""
    val = os.environ.get(name, "")
    if val:
        return val
    for fb in fallbacks:
        val = os.environ.get(fb, "")
        if val:
            return val
    return ""


def score_run(
    workspace_dir: str,
    checklist_path: str,
    model: str | None = None,
    runtime: UnifiedModelRuntime | None = None,
) -> Dict[str, Any]:
    """Score all checklist items using the official ResearchClawBench scorer."""
    if not osp.exists(checklist_path):
        logger.error(f"Checklist not found: {checklist_path}")
        return {'total_score': 0}

    with open(checklist_path) as f:
        checklist = json.load(f)

    if not checklist:
        logger.warning("Empty checklist, returning score 0")
        return {'total_score': 0}

    workspace = Path(workspace_dir)
    report_text = _read_report(workspace)
    if not report_text:
        logger.warning(f"No report found in {workspace_dir}")
        return {'total_score': 0}

    instructions_path = workspace / "INSTRUCTIONS.md"
    instructions = ""
    if instructions_path.exists():
        instructions = instructions_path.read_text(encoding="utf-8", errors="replace")

    generated_images = _find_generated_images(workspace)

    if runtime is None:
        raise ValueError("Sci evaluator requires the process-owned UnifiedModelRuntime")
    agent = RuntimeScoringAgent(
        runtime=runtime,
        model_name=model,
        max_output_tokens=500,
    )

    target_base = workspace / "target_study"

    def score_item(index, item_data):
        target_path = None
        if item_data.get("type", "text") == "image":
            target_rel = item_data.get("path", "")
            if target_rel:
                target_path = safe_resolve(target_base, target_rel)
        return _score_single_item(
            agent, report_text, item_data, target_path, generated_images, instructions
        )

    inputs = [{"index": i, "item_data": item} for i, item in enumerate(checklist)]
    n = len(checklist)
    logger.info(f"Scoring {n} checklist items in parallel (model={model})")
    raw_results = _parallel_score(inputs, score_item, max_workers=min(n, 16))

    scores: Dict[str, Any] = {}
    total_weight = 0.0
    weighted_sum = 0.0

    for i, (item, result) in enumerate(zip(checklist, raw_results)):
        w = float(item.get('weight', 1.0))
        sr = result if result else {"score": 0, "reasoning": "Scoring failed."}
        scores[f'item_{i}_score'] = sr['score']
        scores[f'item_{i}_reasoning'] = sr['reasoning']
        weighted_sum += sr['score'] * w
        total_weight += w
        logger.info(f"  item_{i}: {sr['score']}/100 (weight={w:.2f})")

    scores['total_score'] = round(weighted_sum / total_weight, 2) if total_weight > 0 else 0.0
    logger.info(f"Weighted total score: {scores['total_score']:.2f}/100")
    return scores


def write_final_info(run_dir: str, scores: Dict[str, Any]) -> str:
    """Write scores as final_info.json for Vegapunk's loop-critic."""
    means = {k: v for k, v in scores.items() if not k.endswith('_reasoning')}
    final_info = {"sci_task": {"means": means}}

    os.makedirs(run_dir, exist_ok=True)
    path = osp.join(run_dir, "final_info.json")
    with open(path, 'w') as f:
        json.dump(final_info, f, indent=2)
    logger.info(f"Wrote final_info.json -> {path}")
    return path
