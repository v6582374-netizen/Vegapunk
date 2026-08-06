from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from unittest.mock import patch

from vegapunk.experiments_utils_codex import CodexRunner, perform_experiments


class PerformExperimentsArtifactTest(unittest.TestCase):
    IDEA = {
        "name": "artifact-check",
        "description": "produce a measured improvement",
        "method": "run the experiment",
    }

    def _perform(self, directory: str) -> bool:
        with patch(
            "vegapunk.experiments_utils_codex.CodexRunner.run",
            return_value="ALL_COMPLETED",
        ), patch(
            "vegapunk.experiments_utils_codex._generate_report_with_codex"
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


class CodexRunnerTest(unittest.TestCase):
    def test_runner_maps_canonical_provider_model_to_codex_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            def complete_codex(command: list[str], **_: object) -> CompletedProcess:
                output_path = Path(
                    command[command.index("--output-last-message") + 1]
                )
                output_path.write_text("finished", encoding="utf-8")
                return CompletedProcess(command, 0, stdout="", stderr="")

            with patch(
                "vegapunk.experiments_utils_codex.subprocess.run",
                side_effect=complete_codex,
            ) as run_command:
                CodexRunner(model="qwen:qwen3-max").run(
                    "run the exact experiment", cwd=root
                )

            command = run_command.call_args.args[0]
            self.assertEqual(command[command.index("--model") + 1], "qwen3-max")
            self.assertNotIn("model_provider=qwen", command)

    def test_runner_can_override_codex_model_provider_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            def complete_codex(command: list[str], **_: object) -> CompletedProcess:
                output_path = Path(
                    command[command.index("--output-last-message") + 1]
                )
                output_path.write_text("finished", encoding="utf-8")
                return CompletedProcess(command, 0, stdout="", stderr="")

            with patch(
                "vegapunk.experiments_utils_codex.subprocess.run",
                side_effect=complete_codex,
            ) as run_command:
                CodexRunner(
                    model="qwen:qwen3-max",
                    model_provider="qwen",
                ).run("run the exact experiment", cwd=root)

            command = run_command.call_args.args[0]
            self.assertIn("model_provider=qwen", command)

    def test_runner_reads_the_last_message_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            jsonl = '{"type":"turn.completed","status":"completed"}\n'

            def complete_codex(command: list[str], **_: object) -> CompletedProcess:
                output_path = Path(
                    command[command.index("--output-last-message") + 1]
                )
                output_path.write_text("finished", encoding="utf-8")
                return CompletedProcess(
                    command,
                    0,
                    stdout=jsonl,
                    stderr="provider warning",
                )

            with patch(
                "vegapunk.experiments_utils_codex.subprocess.run",
                side_effect=complete_codex,
            ) as run_command:
                output = CodexRunner(model="gpt-5.6-sol").run(
                    "run the exact experiment", cwd=root
                )

            command = run_command.call_args.args[0]
            self.assertEqual(command[:2], ["codex", "exec"])
            self.assertEqual(command[command.index("--cd") + 1], str(root))
            self.assertEqual(command[command.index("--model") + 1], "gpt-5.6-sol")
            self.assertEqual(command[command.index("--sandbox") + 1], "workspace-write")
            self.assertEqual(
                command[command.index("-c") + 1], "approval_policy=never"
            )
            second_config = command.index("-c", command.index("-c") + 1)
            self.assertEqual(
                command[second_config + 1],
                "sandbox_workspace_write.network_access=true",
            )
            self.assertIn("--skip-git-repo-check", command)
            self.assertIn("--json", command)
            output_path = Path(
                command[command.index("--output-last-message") + 1]
            )
            self.assertEqual(output_path.parent, root)
            self.assertEqual(output, "finished")

    def test_runner_rejects_success_text_from_a_failed_process(self) -> None:
        completed = CompletedProcess(
            ["codex", "exec"],
            7,
            stdout='{"type":"turn.completed"}\n',
            stderr="fatal cli failure",
        )

        with patch(
            "vegapunk.experiments_utils_codex.subprocess.run",
            return_value=completed,
        ):
            with self.assertRaises(CalledProcessError) as raised:
                CodexRunner(model="gpt-5.6-sol").run("run experiment")

        self.assertEqual(raised.exception.returncode, 7)
        self.assertEqual(raised.exception.stdout, completed.stdout)
        self.assertEqual(raised.exception.stderr, completed.stderr)

    def test_runner_does_not_return_jsonl_when_final_message_is_missing(self) -> None:
        completed = CompletedProcess(
            ["codex", "exec"],
            0,
            stdout='{"type":"turn.completed"}\n',
            stderr="",
        )

        with patch(
            "vegapunk.experiments_utils_codex.subprocess.run",
            return_value=completed,
        ), self.assertRaises(RuntimeError) as raised:
            CodexRunner(model="gpt-5.6-sol").run("run experiment")

        self.assertIn("final message", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
