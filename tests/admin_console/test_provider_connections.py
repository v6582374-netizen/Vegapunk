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
from admin_console.provider_connections import (
    ProviderConnectionNotReadyError,
    ProviderConnectionService,
)


class FakeSecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, provider: str) -> str | None:
        return self.values.get(provider)

    def set(self, provider: str, secret: str) -> None:
        self.values[provider] = secret

    def delete(self, provider: str) -> None:
        self.values.pop(provider, None)


class FailingSecretStore:
    def get(self, provider: str) -> str | None:
        raise RuntimeError(f"vault unavailable for {provider}")

    def set(self, provider: str, secret: str) -> None:
        raise RuntimeError(f"vault unavailable for {provider}")

    def delete(self, provider: str) -> None:
        raise RuntimeError(f"vault unavailable for {provider}")


class FailAfterFirstReadSecretStore(FakeSecretStore):
    def __init__(self) -> None:
        super().__init__()
        self.reads = 0

    def get(self, provider: str) -> str | None:
        self.reads += 1
        if self.reads > 1:
            raise RuntimeError(f"vault became unavailable for {provider}")
        return super().get(provider)


class FailOnReadSecretStore(FakeSecretStore):
    def get(self, provider: str) -> str | None:
        raise RuntimeError(f"vault unavailable for {provider}")


class CoordinatedSecretStore(FakeSecretStore):
    def __init__(self) -> None:
        super().__init__()
        self.resolve_read_started = threading.Event()
        self.allow_resolve_read = threading.Event()
        self.new_secret_written = threading.Event()

    def get(self, provider: str) -> str | None:
        if threading.current_thread().name == "resolver":
            self.resolve_read_started.set()
            if not self.allow_resolve_read.wait(timeout=2):
                raise RuntimeError("timed out waiting to read the credential")
        return super().get(provider)

    def set(self, provider: str, secret: str) -> None:
        super().set(provider, secret)
        self.new_secret_written.set()


class ProviderConnectionsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.catalog_path = root / "model_catalog.yaml"
        shutil.copy2(REPOSITORY_ROOT / "config" / "model_catalog.yaml", self.catalog_path)
        self.secrets = FakeSecretStore()
        self.probe_results = {
            "invalid-secret": "authentication_failed",
            "valid-secret": "valid",
        }
        self.client = TestClient(
            create_app(
                results_root=root / "results",
                tasks_root=root / "tasks",
                model_catalog_path=self.catalog_path,
                secret_store=self.secrets,
                provider_probe=lambda _provider, _base_url, credential: (
                    self.probe_results[credential]
                ),
            )
        )

    def test_saved_credential_takes_precedence_without_being_returned(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "environment-secret"}):
            before = self.client.get("/api/admin/provider-connections").json()
            relay = next(item for item in before["connections"] if item["provider"] == "relay")
            self.assertEqual(relay["credential_source"], "environment")

            response = self.client.put(
                "/api/admin/provider-connections/relay",
                json={"api_key": "vault-secret", "base_url": relay["base_url"]},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.secrets.values["relay"], "vault-secret")
        self.assertEqual(response.json()["credential_source"], "vault")
        self.assertEqual(response.json()["verification_status"], "unverified")
        self.assertNotIn("vault-secret", response.text)
        self.assertNotIn("environment-secret", response.text)

    def test_online_verification_is_separate_and_tracks_current_credential(self) -> None:
        saved = self.client.put(
            "/api/admin/provider-connections/qwen",
            json={"api_key": "invalid-secret"},
        )
        self.assertEqual(saved.json()["verification_status"], "unverified")

        failed = self.client.post("/api/admin/provider-connections/qwen/verify")
        self.assertEqual(failed.status_code, 200)
        self.assertEqual(failed.json()["verification_status"], "authentication_failed")

        replaced = self.client.put(
            "/api/admin/provider-connections/qwen",
            json={"api_key": "valid-secret"},
        )
        self.assertEqual(replaced.json()["verification_status"], "unverified")
        verified = self.client.post("/api/admin/provider-connections/qwen/verify")
        self.assertEqual(verified.json()["verification_status"], "valid")

    def test_deleting_vault_credential_reveals_environment_fallback(self) -> None:
        self.client.put(
            "/api/admin/provider-connections/relay",
            json={"api_key": "vault-secret"},
        )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "environment-secret"}):
            response = self.client.delete(
                "/api/admin/provider-connections/relay/credential"
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("relay", self.secrets.values)
        self.assertEqual(response.json()["credential_source"], "environment")
        self.assertTrue(response.json()["credential_configured"])
        self.assertNotIn("environment-secret", response.text)

    def test_credential_reveal_requires_an_explicit_request(self) -> None:
        self.secrets.values["relay"] = "vault-secret"

        with patch.dict(os.environ, {"OPENAI_API_KEY": "environment-secret"}):
            listed = self.client.get("/api/admin/provider-connections")
            revealed = self.client.post(
                "/api/admin/provider-connections/relay/credential/reveal"
            )

        self.assertEqual(listed.status_code, 200)
        self.assertNotIn("vault-secret", listed.text)
        self.assertNotIn("environment-secret", listed.text)
        self.assertEqual(revealed.status_code, 200)
        self.assertEqual(revealed.json(), {"api_key": "vault-secret"})

    def test_credential_reveal_uses_environment_fallback_when_needed(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "environment-secret"}):
            response = self.client.post(
                "/api/admin/provider-connections/relay/credential/reveal"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"api_key": "environment-secret"})

    def test_credential_reveal_rejects_missing_credential(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            response = self.client.post(
                "/api/admin/provider-connections/relay/credential/reveal"
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "API key is not configured")

    def test_endpoint_change_is_persisted(self) -> None:
        response = self.client.put(
            "/api/admin/provider-connections/qwen",
            json={"base_url": "https://qwen-proxy.example/v1"},
        )

        self.assertEqual(response.status_code, 200)
        catalog = yaml.safe_load(self.catalog_path.read_text())
        self.assertEqual(
            catalog["providers"]["qwen"]["base_url"],
            "https://qwen-proxy.example/v1",
        )

    def test_unknown_provider_operations_return_not_found(self) -> None:
        self.assertEqual(
            self.client.put(
                "/api/admin/provider-connections/unknown",
                json={"api_key": "secret"},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/admin/provider-connections/unknown/verify"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/admin/provider-connections/unknown/credential/reveal"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete(
                "/api/admin/provider-connections/unknown/credential"
            ).status_code,
            404,
        )

    def test_vault_failure_returns_service_unavailable(self) -> None:
        root = Path(self._tmp.name)
        client = TestClient(
            create_app(
                results_root=root / "failed-results",
                tasks_root=root / "failed-tasks",
                model_catalog_path=self.catalog_path,
                secret_store=FailingSecretStore(),
            )
        )

        listed = client.get("/api/admin/provider-connections")
        saved = client.put(
            "/api/admin/provider-connections/relay", json={"api_key": "secret"}
        )
        revealed = client.post(
            "/api/admin/provider-connections/relay/credential/reveal"
        )
        deleted = client.delete("/api/admin/provider-connections/relay/credential")

        self.assertEqual(listed.status_code, 503)
        self.assertEqual(saved.status_code, 503)
        self.assertEqual(revealed.status_code, 503)
        self.assertEqual(deleted.status_code, 503)
        self.assertNotIn("secret", saved.text)

    def test_credential_is_rolled_back_when_endpoint_persistence_fails(self) -> None:
        self.secrets.values["relay"] = "original-secret"
        service = ProviderConnectionService(self.catalog_path, self.secrets)

        with patch(
            "admin_console.provider_connections.save_catalog",
            side_effect=OSError("disk full"),
        ):
            with self.assertRaisesRegex(OSError, "disk full"):
                service.update(
                    "relay",
                    api_key="replacement-secret",
                    base_url="https://new-relay.example/v1",
                )

        self.assertEqual(self.secrets.values["relay"], "original-secret")

    def test_save_response_does_not_reread_vault_after_commit(self) -> None:
        secrets = FailAfterFirstReadSecretStore()
        secrets.values["relay"] = "original-secret"
        service = ProviderConnectionService(self.catalog_path, secrets)

        connection = service.update(
            "relay",
            api_key="replacement-secret",
            base_url="https://new-relay.example/v1",
        )

        self.assertEqual(secrets.reads, 1)
        self.assertEqual(secrets.values["relay"], "replacement-secret")
        self.assertEqual(connection["credential_source"], "vault")
        self.assertEqual(connection["base_url"], "https://new-relay.example/v1")

    def test_delete_response_does_not_read_vault_after_commit(self) -> None:
        secrets = FailOnReadSecretStore()
        secrets.values["relay"] = "stored-secret"
        service = ProviderConnectionService(self.catalog_path, secrets)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "environment-secret"}):
            connection = service.delete_credential("relay")

        self.assertNotIn("relay", secrets.values)
        self.assertEqual(connection["credential_source"], "environment")
        self.assertTrue(connection["credential_configured"])

    def test_execution_preflight_probes_current_connection_every_time(self) -> None:
        self.secrets.values["relay"] = "valid-secret"
        statuses = iter(["valid", "authentication_failed"])
        probes: list[str] = []
        service = ProviderConnectionService(
            self.catalog_path,
            self.secrets,
            probe=lambda _provider, _base_url, credential: (
                probes.append(credential) or next(statuses)
            ),
        )

        service.resolve_for_execution("relay")
        with self.assertRaises(ProviderConnectionNotReadyError):
            service.resolve_for_execution("relay")

        self.assertEqual(probes, ["valid-secret", "valid-secret"])

    def test_execution_resolution_cannot_mix_concurrent_provider_updates(self) -> None:
        secrets = CoordinatedSecretStore()
        secrets.values["relay"] = "old-secret"
        old_base_url = yaml.safe_load(self.catalog_path.read_text())["providers"][
            "relay"
        ]["base_url"]
        probes: list[tuple[str, str]] = []
        errors: list[Exception] = []
        service = ProviderConnectionService(
            self.catalog_path,
            secrets,
            probe=lambda _provider, base_url, credential: (
                probes.append((base_url, credential)) or "valid"
            ),
        )

        def resolve() -> None:
            try:
                service.resolve_for_execution("relay")
            except Exception as error:
                errors.append(error)

        def update() -> None:
            try:
                service.update(
                    "relay",
                    api_key="new-secret",
                    base_url="https://new-relay.example/v1",
                )
            except Exception as error:
                errors.append(error)

        resolver = threading.Thread(target=resolve, name="resolver")
        updater = threading.Thread(target=update, name="updater")
        resolver.start()
        self.assertTrue(secrets.resolve_read_started.wait(timeout=1))
        updater.start()
        secrets.new_secret_written.wait(timeout=0.2)
        secrets.allow_resolve_read.set()
        resolver.join(timeout=2)
        updater.join(timeout=2)

        self.assertFalse(resolver.is_alive())
        self.assertFalse(updater.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(probes, [(old_base_url, "old-secret")])


if __name__ == "__main__":
    unittest.main()
