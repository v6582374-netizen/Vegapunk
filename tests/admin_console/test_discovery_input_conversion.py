from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from admin_console.app import create_app
from admin_console.discovery_conversion import ConversionResult, DiscoveryConfigurationError
from tests.admin_console.client import TestClient


class RecordingDiscoveryInputConverter:
    def __init__(self) -> None:
        self.requests = []

    def convert(self, request):
        self.requests.append(request)
        return ConversionResult(
            formatted_input="# Formatted Discovery Input\n\nInvestigate the observed transition.",
            model_id="relay/test",
        )


class ConfigurationFailingDiscoveryInputConverter:
    def convert(self, _request):
        raise DiscoveryConfigurationError("default text model unavailable")


class DiscoveryInputConversionApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.results_root = root / "results"
        self.results_root.mkdir()
        self.prompt_path = root / "discovery_input_conversion_prompt.yaml"
        self.converter = RecordingDiscoveryInputConverter()
        self.client = self._new_client()

    def _new_client(self) -> TestClient:
        return TestClient(
            create_app(
                results_root=self.results_root,
                runner_command=["echo"],
                discovery_input_conversion_prompt_path=self.prompt_path,
                discovery_input_converter=self.converter,
            )
        )

    def _create_preparation(self) -> str:
        response = self.client.post(
            "/api/workspace/discovery-preparations",
            data={"research_text": "What controls the observed transition?"},
            files={"sources": ("observations.txt", io.BytesIO(b"Transition at 45 C."), "text/plain")},
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def test_conversion_uses_configured_prompt_without_saving_a_revision(self) -> None:
        self.client.put(
            "/api/admin/discovery-input-conversion-prompt",
            json={"instruction": "Turn the source into a concise Discovery-ready brief."},
        )
        preparation_id = self._create_preparation()

        converted = self.client.post(
            f"/api/workspace/discovery-preparations/{preparation_id}/conversion"
        )

        self.assertEqual(converted.status_code, 200)
        self.assertEqual(converted.json()["preparation_id"], preparation_id)
        self.assertEqual(converted.json()["model_id"], "relay/test")
        self.assertIn("Formatted Discovery Input", converted.json()["formatted_input"])
        self.assertEqual(
            self.converter.requests[0].instruction,
            "Turn the source into a concise Discovery-ready brief.",
        )
        self.assertEqual(self.converter.requests[0].sources[0].name, "observations.txt")
        self.assertEqual(self.converter.requests[0].sources[0].content, "Transition at 45 C.")

        saved = self.client.get(
            f"/api/workspace/discovery-preparations/{preparation_id}"
        ).json()
        self.assertEqual(saved["revisions"], [])
        self.assertEqual(self.client.get("/api/admin/queue").json()["entries"], [])

    def test_explicit_save_creates_a_revision_that_survives_restart(self) -> None:
        preparation_id = self._create_preparation()

        saved = self.client.post(
            f"/api/workspace/discovery-preparations/{preparation_id}/revisions",
            json={"formatted_input": "# Revised Discovery Input\n\nRun the comparison."},
        )

        self.assertEqual(saved.status_code, 201)
        revision_id = saved.json()["id"]

        restarted = self._new_client().get(
            f"/api/workspace/discovery-preparations/{preparation_id}"
        )
        self.assertEqual(restarted.status_code, 200)
        self.assertEqual(
            restarted.json()["revisions"],
            [
                {
                    "id": revision_id,
                    "created_at": saved.json()["created_at"],
                    "formatted_input": "# Revised Discovery Input\n\nRun the comparison.",
                }
            ],
        )

    def test_preparation_research_text_can_be_updated_without_touching_revisions(self) -> None:
        preparation_id = self._create_preparation()
        revision = self.client.post(
            f"/api/workspace/discovery-preparations/{preparation_id}/revisions",
            json={"formatted_input": "Keep this Launch input stable."},
        ).json()

        updated = self.client.put(
            f"/api/workspace/discovery-preparations/{preparation_id}",
            json={"research_text": "A later observation for the next Launch."},
        )

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["research_text"], "A later observation for the next Launch.")
        self.assertEqual(updated.json()["revisions"][0]["id"], revision["id"])

    def test_conversion_requires_a_configured_discovery_input_prompt(self) -> None:
        preparation_id = self._create_preparation()

        response = self.client.post(
            f"/api/workspace/discovery-preparations/{preparation_id}/conversion"
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("Discovery Input Conversion Prompt is not configured", response.json()["detail"])

    def test_conversion_surfaces_a_model_settings_failure_without_launching(self) -> None:
        self.client = TestClient(
            create_app(
                results_root=self.results_root,
                runner_command=["echo"],
                discovery_input_conversion_prompt_path=self.prompt_path,
                discovery_input_converter=ConfigurationFailingDiscoveryInputConverter(),
            )
        )
        self.client.put(
            "/api/admin/discovery-input-conversion-prompt",
            json={"instruction": "Format the input."},
        )
        preparation_id = self._create_preparation()

        response = self.client.post(
            f"/api/workspace/discovery-preparations/{preparation_id}/conversion"
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("default text model unavailable", response.json()["detail"])
        self.assertEqual(self.client.get("/api/admin/queue").json()["entries"], [])

    def test_conversion_surfaces_a_malformed_conversion_prompt_as_settings_error(self) -> None:
        self.prompt_path.write_text("instruction: [broken\n", encoding="utf-8")
        preparation_id = self._create_preparation()

        response = self.client.post(
            f"/api/workspace/discovery-preparations/{preparation_id}/conversion"
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("Discovery Input Conversion Prompt", response.json()["detail"])

    def test_conversion_rejects_invalid_utf8_with_the_source_name(self) -> None:
        self.client.put(
            "/api/admin/discovery-input-conversion-prompt",
            json={"instruction": "Format the input."},
        )
        preparation = self.client.post(
            "/api/workspace/discovery-preparations",
            data={"research_text": "Inspect this source."},
            files={"sources": ("broken.txt", io.BytesIO(b"\xff\xfe"), "text/plain")},
        ).json()

        response = self.client.post(
            f"/api/workspace/discovery-preparations/{preparation['id']}/conversion"
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("broken.txt", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
