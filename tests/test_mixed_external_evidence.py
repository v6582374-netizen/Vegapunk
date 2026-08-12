from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from vegapunk.mas.memory.memory_manager import InMemoryMemoryManager
from vegapunk.mas.workflow.data_type import Idea, Task, WorkflowSession, WorkflowState
from vegapunk.mas.workflow.external_data import MANIFEST_FILENAME
from vegapunk.mas.workflow.orchestration_agent import OrchestrationAgent


def _write_connector_artifact(workspace: Path, idea: Idea) -> None:
    (workspace / "shared-response.json").write_text("{}", encoding="utf-8")
    (workspace / MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "artifacts": [
                    {
                        "artifact_path": "shared-response.json",
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


def _append_web_artifact(workspace: Path, idea: Idea) -> None:
    (workspace / "shared-response.csv").write_text("salt,permeability\nNaCl,0.2\n", encoding="utf-8")
    manifest = json.loads((workspace / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    manifest["artifacts"].append(
        {
            "artifact_path": "shared-response.csv",
            "source": "Official supplementary dataset",
            "api_id": "non_api",
            "request": idea.external_data_request,
            "retrieved_at": "2026-08-06T10:01:00+00:00",
        }
    )
    (workspace / MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")


class MixedExternalEvidenceWorkflowTest(unittest.IsolatedAsyncioTestCase):
    async def test_mixed_batch_isolates_workspaces_failures_and_evolution_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_free = Idea(
                id="data-free",
                text="Use the supplied model.",
                score=0.1,
                requires_external_data=False,
                external_data_reason="The supplied model is sufficient.",
            )
            connector_only = Idea(
                id="connector-only",
                text="Measure water permeability.",
                score=0.2,
                requires_external_data=True,
                external_data_request="Water permeability by salinity.",
                external_data_route="registered_api",
            )
            web_supplemented = Idea(
                id="web-supplemented",
                text="Measure water and salt permeability.",
                score=0.3,
                requires_external_data=True,
                external_data_request="Water and salt permeability by salinity.",
                external_data_route="registered_api",
            )
            failed = Idea(
                id="failed-acquisition",
                text="Measure an unavailable quantity.",
                score=0.4,
                requires_external_data=True,
                external_data_request="Unavailable quantity by salinity.",
                external_data_route="registered_api",
            )
            ideas = [data_free, connector_only, web_supplemented, failed]
            session = WorkflowSession(
                id="mixed-session",
                task=Task(id="task-1", description="Study membrane transport.", domain="materials"),
                ideas=ideas,
            )
            active_acquisitions = 0
            peak_acquisitions = 0

            async def scholar_execute(context: dict, _: dict) -> dict:
                return {"evidence": [{"title": f"Paper for {context['hypothesis']['id']}"}], "references": []}

            async def connector_execute(context: dict, _: dict) -> dict:
                nonlocal active_acquisitions, peak_acquisitions
                idea = next(item for item in ideas if item.id == context["hypothesis"]["id"])
                active_acquisitions += 1
                peak_acquisitions = max(peak_acquisitions, active_acquisitions)
                try:
                    await asyncio.sleep(0.01)
                    if idea.id == failed.id:
                        raise RuntimeError("Connector source unavailable")
                    _write_connector_artifact(Path(context["idea_data_workspace"]), idea)
                    return {
                        "coverage_feedback": (
                            "Partial coverage: salt data is unavailable."
                            if idea.id == web_supplemented.id
                            else "Sufficient coverage: all requested data was saved."
                        ),
                        "open_web_evidence_gate": idea.id == web_supplemented.id,
                    }
                finally:
                    active_acquisitions -= 1

            async def web_execute(context: dict, _: dict) -> dict:
                nonlocal active_acquisitions, peak_acquisitions
                self.assertEqual(context["hypothesis"]["id"], web_supplemented.id)
                self.assertIn("Partial coverage", context["connector_coverage_feedback"])
                active_acquisitions += 1
                peak_acquisitions = max(peak_acquisitions, active_acquisitions)
                try:
                    await asyncio.sleep(0.01)
                    _append_web_artifact(Path(context["idea_data_workspace"]), web_supplemented)
                    return {"coverage_feedback": "Supplementary salt data saved."}
                finally:
                    active_acquisitions -= 1

            evolution_contexts: list[dict] = []

            async def evolution_execute(context: dict, _: dict) -> dict:
                evolution_contexts.append(context)
                return {"evolved_hypotheses": []}

            scholar = SimpleNamespace(execute=AsyncMock(side_effect=scholar_execute))
            connector = SimpleNamespace(execute=AsyncMock(side_effect=connector_execute))
            web_evidence = SimpleNamespace(execute=AsyncMock(side_effect=web_execute))
            evolution = SimpleNamespace(execute=AsyncMock(side_effect=evolution_execute))
            orchestrator = OrchestrationAgent(
                {
                    "workflow": {
                        "external_data_workspace_root": temporary_directory,
                        "max_concurrent_tasks": 1,
                    }
                },
                InMemoryMemoryManager(),
                model_runtime=SimpleNamespace(),
                agent_registry={
                    "scholar": scholar,
                    "connector": connector,
                    "web_evidence": web_evidence,
                    "evolution": evolution,
                },
            )

            session.state = WorkflowState.EXTERNAL_DATA
            await orchestrator._execute_current_phase(session)

            self.assertEqual(session.state, WorkflowState.EVOLVING)
            self.assertEqual(scholar.execute.await_count, 4)
            self.assertEqual(connector.execute.await_count, 3)
            web_evidence.execute.assert_awaited_once()
            self.assertEqual(peak_acquisitions, 1)
            self.assertEqual(data_free.data_workspace, "")
            self.assertEqual(
                len({connector_only.data_workspace, web_supplemented.data_workspace, failed.data_workspace}),
                3,
            )
            self.assertNotEqual(connector_only.data_workspace, web_supplemented.data_workspace)
            self.assertTrue(Path(connector_only.data_workspace, "shared-response.json").is_file())
            self.assertTrue(Path(web_supplemented.data_workspace, "shared-response.json").is_file())
            self.assertEqual(failed.score, 0.4)
            self.assertEqual(failed.evidence, [{"title": "Paper for failed-acquisition"}])
            self.assertEqual(failed.acquisition_events[0]["acquired_by"], "connector")
            self.assertEqual(failed.acquisition_events[0]["status"], "failed")

            await orchestrator._execute_current_phase(session)

            self.assertEqual(session.state, WorkflowState.RANKING)
            contexts_by_id = {context["hypothesis"]["id"]: context for context in evolution_contexts}
            self.assertEqual(len(contexts_by_id), 4)
            self.assertTrue(
                {"connector", "web_evidence"}.issubset(
                    {
                        entry.get("acquired_by")
                        for entry in contexts_by_id[web_supplemented.id]["evidence"]
                    }
                )
            )
            self.assertIn(
                "connector",
                {
                    entry.get("acquired_by")
                    for entry in contexts_by_id[connector_only.id]["evidence"]
                },
            )

    async def test_web_evidence_reaches_refinement_context_through_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            idea = Idea(
                id="refinement-idea",
                text="Measure water and salt permeability.",
                requires_external_data=True,
                external_data_request="Water and salt permeability by salinity.",
                external_data_route="registered_api",
                method_details={"method": "Compare transport curves."},
            )
            session = WorkflowSession(
                id="refinement-session",
                task=Task(id="task-1", description="Study membrane transport.", domain="materials"),
                ideas=[idea],
                method_phase=True,
            )
            scholar = SimpleNamespace(execute=AsyncMock(return_value={"evidence": [], "references": []}))

            async def connector_execute(context: dict, _: dict) -> dict:
                _write_connector_artifact(Path(context["idea_data_workspace"]), idea)
                return {"coverage_feedback": "Partial coverage: salt data is unavailable.", "open_web_evidence_gate": True}

            async def web_execute(context: dict, _: dict) -> dict:
                _append_web_artifact(Path(context["idea_data_workspace"]), idea)
                return {"coverage_feedback": "Supplementary salt data saved."}

            refinement_contexts: list[dict] = []

            async def refinement_execute(context: dict, _: dict) -> dict:
                refinement_contexts.append(context)
                return {"refined_method": {"method": "Use both local artifacts."}}

            orchestrator = OrchestrationAgent(
                {"workflow": {"external_data_workspace_root": temporary_directory}},
                InMemoryMemoryManager(),
                model_runtime=SimpleNamespace(),
                agent_registry={
                    "scholar": scholar,
                    "connector": SimpleNamespace(execute=AsyncMock(side_effect=connector_execute)),
                    "web_evidence": SimpleNamespace(execute=AsyncMock(side_effect=web_execute)),
                    "refinement": SimpleNamespace(execute=AsyncMock(side_effect=refinement_execute)),
                },
            )

            session.state = WorkflowState.EXTERNAL_DATA
            await orchestrator.memory_manager.store_session(session)
            orchestrator.active_sessions[session.id] = session

            completed_session = await orchestrator.run_session(session.id)

            self.assertEqual(completed_session.state, WorkflowState.COMPLETED)
            self.assertEqual(
                {entry.get("acquired_by") for entry in refinement_contexts[0]["literature"]},
                {"connector", "web_evidence"},
            )
            self.assertEqual(idea.refined_method_details["method"], "Use both local artifacts.")


if __name__ == "__main__":
    unittest.main()
