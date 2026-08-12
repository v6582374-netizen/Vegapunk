from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from vegapunk.mas.agents.generation_agent import GenerationAgent
from vegapunk.mas.memory.memory_manager import InMemoryMemoryManager
from vegapunk.mas.workflow.data_type import Idea, Task, WorkflowSession, WorkflowState
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
    async def test_generation_schema_and_result_include_explicit_declaration(self) -> None:
        model = _StructuredModel(
            {
                "hypotheses": [
                    {
                        "text": "Measure permeability under salinity gradients.",
                        "rationale": "The gradient may change transport selectivity.",
                        "requires_external_data": True,
                        "external_data_request": "Water and salt permeability by salinity and temperature.",
                        "external_data_reason": "",
                        "external_data_route": "public_web",
                    },
                    {
                        "text": "Compare two existing analytical models.",
                        "rationale": "The comparison can use the supplied equations.",
                        "requires_external_data": False,
                        "external_data_request": "",
                        "external_data_reason": "The idea is evaluated from the supplied analytical models.",
                        "external_data_route": "none",
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
                {
                    "use_memory": False,
                    "filter_failed_ideas": False,
                },
            )

        agent.get_allowed_tools = AsyncMock(return_value=[])
        result = await agent.execute(
            {"goal": {"description": "Study membrane transport."}},
            {},
        )

        hypotheses = result["hypotheses"]
        self.assertEqual(hypotheses[0]["requires_external_data"], True)
        self.assertIn("salinity", hypotheses[0]["external_data_request"])
        self.assertEqual(hypotheses[0]["external_data_route"], "public_web")
        self.assertEqual(hypotheses[1]["requires_external_data"], False)
        self.assertTrue(hypotheses[1]["external_data_reason"])

        item_schema = model.schemas[0]["properties"]["hypotheses"]["items"]
        self.assertEqual(
            set(item_schema["required"]),
            {
                "text",
                "rationale",
                "requires_external_data",
                "external_data_request",
                "external_data_reason",
                "external_data_route",
            },
        )
        self.assertIn("external_data_route", model.system_prompts[0])

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
                        "requires_external_data": True,
                        "external_data_request": "",
                        "external_data_reason": "",
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
                {
                    "use_memory": False,
                    "filter_failed_ideas": False,
                },
            )

        agent.get_allowed_tools = AsyncMock(return_value=[])
        with self.assertLogs(
            "vegapunk.mas.agents.generation_agent",
            level="WARNING",
        ):
            result = await agent.execute(
                {"goal": {"description": "Study membrane transport."}},
                {},
            )

        for hypothesis in result["hypotheses"]:
            self.assertFalse(hypothesis["requires_external_data"])
            self.assertEqual(hypothesis["external_data_request"], "")
            self.assertTrue(hypothesis["external_data_reason"])

    async def test_regenerated_hypothesis_is_normalized_before_returning(self) -> None:
        model = _StructuredModel(
            {
                "hypotheses": [
                    {
                        "text": "Initial candidate.",
                        "rationale": "Initial rationale.",
                        "requires_external_data": False,
                        "external_data_request": "",
                        "external_data_reason": "No data is needed initially.",
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
                {
                    "use_memory": False,
                    "filter_failed_ideas": True,
                },
            )

        agent.get_allowed_tools = AsyncMock(return_value=[])
        agent.use_memory = True
        agent.memory_retriever = object()
        agent._filter_and_regenerate_hypotheses = AsyncMock(
            return_value=[
                {
                    "text": "Regenerated candidate.",
                    "rationale": "Regenerated rationale.",
                }
            ]
        )

        result = await agent.execute(
            {"goal": {"description": "Study membrane transport."}},
            {},
        )

        regenerated = result["hypotheses"][0]
        self.assertFalse(regenerated["requires_external_data"])
        self.assertEqual(regenerated["external_data_request"], "")
        self.assertTrue(regenerated["external_data_reason"])


class IdeaExternalDataPersistenceTest(unittest.TestCase):
    def test_external_data_declaration_round_trips_with_idea(self) -> None:
        idea = Idea(
            id="idea-1",
            text="Measure permeability.",
            requires_external_data=True,
            external_data_request="Permeability by salinity.",
            external_data_reason="",
        )

        restored = Idea.from_dict(idea.to_dict())

        self.assertTrue(restored.requires_external_data)
        self.assertEqual(
            restored.external_data_request,
            "Permeability by salinity.",
        )
        self.assertEqual(restored.external_data_reason, "")


class OrchestrationExternalDataGateTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.orchestrator = OrchestrationAgent(
            {"workflow": {}},
            InMemoryMemoryManager(),
            model_runtime=SimpleNamespace(),
        )

    def test_data_free_idea_is_closed(self) -> None:
        idea = Idea(
            id="idea-1",
            text="Use the supplied analytical model.",
            requires_external_data=False,
            external_data_reason="The supplied model is sufficient.",
        )

        self.assertFalse(self.orchestrator.should_acquire_external_data(idea))

    async def test_data_free_idea_keeps_scholar_retrieval_enabled(self) -> None:
        idea = Idea(
            id="idea-1",
            text="Use the supplied analytical model.",
            requires_external_data=False,
            external_data_reason="The supplied model is sufficient.",
        )
        session = WorkflowSession(
            id="session-1",
            task=Task(
                id="task-1",
                description="Study membrane transport.",
                domain="materials science",
            ),
            ideas=[idea],
        )
        scholar = SimpleNamespace(
            execute=AsyncMock(return_value={"evidence": [{"title": "Paper"}], "references": []})
        )
        self.orchestrator._get_agent = Mock(return_value=scholar)
        self.orchestrator._update_session_state = AsyncMock()

        self.assertFalse(self.orchestrator.should_acquire_external_data(idea))
        await self.orchestrator._run_external_data_phase(session)

        scholar.execute.assert_awaited_once()
        self.assertEqual(idea.evidence, [{"title": "Paper"}])
        self.orchestrator._update_session_state.assert_awaited_once_with(
            session,
            WorkflowState.EVOLVING,
        )

    def test_data_required_idea_opens_gate_only_with_concrete_request(self) -> None:
        valid = Idea(
            id="idea-1",
            text="Measure permeability.",
            requires_external_data=True,
            external_data_request="Permeability by salinity.",
        )
        invalid = Idea(
            id="idea-2",
            text="Measure permeability.",
            requires_external_data=True,
            external_data_request=" ",
        )

        self.assertTrue(self.orchestrator.should_acquire_external_data(valid))
        with self.assertLogs(
            "vegapunk.mas.workflow.orchestration_agent",
            level="WARNING",
        ):
            self.assertFalse(self.orchestrator.should_acquire_external_data(invalid))
        self.assertTrue(invalid.external_data_reason)

    async def test_evolved_idea_preserves_its_parent_public_data_route(self) -> None:
        parent = Idea(
            id="idea-1",
            text="Assess GenAI labor-market effects.",
            requires_external_data=True,
            external_data_request="BLS employment projections by SOC occupation.",
            external_data_route="public_web",
        )
        session = WorkflowSession(
            id="session-1",
            task=Task(
                id="task-1",
                description="Study GenAI labor-market effects.",
                domain="labor economics",
            ),
            ideas=[parent],
        )
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
        self.assertTrue(evolved.requires_external_data)
        self.assertEqual(evolved.external_data_route, "public_web")
        self.assertEqual(
            evolved.external_data_request,
            "BLS employment projections by SOC occupation.",
        )


if __name__ == "__main__":
    unittest.main()
