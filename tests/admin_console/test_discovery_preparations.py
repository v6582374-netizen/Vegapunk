from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from admin_console.app import create_app
from tests.admin_console.client import TestClient


class DiscoveryPreparationApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.results_root = root / "results"
        self.results_root.mkdir()
        config = root / "default_config.yaml"
        config.write_text("system: {}\n")
        self.config_paths = [config]
        self.client = self._new_client()

    def _new_client(self) -> TestClient:
        return TestClient(
            create_app(
                results_root=self.results_root,
                config_paths=self.config_paths,
                runner_command=["echo"],
            )
        )

    def test_text_preparation_can_be_retrieved_after_recreating_the_app(self) -> None:
        response = self.client.post(
            "/api/workspace/discovery-preparations",
            data={"research_text": "Why do these materials self-assemble?"},
        )

        self.assertEqual(response.status_code, 201)
        preparation_id = response.json()["id"]

        recreated_client = self._new_client()
        list_response = recreated_client.get("/api/workspace/discovery-preparations")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual([item["id"] for item in list_response.json()["preparations"]], [preparation_id])

        detail_response = recreated_client.get(
            f"/api/workspace/discovery-preparations/{preparation_id}"
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(
            detail_response.json()["research_text"],
            "Why do these materials self-assemble?",
        )
        self.assertEqual(detail_response.json()["sources"], [])

    def test_accepts_each_supported_source_type_and_lists_the_sources(self) -> None:
        files = [
            ("sources", ("notes.txt", io.BytesIO(b"notes"), "text/plain")),
            ("sources", ("hypothesis.md", io.BytesIO(b"# Hypothesis"), "text/markdown")),
            ("sources", ("paper.pdf", io.BytesIO(b"%PDF-1.7"), "application/pdf")),
            (
                "sources",
                (
                    "observations.docx",
                    io.BytesIO(b"docx bytes"),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            ),
            ("sources", ("measurements.csv", io.BytesIO(b"x,y\n1,2\n"), "text/csv")),
            ("sources", ("baseline.zip", io.BytesIO(b"PK\x03\x04"), "application/zip")),
        ]

        response = self.client.post(
            "/api/workspace/discovery-preparations",
            data={"research_text": "Investigate the provided evidence."},
            files=files,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            [source["name"] for source in response.json()["sources"]],
            [
                "notes.txt",
                "hypothesis.md",
                "paper.pdf",
                "observations.docx",
                "measurements.csv",
                "baseline.zip",
            ],
        )
        self.assertEqual(response.json()["sources"][-1]["kind"], "baseline_code")

    def test_rejects_an_unsupported_source_without_creating_a_preparation(self) -> None:
        response = self.client.post(
            "/api/workspace/discovery-preparations",
            data={"research_text": "Do not save this."},
            files={"sources": ("unknown.exe", io.BytesIO(b"binary"), "application/octet-stream")},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("unsupported source type: unknown.exe", response.json()["detail"])
        self.assertEqual(
            self.client.get("/api/workspace/discovery-preparations").json()["preparations"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
