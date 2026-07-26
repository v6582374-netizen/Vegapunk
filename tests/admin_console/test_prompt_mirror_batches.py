from __future__ import annotations

import threading
import time
import shutil
import sys
import tempfile
import unittest
from json import loads
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from admin_console.app import REPOSITORY_ROOT, create_app
from admin_console.prompt_mirror_batch import (
    BatchAvailability,
    DefaultPromptMirrorTranslator,
    PromptTranslationRequest,
)
from tests.admin_console.client import TestClient
from vegapunk.mas.models.unified_runtime import UnifiedModelRuntime
from vegapunk.prompt_library import DEFAULT_LIBRARY_ROOT, PromptLibrary


FAKE_RUNNER = Path(__file__).with_name("fake_runner.py")
FAKE_RUNNER_COMMAND = [sys.executable, str(FAKE_RUNNER), "{task_dir}", "{launch_dir}"]


class EmptySecretStore:
    def get(self, provider: str) -> str | None:
        return None

    def set(self, provider: str, secret: str) -> None:
        raise AssertionError("no credential write expected")

    def delete(self, provider: str) -> None:
        return None


class DeterministicTranslator:
    def __init__(self) -> None:
        self.calls: list[PromptTranslationRequest] = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.failing_ids: set[str] = set()
        self.invalid_ids: set[str] = set()

    def availability(self) -> BatchAvailability:
        return BatchAvailability(True, None, "relay/test-text")

    def translate(self, request: PromptTranslationRequest) -> str:
        self.calls.append(request)
        self.started.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("test translator was not released")
        if request.prompt_id in self.failing_ids:
            raise RuntimeError("deterministic model outage")
        if request.prompt_id in self.invalid_ids:
            return "不包含模板变量的无效译文"
        return request.source_body


class PromptMirrorBatchApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.results_root = self.root / "results"
        self.results_root.mkdir()
        self.tasks_root = self.root / "tasks"
        (self.tasks_root / "AutoDemo").mkdir(parents=True)
        (self.tasks_root / "AutoDemo" / "prompt.json").write_text("{}")
        self.config_path = self.root / "default_config.yaml"
        self.catalog_path = self.root / "model_catalog.yaml"
        self.instruction_path = self.root / "prompt_translation_instruction.yaml"
        self.prompt_root = self.root / "prompts"
        shutil.copy2(REPOSITORY_ROOT / "config" / "default_config.yaml", self.config_path)
        shutil.copy2(REPOSITORY_ROOT / "config" / "model_catalog.yaml", self.catalog_path)
        self.instruction_path.write_text("instruction: Translate faithfully.\n")
        shutil.copytree(DEFAULT_LIBRARY_ROOT, self.prompt_root)
        self.library = PromptLibrary(self.prompt_root)
        self.translator = DeterministicTranslator()
        self.client = TestClient(
            create_app(
                results_root=self.results_root,
                tasks_root=self.tasks_root,
                config_paths=[self.config_path, self.catalog_path],
                runner_command=FAKE_RUNNER_COMMAND,
                main_config_path=self.config_path,
                model_catalog_path=self.catalog_path,
                prompt_library_root=self.prompt_root,
                prompt_translation_instruction_path=self.instruction_path,
                prompt_mirror_translator=self.translator,
                secret_store=EmptySecretStore(),
            )
        )

    def _wait_for_completion(self, batch_id: str) -> dict:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            document = self.client.get(f"/api/admin/prompt-mirror-batches/{batch_id}").json()
            if document["state"] == "completed":
                return document
            time.sleep(0.02)
        self.fail("prompt mirror batch did not complete")

    def test_batch_translates_missing_mirrors_and_retries_only_failures(self) -> None:
        entries = self.library.list()
        failing_id = entries[0].id
        successful_id = entries[1].id
        successful_english = self.library.get(successful_id)
        self.translator.failing_ids.add(failing_id)

        started = self.client.post("/api/admin/prompt-mirror-batches")

        self.assertEqual(started.status_code, 201)
        batch = started.json()
        self.assertEqual(batch["state"], "running")
        self.assertTrue(all(item["state"] == "pending" for item in batch["items"]))
        self.assertTrue(self.translator.started.wait(timeout=2))
        self.assertEqual(len(self.translator.calls), 1)
        self.assertEqual(self.translator.calls[0].instruction, "Translate faithfully.")
        self.assertEqual(self.translator.calls[0].direction, "english_to_chinese")
        self.assertEqual(self.translator.calls[0].prompt_id, failing_id)
        self.assertEqual(
            self.translator.calls[0].source_body,
            self.library.get(failing_id),
        )
        self.assertEqual(
            self.translator.calls[0].template_variables,
            tuple(self.library.get_entry(failing_id).template_variables),
        )

        self.translator.release.set()
        completed = self._wait_for_completion(batch["id"])
        states = {item["prompt_id"]: item["state"] for item in completed["items"]}
        self.assertEqual(states[failing_id], "failure")
        self.assertTrue(all(state in {"success", "failure"} for state in states.values()))
        self.assertEqual(completed["progress"]["failure"], 1)
        self.assertEqual(completed["progress"]["success"], len(entries) - 1)
        self.assertEqual(self.library.describe(failing_id)["chinese_mirror"]["state"], "missing")
        self.assertEqual(self.library.describe(successful_id)["chinese_mirror"]["state"], "ready")
        successful_mirror = self.root / self.library.describe(successful_id)["chinese_mirror"]["file"]
        successful_bytes = successful_mirror.read_bytes()
        initial_call_count = len(self.translator.calls)

        self.translator.failing_ids.clear()
        retried = self.client.post(
            f"/api/admin/prompt-mirror-batches/{batch['id']}/retry"
        )

        self.assertEqual(retried.status_code, 201)
        retry_completed = self._wait_for_completion(retried.json()["id"])
        self.assertEqual(retry_completed["progress"], {"total": 1, "pending": 0, "success": 1, "failure": 0, "skipped": 0})
        self.assertEqual(
            [call.prompt_id for call in self.translator.calls[initial_call_count:]],
            [failing_id],
        )
        self.assertEqual(successful_mirror.read_bytes(), successful_bytes)
        self.assertEqual(self.library.describe(failing_id)["chinese_mirror"]["state"], "ready")
        self.assertEqual(self.library.get(successful_id), successful_english)

    def test_batch_rejects_model_output_that_breaks_the_template_contract(self) -> None:
        required_entry = next(
            entry for entry in self.library.list() if entry.required_template_variables
        )
        self.translator.invalid_ids.add(required_entry.id)
        self.translator.release.set()

        batch = self.client.post("/api/admin/prompt-mirror-batches").json()
        completed = self._wait_for_completion(batch["id"])
        required_item = next(
            item for item in completed["items"] if item["prompt_id"] == required_entry.id
        )

        self.assertEqual(required_item["state"], "failure")
        self.assertIn("required template variable", required_item["error"])
        self.assertEqual(
            self.library.describe(required_entry.id)["chinese_mirror"]["state"],
            "missing",
        )

    def test_reading_prompts_and_batch_availability_never_calls_the_model(self) -> None:
        self.client.get("/api/admin/prompts")
        availability = self.client.get("/api/admin/prompt-mirror-batches/availability")

        self.assertEqual(availability.status_code, 200)
        self.assertEqual(availability.json()["available"], True)
        self.assertEqual(self.translator.calls, [])

    def test_default_translator_uses_the_structured_active_text_model_envelope(self) -> None:
        class ProviderConnections:
            def resolve_for_execution(self, provider: str) -> SimpleNamespace:
                self.provider = provider
                return SimpleNamespace(
                    base_url="https://models.example.test/v1",
                    credential="test-credential",
                )

        connections = ProviderConnections()
        translator = DefaultPromptMirrorTranslator(self.catalog_path, connections)  # type: ignore[arg-type]
        request = PromptTranslationRequest(
            instruction="Translate faithfully.",
            direction="chinese_to_english",
            prompt_id="experiment.coder_openhands",
            template_variables=("idea_description",),
            source_body="中文源提示词 {idea_description}",
        )

        with patch.object(
            UnifiedModelRuntime,
            "generate_json",
            new_callable=AsyncMock,
            return_value={"target_body": "English translation {idea_description}"},
        ) as generate_json:
            translated = translator.translate(request)

        self.assertEqual(translated, "English translation {idea_description}")
        self.assertEqual(connections.provider, "relay")
        kwargs = generate_json.await_args.kwargs
        self.assertEqual(kwargs["system_prompt"], request.instruction)
        self.assertEqual(kwargs["model_id"], "relay/gpt-5.6-sol")
        self.assertEqual(
            loads(generate_json.await_args.args[0]),
            {
                "operation": "generate_prompt_mirror",
                "direction": "chinese_to_english",
                "prompt_id": request.prompt_id,
                "template_variables": ["idea_description"],
                "source_body": request.source_body,
            },
        )
        self.assertEqual(
            kwargs["schema"],
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["target_body"],
                "properties": {"target_body": {"type": "string"}},
            },
        )


if __name__ == "__main__":
    unittest.main()
