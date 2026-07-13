"""Lazy model registry for the embedded DeepResearch workflow."""

from importlib import import_module
from typing import Any

from .base_model import BaseModel


_MODEL_TYPES = {
    "DeepSeekModel": (".deepseek", "DeepSeekModel"),
    "OpenAIModel": (".openai_model", "OpenAIModel"),
    "QwenModel": (".vllm_qwen", "QwenModel"),
    "InternS1Model": (".intern_s1", "InternS1Model"),
    "QwenAPIModel": (".qwen_model", "QwenAPIModel"),
    "GeminiModel": (".gemini_model", "GeminiModel"),
}


def __getattr__(name: str) -> Any:
    """Load provider code only when that provider is actually selected."""
    target = _MODEL_TYPES.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, class_name = target
    model_class = getattr(import_module(module_name, __name__), class_name)
    globals()[name] = model_class
    return model_class


def get_model(model_name: str, **kwargs: Any) -> BaseModel:
    """Create the DR provider selected by its existing model-name convention."""
    if "deepseek" in model_name:
        model_class = __getattr__("DeepSeekModel")
    elif model_name.startswith(("gpt", "o")):
        model_class = __getattr__("OpenAIModel")
    elif model_name.startswith(("Qwen/", "qwen")):
        model_class = __getattr__("QwenAPIModel")
    elif model_name.startswith(("Qwen", "vllm")):
        model_class = __getattr__("QwenModel")
    elif model_name.startswith("intern"):
        model_class = __getattr__("InternS1Model")
    elif model_name.startswith("gemini"):
        model_class = __getattr__("GeminiModel")
    else:
        raise ValueError(f"Unsupported model: {model_name}")
    return model_class(model_name, **kwargs)


__all__ = [
    "BaseModel",
    "DeepSeekModel",
    "OpenAIModel",
    "get_model",
    "QwenModel",
    "InternS1Model",
    "QwenAPIModel",
    "GeminiModel",
]
