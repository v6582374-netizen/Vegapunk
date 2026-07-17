"""Responses-native OpenAI adapter for the InternAgent Model Runtime."""

from __future__ import annotations

import copy
import asyncio
import json
import logging
import os
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Union

from openai import AsyncOpenAI

from .base_model import BaseModel, ModelRunTerminalError
from .runtime import (
    FunctionCall,
    FunctionCallOutput,
    FunctionTool,
    ImageContent,
    Message,
    ModelRunRequest,
    ModelRunResult,
    ModelUsage,
    OutputText,
)

logger = logging.getLogger(__name__)


class OpenAIModel(BaseModel):
    """OpenAI Responses implementation with GPT-5.6 runtime policy."""

    supports_prompt_cache = True
    _ALLOWED_CONFIG_KEYS = {
        "provider",
        "default_provider",
        "api_key",
        "base_url",
        "model_name",
        "max_output_tokens",
        "temperature",
        "timeout",
        "default_headers",
        "api_mode",
        "reasoning",
        "store",
        "prompt_cache",
        "request_timeout",
        "response_state",
        "provider_name",
        "api_key_env",
    }
    _OBSOLETE_CONFIG_KEYS = {
        "max_tokens": "max_output_tokens",
        "prompt_cache_retention": "prompt_cache.ttl",
        "reasoning_effort": "reasoning.effort",
        "reasoning_context": "reasoning.context",
        "reasoning_mode": "reasoning.mode",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: str = "gpt-5.6-sol",
        max_output_tokens: Optional[int] = None,
        temperature: float = 0.7,
        timeout: int = 600,
        default_headers: Optional[Dict[str, str]] = None,
        api_key_env_var: str = "OPENAI_API_KEY",
        provider_name: str = "OpenAI",
        api_mode: str = "responses",
        reasoning_effort: str = "xhigh",
        reasoning_context: str = "auto",
        reasoning_mode: str = "standard",
        store: bool = True,
        prompt_cache_mode: str = "explicit",
        prompt_cache_ttl: str = "30m",
        request_timeout: float = 3600.0,
        response_state_mode: str = "server",
        response_state_max_entries: int = 128,
        client: Optional[Any] = None,
    ) -> None:
        super().__init__()
        if api_mode != "responses":
            raise ValueError(
                "Native OpenAI requires api_mode='responses'; Chat-compatible "
                "gateways must use their dedicated adapter"
            )

        self.api_key = api_key or os.environ.get(api_key_env_var)
        self.base_url = base_url or os.environ.get(
            "OPENAI_API_BASE_URL", "https://api.openai.com/v1"
        )
        self.model_name = model_name
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.default_headers = default_headers
        self.provider_name = provider_name
        self.api_mode = api_mode
        self.reasoning_effort = reasoning_effort
        self.reasoning_context = reasoning_context
        self.reasoning_mode = reasoning_mode
        self.store = store
        self.prompt_cache_mode = prompt_cache_mode
        self.prompt_cache_ttl = prompt_cache_ttl
        self.request_timeout = request_timeout
        if response_state_mode not in {"server", "replay"}:
            raise ValueError("OpenAI response state mode must be server or replay")
        if response_state_max_entries < 1:
            raise ValueError("OpenAI replay state max_entries must be positive")
        self.response_state_mode = response_state_mode
        self.response_state_max_entries = response_state_max_entries
        self._replay_states: OrderedDict[str, list[Dict[str, Any]]] = OrderedDict()

        if not self.api_key:
            logger.warning(
                "%s API key not provided; set %s",
                self.provider_name,
                api_key_env_var,
            )

        if client is not None:
            self.client = client
        else:
            client_kwargs: Dict[str, Any] = {
                "api_key": self.api_key,
                "base_url": self.base_url,
                "timeout": self.timeout,
            }
            if self.default_headers:
                client_kwargs["default_headers"] = self.default_headers
            self.client = AsyncOpenAI(**client_kwargs)

    async def _run(self, request: ModelRunRequest) -> ModelRunResult:
        request_params = self._build_request_params(request)
        try:
            response = await asyncio.wait_for(
                self.client.responses.create(**request_params),
                timeout=self.request_timeout,
            )
        except asyncio.TimeoutError as error:
            raise ModelRunTerminalError(
                f"{self.provider_name} response exceeded request timeout "
                f"of {self.request_timeout} seconds"
            ) from error

        result = self._response_to_run_result(response)
        self._raise_for_terminal_status(response, result)
        replay_input_items = request_params.get("input")
        if self.response_state_mode == "replay" and isinstance(replay_input_items, list):
            self._store_replay_state(
                response_id=result.response_id,
                input_items=replay_input_items,
                response=response,
            )
        return result

    def _build_request_params(self, request: ModelRunRequest) -> Dict[str, Any]:
        reasoning = {
            "effort": self.reasoning_effort,
            "context": self.reasoning_context,
            "mode": self.reasoning_mode,
        }
        if request.reasoning is not None:
            for key in ("effort", "context", "mode"):
                value = getattr(request.reasoning, key)
                if value is not None:
                    reasoning[key] = value

        input_items: list[Dict[str, Any]] = []
        request_params: Dict[str, Any] = {
            "model": self.model_name,
            "reasoning": reasoning,
            "store": self.store,
            "prompt_cache_options": {
                "mode": self.prompt_cache_mode,
                "ttl": self.prompt_cache_ttl,
            },
            "text": {"format": {"type": request.response_format}},
        }

        max_output_tokens = (
            request.max_output_tokens
            if request.max_output_tokens is not None
            else self.max_output_tokens
        )
        if max_output_tokens is not None:
            request_params["max_output_tokens"] = max_output_tokens

        if request.instructions:
            if self.prompt_cache_mode == "explicit":
                input_items.append(
                    self._message_to_response_input(
                        Message.developer(request.instructions),
                        cache_breakpoint=True,
                    )
                )
            else:
                request_params["instructions"] = request.instructions
        input_items.extend(
            self._input_to_response_item(item) for item in request.input
        )
        replay_input_items: list[Dict[str, Any]] | None = None
        if request.previous_response_id and self.response_state_mode == "replay":
            previous_items = self._replay_states.get(request.previous_response_id)
            if previous_items is None:
                raise ModelRunTerminalError(
                    "Unknown replay response state: "
                    f"{request.previous_response_id}"
                )
            self._replay_states.move_to_end(request.previous_response_id)
            input_items = copy.deepcopy(previous_items) + input_items
            replay_input_items = input_items
        elif self.response_state_mode == "replay":
            replay_input_items = input_items
        request_params["input"] = input_items

        temperature = (
            request.temperature
            if request.temperature is not None
            else self.temperature
        )
        if temperature is not None:
            request_params["temperature"] = temperature
        if request.previous_response_id and self.response_state_mode == "server":
            request_params["previous_response_id"] = request.previous_response_id
        if request.prompt_cache_key:
            request_params["prompt_cache_key"] = request.prompt_cache_key
        if request.tools:
            request_params["tools"] = [
                self._function_tool_to_response(tool) for tool in request.tools
            ]

        return request_params

    def _store_replay_state(
        self,
        *,
        response_id: str,
        input_items: list[Dict[str, Any]],
        response: Any,
    ) -> None:
        output_items = [
            self._to_plain_item(item)
            for item in (self._field(response, "output", []) or [])
        ]
        self._replay_states[response_id] = (
            copy.deepcopy(input_items) + output_items
        )
        self._replay_states.move_to_end(response_id)
        while len(self._replay_states) > self.response_state_max_entries:
            self._replay_states.popitem(last=False)

    @classmethod
    def _to_plain_item(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: cls._to_plain_item(item)
                for key, item in value.items()
                if item is not None
            }
        if isinstance(value, (list, tuple)):
            return [cls._to_plain_item(item) for item in value]
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return cls._to_plain_item(model_dump(exclude_none=True))
        if hasattr(value, "__dict__"):
            return {
                key: cls._to_plain_item(item)
                for key, item in vars(value).items()
                if not key.startswith("_") and item is not None
            }
        return value

    @staticmethod
    def _input_to_response_item(item: Any) -> Dict[str, Any]:
        if isinstance(item, Message):
            return OpenAIModel._message_to_response_input(item)
        if isinstance(item, FunctionCallOutput):
            output = item.output
            if not isinstance(output, str):
                output = json.dumps(output, ensure_ascii=False)
            return {
                "type": "function_call_output",
                "call_id": item.call_id,
                "output": output,
            }
        raise TypeError(f"Unsupported Runtime input item: {type(item).__name__}")

    @staticmethod
    def _message_to_response_input(
        message: Message, *, cache_breakpoint: bool = False
    ) -> Dict[str, Any]:
        content: list[Dict[str, Any]] = []
        for item in message.content:
            if isinstance(item, ImageContent):
                content_item: Dict[str, Any] = {
                    "type": "input_image",
                    "image_url": item.image_url,
                    "detail": item.detail,
                }
            else:
                content_item = {"type": "input_text", "text": item.text}
                if cache_breakpoint:
                    content_item["prompt_cache_breakpoint"] = {
                        "mode": "explicit"
                    }
            content.append(content_item)
        return {
            "type": "message",
            "role": message.role,
            "content": content,
        }

    @staticmethod
    def _function_tool_to_response(tool: FunctionTool) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": dict(tool.parameters),
            "strict": tool.strict,
        }

    @classmethod
    def _response_to_run_result(cls, response: Any) -> ModelRunResult:
        items: list[OutputText | FunctionCall] = []
        for output_item in cls._field(response, "output", []) or []:
            item_type = cls._field(output_item, "type")
            if item_type == "function_call":
                raw_arguments = cls._field(output_item, "arguments", "{}")
                try:
                    arguments = json.loads(raw_arguments) if raw_arguments else {}
                except json.JSONDecodeError as error:
                    raise ModelRunTerminalError(
                        "OpenAI returned invalid function-call arguments for "
                        f"{cls._field(output_item, 'name', '<unknown>')}"
                    ) from error
                if not isinstance(arguments, dict):
                    raise ModelRunTerminalError(
                        "OpenAI function-call arguments must be a JSON object"
                    )
                items.append(
                    FunctionCall(
                        call_id=cls._field(output_item, "call_id", ""),
                        name=cls._field(output_item, "name", ""),
                        arguments=arguments,
                        status=cls._field(output_item, "status"),
                    )
                )
                continue

            if item_type != "message":
                continue
            for content in cls._field(output_item, "content", []) or []:
                if cls._field(content, "type") == "output_text":
                    items.append(OutputText(text=cls._field(content, "text", "")))

        usage = cls._field(response, "usage")
        input_details = cls._field(usage, "input_tokens_details")
        output_details = cls._field(usage, "output_tokens_details")
        reasoning = cls._field(response, "reasoning")
        return ModelRunResult(
            response_id=cls._field(response, "id", ""),
            status=cls._field(response, "status", "unknown"),
            model=cls._field(response, "model", ""),
            items=tuple(items),
            usage=ModelUsage(
                input_tokens=cls._field(usage, "input_tokens", 0) or 0,
                output_tokens=cls._field(usage, "output_tokens", 0) or 0,
                total_tokens=cls._field(usage, "total_tokens", 0) or 0,
                cached_tokens=(
                    cls._field(input_details, "cached_tokens", 0) or 0
                ),
                cache_write_tokens=(cls._field(
                    input_details, "cache_write_tokens", 0
                ) or 0),
                reasoning_tokens=(cls._field(
                    output_details, "reasoning_tokens", 0
                ) or 0),
            ),
            reasoning_context=cls._field(reasoning, "context"),
            raw_response=response,
        )

    @classmethod
    def _raise_for_terminal_status(
        cls, response: Any, result: ModelRunResult
    ) -> None:
        if result.status == "completed":
            return
        detail = cls._field(response, "error") or cls._field(
            response, "incomplete_details"
        )
        raise ModelRunTerminalError(
            f"OpenAI response {result.response_id} ended with status "
            f"{result.status}: {detail}"
        )

    @staticmethod
    def _field(value: Any, name: str, default: Any = None) -> Any:
        if value is None:
            return default
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    async def embed(
        self, text: Union[str, List[str]]
    ) -> Union[List[float], List[List[float]]]:
        text_list = [text] if isinstance(text, str) else text
        response = await self.client.embeddings.create(
            model="text-embedding-ada-002",
            input=text_list,
        )
        embeddings = [item.embedding for item in response.data]
        return embeddings[0] if isinstance(text, str) else embeddings

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "OpenAIModel":
        cls._validate_config(config)
        reasoning = config.get("reasoning", {})
        prompt_cache = config.get("prompt_cache", {})
        response_state = config.get("response_state", {})
        return cls(
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
            model_name=config.get("model_name", "gpt-5.6-sol"),
            max_output_tokens=config.get("max_output_tokens"),
            temperature=config.get("temperature", 0.7),
            timeout=config.get("timeout", 600),
            default_headers=config.get("default_headers"),
            api_key_env_var=config.get("api_key_env", "OPENAI_API_KEY"),
            provider_name=config.get("provider_name", "OpenAI"),
            api_mode=config.get("api_mode", "responses"),
            reasoning_effort=reasoning.get("effort", "xhigh"),
            reasoning_context=reasoning.get("context", "auto"),
            reasoning_mode=reasoning.get("mode", "standard"),
            store=config.get("store", True),
            prompt_cache_mode=prompt_cache.get("mode", "explicit"),
            prompt_cache_ttl=prompt_cache.get("ttl", "30m"),
            request_timeout=config.get("request_timeout", 3600),
            response_state_mode=response_state.get("mode", "server"),
            response_state_max_entries=response_state.get("max_entries", 128),
        )

    @classmethod
    def _validate_config(cls, config: Dict[str, Any]) -> None:
        obsolete = sorted(set(config).intersection(cls._OBSOLETE_CONFIG_KEYS))
        if obsolete:
            replacements = ", ".join(
                f"{key}->{cls._OBSOLETE_CONFIG_KEYS[key]}" for key in obsolete
            )
            raise ValueError(f"Obsolete OpenAI configuration keys: {replacements}")

        unknown = sorted(set(config).difference(cls._ALLOWED_CONFIG_KEYS))
        if unknown:
            raise ValueError(
                "Unknown OpenAI configuration keys: " + ", ".join(unknown)
            )
        if config.get("api_mode", "responses") != "responses":
            raise ValueError("OpenAI api_mode must be 'responses'")

        reasoning = config.get("reasoning", {})
        if not isinstance(reasoning, dict):
            raise ValueError("OpenAI reasoning must be a mapping")
        unknown_reasoning = sorted(
            set(reasoning).difference({"effort", "context", "mode"})
        )
        if unknown_reasoning:
            raise ValueError(
                "Unknown OpenAI reasoning keys: "
                + ", ".join(unknown_reasoning)
            )
        if reasoning.get("effort", "xhigh") not in {
            "none",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        }:
            raise ValueError("Unsupported OpenAI reasoning.effort")
        if reasoning.get("context", "auto") not in {
            "auto",
            "current_turn",
            "all_turns",
        }:
            raise ValueError("Unsupported OpenAI reasoning.context")
        if reasoning.get("mode", "standard") not in {"standard", "pro"}:
            raise ValueError("Unsupported OpenAI reasoning.mode")

        prompt_cache = config.get("prompt_cache", {})
        if not isinstance(prompt_cache, dict):
            raise ValueError("OpenAI prompt_cache must be a mapping")
        if set(prompt_cache).difference({"mode", "ttl"}):
            raise ValueError("Unknown OpenAI prompt_cache configuration")
        if prompt_cache.get("mode", "explicit") not in {"implicit", "explicit"}:
            raise ValueError("Unsupported OpenAI prompt_cache.mode")
        if prompt_cache.get("ttl", "30m") != "30m":
            raise ValueError("OpenAI prompt_cache.ttl currently supports only '30m'")

        response_state = config.get("response_state", {})
        if not isinstance(response_state, dict):
            raise ValueError("OpenAI response_state must be a mapping")
        if set(response_state).difference({"mode", "max_entries"}):
            raise ValueError("Unknown OpenAI response_state configuration")
        if response_state.get("mode", "server") not in {"server", "replay"}:
            raise ValueError("Unsupported OpenAI response_state.mode")
        max_entries = response_state.get("max_entries", 128)
        if isinstance(max_entries, bool) or not isinstance(max_entries, int):
            raise ValueError("OpenAI response_state.max_entries must be an integer")
        if max_entries < 1:
            raise ValueError("OpenAI response_state.max_entries must be positive")
