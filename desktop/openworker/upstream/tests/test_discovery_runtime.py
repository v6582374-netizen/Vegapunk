"""Regression tests for the production Discovery runtime admission seam."""

from __future__ import annotations

import json
import sys
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


def test_preflight_prefers_stored_qwen_key_over_inherited_environment(
    tmp_path, monkeypatch
):
    """A stale parent-shell key must not shadow the Launch's configured key."""
    catalog_path = tmp_path / "model_catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(_catalog()), encoding="utf-8")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "stale-parent-key")
    monkeypatch.setenv("OPENAI_API_KEY", "relay-parent-key")

    prepared = prepare_launch_environment(
        catalog_path,
        secret_store=MemorySecrets(
            {
                "provider:qwen": {"api_key": "stored-qwen-key"},
                "provider:relay": {"api_key": "stored-relay-key"},
            }
        ),
        base_environment={
            "DASHSCOPE_API_KEY": "stale-parent-key",
            "OPENAI_API_KEY": "relay-parent-key",
        },
        required_modules=(),
    )

    assert prepared.environment["DASHSCOPE_API_KEY"] == "stored-qwen-key"
    assert prepared.environment["OPENAI_API_KEY"] == "stored-relay-key"


def test_preflight_injects_nlr_key_only_for_launch_owned_external_data(tmp_path, monkeypatch):
    catalog_path = tmp_path / "model_catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(_catalog()), encoding="utf-8")
    monkeypatch.delenv("NLR_API_KEY", raising=False)

    prepared = prepare_launch_environment(
        catalog_path,
        secret_store=MemorySecrets(
            {
                "provider:qwen": {"api_key": "qwen-secret"},
                "provider:relay": {"api_key": "relay-secret"},
                "api-service:nlr_developer_network": {
                    "enabled": True,
                    "credential": "nlr-secret",
                    "docs_url": "https://developer.nlr.gov/docs/",
                },
            }
        ),
        external_data={
            "api_registry": [
                {
                    "api_id": "nlr_developer_network",
                    "source": "NLR",
                    "description": "Use the official NLR API documentation.",
                    "official_docs_url": "https://developer.nlr.gov/docs/",
                }
            ]
        },
        required_modules=(),
    )

    assert prepared.required_external_data == ("nlr_developer_network",)
    assert prepared.environment["NLR_API_KEY"] == "nlr-secret"
    assert "nlr-secret" not in repr(prepared)


def test_preflight_injects_enabled_paper_service_credentials_for_paper_orchestra(
    tmp_path, monkeypatch
):
    catalog_path = tmp_path / "model_catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(_catalog()), encoding="utf-8")
    for variable in (
        "SEMANTIC_SCHOLAR_API_KEY",
        "S2_API_KEY",
        "ARXIV_EMAIL",
        "CROSSREF_EMAIL",
        "CORE_API_KEY",
    ):
        monkeypatch.delenv(variable, raising=False)

    prepared = prepare_launch_environment(
        catalog_path,
        secret_store=MemorySecrets(
            {
                "provider:qwen": {"api_key": "qwen-secret"},
                "provider:relay": {"api_key": "relay-secret"},
                "api-service:semantic-scholar": {
                    "enabled": True,
                    "credential": "semantic-secret",
                },
                "api-service:arxiv": {
                    "enabled": True,
                    "credential": "research@example.com",
                },
                "api-service:crossref": {
                    "enabled": True,
                    "credential": "crossref@example.com",
                },
                "api-service:core": {
                    "enabled": True,
                    "credential": "core-secret",
                },
                "api-service:nlr_developer_network": {
                    "enabled": True,
                    "credential": "nlr-secret",
                    "docs_url": "https://developer.nlr.gov/docs/",
                },
            }
        ),
        required_modules=(),
    )

    assert prepared.environment["SEMANTIC_SCHOLAR_API_KEY"] == "semantic-secret"
    assert prepared.environment["S2_API_KEY"] == "semantic-secret"
    assert prepared.environment["ARXIV_EMAIL"] == "research@example.com"
    assert prepared.environment["CROSSREF_EMAIL"] == "crossref@example.com"
    assert prepared.environment["CORE_API_KEY"] == "core-secret"
    assert "NLR_API_KEY" not in prepared.environment
    assert "semantic-secret" not in repr(prepared)
    assert "core-secret" not in repr(prepared)


def test_preflight_prefers_stored_paper_service_credentials_over_inherited_environment(
    tmp_path, monkeypatch
):
    catalog_path = tmp_path / "model_catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(_catalog()), encoding="utf-8")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "inherited-secret")
    monkeypatch.setenv("S2_API_KEY", "inherited-alias")

    prepared = prepare_launch_environment(
        catalog_path,
        secret_store=MemorySecrets(
            {
                "provider:qwen": {"api_key": "qwen-secret"},
                "provider:relay": {"api_key": "relay-secret"},
                "api-service:semantic-scholar": {
                    "enabled": True,
                    "credential": "stored-secret",
                },
            }
        ),
        required_modules=(),
    )

    assert prepared.environment["SEMANTIC_SCHOLAR_API_KEY"] == "stored-secret"
    assert prepared.environment["S2_API_KEY"] == "stored-secret"


def test_preflight_reports_missing_nlr_key_without_leaking_snapshot_or_prompt_data(tmp_path, monkeypatch):
    catalog_path = tmp_path / "model_catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(_catalog()), encoding="utf-8")
    monkeypatch.delenv("NLR_API_KEY", raising=False)

    with pytest.raises(DiscoveryRuntimePreflightError, match="nlr_developer_network"):
        prepare_launch_environment(
            catalog_path,
            secret_store=MemorySecrets(
                {
                    "provider:qwen": {"api_key": "qwen-secret"},
                    "provider:relay": {"api_key": "relay-secret"},
                }
            ),
            external_data={
                "api_registry": [
                    {
                        "api_id": "nlr_developer_network",
                        "source": "NLR",
                        "description": "Use the official NLR API documentation.",
                        "official_docs_url": "https://developer.nlr.gov/docs/",
                    }
                ]
            },
            required_modules=(),
        )


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


def _admitted_secrets() -> MemorySecrets:
    return MemorySecrets(
        {
            "provider:qwen": {"api_key": "qwen-secret"},
            "provider:relay": {"api_key": "relay-secret"},
        }
    )


def test_preflight_refuses_a_launch_whose_backend_cli_is_not_on_path(
    tmp_path, monkeypatch
):
    """The only executable step of a Launch must be verified at admission."""
    catalog_path = tmp_path / "model_catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(_catalog()), encoding="utf-8")
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.delenv("QWEN_CODE_BIN", raising=False)

    with pytest.raises(DiscoveryRuntimePreflightError, match="qwen"):
        prepare_launch_environment(
            catalog_path,
            secret_store=_admitted_secrets(),
            required_modules=(),
            exp_backend="qwen_code",
        )


def test_preflight_accepts_a_backend_cli_named_by_its_override_variable(
    tmp_path, monkeypatch
):
    catalog_path = tmp_path / "model_catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(_catalog()), encoding="utf-8")
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.setenv("QWEN_CODE_BIN", sys.executable)

    prepared = prepare_launch_environment(
        catalog_path,
        secret_store=_admitted_secrets(),
        required_modules=(),
        exp_backend="qwen_code",
    )

    assert prepared.required_providers == ("qwen", "relay")


def test_preflight_admits_openhands_without_a_local_executable(tmp_path, monkeypatch):
    """OpenHands is reached over a WebSocket URI, so it owns no local binary."""
    catalog_path = tmp_path / "model_catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(_catalog()), encoding="utf-8")
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))

    prepared = prepare_launch_environment(
        catalog_path,
        secret_store=_admitted_secrets(),
        required_modules=(),
        exp_backend="openhands",
    )

    assert prepared.required_external_data == ()


def test_preflight_rejects_an_undeclared_experiment_backend(tmp_path):
    catalog_path = tmp_path / "model_catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(_catalog()), encoding="utf-8")

    with pytest.raises(DiscoveryRuntimePreflightError, match="not-a-backend"):
        prepare_launch_environment(
            catalog_path,
            secret_store=_admitted_secrets(),
            required_modules=(),
            exp_backend="not-a-backend",
        )


def test_preflight_reports_a_missing_backend_alongside_missing_credentials(
    tmp_path, monkeypatch
):
    """Admission reports every unmet precondition in one verdict."""
    catalog_path = tmp_path / "model_catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(_catalog()), encoding="utf-8")
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_CODE_BIN", raising=False)

    with pytest.raises(DiscoveryRuntimePreflightError) as failure:
        prepare_launch_environment(
            catalog_path,
            secret_store=MemorySecrets(),
            required_modules=(),
            exp_backend="qwen_code",
        )

    message = str(failure.value)
    assert "DASHSCOPE_API_KEY" in message
    assert "OPENAI_API_KEY" in message
    assert "qwen" in message


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
    # The backend CLI is a host fact. Pin it to an executable that always exists
    # so these assertions describe the worker, not this machine's PATH.
    monkeypatch.setenv("CODEX_BIN", sys.executable)
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
    monkeypatch.setenv("CODEX_BIN", sys.executable)
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
