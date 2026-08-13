from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from vegapunk.experiments_utils_qwen_code import (
    QwenCodeAuthenticationError,
    QwenCodeConfigurationError,
    QwenCodeRunner,
    _final_qwen_message,
    perform_experiments,
)


class QwenCodeRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._dashscope_environment = patch.dict(
            "vegapunk.experiments_utils_qwen_code.os.environ",
            {"DASHSCOPE_API_KEY": "dashscope-key"},
            clear=False,
        )
        self._dashscope_environment.start()

    def tearDown(self) -> None:
        self._dashscope_environment.stop()

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

    def test_uses_official_headless_flags_and_provider_local_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = [{"type": "result", "subtype": "success", "result": "done"}]

            with patch(
                "vegapunk.experiments_utils_qwen_code.subprocess.run",
                return_value=CompletedProcess(
                    ["qwen"], 0, stdout=json.dumps(payload), stderr=""
                ),
            ) as run_command:
                output = QwenCodeRunner(
                    model="qwen/qwen3.6-plus", command="qwen"
                ).run("make the change", cwd=root)

            self.assertEqual(output, "done")
            command = run_command.call_args.args[0]
            self.assertEqual(command[0], "qwen")
            self.assertEqual(command[command.index("--model") + 1], "qwen3.6-plus")
            self.assertEqual(
                command[command.index("--approval-mode") + 1], "yolo"
            )
            self.assertEqual(
                command[command.index("--output-format") + 1], "json"
            )
            self.assertIn("--sandbox=false", command)

    def test_binds_dashscope_credentials_when_openai_key_is_also_present(self) -> None:
        """Qwen Code must not inherit the parent's unrelated OpenAI route."""
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "vegapunk.experiments_utils_qwen_code.os.environ",
            {
                "DASHSCOPE_API_KEY": "dashscope-key",
                "OPENAI_API_KEY": "unrelated-openai-key",
            },
            clear=False,
        ):
            payload = [{"type": "result", "subtype": "success", "result": "done"}]
            with patch(
                "vegapunk.experiments_utils_qwen_code.subprocess.run",
                return_value=CompletedProcess(
                    ["qwen"], 0, stdout=json.dumps(payload), stderr=""
                ),
            ) as run_command:
                QwenCodeRunner(model="qwen/qwen3-max", command="qwen").run(
                    "make the change", cwd=Path(directory)
                )

            command = run_command.call_args.args[0]
            environment = run_command.call_args.kwargs["env"]
            self.assertEqual(
                command[command.index("--auth-type") + 1], "openai"
            )
            self.assertEqual(
                command[command.index("--openai-base-url") + 1],
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            self.assertEqual(environment["OPENAI_API_KEY"], "dashscope-key")

    def test_requires_dashscope_key_instead_of_falling_back_to_openai_key(self) -> None:
        """A missing Qwen credential must fail before a DashScope request is made."""
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "vegapunk.experiments_utils_qwen_code.os.environ",
            {"OPENAI_API_KEY": "unrelated-openai-key"},
            clear=True,
        ), patch("vegapunk.experiments_utils_qwen_code.subprocess.run") as run_command:
            with self.assertRaises(QwenCodeConfigurationError):
                QwenCodeRunner(command="qwen").run(
                    "make the change", cwd=Path(directory)
                )

            run_command.assert_not_called()

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
