from __future__ import annotations

import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from tests.admin_console.client import TestClient

from admin_console.app import REPOSITORY_ROOT, create_app
from admin_console.default_configuration import save_default_configuration
from admin_console.provider_connections import ProviderConnectionService
from admin_console.queue import LaunchQueue


class EmptySecretStore:
    def get(self, provider: str) -> str | None:
        return None

    def set(self, provider: str, secret: str) -> None:
        raise AssertionError("no credential write expected")

    def delete(self, provider: str) -> None:
        return None


class ToggleSecretStore(EmptySecretStore):
    def __init__(self) -> None:
        self.available = True

    def get(self, provider: str) -> str | None:
        if not self.available:
            raise RuntimeError(f"vault unavailable for {provider}")
        return None


class DefaultConfigurationApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.config_path = self.root / "default_config.yaml"
        self.catalog_path = self.root / "model_catalog.yaml"
        shutil.copy2(REPOSITORY_ROOT / "config" / "default_config.yaml", self.config_path)
        shutil.copy2(REPOSITORY_ROOT / "config" / "model_catalog.yaml", self.catalog_path)
        self.client = TestClient(
            create_app(
                results_root=self.root / "results",
                tasks_root=self.root / "tasks",
                main_config_path=self.config_path,
                model_catalog_path=self.catalog_path,
                secret_store=EmptySecretStore(),
            )
        )

    def test_get_exposes_bindings_and_registered_parameters_only(self) -> None:
        response = self.client.get("/api/admin/default-configuration")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["bindings"]["active_text_model"], "relay/gpt-5.6-sol")
        self.assertEqual(body["bindings"]["image_model"], "relay/gpt-image-1")
        self.assertEqual(
            body["bindings"]["embedding_model"], "local/BAAI-bge-base-en-v1.5"
        )
        paths = {field["path"] for field in body["parameter_catalog"]}
        self.assertIn("workflow.loop_rounds", paths)
        self.assertNotIn("model_catalog_path", paths)
        self.assertNotIn("memory.task_memory.memory_dir", paths)
        self.assertNotIn("tools.literature_search.api_keys", paths)
        self.assertNotIn("model_catalog_path", str(body["parameters"]))

    def test_save_commits_bindings_and_parameters_as_one_revision(self) -> None:
        current = self.client.get("/api/admin/default-configuration").json()
        payload = {
            "bindings": {
                "active_text_model": "qwen/qwen3.7-max",
                "image_model": "qwen/qwen-image-2.0-pro",
                "embedding_model": "local/BAAI-bge-base-en-v1.5",
            },
            "parameters": current["parameters"],
        }
        payload["parameters"]["workflow"]["loop_rounds"] = 3

        response = self.client.put("/api/admin/default-configuration", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotEqual(body["revision"], current["revision"])
        self.assertEqual(body["bindings"], payload["bindings"])
        self.assertEqual(body["parameters"]["workflow"]["loop_rounds"], 3)
        catalog = yaml.safe_load(self.catalog_path.read_text())
        parameters = yaml.safe_load(self.config_path.read_text())
        self.assertEqual(catalog["active_text_model"], "qwen/qwen3.7-max")
        self.assertEqual(
            catalog["capability_models"]["image_generation"],
            "qwen/qwen-image-2.0-pro",
        )
        self.assertEqual(parameters["workflow"]["loop_rounds"], 3)

    def test_invalid_revision_leaves_both_sources_unchanged(self) -> None:
        current = self.client.get("/api/admin/default-configuration").json()
        original_config = self.config_path.read_bytes()
        original_catalog = self.catalog_path.read_bytes()
        payload = {
            "bindings": {
                "active_text_model": "relay/gpt-5.6-sol",
                "image_model": "qwen/qwen-image-2.0-pro",
                "embedding_model": "local/BAAI-bge-base-en-v1.5",
            },
            "parameters": current["parameters"],
        }
        payload["parameters"]["workflow"]["loop_rounds"] = 0

        response = self.client.put("/api/admin/default-configuration", json=payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.config_path.read_bytes(), original_config)
        self.assertEqual(self.catalog_path.read_bytes(), original_catalog)

    def test_readiness_includes_every_provider_required_by_runtime_bindings(self) -> None:
        current = self.client.get("/api/admin/default-configuration").json()
        response = self.client.put(
            "/api/admin/default-configuration",
            json={
                "bindings": {
                    "active_text_model": "qwen/qwen3.7-max",
                    "image_model": "qwen/qwen-image-2.0-pro",
                    "embedding_model": "local/BAAI-bge-base-en-v1.5",
                },
                "parameters": current["parameters"],
            },
        )

        self.assertEqual(response.status_code, 200)
        providers = {
            connection["provider"]
            for connection in response.json()["readiness"]["connections"]
        }
        self.assertEqual(providers, {"qwen", "relay"})

    def test_launch_snapshot_cannot_observe_a_partially_saved_revision(self) -> None:
        current = self.client.get("/api/admin/default-configuration").json()
        parameters = current["parameters"]
        parameters["workflow"]["loop_rounds"] = 3
        bindings = {
            "active_text_model": "qwen/qwen3.7-max",
            "image_model": "qwen/qwen-image-2.0-pro",
            "embedding_model": "local/BAAI-bge-base-en-v1.5",
        }
        connections = ProviderConnectionService(self.catalog_path, EmptySecretStore())
        results_root = self.root / "snapshot-results"
        tasks_root = self.root / "snapshot-tasks"
        results_root.mkdir()
        tasks_root.mkdir()
        queue = LaunchQueue(
            results_root=results_root,
            tasks_root=tasks_root,
            config_paths=[self.config_path, self.catalog_path],
            runner_command=[],
        )
        launch_dir = results_root / "launch"
        launch_dir.mkdir()

        config_replaced = threading.Event()
        allow_save_to_finish = threading.Event()
        snapshot_finished = threading.Event()
        errors: list[BaseException] = []
        original_replace = os.replace

        def controlled_replace(source: str | Path, target: str | Path) -> None:
            original_replace(source, target)
            if Path(target) == self.config_path:
                config_replaced.set()
                if not allow_save_to_finish.wait(5):
                    raise TimeoutError("timed out waiting to finish configuration save")

        def save_revision() -> None:
            try:
                save_default_configuration(
                    self.config_path,
                    self.catalog_path,
                    connections,
                    bindings,
                    parameters,
                )
            except BaseException as error:
                errors.append(error)

        def capture_snapshot() -> None:
            try:
                queue._snapshot_configuration(launch_dir)
            except BaseException as error:
                errors.append(error)
            finally:
                snapshot_finished.set()

        with patch("admin_console.default_configuration.os.replace", side_effect=controlled_replace):
            save_thread = threading.Thread(target=save_revision)
            save_thread.start()
            self.assertTrue(config_replaced.wait(5))
            snapshot_thread = threading.Thread(target=capture_snapshot)
            snapshot_thread.start()
            snapshot_was_blocked = not snapshot_finished.wait(0.2)
            allow_save_to_finish.set()
            save_thread.join(5)
            snapshot_thread.join(5)

        self.assertTrue(snapshot_was_blocked)
        self.assertEqual(errors, [])
        snapshot = launch_dir / "config_snapshot"
        self.assertEqual(
            yaml.safe_load((snapshot / "default_config.yaml").read_text())["workflow"][
                "loop_rounds"
            ],
            3,
        )
        self.assertEqual(
            yaml.safe_load((snapshot / "model_catalog.yaml").read_text())[
                "active_text_model"
            ],
            "qwen/qwen3.7-max",
        )

    def test_vault_failure_before_commit_leaves_revision_unchanged(self) -> None:
        root = self.root / "vault-failure"
        root.mkdir()
        config_path = root / "default_config.yaml"
        catalog_path = root / "model_catalog.yaml"
        shutil.copy2(REPOSITORY_ROOT / "config" / "default_config.yaml", config_path)
        shutil.copy2(REPOSITORY_ROOT / "config" / "model_catalog.yaml", catalog_path)
        secret_store = ToggleSecretStore()
        client = TestClient(
            create_app(
                results_root=root / "results",
                tasks_root=root / "tasks",
                main_config_path=config_path,
                model_catalog_path=catalog_path,
                secret_store=secret_store,
            )
        )
        current = client.get("/api/admin/default-configuration").json()
        original_config = config_path.read_bytes()
        original_catalog = catalog_path.read_bytes()
        secret_store.available = False

        response = client.put(
            "/api/admin/default-configuration",
            json={
                "bindings": {
                    "active_text_model": "qwen/qwen3.7-max",
                    "image_model": "qwen/qwen-image-2.0-pro",
                    "embedding_model": "local/BAAI-bge-base-en-v1.5",
                },
                "parameters": current["parameters"],
            },
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(config_path.read_bytes(), original_config)
        self.assertEqual(catalog_path.read_bytes(), original_catalog)


if __name__ == "__main__":
    unittest.main()
