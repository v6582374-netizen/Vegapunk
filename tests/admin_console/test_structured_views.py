from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from admin_console.app import create_app

FAKE_RUNNER = Path(__file__).parent / "fake_runner.py"
FAKE_RUNNER_COMMAND = [sys.executable, str(FAKE_RUNNER), "{task_dir}", "{launch_dir}"]


class StructuredViewsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.results_root = Path(self._tmp.name)
        self.launch = self.results_root / "AutoDemo" / "20260718_120000_launch"
        self.launch.mkdir(parents=True)
        self.launch_id = "AutoDemo/20260718_120000_launch"
        self._seed_historical_layout()
        self.client = TestClient(create_app(results_root=self.results_root))

    def _seed_historical_layout(self) -> None:
        session = self.launch / "session_1"
        session.mkdir()
        (session / "ideas.json").write_text(
            json.dumps(
                [
                    {
                        "name": "FakeIdea",
                        "title": "A fake idea",
                        "description": "desc",
                        "method": "method text",
                    }
                ]
            )
        )
        candidate = session / "20260718_120100_FakeIdea"
        candidate.mkdir()
        (candidate / "notes.txt").write_text("# Method notes\n")
        (candidate / "experiment_report.txt").write_text("report body\n")

        run0 = candidate / "run_0"
        (run0 / "code").mkdir(parents=True)
        (run0 / "code" / "experiment.py").write_text("print('baseline')\n")
        (run0 / "final_info.json").write_text(json.dumps({"combined_score": 0.1, "loss": 1.0}))
        (run0 / "log.txt").write_text("baseline ok\n")

        run1 = candidate / "run_1"
        (run1 / "code").mkdir(parents=True)
        (run1 / "code" / "experiment.py").write_text("print('improved')\n")
        (run1 / "final_info.json").write_text(json.dumps({"combined_score": 0.5, "loss": 0.4}))
        (run1 / "log.txt").write_text("run1 ok\n")

        run2 = candidate / "run_2"
        (run2 / "code").mkdir(parents=True)
        (run2 / "code" / "experiment.py").write_text("print('broken')\n")
        (run2 / "traceback.log").write_text("Traceback (most recent call last):\nRuntimeError\n")
        (run2 / "log.txt").write_text("run2 failed\n")

        (self.launch / "orphan.txt").write_text("still reachable via Artifact Explorer\n")
        (self.launch / "manuscript").mkdir()
        (self.launch / "manuscript" / "draft.md").write_text("# paper\n")

    def test_timeline_lists_rounds_candidates_and_runs_with_jump_paths(self) -> None:
        response = self.client.get(f"/api/launches/{self.launch_id}/timeline")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["stage"], "paper")
        self.assertEqual(len(body["rounds"]), 1)
        round0 = body["rounds"][0]
        self.assertEqual(round0["path"], "session_1")
        self.assertEqual(round0["ideas_path"], "session_1/ideas.json")
        self.assertEqual(round0["ideas"][0]["name"], "FakeIdea")
        self.assertEqual(len(round0["candidates"]), 1)
        candidate = round0["candidates"][0]
        self.assertEqual(candidate["name"], "FakeIdea")
        self.assertEqual(candidate["method_path"], "session_1/20260718_120100_FakeIdea/notes.txt")
        run_ids = [run["id"] for run in candidate["runs"]]
        self.assertEqual(run_ids, ["run_0", "run_1", "run_2"])
        self.assertEqual(candidate["runs"][1]["metrics_path"], "session_1/20260718_120100_FakeIdea/run_1/final_info.json")
        self.assertEqual(candidate["runs"][1]["combined_score"], 0.5)
        self.assertEqual(candidate["runs"][2]["outcome"], "failed")
        self.assertEqual(body["paper"]["path"], "manuscript")

    def test_experiment_run_detail_includes_metrics_log_and_code_diff(self) -> None:
        run_path = "session_1/20260718_120100_FakeIdea/run_1"
        response = self.client.get(
            f"/api/launches/{self.launch_id}/experiment-run",
            params={"path": run_path},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["path"], run_path)
        self.assertEqual(body["outcome"], "completed")
        self.assertEqual(body["metrics"]["combined_score"], 0.5)
        self.assertEqual(body["log_path"], f"{run_path}/log.txt")
        self.assertIn("run1 ok", body["log_preview"])
        self.assertTrue(any(f["name"] == "experiment.py" for f in body["code_files"]))
        self.assertIn("improved", body["code_diff"])
        self.assertIn("baseline", body["code_diff"])

    def test_failed_experiment_run_detail_is_available_without_metrics(self) -> None:
        run_path = "session_1/20260718_120100_FakeIdea/run_2"
        response = self.client.get(
            f"/api/launches/{self.launch_id}/experiment-run",
            params={"path": run_path},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["outcome"], "failed")
        self.assertIsNone(body["metrics"])
        self.assertEqual(body["traceback_path"], f"{run_path}/traceback.log")
        self.assertIn("RuntimeError", body["log_preview"])

    def test_unmodeled_files_remain_reachable_via_artifact_explorer(self) -> None:
        tree = self.client.get(f"/api/artifacts/{self.launch_id}/tree").json()["tree"]
        paths = {node["path"] for node in _flatten(tree)}
        self.assertIn("orphan.txt", paths)
        file_response = self.client.get(
            f"/api/artifacts/{self.launch_id}/file",
            params={"path": "orphan.txt"},
        )
        self.assertEqual(file_response.status_code, 200)
        self.assertIn("Artifact Explorer", file_response.text)

    def test_fake_runner_launch_has_timeline_and_run_detail(self) -> None:
        root = Path(self._tmp.name) / "queue_case"
        results_root = root / "results"
        tasks_root = root / "tasks"
        config_dir = root / "config"
        results_root.mkdir(parents=True)
        config_dir.mkdir()
        (tasks_root / "AutoDemo").mkdir(parents=True)
        (tasks_root / "AutoDemo" / "prompt.json").write_text("{}")
        (config_dir / "default_config.yaml").write_text("system:\n  debug: false\n")
        (config_dir / "model_catalog.yaml").write_text("providers: {}\n")
        client = TestClient(
            create_app(
                results_root=results_root,
                tasks_root=tasks_root,
                config_paths=list(config_dir.glob("*.yaml")),
                runner_command=FAKE_RUNNER_COMMAND,
            )
        )
        submitted = client.post("/api/queue", json={"task": "AutoDemo"})
        self.assertEqual(submitted.status_code, 201)
        queue_id = submitted.json()["queue_id"]
        launch_id = None
        for _ in range(80):
            entry = next(
                item
                for item in client.get("/api/queue").json()["entries"]
                if item["queue_id"] == queue_id
            )
            if entry["state"] == "completed" and entry["launch_id"]:
                launch_id = entry["launch_id"]
                break
            time.sleep(0.05)
        self.assertIsNotNone(launch_id)
        timeline = client.get(f"/api/launches/{launch_id}/timeline").json()
        self.assertGreaterEqual(len(timeline["rounds"]), 1)
        run_path = timeline["rounds"][0]["candidates"][0]["runs"][1]["path"]
        detail = client.get(
            f"/api/launches/{launch_id}/experiment-run",
            params={"path": run_path},
        ).json()
        self.assertEqual(detail["outcome"], "completed")
        self.assertIn("improved", detail["code_diff"])


def _flatten(nodes: list[dict]) -> list[dict]:
    result = []
    for node in nodes:
        result.append(node)
        result.extend(_flatten(node.get("children", [])))
    return result


if __name__ == "__main__":
    unittest.main()
