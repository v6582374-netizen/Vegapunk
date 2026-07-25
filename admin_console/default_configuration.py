"""Product-facing aggregate for model bindings and registered run defaults."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from admin_console.configuration_files import source_configuration_transaction
from admin_console.model_catalog import (
    load_catalog,
    save_catalog,
    validate_catalog,
)
from admin_console.parameters import (
    load_registered_values,
    registered_parameter_catalog,
    save_values,
    validate_registered_values,
)
from admin_console.provider_connections import ProviderConnectionService


def read_default_configuration(
    config_path: Path,
    catalog_path: Path,
    provider_connections: ProviderConnectionService,
) -> dict:
    with source_configuration_transaction():
        catalog = load_catalog(catalog_path)
        parameters = load_registered_values(config_path)
        return _configuration_document(catalog, parameters, provider_connections)


def _configuration_document(
    catalog: dict,
    parameters: dict,
    provider_connections: ProviderConnectionService,
) -> dict:
    bindings = {
        "active_text_model": catalog["active_text_model"],
        "image_model": catalog["capability_models"]["image_generation"],
        "embedding_model": catalog["capability_models"]["embedding"],
    }
    models = [
        {
            "id": identity,
            "provider": model["provider"],
            "model": model["model"],
            "capabilities": model.get("capabilities", []),
        }
        for identity, model in catalog.get("models", {}).items()
    ]
    runtime_model_ids = {
        catalog["active_text_model"],
        *catalog.get("capability_models", {}).values(),
    }
    required_providers = sorted(
        {
            catalog["models"][identity]["provider"]
            for identity in runtime_model_ids
            if catalog["models"][identity]["provider"] != "local"
        }
    )
    connections = [provider_connections.get(provider) for provider in required_providers]
    revision_source = json.dumps(
        {"bindings": bindings, "parameters": parameters},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "revision": hashlib.sha256(revision_source).hexdigest()[:16],
        "bindings": bindings,
        "models": models,
        "parameter_catalog": registered_parameter_catalog(),
        "parameters": parameters,
        "readiness": {
            "ready": all(
                connection["verification_status"] == "valid"
                for connection in connections
            ),
            "connections": connections,
        },
    }


def save_default_configuration(
    config_path: Path,
    catalog_path: Path,
    provider_connections: ProviderConnectionService,
    bindings: dict,
    parameters: dict,
) -> dict:
    required_bindings = {"active_text_model", "image_model", "embedding_model"}
    if set(bindings) != required_bindings:
        raise ValueError(
            "bindings must contain active_text_model, image_model, and embedding_model"
        )

    with source_configuration_transaction():
        catalog = load_catalog(catalog_path)
        capability_by_binding = {
            "active_text_model": "text",
            "image_model": "image_generation",
            "embedding_model": "embedding",
        }
        for binding, capability in capability_by_binding.items():
            identity = bindings[binding]
            model = catalog.get("models", {}).get(identity)
            if model is None:
                raise ValueError(f"unknown Canonical Model Identity: {identity}")
            if capability not in model.get("capabilities", []):
                raise ValueError(f"{identity} does not provide {capability}")

        catalog["active_text_model"] = bindings["active_text_model"]
        catalog["capability_models"]["image_generation"] = bindings["image_model"]
        catalog["capability_models"]["embedding"] = bindings["embedding_model"]
        catalog_document = validate_catalog(catalog)
        parameter_document = validate_registered_values(config_path, parameters)
        catalog_temporary = _temporary_path(catalog_path)
        config_temporary = _temporary_path(config_path)
        original_catalog = catalog_path.read_bytes()
        original_config = config_path.read_bytes()
        try:
            save_catalog(catalog_temporary, catalog_document)
            save_values(config_temporary, parameter_document)
            pending = _configuration_document(
                load_catalog(catalog_temporary),
                load_registered_values(config_temporary),
                provider_connections,
            )
            os.replace(config_temporary, config_path)
            os.replace(catalog_temporary, catalog_path)
        except Exception:
            _replace_bytes(config_path, original_config)
            _replace_bytes(catalog_path, original_catalog)
            raise
        finally:
            config_temporary.unlink(missing_ok=True)
            catalog_temporary.unlink(missing_ok=True)

    return pending


def _temporary_path(target: Path) -> Path:
    with NamedTemporaryFile(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False
    ) as temporary:
        path = Path(temporary.name)
    if target.exists():
        path.chmod(target.stat().st_mode)
    return path


def _replace_bytes(target: Path, content: bytes) -> None:
    temporary = _temporary_path(target)
    try:
        temporary.write_bytes(content)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
