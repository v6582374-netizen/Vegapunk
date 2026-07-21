from __future__ import annotations

import unittest
from types import SimpleNamespace

from vegapunk.mas.models.openai_model import OpenAIModel
from vegapunk.mas.models.runtime import (
    FunctionCallOutput,
    FunctionTool,
    Message,
    ModelRunRequest,
    ReasoningConfig,
)


class _FakeResponses:
    def __init__(self, *, text: str = "The runtime preserved every Responses item.") -> None:
        self.requests: list[dict[str, object]] = []
        self.text = text

    async def create(self, **request: object) -> SimpleNamespace:
        self.requests.append(request)
        return SimpleNamespace(
            id="resp_test",
            status="completed",
            model="gpt-5.6-sol",
            output=[
                SimpleNamespace(
                    type="function_call",
                    call_id="call_search",
                    name="search_papers",
                    arguments='{"query":"typed model runtime"}',
                    status="completed",
                ),
                SimpleNamespace(
                    type="message",
                    content=[
                        SimpleNamespace(
                            type="output_text",
                            text=self.text,
                        )
                    ],
                ),
            ],
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                input_tokens_details=SimpleNamespace(
                    cached_tokens=40,
                    cache_write_tokens=20,
                ),
                output_tokens_details=SimpleNamespace(reasoning_tokens=30),
            ),
            reasoning=SimpleNamespace(context="all_turns"),
        )


class _FakeOpenAIClient:
    def __init__(self, *, text: str = "The runtime preserved every Responses item.") -> None:
        self.responses = _FakeResponses(text=text)


class _FailedResponses:
    async def create(self, **_: object) -> SimpleNamespace:
        return SimpleNamespace(
            id="resp_failed",
            status="failed",
            model="gpt-5.6-sol",
            output=[],
            usage=None,
            reasoning=None,
            error={"code": "server_error", "message": "failed"},
        )


class _FailedOpenAIClient:
    def __init__(self) -> None:
        self.responses = _FailedResponses()


class _ReplayResponses:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    async def create(self, **request: object) -> SimpleNamespace:
        self.requests.append(request)
        if len(self.requests) == 1:
            output = [
                SimpleNamespace(
                    type="function_call",
                    call_id="call_replay",
                    name="lookup_constant",
                    arguments='{"code":"alpha"}',
                    status="completed",
                )
            ]
        else:
            output = [
                SimpleNamespace(
                    type="message",
                    content=[
                        SimpleNamespace(type="output_text", text="VALUE=42")
                    ],
                )
            ]
        return SimpleNamespace(
            id=f"resp_replay_{len(self.requests)}",
            status="completed",
            model="gpt-5.6-sol",
            output=output,
            usage=None,
            reasoning=SimpleNamespace(context="all_turns"),
        )


class _ReplayOpenAIClient:
    def __init__(self) -> None:
        self.responses = _ReplayResponses()


class OpenAIResponsesRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_default_output_token_ceiling_is_omitted(self) -> None:
        client = _FakeOpenAIClient()
        model = OpenAIModel(api_key="test-key", client=client)

        await model.run(
            ModelRunRequest(input=(Message.user("Use the provider default."),))
        )

        self.assertNotIn("max_output_tokens", client.responses.requests[0])

    async def test_run_returns_typed_items_and_usage(self) -> None:
        model = OpenAIModel(
            api_key="test-key",
            model_name="gpt-5.6-sol",
            client=_FakeOpenAIClient(),
        )

        result = await model.run(
            ModelRunRequest(input=(Message.user("Find relevant papers."),))
        )

        self.assertEqual(result.response_id, "resp_test")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.model, "gpt-5.6-sol")
        self.assertEqual(
            result.text, "The runtime preserved every Responses item."
        )
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0].call_id, "call_search")
        self.assertEqual(result.tool_calls[0].name, "search_papers")
        self.assertEqual(
            result.tool_calls[0].arguments,
            {"query": "typed model runtime"},
        )
        self.assertEqual(result.usage.input_tokens, 100)
        self.assertEqual(result.usage.cached_tokens, 40)
        self.assertEqual(result.usage.cache_write_tokens, 20)
        self.assertEqual(result.usage.reasoning_tokens, 30)
        self.assertEqual(result.reasoning_context, "all_turns")

    async def test_run_projects_runtime_policy_to_responses_parameters(self) -> None:
        client = _FakeOpenAIClient()
        model = OpenAIModel(
            api_key="test-key",
            model_name="gpt-5.6-sol",
            max_output_tokens=128000,
            reasoning_effort="xhigh",
            reasoning_context="auto",
            reasoning_mode="standard",
            store=True,
            prompt_cache_mode="explicit",
            prompt_cache_ttl="30m",
            client=client,
        )
        request = ModelRunRequest(
            instructions="Keep the original agent instructions unchanged.",
            input=(Message.user("Return the selected paper as JSON."),),
            tools=(
                FunctionTool(
                    name="select_paper",
                    description="Select one paper.",
                    parameters={
                        "type": "object",
                        "properties": {"paper_id": {"type": "string"}},
                        "required": ["paper_id"],
                    },
                ),
            ),
            response_format="json_object",
            previous_response_id="resp_previous",
            prompt_cache_key="vegapunk:generation:prompt-v1",
            reasoning=ReasoningConfig(mode="pro"),
        )

        await model.run(request)

        sent = client.responses.requests[0]
        self.assertEqual(sent["model"], "gpt-5.6-sol")
        self.assertEqual(sent["max_output_tokens"], 128000)
        self.assertEqual(sent["store"], True)
        self.assertNotIn("background", sent)
        self.assertEqual(sent["previous_response_id"], "resp_previous")
        self.assertEqual(
            sent["reasoning"],
            {"effort": "xhigh", "context": "auto", "mode": "pro"},
        )
        self.assertEqual(
            sent["prompt_cache_options"], {"mode": "explicit", "ttl": "30m"}
        )
        self.assertEqual(
            sent["prompt_cache_key"], "vegapunk:generation:prompt-v1"
        )
        self.assertEqual(sent["text"], {"format": {"type": "json_object"}})
        self.assertEqual(
            sent["tools"],
            [
                {
                    "type": "function",
                    "name": "select_paper",
                    "description": "Select one paper.",
                    "parameters": {
                        "type": "object",
                        "properties": {"paper_id": {"type": "string"}},
                        "required": ["paper_id"],
                    },
                    "strict": False,
                }
            ],
        )
        self.assertEqual(
            sent["input"][0],
            {
                "type": "message",
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Keep the original agent instructions unchanged.",
                        "prompt_cache_breakpoint": {"mode": "explicit"},
                    }
                ],
            },
        )

    async def test_run_sends_tool_results_as_function_call_outputs(self) -> None:
        client = _FakeOpenAIClient()
        model = OpenAIModel(
            api_key="test-key",
            model_name="gpt-5.6-sol",
            client=client,
        )

        await model.run(
            ModelRunRequest(
                input=(
                    FunctionCallOutput(
                        call_id="call_search",
                        output={"papers": ["paper-1"]},
                    ),
                ),
                previous_response_id="resp_with_tool_call",
            )
        )

        sent = client.responses.requests[0]
        self.assertEqual(
            sent["input"],
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_search",
                    "output": '{"papers": ["paper-1"]}',
                }
            ],
        )
        self.assertEqual(
            sent["previous_response_id"], "resp_with_tool_call"
        )

    async def test_replay_state_resends_response_items_without_previous_id(self) -> None:
        client = _ReplayOpenAIClient()
        model = OpenAIModel(
            api_key="test-key",
            response_state_mode="replay",
            client=client,
        )
        tool = FunctionTool(
            name="lookup_constant",
            description="Look up a test constant.",
            parameters={
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        )

        first = await model.run(
            ModelRunRequest(
                input=(Message.user("Use the tool."),),
                tools=(tool,),
            )
        )
        second = await model.run(
            ModelRunRequest(
                input=(
                    FunctionCallOutput(
                        call_id=first.tool_calls[0].call_id,
                        output={"value": 42},
                    ),
                ),
                tools=(tool,),
                previous_response_id=first.response_id,
            )
        )

        self.assertEqual(second.text, "VALUE=42")
        continuation = client.responses.requests[1]
        self.assertNotIn("previous_response_id", continuation)
        self.assertEqual(
            [item["type"] for item in continuation["input"]],
            ["message", "function_call", "function_call_output"],
        )
        self.assertEqual(continuation["input"][1]["call_id"], "call_replay")
        self.assertEqual(continuation["input"][2]["call_id"], "call_replay")

    async def test_replay_state_rejects_an_unknown_local_response(self) -> None:
        model = OpenAIModel(
            api_key="test-key",
            response_state_mode="replay",
            client=_ReplayOpenAIClient(),
        )

        with self.assertRaisesRegex(Exception, "Unknown replay response state"):
            await model.run(
                ModelRunRequest(
                    input=(
                        FunctionCallOutput(
                            call_id="call_missing",
                            output="missing",
                        ),
                    ),
                    previous_response_id="resp_missing",
                )
            )

    async def test_generate_json_uses_json_object_responses_mode(self) -> None:
        client = _FakeOpenAIClient(text='{"paper_id":"paper-1"}')
        model = OpenAIModel(
            api_key="test-key",
            model_name="gpt-5.6-sol",
            client=client,
        )

        result = await model.generate_json(
            prompt="Select one paper.",
            schema={
                "type": "object",
                "properties": {"paper_id": {"type": "string"}},
                "required": ["paper_id"],
            },
            system_prompt="Return the requested selection.",
        )

        self.assertEqual(result, {"paper_id": "paper-1"})
        sent = client.responses.requests[0]
        self.assertEqual(sent["text"], {"format": {"type": "json_object"}})
        self.assertIn(
            "Return the requested selection.", sent["input"][0]["content"][0]["text"]
        )

    async def test_synchronous_responses_do_not_poll_or_submit_background_work(self) -> None:
        client = _FakeOpenAIClient(text="Synchronous response")
        model = OpenAIModel(
            api_key="test-key",
            model_name="gpt-5.6-sol",
            client=client,
        )

        result = await model.run(
            ModelRunRequest(input=(Message.user("Write the final paper."),))
        )

        self.assertEqual(result.text, "Synchronous response")
        self.assertNotIn("background", client.responses.requests[0])

    async def test_failed_terminal_status_does_not_look_successful(self) -> None:
        model = OpenAIModel(
            api_key="test-key",
            client=_FailedOpenAIClient(),
        )

        with self.assertRaisesRegex(Exception, "ended with status failed"):
            await model.run(
                ModelRunRequest(input=(Message.user("Fail explicitly."),))
            )

    async def test_runtime_telemetry_reports_actual_response_fields(self) -> None:
        model = OpenAIModel(
            api_key="test-key",
            client=_FakeOpenAIClient(),
        )
        events: list[dict[str, object]] = []
        model.set_completion_callback(lambda **event: events.append(event))

        await model.run(ModelRunRequest(input=(Message.user("Observe this."),)))

        self.assertEqual(events[0]["model"], "gpt-5.6-sol")
        self.assertEqual(events[0]["response_id"], "resp_test")
        self.assertEqual(events[0]["reasoning_tokens"], 30)
        self.assertEqual(events[0]["cached_tokens"], 40)
        self.assertEqual(events[0]["cache_write_tokens"], 20)

    async def test_null_usage_details_are_normalized_to_zero(self) -> None:
        client = _FakeOpenAIClient()
        response = await client.responses.create()
        response.usage.input_tokens_details.cache_write_tokens = None
        response.usage.output_tokens_details.reasoning_tokens = None

        result = OpenAIModel._response_to_run_result(response)

        self.assertEqual(result.usage.cache_write_tokens, 0)
        self.assertEqual(result.usage.reasoning_tokens, 0)


if __name__ == "__main__":
    unittest.main()
