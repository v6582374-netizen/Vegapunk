from __future__ import annotations

import unittest
from types import SimpleNamespace

from internagent.mas.agents.dr_agents.models import get_model
from internagent.mas.models.runtime import Message, ModelRunRequest, ModelRunResult, OutputText


class _Catalog:
    active_text_model = "qwen/qwen3.7-max"

    def resolve_model(self, model_id, capability=None):
        del capability
        if "/" not in model_id:
            raise ValueError("canonical provider/model identity required")
        return SimpleNamespace(canonical_id=model_id, model=model_id.split("/", 1)[1])


class _RuntimeModel:
    model_name = "qwen3.7-max"
    supports_prompt_cache = False

    def make_prompt_cache_key(self, **kwargs):
        return "cache"

    async def run(self, request):
        return ModelRunResult("resp", "completed", self.model_name, (OutputText("OK"),))


class _Runtime:
    def __init__(self):
        self.catalog = _Catalog()
        self.model = _RuntimeModel()

    def model_for(self, model_id, *, capability):
        if capability != "text":
            raise ValueError(capability)
        if model_id != self.catalog.active_text_model:
            raise ValueError(model_id)
        return self.model

    async def run(self, request, *, model_id, capability):
        return await self.model.run(request)


class DeepResearchRuntimeTest(unittest.TestCase):
    def test_get_model_requires_explicit_runtime_and_canonical_identity(self):
        runtime = _Runtime()
        model = get_model(
            "qwen/qwen3.7-max",
            runtime=runtime,
            agent_role="dr_synthesizer",
        )
        self.assertEqual(model.model_id, "qwen/qwen3.7-max")
        self.assertEqual(model.generate("Reply with OK."), "OK")

    def test_model_name_prefixes_are_not_provider_dispatch(self):
        with self.assertRaisesRegex(ValueError, "injected UnifiedModelRuntime"):
            get_model("gemini-3-flash-preview")

    def test_tool_loop_request_is_forwarded_through_runtime_facade(self):
        runtime = _Runtime()
        model = get_model("qwen/qwen3.7-max", runtime=runtime)
        result = model.run(ModelRunRequest(input=(Message.user("hello"),)))
        self.assertEqual(result.text, "OK")


if __name__ == "__main__":
    unittest.main()
