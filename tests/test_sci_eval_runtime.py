from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import internagent

from internagent.mas.models.runtime import ImageContent, ModelRunResult, OutputText
from internagent.sci_eval import RuntimeScoringAgent


class _Model:
    def __init__(self):
        self.requests = []

    def make_prompt_cache_key(self, *, agent_role, stable_prefix):
        return f"{agent_role}:{len(stable_prefix)}"

    async def run(self, request):
        self.requests.append(request)
        return ModelRunResult(
            response_id="resp_score",
            status="completed",
            model="qwen3.7-max",
            items=(OutputText('{"reasoning":"grounded","score":75}'),),
        )


class _Runtime:
    class _Catalog:
        active_text_model = "qwen/qwen3.7-max"

        def resolve_model(self, model_id, capability=None):
            del capability
            if "/" not in model_id:
                raise ValueError("canonical provider/model identity required")
            return SimpleNamespace(canonical_id=model_id, model=model_id.split("/", 1)[1])

        def binding_for(self, capability):
            if capability != "vision":
                raise ValueError(capability)
            return SimpleNamespace(canonical_id="qwen/qwen3.6-plus")

    def __init__(self):
        self.catalog = self._Catalog()
        self.models = {}

    def model_for(self, model_id, *, capability):
        self.models.setdefault((model_id, capability), _Model())
        return self.models[(model_id, capability)]


class RuntimeScoringAgentTest(unittest.TestCase):
    def test_uses_injected_runtime_for_json_and_original_images(self) -> None:
        runtime = _Runtime()
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "figure.png"
            image_path.write_bytes(b"not-a-real-png")
            scorer = RuntimeScoringAgent(runtime=runtime)
            result = scorer(
                "Score this report.",
                image_paths=[str(image_path)],
            )

        self.assertEqual(result, {"reasoning": "grounded", "score": 75})
        request = runtime.models[("qwen/qwen3.6-plus", "vision")].requests[0]
        self.assertEqual(request.response_format, "json_object")
        self.assertEqual(request.reasoning.context, "current_turn")
        images = [
            item
            for item in request.input[0].content
            if isinstance(item, ImageContent)
        ]
        self.assertEqual(images[0].detail, "original")

    def test_rejects_an_implicit_model_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "active_text_model"):
            RuntimeScoringAgent(runtime=_Runtime(), model_name="qwen3.7-max")

    def test_rcb_evaluation_is_a_cross_platform_package_bridge(self) -> None:
        package_path = Path(internagent.__file__).parent / "rcb_evaluation"
        self.assertTrue(package_path.is_dir())
        self.assertFalse(package_path.is_symlink())


if __name__ == "__main__":
    unittest.main()
