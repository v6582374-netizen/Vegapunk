from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from vegapunk.experiments_utils_qwen_code import (
    QwenCodeAuthenticationError,
    QwenCodeRunner,
    _final_qwen_message,
    perform_experiments,
)


class QwenCodeRunnerTest(unittest.TestCase):
    def test_extracts_terminal_result_event(self) -> None:
        payload = [
            {"type": "assistant", "message": {"content": [{"text": "draft"}]}},
            {"type": "result", "subtype": "success", "result": "ALL_COMPLETED"},
        ]
        self.assertEqual(_final_qwen_message(json.dumps(payload)), "ALL_COMPLETED")

    def test_extracts_terminal_result_from_json_event_stream(self) -> None:
        """Qwen Code may emit consecutive JSON event documents, not one array."""
        stdout = "\n".join(
            [
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {"content": [{"text": "draft"}]},
                    }
                ),
                json.dumps(
                    {
                        "type": "result",
                        "subtype": "success",
                        "result": "ALL_COMPLETED",
                    }
                ),
            ]
        )

        self.assertEqual(_final_qwen_message(stdout), "ALL_COMPLETED")

    def test_protocol_error_does_not_reject_a_verified_baseline(self) -> None:
        """A malformed Qwen receipt must not override a successful run artifact."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def qwen_completion(
                command: list[str], *, cwd: str, **_: object
            ) -> CompletedProcess:
                workspace = Path(cwd)
                (workspace / "code").mkdir()
                (workspace / "launcher.sh").write_text(
                    "#!/usr/bin/env bash\n", encoding="utf-8"
                )
                return CompletedProcess(
                    command, 0, stdout="not a Qwen JSON event", stderr=""
                )

            def execute_baseline(
                folder_name: str | Path, run_num: int, **_: object
            ) -> tuple[int, str, None, None]:
                run_directory = Path(folder_name) / f"run_{run_num}"
                run_directory.mkdir()
                (run_directory / "final_info.json").write_text(
                    json.dumps({"accuracy": 0.75}), encoding="utf-8"
                )
                return 0, "continue", None, None

            with patch(
                "vegapunk.experiments_utils_qwen_code.subprocess.run",
                side_effect=qwen_completion,
            ), patch(
                "vegapunk.experiments_utils_codex.run_experiment",
                side_effect=execute_baseline,
            ):
                completed = perform_experiments(
                    {"name": "candidate", "title": "Candidate"},
                    root,
                    max_runs=0,
                    stop_after_baseline=True,
                )

            self.assertTrue(completed)
            self.assertTrue((root / "run_0" / "final_info.json").exists())

    def test_does_not_treat_model_prose_about_authentication_as_an_error(self) -> None:
        payload = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"text": "The patch handles 401 API key authentication."}
                    ]
                },
            },
            {"type": "result", "subtype": "success", "result": "done"},
        ]
        self.assertEqual(_final_qwen_message(json.dumps(payload)), "done")

    def test_does_not_treat_authentication_prose_in_an_event_stream_as_an_error(
        self,
    ) -> None:
        stdout = "\n".join(
            [
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {"text": "The patch handles 401 API key authentication."}
                            ]
                        },
                    }
                ),
                json.dumps(
                    {"type": "result", "subtype": "success", "result": "done"}
                ),
            ]
        )

        self.assertEqual(_final_qwen_message(stdout), "done")

    def test_invokes_qwen_with_only_a_prompt_and_a_workspace(self) -> None:
        """Qwen Code owns its own model and auth; Discovery selects neither."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = [{"type": "result", "subtype": "success", "result": "done"}]

            with patch(
                "vegapunk.experiments_utils_qwen_code.subprocess.run",
                return_value=CompletedProcess(
                    ["qwen"], 0, stdout=json.dumps(payload), stderr=""
                ),
            ) as run_command:
                output = QwenCodeRunner(command="qwen").run(
                    "make the change", cwd=root
                )

            self.assertEqual(output, "done")
            command = run_command.call_args.args[0]
            self.assertEqual(command[0], "qwen")
            # The prompt travels over stdin so a growing research context can
            # never exceed the kernel argv limit (ARG_MAX).
            self.assertNotIn("--prompt", command)
            self.assertNotIn("make the change", command)
            self.assertEqual(run_command.call_args.kwargs["input"], "make the change")
            self.assertEqual(command[command.index("--approval-mode") + 1], "yolo")
            self.assertEqual(command[command.index("--output-format") + 1], "json")
            self.assertIn("--sandbox=false", command)
            self.assertEqual(run_command.call_args.kwargs["cwd"], str(root))
            for owned_by_the_cli in ("--model", "--auth-type", "--openai-base-url"):
                self.assertNotIn(owned_by_the_cli, command)

    def test_does_not_hand_discovery_provider_credentials_to_the_cli(self) -> None:
        """The Launch's own API key must not become Qwen Code's credential."""
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "vegapunk.experiments_utils_qwen_code.os.environ",
            {"OPENAI_API_KEY": "discovery-relay-key"},
            clear=True,
        ):
            payload = [{"type": "result", "subtype": "success", "result": "done"}]
            with patch(
                "vegapunk.experiments_utils_qwen_code.subprocess.run",
                return_value=CompletedProcess(
                    ["qwen"], 0, stdout=json.dumps(payload), stderr=""
                ),
            ) as run_command:
                QwenCodeRunner(command="qwen").run(
                    "make the change", cwd=Path(directory)
                )

            environment = run_command.call_args.kwargs["env"]
            self.assertEqual(environment["OPENAI_API_KEY"], "discovery-relay-key")
            self.assertNotIn("OPENAI_BASE_URL", environment)

    def test_runs_without_any_discovery_provider_credential_present(self) -> None:
        """A Launch with no Qwen credential must still reach the installed CLI."""
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "vegapunk.experiments_utils_qwen_code.os.environ",
            {},
            clear=True,
        ):
            payload = [{"type": "result", "subtype": "success", "result": "done"}]
            with patch(
                "vegapunk.experiments_utils_qwen_code.subprocess.run",
                return_value=CompletedProcess(
                    ["qwen"], 0, stdout=json.dumps(payload), stderr=""
                ),
            ) as run_command:
                output = QwenCodeRunner(command="qwen").run(
                    "make the change", cwd=Path(directory)
                )

            self.assertEqual(output, "done")
            run_command.assert_called_once()

    def test_rejects_authentication_error_with_success_exit_code(self) -> None:
        """Qwen Code can encode an upstream 401 in a successful JSON event."""
        with tempfile.TemporaryDirectory() as directory:
            payload = [
                {
                    "type": "result",
                    "subtype": "success",
                    "result": "[API Error: 401 Incorrect API key provided]",
                }
            ]

            with patch(
                "vegapunk.experiments_utils_qwen_code.subprocess.run",
                return_value=CompletedProcess(
                    ["qwen"], 0, stdout=json.dumps(payload), stderr=""
                ),
            ):
                with self.assertRaises(QwenCodeAuthenticationError):
                    QwenCodeRunner(command="qwen").run(
                        "make the change", cwd=Path(directory)
                    )

    def test_authentication_error_stops_before_launcher_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = [
                {
                    "type": "result",
                    "subtype": "success",
                    "result": "[API Error: 401 Incorrect API key provided]",
                }
            ]
            with patch(
                "vegapunk.experiments_utils_qwen_code.subprocess.run",
                return_value=CompletedProcess(
                    ["qwen"], 0, stdout=json.dumps(payload), stderr=""
                ),
            ), patch(
                "vegapunk.experiments_utils_codex.run_experiment"
            ) as run_experiment:
                with self.assertRaises(QwenCodeAuthenticationError):
                    perform_experiments(
                        {"name": "candidate", "title": "Candidate"},
                        directory,
                        max_runs=1,
                    )

            run_experiment.assert_not_called()


if __name__ == "__main__":
    unittest.main()
