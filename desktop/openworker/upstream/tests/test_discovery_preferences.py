"""Discovery Launch preference contract and snapshot tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coworker.server import SessionManager, create_app
from coworker.server import discovery_preferences as preferences_module
from coworker.server.discovery_preferences import (
    DEFAULT_DISCOVERY_LAUNCH_PREFERENCES,
    DiscoveryLaunchPreferences,
    DiscoveryPreferencesValidationError,
)
from coworker.server.discovery_launch import DiscoveryLaunchStore


def test_defaults_are_complete_and_round_trip(tmp_path):
    path = tmp_path / "discovery-launch.json"
    preferences = DiscoveryLaunchPreferences(path)

    assert preferences.get() == DEFAULT_DISCOVERY_LAUNCH_PREFERENCES
    saved = preferences.save({"values": {"workflow": {"loop_rounds": 12}}})
    assert saved["values"]["workflow"]["loop_rounds"] == 12
    assert saved["values"]["workflow"]["loop_mode"] == "incremental"
    assert DiscoveryLaunchPreferences(path).get()["workflow"]["loop_rounds"] == 12


@pytest.mark.parametrize(
    ("patch", "path"),
    [
        ({"workflow": {"loop_rounds": "10"}}, "workflow.loop_rounds"),
        ({"workflow": {"loop_mode": "adaptive"}}, "workflow.loop_mode"),
        ({"agents": {"generation": {"creativity": 2}}}, "agents.generation.creativity"),
        ({"agents": {"ranking": {"criteria": {"novelty": 0.5}}}}, "agents.ranking.criteria"),
    ],
)
def test_invalid_types_enums_and_ranking_are_rejected_without_mutation(tmp_path, patch, path):
    preferences = DiscoveryLaunchPreferences(tmp_path / "discovery-launch.json")
    before = preferences.get()

    with pytest.raises(DiscoveryPreferencesValidationError) as raised:
        preferences.save({"values": patch})

    assert any(item["path"] == path for item in raised.value.violations)
    assert preferences.get() == before
    assert not (tmp_path / "discovery-launch.json").exists()


def test_unknown_fields_are_rejected_and_atomic_replace_preserves_old_value(tmp_path, monkeypatch):
    path = tmp_path / "discovery-launch.json"
    preferences = DiscoveryLaunchPreferences(path)
    preferences.save({"values": {"workflow": {"loop_rounds": 11}}})
    before = json.loads(path.read_text(encoding="utf-8"))

    with pytest.raises(DiscoveryPreferencesValidationError):
        preferences.save({"values": {"workflow": {"not_a_setting": 1}}})

    original_replace = preferences_module.os.replace

    def fail_replace(source, destination):
        if Path(destination) == path:
            raise OSError("simulated storage failure")
        return original_replace(source, destination)

    monkeypatch.setattr(preferences_module.os, "replace", fail_replace)
    with pytest.raises(OSError):
        preferences.save({"values": {"workflow": {"loop_rounds": 13}}})

    assert preferences.get()["workflow"]["loop_rounds"] == 11
    assert json.loads(path.read_text(encoding="utf-8")) == before


def test_settings_endpoint_returns_schema_and_rejects_invalid_save(tmp_path):
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "data")))

    response = client.get("/v1/settings/discovery-launch")
    assert response.status_code == 200
    document = response.json()
    assert document["values"] == document["defaults"]
    assert document["parameters"]["workflow.loop_rounds"]["type"] == "integer"

    saved = client.put(
        "/v1/settings/discovery-launch",
        json={"values": {"workflow": {"loop_rounds": 8}}},
    )
    assert saved.status_code == 200
    assert saved.json()["ok"] is True
    assert saved.json()["values"]["workflow"]["loop_rounds"] == 8

    rejected = client.put(
        "/v1/settings/discovery-launch",
        json={"values": {"workflow": {"loop_rounds": 0}}},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["violations"][0]["path"] == "workflow.loop_rounds"
    assert client.get("/v1/settings").json()["discovery_launch_preferences"]["values"]["workflow"]["loop_rounds"] == 8


def test_backend_is_a_top_level_closed_setting(tmp_path):
    preferences = DiscoveryLaunchPreferences(tmp_path / "discovery-launch.json")
    assert preferences.get()["backend"] == "codex"
    assert preferences.document()["parameters"]["backend"]["values"] == [
        "codex",
        "qwen_code",
        "openhands",
    ]

    preferences.save({"values": {"backend": "qwen_code"}})
    assert preferences.snapshot()["backend"] == "qwen_code"

    with pytest.raises(DiscoveryPreferencesValidationError) as raised:
        preferences.save({"values": {"backend": "legacy_backend"}})
    assert any(item["path"] == "backend" for item in raised.value.violations)


def test_launch_configuration_captures_old_preferences_after_later_edit(tmp_path):
    preferences = DiscoveryLaunchPreferences(tmp_path / "discovery-launch.json")
    old_snapshot = preferences.snapshot()
    store = DiscoveryLaunchStore(tmp_path / "discovery")
    result = store.admit(
        request_fingerprint="fingerprint",
        idempotency_key="launch-1",
        input_snapshot={"preparation_id": "preparation", "revision_id": "revision-1"},
        configuration_snapshot={
            "model_id": "relay/test-model",
            "settings": {},
            "discovery_launch_preferences": old_snapshot,
        },
        response_builder=lambda: {},
    )

    preferences.save({"values": {"workflow": {"loop_rounds": 99}}})
    launch_dir = tmp_path / "discovery" / "launches" / result["launch_id"]
    persisted = json.loads(
        (launch_dir / "launch_configuration.json").read_text(encoding="utf-8")
    )
    assert persisted["discovery_launch_preferences"] == old_snapshot
