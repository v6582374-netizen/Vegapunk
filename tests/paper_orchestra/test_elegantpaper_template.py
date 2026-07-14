from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from internagent.paper_orchestra.utils.pdf_utils import compile_latex

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = REPOSITORY_ROOT / "tex_templates" / "elegantpaper"


class ElegantPaperTemplateTest(unittest.TestCase):
    def test_chinese_template_compiles_with_xelatex_and_biber(self) -> None:
        for executable in ("latexmk", "xelatex", "biber"):
            if shutil.which(executable) is None:
                self.skipTest(
                    f"{executable} is required for the ElegantPaper smoke test"
                )

        with self.subTest("workspace uses the shared template resources"):
            import tempfile

            with tempfile.TemporaryDirectory() as temporary_directory:
                workspace = Path(temporary_directory) / "paper"
                workspace.mkdir()
                shutil.copyfile(
                    TEMPLATE_ROOT / "reference.bib", workspace / "references.bib"
                )
                template_path = workspace / "template.tex"
                template_path.write_text(
                    (TEMPLATE_ROOT / "template.tex").read_text(encoding="utf-8").replace(
                        "\\printbibliography", "\\nocite{en3}\n\\printbibliography"
                    ),
                    encoding="utf-8",
                )

                pdf_path = compile_latex(
                    work_dir=workspace,
                    tex_path=template_path,
                    output_pdf=workspace / "compiled-template.pdf",
                    log_path=workspace / "logs" / "compile.log",
                    stage="compile_initial_draft",
                    timeout=120,
                    template_dir=TEMPLATE_ROOT,
                )

                self.assertFalse((workspace / "elegantpaper.cls").exists())
                self.assertGreater(pdf_path.stat().st_size, 0)
                pdf_bytes = pdf_path.read_bytes()
                self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
                self.assertTrue(pdf_bytes.rstrip().endswith(b"%%EOF"))
                self.assertGreater((workspace / "template.bbl").stat().st_size, 0)
                self.assertGreater((workspace / "logs" / "compile.log").stat().st_size, 0)
