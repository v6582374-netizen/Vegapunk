from __future__ import annotations

import base64
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from internagent.mas.models.runtime import (
    ImageContent,
    ModelRunResult,
    OutputText,
    TextContent,
)
from internagent.paper_orchestra.responses_runtime import (
    PaperOrchestraResponsesRuntime,
)


class PaperOrchestraResponsesRuntimeTest(unittest.TestCase):
    def test_limits_parallel_requests_without_changing_upstream_workers(self) -> None:
        lock = threading.Lock()
        active = 0
        maximum_active = 0

        class FakeModel:
            def run(self, request):
                nonlocal active, maximum_active
                with lock:
                    active += 1
                    maximum_active = max(maximum_active, active)
                time.sleep(0.03)
                with lock:
                    active -= 1
                return ModelRunResult(
                    response_id="response-1",
                    status="completed",
                    model="writer-model",
                    items=(OutputText("model output"),),
                )

        runtime = PaperOrchestraResponsesRuntime(
            {
                "max_concurrent_model_requests": 2,
                "provider": {"base_url": "https://relay.example/v1"},
            },
            model_factory=lambda **kwargs: FakeModel(),
        )

        with ThreadPoolExecutor(max_workers=6) as executor:
            outputs = list(
                executor.map(
                    lambda _: runtime.generate_text(
                        model_name="writer-model",
                        content=(TextContent("write"),),
                    ),
                    range(6),
                )
            )

        self.assertEqual(outputs, ["model output"] * 6)
        self.assertEqual(maximum_active, 2)

    def test_maps_upstream_alias_to_responses_request(self) -> None:
        created: list[tuple[str, dict[str, object], str]] = []
        requests = []

        class FakeModel:
            def run(self, request):
                requests.append(request)
                return ModelRunResult(
                    response_id="response-1",
                    status="completed",
                    model="writer-model",
                    items=(OutputText("model output"),),
                )

        def model_factory(*, model_name, runtime_config, agent_role):
            created.append((model_name, runtime_config, agent_role))
            return FakeModel()

        runtime = PaperOrchestraResponsesRuntime(
            {
                "provider": {
                    "provider": "openai",
                    "api_mode": "responses",
                    "base_url": "https://relay.example/v1",
                },
                "models": {"image": "image-model"},
                "model_aliases": {"gemini-3-flash-preview": "writer-model"},
            },
            model_factory=model_factory,
        )

        text = runtime.generate_text(
            model_name="gemini-3-flash-preview",
            content=(
                TextContent("find papers"),
                ImageContent("data:image/png;base64,AA==", detail="original"),
            ),
            system_prompt="write JSON",
            temperature=0.2,
        )

        self.assertEqual(text, "model output")
        self.assertEqual(created[0][0], "writer-model")
        self.assertEqual(created[0][1]["base_url"], "https://relay.example/v1")
        self.assertIsNone(created[0][1]["temperature"])
        self.assertEqual(created[0][2], "paper_orchestra")
        self.assertEqual(requests[0].instructions, "write JSON")
        self.assertIsNone(requests[0].temperature)
        self.assertEqual(requests[0].input[0].content[0], TextContent("find papers"))
        self.assertEqual(
            requests[0].input[0].content[1],
            ImageContent("data:image/png;base64,AA==", detail="original"),
        )

    def test_image_generation_uses_the_same_provider(self) -> None:
        calls = []
        expected = b"generated image"

        class FakeImages:
            def generate(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(
                    data=[
                        SimpleNamespace(
                            b64_json=base64.b64encode(expected).decode("ascii"),
                            url=None,
                        )
                    ]
                )

        class FakeClient:
            images = FakeImages()

        client_arguments = []

        def image_client_factory(**kwargs):
            client_arguments.append(kwargs)
            return FakeClient()

        runtime = PaperOrchestraResponsesRuntime(
            {
                "provider": {
                    "provider": "openai",
                    "api_mode": "responses",
                    "api_key": "relay-key",
                    "base_url": "https://relay.example/v1",
                    "timeout": 90,
                },
                "models": {"image": "image-model"},
                "model_aliases": {
                    "gemini-3-pro-image-preview": "image-model"
                },
            },
            image_client_factory=image_client_factory,
        )

        generated = runtime.generate_image(
            model_name="gemini-3-pro-image-preview",
            prompt="draw a method diagram",
            aspect_ratio="16:9",
        )

        self.assertEqual(generated, expected)
        self.assertEqual(client_arguments[0]["base_url"], "https://relay.example/v1")
        self.assertEqual(client_arguments[0]["api_key"], "relay-key")
        self.assertEqual(calls[0]["model"], "image-model")
        self.assertEqual(calls[0]["prompt"], "draw a method diagram")
        self.assertEqual(calls[0]["size"], "1536x1024")


if __name__ == "__main__":
    unittest.main()
