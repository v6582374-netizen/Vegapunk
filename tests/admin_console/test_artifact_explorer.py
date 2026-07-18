from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from admin_console.app import create_app


class ArtifactExplorerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.results_root = Path(self._tmp.name)
        launch = self.results_root / "AutoDemo" / "20260718_000000_launch"
        (launch / "session_1" / "ideas").mkdir(parents=True)
        (launch / "session_1" / "ideas" / "ideas.json").write_text('{"ideas": []}')
        (launch / "console.log").write_text("line one\nline two\n")
        (launch / "figure.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
        self.client = TestClient(create_app(results_root=self.results_root))
        self.launch_id = "AutoDemo/20260718_000000_launch"

    def test_tree_lists_every_file_and_directory(self) -> None:
        response = self.client.get(f"/api/artifacts/{self.launch_id}/tree")
        self.assertEqual(response.status_code, 200)
        tree = response.json()["tree"]
        names = {node["path"] for node in _flatten(tree)}
        self.assertEqual(
            names,
            {
                "console.log",
                "figure.png",
                "session_1",
                "session_1/ideas",
                "session_1/ideas/ideas.json",
            },
        )

    def test_text_file_content_is_returned_with_kind(self) -> None:
        response = self.client.get(
            f"/api/artifacts/{self.launch_id}/file", params={"path": "console.log"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("line one", response.text)

    def test_binary_file_is_served_with_content_type(self) -> None:
        response = self.client.get(
            f"/api/artifacts/{self.launch_id}/file", params={"path": "figure.png"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG"))

    def test_path_traversal_is_rejected(self) -> None:
        secret = self.results_root / "secret.txt"
        secret.write_text("do not leak")
        response = self.client.get(
            f"/api/artifacts/{self.launch_id}/file", params={"path": "../../secret.txt"}
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_launch_returns_404(self) -> None:
        response = self.client.get("/api/artifacts/NoTask/20990101_000000_launch/tree")
        self.assertEqual(response.status_code, 404)


def _flatten(nodes: list[dict]) -> list[dict]:
    result = []
    for node in nodes:
        result.append(node)
        result.extend(_flatten(node.get("children", [])))
    return result


if __name__ == "__main__":
    unittest.main()
