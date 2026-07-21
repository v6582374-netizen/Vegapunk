from __future__ import annotations

import unittest

from vegapunk.mas.agents.exp_analyze_agent import ExpAnalyzeAgent


class _RecordingModel:
    def __init__(self) -> None:
        self.generate_calls: list[dict[str, object]] = []
        self.responses = iter(("higher", "custom_metric"))

    async def generate(self, **kwargs: object) -> str:
        self.generate_calls.append(kwargs)
        return next(self.responses)


class ExpAnalyzeOutputTokenTest(unittest.IsolatedAsyncioTestCase):
    async def test_short_metric_prompts_do_not_send_legacy_caps(self) -> None:
        model = _RecordingModel()
        agent = ExpAnalyzeAgent(
            model,  # type: ignore[arg-type]
            {
                "use_llm_for_metric_direction": True,
                "use_llm_for_primary_metric": True,
            },
        )

        await agent._get_metric_direction_from_llm("custom_metric")
        await agent._select_primary_metric_with_llm({"custom_metric": 1.0})

        self.assertEqual(len(model.generate_calls), 2)
        for call in model.generate_calls:
            self.assertNotIn("max_output_tokens", call)


if __name__ == "__main__":
    unittest.main()
