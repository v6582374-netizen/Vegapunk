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
FAKE_RUNNER_COMMAND = [
    sys.executable,
    str(FAKE_RUNNER),
    "{task_dir}",
    "{launch_dir}",
    "--config",
    "{snapshot_dir}/default_config.yaml",
]


class StopAndResumeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.results_root = root / "results"
        self.results_root.mkdir()
        self.tasks_root = root / "tasks"
        (self.tasks_root / "AutoDemo").mkdir(parents=True)
        (self.tasks_root / "AutoDemo" / "prompt.json").write_text("{}")
        self.config_path = root / "default_config.yaml"
        self.config_path.write_text("workflow:\n  loop_rounds: 10\n")
        self.client = TestClient(
            create_app(
                results_root=self.results_root,
                tasks_root=self.tasks_root,
                config_paths=[self.config_path],
                runner_command=FAKE_RUNNER_COMMAND,
            )
        )

    def _wait(self, queue_id: str, state: str, timeout: float = 10.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            entries = self.client.get("/api/queue").json()["entries"]
            entry = next(e for e in entries if e["queue_id"] == queue_id)
            if entry["state"] == state:
                return entry
            time.sleep(0.05)
        raise AssertionError(f"entry {queue_id} never reached {state}: {entry}")

    def _submit_running(self) -> dict:
        entry = self.client.post("/api/queue", json={"task": "AutoDemo"}).json()
        running = self._wait(entry["queue_id"], "running")
        launch_dir = self.results_root / running["launch_id"]
        log_path = launch_dir / "console.log"
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            entries = self.client.get("/api/queue").json()["entries"]
            running = next(item for item in entries if item["queue_id"] == entry["queue_id"])
            if (
                running["pid"] is not None
                and log_path.is_file()
                and "fake runner started" in log_path.read_text()
            ):
                return running
            time.sleep(0.05)
        raise AssertionError(f"runner {entry['queue_id']} did not become signal-ready")

    def test_graceful_stop_checkpoints_and_marks_aborted(self) -> None:
        with unittest.mock.patch.dict("os.environ", {"FAKE_RUNNER_SLEEP": "30"}):
            running = self._submit_running()
            response = self.client.post(f"/api/queue/{running['queue_id']}/stop")
            self.assertEqual(response.status_code, 200)
            aborted = self._wait(running["queue_id"], "aborted")

        launch_dir = self.results_root / aborted["launch_id"]
        self.assertTrue((launch_dir / "checkpoint.json").is_file())
        self.assertEqual(aborted["stopped_how"], "graceful")

    def test_force_kill_works_when_graceful_stop_is_ignored(self) -> None:
        with unittest.mock.patch.dict(
            "os.environ", {"FAKE_RUNNER_SLEEP": "30", "FAKE_RUNNER_IGNORE_SIGTERM": "1"}
        ):
            running = self._submit_running()
            self.client.post(f"/api/queue/{running['queue_id']}/stop")
            time.sleep(0.5)
            response = self.client.post(f"/api/queue/{running['queue_id']}/kill")
            self.assertEqual(response.status_code, 200)
            aborted = self._wait(running["queue_id"], "aborted")
        self.assertEqual(aborted["stopped_how"], "force")

    def test_stop_rejected_when_not_running(self) -> None:
        entry = self.client.post("/api/queue", json={"task": "AutoDemo"}).json()
        self._wait(entry["queue_id"], "completed")
        response = self.client.post(f"/api/queue/{entry['queue_id']}/stop")
        self.assertEqual(response.status_code, 409)

    def test_resume_reuses_launch_dir_and_original_snapshot(self) -> None:
        with unittest.mock.patch.dict("os.environ", {"FAKE_RUNNER_SLEEP": "30"}):
            running = self._submit_running()
            self.client.post(f"/api/queue/{running['queue_id']}/stop")
            aborted = self._wait(running["queue_id"], "aborted")

        # Edit the global config after the abort; resume must NOT absorb it.
        self.config_path.write_text("workflow:\n  loop_rounds: 99\n")

        response = self.client.post(f"/api/launches/{aborted['launch_id']}/resume")
        self.assertEqual(response.status_code, 201)
        resumed = response.json()
        self.assertEqual(resumed["launch_id"], aborted["launch_id"])
        finished = self._wait(resumed["queue_id"], "completed")

        launch_dir = self.results_root / finished["launch_id"]
        snapshot = (launch_dir / "config_snapshot" / "default_config.yaml").read_text()
        self.assertIn("loop_rounds: 10", snapshot)
        self.assertNotIn("loop_rounds: 99", snapshot)

    def test_resume_of_running_launch_is_rejected(self) -> None:
        with unittest.mock.patch.dict("os.environ", {"FAKE_RUNNER_SLEEP": "30"}):
            running = self._submit_running()
            response = self.client.post(f"/api/launches/{running['launch_id']}/resume")
            self.assertEqual(response.status_code, 409)
            self.client.post(f"/api/queue/{running['queue_id']}/kill")
            self._wait(running["queue_id"], "aborted")

    def test_resume_of_completed_launch_is_rejected(self) -> None:
        entry = self.client.post("/api/queue", json={"task": "AutoDemo"}).json()
        finished = self._wait(entry["queue_id"], "completed")
        response = self.client.post(f"/api/launches/{finished['launch_id']}/resume")
        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
