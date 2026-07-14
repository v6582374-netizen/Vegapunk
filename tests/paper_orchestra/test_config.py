from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from internagent.paper_orchestra.config import load_paper_config


class PaperConfigTest(unittest.TestCase):
    def test_loads_and_resolves_isolated_paper_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template_dir = root / "templates" / "elegantpaper"
            template_dir.mkdir(parents=True)
            (template_dir / "template.tex").write_text("template", encoding="utf-8")
            (template_dir / "guidelines.md").write_text("rules", encoding="utf-8")
            config_path = root / "paper_orchestra.yaml"
            config_path.write_text(
                """template_dir: templates/elegantpaper
layout_review_enabled: true
max_content_refinement_iterations: 3
max_format_correction_iterations: 1
draft_batch_max_chars: 120000
plotting_max_critic_rounds: 3
image_generation:
  base_url: https://yunwu.ai/v1
  model: gemini-3-pro-image-preview
  api_key_env: PAPER_ORCHESTRA_IMAGE_API_KEY
""",
                encoding="utf-8",
            )

            config = load_paper_config(config_path, repository_root=root)

            self.assertEqual(config.template_dir, template_dir.resolve())
            self.assertTrue(config.layout_review_enabled)
            self.assertEqual(config.max_content_refinement_iterations, 3)
            self.assertEqual(config.max_format_correction_iterations, 1)
            self.assertEqual(config.draft_batch_max_chars, 120000)
            self.assertEqual(config.plotting_max_critic_rounds, 3)
            self.assertEqual(
                config.image_generation.base_url, "https://yunwu.ai/v1"
            )
            self.assertEqual(
                config.image_generation.model, "gemini-3-pro-image-preview"
            )
            self.assertEqual(
                config.image_generation.api_key_env,
                "PAPER_ORCHESTRA_IMAGE_API_KEY",
            )
