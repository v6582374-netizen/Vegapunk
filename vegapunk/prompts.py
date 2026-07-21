"""Backward-compatible accessors for experiment prompts.

Bodies live in the Prompt Library (``config/prompts/``). Prefer
``vegapunk.prompt_library.prompts.get(...)`` for new call sites.
"""

from vegapunk.prompt_library import prompts as _library


def _load(prompt_id: str) -> str:
    return _library.get(prompt_id)


# Lazy module-level names keep ``from vegapunk.prompts import X`` working
# while always reading the current library root (global or Launch snapshot).


def __getattr__(name: str) -> str:
    mapping = {
        "CODER_PROMPT_MCTS_DRAFT": "experiment.coder_mcts_draft",
        "CODER_PROMPT_OPENHANDS": "experiment.coder_openhands",
        "CODE_STRUCTURE_PROMPT": "experiment.code_structure",
        "DEBUG_PROMPT_WITH_STRUCTURE": "experiment.debug_with_structure",
        "NEXT_EXPERIMENT_PROMPT": "experiment.next_experiment",
        "CODER_PROMPT_SCI_TASK": "experiment.coder_sci_task",
        "NEXT_EXPERIMENT_PROMPT_SCI": "experiment.next_experiment_sci",
        "MCTS_IMPROVE_PROMPT": "experiment.mcts_improve",
    }
    if name not in mapping:
        raise AttributeError(name)
    return _load(mapping[name])
