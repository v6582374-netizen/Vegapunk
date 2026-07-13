from __future__ import annotations

import unittest

from internagent.mas.agents.tool_loop import ModelToolLoop
from internagent.mas.models.runtime import (
    FunctionCall,
    FunctionCallOutput,
    FunctionTool,
    ModelRunRequest,
    ModelRunResult,
    OutputText,
)


class _ScriptedModel:
    def __init__(self) -> None:
        self.requests: list[ModelRunRequest] = []
        self.results = [
            ModelRunResult(
                response_id="resp_tool_call",
                status="completed",
                model="gpt-5.6-sol",
                items=(
                    FunctionCall(
                        call_id="call_search",
                        name="search_papers",
                        arguments={"query": "model runtime"},
                    ),
                ),
            ),
            ModelRunResult(
                response_id="resp_final",
                status="completed",
                model="gpt-5.6-sol",
                items=(OutputText(text="Found the relevant paper."),),
            ),
        ]

    async def run(self, request: ModelRunRequest) -> ModelRunResult:
        self.requests.append(request)
        return self.results.pop(0)


class RuntimeToolLoopTest(unittest.IsolatedAsyncioTestCase):
    async def test_tool_results_continue_the_same_response_chain(self) -> None:
        model = _ScriptedModel()
        executions: list[tuple[str, dict[str, object]]] = []

        async def execute_tool(
            name: str, arguments: dict[str, object]
        ) -> dict[str, object]:
            executions.append((name, arguments))
            return {"papers": ["paper-1"]}

        loop = ModelToolLoop(model=model, execute_tool=execute_tool)
        result = await loop.run(
            instructions="Use tools to gather evidence.",
            prompt="Find papers about typed model runtimes.",
            tools=(
                FunctionTool(
                    name="search_papers",
                    description="Search papers.",
                    parameters={
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                ),
            ),
            max_iterations=4,
            max_tool_calls=4,
        )

        self.assertEqual(result.content, "Found the relevant paper.")
        self.assertEqual(result.iterations, 2)
        self.assertEqual(result.total_tool_calls, 1)
        self.assertEqual(
            executions, [("search_papers", {"query": "model runtime"})]
        )
        continuation = model.requests[1]
        self.assertEqual(
            continuation.previous_response_id, "resp_tool_call"
        )
        self.assertEqual(len(continuation.input), 1)
        self.assertIsInstance(continuation.input[0], FunctionCallOutput)
        self.assertEqual(continuation.input[0].call_id, "call_search")
        self.assertEqual(
            continuation.input[0].output, {"papers": ["paper-1"]}
        )


if __name__ == "__main__":
    unittest.main()
