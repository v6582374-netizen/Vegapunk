from __future__ import annotations

import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from admin_console.app import REPOSITORY_ROOT, create_app
from internagent.prompt_library import (
    DEFAULT_LIBRARY_ROOT,
    PromptLibrary,
    configure_prompt_root,
    prompts,
)

FAKE_RUNNER = Path(__file__).parent / "fake_runner.py"
FAKE_RUNNER_COMMAND = [sys.executable, str(FAKE_RUNNER), "{task_dir}", "{launch_dir}"]


class PromptLibraryUnitTest(unittest.TestCase):
    def test_experiment_prompt_matches_library_file(self) -> None:
        configure_prompt_root(DEFAULT_LIBRARY_ROOT)
        from internagent import prompts as legacy

        self.assertEqual(
            legacy.CODER_PROMPT_OPENHANDS,
            (DEFAULT_LIBRARY_ROOT / "experiment" / "coder_openhands.txt").read_text(),
        )

    def test_generation_system_prompt_reads_from_library(self) -> None:
        configure_prompt_root(DEFAULT_LIBRARY_ROOT)
        from internagent.mas.agents.generation_agent import GenerationAgent

        agent = GenerationAgent.__new__(GenerationAgent)
        text = GenerationAgent._build_system_prompt(agent, creativity=0.9)
        self.assertIn("highly innovative and out-of-the-box", text)
        self.assertEqual(
            text,
            prompts.render(
                "discovery.generation.system",
                tone="highly innovative and out-of-the-box",
            ),
        )


class PromptLibraryApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.results_root = root / "results"
        self.results_root.mkdir()
        self.tasks_root = root / "tasks"
        (self.tasks_root / "AutoDemo").mkdir(parents=True)
        (self.tasks_root / "AutoDemo" / "prompt.json").write_text("{}")
        self.config_path = root / "default_config.yaml"
        self.config_path.write_text("system: {}\n")
        self.prompt_root = root / "prompts"
        shutil.copytree(DEFAULT_LIBRARY_ROOT, self.prompt_root)
        self.client = TestClient(
            create_app(
                results_root=self.results_root,
                tasks_root=self.tasks_root,
                config_paths=[self.config_path],
                runner_command=FAKE_RUNNER_COMMAND,
                prompt_library_root=self.prompt_root,
            )
        )

    def test_list_prompts_grouped_metadata_and_text(self) -> None:
        response = self.client.get("/api/prompts")
        self.assertEqual(response.status_code, 200)
        items = response.json()["prompts"]
        self.assertGreaterEqual(len(items), 10)
        by_id = {item["id"]: item for item in items}
        self.assertIn("discovery.generation.system", by_id)
        self.assertEqual(by_id["discovery.generation.system"]["stage"], "discovery")
        self.assertTrue(by_id["discovery.generation.system"]["description"])
        self.assertIn("{tone}", by_id["discovery.generation.system"]["text"])

    def test_edit_is_persisted_and_snapshotted_into_next_launch(self) -> None:
        marker = "PROMPT_LIBRARY_TEST_MARKER_XYZ"
        original = self.client.get("/api/prompts/experiment.coder_openhands").json()["text"]
        edited = original + "\n" + marker + "\n"
        response = self.client.put(
            "/api/prompts/experiment.coder_openhands", json={"text": edited}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(marker, (self.prompt_root / "experiment" / "coder_openhands.txt").read_text())

        entry = self.client.post("/api/queue", json={"task": "AutoDemo"}).json()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = next(
                e
                for e in self.client.get("/api/queue").json()["entries"]
                if e["queue_id"] == entry["queue_id"]
            )
            if state["state"] == "completed":
                break
            time.sleep(0.05)
        else:
            self.fail("launch never completed")

        snapshot = (
            self.results_root
            / state["launch_id"]
            / "config_snapshot"
            / "prompts"
            / "experiment"
            / "coder_openhands.txt"
        )
        self.assertTrue(snapshot.is_file())
        self.assertIn(marker, snapshot.read_text())

        # Global edit after start would not affect an already-written snapshot.
        self.client.put(
            "/api/prompts/experiment.coder_openhands",
            json={"text": original + "\nAFTER_START\n"},
        )
        self.assertNotIn("AFTER_START", snapshot.read_text())


if __name__ == "__main__":
    unittest.main()
