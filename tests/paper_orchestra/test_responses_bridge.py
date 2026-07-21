from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from vegapunk.mas.models.runtime import ImageContent, ModelRunResult, OutputText, TextContent
from vegapunk.paper_orchestra.responses_runtime import PaperOrchestraResponsesRuntime


class _Catalog:
    active_text_model = "qwen/qwen3.7-max"
    capability_models = {"vision": "qwen/qwen3.6-plus"}

    def resolve_model(self, model_id, capability=None):
        del capability
        if "/" not in model_id:
            raise ValueError("canonical provider/model identity required")
        return SimpleNamespace(canonical_id=model_id)

    def binding_for(self, capability):
        return SimpleNamespace(canonical_id=self.capability_models[capability])


class _Runtime:
    catalog = _Catalog()

    def __init__(self):
        self.requests = []

    async def run(self, request, *, model_id, capability):
        self.requests.append((request, model_id, capability))
        return ModelRunResult(
            response_id="response-1",
            status="completed",
            model=model_id.split("/", 1)[1],
            items=(OutputText("model output"),),
        )

    async def generate_image(self, prompt, *, aspect_ratio, model_id):
        self.requests.append((prompt, model_id, aspect_ratio))
        return b"generated image"


class PaperOrchestraResponsesRuntimeTest(unittest.TestCase):
    def test_maps_canonical_text_and_vision_requests(self) -> None:
        runtime = _Runtime()
        bridge = PaperOrchestraResponsesRuntime(runtime=runtime)

        text = bridge.generate_text(
            model_name="qwen/qwen3.7-max",
            content=(TextContent("find papers"),),
            system_prompt="write JSON",
        )
        vision = bridge.generate_text(
            model_name="qwen/qwen3.7-max",
            content=(TextContent("inspect"), ImageContent("data:image/png;base64,AA==")),
        )

        self.assertEqual(text, "model output")
        self.assertEqual(vision, "model output")
        self.assertEqual(runtime.requests[0][1:], ("qwen/qwen3.7-max", "text"))
        self.assertEqual(runtime.requests[1][1:], ("qwen/qwen3.6-plus", "vision"))

    def test_aliases_and_implicit_provider_names_are_rejected(self) -> None:
        bridge = PaperOrchestraResponsesRuntime(runtime=_Runtime())
        with self.assertRaises(ValueError):
            bridge.resolve_model("gemini-3-flash-preview")

    def test_image_generation_stays_on_the_runtime_image_binding(self) -> None:
        runtime = _Runtime()
        bridge = PaperOrchestraResponsesRuntime(runtime=runtime)
        self.assertEqual(
            bridge.generate_image(
                model_name="qwen/qwen-image-2.0-pro",
                prompt="draw a method diagram",
                aspect_ratio="16:9",
            ),
            b"generated image",
        )
        self.assertEqual(runtime.requests[0][1:], ("qwen/qwen-image-2.0-pro", "16:9"))


if __name__ == "__main__":
    unittest.main()
