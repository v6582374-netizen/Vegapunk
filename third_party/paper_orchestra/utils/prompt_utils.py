"""Prompt bodies relocated to the Vegapunk Prompt Library."""
from vegapunk.prompt_library import prompts as _library
_IDS = {
    "UNIVERSAL_NO_LEAKAGE_PROMPT": "paper.prompt_utils.universal_no_leakage_prompt",
}

def __getattr__(name: str) -> str:
    if name not in _IDS:
        raise AttributeError(name)
    return _library.get(_IDS[name])

