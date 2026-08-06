"""Qwen Code MCTS adapter using the shared Codex-compatible MCTS contract."""

from __future__ import annotations

from .experiments_utils_qwen_code import QwenCodeRunner
from .mcts_experiments_utils_codex import (
    perform_experiments_mcts as _perform_experiments_mcts,
)


def perform_experiments_mcts(
    idea,
    folder_name: str,
    proxy_settings=None,
    model="qwen3.6-plus",
    gpu_ids=None,
    log_file=None,
) -> bool:
    return _perform_experiments_mcts(
        idea,
        folder_name,
        proxy_settings=proxy_settings,
        model=model,
        runner_cls=QwenCodeRunner,
    )


__all__ = ["perform_experiments_mcts", "QwenCodeRunner"]
