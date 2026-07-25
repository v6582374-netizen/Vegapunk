from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from admin_console.app import REPOSITORY_ROOT
from admin_console.provider_connections import (
    ProviderConnectionNotReadyError,
    ProviderConnectionService,
)
from admin_console.runtime_configuration import CapabilityPreflight


class FakeSecretStore:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def get(self, provider: str) -> str | None:
        return self.values.get(provider)

    def set(self, provider: str, secret: str) -> None:
        self.values[provider] = secret

    def delete(self, provider: str) -> None:
        self.values.pop(provider, None)


class CapabilityPreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.live_catalog_path = self.root / "live-model-catalog.yaml"
        shutil.copy2(
            REPOSITORY_ROOT / "config" / "model_catalog.yaml",
            self.live_catalog_path,
        )
        self.snapshot_dir = self.root / "snapshot"
        self.snapshot_dir.mkdir()
        shutil.copy2(
            REPOSITORY_ROOT / "config" / "model_catalog.yaml",
            self.snapshot_dir / "model_catalog.yaml",
        )
        (self.snapshot_dir / "default_config.yaml").write_text(
            "workflow:\n  loop_rounds: 7\n"
            f"model_catalog_path: {self.snapshot_dir / 'model_catalog.yaml'}\n"
        )
        self.secrets = FakeSecretStore({"relay": "vault-relay-secret"})
        self.probe_calls: list[tuple[str, str, str]] = []

        def probe(provider: str, base_url: str, credential: str) -> str:
            self.probe_calls.append((provider, base_url, credential))
            return "valid"

        self.connections = ProviderConnectionService(
            self.live_catalog_path, self.secrets, probe=probe
        )
        self.preflight = CapabilityPreflight(self.connections)

    def test_prepares_secret_free_runtime_config_with_current_connection(self) -> None:
        live = yaml.safe_load(self.live_catalog_path.read_text())
        live["providers"]["relay"]["base_url"] = "https://current-relay.example/v1"
        self.live_catalog_path.write_text(yaml.safe_dump(live, sort_keys=False))
        runtime_dir = self.root / "runtime"

        prepared = self.preflight.prepare(self.snapshot_dir, runtime_dir)

        runtime_config = yaml.safe_load(prepared.config_path.read_text())
        runtime_catalog_path = Path(runtime_config["model_catalog_path"])
        runtime_catalog = yaml.safe_load(runtime_catalog_path.read_text())
        self.assertEqual(runtime_config["workflow"]["loop_rounds"], 7)
        self.assertEqual(runtime_catalog["active_text_model"], "relay/gpt-5.6-sol")
        self.assertEqual(
            runtime_catalog["providers"]["relay"]["base_url"],
            "https://current-relay.example/v1",
        )
        self.assertEqual(prepared.environment["OPENAI_API_KEY"], "vault-relay-secret")
        self.assertNotIn("vault-relay-secret", prepared.config_path.read_text())
        self.assertNotIn("vault-relay-secret", runtime_catalog_path.read_text())
        self.assertEqual(len(self.probe_calls), 1)

    def test_resume_keeps_snapshot_bindings_after_global_binding_change(self) -> None:
        live = yaml.safe_load(self.live_catalog_path.read_text())
        live["active_text_model"] = "qwen/qwen3.7-max"
        live["capability_models"]["image_generation"] = "qwen/qwen-image-2.0-pro"
        live["providers"]["relay"]["base_url"] = "https://new-relay.example/v1"
        self.live_catalog_path.write_text(yaml.safe_dump(live, sort_keys=False))

        prepared = self.preflight.prepare(self.snapshot_dir, self.root / "resume-runtime")

        runtime_config = yaml.safe_load(prepared.config_path.read_text())
        runtime_catalog = yaml.safe_load(
            Path(runtime_config["model_catalog_path"]).read_text()
        )
        self.assertEqual(runtime_catalog["active_text_model"], "relay/gpt-5.6-sol")
        self.assertEqual(
            runtime_catalog["capability_models"]["image_generation"],
            "relay/gpt-image-1",
        )
        self.assertEqual(
            runtime_catalog["providers"]["relay"]["base_url"],
            "https://new-relay.example/v1",
        )
        self.assertNotIn("DASHSCOPE_API_KEY", prepared.environment)

    def test_preflight_blocks_execution_when_current_connection_is_invalid(self) -> None:
        connections = ProviderConnectionService(
            self.live_catalog_path,
            self.secrets,
            probe=lambda _provider, _base_url, _credential: "authentication_failed",
        )

        with self.assertRaisesRegex(
            ProviderConnectionNotReadyError, "authentication_failed"
        ):
            CapabilityPreflight(connections).prepare(
                self.snapshot_dir, self.root / "invalid-runtime"
            )


if __name__ == "__main__":
    unittest.main()
