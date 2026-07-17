"""Provider-independent model Runtime contract for InternAgent."""

from __future__ import annotations

import abc
import inspect
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Union

from json_repair import repair_json

from .runtime import (
    Message,
    ModelRunRequest,
    ModelRunResult,
    ReasoningConfig,
    build_prompt_cache_key,
)

logger = logging.getLogger(__name__)


class ModelError(Exception):
    """Base exception for model Runtime failures."""


class RateLimitError(ModelError):
    """Raised when API quotas or rate limits are exceeded."""


class TokenLimitError(ModelError):
    """Raised when input or output exceeds a model limit."""


class AuthenticationError(ModelError):
    """Raised when model credentials are invalid or expired."""


class ServiceUnavailableError(ModelError):
    """Raised when a provider cannot be reached."""


class UnsupportedModelCapabilityError(ModelError):
    """Raised when a provider cannot honor a requested Runtime capability."""


class ModelRunTerminalError(ModelError):
    """Raised when a provider accepts a run but it ends unsuccessfully."""


class BaseModel(abc.ABC):
    """Deep model seam consumed by every InternAgent production caller."""

    supports_prompt_cache = False

    def __init__(self) -> None:
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.total_tokens = 0
        self.total_time = 0.0
        self._on_completion: Optional[Callable[..., Any]] = None

    async def run(self, request: ModelRunRequest) -> ModelRunResult:
        """Execute one typed inference run and emit provider-neutral telemetry."""

        from internagent.research_draft import record_research_event

        record_research_event(request)
        started_at = time.perf_counter()
        self.total_calls += 1
        result: ModelRunResult | None = None
        error: Exception | None = None

        try:
            result = await self._run(request)
            if not isinstance(result, ModelRunResult):
                raise TypeError(
                    f"{self.__class__.__name__}._run returned "
                    f"{type(result).__name__}, expected ModelRunResult"
                )
            self.successful_calls += 1
            self.total_tokens += result.usage.total_tokens
            return result
        except Exception as exc:
            error = exc
            self.failed_calls += 1
            classified = self._classify_error(exc)
            if classified is exc:
                raise
            raise classified from exc
        finally:
            if result is not None:
                record_research_event(result)
            if error is not None:
                record_research_event(error)
            elapsed = time.perf_counter() - started_at
            self.total_time += elapsed
            telemetry = self._telemetry_event(
                request=request,
                result=result,
                error=error,
                elapsed=elapsed,
            )
            self._log_telemetry(telemetry)
            await self._emit_completion(telemetry)

    @abc.abstractmethod
    async def _run(self, request: ModelRunRequest) -> ModelRunResult:
        """Provider adapter implementation for :meth:`run`."""

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        *,
        prompt_cache_key: Optional[str] = None,
        agent_role: Optional[str] = None,
        reasoning: Optional[ReasoningConfig] = None,
    ) -> str:
        """Convenience interface for a one-turn text Runtime request."""

        cache_key = prompt_cache_key or self.make_prompt_cache_key(
            agent_role=agent_role,
            stable_prefix=system_prompt,
        )
        result = await self.run(
            ModelRunRequest(
                instructions=system_prompt,
                input=(Message.user(prompt),),
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                prompt_cache_key=cache_key,
                reasoning=reasoning,
            )
        )
        return result.text

    async def generate_json(
        self,
        prompt: str,
        schema: Dict[str, Any],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        default: Optional[Dict[str, Any]] = None,
        *,
        max_output_tokens: Optional[int] = None,
        prompt_cache_key: Optional[str] = None,
        agent_role: Optional[str] = None,
        reasoning: Optional[ReasoningConfig] = None,
    ) -> Dict[str, Any]:
        """Generate a JSON Object while retaining the existing repair fallback."""

        if system_prompt:
            instructions = (
                f"{system_prompt}\n\nRespond with JSON that matches this schema: "
                f"{json.dumps(schema)}"
            )
        else:
            instructions = (
                "Respond with JSON that matches this schema: "
                f"{json.dumps(schema)}"
            )

        cache_key = prompt_cache_key or self.make_prompt_cache_key(
            agent_role=agent_role,
            stable_prefix=instructions,
        )
        try:
            result = await self.run(
                ModelRunRequest(
                    instructions=instructions,
                    input=(Message.user(prompt),),
                    response_format="json_object",
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    prompt_cache_key=cache_key,
                    reasoning=reasoning,
                )
            )
            try:
                parsed = json.loads(result.text)
            except json.JSONDecodeError:
                parsed = json.loads(repair_json(result.text))
            if not isinstance(parsed, dict):
                raise ValueError("Model JSON response must be an object")
            return parsed
        except Exception:
            if default is not None:
                logger.warning("Returning configured default after JSON run failure")
                return default
            raise

    async def embed(
        self, text: Union[str, List[str]]
    ) -> Union[List[float], List[List[float]]]:
        """Embedding is an optional capability, separate from GPT-5.6 inference."""

        raise UnsupportedModelCapabilityError(
            f"{self.__class__.__name__} does not support embeddings"
        )

    @classmethod
    @abc.abstractmethod
    def from_config(cls, config: Dict[str, Any]) -> "BaseModel":
        """Create a provider adapter from validated configuration."""

    def make_prompt_cache_key(
        self,
        *,
        agent_role: Optional[str],
        stable_prefix: Optional[str],
    ) -> Optional[str]:
        """Return a central cache key only for adapters that support the feature."""

        if not self.supports_prompt_cache or not agent_role or not stable_prefix:
            return None
        return build_prompt_cache_key(
            model=str(getattr(self, "model_name", "unknown")),
            agent_role=agent_role,
            stable_prefix=stable_prefix,
        )

    def set_completion_callback(self, callback: Callable[..., Any]) -> None:
        self._on_completion = callback

    async def _emit_completion(self, telemetry: Dict[str, Any]) -> None:
        if self._on_completion is None:
            return
        try:
            callback_result = self._on_completion(**telemetry)
            if inspect.isawaitable(callback_result):
                await callback_result
        except Exception as callback_error:
            logger.warning("Model telemetry callback failed: %s", callback_error)

    @staticmethod
    def _classify_error(error: Exception) -> ModelError:
        if isinstance(error, ModelError):
            return error
        message = str(error)
        lower = message.lower()
        if "rate limit" in lower or "429" in lower:
            return RateLimitError(message)
        if "token" in lower and ("limit" in lower or "exceed" in lower):
            return TokenLimitError(message)
        if any(term in lower for term in ("auth", "api key", "credential", "401")):
            return AuthenticationError(message)
        if any(term in lower for term in ("unavailable", "connect", "timeout", "503")):
            return ServiceUnavailableError(message)
        return ModelError(message)

    @staticmethod
    def _telemetry_event(
        *,
        request: ModelRunRequest,
        result: ModelRunResult | None,
        error: Exception | None,
        elapsed: float,
    ) -> Dict[str, Any]:
        usage = result.usage if result is not None else None
        return {
            "success": result is not None and error is None,
            "elapsed_time": elapsed,
            "model": result.model if result is not None else None,
            "response_id": result.response_id if result is not None else None,
            "status": result.status if result is not None else "failed",
            "input_tokens": usage.input_tokens if usage else 0,
            "output_tokens": usage.output_tokens if usage else 0,
            "reasoning_tokens": usage.reasoning_tokens if usage else 0,
            "cached_tokens": usage.cached_tokens if usage else 0,
            "cache_write_tokens": usage.cache_write_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
            "reasoning_context": (
                result.reasoning_context
                if result is not None
                else (
                    request.reasoning.context
                    if request.reasoning is not None
                    else None
                )
            ),
            "error": str(error) if error is not None else None,
        }

    @staticmethod
    def _log_telemetry(telemetry: Dict[str, Any]) -> None:
        logger.info(
            "model_run status=%s model=%s response_id=%s latency=%.3fs "
            "input=%d output=%d reasoning=%d cached=%d cache_write=%d "
            "reasoning_context=%s",
            telemetry["status"],
            telemetry["model"],
            telemetry["response_id"],
            telemetry["elapsed_time"],
            telemetry["input_tokens"],
            telemetry["output_tokens"],
            telemetry["reasoning_tokens"],
            telemetry["cached_tokens"],
            telemetry["cache_write_tokens"],
            telemetry["reasoning_context"],
        )

    def get_stats(self) -> Dict[str, Any]:
        average = self.total_time / self.total_calls if self.total_calls else 0.0
        success_rate = (
            self.successful_calls / self.total_calls * 100
            if self.total_calls
            else 0.0
        )
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": success_rate,
            "total_tokens": self.total_tokens,
            "total_time": self.total_time,
            "average_time_per_call": average,
            "model_type": self.__class__.__name__,
        }
