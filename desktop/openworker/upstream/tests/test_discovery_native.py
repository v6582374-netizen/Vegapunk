"""Native Desktop Discovery route contract tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from coworker.server import SessionManager, create_app


def test_discovery_facade_is_registered_on_the_existing_authenticated_sidecar(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("COWORKER_API_TOKEN", "a" * 64)
    manager = SessionManager(workspace=tmp_path)
    app = create_app(manager)
    client = TestClient(app)

    # Discovery is a route on the same app object, not a second service.
    assert app.state.manager is manager
    assert sum(route.path == "/v1/discovery" for route in app.routes) == 1
    assert client.get("/v1/discovery").status_code == 401

    response = client.get(
        "/v1/discovery", headers={"X-OpenWorker-Token": "a" * 64}
    )
    assert response.status_code == 200
    assert response.json() == {
        "module": "discovery",
        "schema_version": 1,
        "contexts": [
            {
                "id": "preparation",
                "label": "Preparation",
                "description": "Gather and review research inputs before a launch.",
            },
            {
                "id": "launch",
                "label": "Current Launch",
                "description": "Observe the active Discovery launch.",
            },
            {
                "id": "history",
                "label": "History",
                "description": "Review completed and interrupted Discovery launches.",
            },
        ],
        "active_context": "preparation",
        "preparation": {"status": "empty"},
        "current_launch": None,
        "history": [],
    }

    # The native facade must not redirect callers back to Web-only route families.
    assert client.get(
        "/api/workspace/discovery", headers={"X-OpenWorker-Token": "a" * 64}
    ).status_code == 404
    assert client.get(
        "/api/admin/discovery", headers={"X-OpenWorker-Token": "a" * 64}
    ).status_code == 404
