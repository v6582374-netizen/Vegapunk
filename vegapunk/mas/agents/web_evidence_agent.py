"""Web Evidence agent for Connector-authorized external-data supplementation."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping

from .base_agent import AgentExecutionError, BaseAgent
from ..workflow.external_data import (
    MANIFEST_FILENAME,
    WEB_EVIDENCE_ACQUISITION_FILENAME,
)


class WebEvidenceAgent(BaseAgent):
    """Acquire supplementary local evidence after the Connector opens its gate."""

    async def execute(self, context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        del params
        request = context.get("external_data_request")
        connector_feedback = context.get("connector_coverage_feedback")
        registry = context.get("api_registry")
        workspace = context.get("idea_data_workspace")
        if not isinstance(request, str) or not request.strip():
            raise ValueError("Web Evidence requires a concrete external_data_request")
        if not isinstance(connector_feedback, str):
            raise ValueError("Web Evidence requires Connector coverage feedback")
        if not isinstance(registry, list):
            raise ValueError("Web Evidence requires an API registry list")
        if not isinstance(workspace, str) or not workspace:
            raise ValueError("Web Evidence requires an Idea data workspace")

        workspace_path = Path(workspace).expanduser().resolve()
        workspace_path.mkdir(parents=True, exist_ok=True)
        prompt = self._build_prompt(
            request=request.strip(),
            connector_feedback=connector_feedback,
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
                connector_feedback=connector_feedback,
                coverage_feedback="",
                status="failed",
                error=str(error),
            )
            raise AgentExecutionError(f"Web Evidence acquisition failed: {error}") from error

        self._write_acquisition_record(
            workspace_path,
            request=request,
            connector_feedback=connector_feedback,
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
        connector_feedback: str,
        registry: list[Mapping[str, Any]],
        idea: Any,
        goal: Any,
        workspace: Path,
    ) -> str:
        return f"""You are the Web Evidence Agent supplementing one research Idea.

Research goal:
{json.dumps(goal, ensure_ascii=False, indent=2)}

Idea:
{json.dumps(idea, ensure_ascii=False, indent=2)}

Original external-data request:
{request}

Connector coverage feedback:
{connector_feedback}

Relevant API and source context:
{json.dumps(registry, ensure_ascii=False, indent=2)}

The Connector has already authorized this startup. Continue research freely without applying
additional Connector-specific search restrictions: search, browse, call APIs, use available
local authentication, and download complementary artifacts as appropriate. Save every retained
artifact locally under {workspace}. Read {MANIFEST_FILENAME} if it exists and append Web Evidence
entries to its `artifacts` list; do not discard existing Connector entries. Each retained web
artifact needs artifact_path, source, api_id set to `non_api`, request, and retrieved_at
(ISO-8601); include docs_url whenever an official documentation page applies. Never claim an
artifact that is not a real file in this workspace. Finish with concise natural-language coverage
feedback. Do not lower or assess the scientific score of the Idea."""

    @staticmethod
    def _write_acquisition_record(
        workspace: Path,
        *,
        request: str,
        connector_feedback: str,
        coverage_feedback: str,
        status: str,
        error: str | None = None,
    ) -> None:
        record = {
            "acquired_by": "web_evidence",
            "request": request,
            "connector_coverage_feedback": connector_feedback,
            "coverage_feedback": coverage_feedback,
            "status": status,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }
        if error:
            record["error"] = error
        (workspace / WEB_EVIDENCE_ACQUISITION_FILENAME).write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
