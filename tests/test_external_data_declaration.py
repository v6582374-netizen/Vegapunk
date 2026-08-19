from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from vegapunk.mas.agents import generation_agent as generation_agent_module
from vegapunk.mas.agents.generation_agent import GenerationAgent
from vegapunk.mas.memory.memory_manager import InMemoryMemoryManager
from vegapunk.mas.workflow.data_type import (
    EXTERNAL_DATA_POLICY_FORBIDDEN,
    ExternalDataDeclaration,
    Idea,
    Task,
    WorkflowSession,
    WorkflowState,
)
from vegapunk.mas.workflow.orchestration_agent import OrchestrationAgent


class _ToolRegistry:
    async def get_all_definitions(self, **_: object) -> list[object]:
        return []


class _StructuredModel:
    model_id = "test-model"

    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.schemas: list[dict[str, object]] = []
        self.prompts: list[str] = []
        self.system_prompts: list[str] = []

    async def generate_json(self, **kwargs: object) -> dict[str, object]:
        self.schemas.append(kwargs["schema"])
        self.prompts.append(kwargs["prompt"])
        self.system_prompts.append(kwargs["system_prompt"])
        return self.response


class GenerationExternalDataDeclarationTest(unittest.IsolatedAsyncioTestCase):
    async def test_schema_offers_two_branches_and_neither_carries_the_other(self) -> None:
        """The declaration is a choice, so each branch carries only its own payload."""
        model = _StructuredModel(
            {
                "hypotheses": [
                    {
                        "text": "Measure permeability under salinity gradients.",
                        "rationale": "The gradient may change transport selectivity.",
                        "external_data": {
                            "required": True,
                            "request": "Water and salt permeability by salinity.",
                        },
                    },
                    {
                        "text": "Compare two existing analytical models.",
                        "rationale": "The comparison can use the supplied equations.",
                        "external_data": {
                            "required": False,
                            "reason": "Evaluated from the supplied analytical models.",
                        },
                    },
                ],
                "reasoning": "Generated two distinct candidates.",
            }
        )

        with patch(
            "vegapunk.mas.agents.generation_agent.get_registry",
            return_value=_ToolRegistry(),
        ):
            agent = GenerationAgent(
                model,
                {"use_memory": False, "filter_failed_ideas": False},
            )

        agent.get_allowed_tools = AsyncMock(return_value=[])
        result = await agent.execute(
            {"goal": {"description": "Study membrane transport."}},
            {},
        )

        hypotheses = result["hypotheses"]
        self.assertTrue(hypotheses[0]["external_data"]["required"])
        self.assertIn("salinity", hypotheses[0]["external_data"]["request"])
        self.assertFalse(hypotheses[1]["external_data"]["required"])
        self.assertTrue(hypotheses[1]["external_data"]["reason"])

        item_schema = model.schemas[0]["properties"]["hypotheses"]["items"]
        self.assertEqual(
            set(item_schema["required"]), {"text", "rationale", "external_data"}
        )
        branches = item_schema["properties"]["external_data"]["oneOf"]
        self.assertEqual(len(branches), 2)
        open_branch, closed_branch = branches
        self.assertEqual(set(open_branch["required"]), {"required", "request"})
        self.assertNotIn("reason", open_branch["properties"])
        self.assertEqual(set(closed_branch["required"]), {"required", "reason"})
        self.assertNotIn("request", closed_branch["properties"])

    async def test_closed_branch_alone_produces_no_warning(self) -> None:
        """A correct refusal must not be recorded as a contradiction."""
        model = _StructuredModel(
            {
                "hypotheses": [
                    {
                        "text": "Reproduce the published result from supplied data.",
                        "rationale": "The supplied dataset is sufficient.",
                        "external_data": {
                            "required": False,
                            "reason": "The task supplies every needed field.",
                        },
                    }
                ],
                "reasoning": "One self-contained candidate.",
            }
        )

        with patch(
            "vegapunk.mas.agents.generation_agent.get_registry",
            return_value=_ToolRegistry(),
        ):
            agent = GenerationAgent(
                model,
                {"use_memory": False, "filter_failed_ideas": False},
            )

        agent.get_allowed_tools = AsyncMock(return_value=[])
        with patch.object(
            generation_agent_module.logger, "warning"
        ) as warning:
            result = await agent.execute(
                {"goal": {"description": "Reproduce the study."}},
                {},
            )

        warning.assert_not_called()
        self.assertFalse(result["hypotheses"][0]["external_data"]["required"])

    async def test_generation_prompt_asks_for_no_source_or_route(self) -> None:
        """Route selection left the side that cannot see the registry."""
        model = _StructuredModel({"hypotheses": [], "reasoning": ""})

        with patch(
            "vegapunk.mas.agents.generation_agent.get_registry",
            return_value=_ToolRegistry(),
        ):
            agent = GenerationAgent(
                model,
                {"use_memory": False, "filter_failed_ideas": False},
            )

        agent.get_allowed_tools = AsyncMock(return_value=[])
        await agent.execute({"goal": {"description": "Study transport."}}, {})

        system_prompt = model.system_prompts[0]
        self.assertNotIn("external_data_route", system_prompt)
        self.assertNotIn("registered_api", system_prompt)
        self.assertNotIn("public_web", system_prompt)

    async def test_invalid_declaration_closes_gate_with_reason(self) -> None:
        model = _StructuredModel(
            {
                "hypotheses": [
                    {
                        "text": "An incomplete candidate.",
                        "rationale": "The model omitted the data declaration.",
                    },
                    {
                        "text": "A request without requested data.",
                        "rationale": "The request cannot be executed as written.",
                        "external_data": {"required": True, "request": "  "},
                    },
                ],
                "reasoning": "Malformed declaration response.",
            }
        )

        with patch(
            "vegapunk.mas.agents.generation_agent.get_registry",
            return_value=_ToolRegistry(),
        ):
            agent = GenerationAgent(
                model,
                {"use_memory": False, "filter_failed_ideas": False},
            )

        agent.get_allowed_tools = AsyncMock(return_value=[])
        with self.assertLogs(
            "vegapunk.mas.agents.generation_agent", level="WARNING"
        ):
            result = await agent.execute(
                {"goal": {"description": "Study membrane transport."}},
                {},
            )

        for hypothesis in result["hypotheses"]:
            self.assertFalse(hypothesis["external_data"]["required"])
            self.assertEqual(hypothesis["external_data"]["request"], "")
            self.assertTrue(hypothesis["external_data"]["reason"])

    async def test_forbidding_task_refuses_an_idea_level_request(self) -> None:
        """An Idea may narrow the Task authority, never widen it."""
        model = _StructuredModel(
            {
                "hypotheses": [
                    {
                        "text": "Supplement with an external membrane database.",
                        "rationale": "More data would sharpen the fit.",
                        "external_data": {
                            "required": True,
                            "request": "External membrane permeability records.",
                        },
                    }
                ],
                "reasoning": "One candidate that wants outside data.",
            }
        )

        with patch(
            "vegapunk.mas.agents.generation_agent.get_registry",
            return_value=_ToolRegistry(),
        ):
            agent = GenerationAgent(
                model,
                {"use_memory": False, "filter_failed_ideas": False},
            )

        agent.get_allowed_tools = AsyncMock(return_value=[])
        with self.assertLogs(
            "vegapunk.mas.agents.generation_agent", level="WARNING"
        ):
            result = await agent.execute(
                {
                    "goal": {
                        "description": "Reproduce using only the supplied dataset.",
                        "external_data_policy": EXTERNAL_DATA_POLICY_FORBIDDEN,
                    }
                },
                {},
            )

        declaration = result["hypotheses"][0]["external_data"]
        self.assertFalse(declaration["required"])
        self.assertEqual(declaration["request"], "")
        self.assertTrue(declaration["reason"])

    async def test_regenerated_hypothesis_is_resolved_before_returning(self) -> None:
        model = _StructuredModel(
            {
                "hypotheses": [
                    {
                        "text": "Initial candidate.",
                        "rationale": "Initial rationale.",
                        "external_data": {
                            "required": False,
                            "reason": "No data is needed initially.",
                        },
                    }
                ],
                "reasoning": "Initial response.",
            }
        )

        with patch(
            "vegapunk.mas.agents.generation_agent.get_registry",
            return_value=_ToolRegistry(),
        ):
            agent = GenerationAgent(
                model,
                {"use_memory": False, "filter_failed_ideas": True},
            )

        agent.get_allowed_tools = AsyncMock(return_value=[])
        agent.use_memory = True
        agent.memory_retriever = object()
        agent._filter_and_regenerate_hypotheses = AsyncMock(
            return_value=[
                {"text": "Regenerated candidate.", "rationale": "Regenerated rationale."}
            ]
        )

        result = await agent.execute(
            {"goal": {"description": "Study membrane transport."}},
            {},
        )

        regenerated = result["hypotheses"][0]["external_data"]
        self.assertFalse(regenerated["required"])
        self.assertEqual(regenerated["request"], "")
        self.assertTrue(regenerated["reason"])


class IdeaExternalDataPersistenceTest(unittest.TestCase):
    def test_declaration_round_trips_as_one_value(self) -> None:
        idea = Idea(
            id="idea-1",
            text="Measure permeability.",
            external_data=ExternalDataDeclaration(
                required=True, request="Permeability by salinity."
            ),
        )

        restored = Idea.from_dict(idea.to_dict())

        self.assertTrue(restored.external_data.required)
        self.assertEqual(restored.external_data.request, "Permeability by salinity.")
        self.assertEqual(restored.external_data.reason, "")

    def test_task_policy_round_trips(self) -> None:
        task = Task(
            id="task-1",
            description="Reproduce from supplied data only.",
            domain="materials science",
            external_data_policy=EXTERNAL_DATA_POLICY_FORBIDDEN,
        )

        restored = Task.from_dict(task.to_dict())

        self.assertEqual(restored.external_data_policy, EXTERNAL_DATA_POLICY_FORBIDDEN)


class OrchestrationExternalDataGateTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.orchestrator = OrchestrationAgent(
            {"workflow": {}},
            InMemoryMemoryManager(),
            model_runtime=SimpleNamespace(),
        )

    @staticmethod
    def _session(idea: Idea, *, policy: str | None = None) -> WorkflowSession:
        task = Task(
            id="task-1",
            description="Study membrane transport.",
            domain="materials science",
        )
        if policy is not None:
            task.external_data_policy = policy
        return WorkflowSession(id="session-1", task=task, ideas=[idea])

    def test_closed_declaration_keeps_the_gate_shut(self) -> None:
        idea = Idea(id="idea-1", text="Use the supplied analytical model.")
        session = self._session(idea)

        self.assertFalse(
            self.orchestrator.admit_external_data_declaration(
                idea,
                session,
                {"required": False, "reason": "The supplied model is sufficient."},
            )
        )
        self.assertFalse(self.orchestrator.should_acquire_external_data(idea))

    def test_open_declaration_needs_a_concrete_request(self) -> None:
        valid = Idea(id="idea-1", text="Measure permeability.")
        invalid = Idea(id="idea-2", text="Measure permeability.")
        session = self._session(valid)

        self.assertTrue(
            self.orchestrator.admit_external_data_declaration(
                valid, session, {"required": True, "request": "Permeability by salinity."}
            )
        )
        with self.assertLogs(
            "vegapunk.mas.workflow.orchestration_agent", level="WARNING"
        ):
            self.assertFalse(
                self.orchestrator.admit_external_data_declaration(
                    invalid, session, {"required": True, "request": " "}
                )
            )
        self.assertTrue(invalid.external_data.reason)

    def test_forbidding_task_overrides_an_idea_claim(self) -> None:
        idea = Idea(id="idea-1", text="Supplement with outside records.")
        session = self._session(idea, policy=EXTERNAL_DATA_POLICY_FORBIDDEN)

        with self.assertLogs(
            "vegapunk.mas.workflow.orchestration_agent", level="WARNING"
        ):
            opened = self.orchestrator.admit_external_data_declaration(
                idea, session, {"required": True, "request": "Outside records."}
            )

        self.assertFalse(opened)
        self.assertEqual(idea.external_data.request, "")
        self.assertTrue(idea.external_data.reason)

    async def test_data_free_idea_keeps_scholar_retrieval_enabled(self) -> None:
        idea = Idea(
            id="idea-1",
            text="Use the supplied analytical model.",
            external_data=ExternalDataDeclaration(
                reason="The supplied model is sufficient."
            ),
        )
        session = self._session(idea)
        scholar = SimpleNamespace(
            execute=AsyncMock(
                return_value={"evidence": [{"title": "Paper"}], "references": []}
            )
        )
        self.orchestrator._get_agent = Mock(return_value=scholar)
        self.orchestrator._update_session_state = AsyncMock()

        await self.orchestrator._run_external_data_phase(session)

        scholar.execute.assert_awaited_once()
        self.assertEqual(idea.evidence, [{"title": "Paper"}])
        self.orchestrator._update_session_state.assert_awaited_once_with(
            session,
            WorkflowState.EVOLVING,
        )

    async def test_evolved_idea_inherits_the_whole_parent_decision(self) -> None:
        parent = Idea(
            id="idea-1",
            text="Assess GenAI labor-market effects.",
            external_data=ExternalDataDeclaration(
                required=True,
                request="BLS employment projections by SOC occupation.",
            ),
        )
        session = self._session(parent)
        evolution = SimpleNamespace(
            execute=AsyncMock(
                return_value={
                    "evolved_hypotheses": [
                        {
                            "text": "Refined labor-market effect model.",
                            "rationale": "Addresses the identification critique.",
                        }
                    ]
                }
            )
        )
        self.orchestrator._get_agent = Mock(return_value=evolution)
        self.orchestrator._update_session_state = AsyncMock()

        await self.orchestrator._run_evolution_phase(session)

        evolved = next(idea for idea in session.ideas if idea.parent_id == parent.id)
        self.assertTrue(evolved.external_data.required)
        self.assertEqual(
            evolved.external_data.request,
            "BLS employment projections by SOC occupation.",
        )
        self.assertEqual(evolved.external_data.reason, "")

    async def test_forbidding_task_also_closes_the_evolution_entrance(self) -> None:
        parent = Idea(id="idea-1", text="Reproduce from supplied data.")
        session = self._session(parent, policy=EXTERNAL_DATA_POLICY_FORBIDDEN)
        evolution = SimpleNamespace(
            execute=AsyncMock(
                return_value={
                    "evolved_hypotheses": [
                        {
                            "text": "Add an outside database.",
                            "rationale": "More data would help.",
                            "external_data": {
                                "required": True,
                                "request": "Outside membrane records.",
                            },
                        }
                    ]
                }
            )
        )
        self.orchestrator._get_agent = Mock(return_value=evolution)
        self.orchestrator._update_session_state = AsyncMock()

        with self.assertLogs(
            "vegapunk.mas.workflow.orchestration_agent", level="WARNING"
        ):
            await self.orchestrator._run_evolution_phase(session)

        evolved = next(idea for idea in session.ideas if idea.parent_id == parent.id)
        self.assertFalse(evolved.external_data.required)
        self.assertEqual(evolved.external_data.request, "")


if __name__ == "__main__":
    unittest.main()
