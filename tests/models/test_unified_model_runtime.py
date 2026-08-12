from __future__ import annotations

import asyncio
import base64
import logging
import os
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from vegapunk.mas.models.base_model import BaseModel, ServiceUnavailableError
from vegapunk.mas.models.runtime import (
    Message,
    ModelRunRequest,
    ModelRunResult,
    ModelUsage,
    OutputText,
)
from vegapunk.mas.models.unified_runtime import (
    ModelCatalog,
    UnifiedModelRuntime,
)


CATALOG = {
    "version": 1,
    "active_text_model": "qwen/qwen3.7-max",
    "capability_models": {
        "vision": "qwen/qwen3.6-plus",
        "image_generation": "qwen/qwen-image-2.0-pro",
        "embedding": "local/BAAI-bge-base-en-v1.5",
    },
    "providers": {
        "relay": {"protocol": "responses", "base_url": "https://relay.test/v1", "api_key_env": "OPENAI_API_KEY"},
        "qwen": {"protocol": "responses", "base_url": "https://qwen.test/v1", "api_key_env": "DASHSCOPE_API_KEY"},
        "local": {"protocol": "local_embedding"},
    },
    "models": {
        "relay/gpt-5.6-sol": {
            "provider": "relay",
            "model": "gpt-5.6-sol",
            "capabilities": ["text", "json", "tools", "vision", "reasoning"],
        },
        "qwen/qwen3.7-max": {
            "provider": "qwen",
            "model": "qwen3.7-max",
            "capabilities": ["text", "json", "tools", "reasoning", "continuation"],
        },
        "qwen/qwen3.6-plus": {
            "provider": "qwen",
            "model": "qwen3.6-plus",
            "capabilities": [
                "text",
                "json",
                "tools",
                "vision",
                "reasoning",
                "continuation",
            ],
        },
        "qwen/qwen-image-2.0-pro": {
            "provider": "qwen",
            "model": "qwen-image-2.0-pro",
            "protocol": "dashscope_multimodal",
            "capabilities": ["image_generation"],
        },
        "local/BAAI-bge-base-en-v1.5": {
            "provider": "local",
            "model": "BAAI/bge-base-en-v1.5",
            "protocol": "local_embedding",
            "capabilities": ["embedding"],
        },
    },
    "retry": {
        "max_attempts": 3,
        "max_elapsed_seconds": 10,
        "initial_backoff_seconds": 0,
        "max_backoff_seconds": 0,
    },
    "concurrency": {"relay": 2, "qwen": 2, "local": 2},
}


@dataclass
class FakeAdapter:
    provider: str
    model: str
    failures_before_success: int = 0
    active: int = 0
    maximum_active: int = 0
    calls: int = 0

    async def run(self, request: ModelRunRequest) -> ModelRunResult:
        self.calls += 1
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        try:
            await asyncio.sleep(0.01)
            if self.calls <= self.failures_before_success:
                raise ServiceUnavailableError("transient failure")
            return ModelRunResult(
                response_id=f"resp-{self.calls}",
                status="completed",
                model=self.model,
                items=(OutputText("ok"),),
            )
        finally:
            self.active -= 1


class TelemetryFakeAdapter(BaseModel):
    """Provider-shaped adapter that exercises the nested BaseModel seam."""

    def __init__(self, model: str) -> None:
        super().__init__()
        self.model = model

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "TelemetryFakeAdapter":
        return cls(str(config["model"]))

    async def _run(self, request: ModelRunRequest) -> ModelRunResult:
        del request
        return ModelRunResult(
            response_id="resp-telemetry",
            status="completed",
            model=self.model,
            items=(OutputText("ok"),),
            usage=ModelUsage(input_tokens=1, output_tokens=2, total_tokens=3),
        )


class UnifiedModelRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.created: list[FakeAdapter] = []

        def adapter_factory(model_def: Any, provider_config: Any) -> FakeAdapter:
            del provider_config
            adapter = FakeAdapter(
                provider=model_def.provider,
                model=model_def.model,
                failures_before_success=(
                    2 if model_def.canonical_id == "qwen/qwen3.7-max" else 0
                ),
            )
            self.created.append(adapter)
            return adapter

        self.runtime = UnifiedModelRuntime(
            ModelCatalog.from_mapping(CATALOG), adapter_factory=adapter_factory
        )

    async def test_resolves_canonical_bindings_and_runs_active_text_model(self) -> None:
        result = await self.runtime.run(
            ModelRunRequest(input=(Message.user("hello"),))
        )

        self.assertEqual(result.text, "ok")
        self.assertEqual(result.model, "qwen3.7-max")
        self.assertEqual(self.created[0].provider, "qwen")
        self.assertEqual(self.created[0].calls, 3)

    async def test_runtime_bound_model_logs_one_completion_per_provider_request(self) -> None:
        def adapter_factory(model_def: Any, provider_config: Any) -> TelemetryFakeAdapter:
            del provider_config
            return TelemetryFakeAdapter(model_def.model)

        runtime = UnifiedModelRuntime(
            ModelCatalog.from_mapping(CATALOG),
            adapter_factory=adapter_factory,
        )

        with self.assertLogs(
            "vegapunk.mas.models.base_model", level=logging.INFO
        ) as captured:
            result = await runtime.model_for().run(
                ModelRunRequest(input=(Message.user("hello"),))
            )

        model_run_lines = [
            line for line in captured.output if "model_run " in line
        ]
        self.assertEqual(result.response_id, "resp-telemetry")
        self.assertEqual(len(model_run_lines), 1)
        self.assertIn("response_id=resp-telemetry", model_run_lines[0])

    async def test_retries_do_not_change_provider_or_model(self) -> None:
        await self.runtime.run(
            ModelRunRequest(input=(Message.user("hello"),)),
            model_id="qwen/qwen3.7-max",
        )

        self.assertEqual(len(self.created), 1)
        self.assertEqual(self.created[0].provider, "qwen")
        self.assertEqual(self.created[0].model, "qwen3.7-max")

    async def test_provider_concurrency_is_centralized(self) -> None:
        await asyncio.gather(
            *(
                self.runtime.run(
                    ModelRunRequest(input=(Message.user(str(index)),)),
                    model_id="qwen/qwen3.6-plus",
                )
                for index in range(6)
            )
        )

        adapter = next(
            adapter
            for adapter in self.created
            if adapter.model == "qwen3.6-plus"
        )
        self.assertLessEqual(adapter.maximum_active, 2)

    async def test_capability_preflight_rejects_wrong_request_binding(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not declare capability 'vision'"):
            await self.runtime.run(
                ModelRunRequest(input=(Message.user("hello"),)),
                model_id="qwen/qwen3.7-max",
                capability="vision",
            )

    def test_catalog_rejects_implicit_provider_resolution(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "canonical provider/model identity"
        ):
            self.runtime.catalog.resolve_model("qwen3.7-max")

    def test_default_catalog_binds_relay_and_bounds_remote_requests(self) -> None:
        catalog_path = (
            Path(__file__).resolve().parents[2] / "config/model_catalog.yaml"
        )
        catalog = ModelCatalog.from_yaml(catalog_path)

        self.assertEqual(catalog.active_text_model, "relay/gpt-5.6-sol")
        self.assertEqual(
            catalog.capability_models["vision"], "relay/gpt-5.6-sol"
        )
        self.assertEqual(
            catalog.capability_models["image_generation"], "relay/gpt-image-2"
        )

        for provider in catalog.providers.values():
            if provider.protocol == "local_embedding":
                continue
            request_timeout = provider.settings["request_timeout"]
            self.assertEqual(request_timeout, 3600)
            self.assertLessEqual(request_timeout, catalog.retry.max_elapsed_seconds)
            self.assertNotIn("max_output_tokens", provider.settings)

    def test_default_catalog_disables_prompt_cache_options(self) -> None:
        catalog_path = (
            Path(__file__).resolve().parents[2] / "config/model_catalog.yaml"
        )
        catalog = ModelCatalog.from_yaml(catalog_path)

        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-key", "DASHSCOPE_API_KEY": "test-key"},
        ):
            relay = UnifiedModelRuntime._default_adapter_factory(
                catalog.resolve_model("relay/gpt-5.6-sol"),
                catalog.provider_for(catalog.resolve_model("relay/gpt-5.6-sol")),
            )
            qwen = UnifiedModelRuntime._default_adapter_factory(
                catalog.resolve_model("qwen/qwen3-max"),
                catalog.provider_for(catalog.resolve_model("qwen/qwen3-max")),
            )

        self.assertFalse(relay.prompt_cache_supports_options)
        self.assertFalse(qwen.prompt_cache_supports_options)

    async def test_openai_image_adapter_uses_gpt_image_2_images_endpoint(self) -> None:
        catalog_path = (
            Path(__file__).resolve().parents[2] / "config/model_catalog.yaml"
        )
        catalog = ModelCatalog.from_yaml(catalog_path)
        model = catalog.resolve_model(
            "relay/gpt-image-2", capability="image_generation"
        )
        provider = catalog.provider_for(model)
        requests: list[dict[str, object]] = []

        def generate(**request: object) -> SimpleNamespace:
            requests.append(request)
            encoded = base64.b64encode(b"fake-png").decode("ascii")
            return SimpleNamespace(
                data=[SimpleNamespace(b64_json=encoded)]
            )

        fake_client = SimpleNamespace(
            images=SimpleNamespace(generate=generate)
        )
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch(
            "openai.OpenAI", return_value=fake_client
        ):
            adapter = UnifiedModelRuntime._default_adapter_factory(model, provider)
            image = await adapter.generate_image(
                prompt="draw a method diagram", aspect_ratio="16:9"
            )

        self.assertEqual(image, b"fake-png")
        self.assertEqual(
            requests,
            [
                {
                    "model": "gpt-image-2",
                    "prompt": "draw a method diagram",
                    "size": "1536x1024",
                }
            ],
        )

    def test_default_adapter_ignores_provider_ui_metadata(self) -> None:
        """Provider settings may contain Desktop-only metadata, not adapter kwargs."""

        catalog = ModelCatalog.from_mapping(
            {
                **CATALOG,
                "providers": {
                    **CATALOG["providers"],
                    "qwen": {
                        **CATALOG["providers"]["qwen"],
                        "user_configurable_fields": ["base_url"],
                    },
                },
            }
        )
        model = catalog.resolve_model("qwen/qwen3.7-max")

        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key"}):
            adapter = UnifiedModelRuntime._default_adapter_factory(
                model, catalog.provider_for(model)
            )

        self.assertEqual(adapter.provider_name, "qwen")
        self.assertEqual(adapter.model_name, "qwen3.7-max")


if __name__ == "__main__":
    unittest.main()
