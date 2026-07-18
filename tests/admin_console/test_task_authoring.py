from __future__ import annotations

import io
import json
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from admin_console.app import create_app

FAKE_RUNNER = Path(__file__).parent / "fake_runner.py"
FAKE_RUNNER_COMMAND = [sys.executable, str(FAKE_RUNNER), "{task_dir}", "{launch_dir}"]


class TaskAuthoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.results_root = root / "results"
        self.results_root.mkdir()
        self.tasks_root = root / "tasks"
        self.tasks_root.mkdir()
        # Existing auto + sci tasks for browse/reuse.
        (self.tasks_root / "ExistingAuto").mkdir()
        (self.tasks_root / "ExistingAuto" / "prompt.json").write_text("{}")
        (self.tasks_root / "ExistingSci").mkdir()
        (self.tasks_root / "ExistingSci" / "task_info.json").write_text("{}")
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

    def test_create_task_writes_prompt_json_and_lists_it(self) -> None:
        response = self.client.post(
            "/api/tasks",
            data={
                "name": "MyNewTask",
                "system": "You are a researcher.",
                "task_description": "Improve the model.",
                "domain": "vision",
                "background": "Background text.",
                "constraints": json.dumps(["no data change"]),
            },
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["name"], "MyNewTask")
        self.assertFalse(body["has_baseline_code"])
        self.assertEqual(body["path_mode"], "report")

        prompt = json.loads((self.tasks_root / "MyNewTask" / "prompt.json").read_text())
        self.assertEqual(prompt["system"], "You are a researcher.")
        self.assertEqual(prompt["task_description"], "Improve the model.")
        self.assertEqual(prompt["domain"], "vision")
        self.assertEqual(prompt["background"], "Background text.")
        self.assertEqual(prompt["constraints"], ["no data change"])

        tasks = self.client.get("/api/tasks").json()["tasks"]
        names = {t["name"] if isinstance(t, dict) else t for t in tasks}
        self.assertIn("MyNewTask", names)

    def test_create_with_baseline_zip_marks_experiment_path(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("code/experiment.py", "print('ok')\n")
            archive.writestr("launcher.sh", "python code/experiment.py\n")
        buffer.seek(0)

        response = self.client.post(
            "/api/tasks",
            data={
                "name": "CodedTask",
                "system": "s",
                "task_description": "d",
                "domain": "dom",
                "background": "b",
                "constraints": "[]",
            },
            files={"baseline_code": ("baseline.zip", buffer, "application/zip")},
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["has_baseline_code"])
        self.assertEqual(body["path_mode"], "experiment")
        self.assertTrue((self.tasks_root / "CodedTask" / "code" / "experiment.py").is_file())
        self.assertTrue((self.tasks_root / "CodedTask" / "launcher.sh").is_file())

    def test_duplicate_name_is_rejected(self) -> None:
        payload = {
            "name": "ExistingAuto",
            "system": "s",
            "task_description": "d",
            "domain": "dom",
            "background": "b",
            "constraints": "[]",
        }
        response = self.client.post("/api/tasks", data=payload)
        self.assertEqual(response.status_code, 409)

    def test_invalid_name_is_rejected(self) -> None:
        response = self.client.post(
            "/api/tasks",
            data={
                "name": "../escape",
                "system": "s",
                "task_description": "d",
                "domain": "dom",
                "background": "b",
                "constraints": "[]",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_tasks_list_includes_path_mode_for_existing(self) -> None:
        (self.tasks_root / "ExistingAuto" / "code").mkdir()
        (self.tasks_root / "ExistingAuto" / "code" / "experiment.py").write_text("x")
        response = self.client.get("/api/tasks")
        self.assertEqual(response.status_code, 200)
        by_name = {t["name"]: t for t in response.json()["tasks"]}
        self.assertEqual(by_name["ExistingAuto"]["path_mode"], "experiment")
        self.assertEqual(by_name["ExistingSci"]["path_mode"], "report")

    def test_created_task_can_be_enqueued(self) -> None:
        self.client.post(
            "/api/tasks",
            data={
                "name": "EnqueueMe",
                "system": "s",
                "task_description": "d",
                "domain": "dom",
                "background": "b",
                "constraints": "[]",
            },
        )
        entry = self.client.post("/api/queue", json={"task": "EnqueueMe"}).json()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = next(
                e
                for e in self.client.get("/api/queue").json()["entries"]
                if e["queue_id"] == entry["queue_id"]
            )
            if state["state"] == "completed":
                return
            time.sleep(0.05)
        self.fail(f"enqueued authored task never completed: {state}")


if __name__ == "__main__":
    unittest.main()
