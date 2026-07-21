from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from admin_console.auth import AdminAuth
from admin_console.app import create_app


class AdminAuthenticationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.client = TestClient(
            create_app(
                results_root=root / "results",
                tasks_root=root / "tasks",
                auth_db_path=root / "admin-auth.sqlite3",
            )
        )

    def test_admin_routes_require_an_authenticated_session(self) -> None:
        response = self.client.get("/api/admin/launches")

        self.assertEqual(response.status_code, 401)

    def test_default_admin_credentials_create_a_session(self) -> None:
        login = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )

        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.json()["authenticated"])
        self.assertIn("vegapunk_admin_session", self.client.cookies)
        self.assertEqual(self.client.get("/api/auth/me").json(), {
            "authenticated": True,
            "username": "admin",
        })
        self.assertEqual(self.client.get("/api/admin/launches").status_code, 200)

    def test_invalid_credentials_do_not_create_a_session(self) -> None:
        response = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("vegapunk_admin_session", self.client.cookies)
        self.assertEqual(self.client.get("/api/auth/me").json(), {"authenticated": False})

    def test_logout_revokes_the_current_session(self) -> None:
        self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )

        logout = self.client.post("/api/auth/logout")

        self.assertEqual(logout.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").json(), {"authenticated": False})
        self.assertEqual(self.client.get("/api/admin/launches").status_code, 401)

    def test_legacy_unprotected_admin_route_is_not_available(self) -> None:
        response = self.client.get("/api/launches")

        self.assertEqual(response.status_code, 404)

    def test_untrusted_hosts_are_rejected(self) -> None:
        response = self.client.get("/api/auth/me", headers={"host": "evil.example"})

        self.assertEqual(response.status_code, 400)

    def test_cross_origin_state_changes_are_rejected(self) -> None:
        response = self.client.post(
            "/api/auth/login",
            headers={"origin": "http://evil.example"},
            json={"username": "admin", "password": "admin"},
        )

        self.assertEqual(response.status_code, 403)

    def test_idle_sessions_expire_and_are_removed(self) -> None:
        root = Path(self._tmp.name)
        now = [100.0]
        auth = AdminAuth(
            root / "clock-auth.sqlite3",
            clock=lambda: now[0],
            idle_seconds=10,
            absolute_seconds=100,
        )
        token = auth.login("admin", "admin")
        self.assertIsNotNone(token)

        now[0] = 111.0

        self.assertIsNone(auth.session_username(token))
        self.assertIsNone(auth.session_username(token))


if __name__ == "__main__":
    unittest.main()
