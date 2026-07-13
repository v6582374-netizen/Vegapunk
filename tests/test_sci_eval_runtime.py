from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from internagent.mas.models.runtime import (
    ImageContent,
    ModelRunResult,
    OutputText,
)
from internagent.sci_eval import RuntimeScoringAgent


class _RecordingRuntimeModel:
    instances: list["_RecordingRuntimeModel"] = []

    def __init__(self, **kwargs: object) -> None:
        self.config = kwargs
        self.requests = []
        self.__class__.instances.append(self)

    def make_prompt_cache_key(
        self, *, agent_role: str, stable_prefix: str
    ) -> str:
        return f"test:{agent_role}:{len(stable_prefix)}"

    async def run(self, request):
        self.requests.append(request)
        return ModelRunResult(
            response_id="resp_score",
            status="completed",
            model="gpt-5.6-sol",
            items=(OutputText(text='{"reasoning":"grounded","score":75}'),),
        )


class RuntimeScoringAgentTest(unittest.TestCase):
    def setUp(self) -> None:
        _RecordingRuntimeModel.instances.clear()

    def test_uses_responses_runtime_for_json_and_original_images(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "figure.png"
            image_path.write_bytes(b"not-a-real-png")
            scorer = RuntimeScoringAgent(
                api_key="test",
                base_url="",
                model_name="gpt-5.6-sol",
            )
            with patch(
                "internagent.sci_eval.OpenAIModel", _RecordingRuntimeModel
            ):
                result = scorer(
                    "Score this report.",
                    image_paths=[str(image_path)],
                    return_example={"reasoning": "str", "score": 0},
                )

        self.assertEqual(result, {"reasoning": "grounded", "score": 75})
        request = _RecordingRuntimeModel.instances[0].requests[0]
        self.assertEqual(request.response_format, "json_object")
        self.assertEqual(request.reasoning.context, "current_turn")
        self.assertEqual(request.reasoning.mode, "pro")
        images = [
            item
            for item in request.input[0].content
            if isinstance(item, ImageContent)
        ]
        self.assertEqual(images[0].detail, "original")

    def test_rejects_an_old_scorer_model(self) -> None:
        with self.assertRaisesRegex(ValueError, "gpt-5.6-sol"):
            RuntimeScoringAgent(
                api_key="test",
                base_url="",
                model_name="gpt-5.5",
            )


if __name__ == "__main__":
    unittest.main()
