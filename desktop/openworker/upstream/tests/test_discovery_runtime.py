"""Regression tests for the production Discovery runtime admission seam."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from coworker.server.discovery_runtime import (
    DiscoveryRuntimePreflightError,
    apply_provider_overrides,
    prepare_launch_environment,
)
from coworker.server.discovery_launch import DiscoveryLaunchStore
from coworker.server import discovery_launch as discovery_launch_module
from coworker.server import discovery_worker as discovery_worker_module


class MemorySecrets:
    def __init__(self, profiles: dict[str, dict[str, object]] | None = None) -> None:
        self.profiles = profiles or {}

    def get(self, profile: str):
        return self.profiles.get(profile)


def _catalog(*, active: str = "qwen/text", image: str = "qwen/image") -> dict:
    return {
        "active_text_model": active,
        "capability_models": {
            "vision": "relay/vision",
            "image_generation": image,
            "embedding": "local/embedding",
        },
        "providers": {
            "qwen": {
                "protocol": "responses",
                "base_url": "https://qwen.invalid/v1",
                "api_key_env": "DASHSCOPE_API_KEY",
                "user_configurable_fields": ["base_url"],
            },
            "relay": {
                "protocol": "responses",
                "base_url": "https://relay.invalid/v1",
                "api_key_env": "OPENAI_API_KEY",
                "user_configurable_fields": ["base_url"],
            },
            "local": {"protocol": "local_embedding"},
        },
        "models": {
            "qwen/text": {
                "provider": "qwen",
                "model": "text",
                "capabilities": ["text", "json", "tools", "reasoning"],
            },
            "qwen/image": {
                "provider": "qwen",
                "model": "image",
                "capabilities": ["image_generation"],
                "protocol": "dashscope_multimodal",
            },
            "relay/vision": {
                "provider": "relay",
                "model": "vision",
                "capabilities": ["vision"],
            },
            "local/embedding": {
                "provider": "local",
                "model": "embedding",
                "capabilities": ["embedding"],
                "protocol": "local_embedding",
            },
        },
    }


def test_preflight_injects_secret_store_credentials_for_every_bound_provider(tmp_path, monkeypatch):
    catalog_path = tmp_path / "model_catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(_catalog()), encoding="utf-8")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    prepared = prepare_launch_environment(
        catalog_path,
        secret_store=MemorySecrets(
            {
                "provider:qwen": {
                    "api_key": "qwen-secret",
                    "base_url": "https://qwen.example/v1",
                },
                "provider:relay": {
                    "api_key": "relay-secret",
                    "base_url": "https://relay.example/v1",
                },
            }
        ),
        required_modules=(),
    )

    assert prepared.required_providers == ("qwen", "relay")
    assert prepared.environment["DASHSCOPE_API_KEY"] == "qwen-secret"
    assert prepared.environment["OPENAI_API_KEY"] == "relay-secret"
    assert prepared.provider_overrides == {
        "qwen": {"base_url": "https://qwen.example/v1"},
        "relay": {"base_url": "https://relay.example/v1"},
    }
    assert "qwen-secret" not in repr(prepared)
    assert "relay-secret" not in repr(prepared)


def test_preflight_reports_all_missing_credentials_before_workflow_start(tmp_path, monkeypatch):
    catalog_path = tmp_path / "model_catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(_catalog()), encoding="utf-8")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(DiscoveryRuntimePreflightError) as raised:
        prepare_launch_environment(
            catalog_path,
            secret_store=MemorySecrets(),
            required_modules=(),
        )

    message = str(raised.value)
    assert "qwen" in message
    assert "DASHSCOPE_API_KEY" in message
    assert "relay" in message
    assert "OPENAI_API_KEY" in message


def test_provider_overrides_update_only_launch_owned_catalog(tmp_path):
    catalog_path = tmp_path / "model_catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(_catalog()), encoding="utf-8")

    apply_provider_overrides(
        catalog_path,
        {"qwen": {"base_url": "https://override.example/v1"}},
    )

    updated = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    assert updated["providers"]["qwen"]["base_url"] == "https://override.example/v1"
    assert "api_key" not in updated["providers"]["qwen"]


def test_preflight_reports_missing_production_dependency(tmp_path, monkeypatch):
    catalog_path = tmp_path / "model_catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(_catalog()), encoding="utf-8")
    monkeypatch.setattr(
        "coworker.server.discovery_runtime.importlib.util.find_spec",
        lambda name: None if name == "fastmcp" else object(),
    )

    with pytest.raises(DiscoveryRuntimePreflightError, match="fastmcp"):
        prepare_launch_environment(
            catalog_path,
            secret_store=MemorySecrets(
                {
                    "provider:qwen": {"api_key": "qwen-secret"},
                    "provider:relay": {"api_key": "relay-secret"},
                }
            ),
            required_modules=("fastmcp",),
        )


def test_worker_does_not_project_running_before_preflight(tmp_path, monkeypatch):
    repository_root = tmp_path / "repo"
    (repository_root / "config").mkdir(parents=True)
    (repository_root / "config" / "default_config.yaml").write_text(
        "model_catalog_path: config/model_catalog.yaml\n", encoding="utf-8"
    )
    (repository_root / "config" / "model_catalog.yaml").write_text(
        yaml.safe_dump(_catalog()), encoding="utf-8"
    )
    root = tmp_path / "state" / "discovery"
    store = DiscoveryLaunchStore(
        root,
        runner_mode="real",
        repository_root=repository_root,
    )

    class Process:
        pid = 0

    monkeypatch.setattr(
        discovery_launch_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: Process(),
    )
    admitted = store.admit(
        request_fingerprint="preflight-failure",
        idempotency_key="preflight-failure",
        input_snapshot={
            "preparation_id": "preparation",
            "revision_id": "revision",
            "execution_input": {"task_description": "test"},
            "sources": [],
        },
        configuration_snapshot={"model_id": "qwen/text", "settings": {}},
        response_builder=lambda: {},
    )
    launch_id = admitted["launch_id"]
    launch_dir = root / "launches" / launch_id
    attempt_id = json.loads(
        (launch_dir / "record.json").read_text(encoding="utf-8")
    )["current_attempt_id"]

    monkeypatch.undo()
    result = discovery_worker_module.run(
        launcher_entry=repository_root / "launch_discovery.py",
        launch_dir=launch_dir,
        discovery_root=root,
        attempt_id=attempt_id,
        repository_root=repository_root,
        mode="experiment",
        exp_backend="codex",
        resume=False,
        secret_store=MemorySecrets(),
    )

    assert result == 1
    status = store.status(launch_id)
    assert status["launch"]["state"] == "failed"
    assert "DASHSCOPE_API_KEY" in status["launch"]["error"]
    assert "OPENAI_API_KEY" in status["launch"]["error"]


def test_worker_projects_known_launcher_error_into_launch_record(tmp_path, monkeypatch):
    repository_root = tmp_path / "repo"
    (repository_root / "config").mkdir(parents=True)
    (repository_root / "config" / "default_config.yaml").write_text(
        "model_catalog_path: config/model_catalog.yaml\n", encoding="utf-8"
    )
    (repository_root / "config" / "model_catalog.yaml").write_text(
        yaml.safe_dump(_catalog()), encoding="utf-8"
    )
    launcher = repository_root / "fake_launcher.py"
    launcher.write_text(
        "print('Fatal error: synthetic MAS failure', flush=True)\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    root = tmp_path / "state" / "discovery"
    store = DiscoveryLaunchStore(
        root,
        runner_mode="real",
        repository_root=repository_root,
    )

    class Process:
        pid = 0

    monkeypatch.setattr(
        discovery_launch_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: Process(),
    )
    admitted = store.admit(
        request_fingerprint="launcher-error",
        idempotency_key="launcher-error",
        input_snapshot={
            "preparation_id": "preparation",
            "revision_id": "revision",
            "execution_input": {"task_description": "test"},
            "sources": [],
        },
        configuration_snapshot={"model_id": "qwen/text", "settings": {}},
        response_builder=lambda: {},
    )
    launch_id = admitted["launch_id"]
    launch_dir = root / "launches" / launch_id
    attempt_id = json.loads(
        (launch_dir / "record.json").read_text(encoding="utf-8")
    )["current_attempt_id"]

    monkeypatch.undo()
    result = discovery_worker_module.run(
        launcher_entry=launcher,
        launch_dir=launch_dir,
        discovery_root=root,
        attempt_id=attempt_id,
        repository_root=repository_root,
        mode="experiment",
        exp_backend="codex",
        resume=False,
        secret_store=MemorySecrets(
            {
                "provider:qwen": {"api_key": "qwen-secret"},
                "provider:relay": {"api_key": "relay-secret"},
            }
        ),
    )

    assert result == 1
    status = store.status(launch_id)
    assert status["launch"]["error"] == "Fatal error: synthetic MAS failure"
