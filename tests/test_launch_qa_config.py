from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from launch_qa import _load_qa_config


class LaunchQAConfigTest(unittest.TestCase):
    def test_qa_inherits_the_shared_openai_runtime_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.yaml"
            config_path.write_text(
                """models:
  default_provider: openrouter
  openai:
    model_name: gpt-5.6-sol
    api_mode: responses
    reasoning:
      effort: xhigh
agents:
  dr:
    enabled: true
    mode: complex
""",
                encoding="utf-8",
            )

            model_name, dr_config = _load_qa_config(str(config_path))

        self.assertEqual(model_name, "gpt-5.6-sol")
        self.assertEqual(dr_config["mode"], "qa")
        self.assertEqual(
            dr_config["_global_config"]["models"]["openai"]["api_mode"],
            "responses",
        )


if __name__ == "__main__":
    unittest.main()
