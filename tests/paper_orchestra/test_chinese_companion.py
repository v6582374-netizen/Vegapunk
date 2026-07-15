from __future__ import annotations

import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from internagent.paper_orchestra.chinese_companion import (
    generate_chinese_companion,
)


class ChineseCompanionTest(unittest.TestCase):
    def test_generates_complete_chinese_tex_and_pdf_without_changing_english(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            work_dir = run_dir / "content_refinement_workdir"
            work_dir.mkdir()
            source_tex = work_dir / "final_refined_paper.tex"
            english = r"""\documentclass{article}
\title{English title}
\begin{document}
English evidence \citep{Keep2024} and $R^2=0.95$.
\end{document}
"""
            source_tex.write_text(english, encoding="utf-8")
            translated = r"""```latex
\documentclass{article}
\title{中文标题}
\begin{document}
中文证据 \citep{Keep2024} and $R^2=0.95$.
\end{document}
```"""

            def run_command(command, *, cwd, **kwargs):
                if command[0] == "xelatex":
                    (Path(cwd) / "final_paper_zh_CN.pdf").write_bytes(
                        b"%PDF-1.4\ntranslated\n%%EOF"
                    )
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch(
                "internagent.paper_orchestra.chinese_companion."
                "PaperOrchestraResponsesRuntime"
            ) as runtime_type, mock.patch(
                "internagent.paper_orchestra.chinese_companion.subprocess.run",
                side_effect=run_command,
            ):
                runtime_type.return_value.generate_text.return_value = (
                    translated
                )

                generate_chinese_companion(
                    run_dir=run_dir,
                    provider_config={
                        "base_url": "https://relay.example/v1",
                        "api_key": "secret",
                    },
                    model_name="writer-model",
                )

            self.assertEqual(source_tex.read_text(encoding="utf-8"), english)
            chinese_tex = work_dir / "final_paper.zh-CN.tex"
            chinese = chinese_tex.read_text(encoding="utf-8")
            self.assertIn(r"\usepackage[UTF8,fontset=fandol]{ctex}", chinese)
            self.assertIn("中文标题", chinese)
            self.assertIn(r"\citep{Keep2024}", chinese)
            self.assertIn(r"$R^2=0.95$", chinese)
            self.assertEqual(
                (run_dir / "final_paper.zh-CN.pdf").read_bytes(),
                b"%PDF-1.4\ntranslated\n%%EOF",
            )
            runtime_type.assert_called_once()
            call = runtime_type.return_value.generate_text.call_args
            self.assertEqual(call.kwargs["model_name"], "writer-model")
            self.assertEqual(len(call.kwargs["content"]), 1)
            self.assertIn(english, call.kwargs["content"][0].text)

    @unittest.skipUnless(
        shutil.which("xelatex") and shutil.which("bibtex"),
        "XeLaTeX and BibTeX are required",
    )
    def test_compiles_chinese_with_the_installed_tex_toolchain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            work_dir = run_dir / "content_refinement_workdir"
            work_dir.mkdir()
            (work_dir / "final_refined_paper.tex").write_text(
                r"""\documentclass{article}
\begin{document}
English paper.
\end{document}
""",
                encoding="utf-8",
            )
            translated = r"""\documentclass{article}
\begin{document}
中文论文。
\end{document}
"""

            with mock.patch(
                "internagent.paper_orchestra.chinese_companion."
                "PaperOrchestraResponsesRuntime"
            ) as runtime_type:
                runtime_type.return_value.generate_text.return_value = (
                    translated
                )
                generate_chinese_companion(
                    run_dir=run_dir,
                    provider_config={"base_url": "https://relay.example/v1"},
                    model_name="writer-model",
                )

            pdf = (run_dir / "final_paper.zh-CN.pdf").read_bytes()
            self.assertTrue(pdf.startswith(b"%PDF-"))
            self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))


if __name__ == "__main__":
    unittest.main()
