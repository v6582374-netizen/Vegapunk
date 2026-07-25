"""Prepare one secret-free runtime configuration after capability preflight."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml

from admin_console.provider_connections import ProviderConnectionService
from vegapunk.mas.models.unified_runtime import ModelCatalog


@dataclass(frozen=True)
class PreparedExecution:
    config_path: Path
    environment: dict[str, str]


class ExecutionPreparer(Protocol):
    def prepare(self, snapshot_dir: Path, runtime_dir: Path) -> PreparedExecution: ...


class CapabilityPreflight:
    """Keep snapshot bindings while resolving current Provider connections."""

    def __init__(self, provider_connections: ProviderConnectionService) -> None:
        self._provider_connections = provider_connections

    def prepare(self, snapshot_dir: Path, runtime_dir: Path) -> PreparedExecution:
        snapshot_config_path = snapshot_dir / "default_config.yaml"
        snapshot_catalog_path = snapshot_dir / "model_catalog.yaml"
        snapshot_config = yaml.safe_load(snapshot_config_path.read_text()) or {}
        snapshot_catalog = yaml.safe_load(snapshot_catalog_path.read_text()) or {}
        if not isinstance(snapshot_config, dict):
            raise ValueError("Launch Configuration Snapshot must contain a mapping")
        if not isinstance(snapshot_catalog, dict):
            raise ValueError("Launch model catalog snapshot must contain a mapping")

        catalog = ModelCatalog.from_mapping(snapshot_catalog)
        model_ids = {
            catalog.active_text_model,
            *catalog.capability_models.values(),
        }
        provider_names = sorted(
            {
                catalog.resolve_model(model_id).provider
                for model_id in model_ids
                if catalog.resolve_model(model_id).provider != "local"
            }
        )

        runtime_catalog = dict(snapshot_catalog)
        runtime_catalog["providers"] = {
            name: dict(settings)
            for name, settings in snapshot_catalog["providers"].items()
        }
        environment: dict[str, str] = {}
        for provider in provider_names:
            connection = self._provider_connections.resolve_for_execution(provider)
            provider_config = runtime_catalog["providers"].get(provider)
            if not isinstance(provider_config, dict):
                raise ValueError(
                    f"Launch model catalog does not declare Provider {provider!r}"
                )
            provider_config["base_url"] = connection.base_url
            provider_config["api_key_env"] = connection.environment_variable
            provider_config.pop("api_key", None)
            environment[connection.environment_variable] = connection.credential

        ModelCatalog.from_mapping(runtime_catalog)
        runtime_dir.mkdir(parents=True, exist_ok=False)
        runtime_catalog_path = runtime_dir / "model_catalog.yaml"
        runtime_catalog_path.write_text(
            yaml.safe_dump(runtime_catalog, allow_unicode=True, sort_keys=False)
        )
        runtime_config = dict(snapshot_config)
        runtime_config["model_catalog_path"] = str(runtime_catalog_path)
        runtime_config_path = runtime_dir / "default_config.yaml"
        runtime_config_path.write_text(
            yaml.safe_dump(runtime_config, allow_unicode=True, sort_keys=False)
        )
        return PreparedExecution(runtime_config_path, environment)
