from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from internagent.mas.models.model_factory import ModelFactory
from internagent.mas.models.openai_model import (
    OpenAIModel,
    get_builtin_openai_config,
)


class ModelFactoryRuntimeTest(unittest.TestCase):
    def tearDown(self) -> None:
        ModelFactory.clear_cache()

    def test_agent_reasoning_overrides_the_single_openai_default(self) -> None:
        project_config = {
            "models": {
                "default_provider": "openai",
                "openai": {
                    "api_key": "test-key",
                    "model_name": "gpt-5.6-sol",
                    "api_mode": "responses",
                    "temperature": 0.7,
                    "max_output_tokens": 128000,
                    "reasoning": {
                        "effort": "xhigh",
                        "context": "auto",
                        "mode": "standard",
                    },
                    "store": True,
                    "prompt_cache": {"mode": "explicit", "ttl": "30m"},
                    "background": {
                        "poll_interval_seconds": 2,
                        "timeout_seconds": 3600,
                    },
                },
            }
        }
        agent_config = {
            "model_provider": "default",
            "reasoning": {"context": "current_turn"},
            "_global_config": project_config,
        }

        model = ModelFactory.create_model_for_agent(
            "exp_analyze", agent_config
        )

        self.assertIsInstance(model, OpenAIModel)
        self.assertEqual(model.model_name, "gpt-5.6-sol")
        self.assertEqual(model.api_mode, "responses")
        self.assertEqual(model.max_output_tokens, 128000)
        self.assertEqual(model.reasoning_effort, "xhigh")
        self.assertEqual(model.reasoning_context, "current_turn")
        self.assertEqual(model.reasoning_mode, "standard")
        self.assertEqual(model.store, True)
        self.assertEqual(model.prompt_cache_mode, "explicit")
        self.assertEqual(model.prompt_cache_ttl, "30m")
        self.assertEqual(model.background_poll_interval, 2)
        self.assertEqual(model.background_timeout, 3600)

    def test_builtin_openai_gateway_uses_declared_compatibility_modes(self) -> None:
        config_path = Path(__file__).parents[2] / "config" / "default_config.yaml"
        with config_path.open(encoding="utf-8") as file:
            config = yaml.safe_load(file)["models"]["openai"]

        model = OpenAIModel.from_config({**config, "api_key": "test-key"})

        self.assertEqual(model.base_url, "https://ai.cloudyz.top/v1")
        self.assertEqual(model.prompt_cache_mode, "implicit")
        self.assertEqual(model.prompt_cache_ttl, "30m")
        self.assertEqual(model.response_state_mode, "replay")
        self.assertEqual(model.response_state_max_entries, 128)

        fallback = get_builtin_openai_config()
        self.assertEqual(fallback["base_url"], config["base_url"])
        self.assertEqual(fallback["prompt_cache"], config["prompt_cache"])
        self.assertEqual(fallback["response_state"], config["response_state"])

    def test_models_with_different_runtime_policies_are_not_cache_collapsed(self) -> None:
        project_config = {
            "models": {
                "default_provider": "openai",
                "openai": {
                    "api_key": "test-key",
                    "model_name": "gpt-5.6-sol",
                    "api_mode": "responses",
                    "reasoning": {
                        "effort": "xhigh",
                        "context": "auto",
                        "mode": "standard",
                    },
                },
            }
        }

        inherited = ModelFactory.create_model_for_agent(
            "generation",
            {"model_provider": "default", "_global_config": project_config},
        )
        isolated = ModelFactory.create_model_for_agent(
            "exp_analyze",
            {
                "model_provider": "default",
                "reasoning": {"context": "current_turn"},
                "_global_config": project_config,
            },
        )

        self.assertIsNot(inherited, isolated)
        self.assertEqual(inherited.reasoning_context, "auto")
        self.assertEqual(isolated.reasoning_context, "current_turn")

    def test_response_state_modes_are_not_cache_collapsed(self) -> None:
        base_config = {
            "provider": "openai",
            "api_key": "test-key",
            "model_name": "gpt-5.6-sol",
            "api_mode": "responses",
        }

        server = ModelFactory.create_model(
            {**base_config, "response_state": {"mode": "server"}}
        )
        replay = ModelFactory.create_model(
            {**base_config, "response_state": {"mode": "replay"}}
        )

        self.assertIsNot(server, replay)
        self.assertEqual(server.response_state_mode, "server")
        self.assertEqual(replay.response_state_mode, "replay")

    def test_responses_only_role_can_select_openai_over_default_provider(self) -> None:
        project_config = {
            "models": {
                "default_provider": "openrouter",
                "openrouter": {
                    "api_key": "openrouter-key",
                    "model_name": "vendor/chat-model",
                    "api_mode": "chat_completions",
                },
                "openai": {
                    "api_key": "openai-key",
                    "model_name": "gpt-5.6-sol",
                    "api_mode": "responses",
                    "reasoning": {"effort": "xhigh"},
                    "store": True,
                },
            }
        }

        model = ModelFactory.create_model_for_agent(
            "paper_orchestra",
            {
                "model_provider": "openai",
                "_global_config": project_config,
            },
        )

        self.assertIsInstance(model, OpenAIModel)
        self.assertEqual(model.model_name, "gpt-5.6-sol")
        self.assertEqual(model.api_mode, "responses")

    def test_obsolete_openai_runtime_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_tokens->max_output_tokens"):
            ModelFactory.create_model(
                {
                    "provider": "openai",
                    "api_key": "test-key",
                    "model_name": "gpt-5.6-sol",
                    "max_tokens": 4096,
                }
            )

    def test_prompt_cache_key_is_stable_and_role_scoped(self) -> None:
        model = OpenAIModel(api_key="test-key")
        first = model.make_prompt_cache_key(
            agent_role="generation",
            stable_prefix="Stable developer instructions",
        )
        repeated = model.make_prompt_cache_key(
            agent_role="generation",
            stable_prefix="Stable developer instructions",
        )
        other_role = model.make_prompt_cache_key(
            agent_role="review",
            stable_prefix="Stable developer instructions",
        )

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, other_role)
        self.assertLessEqual(len(first), 64)


if __name__ == "__main__":
    unittest.main()
