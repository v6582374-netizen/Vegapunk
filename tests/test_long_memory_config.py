from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LONG_MEMORY_PATH = (
    REPOSITORY_ROOT / "internagent" / "mas" / "memory" / "long_memory.py"
)


def _stub_module(name: str, **attributes: object) -> types.ModuleType:
    module = types.ModuleType(name)
    for attribute_name, value in attributes.items():
        setattr(module, attribute_name, value)
    return module


def _load_long_memory_module() -> types.ModuleType:
    """Load long_memory without requiring its optional vector-store dependencies."""
    networkx = _stub_module("networkx", Graph=object)
    chromadb = _stub_module("chromadb", PersistentClient=object)
    chromadb_config = _stub_module("chromadb.config", Settings=object)
    chromadb_utils = _stub_module(
        "chromadb.utils",
        embedding_functions=types.SimpleNamespace(OpenAIEmbeddingFunction=object),
    )
    agent_factory = _stub_module(
        "internagent.mas.agents.agent_factory", AgentFactory=object
    )
    model_factory = _stub_module(
        "internagent.mas.models.model_factory", ModelFactory=object
    )

    module_name = "_long_memory_config_test"
    spec = importlib.util.spec_from_file_location(module_name, LONG_MEMORY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {LONG_MEMORY_PATH}")
    module = importlib.util.module_from_spec(spec)

    stubs = {
        "networkx": networkx,
        "chromadb": chromadb,
        "chromadb.config": chromadb_config,
        "chromadb.utils": chromadb_utils,
        "internagent.mas.agents.agent_factory": agent_factory,
        "internagent.mas.models.model_factory": model_factory,
        module_name: module,
    }
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)

    return module


class ExperienceGeneratorConfigTest(unittest.TestCase):
    def test_loads_repository_default_config_when_path_is_omitted(self) -> None:
        long_memory = _load_long_memory_module()
        generator = object.__new__(long_memory.ExperienceGenerator)

        loaded_config = generator._load_config(None)

        default_config_path = REPOSITORY_ROOT / "config" / "default_config.yaml"
        with default_config_path.open(encoding="utf-8") as config_file:
            expected_config = yaml.safe_load(config_file)
        self.assertEqual(loaded_config, expected_config)


if __name__ == "__main__":
    unittest.main()
