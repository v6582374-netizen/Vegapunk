from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from internagent.mas.memory.online_memory import OnlineMemorySaver
from internagent.mas.models.model_factory import ModelFactory


class OnlineMemoryConfigTest(unittest.TestCase):
    def tearDown(self) -> None:
        ModelFactory.clear_cache()

    def _config(self, memory_directory: str) -> dict[str, Any]:
        return {
            "models": {
                "default_provider": "openai",
                "openai": {
                    "api_key": "test-key",
                    "base_url": "https://models.example.test/v1",
                    "model_name": "gpt-5.6-sol",
                    "api_mode": "responses",
                    "store": True,
                    "prompt_cache": {"mode": "implicit", "ttl": "30m"},
                    "response_state": {"mode": "replay", "max_entries": 64},
                },
            },
            "agents": {
                "exp_analyze": {
                    "model_provider": "default",
                    "reasoning": {"context": "current_turn"},
                    "timeout": 120,
                }
            },
            "memory": {
                "online_memory": {"enabled": True},
                "task_memory": {
                    "memory_dir": memory_directory,
                    "embedding": {"model_type": "local"},
                },
            },
        }

    def _create_saver(self, config: dict[str, Any]) -> OnlineMemorySaver:
        with patch(
            "internagent.mas.memory.task_memory.EmbeddingModel",
            return_value=SimpleNamespace(dimension=8),
        ):
            return OnlineMemorySaver(config, "config-test")

    def test_exp_analyze_inherits_the_global_model_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            saver = self._create_saver(self._config(directory))

        model = saver.memory.analyze_agent.model
        self.assertEqual(model.base_url, "https://models.example.test/v1")
        self.assertEqual(model.api_mode, "responses")
        self.assertIs(model.store, True)
        self.assertEqual(model.prompt_cache_mode, "implicit")
        self.assertEqual(model.prompt_cache_ttl, "30m")
        self.assertEqual(model.response_state_mode, "replay")
        self.assertEqual(model.response_state_max_entries, 64)

    def test_exp_analyze_preserves_agent_model_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self._config(directory)
            config["agents"]["exp_analyze"].update(
                {
                    "api_key": "agent-key",
                    "base_url": "https://agent.example.test/v1",
                    "model_name": "agent-analysis-model",
                    "default_headers": {"X-Agent": "exp-analyze"},
                }
            )
            saver = self._create_saver(config)

        model = saver.memory.analyze_agent.model
        self.assertEqual(model.api_key, "agent-key")
        self.assertEqual(model.base_url, "https://agent.example.test/v1")
        self.assertEqual(model.model_name, "agent-analysis-model")
        self.assertEqual(model.default_headers, {"X-Agent": "exp-analyze"})


if __name__ == "__main__":
    unittest.main()
