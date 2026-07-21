#!/usr/bin/env python3
"""Prompt loader for Deep Research agents.

Prefers the Vegapunk Prompt Library (``deep_research.*`` ids). Falls back
to loading a named variable from a Python file for custom ``prompt_path`` /
``prompt_name`` overrides in agent config.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any, Dict

from utils.logger import get_logger

logger = get_logger("PromptLoader")

# Map historic variable names to Prompt Library ids.
_LIBRARY_IDS = {
    "GLOBAL_PLANNER_PROMPT": "deep_research.global_planner",
    "GLOBAL_COORDINATOR_PROMPT": "deep_research.global_coordinator",
    "OUTLINE_GENERATION_PROMPT": "deep_research.outline_generation",
    "SECTION_WRITING_PROMPT": "deep_research.section_writing",
    "INTRODUCTION_SECTION_PROMPT": "deep_research.introduction_section",
    "SECTION_POLISHING_PROMPT": "deep_research.section_polishing",
    "TASK_SUMMARY_PROMPT": "deep_research.task_summary",
    "PLANNER_PROMPT": "deep_research.planner",
    "EXECUTION_PROMPT": "deep_research.execution",
    "SUMMARY_PROMPT": "deep_research.summary",
    "QA_SYNTHESIZER_PROMPT": "deep_research.qa_synthesizer",
}


def load_prompt(
    config: Dict[str, Any],
    default_name: str,
    default_path: str = "prompts/default_prompts.py",
) -> str:
    if config is None:
        config = {}

    prompt_path = config.get("prompt_path") or default_path
    prompt_name = config.get("prompt_name") or default_name

    # Default path: always read through the Prompt Library so Launch
    # Configuration Snapshots apply.
    if (
        prompt_path in {"prompts/default_prompts.py", "default_prompts.py"}
        and prompt_name in _LIBRARY_IDS
        and not config.get("prompt_path")
        and not config.get("prompt_name")
    ):
        from vegapunk.prompt_library import prompts

        return prompts.get(_LIBRARY_IDS[prompt_name])

    # Custom override path still supported for experiments.
    if prompt_name in _LIBRARY_IDS and (
        prompt_path.endswith("default_prompts.py") or not config.get("prompt_path")
    ):
        from vegapunk.prompt_library import prompts

        return prompts.get(_LIBRARY_IDS[prompt_name])

    try:
        loaded_prompt = load_prompt_from_file(prompt_path, prompt_name)
        logger.debug(f"Loaded prompt from file: {prompt_path} -> {prompt_name}")
        return loaded_prompt
    except Exception as error:
        logger.error(f"加载prompt失败: {error}")
        raise


def load_prompt_from_file(prompt_path: str, prompt_name: str) -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full_path = os.path.join(project_root, prompt_path)

    if not os.path.exists(full_path):
        raise FileNotFoundError(f"Prompt文件不存在: {full_path}")

    spec = importlib.util.spec_from_file_location("prompt_module", full_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {full_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, prompt_name):
        raise AttributeError(f"模块 {prompt_path} 中不存在变量 {prompt_name}")

    prompt = getattr(module, prompt_name)
    if not isinstance(prompt, str):
        raise TypeError(f"Prompt变量 {prompt_name} 不是字符串类型")
    return prompt
