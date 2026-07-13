"""Synchronous DeepResearch facade over InternAgent's Responses Runtime."""

from __future__ import annotations

import asyncio
import inspect
import os
import threading
from dataclasses import replace
from typing import Any, Dict, Optional

from internagent.mas.models.openai_model import OpenAIModel as RuntimeOpenAIModel
from internagent.mas.models.runtime import (
    Message,
    ModelRunRequest,
    ModelRunResult,
    ReasoningConfig,
)

try:
    # Package-native imports used by tests and normal InternAgent imports.
    from .base_model import BaseModel
    from ..utils.fix_json import repair_json_string
    from ..utils.logger import get_logger
except ImportError:
    # The legacy DR bootstrap also loads this module as top-level ``models``
    # after adding ``dr_agents`` to sys.path. Keep that entry point working
    # until the whole embedded workflow is converted to package imports.
    from models.base_model import BaseModel
    from utils.fix_json import repair_json_string
    from utils.logger import get_logger

logger = get_logger(__name__)


class _ThreadRuntimeState:
    """Own one async Runtime client and event loop for a DR worker thread."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.model: Optional[RuntimeOpenAIModel] = None

    def close(self) -> None:
        if self.loop.is_closed():
            return
        client = getattr(self.model, "client", None)
        close = getattr(client, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                self.loop.run_until_complete(result)
        self.loop.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            # Interpreter shutdown and abrupt worker termination must not hide
            # the original DR result with cleanup errors.
            pass


def _is_likely_json_response(text: str) -> bool:
    stripped = text.strip() if isinstance(text, str) else ""
    return (
        stripped.startswith(("{", "[", "```json"))
        or "```json" in stripped.lower()
    )


class OpenAIModel(BaseModel):
    """Expose synchronous DR methods without exposing an SDK response shape."""

    def __init__(
        self,
        model_name: str = "gpt-5.6-sol",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        *,
        runtime_config: Optional[Dict[str, Any]] = None,
        agent_role: str = "deep_research",
        reasoning_context: str = "current_turn",
        reasoning_mode: str = "standard",
        background: bool = False,
        **_: Any,
    ) -> None:
        self.model_name = model_name
        self.agent_role = agent_role
        self.reasoning_context = reasoning_context
        self.reasoning_mode = reasoning_mode
        self.background = background
        if not (base_url or (runtime_config or {}).get("base_url")):
            raise ValueError(
                "DeepResearch OpenAI requires explicit runtime_config with "
                "base_url"
            )
        self.runtime_config = dict(runtime_config or {})
        self.runtime_config.update(
            {
                "provider": "openai",
                "model_name": model_name,
                "api_mode": "responses",
            }
        )
        if api_key:
            self.runtime_config["api_key"] = api_key
        elif not self.runtime_config.get("api_key"):
            self.runtime_config["api_key"] = (
                os.getenv("OPENAI_API_KEY_WORKFLOW")
                or os.getenv("OPENAI_API_KEY")
            )
        if base_url:
            self.runtime_config["base_url"] = base_url
        elif not self.runtime_config.get("base_url"):
            self.runtime_config["base_url"] = (
                os.getenv("OPENAI_BASE_URL_WORKFLOW")
                or os.getenv("OPENAI_API_BASE_URL")
            )
        self._thread_state = threading.local()

    def _state(self) -> _ThreadRuntimeState:
        state = getattr(self._thread_state, "runtime_state", None)
        if state is None or state.loop.is_closed():
            state = _ThreadRuntimeState()
            self._thread_state.runtime_state = state
        return state

    def _runtime(self) -> RuntimeOpenAIModel:
        state = self._state()
        if state.model is None:
            state.model = RuntimeOpenAIModel.from_config(self.runtime_config)
        return state.model

    def _await(self, coroutine):
        return self._state().loop.run_until_complete(coroutine)

    def close(self) -> None:
        """Release the Runtime client owned by the current DR worker thread."""
        state = getattr(self._thread_state, "runtime_state", None)
        if state is not None:
            state.close()
            del self._thread_state.runtime_state

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def run(self, request: ModelRunRequest) -> ModelRunResult:
        runtime = self._runtime()
        reasoning = request.reasoning or ReasoningConfig(
            context=self.reasoning_context,
            mode=self.reasoning_mode,
        )
        prompt_cache_key = request.prompt_cache_key
        if prompt_cache_key is None and request.instructions:
            prompt_cache_key = runtime.make_prompt_cache_key(
                agent_role=self.agent_role,
                stable_prefix=request.instructions,
            )
        effective_request = replace(
            request,
            reasoning=reasoning,
            background=request.background or self.background,
            prompt_cache_key=prompt_cache_key,
        )
        return self._await(runtime.run(effective_request))

    def probe(self) -> None:
        """Verify that the configured deployment can run this model."""

        self.run(
            ModelRunRequest(
                input=(Message.user("Reply with OK."),),
                reasoning=ReasoningConfig(
                    effort="low",
                    context="current_turn",
                    mode="standard",
                ),
                max_output_tokens=16,
            )
        )

    def generate(
        self,
        prompt: str,
        auto_fix_json: bool = True,
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        max_output_tokens = kwargs.pop("max_output_tokens", None)
        temperature = kwargs.pop("temperature", None)
        for internal_key in (
            "runtime_config",
            "agent_role",
            "reasoning_context",
            "reasoning_mode",
            "background",
            "extraction_model",
            "stream",
            "model",
        ):
            kwargs.pop(internal_key, None)
        if kwargs:
            raise ValueError(
                "Unsupported DeepResearch Runtime options: "
                + ", ".join(sorted(kwargs))
            )
        result = self.run(
            ModelRunRequest(
                instructions=system_prompt,
                input=(Message.user(prompt),),
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        )
        content = result.text
        if auto_fix_json and _is_likely_json_response(content):
            try:
                return repair_json_string(content)
            except Exception as error:
                logger.warning("Failed to repair JSON response: %s", error)
        return content

    def generate_with_system_prompt(
        self,
        system_prompt: str,
        user_prompt: str,
        auto_fix_json: bool = True,
        **kwargs: Any,
    ) -> str:
        return self.generate(
            user_prompt,
            system_prompt=system_prompt,
            auto_fix_json=auto_fix_json,
            **kwargs,
        )
