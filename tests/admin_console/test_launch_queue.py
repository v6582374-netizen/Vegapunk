from __future__ import annotations

import json
import subprocess
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


def _wait_for_state(client: TestClient, queue_id: str, state: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entries = client.get("/api/queue").json()["entries"]
        entry = next(item for item in entries if item["queue_id"] == queue_id)
        if entry["state"] == state:
            return entry
        time.sleep(0.05)
    raise AssertionError(f"queue entry {queue_id} never reached state {state}: {entry}")


class LaunchQueueEnvironment:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.results_root = root / "results"
        self.tasks_root = root / "tasks"
        self.config_dir = root / "config"
        self.results_root.mkdir()
        self.config_dir.mkdir()
        (self.tasks_root / "AutoDemo").mkdir(parents=True)
        (self.tasks_root / "AutoDemo" / "prompt.json").write_text("{}")
        (self.config_dir / "default_config.yaml").write_text("system:\n  debug: false\n")
        (self.config_dir / "model_catalog.yaml").write_text("providers: {}\n")

    def create_client(self) -> TestClient:
        return TestClient(
            create_app(
                results_root=self.results_root,
                tasks_root=self.tasks_root,
                config_paths=list(self.config_dir.glob("*.yaml")),
                runner_command=FAKE_RUNNER_COMMAND,
            )
        )

    def cleanup(self) -> None:
        self._tmp.cleanup()


class LaunchQueueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = LaunchQueueEnvironment()
        self.addCleanup(self.env.cleanup)

    def test_submitted_launch_runs_to_completion_with_snapshot(self) -> None:
        client = self.env.create_client()

        response = client.post("/api/queue", json={"task": "AutoDemo"})
        self.assertEqual(response.status_code, 201)
        entry = response.json()
        queue_id = entry["queue_id"]
        self.assertEqual(entry["task"], "AutoDemo")

        finished = _wait_for_state(client, queue_id, "completed")

        launch_dir = self.env.results_root / finished["launch_id"]
        self.assertTrue((launch_dir / "ideas.json").is_file())
        snapshot = launch_dir / "config_snapshot"
        self.assertEqual(
            (snapshot / "default_config.yaml").read_text(),
            "system:\n  debug: false\n",
        )
        self.assertTrue((snapshot / "model_catalog.yaml").is_file())

    def test_available_tasks_are_listed(self) -> None:
        client = self.env.create_client()
        response = client.get("/api/tasks")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tasks"], ["AutoDemo"])

    def test_unknown_task_is_rejected(self) -> None:
        client = self.env.create_client()
        response = client.post("/api/queue", json={"task": "NoSuchTask"})
        self.assertEqual(response.status_code, 404)

    def test_second_launch_waits_until_first_finishes(self) -> None:
        client = self.env.create_client()
        with unittest.mock.patch.dict("os.environ", {"FAKE_RUNNER_SLEEP": "0.4"}):
            first = client.post("/api/queue", json={"task": "AutoDemo"}).json()
            second = client.post("/api/queue", json={"task": "AutoDemo"}).json()

            _wait_for_state(client, first["queue_id"], "running")
            entries = {e["queue_id"]: e for e in client.get("/api/queue").json()["entries"]}
            self.assertEqual(entries[second["queue_id"]]["state"], "queued")

        _wait_for_state(client, first["queue_id"], "completed")
        _wait_for_state(client, second["queue_id"], "completed")

    def test_queued_launch_can_be_cancelled_but_running_cannot(self) -> None:
        client = self.env.create_client()
        with unittest.mock.patch.dict("os.environ", {"FAKE_RUNNER_SLEEP": "0.4"}):
            first = client.post("/api/queue", json={"task": "AutoDemo"}).json()
            second = client.post("/api/queue", json={"task": "AutoDemo"}).json()
            _wait_for_state(client, first["queue_id"], "running")

            cancelled = client.delete(f"/api/queue/{second['queue_id']}")
            self.assertEqual(cancelled.status_code, 200)
            self.assertEqual(cancelled.json()["state"], "cancelled")

            running_cancel = client.delete(f"/api/queue/{first['queue_id']}")
            self.assertEqual(running_cancel.status_code, 409)

        _wait_for_state(client, first["queue_id"], "completed")
        entries = {e["queue_id"]: e for e in client.get("/api/queue").json()["entries"]}
        self.assertEqual(entries[second["queue_id"]]["state"], "cancelled")

    def test_failed_runner_marks_launch_failed(self) -> None:
        client = self.env.create_client()
        with unittest.mock.patch.dict("os.environ", {"FAKE_RUNNER_OUTCOME": "failed"}):
            entry = client.post("/api/queue", json={"task": "AutoDemo"}).json()
            _wait_for_state(client, entry["queue_id"], "failed")

    def test_runner_is_pointed_at_the_snapshot_config(self) -> None:
        client = self.env.create_client()
        entry = client.post("/api/queue", json={"task": "AutoDemo"}).json()
        finished = _wait_for_state(client, entry["queue_id"], "completed")

        launch_dir = self.env.results_root / finished["launch_id"]
        argv = json.loads((launch_dir / "runner_argv.json").read_text())
        config_arg = argv[argv.index("--config") + 1]
        self.assertEqual(
            Path(config_arg),
            launch_dir / "config_snapshot" / "default_config.yaml",
        )

    def test_completed_console_launch_state_appears_in_listing(self) -> None:
        client = self.env.create_client()
        entry = client.post("/api/queue", json={"task": "AutoDemo"}).json()
        finished = _wait_for_state(client, entry["queue_id"], "completed")

        launches = client.get("/api/launches").json()["launches"]
        listed = next(item for item in launches if item["id"] == finished["launch_id"])
        self.assertEqual(listed["state"], "completed")

    def test_surviving_run_from_previous_service_blocks_the_queue(self) -> None:
        orphan = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(orphan.kill)
        state_path = self.env.results_root / "launch_queue.json"
        state_path.write_text(
            '{"entries": [{"queue_id": "orphan000001", "task": "AutoDemo",'
            ' "state": "running", "submitted_at": "2026-07-18T00:00:00",'
            f' "launch_id": "AutoDemo/20260718_000000_launch", "pid": {orphan.pid}}}]}}'
        )

        client = self.env.create_client()
        entry = client.post("/api/queue", json={"task": "AutoDemo"}).json()
        time.sleep(0.4)
        entries = {e["queue_id"]: e for e in client.get("/api/queue").json()["entries"]}
        self.assertEqual(entries["orphan000001"]["state"], "running")
        self.assertEqual(entries[entry["queue_id"]]["state"], "queued")

        orphan.kill()
        orphan.wait()
        _wait_for_state(client, "orphan000001", "interrupted")
        _wait_for_state(client, entry["queue_id"], "completed")

    def test_queue_state_survives_service_restart(self) -> None:
        client = self.env.create_client()
        entry = client.post("/api/queue", json={"task": "AutoDemo"}).json()
        _wait_for_state(client, entry["queue_id"], "completed")

        restarted = self.env.create_client()
        entries = {e["queue_id"]: e for e in restarted.get("/api/queue").json()["entries"]}
        self.assertEqual(entries[entry["queue_id"]]["state"], "completed")

    def test_stale_running_entry_becomes_interrupted_after_restart(self) -> None:
        state_path = self.env.results_root / "launch_queue.json"
        state_path.write_text(
            '{"entries": [{"queue_id": "dead00000001", "task": "AutoDemo",'
            ' "state": "running", "submitted_at": "2026-07-18T00:00:00",'
            ' "launch_id": "AutoDemo/20260718_000000_launch", "pid": 999999999}]}'
        )
        client = self.env.create_client()
        entries = client.get("/api/queue").json()["entries"]
        self.assertEqual(entries[0]["state"], "interrupted")


if __name__ == "__main__":
    unittest.main()
