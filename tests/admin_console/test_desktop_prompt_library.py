from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tests.admin_console.client import TestClient
from admin_console.app import create_app
from vegapunk.prompt_library import DEFAULT_LIBRARY_ROOT


class DesktopPromptLibraryApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.prompt_root = root / "prompts"
        shutil.copytree(DEFAULT_LIBRARY_ROOT, self.prompt_root)
        self.baseline_root = root / "baseline"
        shutil.copytree(DEFAULT_LIBRARY_ROOT, self.baseline_root)
        self.client = TestClient(
            create_app(
                prompt_library_root=self.prompt_root,
                prompt_baseline_root=self.baseline_root,
            )
        )

    def test_health_reports_version_and_ready(self) -> None:
        response = self.client.get("/api/prompt-library/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"api_version": "v1", "status": "ready"})

    def test_catalogue_hides_storage_and_mirror_details(self) -> None:
        response = self.client.get("/api/prompt-library/v1/prompts")
        self.assertEqual(response.status_code, 200)
        prompt = next(
            item
            for item in response.json()["prompts"]
            if item["id"] == "discovery.generation.system"
        )
        self.assertIn("text", prompt)
        self.assertIn("source_revision", prompt)
        self.assertNotIn("file", prompt)
        self.assertNotIn("chinese_mirror", prompt)

    def test_tauri_dev_origin_can_read_and_preflight_saves(self) -> None:
        for origin in ("http://localhost:1420", "http://127.0.0.1:1420"):
            with self.subTest(origin=origin):
                catalogue = self.client.get(
                    "/api/prompt-library/v1/prompts",
                    headers={"Origin": origin},
                )
                self.assertEqual(catalogue.status_code, 200)
                self.assertEqual(catalogue.headers["access-control-allow-origin"], origin)

                preflight = self.client.options(
                    "/api/prompt-library/v1/prompts/discovery.generation.system",
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "PUT",
                        "Access-Control-Request-Headers": "content-type",
                    },
                )
                self.assertEqual(preflight.status_code, 200)
                self.assertEqual(preflight.headers["access-control-allow-origin"], origin)
                self.assertIn("PUT", preflight.headers["access-control-allow-methods"])

    def test_untrusted_origin_cannot_access_prompt_library(self) -> None:
        response = self.client.get(
            "/api/prompt-library/v1/prompts",
            headers={"Origin": "https://example.com"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["message"], "origin not allowed")

    def test_detail_distinguishes_active_and_system_original(self) -> None:
        response = self.client.get(
            "/api/prompt-library/v1/prompts/discovery.generation.system"
        )
        self.assertEqual(response.status_code, 200)
        prompt = response.json()["prompt"]
        self.assertEqual(prompt["text"], prompt["system_original_text"])
        self.assertIn("{tone}", prompt["system_original_text"])

    def test_unknown_prompt_uses_stable_error(self) -> None:
        response = self.client.get("/api/prompt-library/v1/prompts/missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "prompt_not_found")

    def test_invalid_save_preserves_active_source(self) -> None:
        path = self.prompt_root / "discovery" / "generation_system.txt"
        original = path.read_text()
        response = self.client.put(
            "/api/prompt-library/v1/prompts/discovery.generation.system",
            json={"text": original.replace("{tone}", "focused")},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "invalid_prompt")
        self.assertEqual(path.read_text(), original)

    def test_successful_save_returns_new_active_revision(self) -> None:
        original = self.client.get(
            "/api/prompt-library/v1/prompts/experiment.coder_openhands"
        ).json()["prompt"]["text"]
        updated = original + "\nDESKTOP_API_MARKER\n"
        response = self.client.put(
            "/api/prompt-library/v1/prompts/experiment.coder_openhands",
            json={"text": updated},
        )
        self.assertEqual(response.status_code, 200)
        prompt = response.json()["prompt"]
        self.assertEqual(prompt["text"], updated)
        self.assertNotEqual(prompt["source_revision"], "")


if __name__ == "__main__":
    unittest.main()
