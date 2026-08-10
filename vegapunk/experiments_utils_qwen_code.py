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
import subprocess
from datetime import datetime

from .experiments_utils_codex import (
    _split_codex_model_identity,
    extract_idea_info,
    perform_experiments as _perform_experiments,
)

logger = logging.getLogger(__name__)


def _final_qwen_message(stdout: str) -> str:
    """Extract the terminal model message from Qwen Code JSON output."""
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
        command = [
            self.command,
            "--prompt",
            prompt,
            "--model",
            self.model,
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


__all__ = ["QwenCodeRunner", "perform_experiments", "extract_idea_info"]
