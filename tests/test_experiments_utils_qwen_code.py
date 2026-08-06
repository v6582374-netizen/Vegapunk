from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from vegapunk.experiments_utils_qwen_code import QwenCodeRunner, _final_qwen_message


class QwenCodeRunnerTest(unittest.TestCase):
    def test_extracts_terminal_result_event(self) -> None:
        payload = [
            {"type": "assistant", "message": {"content": [{"text": "draft"}]}},
            {"type": "result", "subtype": "success", "result": "ALL_COMPLETED"},
        ]
        self.assertEqual(_final_qwen_message(json.dumps(payload)), "ALL_COMPLETED")

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


if __name__ == "__main__":
    unittest.main()
