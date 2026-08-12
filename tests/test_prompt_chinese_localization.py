from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

from vegapunk.prompt_library import DEFAULT_LIBRARY_ROOT

BASELINE_ROOT = DEFAULT_LIBRARY_ROOT.parent / "prompt_baseline"


class PromptChineseLocalizationTest(unittest.TestCase):
    def test_every_runtime_template_contains_chinese_instruction_text(self) -> None:
        catalog = yaml.safe_load(
            (DEFAULT_LIBRARY_ROOT / "catalog.yaml").read_text(encoding="utf-8")
        )
        missing_chinese: list[str] = []
        for entry in catalog["prompts"]:
            text = (DEFAULT_LIBRARY_ROOT / entry["file"]).read_text(encoding="utf-8")
            if not re.search(r"[\u4e00-\u9fff]", text):
                missing_chinese.append(entry["id"])

        self.assertEqual(
            missing_chinese,
            [],
            "Runtime prompt templates must contain Chinese instruction text: "
            + ", ".join(missing_chinese),
        )

    def test_desktop_reset_baseline_matches_the_runtime_templates(self) -> None:
        catalog = yaml.safe_load(
            (DEFAULT_LIBRARY_ROOT / "catalog.yaml").read_text(encoding="utf-8")
        )
        mismatches = [
            entry["id"]
            for entry in catalog["prompts"]
            if (DEFAULT_LIBRARY_ROOT / entry["file"]).read_text(encoding="utf-8")
            != (BASELINE_ROOT / entry["file"]).read_text(encoding="utf-8")
        ]

        self.assertEqual(
            mismatches,
            [],
            "Desktop reset baselines must match the runtime prompt templates: "
            + ", ".join(mismatches),
        )
