from __future__ import annotations

from fastapi.testclient import TestClient as FastAPITestClient


class TestClient(FastAPITestClient):
    """Test client that authenticates once for protected Admin Console tests."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        response = super().post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        if response.status_code != 200:
            raise AssertionError(f"test administrator login failed: {response.text}")
