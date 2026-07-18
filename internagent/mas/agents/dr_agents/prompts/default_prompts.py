"""Deep Research prompts — bodies live in the Prompt Library.

Kept as a thin facade so ``prompt_loader.load_prompt_from_file`` and
``from ...default_prompts import X`` continue to work.
"""

from __future__ import annotations

from internagent.prompt_library import prompts as _library

_PROMPT_IDS = {
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


def __getattr__(name: str) -> str:
    if name not in _PROMPT_IDS:
        raise AttributeError(name)
    return _library.get(_PROMPT_IDS[name])


def __dir__():
    return sorted(list(_PROMPT_IDS) + ['__getattr__', '__dir__'])
