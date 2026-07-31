"""Responses-native Relay provider tests.

The fake client records the wire request so these tests prove that Relay never
falls through to the Chat Completions API and that canonical engine messages are
translated into Responses input items.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from coworker.providers import AssistantTurn, RelayProvider, ToolCall, capabilities_for


class _FakeResponses:
    def __init__(self, response=None, events=None):
        self.response = response
        self.events = events
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return iter(self.events or [])
        return self.response


class _FakeClient:
    def __init__(self, response=None, events=None):
        self.responses = _FakeResponses(response=response, events=events)


def _message(text: str):
    return SimpleNamespace(
        type="message",
        role="assistant",
        content=[SimpleNamespace(type="output_text", text=text)],
    )


def test_complete_uses_responses_and_translates_tool_history():
    response = SimpleNamespace(
        status="completed",
        output=[
            SimpleNamespace(
                type="function_call",
                call_id="call_2",
                name="read_file",
                arguments='{"path":"a.py"}',
            ),
            _message("done"),
        ],
    )
    client = _FakeClient(response=response)
    provider = RelayProvider(client=client)

    turn = provider.complete(
        model="gpt-5.6-sol",
        messages=[
            {"role": "system", "content": "follow the policy"},
            {"role": "user", "content": "read a.py"},
            {
                "role": "assistant",
                "content": "previous result",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "list_files",
                            "arguments": json.dumps({"recursive": True}),
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "[a.py]"},
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read one file.",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        max_tokens=128,
        reasoning_effort="high",
    )

    sent = client.responses.calls[0]
    assert sent["model"] == "gpt-5.6-sol"
    assert "chat" not in vars(client)
    assert sent["max_output_tokens"] == 128
    assert sent["reasoning"] == {"effort": "high"}
    assert sent["tools"] == [
        {
            "type": "function",
            "name": "read_file",
            "description": "Read one file.",
            "parameters": {"type": "object", "properties": {}},
        }
    ]
    assert [item["type"] for item in sent["input"]] == [
        "message",
        "message",
        "message",
        "function_call",
        "function_call_output",
    ]
    assert sent["input"][0]["role"] == "system"
    assert sent["input"][2] == {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "input_text", "text": "previous result"}],
    }
    assert sent["input"][3] == {
        "type": "function_call",
        "call_id": "call_1",
        "name": "list_files",
        "arguments": '{"recursive": true}',
        "status": "completed",
    }
    assert sent["input"][4] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": "[a.py]",
    }
    assert turn == AssistantTurn(
        text="done",
        tool_calls=[ToolCall("call_2", "read_file", {"path": "a.py"})],
        finish_reason="completed",
        raw=response,
    )


def test_complete_maps_structured_output_settings_to_responses_text_format():
    client = _FakeClient(response=SimpleNamespace(status="completed", output=[]))
    RelayProvider(client=client).complete(
        model="custom-text-model",
        messages=[{"role": "user", "content": "return json"}],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "answer",
                "schema": {"type": "object", "properties": {}},
                "strict": True,
            },
        },
    )
    assert client.responses.calls[0]["text"] == {
        "format": {
            "type": "json_schema",
            "name": "answer",
            "schema": {"type": "object", "properties": {}},
            "strict": True,
        }
    }


def test_stream_surfaces_text_reasoning_and_function_call_deltas():
    events = [
        SimpleNamespace(type="response.reasoning_text.delta", delta="think "),
        SimpleNamespace(type="response.output_text.delta", delta="Hel"),
        SimpleNamespace(
            type="response.output_item.added",
            item=SimpleNamespace(
                type="function_call",
                id="fc_item",
                call_id="call_3",
                name="read_file",
                arguments="",
            ),
            output_index=0,
        ),
        SimpleNamespace(
            type="response.function_call_arguments.delta",
            delta='{"path":',
            output_index=0,
            item_id="fc_item",
        ),
        SimpleNamespace(
            type="response.function_call_arguments.delta",
            delta='"a.py"}',
            output_index=0,
            item_id="fc_item",
        ),
        SimpleNamespace(type="response.output_text.delta", delta="lo"),
        SimpleNamespace(
            type="response.output_item.done",
            item=SimpleNamespace(
                type="function_call",
                id="fc_item",
                call_id="call_3",
                name="read_file",
                arguments='{"path":"a.py"}',
            ),
            output_index=0,
        ),
        SimpleNamespace(
            type="response.completed",
            response=SimpleNamespace(status="completed", output=[]),
        ),
    ]
    provider = RelayProvider(client=_FakeClient(events=events))

    chunks = list(provider.stream(model="gpt-5.6-sol", messages=[]))
    assert [chunk.reasoning_delta for chunk in chunks if chunk.reasoning_delta] == [
        "think "
    ]
    assert [chunk.text_delta for chunk in chunks if chunk.text_delta] == ["Hel", "lo"]
    final = chunks[-1].turn
    assert final is not None
    assert final.text == "Hello"
    assert final.reasoning == "think "
    assert final.tool_calls == [ToolCall("call_3", "read_file", {"path": "a.py"})]


def test_relay_client_resolves_its_own_key_and_endpoint(monkeypatch):
    captured: dict = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    RelayProvider(api_key="relay-key", base_url="https://relay.example/v1/")._ensure_client()
    assert captured == {
        "api_key": "relay-key",
        "base_url": "https://relay.example/v1",
    }


def test_relay_client_does_not_use_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.delenv("RELAY_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Relay API key"):
        RelayProvider()._ensure_client()


def test_relay_registry_uses_own_profile_and_recommended_model():
    from coworker.providers.registry import RELAY_BASE_URL, build_provider_client, get_descriptor

    descriptor = get_descriptor("relay")
    assert descriptor is not None
    assert descriptor.recommended_model == "gpt-5.6-sol"
    endpoint = "https://relay.example/v1"
    client = build_provider_client(
        "relay", {"api_key": "relay-key", "base_url": endpoint}, secrets=None
    )
    assert isinstance(client, RelayProvider)
    assert client._api_key == "relay-key"
    assert client._base_url == endpoint
    assert (
        next(field for field in descriptor.fields if field.key == "base_url").default
        == RELAY_BASE_URL
    )


def test_relay_custom_models_keep_agent_capabilities():
    caps = capabilities_for("relay:my-text-model")
    assert caps.tools and caps.parallel_tool_calls and caps.streaming
    assert not caps.vision and not caps.pdf
