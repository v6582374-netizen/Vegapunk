"""Additional public intake validation for Native Desktop Discovery."""

from __future__ import annotations

from fastapi.testclient import TestClient

from coworker.server import SessionManager, create_app

TOKEN = "a" * 64


def _client(state_root) -> TestClient:
    return TestClient(create_app(SessionManager(data_dir=state_root)))


def _headers() -> dict[str, str]:
    return {"X-OpenWorker-Token": TOKEN}


def test_empty_text_is_not_an_intake_without_a_source(tmp_path, monkeypatch):
    monkeypatch.setenv("COWORKER_API_TOKEN", TOKEN)
    client = _client(tmp_path / "state")

    response = client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": "   ", "files": []},
    )

    assert response.status_code == 422
    assert "text or at least one file" in response.json()["detail"]
    preparation = client.get("/v1/discovery", headers=_headers()).json()["preparation"]
    assert preparation["draft"] == {"text": "", "sources": []}
    assert preparation["saved"] == {"text": "", "sources": []}
