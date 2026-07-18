from __future__ import annotations

import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from admin_console.app import REPOSITORY_ROOT, create_app

FAKE_RUNNER = Path(__file__).parent / "fake_runner.py"
FAKE_RUNNER_COMMAND = [sys.executable, str(FAKE_RUNNER), "{task_dir}", "{launch_dir}"]


class ParameterRegistryTest(unittest.TestCase):
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
        shutil.copy2(REPOSITORY_ROOT / "config" / "default_config.yaml", self.config_path)
        self.client = TestClient(
            create_app(
                results_root=self.results_root,
                tasks_root=self.tasks_root,
                config_paths=[self.config_path],
                runner_command=FAKE_RUNNER_COMMAND,
                main_config_path=self.config_path,
            )
        )

    def test_every_parameter_appears_in_catalog_with_description(self) -> None:
        response = self.client.get("/api/parameters")
        self.assertEqual(response.status_code, 200)
        body = response.json()

        catalog_paths = {field["path"] for field in body["catalog"]}
        def leaf_paths(node, prefix=""):
            paths = set()
            if isinstance(node, dict) and node:
                for key, value in node.items():
                    paths |= leaf_paths(value, f"{prefix}{key}." if not isinstance(value, (dict,)) or value else f"{prefix}{key}.")
            return paths

        # Every leaf key of the real config file must be reachable through
        # some catalog entry (exact leaf or a structured-json ancestor).
        values = body["values"]
        flat_config = _flatten(yaml.safe_load(self.config_path.read_text()))
        for path in flat_config:
            covered = any(path == entry or path.startswith(entry + ".") for entry in catalog_paths)
            self.assertTrue(covered, f"config key {path} not covered by catalog")

        for field in body["catalog"]:
            self.assertTrue(field["description"], f"{field['path']} lacks a description")
        self.assertEqual(_dig(values, "workflow.loop_rounds"), 10)

    def test_invalid_value_is_rejected_with_reason(self) -> None:
        current = self.client.get("/api/parameters").json()["values"]
        current["memory"]["task_memory"]["top_k"] = "not-a-number"
        response = self.client.put("/api/parameters", json=current)
        self.assertEqual(response.status_code, 422)
        detail = str(response.json())
        self.assertIn("top_k", detail)
        # The file must be untouched after a rejected save.
        persisted = yaml.safe_load(self.config_path.read_text())
        self.assertEqual(persisted["memory"]["task_memory"]["top_k"], 5)

    def test_valid_edit_is_persisted_and_reaches_next_launch_snapshot(self) -> None:
        current = self.client.get("/api/parameters").json()["values"]
        current["workflow"]["loop_rounds"] = 3
        response = self.client.put("/api/parameters", json=current)
        self.assertEqual(response.status_code, 200)

        persisted = yaml.safe_load(self.config_path.read_text())
        self.assertEqual(persisted["workflow"]["loop_rounds"], 3)

        entry = self.client.post("/api/queue", json={"task": "AutoDemo"}).json()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            entries = self.client.get("/api/queue").json()["entries"]
            state = next(e for e in entries if e["queue_id"] == entry["queue_id"])
            if state["state"] == "completed":
                break
            time.sleep(0.05)
        snapshot = self.results_root / state["launch_id"] / "config_snapshot" / "default_config.yaml"
        self.assertEqual(yaml.safe_load(snapshot.read_text())["workflow"]["loop_rounds"], 3)

    def test_out_of_range_value_is_rejected(self) -> None:
        current = self.client.get("/api/parameters").json()["values"]
        current["memory"]["task_memory"]["alpha"] = 2.5
        response = self.client.put("/api/parameters", json=current)
        self.assertEqual(response.status_code, 422)


def _flatten(node: dict, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for key, value in node.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict) and value:
            paths |= _flatten(value, f"{path}.")
        else:
            paths.add(path)
    return paths


def _dig(values: dict, dotted: str):
    node = values
    for part in dotted.split("."):
        node = node[part]
    return node


if __name__ == "__main__":
    unittest.main()
