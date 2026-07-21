from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vegapunk.paper_orchestra.config import load_paper_config


class PaperConfigTest(unittest.TestCase):
    def test_resolves_vendor_and_template_without_a_second_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            vendor_root = root / "third_party" / "paper_orchestra"
            template_dir = vendor_root / "templates" / "iclr2025"
            template_dir.mkdir(parents=True)
            (vendor_root / "paper_writing_cli.py").write_text(
                "# upstream CLI", encoding="utf-8"
            )
            (template_dir / "template.tex").write_text(
                "template", encoding="utf-8"
            )
            (template_dir / "guidelines.md").write_text(
                "rules", encoding="utf-8"
            )
            config_path = root / "paper_orchestra.yaml"
            config_path.write_text(
                """vendor_root: third_party/paper_orchestra
template_dir: templates/iclr2025
use_plotting: true
plotting_max_critic_rounds: 3
research_cutoff: null
""",
                encoding="utf-8",
            )

            config = load_paper_config(config_path, repository_root=root)

            self.assertEqual(config.vendor_root, vendor_root.resolve())
            self.assertEqual(config.template_dir, template_dir.resolve())
            self.assertTrue(config.use_plotting)
            self.assertEqual(config.plotting_max_critic_rounds, 3)
            self.assertIsNone(config.research_cutoff)


if __name__ == "__main__":
    unittest.main()
