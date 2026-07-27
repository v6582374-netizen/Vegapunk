from __future__ import annotations

import io
import json
import tempfile
import time
import unittest
from pathlib import Path

from admin_console.app import create_app
from tests.admin_console.client import TestClient


class WorkspaceDiscoveryApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.results_root = root / "results"
        self.results_root.mkdir()
        self.tasks_root = root / "tasks"
        self.tasks_root.mkdir()
        config = root / "default_config.yaml"
        config.write_text("system: {}\n")
        self.client = TestClient(
            create_app(
                results_root=self.results_root,
                tasks_root=self.tasks_root,
                config_paths=[config],
                runner_command=["/bin/sh", "-c", "printf 'workspace launch\\n'; sleep 0.8"],
            )
        )

    def _prepared_revision(self) -> tuple[str, str]:
        preparation = self.client.post(
            "/api/workspace/discovery-preparations",
            data={"research_text": "Find a useful mechanism."},
        ).json()
        revision = self.client.post(
            f"/api/workspace/discovery-preparations/{preparation['id']}/revisions",
            json={"formatted_input": "Find a useful mechanism."},
        ).json()
        return preparation["id"], revision["id"]

    def test_moonshot_records_an_immutable_input_snapshot_and_blocks_second_run(self) -> None:
        preparation_id, revision_id = self._prepared_revision()
        response = self.client.post(
            "/api/workspace/discovery-launches",
            json={"preparation_id": preparation_id, "revision_id": revision_id},
        )
        self.assertEqual(response.status_code, 201)
        launch_id = response.json()["launch_id"]
        snapshot = self.results_root / launch_id / "discovery_input_snapshot.json"
        self.assertTrue(snapshot.is_file())
        self.assertTrue((self.results_root / launch_id / "config_snapshot").is_dir())
        self.assertIn(revision_id, snapshot.read_text())
        updated = self.client.put(
            f"/api/workspace/discovery-preparations/{preparation_id}",
            json={"research_text": "A later preparation edit."},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertNotIn("A later preparation edit.", snapshot.read_text())
        listed = self.client.get("/api/workspace/discovery-launches").json()["launches"]
        self.assertIn(listed[0]["state"], {"starting", "running"})

        second = self.client.post(
            "/api/workspace/discovery-launches",
            json={"preparation_id": preparation_id, "revision_id": revision_id},
        )
        self.assertEqual(second.status_code, 409)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if all(entry["state"] not in {"queued", "running"} for entry in self.client.get("/api/admin/queue").json()["entries"]):
                break
            time.sleep(0.05)

    def test_workspace_artifact_tree_hides_machine_only_files(self) -> None:
        launch_dir = self.results_root / "Discovery" / "20260727_000000_launch"
        launch_dir.mkdir(parents=True)
        (launch_dir / "report.md").write_text("# Report")
        (launch_dir / "weights.pt").write_bytes(b"weights")
        (launch_dir / "config_snapshot").mkdir()
        (launch_dir / "config_snapshot" / "default_config.yaml").write_text("system: {}")

        response = self.client.get(
            "/api/workspace/discovery-launches/Discovery/20260727_000000_launch/artifacts/tree"
        )
        self.assertEqual(response.status_code, 200)
        paths = {
            node["path"]
            for node in _flatten(response.json()["tree"])
        }
        self.assertEqual(paths, {"report.md"})

    def test_moonshot_rejects_a_saved_revision_with_an_unreadable_source(self) -> None:
        preparation = self.client.post(
            "/api/workspace/discovery-preparations",
            data={"research_text": "Inspect this baseline."},
            files={"sources": ("baseline.zip", io.BytesIO(b"not a zip"), "application/zip")},
        ).json()
        revision = self.client.post(
            f"/api/workspace/discovery-preparations/{preparation['id']}/revisions",
            json={"formatted_input": "Inspect this baseline."},
        ).json()

        response = self.client.post(
            "/api/workspace/discovery-launches",
            json={"preparation_id": preparation["id"], "revision_id": revision["id"]},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("baseline.zip", response.json()["detail"])
        self.assertEqual(self.client.get("/api/workspace/discovery-launches").json()["launches"], [])

    def test_workspace_status_and_listing_preserve_historical_terminal_outcomes(self) -> None:
        launch_dir = self.results_root / "Discovery" / "20260727_000001_launch"
        launch_dir.mkdir(parents=True)
        (launch_dir / "launch_outcome.json").write_text(
            json.dumps({"outcome": "failed"}),
            encoding="utf-8",
        )

        listed = self.client.get("/api/workspace/discovery-launches").json()["launches"]
        self.assertEqual(listed[0]["state"], "failed")
        status = self.client.get(
            "/api/workspace/discovery-launches/Discovery/20260727_000001_launch/status"
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["state"], "failed")

    def test_workspace_replays_historical_console_and_confines_artifact_access(self) -> None:
        launch_dir = self.results_root / "Discovery" / "20260727_000002_launch"
        launch_dir.mkdir(parents=True)
        (launch_dir / "runner.log").write_text("first\nsecond\n", encoding="utf-8")
        (launch_dir / "report.md").write_text("# Report\n", encoding="utf-8")

        received: list[str] = []
        with self.client.stream(
            "GET",
            "/api/workspace/discovery-launches/Discovery/20260727_000002_launch/logs/stream",
        ) as response:
            self.assertEqual(response.status_code, 200)
            for line in response.iter_lines():
                if line.startswith("data: "):
                    received.append(line[6:])

        self.assertEqual(received, ["first", "second"])
        alternate_log = self.client.get(
            "/api/workspace/discovery-launches/Discovery/20260727_000002_launch/logs/stream",
            params={"file": "report.md"},
        )
        self.assertEqual(alternate_log.status_code, 400)
        report = self.client.get(
            "/api/workspace/discovery-launches/Discovery/20260727_000002_launch/artifacts/file",
            params={"path": "report.md"},
        )
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.text, "# Report\n")
        traversal = self.client.get(
            "/api/workspace/discovery-launches/Discovery/20260727_000002_launch/artifacts/file",
            params={"path": "../launch_queue.json"},
        )
        self.assertEqual(traversal.status_code, 404)

    def test_workspace_status_exposes_a_gracefully_stopped_launch_as_aborted(self) -> None:
        preparation_id, revision_id = self._prepared_revision()
        submitted = self.client.post(
            "/api/workspace/discovery-launches",
            json={"preparation_id": preparation_id, "revision_id": revision_id},
        ).json()
        self.assertEqual(set(submitted), {"launch_id", "state"})
        queue_entry = next(
            item
            for item in self.client.get("/api/admin/queue").json()["entries"]
            if item["launch_id"] == submitted["launch_id"]
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            entries = self.client.get("/api/admin/queue").json()["entries"]
            entry = next(item for item in entries if item["queue_id"] == queue_entry["queue_id"])
            if entry["state"] == "running" and entry["pid"] is not None:
                break
            time.sleep(0.05)
        else:
            self.fail("workspace launch never reached running state")

        stopped = self.client.post(f"/api/admin/queue/{queue_entry['queue_id']}/stop")
        self.assertEqual(stopped.status_code, 200)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            entry = next(
                item
                for item in self.client.get("/api/admin/queue").json()["entries"]
                if item["queue_id"] == queue_entry["queue_id"]
            )
            if entry["state"] == "aborted":
                break
            time.sleep(0.05)
        else:
            self.fail("workspace launch never reached aborted state")

        status = self.client.get(
            f"/api/workspace/discovery-launches/{submitted['launch_id']}/status"
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["state"], "aborted")


def _flatten(nodes: list[dict]) -> list[dict]:
    result: list[dict] = []
    for node in nodes:
        result.append(node)
        result.extend(_flatten(node.get("children", [])))
    return result


if __name__ == "__main__":
    unittest.main()
