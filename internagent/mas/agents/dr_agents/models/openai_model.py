"""Synchronous DeepResearch facade over the shared Unified Model Runtime."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict, Optional

from internagent.mas.models.runtime import (
    Message,
    ModelRunRequest,
    ModelRunResult,
    ReasoningConfig,
)
from internagent.mas.models.unified_runtime import UnifiedModelRuntime

try:
    from .base_model import BaseModel
    from ..utils.fix_json import repair_json_string
    from ..utils.logger import get_logger
except ImportError:  # pragma: no cover - legacy top-level DR bootstrap
    from models.base_model import BaseModel
    from utils.fix_json import repair_json_string
    from utils.logger import get_logger

logger = get_logger(__name__)


def _is_likely_json_response(text: str) -> bool:
    stripped = text.strip() if isinstance(text, str) else ""
    return stripped.startswith(("{", "[", "```json")) or "```json" in stripped.lower()


class OpenAIModel(BaseModel):
    """Keep the DR synchronous interface while delegating every call to Runtime."""

    def __init__(
        self,
        model_name: str = "qwen/qwen3.7-max",
        *,
        runtime: UnifiedModelRuntime | None = None,
        runtime_config: Optional[Dict[str, Any]] = None,
        agent_role: str = "deep_research",
        reasoning_context: str = "current_turn",
        reasoning_mode: str = "standard",
        **_: Any,
    ) -> None:
        runtime = runtime or (runtime_config or {}).get("runtime")
        if runtime is None or not hasattr(runtime, "catalog") or not hasattr(runtime, "model_for"):
            raise ValueError(
                "DeepResearch requires an injected UnifiedModelRuntime; "
                "Provider-local configuration is not supported"
            )
        self.runtime = runtime
        self.model_id = runtime.catalog.resolve_model(model_name, capability="text").canonical_id
        self.model_name = runtime.catalog.resolve_model(self.model_id).model
        self.agent_role = agent_role
        self.reasoning_context = reasoning_context
        self.reasoning_mode = reasoning_mode
        self._thread_local = threading.local()

    def _await(self, coroutine):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)
        result: list[Any] = []
        error: list[BaseException] = []

        def runner() -> None:
            try:
                result.append(asyncio.run(coroutine))
            except BaseException as exc:  # pragma: no cover - defensive bridge
                error.append(exc)

        thread = threading.Thread(target=runner)
        thread.start()
        thread.join()
        if error:
            raise error[0]
        return result[0]

    def run(self, request: ModelRunRequest) -> ModelRunResult:
        reasoning = request.reasoning or ReasoningConfig(
            context=self.reasoning_context,
            mode=self.reasoning_mode,
        )
        prompt_cache_key = request.prompt_cache_key
        if prompt_cache_key is None and request.instructions:
            prompt_cache_key = self.runtime.model_for(
                self.model_id, capability="text"
            ).make_prompt_cache_key(
                agent_role=self.agent_role,
                stable_prefix=request.instructions,
            )
        request = request.__class__(
            input=request.input,
            instructions=request.instructions,
            tools=request.tools,
            response_format=request.response_format,
            previous_response_id=request.previous_response_id,
            prompt_cache_key=prompt_cache_key,
            reasoning=reasoning,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
        )
        return self._await(
            self.runtime.run(request, model_id=self.model_id, capability="text")
        )

    def probe(self) -> None:
        self.run(
            ModelRunRequest(
                input=(Message.user("Reply with OK."),),
                reasoning=ReasoningConfig(
                    effort="low", context="current_turn", mode="standard"
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
        allowed = {"max_output_tokens", "temperature"}
        unsupported = set(kwargs) - allowed
        if unsupported:
            raise ValueError(
                "Unsupported DeepResearch Runtime options: "
                + ", ".join(sorted(unsupported))
            )
        result = self.run(
            ModelRunRequest(
                instructions=system_prompt,
                input=(Message.user(prompt),),
                temperature=kwargs.get("temperature"),
                max_output_tokens=kwargs.get("max_output_tokens"),
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

    def close(self) -> None:
        """Runtime ownership belongs to the process; there is no client to close."""


__all__ = ["OpenAIModel"]
