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
            coverage_feedback = await asyncio.to_thread(
                runner.run,
                prompt,
                cwd=str(workspace_path),
            )
        except Exception as error:
            self._write_acquisition_record(
                workspace_path,
                request=request,
                coverage_feedback="",
                status="failed",
                error=str(error),
            )
            raise AgentExecutionError(f"Connector acquisition failed: {error}") from error

        self._write_acquisition_record(
            workspace_path,
            request=request,
            coverage_feedback=str(coverage_feedback),
            status="completed",
        )
        return {
            "coverage_feedback": str(coverage_feedback),
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
Finish with concise natural-language coverage feedback explaining what the saved data covers
and what remains unavailable. Do not lower or assess the scientific score of the Idea."""

    @staticmethod
    def _write_acquisition_record(
        workspace: Path,
        *,
        request: str,
        coverage_feedback: str,
        status: str,
        error: str | None = None,
    ) -> None:
        record = {
            "acquired_by": "connector",
            "request": request,
            "coverage_feedback": coverage_feedback,
            "status": status,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }
        if error:
            record["error"] = error
        (workspace / CONNECTOR_ACQUISITION_FILENAME).write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
