from __future__ import annotations

import unittest
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from vegapunk.mas.agents.dr_agents.models import get_model
from vegapunk.mas.models.runtime import Message, ModelRunRequest, ModelRunResult, OutputText


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
    def _run_in_dr_agents_path(
        self, script: str
    ) -> subprocess.CompletedProcess[str]:
        """Run ``script`` with the vendored dr_agents tree on ``sys.path``.

        The vendored tree owns top-level ``camel``, ``tools`` and ``utils``
        packages. Adding it to this interpreter's path would shadow the
        identically named packages other suites import, so anything needing it
        runs in its own interpreter.
        """
        repository_root = Path(__file__).parents[2]
        dr_agents_root = repository_root / "vegapunk" / "mas" / "agents" / "dr_agents"
        environment = os.environ.copy()
        inherited_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(dr_agents_root), inherited_path) if part
        )
        return subprocess.run(
            [sys.executable, "-c", script],
            cwd=repository_root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_tool_manager_uses_the_runtime_configured_integration_module(self):
        """Tool loading must not re-import integration under a second module name."""
        script = """
import importlib
from unittest.mock import patch

tools = importlib.import_module("tools")
integration = importlib.import_module("tools.tool_integration")
config = {
    "tools": {"enabled_tools": ["image_processor"]},
    "extraction_model": "qwen/qwen3.7-max",
    "runtime_model": {},
}
with patch.object(integration, "construct_agent_list", return_value=[]) as construct:
    tools.ToolManager(config=config)
assert construct.call_count == 1, (
    "ToolManager bypassed the runtime-configured tools.tool_integration module"
)
"""
        result = self._run_in_dr_agents_path(script)

        self.assertEqual(
            result.returncode,
            0,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_camel_config_imports_without_pydantic_instance_field_warnings(self):
        """The vendored CAMEL configs resolve only with dr_agents on the path.

        Injecting that directory into this process would shadow the sibling
        ``utils`` and ``tools`` packages other suites import, so the import runs
        in a subprocess exactly as the tool-manager test above does.
        """
        script = """
import importlib
import warnings

modules = (
    "camel.configs.cohere_config",
    "camel.configs.mistral_config",
    "camel.configs.reka_config",
    "camel.configs.samba_config",
)
with warnings.catch_warnings(record=True) as captured:
    warnings.simplefilter("always")
    for module_name in modules:
        importlib.reload(importlib.import_module(module_name))

deprecated = [
    str(warning.message)
    for warning in captured
    if "model_fields" in str(warning.message)
]
assert not deprecated, "pydantic instance-field access: " + "; ".join(deprecated)
"""
        result = self._run_in_dr_agents_path(script)

        self.assertEqual(
            result.returncode,
            0,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_get_model_requires_explicit_runtime_and_canonical_identity(self):
        runtime = _Runtime()
        model = get_model(
            "qwen/qwen3.7-max",
            runtime=runtime,
            agent_role="dr_synthesizer",
        )
        self.assertEqual(model.model_id, "qwen/qwen3.7-max")
        self.assertEqual(model.generate("Reply with OK."), "OK")

    def test_generate_ignores_repeated_runtime_construction_policy(self):
        """Legacy DR agents repeat their construction policy on every generation."""
        runtime = _Runtime()
        policy = {
            "runtime_config": {"runtime": runtime},
            "agent_role": "dr_synthesizer",
            "reasoning_context": "all_turns",
            "reasoning_mode": "standard",
            "extraction_model": "qwen/qwen3.7-max",
        }
        model = get_model("qwen/qwen3.7-max", **policy)

        self.assertEqual(model.generate("Reply with OK.", **policy), "OK")

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
