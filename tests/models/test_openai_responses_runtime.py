from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from internagent.mas.models.base_model import ModelError
from internagent.mas.models.openai_model import OpenAIModel
from internagent.mas.models.runtime import (
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


class _BackgroundResponses:
    def __init__(self) -> None:
        self.create_count = 0
        self.retrieve_count = 0

    async def create(self, **_: object) -> SimpleNamespace:
        self.create_count += 1
        return SimpleNamespace(
            id="resp_background",
            status="in_progress",
            model="gpt-5.6-sol",
            output=[],
            usage=None,
            reasoning=None,
        )

    async def retrieve(self, response_id: str) -> SimpleNamespace:
        self.retrieve_count += 1
        self.last_response_id = response_id
        return SimpleNamespace(
            id=response_id,
            status="completed",
            model="gpt-5.6-sol",
            output=[
                SimpleNamespace(
                    type="message",
                    content=[
                        SimpleNamespace(type="output_text", text="Final paper")
                    ],
                )
            ],
            usage=None,
            reasoning=None,
        )


class _BackgroundOpenAIClient:
    def __init__(self) -> None:
        self.responses = _BackgroundResponses()


class _RecordingResponseCheckpoint:
    def __init__(self) -> None:
        self.responses: dict[str, dict[str, str]] = {}
        self.history: list[tuple[str, str, str]] = []

    def get_model_response(self, checkpoint_key: str) -> dict[str, str] | None:
        return self.responses.get(checkpoint_key)

    def record_model_response(
        self, *, checkpoint_key: str, response_id: str, status: str
    ) -> None:
        self.responses[checkpoint_key] = {
            "response_id": response_id,
            "status": status,
        }
        self.history.append((checkpoint_key, response_id, status))


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
            prompt_cache_key="internagent:generation:prompt-v1",
            reasoning=ReasoningConfig(mode="pro"),
            background=True,
        )

        await model.run(request)

        sent = client.responses.requests[0]
        self.assertEqual(sent["model"], "gpt-5.6-sol")
        self.assertEqual(sent["max_output_tokens"], 128000)
        self.assertEqual(sent["store"], True)
        self.assertEqual(sent["background"], True)
        self.assertEqual(sent["previous_response_id"], "resp_previous")
        self.assertEqual(
            sent["reasoning"],
            {"effort": "xhigh", "context": "auto", "mode": "pro"},
        )
        self.assertEqual(
            sent["prompt_cache_options"], {"mode": "explicit", "ttl": "30m"}
        )
        self.assertEqual(
            sent["prompt_cache_key"], "internagent:generation:prompt-v1"
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

    async def test_run_waits_for_a_background_response_to_complete(self) -> None:
        client = _BackgroundOpenAIClient()
        model = OpenAIModel(
            api_key="test-key",
            model_name="gpt-5.6-sol",
            background_poll_interval=0,
            client=client,
        )

        result = await model.run(
            ModelRunRequest(
                input=(Message.user("Write the final paper."),),
                background=True,
            )
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.text, "Final paper")
        self.assertEqual(client.responses.retrieve_count, 1)
        self.assertEqual(
            client.responses.last_response_id, "resp_background"
        )

    async def test_background_run_resumes_checkpointed_response_id(self) -> None:
        client = _BackgroundOpenAIClient()
        model = OpenAIModel(
            api_key="test-key",
            model_name="gpt-5.6-sol",
            background_poll_interval=0,
            client=client,
        )
        checkpoint = _RecordingResponseCheckpoint()
        checkpoint.record_model_response(
            checkpoint_key="write_remaining_sections",
            response_id="resp_background",
            status="submitted",
        )

        with model.bind_response_checkpoint(checkpoint):
            result = await model.run(
                ModelRunRequest(
                    input=(Message.user("Resume the final paper."),),
                    background=True,
                    checkpoint_key="write_remaining_sections",
                )
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(client.responses.create_count, 0)
        self.assertEqual(client.responses.retrieve_count, 1)
        self.assertEqual(
            checkpoint.responses["write_remaining_sections"],
            {"response_id": "resp_background", "status": "completed"},
        )

    async def test_background_run_records_id_before_polling(self) -> None:
        client = _BackgroundOpenAIClient()
        model = OpenAIModel(
            api_key="test-key",
            background_poll_interval=0,
            client=client,
        )
        checkpoint = _RecordingResponseCheckpoint()

        with model.bind_response_checkpoint(checkpoint):
            await model.run(
                ModelRunRequest(
                    input=(Message.user("Start the final paper."),),
                    background=True,
                    checkpoint_key="generate_outline",
                )
            )

        self.assertEqual(
            checkpoint.history,
            [
                ("generate_outline", "resp_background", "submitted"),
                ("generate_outline", "resp_background", "completed"),
            ],
        )

    async def test_checkpoint_binding_is_isolated_per_async_task(self) -> None:
        model = OpenAIModel(
            api_key="test-key",
            client=_FakeOpenAIClient(),
        )
        first = _RecordingResponseCheckpoint()
        second = _RecordingResponseCheckpoint()

        async def bound_checkpoint(checkpoint):
            with model.bind_response_checkpoint(checkpoint):
                await asyncio.sleep(0)
                return model.current_response_checkpoint()

        observed = await asyncio.gather(
            bound_checkpoint(first),
            bound_checkpoint(second),
        )

        self.assertEqual(observed, [first, second])
        self.assertIsNone(model.current_response_checkpoint())

    async def test_background_mode_rejects_store_false(self) -> None:
        model = OpenAIModel(
            api_key="test-key",
            store=False,
            client=_BackgroundOpenAIClient(),
        )

        with self.assertRaisesRegex(ModelError, "require store=true"):
            await model.run(
                ModelRunRequest(
                    input=(Message.user("Do not submit this."),),
                    background=True,
                )
            )

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
