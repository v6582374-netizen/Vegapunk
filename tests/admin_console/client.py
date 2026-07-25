from __future__ import annotations

from fastapi.testclient import TestClient as FastAPITestClient


class TestClient(FastAPITestClient):
    """Test client for the local, unauthenticated workspace API."""
