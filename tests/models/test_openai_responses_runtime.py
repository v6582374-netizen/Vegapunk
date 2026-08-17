from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace

import httpx

from vegapunk.mas.models.openai_model import OpenAIModel
from vegapunk.mas.models.runtime import (
    FunctionCallOutput,
    FunctionTool,
    ImageContent,
    Message,
    ModelRunRequest,
    ReasoningConfig,
    TextContent,
)


def _accept_encoding_on_the_wire(model: OpenAIModel) -> str:
    """Read the header the SDK will actually send.

    Per-client overrides are merged when a request is built, not onto the
    underlying transport's own defaults, so the built request is the only
    honest place to observe what a Provider will really receive.
    """

    from openai._models import FinalRequestOptions

    request = model.client._build_request(
        FinalRequestOptions.construct(
            method="post", url="/responses", json_data={"model": "m"}
        )
    )
    return request.headers["accept-encoding"]


class _FakeEventStream:
    """Async-iterable stand-in for one streamed Responses run."""

    def __init__(self, events: list[object]) -> None:
        self._events = list(events)
        self.closed = False

    def __aiter__(self) -> "_FakeEventStream":
        return self

    async def __anext__(self) -> object:
        if not self._events:
            raise StopAsyncIteration
        event = self._events.pop(0)
        if callable(event):
            return await event()
        return event

    async def close(self) -> None:
        self.closed = True


def _completed(response: object) -> SimpleNamespace:
    return SimpleNamespace(type="response.completed", response=response)


def _delta(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="response.output_text.delta", delta=text)


class _FakeResponses:
    def __init__(self, *, text: str = "The runtime preserved every Responses item.") -> None:
        self.requests: list[dict[str, object]] = []
        self.text = text
        self.streams: list[_FakeEventStream] = []

    async def create(self, **request: object) -> _FakeEventStream:
        self.requests.append(request)
        response = SimpleNamespace(
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
        stream = _FakeEventStream([_delta(self.text), _completed(response)])
        self.streams.append(stream)
        return stream


class _FakeOpenAIClient:
    def __init__(self, *, text: str = "The runtime preserved every Responses item.") -> None:
        self.responses = _FakeResponses(text=text)


class _FailedResponses:
    async def create(self, **_: object) -> _FakeEventStream:
        return _FakeEventStream(
            [
                _completed(
                    SimpleNamespace(
                        id="resp_failed",
                        status="failed",
                        model="gpt-5.6-sol",
                        output=[],
                        usage=None,
                        reasoning=None,
                        error={"code": "server_error", "message": "failed"},
                    )
                )
            ]
        )


class _FailedOpenAIClient:
    def __init__(self) -> None:
        self.responses = _FailedResponses()


class _SilentResponses:
    """A stream that connects and then never says anything again."""

    async def create(self, **_: object) -> _FakeEventStream:
        async def never() -> object:
            await asyncio.sleep(3600)
            raise AssertionError("unreachable")

        self.stream = _FakeEventStream([never])
        return self.stream


class _SilentOpenAIClient:
    def __init__(self) -> None:
        self.responses = _SilentResponses()


class _HeartbeatResponses:
    """Slow but alive: many quiet gaps, none of them longer than the bound."""

    def __init__(self, *, beats: int, gap: float, text: str) -> None:
        self.beats = beats
        self.gap = gap
        self.text = text

    async def create(self, **_: object) -> _FakeEventStream:
        async def beat() -> object:
            await asyncio.sleep(self.gap)
            return _delta("...")

        async def final() -> object:
            await asyncio.sleep(self.gap)
            return _completed(
                SimpleNamespace(
                    id="resp_slow",
                    status="completed",
                    model="gpt-5.6-sol",
                    output=[
                        SimpleNamespace(
                            type="message",
                            content=[
                                SimpleNamespace(
                                    type="output_text", text=self.text
                                )
                            ],
                        )
                    ],
                    usage=None,
                    reasoning=None,
                )
            )

        return _FakeEventStream([beat] * self.beats + [final])


class _HeartbeatOpenAIClient:
    def __init__(self, *, beats: int, gap: float, text: str) -> None:
        self.responses = _HeartbeatResponses(beats=beats, gap=gap, text=text)


class _ErrorEventResponses:
    async def create(self, **_: object) -> _FakeEventStream:
        return _FakeEventStream(
            [
                SimpleNamespace(
                    type="error",
                    code="upstream_gone",
                    message="upstream closed the connection",
                )
            ]
        )


class _ErrorEventOpenAIClient:
    def __init__(self) -> None:
        self.responses = _ErrorEventResponses()


class _ReplayResponses:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    async def create(self, **request: object) -> _FakeEventStream:
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
        return _FakeEventStream(
            [
                _completed(
                    SimpleNamespace(
                        id=f"resp_replay_{len(self.requests)}",
                        status="completed",
                        model="gpt-5.6-sol",
                        output=output,
                        usage=None,
                        reasoning=SimpleNamespace(context="all_turns"),
                    )
                )
            ]
        )


class _ReplayOpenAIClient:
    def __init__(self) -> None:
        self.responses = _ReplayResponses()


def _item_done(index: int, item: object) -> SimpleNamespace:
    return SimpleNamespace(
        type="response.output_item.done", output_index=index, item=item
    )


class _EmptyTerminalSnapshotResponses:
    """A gateway that delivers items only in the stream.

    Some Responses gateways treat ``response.output_item.done`` as the single
    delivery of an assembled item and leave ``output`` empty on the terminal
    snapshot.  For them the stream is the authoritative record of the run.
    """

    def __init__(self, *, text: str = "Only the stream carried this.") -> None:
        self.text = text
        self.requests: list[dict[str, object]] = []

    async def create(self, **request: object) -> _FakeEventStream:
        self.requests.append(request)
        message = SimpleNamespace(
            type="message",
            role="assistant",
            status="completed",
            content=[SimpleNamespace(type="output_text", text=self.text)],
        )
        call = SimpleNamespace(
            type="function_call",
            call_id="call_stream",
            name="search_papers",
            arguments='{"query":"streamed only"}',
            status="completed",
        )
        terminal = SimpleNamespace(
            id="resp_stream_only",
            status="completed",
            model="gpt-5.6-sol",
            output=[],
            usage=SimpleNamespace(
                input_tokens=11,
                output_tokens=7,
                total_tokens=18,
                input_tokens_details=SimpleNamespace(
                    cached_tokens=0, cache_write_tokens=0
                ),
                output_tokens_details=SimpleNamespace(reasoning_tokens=0),
            ),
            reasoning=SimpleNamespace(context="current_turn"),
        )
        return _FakeEventStream(
            [
                _delta(self.text),
                _item_done(0, call),
                _item_done(1, message),
                _completed(terminal),
            ]
        )


class _EmptyTerminalSnapshotClient:
    def __init__(self, *, text: str = "Only the stream carried this.") -> None:
        self.responses = _EmptyTerminalSnapshotResponses(text=text)


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
        self.assertNotIn("prompt_cache_options", sent)
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
            sent["instructions"], "Keep the original agent instructions unchanged."
        )
        self.assertNotIn("prompt_cache_breakpoint", repr(sent))

    async def test_provider_without_prompt_cache_options_omits_unsupported_fields(
        self,
    ) -> None:
        model = OpenAIModel.from_config(
            {
                "api_key": "test-key",
                "provider_name": "qwen",
                "model_name": "qwen3-max",
                "prompt_cache": {
                    "mode": "implicit",
                    "ttl": "30m",
                    "supports_options": False,
                },
            }
        )
        client = _FakeOpenAIClient()
        model.client = client

        await model.run(
            ModelRunRequest(
                instructions="Provider-specific cache options are optional.",
                input=(Message.user("Return a short answer."),),
                prompt_cache_key="qwen:stable-prefix",
            )
        )

        sent = client.responses.requests[0]
        self.assertNotIn("prompt_cache_options", sent)
        self.assertEqual(sent["prompt_cache_key"], "qwen:stable-prefix")

    async def test_provider_with_prompt_cache_options_is_omitted(
        self,
    ) -> None:
        model = OpenAIModel.from_config(
            {
                "api_key": "test-key",
                "provider_name": "relay",
                "model_name": "gpt-5.6-sol",
                "prompt_cache": {
                    "mode": "implicit",
                    "ttl": "30m",
                    "supports_options": True,
                },
            }
        )
        client = _FakeOpenAIClient()
        model.client = client

        await model.run(
            ModelRunRequest(input=(Message.user("Return a short answer."),))
        )

        self.assertNotIn("prompt_cache_options", client.responses.requests[0])

    async def test_vision_request_omits_prompt_cache_extensions(self) -> None:
        client = _FakeOpenAIClient(text="VISION_OK")
        model = OpenAIModel(
            api_key="test-key",
            model_name="gpt-5.6-sol",
            prompt_cache_supports_options=True,
            client=client,
        )

        await model.run(
            ModelRunRequest(
                input=(
                    Message(
                        role="user",
                        content=(
                            TextContent("Inspect this figure."),
                            ImageContent("data:image/png;base64,AA=="),
                        ),
                    ),
                ),
            )
        )

        sent = client.responses.requests[0]
        self.assertNotIn("prompt_cache_options", sent)
        self.assertNotIn("prompt_cache_breakpoint", repr(sent))

    def test_prompt_cache_configuration_is_accepted_but_not_sent(self) -> None:
        model = OpenAIModel.from_config(
            {
                "api_key": "test-key",
                "prompt_cache": {
                    "mode": "explicit",
                    "ttl": "30m",
                    "supports_options": False,
                },
            }
        )
        self.assertFalse(model.prompt_cache_supports_options)

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
        self.assertIn("Return the requested selection.", sent["instructions"])

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
        stream = await client.responses.create()
        response = [
            event.response
            async for event in stream
            if getattr(event, "response", None) is not None
        ][-1]
        response.usage.input_tokens_details.cache_write_tokens = None
        response.usage.output_tokens_details.reasoning_tokens = None

        result = OpenAIModel._response_to_run_result(response)

        self.assertEqual(result.usage.cache_write_tokens, 0)
        self.assertEqual(result.usage.reasoning_tokens, 0)

    async def test_requests_are_streamed_so_progress_is_observable(self) -> None:
        client = _FakeOpenAIClient()
        model = OpenAIModel(api_key="test-key", client=client)

        await model.run(
            ModelRunRequest(input=(Message.user("Stream this."),))
        )

        self.assertIs(client.responses.requests[0]["stream"], True)
        self.assertTrue(client.responses.streams[0].closed)

    async def test_a_slow_but_speaking_model_is_never_cut_off(self) -> None:
        """Total duration far exceeds the bound; no single silence does."""

        client = _HeartbeatOpenAIClient(
            beats=20, gap=0.01, text="Finished after a long think."
        )
        model = OpenAIModel(
            api_key="test-key",
            stream_idle_timeout=0.05,
            client=client,
        )

        result = await model.run(
            ModelRunRequest(input=(Message.user("Think for a long time."),))
        )

        self.assertEqual(result.text, "Finished after a long think.")

    async def test_silence_past_the_bound_is_declared_dead(self) -> None:
        client = _SilentOpenAIClient()
        model = OpenAIModel(
            api_key="test-key",
            stream_idle_timeout=0.05,
            client=client,
        )

        with self.assertRaisesRegex(Exception, "no response event"):
            await model.run(
                ModelRunRequest(input=(Message.user("Go quiet forever."),))
            )
        self.assertTrue(client.responses.stream.closed)

    async def test_a_stream_that_only_errors_does_not_look_successful(self) -> None:
        model = OpenAIModel(
            api_key="test-key",
            client=_ErrorEventOpenAIClient(),
        )

        with self.assertRaisesRegex(Exception, "upstream closed the connection"):
            await model.run(
                ModelRunRequest(input=(Message.user("Fail mid-stream."),))
            )

    def test_transport_does_not_silently_multiply_one_attempt(self) -> None:
        model = OpenAIModel(api_key="test-key", stream_idle_timeout=1800)

        self.assertEqual(model.client.max_retries, 0)

    def test_a_codec_that_cannot_survive_concurrency_is_declined(self) -> None:
        """Concurrent streams must not share a compression context.

        A streamed body is compressed as it is produced.  Gateways that fan
        many concurrent streams through one zstd context interleave frames
        that no decoder can separate afterwards, and the damage surfaces as
        unreadable bytes far from the transport.  Compression stays on; only
        the codec that cannot frame each response independently is declined.
        """

        model = OpenAIModel(api_key="test-key")

        accept_encoding = _accept_encoding_on_the_wire(model)
        self.assertNotIn("zstd", accept_encoding)
        # Declining one codec is not declining compression.
        self.assertIn("gzip", accept_encoding)

    def test_a_provider_may_still_state_its_own_encoding(self) -> None:
        """The safeguard is a default, not a policy callers may not override."""

        model = OpenAIModel(
            api_key="test-key",
            default_headers={"Accept-Encoding": "identity"},
        )

        self.assertEqual(_accept_encoding_on_the_wire(model), "identity")

    def test_only_reading_is_allowed_to_idle_as_long_as_the_model_thinks(
        self,
    ) -> None:
        model = OpenAIModel(
            api_key="test-key", timeout=600, stream_idle_timeout=1800
        )

        timeout = model.client.timeout
        self.assertIsInstance(timeout, httpx.Timeout)
        self.assertEqual(timeout.read, 1800)
        self.assertEqual(timeout.connect, 600)

    def test_the_obsolete_total_duration_bound_is_rejected_by_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "request_timeout"):
            OpenAIModel.from_config({"request_timeout": 3600})


    async def test_items_delivered_only_in_the_stream_are_not_lost(self) -> None:
        """An empty terminal snapshot must not erase what the model produced."""

        client = _EmptyTerminalSnapshotClient(text="Recovered from the stream.")
        model = OpenAIModel(api_key="test-key", client=client)

        result = await model.run(
            ModelRunRequest(input=(Message.user("Say something."),))
        )

        self.assertEqual(result.text, "Recovered from the stream.")
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0].name, "search_papers")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.usage.total_tokens, 18)

    async def test_streamed_items_reach_replay_state(self) -> None:
        """Replay must record the same output the caller was given."""

        client = _EmptyTerminalSnapshotClient(text="Durable across turns.")
        model = OpenAIModel(
            api_key="test-key",
            client=client,
            response_state_mode="replay",
        )

        first = await model.run(
            ModelRunRequest(input=(Message.user("Remember this."),))
        )
        await model.run(
            ModelRunRequest(
                input=(Message.user("Continue."),),
                previous_response_id=first.response_id,
            )
        )

        replayed = client.responses.requests[1]["input"]
        self.assertTrue(
            any(
                "Durable across turns." in json.dumps(item, default=str)
                for item in replayed
            ),
            "replayed turn lost the streamed assistant message",
        )


if __name__ == "__main__":
    unittest.main()
