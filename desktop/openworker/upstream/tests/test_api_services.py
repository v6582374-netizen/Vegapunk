"""API Services settings boundary tests."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from coworker.providers import AssistantTurn, ModelCapabilities, ProviderClient
from coworker.server import SessionManager, create_app


class ScriptedProvider(ProviderClient):
    def __init__(self) -> None:
        self._turns = []

    def complete(self, *, model, messages, tools=None, **settings):
        return AssistantTurn(text="ok", finish_reason="stop")

    def capabilities(self, model):
        return ModelCapabilities()


def _client(tmp_path):
    manager = SessionManager(workspace=tmp_path, provider=ScriptedProvider())
    return manager, TestClient(create_app(manager))


def test_api_services_exposes_only_the_fixed_paper_service_catalog(tmp_path):
    _, client = _client(tmp_path)

    response = client.get("/v1/settings/api-services")

    assert response.status_code == 200
    services = response.json()["services"]
    assert [service["name"] for service in services] == [
        "arxiv",
        "semantic-scholar",
        "crossref",
        "core",
    ]
    assert services[0]["endpoint"] == "https://export.arxiv.org/api/query"
    assert services[1]["endpoint"] == "https://api.semanticscholar.org/graph/v1"
    assert services[2]["endpoint"] == "https://api.crossref.org/works"
    assert services[3]["endpoint"] == "https://api.core.ac.uk/v3/search/works"
    assert all("credential" not in service for service in services)


def test_api_service_save_is_independent_and_does_not_change_discovery_settings(tmp_path):
    manager, client = _client(tmp_path)
    before = manager.discovery_model_settings()

    response = client.post(
        "/v1/settings/api-services/crossref",
        json={"enabled": True, "credential": "research@example.com"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["service"]["name"] == "crossref"
    assert body["service"]["enabled"] is True
    assert body["service"]["credential_configured"] is True
    assert "research@example.com" not in response.text
    assert manager.discovery_model_settings() == before


def test_api_service_test_reports_connection_and_redacts_credential(tmp_path, monkeypatch):
    _, client = _client(tmp_path)

    def fake_get(url, *, headers=None, params=None, timeout=None):
        assert url == "https://api.crossref.org/works"
        assert headers["User-Agent"].startswith("Vegapunk/")
        assert "research@example.com" in headers["User-Agent"]
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr("coworker.api_services.httpx.get", fake_get)

    response = client.post(
        "/v1/settings/api-services/crossref/test",
        json={"credential": "research@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["status"] == "connected"
    assert "research@example.com" not in response.text


def test_api_service_requires_a_credential_for_core(tmp_path):
    _, client = _client(tmp_path)

    response = client.post("/v1/settings/api-services/core/test", json={})

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "status": "not_configured",
        "error": "Enter an API key to test CORE.",
    }


def test_optional_service_can_remain_connected_without_a_credential(tmp_path, monkeypatch):
    _, client = _client(tmp_path)

    monkeypatch.setattr(
        "coworker.api_services.httpx.get",
        lambda url, *, headers=None, params=None, timeout=None: SimpleNamespace(
            status_code=200, raise_for_status=lambda: None
        ),
    )

    response = client.post("/v1/settings/api-services/crossref/test", json={})
    assert response.json()["status"] == "connected"
    assert client.get("/v1/settings/api-services").json()["services"][2]["status"] == "connected"
