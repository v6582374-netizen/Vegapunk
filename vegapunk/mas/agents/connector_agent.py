"""Connector agent for structured external-data acquisition through Codex."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping

from .base_agent import AgentExecutionError, BaseAgent
from ..workflow.external_data import CONNECTOR_ACQUISITION_FILENAME, MANIFEST_FILENAME


class ConnectorAgent(BaseAgent):
    """Ask the existing Codex runner to acquire API data into one Idea workspace."""

    async def execute(self, context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        del params
        request = context.get("external_data_request")
        registry = context.get("api_registry")
        workspace = context.get("idea_data_workspace")
        if not isinstance(request, str) or not request.strip():
            raise ValueError("Connector requires a concrete external_data_request")
        if not isinstance(registry, list):
            raise ValueError("Connector requires an API registry list")
        if not isinstance(workspace, str) or not workspace:
            raise ValueError("Connector requires an Idea data workspace")

        workspace_path = Path(workspace).expanduser().resolve()
        workspace_path.mkdir(parents=True, exist_ok=True)
        prompt = self._build_prompt(
            request=request.strip(),
            registry=registry,
            idea=context.get("hypothesis", {}),
            goal=context.get("goal", {}),
            workspace=workspace_path,
        )
        runner = self._create_runner()
        try:
            runner_output = await asyncio.to_thread(
                runner.run,
                prompt,
                cwd=str(workspace_path),
            )
        except Exception as error:
            self._write_acquisition_record(
                workspace_path,
                request=request,
                coverage_feedback="",
                open_web_evidence_gate=False,
                status="failed",
                error=str(error),
            )
            raise AgentExecutionError(f"Connector acquisition failed: {error}") from error

        coverage_feedback, open_web_evidence_gate = self._parse_coverage_decision(
            str(runner_output)
        )
        self._write_acquisition_record(
            workspace_path,
            request=request,
            coverage_feedback=coverage_feedback,
            open_web_evidence_gate=open_web_evidence_gate,
            status="completed",
        )
        return {
            "coverage_feedback": coverage_feedback,
            "open_web_evidence_gate": open_web_evidence_gate,
            "workspace": str(workspace_path),
            "manifest_path": str(workspace_path / MANIFEST_FILENAME),
        }

    def _create_runner(self) -> Any:
        factory: Callable[[], Any] | None = self.config.get("runner_factory")
        if factory is not None:
            return factory()

        global_config = self.config.get("_global_config", {})
        experiment_config = global_config.get("experiment", {})
        from vegapunk.experiments_utils_codex import CodexRunner

        return CodexRunner(
            global_config.get("proxy_settings"),
            model=experiment_config.get("model", "gpt-5.6-sol"),
        )

    @staticmethod
    def _build_prompt(
        *,
        request: str,
        registry: list[Mapping[str, Any]],
        idea: Any,
        goal: Any,
        workspace: Path,
    ) -> str:
        return f"""You are the structured-data Connector for one research Idea.

Research goal:
{json.dumps(goal, ensure_ascii=False, indent=2)}

Idea:
{json.dumps(idea, ensure_ascii=False, indent=2)}

Concrete external-data request:
{request}

Available API registry (choose the appropriate available API yourself):
{json.dumps(registry, ensure_ascii=False, indent=2)}

Use the available APIs through this Codex workspace and save every raw response or
downloaded data file under {workspace}. Do not report an artifact that was not saved
locally. Write {MANIFEST_FILENAME} in that workspace as JSON with an `artifacts` list.
Each retained API artifact must include artifact_path, source, api_id, docs_url, request,
and retrieved_at (ISO-8601). artifact_path must point to a real file inside this workspace.
Finish with exactly one JSON object containing `coverage_feedback` (a natural-language
summary of saved coverage and remaining gaps) and `open_web_evidence_gate` (a boolean). Set the
gate true when coverage is empty or partial and supplementary Web Evidence would be useful; set
it false only when the saved local artifacts sufficiently cover the request. Do not lower or
assess the scientific score of the Idea."""

    @staticmethod
    def _parse_coverage_decision(output: str) -> tuple[str, bool]:
        """Read the Connector-owned Web Evidence startup decision from Codex output."""
        payload = ConnectorAgent._extract_json_object(output)
        if isinstance(payload, Mapping):
            feedback = payload.get("coverage_feedback")
            coverage_feedback = (
                feedback.strip() if isinstance(feedback, str) else output.strip()
            )
            gate = payload.get("open_web_evidence_gate")
            if isinstance(gate, bool):
                return coverage_feedback, gate
        else:
            coverage_feedback = output.strip()

        return coverage_feedback, ConnectorAgent._coverage_needs_web_evidence(
            coverage_feedback
        )

    @staticmethod
    def _extract_json_object(output: str) -> Mapping[str, Any] | None:
        """Accept bare, fenced, or prose-wrapped JSON emitted by the Codex runner."""
        decoder = json.JSONDecoder()
        for start in (index for index, character in enumerate(output) if character == "{"):
            try:
                payload, _ = decoder.raw_decode(output[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, Mapping):
                return payload
        return None

    @staticmethod
    def _coverage_needs_web_evidence(coverage_feedback: str) -> bool:
        """Keep the Connector gate open unless its own feedback establishes sufficiency."""
        feedback = coverage_feedback.lower()
        if not feedback:
            return True
        incomplete_markers = (
            "partial",
            "incomplete",
            "unavailable",
            "missing",
            "insufficient",
            "no coverage",
            "no data",
            "not covered",
            "unable",
        )
        if any(marker in feedback for marker in incomplete_markers):
            return True
        sufficient_markers = (
            "sufficient",
            "complete coverage",
            "fully covers",
            "all requested",
        )
        if any(marker in feedback for marker in sufficient_markers):
            return False
        return True

    @staticmethod
    def _write_acquisition_record(
        workspace: Path,
        *,
        request: str,
        coverage_feedback: str,
        open_web_evidence_gate: bool,
        status: str,
        error: str | None = None,
    ) -> None:
        record = {
            "acquired_by": "connector",
            "request": request,
            "coverage_feedback": coverage_feedback,
            "open_web_evidence_gate": open_web_evidence_gate,
            "status": status,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }
        if error:
            record["error"] = error
        (workspace / CONNECTOR_ACQUISITION_FILENAME).write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
