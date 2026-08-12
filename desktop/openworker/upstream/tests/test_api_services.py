"""API Services settings boundary tests."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient

from coworker import api_services
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


def test_api_services_exposes_only_the_fixed_external_data_catalog(tmp_path):
    _, client = _client(tmp_path)

    response = client.get("/v1/settings/api-services")

    assert response.status_code == 200
    services = response.json()["services"]
    assert [service["name"] for service in services] == [
        "arxiv",
        "semantic-scholar",
        "crossref",
        "core",
        "nlr_developer_network",
    ]
    assert services[0]["endpoint"] == "https://export.arxiv.org/api/query"
    assert services[1]["endpoint"] == "https://api.semanticscholar.org/graph/v1"
    assert services[2]["endpoint"] == "https://api.crossref.org/works"
    assert services[3]["endpoint"] == "https://api.core.ac.uk/v3/search/works"
    assert services[4]["title"] == "NLR"
    assert services[4]["endpoint"] is None
    assert services[4]["docs_url"] == "https://developer.nlr.gov/docs/"
    assert services[4]["docs_url_editable"] is True
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


def test_core_probe_uses_canonical_trailing_slash_endpoint(tmp_path, monkeypatch):
    _, client = _client(tmp_path)

    def fake_get(url, *, headers=None, params=None, timeout=None):
        assert url == "https://api.core.ac.uk/v3/search/works/?q=test&page=1&pageSize=1"
        assert headers["Authorization"] == "Bearer core-key"
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr("coworker.api_services.httpx.get", fake_get)

    response = client.post(
        "/v1/settings/api-services/core/test",
        json={"credential": "core-key"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["status"] == "connected"
    assert "core-key" not in response.text


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


def test_nlr_saves_api_key_and_documentation_url_without_exposing_the_key(tmp_path):
    manager, client = _client(tmp_path)

    response = client.post(
        "/v1/settings/api-services/nlr_developer_network",
        json={
            "enabled": True,
            "credential": "nlr-secret",
            "docs_url": "https://docs.example.test/nlr",
        },
    )

    assert response.status_code == 200
    assert response.json()["service"]["docs_url"] == "https://docs.example.test/nlr"
    assert "nlr-secret" not in response.text
    stored = manager.secrets.get("api-service:nlr_developer_network")
    assert stored == {
        "enabled": True,
        "credential": "nlr-secret",
        "docs_url": "https://docs.example.test/nlr",
    }
    assert manager.external_data_snapshot() == {
        "api_registry": [
            {
                "api_id": "nlr_developer_network",
                "source": "NLR",
                "description": (
                    "Use the official NLR API documentation to select the endpoint and "
                    "fields needed for the research question; the configured API key is "
                    "available as NLR_API_KEY in this run's environment; never print "
                    "the credential or copy it into an artifact."
                ),
                "official_docs_url": "https://docs.example.test/nlr",
            }
        ],
        "provider_status": {"nlr_developer_network": "not_tested"},
    }


def test_nlr_test_validates_configuration_without_a_fixed_endpoint(tmp_path):
    _, client = _client(tmp_path)

    response = client.post(
        "/v1/settings/api-services/nlr_developer_network/test",
        json={"credential": "nlr-secret", "docs_url": "https://docs.example.test/nlr"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["status"] == "connected"
    assert "nlr-secret" not in response.text


def test_nlr_rejects_non_http_documentation_address(tmp_path):
    _, client = _client(tmp_path)

    response = client.post(
        "/v1/settings/api-services/nlr_developer_network",
        json={"enabled": True, "credential": "nlr-secret", "docs_url": "file:///tmp/docs"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "HTTP(S)" in response.json()["error"]


def test_semantic_scholar_test_spaces_requests_for_the_same_key(tmp_path, monkeypatch):
    _, client = _client(tmp_path)
    sleeps = []
    calls = []
    monkeypatch.setattr(api_services, "_semantic_scholar_next_request_at", {})
    monkeypatch.setattr(api_services.time, "sleep", sleeps.append)

    def fake_get(url, *, headers=None, params=None, timeout=None):
        calls.append((url, headers, timeout))
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr("coworker.api_services.httpx.get", fake_get)

    first = client.post(
        "/v1/settings/api-services/semantic-scholar/test",
        json={"credential": "test-key"},
    )
    second = client.post(
        "/v1/settings/api-services/semantic-scholar/test",
        json={"credential": "test-key"},
    )

    assert first.json()["status"] == "connected"
    assert second.json()["status"] == "connected"
    assert len(calls) == 2
    assert len(sleeps) == 1
    assert 1.0 <= sleeps[0] <= 1.1


def test_semantic_scholar_test_retries_one_rate_limited_probe(tmp_path, monkeypatch):
    _, client = _client(tmp_path)
    sleeps = []
    monkeypatch.setattr(api_services, "_semantic_scholar_next_request_at", {})
    monkeypatch.setattr(api_services.time, "sleep", sleeps.append)

    request = httpx.Request(
        "GET", "https://api.semanticscholar.org/graph/v1/paper/search?query=transformer&limit=1"
    )
    responses = [
        httpx.Response(429, request=request),
        httpx.Response(200, request=request),
    ]

    monkeypatch.setattr(
        "coworker.api_services.httpx.get",
        lambda url, *, headers=None, params=None, timeout=None: responses.pop(0),
    )

    response = client.post(
        "/v1/settings/api-services/semantic-scholar/test",
        json={"credential": "test-key"},
    )

    assert response.json()["status"] == "connected"
    assert responses == []
    assert len(sleeps) == 1
    assert 1.0 <= sleeps[0] <= 1.1


def test_semantic_scholar_test_reports_a_rate_limit_explicitly(tmp_path, monkeypatch):
    _, client = _client(tmp_path)
    monkeypatch.setattr(api_services, "_semantic_scholar_next_request_at", {})
    monkeypatch.setattr(api_services.time, "sleep", lambda _: None)
    request = httpx.Request(
        "GET", "https://api.semanticscholar.org/graph/v1/paper/search?query=transformer&limit=1"
    )
    monkeypatch.setattr(
        "coworker.api_services.httpx.get",
        lambda url, *, headers=None, params=None, timeout=None: httpx.Response(429, request=request),
    )

    response = client.post(
        "/v1/settings/api-services/semantic-scholar/test",
        json={"credential": "test-key"},
    )

    assert response.json()["status"] == "error"
    assert response.json()["error"] == "Semantic Scholar rate limited this API key. Wait one second and try again."
