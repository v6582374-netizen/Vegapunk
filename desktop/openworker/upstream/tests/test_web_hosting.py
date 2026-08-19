from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from coworker.providers import AssistantTurn, ModelCapabilities, ProviderClient
from coworker.server import SessionManager, create_app


class _Provider(ProviderClient):
    def complete(self, *, model, messages, tools=None, **settings):
        return AssistantTurn(text="ok", finish_reason="stop")

    def capabilities(self, model):
        return ModelCapabilities()


def test_linux_web_counterpart_serves_desktop_spa_and_cookie_auth(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><head></head><body><div id='root'></div></body></html>",
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("console.log('desktop bundle')", encoding="utf-8")

    monkeypatch.delenv("COWORKER_API_TOKEN", raising=False)
    monkeypatch.setenv("COWORKER_WEB_TOKEN", "web-secret")
    manager = SessionManager(workspace=Path(tmp_path), provider=_Provider())
    client = TestClient(create_app(manager, web_dist=dist, web_enabled=True))

    login_page = client.get("/")
    assert login_page.status_code == 200
    assert "Sign in to Vegapunk" in login_page.text

    denied = client.get("/v1/sessions")
    assert denied.status_code == 401
    assert client.get("/v1/health").json() == {"status": "ok"}

    login = client.post("/web/login", json={"token": "web-secret"})
    assert login.status_code == 200
    assert login.json()["authenticated"] is True

    root = client.get("/settings")
    assert root.status_code == 200
    assert "__OPENWORKER_WEB__" in root.text
    assert client.get("/assets/app.js").text == "console.log('desktop bundle')"
    assert client.get("/v1/sessions").status_code == 200

    # Same-origin cookies authenticate WebSockets too, so the browser does not need the
    # desktop sidecar token as a JavaScript-visible value.
    with client.websocket_connect("/ws/session/web", headers={"Origin": "http://testserver"}) as ws:
        assert ws.receive_json()["type"] == "ready"
