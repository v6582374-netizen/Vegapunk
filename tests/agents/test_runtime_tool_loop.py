from __future__ import annotations

import unittest
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import patch

from internagent.mas.agents.tool_loop import ModelToolLoop
from internagent.mas.models.runtime import (
    FunctionCall,
    FunctionCallOutput,
    FunctionTool,
    ModelRunRequest,
    ModelRunResult,
    OutputText,
    ReasoningConfig,
)
from internagent.research_draft import ResearchDraft


def _load_codeview_runtime():
    easydict = ModuleType("easydict")
    easydict.EasyDict = lambda **values: SimpleNamespace(**values)
    with patch.dict(sys.modules, {"easydict": easydict}):
        from internagent.mas.agents.codeview_agent import _generate_runtime_text

    return _generate_runtime_text


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
    async def test_each_tool_call_and_result_append_to_research_draft(self) -> None:
        model = _ScriptedModel()

        async def execute_tool(
            name: str, arguments: dict[str, object]
        ) -> dict[str, object]:
            return {"tool": name, "query": arguments["query"], "papers": ["p1"]}

        with tempfile.TemporaryDirectory() as temporary_directory:
            draft = ResearchDraft.open(Path(temporary_directory) / "launch")
            with draft.activate():
                await ModelToolLoop(
                    model=model, execute_tool=execute_tool
                ).run(
                    instructions="Use the tool.",
                    prompt="Find evidence.",
                    tools=(),
                    max_iterations=3,
                    max_tool_calls=2,
                )

            content = draft.path.read_text(encoding="utf-8")
            self.assertIn("search_papers", content)
            self.assertIn("model runtime", content)
            self.assertIn("papers", content)
            self.assertIn("p1", content)

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
            reasoning=ReasoningConfig(context="all_turns"),
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
        self.assertEqual(model.requests[0].reasoning.context, "all_turns")
        self.assertEqual(continuation.reasoning.context, "all_turns")

    async def test_loop_does_not_assume_provider_reasoning_support(self) -> None:
        model = _ScriptedModel()
        model.results = [
            ModelRunResult(
                response_id="resp_final",
                status="completed",
                model="vendor/chat-model",
                items=(OutputText(text="done"),),
            )
        ]

        result = await ModelToolLoop(
            model=model,
            execute_tool=lambda *_: None,
        ).run(
            instructions="Answer directly.",
            prompt="Hello.",
            tools=(),
            max_iterations=1,
            max_tool_calls=0,
        )

        self.assertEqual(result.content, "done")
        self.assertIsNone(model.requests[0].reasoning)


class CodeViewRuntimeConfigTest(unittest.TestCase):
    def test_codeview_requires_canonical_runtime_identity(self) -> None:
        _generate_runtime_text = _load_codeview_runtime()
        settings = SimpleNamespace(
            runtime_config={}, temperature=0.6, max_output_tokens=3000
        )

        with self.assertRaisesRegex(ValueError, "canonical"):
            _generate_runtime_text("gpt-5.6-sol", "system", "prompt", settings)

    def test_codeview_uses_injected_runtime(self) -> None:
        _generate_runtime_text = _load_codeview_runtime()
        class _Catalog:
            def resolve_model(self, model_id, capability=None):
                del capability
                return SimpleNamespace(canonical_id=model_id)

        class _Runtime:
            catalog = _Catalog()

            def model_for(self, model_id, *, capability):
                del model_id, capability

                class _FakeModel:
                    async def generate(self, **_):
                        return "summary"

                return _FakeModel()

        config = {"runtime": _Runtime()}
        settings = SimpleNamespace(
            runtime_config=config,
            temperature=0.6,
            max_output_tokens=3000,
        )

        result = _generate_runtime_text(
            "relay/gpt-5.6-sol", "system", "prompt", settings
        )

        self.assertEqual(result, "summary")


if __name__ == "__main__":
    unittest.main()
