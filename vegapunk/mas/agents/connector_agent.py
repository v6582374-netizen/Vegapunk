"""Connector agent for structured external-data acquisition in a private workspace."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping

from .base_agent import AgentExecutionError, BaseAgent
from ..workflow.external_data import CONNECTOR_ACQUISITION_FILENAME, MANIFEST_FILENAME
from vegapunk.prompt_library import prompts


class ConnectorAgent(BaseAgent):
    """Ask the Launch-selected coding-agent backend to acquire API data."""

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
        if not isinstance(global_config, Mapping):
            global_config = {}
        runtime = self.config.get("_runtime") or global_config.get("_runtime")
        if runtime is None:
            raise ValueError(
                "Connector requires the process-owned UnifiedModelRuntime"
            )

        catalog = getattr(runtime, "catalog", None)
        model = getattr(catalog, "active_text_model", None)
        if not isinstance(model, str) or not model.strip():
            raise ValueError(
                "UnifiedModelRuntime catalog must expose active_text_model"
            )
        model = model.strip()

        experiment_config = global_config.get("experiment", {})
        if not isinstance(experiment_config, Mapping):
            experiment_config = {}
        backend = (
            experiment_config.get("backend") or global_config.get("exp_backend")
        )
        proxy_settings = global_config.get("proxy_settings")
        if backend == "qwen_code":
            from vegapunk.experiments_utils_qwen_code import QwenCodeRunner

            return QwenCodeRunner(proxy_settings, model=model)
        if backend == "codex":
            from vegapunk.experiments_utils_codex import CodexRunner

            return CodexRunner(proxy_settings, model=model)
        raise ValueError(
            "Connector requires Launch experiment.backend to be 'codex' or "
            "'qwen_code'"
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
        registry_metadata = ConnectorAgent._skill_like_registry(registry)
        return prompts.render(
            "external_data.connector",
            request=request,
            registry=json.dumps(registry_metadata, ensure_ascii=False, indent=2),
            idea=json.dumps(idea, ensure_ascii=False, indent=2),
            goal=json.dumps(goal, ensure_ascii=False, indent=2),
            workspace=str(workspace),
            manifest_filename=MANIFEST_FILENAME,
        )

    @staticmethod
    def _skill_like_registry(registry: list[Mapping[str, Any]]) -> list[dict[str, str]]:
        """Project each API entry to a progressive-disclosure description and docs link.

        Endpoint names, request fields, and response mappings deliberately stay out of the
        Connector prompt. The model discovers those details from the official documentation.
        """

        projected: list[dict[str, str]] = []
        for item in registry:
            if not isinstance(item, Mapping):
                continue
            entry: dict[str, str] = {}
            for key in ("api_id", "source", "description", "official_docs_url"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    entry[key] = value.strip()
            if "description" not in entry:
                entry["description"] = "Use the official API documentation for this source."
            projected.append(entry)
        return projected

    @staticmethod
    def _parse_coverage_decision(output: str) -> tuple[str, bool]:
        """Read the Connector-owned Web Evidence startup decision from runner output."""
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
        """Accept bare, fenced, or prose-wrapped JSON emitted by the runner."""
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
