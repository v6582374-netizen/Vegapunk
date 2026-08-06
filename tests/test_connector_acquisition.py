from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from vegapunk.mas.agents.connector_agent import ConnectorAgent
from vegapunk.mas.memory.memory_manager import InMemoryMemoryManager
from vegapunk.mas.workflow.data_type import Idea, Task, WorkflowSession, WorkflowState
from vegapunk.mas.workflow.external_data import (
    MANIFEST_FILENAME,
    allocate_idea_data_workspace,
    validate_idea_evidence_manifest,
)
from vegapunk.mas.workflow.orchestration_agent import OrchestrationAgent


API_REGISTRY = [
    {
        "api_id": "nrel-example",
        "source": "NREL",
        "official_docs_url": "https://developer.nrel.gov/docs/",
        "capabilities": "Structured energy and materials data.",
        "parameter_description": "Endpoint-specific query parameters are documented by NREL.",
    }
]


class _FakeCodexRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Path]] = []

    def run(self, prompt: str, cwd: str) -> str:
        workspace = Path(cwd)
        self.calls.append((prompt, workspace))
        (workspace / "permeability.json").write_text('{"value": 1}', encoding="utf-8")
        (workspace / MANIFEST_FILENAME).write_text(
            json.dumps(
                {
                    "artifacts": [
                        {
                            "artifact_path": "permeability.json",
                            "source": "NREL",
                            "api_id": "nrel-example",
                            "docs_url": "https://developer.nrel.gov/docs/",
                            "request": "Water and salt permeability by salinity.",
                            "retrieved_at": "2026-08-06T10:00:00+00:00",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return "Coverage: the requested salinity series was saved locally."


class ConnectorAgentTest(unittest.IsolatedAsyncioTestCase):
    def test_each_idea_receives_an_isolated_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            first = allocate_idea_data_workspace(temporary_directory, "session-1", "idea-1")
            second = allocate_idea_data_workspace(temporary_directory, "session-1", "idea-2")

            self.assertNotEqual(first, second)
            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())

    async def test_connector_uses_codex_runner_with_request_registry_and_workspace(self) -> None:
        runner = _FakeCodexRunner()
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            agent = ConnectorAgent(
                SimpleNamespace(),
                {"runner_factory": lambda: runner},
            )

            result = await agent.execute(
                {
                    "external_data_request": "Water and salt permeability by salinity.",
                    "api_registry": API_REGISTRY,
                    "idea_data_workspace": str(workspace),
                    "hypothesis": {"id": "idea-1", "text": "Measure membrane transport."},
                    "goal": {"description": "Study membrane transport."},
                },
                {},
            )

            self.assertEqual(result["coverage_feedback"], "Coverage: the requested salinity series was saved locally.")
            prompt, cwd = runner.calls[0]
            self.assertEqual(cwd, workspace)
            self.assertIn("Water and salt permeability by salinity.", prompt)
            self.assertIn("nrel-example", prompt)
            self.assertIn("https://developer.nrel.gov/docs/", prompt)

    def test_manifest_rejects_path_outside_workspace_and_missing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workspace = root / "workspace"
            workspace.mkdir()
            outside = root / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            (workspace / MANIFEST_FILENAME).write_text(
                json.dumps(
                    {
                        "artifacts": [
                            {
                                "artifact_path": str(outside),
                                "source": "NREL",
                                "api_id": "nrel-example",
                                "docs_url": "https://developer.nrel.gov/docs/",
                                "request": "Water permeability.",
                                "retrieved_at": "2026-08-06T10:00:00+00:00",
                            },
                            {
                                "artifact_path": "missing-source.json",
                                "api_id": "nrel-example",
                                "docs_url": "https://developer.nrel.gov/docs/",
                                "request": "Salt permeability.",
                                "retrieved_at": "2026-08-06T10:00:00+00:00",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            validation = validate_idea_evidence_manifest(workspace)

            self.assertFalse(validation.valid)
            self.assertEqual(validation.entries, [])
            self.assertGreaterEqual(len(validation.errors), 2)

    def test_manifest_rejects_missing_manifest_and_required_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            self.assertFalse(validate_idea_evidence_manifest(workspace).valid)

            (workspace / "response.json").write_text("{}", encoding="utf-8")
            (workspace / MANIFEST_FILENAME).write_text(
                json.dumps(
                    {
                        "artifacts": [
                            {
                                "artifact_path": "response.json",
                                "source": "NREL",
                                "api_id": "nrel-example",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            validation = validate_idea_evidence_manifest(workspace)

            self.assertFalse(validation.valid)
            self.assertEqual(validation.entries, [])
            self.assertGreaterEqual(len(validation.errors), 3)


class ConnectorWorkflowTest(unittest.IsolatedAsyncioTestCase):
    async def test_data_required_idea_admits_valid_local_connector_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            idea = Idea(
                id="idea-1",
                text="Measure membrane transport.",
                score=0.7,
                requires_external_data=True,
                external_data_request="Water and salt permeability by salinity.",
            )
            session = WorkflowSession(
                id="session-1",
                task=Task(id="task-1", description="Study membrane transport.", domain="materials"),
                ideas=[idea],
            )
            scholar = SimpleNamespace(execute=AsyncMock(return_value={"evidence": [{"title": "Paper"}], "references": []}))

            async def connector_execute(context: dict, _: dict) -> dict:
                workspace = Path(context["idea_data_workspace"])
                (workspace / "permeability.json").write_text('{"value": 1}', encoding="utf-8")
                (workspace / MANIFEST_FILENAME).write_text(
                    json.dumps(
                        {
                            "artifacts": [
                                {
                                    "artifact_path": "permeability.json",
                                    "source": "NREL",
                                    "api_id": "nrel-example",
                                    "docs_url": "https://developer.nrel.gov/docs/",
                                    "request": idea.external_data_request,
                                    "retrieved_at": "2026-08-06T10:00:00+00:00",
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                return {"coverage_feedback": "Coverage complete."}

            connector = SimpleNamespace(execute=AsyncMock(side_effect=connector_execute))
            orchestrator = OrchestrationAgent(
                {
                    "workflow": {"external_data_workspace_root": str(root)},
                    "external_data": {"api_registry": API_REGISTRY},
                },
                InMemoryMemoryManager(),
                model_runtime=SimpleNamespace(),
                agent_registry={"scholar": scholar, "connector": connector},
            )

            await orchestrator._run_external_data_phase(session)

            self.assertEqual(idea.score, 0.7)
            self.assertTrue(Path(idea.data_workspace).is_dir())
            connector.execute.assert_awaited_once()
            self.assertIn({"title": "Paper"}, idea.evidence)
            connector_evidence = next(item for item in idea.evidence if item.get("acquired_by") == "connector")
            self.assertEqual(connector_evidence["source"], "NREL")
            self.assertTrue(Path(connector_evidence["artifact_path"]).is_file())
            self.assertEqual(session.state, WorkflowState.EVOLVING)

    async def test_connector_failure_keeps_score_and_does_not_add_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            idea = Idea(
                id="idea-1",
                text="Measure membrane transport.",
                score=0.7,
                requires_external_data=True,
                external_data_request="Water permeability by salinity.",
            )
            session = WorkflowSession(
                id="session-1",
                task=Task(id="task-1", description="Study membrane transport.", domain="materials"),
                ideas=[idea],
            )
            scholar = SimpleNamespace(execute=AsyncMock(return_value={"evidence": [], "references": []}))
            connector = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("NREL unavailable")))
            orchestrator = OrchestrationAgent(
                {"workflow": {"external_data_workspace_root": temporary_directory}},
                InMemoryMemoryManager(),
                model_runtime=SimpleNamespace(),
                agent_registry={"scholar": scholar, "connector": connector},
            )

            await orchestrator._run_external_data_phase(session)

            self.assertEqual(idea.score, 0.7)
            self.assertEqual(idea.evidence, [])
            self.assertEqual(session.state, WorkflowState.EVOLVING)

    async def test_method_refinement_receives_admitted_connector_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            idea = Idea(
                id="idea-1",
                text="Measure membrane transport.",
                requires_external_data=True,
                external_data_request="Water permeability by salinity.",
            )
            session = WorkflowSession(
                id="session-1",
                task=Task(id="task-1", description="Study membrane transport.", domain="materials"),
                ideas=[idea],
                method_phase=True,
            )
            scholar = SimpleNamespace(execute=AsyncMock(return_value={"evidence": [], "references": []}))

            async def connector_execute(context: dict, _: dict) -> dict:
                workspace = Path(context["idea_data_workspace"])
                (workspace / "permeability.json").write_text('{"value": 1}', encoding="utf-8")
                (workspace / MANIFEST_FILENAME).write_text(
                    json.dumps(
                        {
                            "artifacts": [
                                {
                                    "artifact_path": "permeability.json",
                                    "source": "NREL",
                                    "api_id": "nrel-example",
                                    "docs_url": "https://developer.nrel.gov/docs/",
                                    "request": idea.external_data_request,
                                    "retrieved_at": "2026-08-06T10:00:00+00:00",
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                return {"coverage_feedback": "Coverage complete."}

            connector = SimpleNamespace(execute=AsyncMock(side_effect=connector_execute))
            orchestrator = OrchestrationAgent(
                {"workflow": {"external_data_workspace_root": temporary_directory}},
                InMemoryMemoryManager(),
                model_runtime=SimpleNamespace(),
                agent_registry={"scholar": scholar, "connector": connector},
            )

            await orchestrator._run_external_data_phase(session)

            self.assertEqual(session.state, WorkflowState.REFINING)
            self.assertEqual(len(idea.evidence), 1)
            self.assertEqual(len(idea.refine_evidence), 1)
            self.assertEqual(idea.refine_evidence[0]["acquired_by"], "connector")


if __name__ == "__main__":
    unittest.main()
