from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from admin_console.app import create_app


def _make_launch_dir(results_root: Path, task: str, stamp: str) -> Path:
    launch_dir = results_root / task / f"{stamp}_launch"
    launch_dir.mkdir(parents=True)
    return launch_dir


class LaunchListingTest(unittest.TestCase):
    def test_lists_historical_launches_with_name_time_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results_root = Path(tmp)
            finished = _make_launch_dir(results_root, "AutoDebug", "20260714_131406")
            (finished / "manuscript").mkdir()
            _make_launch_dir(results_root, "AutoChem", "20260701_090000")

            client = TestClient(create_app(results_root=results_root))
            response = client.get("/api/launches")

            self.assertEqual(response.status_code, 200)
            launches = response.json()["launches"]
            by_id = {item["id"]: item for item in launches}
            self.assertIn("AutoDebug/20260714_131406_launch", by_id)
            self.assertIn("AutoChem/20260701_090000_launch", by_id)

            debug = by_id["AutoDebug/20260714_131406_launch"]
            self.assertEqual(debug["task"], "AutoDebug")
            self.assertEqual(debug["started_at"], "2026-07-14T13:14:06")
            self.assertEqual(debug["state"], "completed")

            chem = by_id["AutoChem/20260701_090000_launch"]
            self.assertEqual(chem["state"], "unknown")

    def test_launches_are_sorted_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results_root = Path(tmp)
            _make_launch_dir(results_root, "AutoChem", "20260701_090000")
            _make_launch_dir(results_root, "AutoDebug", "20260714_131406")

            client = TestClient(create_app(results_root=results_root))
            launches = client.get("/api/launches").json()["launches"]

            self.assertEqual(
                [item["id"] for item in launches],
                [
                    "AutoDebug/20260714_131406_launch",
                    "AutoChem/20260701_090000_launch",
                ],
            )

    def test_non_launch_directories_and_files_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results_root = Path(tmp)
            _make_launch_dir(results_root, "AutoDebug", "20260714_131406")
            (results_root / "chroma_db").mkdir()
            (results_root / "AutoDebug" / "traj_session_1.json").write_text("{}")
            (results_root / "launch_queue.json").write_text("{}")

            client = TestClient(create_app(results_root=results_root))
            launches = client.get("/api/launches").json()["launches"]

            self.assertEqual(len(launches), 1)


if __name__ == "__main__":
    unittest.main()
