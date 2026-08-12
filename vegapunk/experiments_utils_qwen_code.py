"""Qwen Code Experiment Backend.

The Discovery workflow stays identical to the Codex runner contract: one private
workspace, iterative prompts, ALL_COMPLETED termination, experiment validation,
and a final report.  Only the coding-agent process adapter differs.
"""

from __future__ import annotations

import json
import logging
import os
import os.path as osp
import re
import subprocess
from datetime import datetime

from .experiments_utils_codex import (
    _split_codex_model_identity,
    extract_idea_info,
    perform_experiments as _perform_experiments,
)

logger = logging.getLogger(__name__)


_DASHSCOPE_COMPATIBLE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class QwenCodeAuthenticationError(RuntimeError):
    """Raised when Qwen Code reports an upstream authentication failure.

    Qwen Code currently emits some API failures as a JSON ``result`` event with
    ``subtype=success`` and exits with status 0.  Keeping a dedicated exception
    lets callers stop the experiment attempt instead of treating that text as a
    model response.
    """


class QwenCodeConfigurationError(RuntimeError):
    """Raised when the Launch Qwen credential is not configured."""


def _text_values(value):
    """Yield text leaves from a Qwen Code JSON event tree."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _text_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _text_values(child)


def _qwen_structured_error_values(payload):
    """Yield error-bearing fields without scanning ordinary model prose."""
    events = payload if isinstance(payload, list) else [payload]
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        subtype = event.get("subtype")
        if event_type == "error" or subtype in {
            "error",
            "error_during_execution",
            "success",
        }:
            for field in ("error", "result"):
                yield from _text_values(event.get(field))


def _qwen_authentication_error_text(stdout: str | None, stderr: str | None = None) -> str | None:
    """Return a bounded upstream authentication message, if one is present."""
    candidates: list[str] = []
    for raw in (stdout, stderr):
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            candidates.append(raw)
            continue
        candidates.extend(_qwen_structured_error_values(payload))

    for candidate in candidates:
        compact = " ".join(candidate.split())
        lowered = compact.lower()
        has_401 = bool(re.search(r"\b401\b", lowered))
        mentions_key = any(
            marker in lowered
            for marker in (
                "api key",
                "api-key",
                "apikey",
                "invalid_api_key",
                "authentication",
                "unauthorized",
            )
        )
        if (has_401 and mentions_key) or re.search(
            r"\b(?:invalid|incorrect|expired|missing)\s+(?:api[- ]?)?key\b",
            lowered,
        ):
            return compact[:500]
    return None


def _final_qwen_message(stdout: str) -> str:
    """Extract the terminal model message from Qwen Code JSON output."""
    auth_error = _qwen_authentication_error_text(stdout)
    if auth_error:
        raise QwenCodeAuthenticationError(
            "Qwen Code authentication failed: upstream rejected the configured "
            f"API key ({auth_error}). Check the Launch Qwen credential and "
            "DASHSCOPE_API_KEY precedence."
        )
    try:
        payload = json.loads(stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Qwen Code returned invalid JSON output") from exc

    events = payload if isinstance(payload, list) else [payload]
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        result = event.get("result")
        if event.get("subtype") == "success" and isinstance(result, str):
            return result.strip()
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            text_parts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ]
            text = "\n".join(part for part in text_parts if part).strip()
            if text:
                return text
    return ""


class QwenCodeRunner:
    """Run the official Qwen Code CLI in unattended workspace mode."""

    backend_label = "Qwen Code"

    def __init__(
        self,
        proxy_settings=None,
        model="qwen3.6-plus",
        *,
        command: str | None = None,
    ):
        self.proxy_settings = proxy_settings or {}
        # Vegapunk model identities are provider/model. Qwen Code receives the
        # provider-local model name; provider routing remains a separate concern.
        self.model, _provider = _split_codex_model_identity(model)
        self.command = command or os.environ.get("QWEN_CODE_BIN", "qwen")

    def run(self, prompt, cwd=None):
        workspace_root = osp.abspath(cwd or os.getcwd())
        env = os.environ.copy()
        env.update(self.proxy_settings)
        # Qwen Code uses the OpenAI-compatible protocol name for its generic
        # provider.  Bind that protocol to the Qwen provider's credential here
        # instead of inheriting a user-level OPENAI_API_KEY / selected auth mode.
        # This child-only alias never changes the parent process environment.
        dashscope_api_key = env.get("DASHSCOPE_API_KEY")
        if not dashscope_api_key:
            raise QwenCodeConfigurationError(
                "Qwen Code requires DASHSCOPE_API_KEY for the configured DashScope "
                "provider; it will not fall back to OPENAI_API_KEY."
            )
        env["OPENAI_API_KEY"] = dashscope_api_key
        env["OPENAI_BASE_URL"] = _DASHSCOPE_COMPATIBLE_BASE_URL
        command = [
            self.command,
            "--prompt",
            prompt,
            "--model",
            self.model,
            "--auth-type",
            "openai",
            "--openai-base-url",
            _DASHSCOPE_COMPATIBLE_BASE_URL,
            "--approval-mode",
            "yolo",
            "--output-format",
            "json",
            "--sandbox=false",
        ]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info("[%s] Running Qwen Code CLI in %s", timestamp, workspace_root)
        result = subprocess.run(
            command,
            cwd=workspace_root,
            capture_output=True,
            text=True,
            env=env,
        )
        logger.info(
            "Qwen Code command completed with return code: %s", result.returncode
        )
        if result.stdout:
            logger.info("Qwen Code stdout: %s", result.stdout[-30000:])
        if result.stderr:
            logger.warning("Qwen Code stderr: %s", result.stderr[-30000:])
        auth_error = _qwen_authentication_error_text(result.stdout, result.stderr)
        if auth_error:
            raise QwenCodeAuthenticationError(
                "Qwen Code authentication failed: upstream rejected the configured "
                f"API key ({auth_error}). Check the Launch Qwen credential and "
                "DASHSCOPE_API_KEY precedence."
            )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                command,
                output=result.stdout,
                stderr=result.stderr,
            )
        output = _final_qwen_message(result.stdout)
        if not output:
            raise RuntimeError(
                "Qwen Code succeeded but produced an empty final message"
            )
        return output


def perform_experiments(
    idea,
    folder_name,
    proxy_settings=None,
    model="qwen3.6-plus",
    gpu_ids=None,
    max_runs=None,
    log_file=None,
    task_type="auto",
    task_info=None,
    checklist=None,
    run_timeout=None,
    runtime=None,
    stop_after_baseline=False,
) -> bool:
    """Run the shared Discovery experiment loop through Qwen Code."""
    return _perform_experiments(
        idea,
        folder_name,
        proxy_settings=proxy_settings,
        model=model,
        gpu_ids=gpu_ids,
        max_runs=max_runs,
        log_file=log_file,
        task_type=task_type,
        task_info=task_info,
        checklist=checklist,
        run_timeout=run_timeout,
        runtime=runtime,
        runner_cls=QwenCodeRunner,
        stop_after_baseline=stop_after_baseline,
    )


__all__ = [
    "QwenCodeAuthenticationError",
    "QwenCodeConfigurationError",
    "QwenCodeRunner",
    "perform_experiments",
    "extract_idea_info",
]
