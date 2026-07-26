from __future__ import annotations

import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

import yaml

from tests.admin_console.client import TestClient

from admin_console.app import REPOSITORY_ROOT, create_app
from vegapunk.prompt_library import (
    DEFAULT_LIBRARY_ROOT,
    PromptLibrary,
    UnknownPromptError,
)


FAKE_RUNNER = Path(__file__).with_name("fake_runner.py")
FAKE_RUNNER_COMMAND = [sys.executable, str(FAKE_RUNNER), "{task_dir}", "{launch_dir}"]


class EmptySecretStore:
    def get(self, provider: str) -> str | None:
        return None

    def set(self, provider: str, secret: str) -> None:
        raise AssertionError("no credential write expected")

    def delete(self, provider: str) -> None:
        return None


class PromptTranslationInstructionApiTest(unittest.TestCase):
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
        self.instruction_path.write_text("instruction: \"\"\n")
        shutil.copytree(DEFAULT_LIBRARY_ROOT, self.prompt_root)
        self.client = self._client()

    def _client(self) -> TestClient:
        return TestClient(
            create_app(
                results_root=self.results_root,
                tasks_root=self.tasks_root,
                config_paths=[self.config_path, self.catalog_path],
                runner_command=FAKE_RUNNER_COMMAND,
                main_config_path=self.config_path,
                model_catalog_path=self.catalog_path,
                prompt_library_root=self.prompt_root,
                prompt_translation_instruction_path=self.instruction_path,
                secret_store=EmptySecretStore(),
            )
        )

    def test_read_save_and_restart_persist_the_independent_instruction(self) -> None:
        response = self.client.get("/api/admin/prompt-translation-instruction")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"instruction": "", "configured": False})

        instruction = "Translate the English source prompt into precise Chinese."
        saved = self.client.put(
            "/api/admin/prompt-translation-instruction",
            json={"instruction": instruction},
        )

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(
            saved.json(),
            {"instruction": instruction, "configured": True},
        )
        self.assertEqual(yaml.safe_load(self.instruction_path.read_text()), {"instruction": instruction})

        restarted = self._client().get("/api/admin/prompt-translation-instruction")
        self.assertEqual(restarted.status_code, 200)
        self.assertEqual(restarted.json(), saved.json())

    def test_whitespace_only_instruction_is_rejected_without_changing_source(self) -> None:
        original = self.instruction_path.read_bytes()

        response = self.client.put(
            "/api/admin/prompt-translation-instruction",
            json={"instruction": "  \n\t"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("must not be empty", response.json()["detail"])
        self.assertEqual(self.instruction_path.read_bytes(), original)

    def test_instruction_is_not_a_registered_prompt_or_launch_snapshot(self) -> None:
        instruction = "Translate faithfully."
        original_config = self.config_path.read_bytes()
        original_catalog = self.catalog_path.read_bytes()
        response = self.client.put(
            "/api/admin/prompt-translation-instruction",
            json={"instruction": instruction},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"instruction", "configured"})
        self.assertEqual(self.config_path.read_bytes(), original_config)
        self.assertEqual(self.catalog_path.read_bytes(), original_catalog)
        prompt_ids = {item["id"] for item in self.client.get("/api/admin/prompts").json()["prompts"]}
        self.assertNotIn("prompt_translation_instruction", prompt_ids)
        self.assertEqual(
            self.client.get("/api/admin/prompts/prompt_translation_instruction").status_code,
            404,
        )
        runtime_library = PromptLibrary(self.prompt_root)
        with self.assertRaises(UnknownPromptError):
            runtime_library.get("prompt_translation_instruction")
        with self.assertRaises(UnknownPromptError):
            runtime_library.render("prompt_translation_instruction")

        entry = self.client.post("/api/admin/queue", json={"task": "AutoDemo"}).json()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = next(
                item
                for item in self.client.get("/api/admin/queue").json()["entries"]
                if item["queue_id"] == entry["queue_id"]
            )
            if state["state"] == "completed":
                break
            time.sleep(0.05)
        else:
            self.fail("launch never completed")

        snapshot = self.results_root / state["launch_id"] / "config_snapshot"
        self.assertFalse((snapshot / self.instruction_path.name).exists())
        self.assertNotIn(instruction, "\n".join(path.read_text() for path in snapshot.rglob("*") if path.is_file()))


if __name__ == "__main__":
    unittest.main()
