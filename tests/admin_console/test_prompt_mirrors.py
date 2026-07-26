from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

import yaml

from tests.admin_console.client import TestClient

from admin_console.app import create_app
from vegapunk.prompt_library import DEFAULT_LIBRARY_ROOT, PromptLibrary


FAKE_RUNNER = Path(__file__).with_name("fake_runner.py")
FAKE_RUNNER_COMMAND = [sys.executable, str(FAKE_RUNNER), "{task_dir}", "{launch_dir}"]


class PromptMirrorApiTest(unittest.TestCase):
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
        self.prompt_root = self.root / "prompts"
        shutil.copytree(DEFAULT_LIBRARY_ROOT, self.prompt_root)
        self.prompt_id = "experiment.coder_openhands"
        self.english_text = PromptLibrary(self.prompt_root).get(self.prompt_id)
        self.chinese_text = "你是一名严谨的 AI 科学家。"
        self.mirror_path = (
            self.root
            / "prompt_localizations"
            / "zh-CN"
            / "experiment"
            / "coder_openhands.yaml"
        )
        self.mirror_path.parent.mkdir(parents=True)
        self.mirror_path.write_text(
            yaml.safe_dump(
                {
                    "source_revision": hashlib.sha256(
                        self.english_text.encode()
                    ).hexdigest(),
                    "text": self.chinese_text,
                },
                allow_unicode=True,
                sort_keys=False,
            )
        )
        self.client = TestClient(
            create_app(
                results_root=self.results_root,
                tasks_root=self.tasks_root,
                config_paths=[self.config_path],
                prompt_library_root=self.prompt_root,
                runner_command=FAKE_RUNNER_COMMAND,
            )
        )

    def test_ready_chinese_mirror_is_exposed_without_affecting_runtime_english(self) -> None:
        response = self.client.get(f"/api/admin/prompts/{self.prompt_id}")

        self.assertEqual(response.status_code, 200)
        prompt = response.json()
        self.assertEqual(
            prompt["chinese_mirror"],
            {
                "state": "ready",
                "file": "prompt_localizations/zh-CN/experiment/coder_openhands.yaml",
                "text": self.chinese_text,
            },
        )
        runtime_library = PromptLibrary(self.prompt_root)
        self.assertEqual(runtime_library.get(self.prompt_id), self.english_text)
        self.assertNotIn(
            self.chinese_text,
            runtime_library.render(
                self.prompt_id,
                idea_description="idea",
                code_server_path="/tmp/code",
                max_runs=1,
                method="method",
            ),
        )

    def test_english_save_marks_the_mirror_stale_without_copying_it_to_launches(self) -> None:
        original_mirror = self.mirror_path.read_bytes()
        edited = self.english_text + "\nENGLISH_PROMPT_UPDATE_MARKER\n"

        response = self.client.put(
            f"/api/admin/prompts/{self.prompt_id}", json={"text": edited}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["chinese_mirror"],
            {
                "state": "stale",
                "file": "prompt_localizations/zh-CN/experiment/coder_openhands.yaml",
                "text": None,
            },
        )
        self.assertEqual(self.mirror_path.read_bytes(), original_mirror)
        self.assertEqual(
            next(
                item
                for item in self.client.get("/api/admin/prompts").json()["prompts"]
                if item["id"] == "discovery.generation.system"
            )["chinese_mirror"]["state"],
            "missing",
        )

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
        self.assertIn(
            "ENGLISH_PROMPT_UPDATE_MARKER",
            (snapshot / "prompts" / "experiment" / "coder_openhands.txt").read_text(),
        )
        self.assertFalse((snapshot / "prompt_localizations").exists())
        self.assertNotIn(
            self.chinese_text,
            "\n".join(path.read_text() for path in snapshot.rglob("*") if path.is_file()),
        )


if __name__ == "__main__":
    unittest.main()
