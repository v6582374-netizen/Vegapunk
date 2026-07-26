from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from admin_console.app import create_app
from admin_console.prompt_mirror_batch import (
    BatchAvailability,
    PromptTranslationRequest,
)
from tests.admin_console.client import TestClient
from vegapunk.prompt_library import DEFAULT_LIBRARY_ROOT, PromptLibrary


FAKE_RUNNER = Path(__file__).with_name("fake_runner.py")
FAKE_RUNNER_COMMAND = [sys.executable, str(FAKE_RUNNER), "{task_dir}", "{launch_dir}"]


class DeterministicTranslator:
    def __init__(self) -> None:
        self.calls: list[PromptTranslationRequest] = []
        self.error: Exception | None = None
        self.output = "You are a rigorous AI scientist with a {tone} tone."

    def availability(self) -> BatchAvailability:
        return BatchAvailability(True, None, "relay/test-text")

    def translate(self, request: PromptTranslationRequest) -> str:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.output


class PromptMirrorSynchronizationApiTest(unittest.TestCase):
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
        self.config_path.write_text("system: {}\n")
        self.instruction_path = self.root / "prompt_translation_instruction.yaml"
        self.instruction_path.write_text("instruction: Translate faithfully.\n")
        self.prompt_root = self.root / "prompts"
        shutil.copytree(DEFAULT_LIBRARY_ROOT, self.prompt_root)
        self.library = PromptLibrary(self.prompt_root)
        self.prompt_id = "discovery.generation.system"
        self.english_text = self.library.get(self.prompt_id)
        self.chinese_text = "你是一名严谨的 AI 科学家，语气应为 {tone}。"
        self.mirror_path = (
            self.root
            / "prompt_localizations"
            / "zh-CN"
            / "discovery"
            / "generation"
            / "system.yaml"
        )
        self.translator = DeterministicTranslator()
        self.client = TestClient(
            create_app(
                results_root=self.results_root,
                tasks_root=self.tasks_root,
                config_paths=[self.config_path],
                runner_command=FAKE_RUNNER_COMMAND,
                prompt_library_root=self.prompt_root,
                prompt_translation_instruction_path=self.instruction_path,
                prompt_mirror_translator=self.translator,
            )
        )

    def _revision(self) -> str:
        return self.client.get(f"/api/admin/prompts/{self.prompt_id}").json()[
            "source_revision"
        ]

    def _synchronize(self, source_revision: str | None = None):
        return self.client.post(
            f"/api/admin/prompts/{self.prompt_id}/synchronize",
            json={
                "chinese_text": self.chinese_text,
                "source_revision": source_revision or self._revision(),
            },
        )

    def test_synchronization_commits_both_bodies_and_launch_uses_only_english(self) -> None:
        response = self._synchronize()

        self.assertEqual(response.status_code, 200)
        prompt = response.json()
        self.assertEqual(prompt["text"], self.translator.output)
        self.assertEqual(prompt["chinese_mirror"]["state"], "ready")
        self.assertEqual(prompt["chinese_mirror"]["text"], self.chinese_text)
        self.assertEqual(
            self.translator.calls,
            [
                PromptTranslationRequest(
                    instruction="Translate faithfully.",
                    direction="chinese_to_english",
                    prompt_id=self.prompt_id,
                    template_variables=("tone",),
                    source_body=self.chinese_text,
                )
            ],
        )
        mirror_document = yaml.safe_load(self.mirror_path.read_text())
        self.assertEqual(mirror_document["text"], self.chinese_text)
        self.assertEqual(
            mirror_document["source_revision"],
            hashlib.sha256(self.translator.output.encode()).hexdigest(),
        )
        self.assertEqual(
            self.library.render(self.prompt_id, tone="careful"),
            "You are a rigorous AI scientist with a careful tone.",
        )

        queue_entry = self.client.post("/api/admin/queue", json={"task": "AutoDemo"}).json()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = next(
                item
                for item in self.client.get("/api/admin/queue").json()["entries"]
                if item["queue_id"] == queue_entry["queue_id"]
            )
            if state["state"] == "completed":
                break
            time.sleep(0.05)
        else:
            self.fail("launch never completed")

        snapshot = self.results_root / state["launch_id"] / "config_snapshot"
        snapshot_prompt = snapshot / "prompts" / "discovery" / "generation_system.txt"
        self.assertEqual(snapshot_prompt.read_text(), self.translator.output)
        self.assertFalse((snapshot / "prompt_localizations").exists())
        self.assertNotIn(
            self.chinese_text,
            "\n".join(path.read_text() for path in snapshot.rglob("*") if path.is_file()),
        )

    def test_stale_english_revision_returns_conflict_without_writing_either_body(self) -> None:
        revision = self._revision()
        changed_english = self.english_text + "\nENGLISH_CHANGE\n"
        self.assertEqual(
            self.client.put(
                f"/api/admin/prompts/{self.prompt_id}", json={"text": changed_english}
            ).status_code,
            200,
        )

        response = self._synchronize(revision)

        self.assertEqual(response.status_code, 409)
        self.assertIn("英文 Prompt", response.json()["detail"])
        self.assertEqual(self.library.get(self.prompt_id), changed_english)
        self.assertFalse(self.mirror_path.exists())
        self.assertEqual(self.translator.calls, [])

    def test_invalid_draft_and_model_failures_leave_persistent_bodies_unchanged(self) -> None:
        revision = self._revision()
        invalid = self.client.post(
            f"/api/admin/prompts/{self.prompt_id}/synchronize",
            json={"chinese_text": "没有必要变量的草稿", "source_revision": revision},
        )

        self.assertEqual(invalid.status_code, 422)
        self.assertFalse(self.mirror_path.exists())
        self.assertEqual(self.library.get(self.prompt_id), self.english_text)
        self.assertEqual(self.translator.calls, [])

        self.translator.error = RuntimeError("deterministic provider outage")
        failed = self._synchronize(revision)

        self.assertEqual(failed.status_code, 502)
        self.assertIn("provider outage", failed.json()["detail"])
        self.assertFalse(self.mirror_path.exists())
        self.assertEqual(self.library.get(self.prompt_id), self.english_text)

    def test_invalid_model_output_leaves_persistent_bodies_unchanged(self) -> None:
        self.translator.output = "The required variable was removed."

        response = self._synchronize()

        self.assertEqual(response.status_code, 422)
        self.assertIn("required template variable", response.json()["detail"])
        self.assertFalse(self.mirror_path.exists())
        self.assertEqual(self.library.get(self.prompt_id), self.english_text)

    def test_two_file_write_failure_restores_existing_english_and_mirror(self) -> None:
        original_chinese = "原始中文镜像 {tone}。"
        self.mirror_path.parent.mkdir(parents=True)
        self.mirror_path.write_text(
            yaml.safe_dump(
                {
                    "source_revision": hashlib.sha256(self.english_text.encode()).hexdigest(),
                    "text": original_chinese,
                },
                allow_unicode=True,
                sort_keys=False,
            )
        )
        original_english = (self.prompt_root / "discovery" / "generation_system.txt").read_bytes()
        original_mirror = self.mirror_path.read_bytes()
        original_replace = os.replace
        failed = False

        def fail_second_write(source: str | bytes | Path, destination: str | bytes | Path) -> None:
            nonlocal failed
            if Path(destination).resolve() == self.mirror_path.resolve() and not failed:
                failed = True
                raise OSError("deterministic mirror replacement failure")
            original_replace(source, destination)

        with patch("vegapunk.prompt_library.os.replace", side_effect=fail_second_write):
            with self.assertRaisesRegex(OSError, "deterministic mirror"):
                self.library.synchronize_chinese_mirror(
                    self.prompt_id,
                    self.chinese_text,
                    self.translator.output,
                    source_revision=hashlib.sha256(self.english_text.encode()).hexdigest(),
                )

        self.assertTrue(failed)
        self.assertEqual(
            (self.prompt_root / "discovery" / "generation_system.txt").read_bytes(),
            original_english,
        )
        self.assertEqual(self.mirror_path.read_bytes(), original_mirror)


if __name__ == "__main__":
    unittest.main()
