from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from vegapunk.mas.agents.connector_agent import ConnectorAgent
from vegapunk.mas.agents.web_evidence_agent import WebEvidenceAgent
from vegapunk.mas.memory.memory_manager import InMemoryMemoryManager
from vegapunk.mas.workflow.data_type import Idea, Task, WorkflowSession, WorkflowState
from vegapunk.mas.workflow.external_data import MANIFEST_FILENAME
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


class _GateRunner:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[tuple[str, str]] = []

    def run(self, prompt: str, cwd: str) -> str:
        self.calls.append((prompt, cwd))
        return self.output


class WebEvidenceAgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_connector_preserves_empty_coverage_and_opens_its_own_gate(self) -> None:
        runner = _GateRunner(
            json.dumps(
                {
                    "coverage_feedback": "",
                    "open_web_evidence_gate": True,
                }
            )
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            agent = ConnectorAgent(SimpleNamespace(), {"runner_factory": lambda: runner})

            result = await agent.execute(
                {
                    "external_data_request": "Water permeability by salinity.",
                    "api_registry": API_REGISTRY,
                    "idea_data_workspace": temporary_directory,
                    "hypothesis": {"id": "idea-1"},
                    "goal": {"description": "Study membrane transport."},
                },
                {},
            )

            self.assertEqual(result["coverage_feedback"], "")
            self.assertTrue(result["open_web_evidence_gate"])
            self.assertIn("open_web_evidence_gate", runner.calls[0][0])

    async def test_connector_gate_handles_prose_coverage_without_suppressing_supplementation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            partial = ConnectorAgent(
                SimpleNamespace(),
                {"runner_factory": lambda: _GateRunner("Partial coverage: salt data is unavailable.")},
            )
            sufficient = ConnectorAgent(
                SimpleNamespace(),
                {"runner_factory": lambda: _GateRunner("Sufficient coverage: all requested data was saved.")},
            )
            context = {
                "external_data_request": "Water permeability by salinity.",
                "api_registry": API_REGISTRY,
                "idea_data_workspace": temporary_directory,
                "hypothesis": {"id": "idea-1"},
                "goal": {"description": "Study membrane transport."},
            }

            partial_result = await partial.execute(context, {})
            sufficient_result = await sufficient.execute(context, {})

            self.assertTrue(partial_result["open_web_evidence_gate"])
            self.assertFalse(sufficient_result["open_web_evidence_gate"])

    async def test_web_evidence_uses_same_workspace_and_connector_feedback(self) -> None:
        runner = _GateRunner("Web evidence saved locally.")
        with tempfile.TemporaryDirectory() as temporary_directory:
            agent = WebEvidenceAgent(SimpleNamespace(), {"runner_factory": lambda: runner})

            result = await agent.execute(
                {
                    "external_data_request": "Water permeability by salinity.",
                    "connector_coverage_feedback": "Partial coverage: no salt measurements.",
                    "api_registry": API_REGISTRY,
                    "idea_data_workspace": temporary_directory,
                    "hypothesis": {"id": "idea-1"},
                    "goal": {"description": "Study membrane transport."},
                },
                {},
            )

            prompt, cwd = runner.calls[0]
            self.assertEqual(cwd, temporary_directory)
            self.assertEqual(result["coverage_feedback"], "Web evidence saved locally.")
            self.assertIn("Water permeability by salinity.", prompt)
            self.assertIn("Partial coverage: no salt measurements.", prompt)
            self.assertIn("NREL", prompt)
            self.assertIn("Continue research freely", prompt)
            self.assertIn("additional Connector-specific search restrictions", prompt)


class WebEvidenceWorkflowTest(unittest.IsolatedAsyncioTestCase):
    async def test_partial_connector_coverage_opens_web_evidence_and_admits_new_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            idea = Idea(
                id="idea-1",
                text="Measure membrane transport.",
                requires_external_data=True,
                external_data_request="Water and salt permeability by salinity.",
            )
            session = WorkflowSession(
                id="session-1",
                task=Task(id="task-1", description="Study membrane transport.", domain="materials"),
                ideas=[idea],
            )
            scholar = SimpleNamespace(execute=AsyncMock(return_value={"evidence": [], "references": []}))

            async def connector_execute(context: dict, _: dict) -> dict:
                workspace = Path(context["idea_data_workspace"])
                (workspace / "connector.json").write_text("{}", encoding="utf-8")
                (workspace / MANIFEST_FILENAME).write_text(
                    json.dumps(
                        {
                            "artifacts": [
                                {
                                    "artifact_path": "connector.json",
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
                return {
                    "coverage_feedback": "Partial coverage: salt permeability is unavailable.",
                    "open_web_evidence_gate": True,
                }

            async def web_execute(context: dict, _: dict) -> dict:
                workspace = Path(context["idea_data_workspace"])
                self.assertEqual(
                    context["connector_coverage_feedback"],
                    "Partial coverage: salt permeability is unavailable.",
                )
                self.assertEqual(context["external_data_request"], idea.external_data_request)
                self.assertEqual(context["api_registry"], API_REGISTRY)
                (workspace / "web.csv").write_text("salt,permeability\nNaCl,0.2\n", encoding="utf-8")
                manifest = json.loads((workspace / MANIFEST_FILENAME).read_text(encoding="utf-8"))
                manifest["artifacts"].append(
                    {
                        "artifact_path": "web.csv",
                        "source": "Official supplementary dataset",
                        "api_id": "non_api",
                        "request": idea.external_data_request,
                        "retrieved_at": "2026-08-06T10:01:00+00:00",
                    }
                )
                (workspace / MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
                return {"coverage_feedback": "Supplementary salt data saved."}

            connector = SimpleNamespace(execute=AsyncMock(side_effect=connector_execute))
            web_evidence = SimpleNamespace(execute=AsyncMock(side_effect=web_execute))
            orchestrator = OrchestrationAgent(
                {
                    "workflow": {"external_data_workspace_root": temporary_directory},
                    "external_data": {"api_registry": API_REGISTRY},
                },
                InMemoryMemoryManager(),
                model_runtime=SimpleNamespace(),
                agent_registry={
                    "scholar": scholar,
                    "connector": connector,
                    "web_evidence": web_evidence,
                },
            )

            await orchestrator._run_external_data_phase(session)

            web_evidence.execute.assert_awaited_once()
            self.assertEqual(session.state, WorkflowState.EVOLVING)
            self.assertEqual(
                {entry.get("acquired_by") for entry in idea.evidence},
                {"connector", "web_evidence"},
            )
            web_entry = next(entry for entry in idea.evidence if entry.get("acquired_by") == "web_evidence")
            self.assertTrue(Path(web_entry["artifact_path"]).is_file())
            self.assertEqual(web_entry["api_id"], "non_api")

    async def test_sufficient_connector_coverage_keeps_web_evidence_closed(self) -> None:
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
            )
            scholar = SimpleNamespace(execute=AsyncMock(return_value={"evidence": [], "references": []}))

            async def connector_execute(context: dict, _: dict) -> dict:
                workspace = Path(context["idea_data_workspace"])
                (workspace / "connector.json").write_text("{}", encoding="utf-8")
                (workspace / MANIFEST_FILENAME).write_text(
                    json.dumps(
                        {
                            "artifacts": [
                                {
                                    "artifact_path": "connector.json",
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
                return {
                    "coverage_feedback": "Sufficient coverage: all requested data was saved.",
                    "open_web_evidence_gate": False,
                }

            connector = SimpleNamespace(execute=AsyncMock(side_effect=connector_execute))
            web_evidence = SimpleNamespace(execute=AsyncMock())
            orchestrator = OrchestrationAgent(
                {"workflow": {"external_data_workspace_root": temporary_directory}},
                InMemoryMemoryManager(),
                model_runtime=SimpleNamespace(),
                agent_registry={
                    "scholar": scholar,
                    "connector": connector,
                    "web_evidence": web_evidence,
                },
            )

            await orchestrator._run_external_data_phase(session)

            web_evidence.execute.assert_not_awaited()
            self.assertEqual(len(idea.evidence), 1)


if __name__ == "__main__":
    unittest.main()
