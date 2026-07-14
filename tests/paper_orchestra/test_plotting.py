from __future__ import annotations

import asyncio
import base64
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from internagent.paper_orchestra.config import ImageGenerationConfig
from internagent.paper_orchestra.image_generation import (
    OpenAIImageGenerationAdapter,
)
from internagent.paper_orchestra.methods.agents.plotting_agent import PlottingAgent
from internagent.mas.models.runtime import ModelRunRequest, ModelRunResult, OutputText
from tests.paper_orchestra.test_agents import RecordingModel


class _FakeImages:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def generate(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(b"diagram").decode())]
        )


class ImageGenerationAdapterTest(unittest.TestCase):
    def test_uses_the_dedicated_model_and_returns_image_bytes(self) -> None:
        images = _FakeImages()
        client = SimpleNamespace(images=images)
        config = ImageGenerationConfig(
            base_url="https://yunwu.ai/v1",
            model="gemini-3-pro-image-preview",
            api_key_env="PAPER_ORCHESTRA_IMAGE_API_KEY",
        )
        adapter = OpenAIImageGenerationAdapter(
            config=config, api_key="test-key", client=client
        )

        image = asyncio.run(
            adapter.generate(prompt="draw the established method", aspect_ratio="16:9")
        )

        self.assertEqual(image, b"diagram")
        self.assertEqual(images.calls[0]["model"], "gemini-3-pro-image-preview")
        self.assertEqual(images.calls[0]["prompt"], "draw the established method")


class _FakeImageGenerator:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    async def generate(self, *, prompt: str, aspect_ratio: str) -> bytes:
        self.calls.append({"prompt": prompt, "aspect_ratio": aspect_ratio})
        return b"generated-diagram"


class PlottingAgentTest(unittest.TestCase):
    def test_generates_statistical_plot_and_method_diagram(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            outline_path = root / "outline.json"
            outline_path.write_text(
                json.dumps(
                    {
                        "plotting_plan": [
                            {
                                "figure_id": "result_plot",
                                "title": "Measured result",
                                "plot_type": "plot",
                                "objective": "Show the recorded values 1 and 2",
                                "aspect_ratio": "16:9",
                            },
                            {
                                "figure_id": "method_diagram",
                                "title": "Method overview",
                                "plot_type": "diagram",
                                "objective": "Explain the established data flow",
                                "aspect_ratio": "4:3",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            materials_path = root / "paper_materials.md"
            materials_path.write_text(
                "Recorded values: 1, 2. Established flow: input -> model -> output.",
                encoding="utf-8",
            )
            model = RecordingModel(
                text_responses=[
                    "```python\nprint('plot')\n```",
                    "Measured values from the recorded experiment.",
                    "A left-to-right input, model, and output architecture.",
                    "Overview of the established method.",
                ]
            )
            image_generator = _FakeImageGenerator()

            def render_plot(code: str, output_path: Path) -> None:
                self.assertIn("print('plot')", code)
                output_path.write_bytes(b"generated-plot")

            info_path = asyncio.run(
                PlottingAgent(
                    model=model,
                    image_generator=image_generator,
                    max_critic_rounds=0,
                    plot_renderer=render_plot,
                ).run(
                    outline_path=outline_path,
                    materials_path=materials_path,
                    figures_dir=root / "figures",
                )
            )

            figures = json.loads(info_path.read_text(encoding="utf-8"))
            self.assertEqual({item["name"] for item in figures}, {
                "result_plot.png",
                "method_diagram.png",
            })
            self.assertEqual(len(image_generator.calls), 1)
            self.assertEqual(image_generator.calls[0]["aspect_ratio"], "4:3")
            self.assertEqual((root / "figures" / "result_plot.png").read_bytes(), b"generated-plot")
            self.assertEqual((root / "figures" / "method_diagram.png").read_bytes(), b"generated-diagram")

    def test_visual_critique_regenerates_a_corrected_figure(self) -> None:
        class CriticModel(RecordingModel):
            async def run(self, request: ModelRunRequest) -> ModelRunResult:
                self.run_calls.append(request)
                return ModelRunResult(
                    response_id="critique-1",
                    status="completed",
                    model="critic",
                    items=(
                        OutputText(
                            text=json.dumps(
                                {
                                    "critic_suggestions": "Clarify the labels.",
                                    "revised_description": "Corrected labeled diagram",
                                }
                            )
                        ),
                    ),
                )

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "outline.json").write_text(
                json.dumps(
                    {
                        "plotting_plan": [
                            {
                                "figure_id": "method",
                                "plot_type": "diagram",
                                "objective": "Explain the method",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (root / "materials.md").write_text("established method", encoding="utf-8")
            model = CriticModel(
                text_responses=["Initial diagram", "Corrected method caption"]
            )
            image_generator = _FakeImageGenerator()

            asyncio.run(
                PlottingAgent(
                    model=model,
                    image_generator=image_generator,
                    max_critic_rounds=1,
                ).run(
                    outline_path=root / "outline.json",
                    materials_path=root / "materials.md",
                    figures_dir=root / "figures",
                )
            )

            self.assertEqual(len(image_generator.calls), 2)
            self.assertEqual(
                image_generator.calls[-1]["prompt"], "Corrected labeled diagram"
            )
            self.assertEqual(len(model.run_calls), 1)


if __name__ == "__main__":
    unittest.main()
