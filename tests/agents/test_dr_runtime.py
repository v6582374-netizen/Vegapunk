from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from internagent.mas.agents.dr_agent import DRAgent, _get_workflow_class
from internagent.mas.agents.dr_agents.models.openai_model import (
    OpenAIModel as DROpenAIModel,
)
from internagent.mas.agents.dr_agents.models import get_model as get_dr_model
from internagent.mas.agents.dr_agents.agents.task.execution_agent import (
    ExecutionAgent,
)
from internagent.research_draft import ResearchDraft
from tools import ToolManager
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

    def test_dr_tool_manager_appends_each_call_and_result_to_draft(self) -> None:
        manager = ToolManager.__new__(ToolManager)
        manager.tools = {
            "lookup": {"function": lambda query: {"query": query, "score": 0.9}}
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            draft = ResearchDraft.open(Path(temporary_directory) / "launch")
            with draft.activate():
                result = manager.call_tool("lookup", query="formula evidence")

            content = draft.path.read_text(encoding="utf-8")
            self.assertEqual(result, {"query": "formula evidence", "score": 0.9})
            self.assertIn("lookup", content)
            self.assertIn("formula evidence", content)
            self.assertIn("0.9", content)

    def test_sync_facade_projects_pro_background_policy(self) -> None:
        with patch(
            "internagent.mas.agents.dr_agents.models.openai_model.RuntimeOpenAIModel",
            _FakeRuntimeOpenAI,
        ):
            model = DROpenAIModel(
                runtime_config={
                    "api_key": "test",
                    "base_url": "https://ai.cloudyz.top/v1",
                },
                agent_role="dr_synthesizer",
                reasoning_context="all_turns",
                reasoning_mode="pro",
                background=True,
            )
            result = model.generate(
                "Synthesize the paper.",
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
        model = DROpenAIModel(
            runtime_config={
                "api_key": "test",
                "base_url": "https://ai.cloudyz.top/v1",
            }
        )

        with self.assertRaisesRegex(
            ValueError, "Unsupported DeepResearch Runtime options: max_tokens"
        ):
            model.generate("Do not call the API.", max_tokens=2000)

    def test_sync_facade_requires_explicit_deployment_config(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicit runtime_config"):
            DROpenAIModel(agent_role="dr_tool_helper")

    def test_sync_facade_accepts_the_model_selected_by_dr(self) -> None:
        model = DROpenAIModel(
            "gpt-5.5",
            runtime_config={
                "api_key": "test",
                "base_url": "https://ai.cloudyz.top/v1",
            },
        )

        self.assertEqual(model.model_name, "gpt-5.5")
        self.assertEqual(model.runtime_config["model_name"], "gpt-5.5")

    def test_sync_facade_availability_probe_is_lightweight(self) -> None:
        with patch(
            "internagent.mas.agents.dr_agents.models.openai_model.RuntimeOpenAIModel",
            _FakeRuntimeOpenAI,
        ):
            model = DROpenAIModel(
                runtime_config={
                    "api_key": "test",
                    "base_url": "https://ai.cloudyz.top/v1",
                }
            )
            model.probe()
            model.close()

        request = _FakeRuntimeOpenAI.instances[0].requests[0]
        self.assertEqual(request.input[0].content[0].text, "Reply with OK.")
        self.assertEqual(request.reasoning.effort, "low")
        self.assertEqual(request.max_output_tokens, 16)

    def test_explicit_openai_deployment_routes_any_dr_model_name(self) -> None:
        model = get_dr_model(
            "gateway-specific-model",
            runtime_config={
                "provider": "openai",
                "api_key": "test",
                "base_url": "https://ai.cloudyz.top/v1",
            },
        )

        self.assertIsInstance(model, DROpenAIModel)
        self.assertEqual(model.model_name, "gateway-specific-model")

    def test_sync_facade_ignores_extraction_routing_at_generation_time(
        self,
    ) -> None:
        with patch(
            "internagent.mas.agents.dr_agents.models.openai_model.RuntimeOpenAIModel",
            _FakeRuntimeOpenAI,
        ):
            model = DROpenAIModel(
                runtime_config={
                    "api_key": "test",
                    "base_url": "https://ai.cloudyz.top/v1",
                }
            )
            result = model.generate(
                "Generate a coordinator response.",
                extraction_model="gpt-5.6-sol",
            )
            model.close()

        self.assertEqual(result, "final synthesis")

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
            return_value=(
                lambda _path: {
                    "model": {
                        "default_model": "gpt-5.6-sol",
                        "global_planner_model": None,
                        "global_execution_model": None,
                    }
                },
                None,
            ),
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
        self.assertIsNone(config["model"]["global_execution_model"])

    def test_dr_keeps_the_selected_workflow_default_model(self) -> None:
        agent = object.__new__(DRAgent)
        agent.mode = "simple"
        workflow_config = {
            "model": {
                "default_model": "dr-config-model",
                "global_planner_model": None,
            }
        }

        with patch(
            "internagent.mas.agents.dr_agent._get_config_loaders",
            return_value=(lambda _path: workflow_config, None),
        ):
            config = agent._load_dr_config(
                {
                    "_global_config": {
                        "models": {
                            "openai": {
                                "model_name": "gpt-5.6-sol",
                                "base_url": "https://ai.cloudyz.top/v1",
                                "api_mode": "responses",
                            }
                        }
                    }
                }
            )

        self.assertEqual(config["model"]["default_model"], "dr-config-model")

    def test_dr_workflow_override_recursively_preserves_sibling_settings(self) -> None:
        agent = object.__new__(DRAgent)
        agent.mode = "simple"
        workflow_config = {
            "model": {"default_model": "gpt-5.6-sol"},
            "global_execution": {
                "max_workers": 10,
                "execution": {
                    "max_tool_calls": 5,
                    "timeout": 120,
                },
            },
        }

        with patch(
            "internagent.mas.agents.dr_agent._get_config_loaders",
            return_value=(lambda _path: workflow_config, None),
        ):
            config = agent._load_dr_config(
                {
                    "workflow_config": {
                        "global_execution": {"max_workers": 3}
                    },
                    "_global_config": {
                        "models": {
                            "openai": {
                                "model_name": "gpt-5.6-sol",
                                "base_url": "https://ai.cloudyz.top/v1",
                            }
                        }
                    },
                }
            )

        self.assertEqual(
            config["global_execution"],
            {
                "max_workers": 3,
                "execution": {
                    "max_tool_calls": 5,
                    "timeout": 120,
                },
            },
        )

    def test_dr_rejects_a_missing_default_model_before_workflow_start(self) -> None:
        agent = object.__new__(DRAgent)
        agent.mode = "simple"

        with patch(
            "internagent.mas.agents.dr_agent._get_config_loaders",
            return_value=(lambda _path: {"model": {}}, None),
        ):
            with self.assertRaisesRegex(ValueError, "default_model"):
                agent._load_dr_config(
                    {
                        "_global_config": {
                            "models": {
                                "openai": {
                                    "model_name": "gpt-5.6-sol",
                                    "base_url": "https://ai.cloudyz.top/v1",
                                }
                            }
                        }
                    }
                )

    def test_explicit_dr_default_model_override_wins(self) -> None:
        agent = object.__new__(DRAgent)
        agent.mode = "simple"

        with patch(
            "internagent.mas.agents.dr_agent._get_config_loaders",
            return_value=(
                lambda _path: {
                    "model": {"default_model": "base-dr-model"}
                },
                None,
            ),
        ):
            config = agent._load_dr_config(
                {
                    "workflow_config": {
                        "model": {"default_model": "override-dr-model"}
                    },
                    "_global_config": {
                        "models": {
                            "openai": {
                                "model_name": "gpt-5.6-sol",
                                "base_url": "https://ai.cloudyz.top/v1",
                            }
                        }
                    },
                }
            )

        self.assertEqual(
            config["model"]["default_model"], "override-dr-model"
        )

    def test_dr_probes_each_effective_model_once_before_workflow_creation(
        self,
    ) -> None:
        events = []
        workflow_config = {
            "model": {
                "default_model": "default-model",
                "global_planner_model": "planner-model",
                "global_execution_model": {
                    "execution_model": "execution-model",
                    "summarizer_model": "default-model",
                },
                "coordinator_model": "planner-model",
                "synthesizer_model": None,
                "extraction_model": "extraction-model",
            },
            "runtime_model": {"provider": "openai"},
        }

        class FakeWorkflow:
            def __init__(self, *, config):
                events.append(("workflow", config))

        def record_probe(model_name, runtime_config):
            events.append(("probe", model_name, runtime_config))

        with (
            patch.object(
                DRAgent,
                "_load_dr_config",
                return_value=workflow_config,
            ),
            patch(
                "internagent.mas.agents.dr_agent._get_workflow_class",
                return_value=FakeWorkflow,
            ),
            patch(
                "internagent.mas.agents.dr_agent._probe_dr_model",
                side_effect=record_probe,
                create=True,
            ),
        ):
            DRAgent(SimpleNamespace(), {})

        self.assertEqual(
            [event[1] for event in events if event[0] == "probe"],
            [
                "default-model",
                "planner-model",
                "execution-model",
                "extraction-model",
            ],
        )
        self.assertEqual(events[-1], ("workflow", workflow_config))

    def test_dr_propagates_model_probe_failure_before_workflow_creation(
        self,
    ) -> None:
        workflow_config = {
            "model": {"default_model": "forbidden-model"},
            "runtime_model": {"provider": "openai"},
        }

        with (
            patch.object(
                DRAgent,
                "_load_dr_config",
                return_value=workflow_config,
            ),
            patch(
                "internagent.mas.agents.dr_agent._get_workflow_class",
                return_value=SimpleNamespace,
            ) as get_workflow,
            patch(
                "internagent.mas.agents.dr_agent._probe_dr_model",
                side_effect=PermissionError("403 Forbidden"),
                create=True,
            ),
        ):
            with self.assertRaisesRegex(PermissionError, "403 Forbidden"):
                DRAgent(SimpleNamespace(), {})

        get_workflow.assert_called_once_with()

    def test_disabled_dr_does_not_load_or_probe_the_workflow(self) -> None:
        with (
            patch.object(DRAgent, "_load_dr_config") as load_config,
            patch(
                "internagent.mas.agents.dr_agent._get_workflow_class"
            ) as get_workflow,
            patch(
                "internagent.mas.agents.dr_agent._probe_dr_model",
                create=True,
            ) as probe,
        ):
            agent = DRAgent(SimpleNamespace(), {"enabled": False})

        self.assertIsNone(agent.workflow)
        load_config.assert_not_called()
        get_workflow.assert_not_called()
        probe.assert_not_called()

    def test_dr_uses_openai_policy_when_another_provider_is_default(self) -> None:
        agent = object.__new__(DRAgent)
        agent.mode = "qa"
        openai_config = {
            "model_name": "gpt-5.6-sol",
            "api_mode": "responses",
            "reasoning": {"effort": "xhigh"},
        }

        with patch(
            "internagent.mas.agents.dr_agent._get_config_loaders",
            return_value=(
                lambda _path: {
                    "model": {"default_model": "gpt-5.6-sol"}
                },
                None,
            ),
        ):
            config = agent._load_dr_config(
                {
                    "_global_config": {
                        "models": {
                            "default_provider": "openrouter",
                            "openrouter": {"model_name": "vendor/model"},
                            "openai": openai_config,
                        }
                    }
                }
            )

        self.assertEqual(
            config["runtime_model"],
            {**openai_config, "provider": "openai"},
        )
        self.assertEqual(config["model"]["default_model"], "gpt-5.6-sol")

    def test_workflow_assigns_responses_policies_and_inherits_extraction_model(
        self,
    ) -> None:
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
                "extraction_model": None,
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
            self.assertEqual(created[role]["extraction_model"], "gpt-5.6-sol")
        self.assertEqual(created["execution"]["reasoning_context"], "all_turns")
        self.assertEqual(created["coordinator"]["reasoning_context"], "all_turns")
        self.assertEqual(created["synthesizer"]["reasoning_context"], "all_turns")
        self.assertEqual(created["synthesizer"]["reasoning_mode"], "pro")
        self.assertTrue(created["synthesizer"]["background"])
        self.assertEqual(created["analysis"]["agent_role"], "dr_query_analysis")

    def test_extraction_uses_the_explicit_dr_model_not_environment(self) -> None:
        _get_workflow_class()
        from tools import info_processing_tools

        runtime_config = {
            "provider": "openai",
            "base_url": "https://ai.cloudyz.top/v1",
        }
        with (
            patch.dict(os.environ, {"EXTRACTION_MODEL": "gpt-5.5"}),
            patch.object(
                info_processing_tools,
                "get_model",
                return_value=SimpleNamespace(),
            ) as get_model,
        ):
            info_processing_tools.extract_paper_content_to_summary(
                "/missing/paper.txt",
                model_name="gpt-5.6-sol",
                runtime_config=runtime_config,
            )

        get_model.assert_called_once_with(
            "gpt-5.6-sol",
            runtime_config=runtime_config,
        )

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
