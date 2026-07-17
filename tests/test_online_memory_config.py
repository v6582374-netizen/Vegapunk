from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace
from typing import Any

from internagent.mas.memory.online_memory import OnlineMemorySaver


class _Embedding:
    model_type = "local"
    model_name = "BAAI/bge-base-en-v1.5"
    dimension = 8

    def encode(self, texts, **kwargs):
        del kwargs
        return [[0.0] * self.dimension for _ in texts]


class _Runtime:
    def embedding_model(self):
        return _Embedding()

    def model_for(self, *, capability):
        return SimpleNamespace(model_id="qwen/qwen3.7-max", capability=capability)


class OnlineMemoryConfigTest(unittest.TestCase):
    def _config(self, memory_directory: str) -> dict[str, Any]:
        return {
            "_runtime": _Runtime(),
            "agents": {"exp_analyze": {"reasoning": {"context": "current_turn"}}},
            "memory": {
                "online_memory": {"enabled": True},
                "task_memory": {
                    "memory_dir": memory_directory,
                },
            },
        }

    def _create_saver(self, config: dict[str, Any]) -> OnlineMemorySaver:
        return OnlineMemorySaver(config, "config-test")

    def test_exp_analyze_uses_the_injected_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            saver = self._create_saver(self._config(directory))
        self.assertEqual(saver.memory.analyze_agent.model.model_id, "qwen/qwen3.7-max")

    def test_embedding_binding_is_owned_by_the_same_runtime_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            saver = self._create_saver(self._config(directory))
        self.assertEqual(saver.memory.embedding_model.model_name, "BAAI/bge-base-en-v1.5")


if __name__ == "__main__":
    unittest.main()
