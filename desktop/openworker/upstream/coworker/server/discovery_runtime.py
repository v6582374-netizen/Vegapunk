"""Admission-time runtime configuration for production Discovery Launches.

The Launch snapshot is the only source of model and external-data metadata. This module
turns that snapshot into the short-lived environment a worker needs, resolving credentials
from the SecretStore at the process seam and validating the complete bound Provider/API set
before the production launcher is marked as running.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlparse

import yaml


class SecretResolver(Protocol):
    def get(self, profile: str) -> Mapping[str, Any] | None:
        """Return one resolved secret profile without exposing it to callers."""


class DiscoveryRuntimePreflightError(RuntimeError):
    """A Launch cannot be admitted to the production runtime."""


@dataclass(frozen=True)
class PreparedRuntimeEnvironment:
    """Validated child-process environment and non-sensitive catalog overrides.

    The environment is intentionally excluded from ``repr`` so a diagnostic or test
    failure cannot print provider credentials.  It is still returned to the worker
    process, where it lives only for the lifetime of the Launch attempt.
    """

    environment: dict[str, str] = field(repr=False)
    required_providers: tuple[str, ...]
    provider_overrides: dict[str, dict[str, str]]
    required_external_data: tuple[str, ...]


def prepare_launch_environment(
    catalog_path: str | Path,
    *,
    secret_store: SecretResolver | None = None,
    base_environment: Mapping[str, str] | None = None,
    external_data: Mapping[str, Any] | None = None,
    required_modules: Sequence[str] = ("fastmcp", "json_repair"),
    exp_backend: str | None = None,
) -> PreparedRuntimeEnvironment:
    """Resolve and validate everything required before ``launch_discovery.py``.

    Stored credentials take precedence over inherited environment variables, matching
    the desktop SecretStore contract.  Plaintext values are never written to the
    catalog or returned in an exception.  The required Provider set is derived from
    the active text model plus every capability binding, and enabled external-data
    entries are resolved from their API-service profiles, so a Launch cannot appear
    ready while a later capability or configured data source is unusable.
    """

    catalog = _read_catalog(Path(catalog_path))
    if secret_store is None:
        from coworker.secrets import SecretStore

        secret_store = SecretStore()

    environment = dict(base_environment or os.environ)
    issues: list[str] = []
    required_providers = _required_providers(catalog, issues)
    required_external_data = _required_external_data(external_data, issues)
    providers = catalog.get("providers")
    if not isinstance(providers, Mapping):
        issues.append("model catalog providers must be a mapping")
        providers = {}

    overrides: dict[str, dict[str, str]] = {}
    for provider_name in required_providers:
        provider = providers.get(provider_name)
        if not isinstance(provider, Mapping):
            issues.append(f"Provider {provider_name!r} is not declared in the model catalog")
            continue
        protocol = str(provider.get("protocol") or "")
        if protocol == "local_embedding":
            continue

        env_name = provider.get("api_key_env")
        if not isinstance(env_name, str) or not env_name.strip():
            issues.append(f"Provider {provider_name!r} does not declare api_key_env")
            continue
        env_name = env_name.strip()

        profile: Mapping[str, Any] = {}
        try:
            resolved = secret_store.get(f"provider:{provider_name}")
            if isinstance(resolved, Mapping):
                profile = resolved
        except Exception as error:  # pragma: no cover - platform vault failures vary
            issues.append(
                f"Credential store could not be read for Provider {provider_name!r}: "
                f"{type(error).__name__}"
            )

        stored_key = profile.get("api_key")
        api_key = stored_key.strip() if isinstance(stored_key, str) else ""
        if not api_key:
            inherited_key = environment.get(env_name, "")
            api_key = inherited_key.strip() if isinstance(inherited_key, str) else ""
        if not api_key:
            issues.append(
                f"Missing API key for Provider {provider_name!r} (expected {env_name})"
            )
        else:
            # This value is passed only to the worker's child environment.  It is not
            # part of PreparedRuntimeEnvironment's repr or any Launch snapshot.
            environment[env_name] = api_key

        base_url = profile.get("base_url")
        if base_url is not None:
            if not isinstance(base_url, str) or urlparse(base_url).scheme not in {
                "http",
                "https",
            }:
                issues.append(
                    f"Stored base_url override for Provider {provider_name!r} "
                    "must be an HTTP(S) URL"
                )
            else:
                overrides[provider_name] = {"base_url": base_url.rstrip("/")}

    # PaperOrchestra and future paper adapters use the same API Services SecretStore
    # profiles as the settings surface. Keep credentials out of catalogs and snapshots;
    # expose them only to this trusted Launch child process, using every declared
    # environment-variable alias so legacy and current adapters share one source.
    from coworker.api_services import get_runtime_api_service_environment

    environment.update(
        get_runtime_api_service_environment(
            secret_store,
            inherited_environment=environment,
        )
    )

    for api_id, docs_url in required_external_data:
        from coworker.api_services import external_data_descriptor

        service = external_data_descriptor(api_id)
        if service is None:
            issues.append(f"External data API {api_id!r} is not declared in the static catalog")
            continue
        parsed_docs_url = urlparse(docs_url)
        if parsed_docs_url.scheme not in {"http", "https"} or not parsed_docs_url.netloc:
            issues.append(f"External data API {api_id!r} documentation URL must be HTTP(S)")
        profile: Mapping[str, Any] = {}
        try:
            resolved = secret_store.get(f"api-service:{service.name}")
            if isinstance(resolved, Mapping):
                profile = resolved
        except Exception as error:  # pragma: no cover - platform vault failures vary
            issues.append(
                f"Credential store could not be read for external data API {api_id!r}: "
                f"{type(error).__name__}"
            )
        stored_key = profile.get("credential")
        api_key = stored_key.strip() if isinstance(stored_key, str) else ""
        env_name = service.environment_variables[0] if service.environment_variables else ""
        if not api_key and env_name:
            inherited_key = environment.get(env_name, "")
            api_key = inherited_key.strip() if isinstance(inherited_key, str) else ""
        if not api_key:
            issues.append(
                f"Missing API key for external data API {api_id!r} (expected {env_name})"
            )
        elif env_name:
            # API keys are injected only into the child process environment and never
            # copied into the launch snapshot, prompt, catalog, or worker log.
            environment[env_name] = api_key

    missing_modules = [
        module_name
        for module_name in required_modules
        if not _module_available(module_name)
    ]
    if missing_modules:
        issues.append(
            "Missing production Python dependencies: "
            + ", ".join(sorted(set(missing_modules)))
        )

    _require_experiment_backend(exp_backend, environment, issues)

    if issues:
        raise DiscoveryRuntimePreflightError("; ".join(issues))

    return PreparedRuntimeEnvironment(
        environment=environment,
        required_providers=required_providers,
        provider_overrides=overrides,
        required_external_data=tuple(api_id for api_id, _ in required_external_data),
    )


def _required_external_data(
    external_data: Mapping[str, Any] | None,
    issues: list[str],
) -> tuple[tuple[str, str], ...]:
    """Validate the launch-owned API registry without retaining any credentials."""

    if external_data is None:
        return ()
    if not isinstance(external_data, Mapping):
        issues.append("external_data must be a mapping")
        return ()
    registry = external_data.get("api_registry", [])
    if not isinstance(registry, list):
        issues.append("external_data.api_registry must be a list")
        return ()
    entries: list[tuple[str, str]] = []
    for index, item in enumerate(registry):
        if not isinstance(item, Mapping):
            issues.append(f"external_data.api_registry[{index}] must be an object")
            continue
        api_id = item.get("api_id")
        docs_url = item.get("official_docs_url")
        if not isinstance(api_id, str) or not api_id.strip():
            issues.append(f"external_data.api_registry[{index}] requires api_id")
            continue
        if not isinstance(docs_url, str) or not docs_url.strip():
            issues.append(f"external_data.api_registry[{index}] requires official_docs_url")
            continue
        entries.append((api_id.strip(), docs_url.strip()))
    return tuple(entries)


def apply_provider_overrides(
    catalog_path: str | Path,
    provider_overrides: Mapping[str, Mapping[str, str]],
) -> None:
    """Persist only allowed, non-sensitive overrides into a Launch-owned catalog."""

    path = Path(catalog_path)
    catalog = _read_catalog(path)
    providers = catalog.get("providers")
    if not isinstance(providers, dict):
        raise DiscoveryRuntimePreflightError("model catalog providers must be a mapping")
    for provider_name, values in provider_overrides.items():
        provider = providers.get(provider_name)
        if not isinstance(provider, dict):
            raise DiscoveryRuntimePreflightError(
                f"Provider {provider_name!r} is not declared in the model catalog"
            )
        base_url = values.get("base_url")
        if base_url is None:
            continue
        if urlparse(base_url).scheme not in {"http", "https"}:
            raise DiscoveryRuntimePreflightError(
                f"Provider {provider_name!r} base_url override must be HTTP(S)"
            )
        provider["base_url"] = base_url.rstrip("/")

    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    os.replace(temporary, path)


def _read_catalog(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise DiscoveryRuntimePreflightError(
            f"Unable to read model catalog {path}: {type(error).__name__}"
        ) from error
    if not isinstance(raw, dict):
        raise DiscoveryRuntimePreflightError("model catalog must be a mapping")
    return raw


def _required_providers(catalog: Mapping[str, Any], issues: list[str]) -> tuple[str, ...]:
    models = catalog.get("models")
    if not isinstance(models, Mapping):
        issues.append("model catalog models must be a mapping")
        return ()
    providers_catalog = catalog.get("providers")
    if not isinstance(providers_catalog, Mapping):
        providers_catalog = {}

    model_ids: list[str] = []
    active = catalog.get("active_text_model")
    if not isinstance(active, str) or not active.strip():
        issues.append("model catalog requires active_text_model")
    else:
        model_ids.append(active.strip())

    capability_models = catalog.get("capability_models", {})
    if not isinstance(capability_models, Mapping):
        issues.append("model catalog capability_models must be a mapping")
        capability_models = {}
    for capability, model_id in capability_models.items():
        if not isinstance(model_id, str) or not model_id.strip():
            issues.append(f"capability binding {capability!r} has no model identity")
            continue
        model_ids.append(model_id.strip())

    providers: list[str] = []
    for model_id in model_ids:
        definition = models.get(model_id)
        if not isinstance(definition, Mapping):
            issues.append(f"model catalog does not declare model {model_id!r}")
            continue
        provider = definition.get("provider")
        if not isinstance(provider, str) or not provider.strip():
            provider = model_id.split("/", 1)[0] if "/" in model_id else ""
        if not provider:
            issues.append(f"model {model_id!r} does not declare a Provider")
            continue
        provider = provider.strip()
        provider_definition = providers_catalog.get(provider)
        if (
            isinstance(provider_definition, Mapping)
            and provider_definition.get("protocol") == "local_embedding"
        ):
            continue
        if provider not in providers:
            providers.append(provider)
    return tuple(providers)


# The experiment backend is an independently installed coding-agent CLI named by
# the Launch snapshot, exactly like a Provider or an external-data source. It is
# resolved here so a Launch whose only executable step cannot run is refused at
# admission instead of spending a full research round to discover it.
_BACKEND_EXECUTABLES: Mapping[str, tuple[str, str]] = {
    # backend -> (default executable, environment variable that may override it)
    "codex": ("codex", "CODEX_BIN"),
    "qwen_code": ("qwen", "QWEN_CODE_BIN"),
    # OpenHands is reached over a WebSocket URI, so it has no local executable.
    "openhands": ("", ""),
}


def _require_experiment_backend(
    exp_backend: str | None,
    environment: Mapping[str, str],
    issues: list[str],
) -> None:
    """Record an issue when the selected backend's CLI is not on the child PATH."""

    if exp_backend is None:
        return
    backend = exp_backend.strip()
    binding = _BACKEND_EXECUTABLES.get(backend)
    if binding is None:
        issues.append(f"Unsupported Discovery experiment backend {backend!r}")
        return
    default_command, override_variable = binding
    if not default_command:
        return
    command = default_command
    if override_variable:
        configured = environment.get(override_variable, "")
        if isinstance(configured, str) and configured.strip():
            command = configured.strip()
    if shutil.which(command, path=environment.get("PATH")) is None:
        issues.append(
            f"Experiment backend {backend!r} requires the {command!r} executable, "
            "which is not on the Launch PATH"
        )


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False
