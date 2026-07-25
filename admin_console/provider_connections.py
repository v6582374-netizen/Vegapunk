"""Provider credential and endpoint management for System Settings."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Protocol
from urllib.parse import urlparse

import httpx

from admin_console.configuration_files import source_configuration_transaction
from admin_console.model_catalog import load_catalog, save_catalog, validate_catalog

ACTIVE_PROVIDERS = ("relay", "qwen")
KEYRING_SERVICE = "vegapunk.model-provider"
VerificationStatus = Literal[
    "unverified", "valid", "authentication_failed", "unreachable"
]
ProviderProbe = Callable[[str, str, str], VerificationStatus]


class SecretStore(Protocol):
    def get(self, provider: str) -> str | None: ...

    def set(self, provider: str, secret: str) -> None: ...

    def delete(self, provider: str) -> None: ...


class KeyringSecretStore:
    """OS credential-vault adapter backed by the cross-platform keyring package."""

    @staticmethod
    def _keyring():
        try:
            import keyring
        except ImportError as error:
            raise RuntimeError(
                "the operating-system credential vault is unavailable; install keyring"
            ) from error
        return keyring

    def get(self, provider: str) -> str | None:
        return self._keyring().get_password(KEYRING_SERVICE, provider)

    def set(self, provider: str, secret: str) -> None:
        self._keyring().set_password(KEYRING_SERVICE, provider, secret)

    def delete(self, provider: str) -> None:
        keyring = self._keyring()
        try:
            keyring.delete_password(KEYRING_SERVICE, provider)
        except keyring.errors.PasswordDeleteError:
            return


class UnknownProviderError(KeyError):
    pass


class InvalidProviderConnectionError(ValueError):
    pass


class SecretStoreUnavailableError(RuntimeError):
    pass


class ProviderConnectionNotReadyError(RuntimeError):
    def __init__(self, provider: str, status: VerificationStatus) -> None:
        self.provider = provider
        self.status = status
        super().__init__(
            f"Provider connection {provider!r} is not ready: {status}"
        )


@dataclass(frozen=True)
class EffectiveProviderConnection:
    provider: str
    base_url: str
    environment_variable: str
    credential: str


def probe_provider(provider: str, base_url: str, credential: str) -> VerificationStatus:
    del provider
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {credential}"},
            timeout=10,
        )
    except httpx.HTTPError:
        return "unreachable"
    if 200 <= response.status_code < 300:
        return "valid"
    if response.status_code in {401, 403}:
        return "authentication_failed"
    return "unreachable"


class ProviderConnectionService:
    def __init__(
        self,
        catalog_path: Path,
        secret_store: SecretStore,
        probe: ProviderProbe = probe_provider,
    ) -> None:
        self._catalog_path = catalog_path
        self._secret_store = secret_store
        self._probe = probe
        self._verification: dict[str, tuple[str, str]] = {}

    def list(self) -> list[dict]:
        return [self.get(provider) for provider in ACTIVE_PROVIDERS]

    def get(self, provider: str) -> dict:
        catalog, config = self._provider(provider)
        credential, source = self._effective_credential(provider, config)
        return self._connection_document(
            provider, catalog, config, credential, source
        )

    def _connection_document(
        self,
        provider: str,
        catalog: dict,
        config: dict,
        credential: str | None,
        source: str,
    ) -> dict:
        signature = self._signature(config.get("base_url", ""), credential)
        recorded_signature, status = self._verification.get(
            provider, ("", "unverified")
        )
        if recorded_signature != signature:
            status = "unverified"
        return {
            "provider": provider,
            "name": "Qwen" if provider == "qwen" else "Relay",
            "base_url": config.get("base_url", ""),
            "base_url_configurable": "base_url"
            in config.get("user_configurable_fields", []),
            "credential_configured": credential is not None,
            "credential_source": source,
            "environment_variable": config.get("api_key_env"),
            "verification_status": status,
            "model_count": sum(
                1
                for model in catalog.get("models", {}).values()
                if model.get("provider") == provider
            ),
        }

    def update(
        self, provider: str, *, api_key: str | None, base_url: str | None
    ) -> dict:
        with source_configuration_transaction():
            catalog, config = self._provider(provider)
            credential, source = self._effective_credential(provider, config)
            if base_url is not None:
                if "base_url" not in config.get("user_configurable_fields", []):
                    raise InvalidProviderConnectionError(
                        f"base_url is not configurable for provider {provider!r}"
                    )
                parsed = urlparse(base_url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise InvalidProviderConnectionError(
                        "base_url must be an absolute HTTP or HTTPS URL"
                    )
                config["base_url"] = base_url.rstrip("/")

            document = validate_catalog(catalog)
            previous_credential: str | None = None
            if api_key is not None:
                if not api_key.strip():
                    raise InvalidProviderConnectionError("api_key must not be empty")
                if source == "vault":
                    previous_credential = credential
                self._set_credential(provider, api_key)
                credential = api_key
                source = "vault"

            try:
                save_catalog(self._catalog_path, document)
            except Exception:
                if api_key is not None:
                    if previous_credential is None:
                        self._delete_stored_credential(provider)
                    else:
                        self._set_credential(provider, previous_credential)
                raise
            self._verification.pop(provider, None)
            return self._connection_document(
                provider, catalog, config, credential, source
            )

    def verify(self, provider: str) -> dict:
        with source_configuration_transaction():
            catalog, config = self._provider(provider)
            credential, source = self._effective_credential(provider, config)
            if credential is None:
                status: VerificationStatus = "authentication_failed"
            else:
                status = self._probe(
                    provider, config.get("base_url", ""), credential
                )
            signature = self._signature(config.get("base_url", ""), credential)
            self._verification[provider] = (signature, status)
            return self._connection_document(
                provider, catalog, config, credential, source
            )

    def delete_credential(self, provider: str) -> dict:
        with source_configuration_transaction():
            catalog, config = self._provider(provider)
            self._delete_stored_credential(provider)
            environment_name = config.get("api_key_env")
            credential = (
                os.environ.get(environment_name) if environment_name else None
            )
            source = "environment" if credential else "missing"
            self._verification.pop(provider, None)
            return self._connection_document(
                provider, catalog, config, credential, source
            )

    def resolve_for_execution(self, provider: str) -> EffectiveProviderConnection:
        """Resolve and verify one current connection without exposing its secret."""

        with source_configuration_transaction():
            _, config = self._provider(provider)
            credential, _ = self._effective_credential(provider, config)
            base_url = config.get("base_url", "")
            signature = self._signature(base_url, credential)
            status = (
                self._probe(provider, base_url, credential)
                if credential is not None
                else "authentication_failed"
            )
            self._verification[provider] = (signature, status)
            if status != "valid":
                raise ProviderConnectionNotReadyError(provider, status)

            environment_variable = config.get("api_key_env")
            if not isinstance(environment_variable, str) or not environment_variable:
                raise InvalidProviderConnectionError(
                    f"provider {provider!r} does not declare an API key environment variable"
                )
            assert credential is not None
            return EffectiveProviderConnection(
                provider=provider,
                base_url=base_url,
                environment_variable=environment_variable,
                credential=credential,
            )

    def _provider(self, provider: str) -> tuple[dict, dict]:
        if provider not in ACTIVE_PROVIDERS:
            raise UnknownProviderError(provider)
        with source_configuration_transaction():
            catalog = load_catalog(self._catalog_path)
            try:
                return catalog, catalog["providers"][provider]
            except KeyError as error:
                raise UnknownProviderError(provider) from error

    def _effective_credential(
        self, provider: str, config: dict
    ) -> tuple[str | None, str]:
        stored = self._stored_credential(provider)
        if stored:
            return stored, "vault"
        environment_name = config.get("api_key_env")
        environment_value = os.environ.get(environment_name) if environment_name else None
        if environment_value:
            return environment_value, "environment"
        return None, "missing"

    def _stored_credential(self, provider: str) -> str | None:
        try:
            return self._secret_store.get(provider)
        except Exception as error:
            raise SecretStoreUnavailableError(
                "the operating-system credential vault is unavailable"
            ) from error

    def _set_credential(self, provider: str, credential: str) -> None:
        try:
            self._secret_store.set(provider, credential)
        except Exception as error:
            raise SecretStoreUnavailableError(
                "the operating-system credential vault is unavailable"
            ) from error

    def _delete_stored_credential(self, provider: str) -> None:
        try:
            self._secret_store.delete(provider)
        except Exception as error:
            raise SecretStoreUnavailableError(
                "the operating-system credential vault is unavailable"
            ) from error

    @staticmethod
    def _signature(base_url: str, credential: str | None) -> str:
        value = f"{base_url}\0{credential or ''}".encode()
        return hashlib.sha256(value).hexdigest()
