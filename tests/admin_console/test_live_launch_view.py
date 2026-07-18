from __future__ import annotations

import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

from fastapi.testclient import TestClient

from admin_console.app import create_app

FAKE_RUNNER = Path(__file__).parent / "fake_runner.py"
FAKE_RUNNER_COMMAND = [sys.executable, str(FAKE_RUNNER), "{task_dir}", "{launch_dir}"]


class LiveLaunchViewTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.results_root = root / "results"
        self.results_root.mkdir()
        self.tasks_root = root / "tasks"
        (self.tasks_root / "AutoDemo").mkdir(parents=True)
        (self.tasks_root / "AutoDemo" / "prompt.json").write_text("{}")
        config = root / "default_config.yaml"
        config.write_text("system: {}\n")
        self.client = TestClient(
            create_app(
                results_root=self.results_root,
                tasks_root=self.tasks_root,
                config_paths=[config],
                runner_command=FAKE_RUNNER_COMMAND,
            )
        )

    def _submit_and_wait(self, timeout: float = 10.0) -> dict:
        entry = self.client.post("/api/queue", json={"task": "AutoDemo"}).json()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            entries = self.client.get("/api/queue").json()["entries"]
            state = next(e for e in entries if e["queue_id"] == entry["queue_id"])
            if state["state"] in {"completed", "failed"}:
                return state
            time.sleep(0.05)
        raise AssertionError(f"launch never finished: {state}")

    def test_status_reports_state_and_recent_artifacts(self) -> None:
        finished = self._submit_and_wait()
        response = self.client.get(f"/api/launches/{finished['launch_id']}/status")
        self.assertEqual(response.status_code, 200)
        status = response.json()
        self.assertEqual(status["state"], "completed")
        recent_paths = [artifact["path"] for artifact in status["recent_artifacts"]]
        self.assertIn("ideas.json", recent_paths)
        self.assertIn("launch_outcome.json", recent_paths)

    def test_status_counts_discovery_rounds_from_sessions(self) -> None:
        launch_dir = self.results_root / "AutoDemo" / "20260718_000000_launch"
        (launch_dir / "session_1").mkdir(parents=True)
        (launch_dir / "session_2").mkdir()
        response = self.client.get("/api/launches/AutoDemo/20260718_000000_launch/status")
        self.assertEqual(response.json()["rounds"], 2)

    def test_log_stream_delivers_runner_output_until_completion(self) -> None:
        with unittest.mock.patch.dict("os.environ", {"FAKE_RUNNER_SLEEP": "0.4"}):
            entry = self.client.post("/api/queue", json={"task": "AutoDemo"}).json()
            deadline = time.monotonic() + 10
            launch_id = None
            while time.monotonic() < deadline and launch_id is None:
                entries = self.client.get("/api/queue").json()["entries"]
                launch_id = next(
                    e for e in entries if e["queue_id"] == entry["queue_id"]
                )["launch_id"]
                time.sleep(0.02)

            received = []
            with self.client.stream(
                "GET", f"/api/launches/{launch_id}/logs/stream", params={"file": "console.log"}
            ) as response:
                self.assertEqual(response.status_code, 200)
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        received.append(line[len("data: "):])

        text = "\n".join(received)
        self.assertIn("fake runner started", text)
        self.assertIn("fake runner finished", text)

    def test_log_stream_of_historical_launch_ends_after_existing_content(self) -> None:
        launch_dir = self.results_root / "AutoDemo" / "20260718_000000_launch"
        launch_dir.mkdir(parents=True)
        (launch_dir / "console.log").write_text("old line\n")
        received = []
        with self.client.stream(
            "GET",
            "/api/launches/AutoDemo/20260718_000000_launch/logs/stream",
            params={"file": "console.log"},
        ) as response:
            for line in response.iter_lines():
                if line.startswith("data: "):
                    received.append(line[len("data: "):])
        self.assertEqual(received, ["old line"])


if __name__ == "__main__":
    unittest.main()
