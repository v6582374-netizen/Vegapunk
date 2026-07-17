from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launch_qa import _load_qa_config


class LaunchQAConfigTest(unittest.TestCase):
    def test_qa_injects_the_catalog_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.yaml"
            config_path.write_text(
                """model_catalog_path: config/model_catalog.yaml
agents:
  dr:
    enabled: true
    mode: complex
""",
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
                runtime, dr_config = _load_qa_config(str(config_path))

        self.assertEqual(runtime.catalog.active_text_model, "relay/gpt-5.6-sol")
        self.assertEqual(dr_config["mode"], "qa")
        self.assertIs(dr_config["_runtime"], runtime)


if __name__ == "__main__":
    unittest.main()
