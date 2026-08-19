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
from vegapunk.prompt_library import prompts


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
        if not isinstance(global_config, Mapping):
            global_config = {}
        experiment_config = global_config.get("experiment", {})
        if not isinstance(experiment_config, Mapping):
            experiment_config = {}
        backend = (
            experiment_config.get("backend") or global_config.get("exp_backend")
        )
        proxy_settings = global_config.get("proxy_settings")
        # The coding-agent backend is an independently installed tool. Its model
        # and credentials come from the user's own CLI configuration, so nothing
        # about Discovery's Provider identity is passed down here.
        if backend == "qwen_code":
            from vegapunk.experiments_utils_qwen_code import QwenCodeRunner

            return QwenCodeRunner(proxy_settings)
        if backend == "codex":
            from vegapunk.experiments_utils_codex import CodexRunner

            return CodexRunner(proxy_settings)
        raise ValueError(
            "Web Evidence requires Launch experiment.backend to be 'codex' or "
            "'qwen_code'"
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
        return prompts.render(
            "external_data.web_evidence",
            request=request,
            connector_feedback=connector_feedback,
            registry=json.dumps(registry, ensure_ascii=False, indent=2),
            idea=json.dumps(idea, ensure_ascii=False, indent=2),
            goal=json.dumps(goal, ensure_ascii=False, indent=2),
            workspace=str(workspace),
            manifest_filename=MANIFEST_FILENAME,
        )

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
