from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from internagent.paper_orchestra import run_paper_orchestra
from tests.paper_orchestra.test_vendored_service import (
    _write_config,
    _write_fake_vendor,
    _write_launch,
)


class PaperOrchestraServiceTest(unittest.TestCase):
    def test_successful_paper_is_reused_after_discovery_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            launch_dir = root / "launch"
            _write_launch(launch_dir)
            vendor_root = _write_fake_vendor(root)
            config_path = _write_config(root, vendor_root)

            first = _run(launch_dir, config_path)
            summary_path = launch_dir / "discovery_summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["rounds"].append(
                {"round": 2, "session_id": "session_2", "results": []}
            )
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            second = _run(launch_dir, config_path)

            self.assertIsNone(first.error, first.error)
            self.assertIsNone(second.error, second.error)
            self.assertEqual(first.run_dir, second.run_dir)
            self.assertEqual(first.paper_orchestra_run_id, "paper")
            self.assertEqual(second.paper_orchestra_run_id, "paper")

    def test_no_successful_candidate_still_runs_from_launch_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            launch_dir = root / "launch"
            _write_launch(launch_dir)
            summary_path = launch_dir / "discovery_summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["rounds"][0]["results"][0]["success"] = False
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            vendor_root = _write_fake_vendor(root)
            config_path = _write_config(root, vendor_root)

            result = _run(launch_dir, config_path)

            self.assertIsNone(result.error, result.error)
            idea = (result.run_dir / "raw_materials/idea_sparse.md").read_text(
                encoding="utf-8"
            )
            experiments = (
                result.run_dir / "raw_materials/experimental_log.md"
            ).read_text(encoding="utf-8")
            self.assertIn("measure the field", idea)
            self.assertNotIn("Selected method notes", idea)
            self.assertEqual(experiments.strip(), "# Experimental Record")

    def test_candidate_selection_runtime_error_does_not_block_paper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            launch_dir = root / "launch"
            _write_launch(launch_dir)
            vendor_root = _write_fake_vendor(root)
            config_path = _write_config(root, vendor_root)

            with patch(
                "internagent.paper_orchestra.service.select_candidate",
                side_effect=RuntimeError("selection backend unavailable"),
            ):
                result = _run(launch_dir, config_path)

            self.assertIsNone(result.error, result.error)
            self.assertTrue(result.final_pdf.is_file())


def _run(launch_dir: Path, config_path: Path):
    with patch(
        "internagent.paper_orchestra.service.generate_chinese_companion"
    ):
        return asyncio.run(
            run_paper_orchestra(
                launch_dir=launch_dir,
                internagent_config={
                    "models": {
                        "openai": {
                            "base_url": "https://relay.example/v1",
                            "model_name": "text-model",
                        }
                    }
                },
                paper_config_path=config_path,
            )
        )


if __name__ == "__main__":
    unittest.main()
