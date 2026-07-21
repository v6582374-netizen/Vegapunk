from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vegapunk.mas.models.base_model import ServiceUnavailableError
from vegapunk.mas.models.runtime import (
    Message,
    ModelRunRequest,
    ModelRunResult,
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
            catalog.capability_models["image_generation"], "relay/gpt-image-1"
        )

        for provider in catalog.providers.values():
            if provider.protocol == "local_embedding":
                continue
            request_timeout = provider.settings["request_timeout"]
            self.assertEqual(request_timeout, 300)
            self.assertLessEqual(request_timeout, catalog.retry.max_elapsed_seconds)
            self.assertNotIn("max_output_tokens", provider.settings)


if __name__ == "__main__":
    unittest.main()
