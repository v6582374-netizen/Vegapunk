from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from vegapunk.mas.agents.connector_agent import ConnectorAgent
from vegapunk.mas.memory.memory_manager import InMemoryMemoryManager
from vegapunk.mas.workflow.data_type import (
    ExternalDataDeclaration,
    Idea,
    Task,
    WorkflowSession,
    WorkflowState,
)
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
    def test_connector_runner_follows_launch_backend_without_a_system_model(self) -> None:
        """The Launch selects the backend; the backend owns its own model."""
        config = {
            "_global_config": {
                "exp_backend": "qwen_code",
                "proxy_settings": {"HTTPS_PROXY": "https://proxy.invalid"},
                "experiment": {"backend": "qwen_code"},
            },
        }

        with patch("vegapunk.experiments_utils_codex.CodexRunner") as codex_runner, patch(
            "vegapunk.experiments_utils_qwen_code.QwenCodeRunner"
        ) as qwen_runner:
            agent = ConnectorAgent(SimpleNamespace(), config)

            runner = agent._create_runner()

        self.assertIs(runner, qwen_runner.return_value)
        qwen_runner.assert_called_once_with({"HTTPS_PROXY": "https://proxy.invalid"})
        codex_runner.assert_not_called()

    def test_connector_registry_prompt_is_limited_to_description_and_docs(self) -> None:
        prompt = ConnectorAgent._build_prompt(
            request="Use NLR data.",
            registry=[
                {
                    "api_id": "nlr_developer_network",
                    "source": "NLR",
                    "description": "Official research data.",
                    "official_docs_url": "https://developer.nlr.gov/docs/",
                    "endpoint": "https://api.example.test/private",
                    "parameter_description": "secret field mapping",
                }
            ],
            idea={},
            goal={},
            workspace=Path("/tmp/connector-test"),
        )

        self.assertIn("Official research data.", prompt)
        self.assertIn("https://developer.nlr.gov/docs/", prompt)
        self.assertNotIn("https://api.example.test/private", prompt)
        self.assertNotIn("secret field mapping", prompt)

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
    async def test_public_web_data_bypasses_an_unrelated_registered_api(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            idea = Idea(
                id="idea-1",
                text="Assess GenAI's effect on employment.",
                external_data=ExternalDataDeclaration(required=True, request=(
                    "BLS employment projections by SOC occupation for 2022–2032."
                )),
            )
            session = WorkflowSession(
                id="session-1",
                task=Task(
                    id="task-1",
                    description="Study GenAI labor-market effects.",
                    domain="labor economics",
                ),
                ideas=[idea],
            )
            scholar = SimpleNamespace(
                execute=AsyncMock(return_value={"evidence": [], "references": []})
            )
            # Only the Connector holds the registry, so only the Connector can
            # find it irrelevant.  It saves nothing and opens the gate itself.
            async def connector_execute(context: dict, _: dict) -> dict:
                return {
                    "coverage_feedback": (
                        "No registered API serves labor-market projections."
                    ),
                    "open_web_evidence_gate": True,
                }

            connector = SimpleNamespace(
                execute=AsyncMock(side_effect=connector_execute)
            )

            async def web_evidence_execute(context: dict, _: dict) -> None:
                workspace = Path(context["idea_data_workspace"])
                (workspace / "bls_projections.csv").write_text(
                    "soc,employment\n15-1252,1650000\n", encoding="utf-8"
                )
                (workspace / MANIFEST_FILENAME).write_text(
                    json.dumps(
                        {
                            "artifacts": [
                                {
                                    "artifact_path": "bls_projections.csv",
                                    "source": "U.S. Bureau of Labor Statistics",
                                    "api_id": "non_api",
                                    "request": idea.external_data.request,
                                    "retrieved_at": "2026-08-10T12:00:00+00:00",
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )

            web_evidence = SimpleNamespace(
                execute=AsyncMock(side_effect=web_evidence_execute)
            )
            orchestrator = OrchestrationAgent(
                {
                    "workflow": {"external_data_workspace_root": str(root)},
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

            # The unrelated API is still bypassed -- but by the Connector's own
            # judgment, not by a route an Idea guessed before seeing the registry.
            connector.execute.assert_awaited_once()
            web_evidence.execute.assert_awaited_once()
            self.assertEqual(idea.evidence[0]["acquired_by"], "web_evidence")
            self.assertEqual(len(idea.evidence), 1)

    async def test_data_required_idea_admits_valid_local_connector_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            idea = Idea(
                id="idea-1",
                text="Measure membrane transport.",
                score=0.7,
                external_data=ExternalDataDeclaration(required=True, request="Water and salt permeability by salinity."),
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
                                    "request": idea.external_data.request,
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
                external_data=ExternalDataDeclaration(required=True, request="Water permeability by salinity."),
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

    async def test_connector_failure_falls_back_to_public_web_evidence(self) -> None:
        """A dead Connector (e.g. missing API key) must not silence the public web.

        The gate exists so the Connector can declare sufficient coverage.  A
        Connector that failed admitted zero evidence, so the fallback opens by
        construction instead of leaving the Idea to fabricate synthetic data.
        """
        with tempfile.TemporaryDirectory() as temporary_directory:
            idea = Idea(
                id="idea-1",
                text="Measure membrane transport.",
                external_data=ExternalDataDeclaration(required=True, request="Water permeability by salinity."),
            )
            session = WorkflowSession(
                id="session-1",
                task=Task(id="task-1", description="Study membrane transport.", domain="materials"),
                ideas=[idea],
            )
            scholar = SimpleNamespace(execute=AsyncMock(return_value={"evidence": [], "references": []}))
            connector = SimpleNamespace(
                execute=AsyncMock(side_effect=RuntimeError("NREL API key is not configured"))
            )

            async def web_evidence_execute(context: dict, _: dict) -> None:
                self.assertIn(
                    "NREL API key is not configured",
                    context["connector_coverage_feedback"],
                )
                workspace = Path(context["idea_data_workspace"])
                (workspace / "nrel_release.csv").write_text(
                    "salinity,permeability\n35,0.2\n", encoding="utf-8"
                )
                (workspace / MANIFEST_FILENAME).write_text(
                    json.dumps(
                        {
                            "artifacts": [
                                {
                                    "artifact_path": "nrel_release.csv",
                                    "source": "NREL",
                                    "api_id": "non_api",
                                    "request": idea.external_data.request,
                                    "retrieved_at": "2026-08-10T12:00:00+00:00",
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )

            web_evidence = SimpleNamespace(execute=AsyncMock(side_effect=web_evidence_execute))
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
            self.assertEqual(len(idea.evidence), 1)
            self.assertEqual(idea.evidence[0]["acquired_by"], "web_evidence")
            self.assertEqual(idea.acquisition_events[0]["acquired_by"], "connector")
            self.assertEqual(idea.acquisition_events[0]["status"], "failed")
            self.assertEqual(session.state, WorkflowState.EVOLVING)

    async def test_rejected_connector_manifest_opens_web_evidence_fallback(self) -> None:
        """A rejected manifest admitted zero evidence, voiding any sufficiency claim."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            idea = Idea(
                id="idea-1",
                text="Measure membrane transport.",
                external_data=ExternalDataDeclaration(required=True, request="Water permeability by salinity."),
            )
            session = WorkflowSession(
                id="session-1",
                task=Task(id="task-1", description="Study membrane transport.", domain="materials"),
                ideas=[idea],
            )
            scholar = SimpleNamespace(execute=AsyncMock(return_value={"evidence": [], "references": []}))

            async def connector_execute(context: dict, _: dict) -> dict:
                # Claims sufficiency, but writes a manifest missing required
                # provenance, so nothing can be admitted.
                workspace = Path(context["idea_data_workspace"])
                (workspace / MANIFEST_FILENAME).write_text(
                    json.dumps({"artifacts": [{"artifact_path": "missing.json"}]}),
                    encoding="utf-8",
                )
                return {
                    "coverage_feedback": "Sufficient coverage: all requested data was saved.",
                    "open_web_evidence_gate": False,
                }

            connector = SimpleNamespace(execute=AsyncMock(side_effect=connector_execute))

            async def web_evidence_execute(context: dict, _: dict) -> None:
                self.assertIn("rejected", context["connector_coverage_feedback"])
                workspace = Path(context["idea_data_workspace"])
                (workspace / "web.csv").write_text("salinity,permeability\n35,0.2\n", encoding="utf-8")
                (workspace / MANIFEST_FILENAME).write_text(
                    json.dumps(
                        {
                            "artifacts": [
                                {
                                    "artifact_path": "web.csv",
                                    "source": "NREL",
                                    "api_id": "non_api",
                                    "request": idea.external_data.request,
                                    "retrieved_at": "2026-08-10T12:00:00+00:00",
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )

            web_evidence = SimpleNamespace(execute=AsyncMock(side_effect=web_evidence_execute))
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
            self.assertEqual(len(idea.evidence), 1)
            self.assertEqual(idea.evidence[0]["acquired_by"], "web_evidence")
            self.assertEqual(idea.acquisition_events[0]["status"], "invalid_manifest")

    async def test_method_refinement_receives_admitted_connector_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            idea = Idea(
                id="idea-1",
                text="Measure membrane transport.",
                external_data=ExternalDataDeclaration(required=True, request="Water permeability by salinity."),
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
                                    "request": idea.external_data.request,
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
