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


class ModelCatalogApiTest(unittest.TestCase):
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
        self.config_path.write_text("system: {}\nmodel_catalog_path: model_catalog.yaml\n")
        self.catalog_path = root / "model_catalog.yaml"
        shutil.copy2(REPOSITORY_ROOT / "config" / "model_catalog.yaml", self.catalog_path)
        self.client = TestClient(
            create_app(
                results_root=self.results_root,
                tasks_root=self.tasks_root,
                config_paths=[self.config_path, self.catalog_path],
                runner_command=FAKE_RUNNER_COMMAND,
                main_config_path=self.config_path,
                model_catalog_path=self.catalog_path,
            )
        )

    def test_get_returns_nested_catalog(self) -> None:
        response = self.client.get("/api/model-catalog")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["active_text_model"], "relay/gpt-5.6-sol")
        self.assertIn("relay", body["providers"])
        self.assertIn("relay/gpt-5.6-sol", body["models"])
        self.assertIn("text", body["models"]["relay/gpt-5.6-sol"]["capabilities"])

    def test_rejects_cross_provider_text_and_image_binding(self) -> None:
        catalog = self.client.get("/api/model-catalog").json()
        catalog["capability_models"]["image_generation"] = "qwen/qwen-image-2.0-pro"
        response = self.client.put("/api/model-catalog", json=catalog)
        self.assertEqual(response.status_code, 422)
        self.assertIn("provider", str(response.json()).lower())

    def test_rejects_unknown_model_identity(self) -> None:
        catalog = self.client.get("/api/model-catalog").json()
        catalog["active_text_model"] = "relay/does-not-exist"
        response = self.client.put("/api/model-catalog", json=catalog)
        self.assertEqual(response.status_code, 422)

    def test_valid_edit_persists_and_reaches_snapshot(self) -> None:
        catalog = self.client.get("/api/model-catalog").json()
        catalog["providers"]["relay"]["timeout"] = 777
        response = self.client.put("/api/model-catalog", json=catalog)
        self.assertEqual(response.status_code, 200)
        persisted = yaml.safe_load(self.catalog_path.read_text())
        self.assertEqual(persisted["providers"]["relay"]["timeout"], 777)

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
            self.results_root / state["launch_id"] / "config_snapshot" / "model_catalog.yaml"
        )
        self.assertEqual(yaml.safe_load(snapshot.read_text())["providers"]["relay"]["timeout"], 777)


if __name__ == "__main__":
    unittest.main()
