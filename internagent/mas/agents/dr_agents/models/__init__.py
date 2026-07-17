"""Runtime-owned model facade for the embedded DeepResearch workflow."""

from typing import Any

from .base_model import BaseModel


def get_model(model_name: str, **kwargs: Any) -> BaseModel:
    """Create the one DR model facade from an explicit catalog identity.

    Provider selection is supplied by the injected Runtime.  A model-name
    prefix is never interpreted as a Provider selector.
    """
    runtime_config = kwargs.get("runtime_config") or {}
    runtime = kwargs.get("runtime") or runtime_config.get("runtime")
    if runtime is None:
        raise ValueError(
            "DeepResearch model creation requires an injected UnifiedModelRuntime"
        )
    from .openai_model import OpenAIModel

    model_class = OpenAIModel
    return model_class(
        model_name,
        runtime=runtime,
        runtime_config=runtime_config,
        **{key: value for key, value in kwargs.items() if key not in {"runtime", "runtime_config"}},
    )


__all__ = [
    "BaseModel",
    "OpenAIModel",
    "get_model",
]
