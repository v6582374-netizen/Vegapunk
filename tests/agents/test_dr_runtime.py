from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from internagent.mas.agents.dr_agent import DRAgent, _get_workflow_class
from internagent.mas.agents.dr_agents.models.openai_model import (
    OpenAIModel as DROpenAIModel,
)
from internagent.mas.agents.dr_agents.agents.task.execution_agent import (
    ExecutionAgent,
)
from internagent.mas.models.runtime import (
    FunctionCall,
    FunctionCallOutput,
    ModelRunRequest,
    ModelRunResult,
    OutputText,
)


class _FakeRuntimeOpenAI:
    instances: list["_FakeRuntimeOpenAI"] = []

    def __init__(self, config) -> None:
        self.config = config
        self.requests = []
        self.__class__.instances.append(self)

    @classmethod
    def from_config(cls, config):
        return cls(config)

    def make_prompt_cache_key(self, *, agent_role, stable_prefix):
        return f"test:{agent_role}:{len(stable_prefix)}"

    async def run(self, request):
        self.requests.append(request)
        return ModelRunResult(
            response_id="resp_dr",
            status="completed",
            model="gpt-5.6-sol",
            items=(OutputText(text="final synthesis"),),
        )


class _ScriptedSyncRuntime:
    def __init__(self) -> None:
        self.requests = []
        self.results = [
            ModelRunResult(
                response_id="resp_tool",
                status="completed",
                model="gpt-5.6-sol",
                items=(
                    FunctionCall(
                        call_id="call_search",
                        name="search_web",
                        arguments={"query": "runtime"},
                    ),
                ),
            ),
            ModelRunResult(
                response_id="resp_done",
                status="completed",
                model="gpt-5.6-sol",
                items=(OutputText(text="evidence gathered"),),
            ),
        ]

    def run(self, request):
        self.requests.append(request)
        return self.results.pop(0)


class DeepResearchRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        _FakeRuntimeOpenAI.instances.clear()

    def test_sync_facade_projects_pro_background_policy(self) -> None:
        with patch(
            "internagent.mas.agents.dr_agents.models.openai_model.RuntimeOpenAIModel",
            _FakeRuntimeOpenAI,
        ):
            model = DROpenAIModel(
                runtime_config={"api_key": "test"},
                agent_role="dr_synthesizer",
                reasoning_context="all_turns",
                reasoning_mode="pro",
                background=True,
            )
            result = model.generate(
                "Synthesize the dossier.",
                system_prompt="Stable synthesis instructions.",
                max_output_tokens=128000,
            )
            model.close()

        self.assertEqual(result, "final synthesis")
        request = _FakeRuntimeOpenAI.instances[0].requests[0]
        self.assertEqual(request.reasoning.context, "all_turns")
        self.assertEqual(request.reasoning.mode, "pro")
        self.assertTrue(request.background)
        self.assertEqual(request.max_output_tokens, 128000)
        self.assertTrue(request.prompt_cache_key.startswith("test:dr_synthesizer"))

    def test_sync_facade_rejects_legacy_openai_options(self) -> None:
        model = DROpenAIModel(runtime_config={"api_key": "test"})

        with self.assertRaisesRegex(
            ValueError, "Unsupported DeepResearch Runtime options: max_tokens"
        ):
            model.generate("Do not call the API.", max_tokens=2000)

    def test_dr_config_inherits_root_openai_runtime(self) -> None:
        agent = object.__new__(DRAgent)
        agent.mode = "simple"
        root_openai = {
            "model_name": "gpt-5.6-sol",
            "api_mode": "responses",
            "max_output_tokens": 128000,
            "reasoning": {
                "effort": "xhigh",
                "context": "auto",
                "mode": "standard",
            },
            "store": True,
            "prompt_cache": {"mode": "explicit", "ttl": "30m"},
        }

        with patch(
            "internagent.mas.agents.dr_agent._get_config_loaders",
            return_value=(lambda _path: {"model": {}}, None),
        ):
            config = agent._load_dr_config(
                {
                    "_global_config": {
                        "models": {
                            "default_provider": "openai",
                            "openai": root_openai,
                        }
                    }
                }
            )

        self.assertEqual(
            config["runtime_model"], {**root_openai, "provider": "openai"}
        )
        self.assertEqual(config["model"]["default_model"], "gpt-5.6-sol")
        self.assertEqual(
            config["model"]["global_execution_model"],
            {
                "execution_model": "gpt-5.6-sol",
                "summarizer_model": "gpt-5.6-sol",
            },
        )

    def test_workflow_assigns_responses_policies_by_role(self) -> None:
        workflow_class = _get_workflow_class()
        self.assertIsNotNone(workflow_class)
        workflow_module = __import__(workflow_class.__module__, fromlist=["Workflow"])
        created = {}

        def capture(role):
            def constructor(*, model, **kwargs):
                created[role] = {"model": model, **kwargs}
                return SimpleNamespace()

            return constructor

        def capture_analysis(model, **kwargs):
            created["analysis"] = {"model": model, **kwargs}
            return SimpleNamespace()

        runtime_config = {
            "provider": "openai",
            "model_name": "gpt-5.6-sol",
            "api_mode": "responses",
        }
        config = {
            "model": {
                "default_model": "gpt-5.6-sol",
                "global_execution_model": {
                    "execution_model": "gpt-5.6-sol",
                    "summarizer_model": "gpt-5.6-sol",
                },
            },
            "runtime_model": runtime_config,
        }

        with (
            patch.object(workflow_module, "GlobalPlannerAgent", capture("planner")),
            patch.object(
                workflow_module,
                "GlobalExecutionAgent",
                capture("execution"),
            ),
            patch.object(
                workflow_module, "CoordinatorAgent", capture("coordinator")
            ),
            patch.object(
                workflow_module, "SynthesizerAgent", capture("synthesizer")
            ),
            patch.object(workflow_module, "get_model", capture_analysis),
        ):
            workflow_class(config=config)

        for role in ("planner", "execution", "coordinator", "synthesizer"):
            self.assertEqual(created[role]["model"], "gpt-5.6-sol")
            self.assertEqual(created[role]["runtime_config"], runtime_config)
        self.assertEqual(created["execution"]["reasoning_context"], "all_turns")
        self.assertEqual(created["coordinator"]["reasoning_context"], "all_turns")
        self.assertEqual(created["synthesizer"]["reasoning_context"], "all_turns")
        self.assertEqual(created["synthesizer"]["reasoning_mode"], "pro")
        self.assertTrue(created["synthesizer"]["background"])
        self.assertEqual(created["analysis"]["agent_role"], "dr_query_analysis")

    def test_execution_loop_preserves_response_and_call_ids(self) -> None:
        model = _ScriptedSyncRuntime()
        agent = object.__new__(ExecutionAgent)
        agent.model_instance = model
        agent.tool_map = {
            "search_web": {
                "name": "search_web",
                "description": "Search the web.",
                "parameters": {"query": {"type": "string"}},
                "required_parameters": ["query"],
            }
        }
        agent.execution_prompt = "Task={task}; subtask={subtask}; query={query}"
        agent.max_tool_calls = 4
        agent._logger = SimpleNamespace(
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
            error=lambda *args, **kwargs: None,
            debug=lambda *args, **kwargs: None,
        )
        agent._execute_single_tool_call = lambda call: {
            "tool_name": call["name"],
            "success": True,
            "arguments": call["arguments"],
            "result": {"items": ["source-1"]},
            "error": None,
        }
        agent._generate_subtask_response = (
            lambda subtask, trace, context: '{"success":true,"summary":"done"}'
        )

        result = agent.execute(
            "Find evidence",
            {
                "task": "Research runtimes",
                "history_subtasks": [],
                "knowledge_info": {},
            },
            query="runtime",
        )

        self.assertTrue(result["success"])
        continuation = model.requests[1]
        self.assertEqual(continuation.previous_response_id, "resp_tool")
        self.assertIsInstance(continuation.input[0], FunctionCallOutput)
        self.assertEqual(continuation.input[0].call_id, "call_search")
        self.assertEqual(
            result["execution_trace"][0]["tool_calls"][0]["call_id"],
            "call_search",
        )


if __name__ == "__main__":
    unittest.main()
