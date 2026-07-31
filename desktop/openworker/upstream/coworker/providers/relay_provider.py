"""Responses-native client for the project's Relay model provider.

Relay deliberately has its own adapter instead of going through
``OpenAIProvider``.  The two APIs have different input items and tool schemas,
so sharing the Chat Completions path would make a valid Relay configuration
look configured while failing as soon as a tool call or a resumed turn arrived.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from .base import AssistantTurn, ModelCapabilities, ProviderClient, StreamChunk, ToolCall
from .capabilities import capabilities_for

DEFAULT_RELAY_BASE_URL = "https://ai.cloudyz.top/v1"


def resolve_relay_api_key(secrets: Any = None) -> Optional[str]:
    """Resolve only Relay credentials, never the OpenAI credential."""
    key = os.environ.get("RELAY_API_KEY", "").strip()
    if key:
        return key
    if secrets is not None:
        profile = secrets.get("provider:relay") or {}
        value = profile.get("api_key")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {"_raw": raw}
    return parsed if isinstance(parsed, dict) else {"_raw": raw}


def _string_output(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def _input_text_parts(content: Any) -> list[dict[str, Any]]:
    """Convert canonical OpenAI content into text-only Responses input parts."""
    if isinstance(content, str):
        return [{"type": "input_text", "text": content}] if content else []
    if not isinstance(content, list):
        return [{"type": "input_text", "text": str(content)}] if content else []

    parts: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        kind = part.get("type")
        if kind == "text":
            text = part.get("text") or ""
            if text:
                parts.append({"type": "input_text", "text": text})
        elif kind == "input_text":
            text = part.get("text") or ""
            if text:
                parts.append({"type": "input_text", "text": text})
        elif kind == "image_url":
            # Relay V1 is a text provider. Engine capability gating normally replaces this
            # before the adapter is called; keep a safe fallback for direct callers.
            parts.append(
                {"type": "input_text", "text": "[image attachment - not viewable by this model]"}
            )
        elif kind == "file":
            parts.append(
                {"type": "input_text", "text": "[file attachment - not viewable by this model]"}
            )
    return parts


def _convert_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert the engine's canonical history into Responses input items."""
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role in ("system", "developer", "user"):
            content = _input_text_parts(message.get("content"))
            if content:
                converted.append(
                    {"type": "message", "role": role, "content": content}
                )
            continue

        if role == "assistant":
            text = message.get("content")
            if isinstance(text, str) and text:
                converted.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "input_text", "text": text}],
                    }
                )
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                name = function.get("name") or ""
                arguments = function.get("arguments")
                if not isinstance(arguments, str):
                    arguments = json.dumps(arguments or {}, default=str)
                converted.append(
                    {
                        "type": "function_call",
                        "call_id": call.get("id") or "",
                        "name": name,
                        "arguments": arguments,
                        "status": "completed",
                    }
                )
            continue

        if role == "tool":
            converted.append(
                {
                    "type": "function_call_output",
                    "call_id": message.get("tool_call_id") or "",
                    "output": _string_output(message.get("content") or ""),
                }
            )

    return converted


def _convert_tools(tools: Optional[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Convert Chat Completions-shaped function schemas to Responses tools."""
    converted: list[dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        function = tool.get("function") or {}
        item: dict[str, Any] = {
            "type": "function",
            "name": function.get("name") or "",
        }
        for key in ("description", "parameters", "strict"):
            if key in function and function[key] is not None:
                item[key] = function[key]
            elif key in tool and tool[key] is not None:
                item[key] = tool[key]
        converted.append(item)
    return converted


def _responses_text_settings(settings: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Translate Chat Completions response_format into Responses text.format."""
    direct = settings.get("text")
    if isinstance(direct, dict):
        return direct

    response_format = settings.get("response_format")
    if not isinstance(response_format, dict):
        return None
    format_type = response_format.get("type")
    if format_type == "json_object":
        return {"format": {"type": "json_object"}}
    if format_type != "json_schema":
        return None

    source = response_format.get("json_schema")
    if not isinstance(source, dict):
        source = response_format
    format_spec: dict[str, Any] = {"type": "json_schema"}
    for key in ("name", "description", "schema", "strict"):
        if key in source and source[key] is not None:
            format_spec[key] = source[key]
    return {"format": format_spec}


def _request_kwargs(
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: Optional[list[dict[str, Any]]],
    settings: dict[str, Any],
    stream: bool = False,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model,
        "input": _convert_messages(messages),
    }
    converted_tools = _convert_tools(tools)
    if converted_tools:
        kwargs["tools"] = converted_tools

    if "max_output_tokens" in settings:
        kwargs["max_output_tokens"] = settings["max_output_tokens"]
    elif "max_tokens" in settings:
        kwargs["max_output_tokens"] = settings["max_tokens"]
    for key in ("temperature", "top_p", "parallel_tool_calls", "top_logprobs"):
        if key in settings and settings[key] is not None:
            kwargs[key] = settings[key]

    reasoning = settings.get("reasoning")
    if isinstance(reasoning, dict):
        kwargs["reasoning"] = dict(reasoning)
    elif settings.get("reasoning_effort") is not None:
        kwargs["reasoning"] = {"effort": settings["reasoning_effort"]}

    text_settings = _responses_text_settings(settings)
    if text_settings is not None:
        kwargs["text"] = text_settings

    if stream:
        kwargs["stream"] = True
    return kwargs


def _response_tool_calls(response: Any) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for item in _value(response, "output", []) or []:
        if _value(item, "type") != "function_call":
            continue
        calls.append(
            ToolCall(
                id=_value(item, "call_id", "") or "",
                name=_value(item, "name", "") or "",
                arguments=_parse_args(_value(item, "arguments")),
            )
        )
    return calls


def _response_text(response: Any) -> Optional[str]:
    parts: list[str] = []
    for item in _value(response, "output", []) or []:
        if _value(item, "type") != "message":
            continue
        for content in _value(item, "content", []) or []:
            if _value(content, "type") == "output_text":
                text = _value(content, "text", "") or ""
                if text:
                    parts.append(text)
    if parts:
        return "".join(parts)
    text = _value(response, "output_text")
    return text if isinstance(text, str) and text else None


def _response_reasoning(response: Any) -> Optional[str]:
    parts: list[str] = []
    for item in _value(response, "output", []) or []:
        if _value(item, "type") != "reasoning":
            continue
        for summary in _value(item, "summary", []) or []:
            text = _value(summary, "text", "") or ""
            if text:
                parts.append(text)
        for content in _value(item, "content", []) or []:
            text = _value(content, "text", "") or ""
            if text:
                parts.append(text)
    return "".join(parts) or None


def _response_finish_reason(response: Any) -> Optional[str]:
    status = _value(response, "status")
    if status == "incomplete":
        details = _value(response, "incomplete_details")
        return _value(details, "reason", "incomplete") or "incomplete"
    return status


def _raise_failed(response: Any) -> None:
    if _value(response, "status") != "failed":
        return
    error = _value(response, "error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("code")
    else:
        message = _value(error, "message") or error
    raise RuntimeError(f"Relay Responses request failed{': ' + str(message) if message else ''}")


def _response_to_turn(response: Any) -> AssistantTurn:
    _raise_failed(response)
    return AssistantTurn(
        text=_response_text(response),
        tool_calls=_response_tool_calls(response),
        finish_reason=_response_finish_reason(response),
        raw=response,
        reasoning=_response_reasoning(response),
    )


def _merge_stream_call(calls: dict[str, dict[str, str]], item: Any, key: str) -> None:
    if _value(item, "type") != "function_call":
        return
    acc = calls.setdefault(key, {"id": "", "name": "", "arguments": ""})
    for source, target in (("call_id", "id"), ("name", "name"), ("arguments", "arguments")):
        value = _value(item, source)
        if value is not None and value != "":
            acc[target] = str(value)


def _stream_turn(
    *,
    response: Any,
    text_parts: list[str],
    reasoning_parts: list[str],
    calls: dict[str, dict[str, str]],
) -> AssistantTurn:
    parsed = _response_to_turn(response) if response is not None else AssistantTurn()
    call_list = [
        ToolCall(
            id=value["id"],
            name=value["name"],
            arguments=_parse_args(value["arguments"]),
        )
        for value in calls.values()
    ]
    return AssistantTurn(
        text="".join(text_parts) or parsed.text,
        tool_calls=call_list or parsed.tool_calls,
        finish_reason=parsed.finish_reason or ("completed" if response is not None else None),
        raw=response,
        reasoning="".join(reasoning_parts) or parsed.reasoning,
    )


class RelayProvider(ProviderClient):
    """A blocking ProviderClient backed only by ``client.responses``."""

    def __init__(
        self,
        client: Any = None,
        *,
        default_model: str = "gpt-5.6-sol",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        secrets: Any = None,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._base_url = (base_url or DEFAULT_RELAY_BASE_URL).strip().rstrip("/")
        self._secrets = secrets
        self.default_model = default_model

    def _ensure_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            key = self._api_key or resolve_relay_api_key(self._secrets)
            if not key:
                raise RuntimeError(
                    "No Relay API key configured. Set RELAY_API_KEY in the environment, "
                    "or add your key in Settings → Models."
                )
            self._client = OpenAI(api_key=key, base_url=self._base_url)
        return self._client

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        **settings: Any,
    ) -> AssistantTurn:
        kwargs = _request_kwargs(
            model=model, messages=messages, tools=tools, settings=settings
        )
        response = self._ensure_client().responses.create(**kwargs)
        return _response_to_turn(response)

    def stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        **settings: Any,
    ):
        kwargs = _request_kwargs(
            model=model, messages=messages, tools=tools, settings=settings, stream=True
        )
        events = self._ensure_client().responses.create(**kwargs)
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        calls: dict[str, dict[str, str]] = {}
        response = None

        for event in events:
            kind = _value(event, "type")
            if kind == "response.output_text.delta":
                delta = _value(event, "delta", "") or ""
                if delta:
                    text_parts.append(delta)
                    yield StreamChunk(text_delta=delta)
            elif kind in (
                "response.reasoning_text.delta",
                "response.reasoning_summary_text.delta",
            ):
                delta = _value(event, "delta", "") or ""
                if delta:
                    reasoning_parts.append(delta)
                    yield StreamChunk(reasoning_delta=delta)
            elif kind == "response.output_item.added":
                item = _value(event, "item")
                key = str(_value(event, "output_index", _value(item, "id", len(calls))))
                _merge_stream_call(calls, item, key)
            elif kind == "response.function_call_arguments.delta":
                item_id = _value(event, "item_id")
                key = str(_value(event, "output_index", item_id or len(calls)))
                acc = calls.setdefault(key, {"id": "", "name": "", "arguments": ""})
                if item_id and not acc["id"]:
                    acc["id"] = str(item_id)
                acc["arguments"] += str(_value(event, "delta", "") or "")
            elif kind == "response.function_call_arguments.done":
                item_id = _value(event, "item_id")
                key = str(_value(event, "output_index", item_id or len(calls)))
                acc = calls.setdefault(key, {"id": "", "name": "", "arguments": ""})
                arguments = _value(event, "arguments")
                if arguments is not None:
                    acc["arguments"] = str(arguments)
            elif kind == "response.output_item.done":
                item = _value(event, "item")
                key = str(_value(event, "output_index", _value(item, "id", len(calls))))
                _merge_stream_call(calls, item, key)
            elif kind == "response.completed":
                response = _value(event, "response")
                break
            elif kind == "response.failed":
                response = _value(event, "response")
                if response is not None:
                    _raise_failed(response)
                raise RuntimeError("Relay Responses request failed")

        yield StreamChunk(
            turn=_stream_turn(
                response=response,
                text_parts=text_parts,
                reasoning_parts=reasoning_parts,
                calls=calls,
            )
        )

    def capabilities(self, model: str) -> ModelCapabilities:
        return capabilities_for(model)
