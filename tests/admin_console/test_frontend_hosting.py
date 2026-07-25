from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from admin_console.app import create_app


class FrontendHostingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.dist = root / "dist"
        (self.dist / "assets").mkdir(parents=True)
        (self.dist / "index.html").write_text("<html><body>unified frontend</body></html>")
        (self.dist / "assets" / "app.js").write_text("console.log('ok')")
        self.client = TestClient(
            create_app(
                results_root=root / "results",
                tasks_root=root / "tasks",
                frontend_dist=self.dist,
            )
        )

    def test_frontend_routes_fall_back_to_the_single_spa_entry(self) -> None:
        root = self.client.get("/")
        nested = self.client.get("/research/new")

        self.assertEqual(root.status_code, 200)
        self.assertEqual(nested.status_code, 200)
        self.assertEqual(root.text, nested.text)

    def test_frontend_assets_are_served_without_shadowing_api_routes(self) -> None:
        asset = self.client.get("/assets/app.js")
        api = self.client.get("/api/admin/launches")

        self.assertEqual(asset.status_code, 200)
        self.assertIn("console.log", asset.text)
        self.assertEqual(api.status_code, 200)
        self.assertEqual(api.json(), {"launches": []})


if __name__ == "__main__":
    unittest.main()
