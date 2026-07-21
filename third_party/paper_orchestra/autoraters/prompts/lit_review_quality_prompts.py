"""Prompt bodies relocated to the Vegapunk Prompt Library."""
from vegapunk.prompt_library import prompts as _library
_IDS = {
    "lit_review_quality_system_prompt": "paper.lit_review_quality_prompts.lit_review_quality_system_prompt",
}

def __getattr__(name: str) -> str:
    if name not in _IDS:
        raise AttributeError(name)
    return _library.get(_IDS[name])

