"""Runtime adapter for providers that expose only Chat Completions semantics."""

from __future__ import annotations

import json
import logging
import os
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Union

from openai import AsyncOpenAI

from .base_model import BaseModel, UnsupportedModelCapabilityError
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


class ChatCompatibleModel(BaseModel):
    """Implement the supported Runtime subset over a Chat-compatible gateway."""

    def __init__(
        self,
        *,
        api_key: Optional[str],
        base_url: Optional[str],
        model_name: str,
        max_output_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: int = 600,
        default_headers: Optional[Dict[str, str]] = None,
        api_mode: str = "chat_completions",
        api_key_env_var: str,
        base_url_env_var: str,
        provider_name: str,
        embedding_model: str = "text-embedding-ada-002",
        strip_reasoning_tags: bool = False,
        client: Optional[Any] = None,
    ) -> None:
        super().__init__()
        if api_mode != "chat_completions":
            raise ValueError(
                f"{provider_name} requires api_mode='chat_completions'"
            )

        self.api_key = api_key or os.environ.get(api_key_env_var)
        self.base_url = base_url or os.environ.get(base_url_env_var)
        self.model_name = model_name
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.default_headers = default_headers
        self.api_mode = api_mode
        self.provider_name = provider_name
        self.embedding_model = embedding_model
        self.strip_reasoning_tags = strip_reasoning_tags
        self._conversation_states: OrderedDict[str, list[dict[str, Any]]] = (
            OrderedDict()
        )
        self._max_conversation_states = 1024

        if not self.api_key:
            logger.warning(
                "%s API key not provided; set %s",
                provider_name,
                api_key_env_var,
            )
        if not self.base_url:
            logger.warning(
                "%s base URL not provided; set %s",
                provider_name,
                base_url_env_var,
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
        self._validate_supported_request(request)
        messages = self._build_messages(request)
        params: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": (
                request.temperature
                if request.temperature is not None
                else self.temperature
            ),
            "max_tokens": (
                request.max_output_tokens
                if request.max_output_tokens is not None
                else self.max_output_tokens
            ),
        }
        if request.response_format == "json_object":
            params["response_format"] = {"type": "json_object"}
        if request.tools:
            params["tools"] = [self._function_tool_to_chat(tool) for tool in request.tools]
            params["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(**params)
        choice = response.choices[0]
        message = choice.message
        raw_text = self._field(message, "content") or ""
        text = self._normalize_text(raw_text)
        items: list[OutputText | FunctionCall] = []
        if text:
            items.append(OutputText(text=text))
        for tool_call in self._field(message, "tool_calls", []) or []:
            function = self._field(tool_call, "function")
            raw_arguments = self._field(function, "arguments", "{}")
            arguments = json.loads(raw_arguments) if raw_arguments else {}
            if not isinstance(arguments, dict):
                raise ValueError("Chat function-call arguments must be a JSON object")
            items.append(
                FunctionCall(
                    call_id=self._field(tool_call, "id", ""),
                    name=self._field(function, "name", ""),
                    arguments=arguments,
                    status="completed",
                )
            )

        response_id = self._field(response, "id", "")
        if not response_id:
            raise ValueError(f"{self.provider_name} returned no response ID")
        stored_messages = [*messages, self._assistant_message_to_dict(message)]
        self._store_state(response_id, stored_messages)

        usage = self._field(response, "usage")
        input_tokens = self._field(usage, "prompt_tokens", 0)
        output_tokens = self._field(usage, "completion_tokens", 0)
        return ModelRunResult(
            response_id=response_id,
            status="completed",
            model=self._field(response, "model", self.model_name),
            items=tuple(items),
            usage=ModelUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=self._field(
                    usage, "total_tokens", input_tokens + output_tokens
                ),
            ),
            raw_response=response,
        )

    def _validate_supported_request(self, request: ModelRunRequest) -> None:
        unsupported = []
        if request.reasoning is not None:
            unsupported.append("reasoning")
        if request.background:
            unsupported.append("background")
        if request.prompt_cache_key:
            unsupported.append("prompt_cache_key")
        if unsupported:
            raise UnsupportedModelCapabilityError(
                f"{self.provider_name} Chat adapter does not support Runtime "
                f"capabilities: {', '.join(unsupported)}"
            )

    def _build_messages(self, request: ModelRunRequest) -> list[dict[str, Any]]:
        if request.previous_response_id:
            previous = self._conversation_states.get(request.previous_response_id)
            if previous is None:
                raise UnsupportedModelCapabilityError(
                    f"Unknown or expired Chat continuation ID: "
                    f"{request.previous_response_id}"
                )
            messages = [dict(message) for message in previous]
        else:
            messages = []
            if request.instructions:
                messages.append({"role": "system", "content": request.instructions})

        for item in request.input:
            if isinstance(item, FunctionCallOutput):
                output = item.output
                if not isinstance(output, str):
                    output = json.dumps(output, ensure_ascii=False)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": item.call_id,
                        "content": output,
                    }
                )
            elif isinstance(item, Message):
                messages.append(self._runtime_message_to_chat(item))
            else:
                raise TypeError(
                    f"Unsupported Runtime input item: {type(item).__name__}"
                )
        return messages

    @staticmethod
    def _runtime_message_to_chat(message: Message) -> dict[str, Any]:
        role = "system" if message.role == "developer" else message.role
        if all(not isinstance(item, ImageContent) for item in message.content):
            return {
                "role": role,
                "content": "\n".join(item.text for item in message.content),
            }

        content: list[dict[str, Any]] = []
        for item in message.content:
            if isinstance(item, ImageContent):
                if item.detail == "original":
                    raise UnsupportedModelCapabilityError(
                        "Chat-compatible adapters do not support original image detail"
                    )
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": item.image_url,
                            "detail": item.detail,
                        },
                    }
                )
            else:
                content.append({"type": "text", "text": item.text})
        return {"role": role, "content": content}

    @staticmethod
    def _function_tool_to_chat(tool: FunctionTool) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": dict(tool.parameters),
                "strict": tool.strict,
            },
        }

    @classmethod
    def _assistant_message_to_dict(cls, message: Any) -> dict[str, Any]:
        if hasattr(message, "model_dump"):
            dumped = message.model_dump(exclude_none=True)
            return dict(dumped)
        result: dict[str, Any] = {
            "role": "assistant",
            "content": cls._field(message, "content"),
        }
        tool_calls = cls._field(message, "tool_calls")
        if tool_calls:
            result["tool_calls"] = [
                tool_call.model_dump(exclude_none=True)
                if hasattr(tool_call, "model_dump")
                else tool_call
                for tool_call in tool_calls
            ]
        return result

    def _normalize_text(self, text: str) -> str:
        if self.strip_reasoning_tags and "</think>" in text:
            return text.split("</think>", 1)[1].strip()
        return text

    def _store_state(
        self, response_id: str, messages: list[dict[str, Any]]
    ) -> None:
        self._conversation_states[response_id] = messages
        self._conversation_states.move_to_end(response_id)
        while len(self._conversation_states) > self._max_conversation_states:
            self._conversation_states.popitem(last=False)

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
            model=self.embedding_model,
            input=text_list,
        )
        embeddings = [item.embedding for item in response.data]
        return embeddings[0] if isinstance(text, str) else embeddings

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "ChatCompatibleModel":
        raise NotImplementedError("Use a concrete Chat-compatible provider adapter")
