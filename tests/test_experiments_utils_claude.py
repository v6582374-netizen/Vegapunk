from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from internagent.experiments_utils_claude import perform_experiments


class PerformExperimentsArtifactTest(unittest.TestCase):
    IDEA = {
        "name": "artifact-check",
        "description": "produce a measured improvement",
        "method": "run the experiment",
    }

    def _perform(self, directory: str) -> bool:
        with patch(
            "internagent.experiments_utils_claude.ClaudeCodeRunner.run",
            return_value="ALL_COMPLETED",
        ), patch(
            "internagent.experiments_utils_claude._generate_report_with_claude"
        ):
            return perform_experiments(
                self.IDEA,
                Path(directory),
                max_runs=1,
            )

    def _write_artifact(self, directory: str, payload: object) -> None:
        run_directory = Path(directory) / "run_1"
        run_directory.mkdir()
        content = payload if isinstance(payload, str) else json.dumps(payload)
        (run_directory / "final_info.json").write_text(
            content,
            encoding="utf-8",
        )

    def test_completion_without_an_improvement_artifact_is_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = self._perform(directory)

        self.assertFalse(completed)

    def test_completion_with_numeric_improvement_metrics_is_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self._write_artifact(
                directory, {"task": {"means": {"accuracy": 0.91}}}
            )
            completed = self._perform(directory)

        self.assertTrue(completed)

    def test_completion_with_flat_numeric_metrics_is_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self._write_artifact(
                directory,
                {
                    "combined_score": 0.08,
                    "mean_r2": 0.94,
                    "config": {"seed": 20260708},
                },
            )
            completed = self._perform(directory)

        self.assertTrue(completed)

    def test_completion_with_empty_metrics_is_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self._write_artifact(directory, {"task": {"means": {}}})
            completed = self._perform(directory)

        self.assertFalse(completed)

    def test_completion_with_malformed_final_info_is_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self._write_artifact(directory, "{not-json")
            completed = self._perform(directory)

        self.assertFalse(completed)

    def test_completion_with_only_numeric_metadata_is_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self._write_artifact(directory, {"metadata": {"seed": "1"}})
            completed = self._perform(directory)

        self.assertFalse(completed)


if __name__ == "__main__":
    unittest.main()
