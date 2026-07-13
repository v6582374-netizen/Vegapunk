from __future__ import annotations

import unittest
from types import SimpleNamespace

from internagent.mas.models.base_model import UnsupportedModelCapabilityError
from internagent.mas.models.openrouter_model import OpenRouterModel
from internagent.mas.models.runtime import (
    FunctionCallOutput,
    FunctionTool,
    Message,
    ModelRunRequest,
    ReasoningConfig,
)


class _FakeChatCompletions:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    async def create(self, **request: object) -> SimpleNamespace:
        self.requests.append(request)
        if len(self.requests) == 1:
            message = SimpleNamespace(
                content=None,
                tool_calls=[
                    SimpleNamespace(
                        id="call_search",
                        function=SimpleNamespace(
                            name="search_papers",
                            arguments='{"query":"runtime adapters"}',
                        ),
                    )
                ],
            )
            response_id = "chat_tool"
        else:
            message = SimpleNamespace(
                content="Found the paper through the Chat adapter.",
                tool_calls=None,
            )
            response_id = "chat_final"
        return SimpleNamespace(
            id=response_id,
            model="moonshotai/kimi-k2.6:free",
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(
                prompt_tokens=20,
                completion_tokens=5,
                total_tokens=25,
            ),
        )


class _FakeClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=_FakeChatCompletions())


class ChatCompatibleRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_tool_continuation_is_isolated_behind_runtime_ids(self) -> None:
        client = _FakeClient()
        model = OpenRouterModel(api_key="test", client=client)
        tools = (
            FunctionTool(
                name="search_papers",
                description="Search papers.",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            ),
        )

        first = await model.run(
            ModelRunRequest(
                instructions="Use available tools.",
                input=(Message.user("Find a paper."),),
                tools=tools,
            )
        )
        second = await model.run(
            ModelRunRequest(
                input=(
                    FunctionCallOutput(
                        call_id=first.tool_calls[0].call_id,
                        output={"papers": ["paper-1"]},
                    ),
                ),
                tools=tools,
                previous_response_id=first.response_id,
            )
        )

        self.assertEqual(second.text, "Found the paper through the Chat adapter.")
        continuation = client.chat.completions.requests[1]
        self.assertEqual(continuation["messages"][-1]["role"], "tool")
        self.assertEqual(
            continuation["messages"][-1]["tool_call_id"], "call_search"
        )

    async def test_unsupported_responses_capability_fails_explicitly(self) -> None:
        model = OpenRouterModel(api_key="test", client=_FakeClient())
        with self.assertRaises(UnsupportedModelCapabilityError):
            await model.run(
                ModelRunRequest(
                    input=(Message.user("Use persisted reasoning."),),
                    reasoning=ReasoningConfig(context="all_turns"),
                )
            )


if __name__ == "__main__":
    unittest.main()
