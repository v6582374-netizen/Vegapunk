from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from vegapunk.mas.agents.agent_factory import (
    AgentFactory,
    AgentInitializationError,
)


class _Runtime:
    def create_model_for_agent(self, _agent_type: str, _config: dict[str, object]) -> object:
        return object()


class _BrokenRuntime:
    def create_model_for_agent(self, agent_type: str, _config: dict[str, object]) -> object:
        raise RuntimeError(f"model unavailable for {agent_type}")


class AgentFactoryConfigurationTest(unittest.TestCase):
    def setUp(self) -> None:
        AgentFactory.clear_cache()

    def tearDown(self) -> None:
        AgentFactory.clear_cache()

    def test_default_null_method_development_config_creates_agent(self) -> None:
        config_path = Path(__file__).parents[2] / "config" / "default_config.yaml"
        with config_path.open(encoding="utf-8") as config_file:
            default_config = yaml.safe_load(config_file)

        self.assertIsNone(default_config["agents"]["method_development"])

        runtime = _Runtime()
        agents = AgentFactory.create_all_agents(
            {"agents": {"method_development": default_config["agents"]["method_development"]}},
            runtime,
        )

        self.assertIn("method_development", agents)
        self.assertEqual(agents["method_development"].detail_level, "high")
        self.assertIs(agents["method_development"].config["_runtime"], runtime)

    def test_agent_initialization_failure_is_reported_at_startup(self) -> None:
        with self.assertRaises(AgentInitializationError) as context:
            AgentFactory.create_all_agents(
                {"agents": {"method_development": None}},
                _BrokenRuntime(),
            )

        error = context.exception
        self.assertIn("method_development", error.failures)
        self.assertIn("model unavailable", str(error))


if __name__ == "__main__":
    unittest.main()
