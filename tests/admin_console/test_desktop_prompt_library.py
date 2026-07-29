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
                frontend_dist=root / "missing-frontend",
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
