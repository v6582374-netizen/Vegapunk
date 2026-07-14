from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from internagent.paper_orchestra.checkpoint import PaperOrchestraCheckpoint
from internagent.paper_orchestra.pipeline import run_writing_pipeline
from tests.paper_orchestra.test_agents import RecordingModel


ADAPTIVE_PAPER = r"""\documentclass[lang=cn]{elegantpaper}
\title{Evidence-Grounded Paper}\author{}\institute{}
\begin{document}\begin{abstract}摘要。\end{abstract}
\section{问题定义}A\section{方法设计}B\section{结果分析}C
\section{适用边界}D\section{结论}E\end{document}"""

REVIEW = {
    "Strengths": [],
    "Weaknesses": [],
    "Questions": [],
    "Originality": 7,
    "Quality": 7,
    "Clarity": 7,
    "Significance": 7,
    "Soundness": 7,
    "Presentation": 7,
    "Contribution": 7,
    "Overall": 7,
    "Confidence": 4,
}

PIPELINE_STAGES = (
    "prepare_latex_workspace",
    "generate_outline",
    "generate_figures",
    "write_introduction_and_related_work",
    "write_remaining_sections",
    "compile_initial_draft",
    "refine_content",
    "review_layout_and_optionally_correct",
    "compile_final",
    "validate_final_outputs",
)


class PipelineTest(unittest.TestCase):
    def test_complete_pipeline_uses_working_material_and_shared_template(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run_dir = root / "paper_orchestra_runs" / "run_001"
            materials_path, evidence_dir, template_dir = _inputs(root)
            model = RecordingModel(
                text_responses=[
                    f"```latex\n{ADAPTIVE_PAPER}\n```",
                    f"```latex\n{ADAPTIVE_PAPER}\n```",
                ],
                json_responses=[
                    {
                        "paper_title": "Evidence-Grounded Paper",
                        "plotting_plan": [],
                        "intro_related_work_plan": {},
                        "section_plan": [],
                    },
                    REVIEW,
                ],
            )
            compile_calls: list[str] = []

            result = asyncio.run(
                run_writing_pipeline(
                    run_dir=run_dir,
                    materials_path=materials_path,
                    evidence_dir=evidence_dir,
                    template_dir=template_dir,
                    candidate_selection=None,
                    model=model,
                    image_generator=None,
                    plotting_max_critic_rounds=3,
                    max_content_refinement_iterations=0,
                    max_format_correction_iterations=1,
                    layout_review_enabled=True,
                    compile_document=_fake_compiler(compile_calls),
                    extract_text=lambda path: f"PDF TEXT {path.name}",
                    render_pages=_fake_renderer,
                )
            )

            self.assertEqual(len(model.json_calls), 2)
            self.assertEqual(len(model.text_calls), 2)
            self.assertEqual(len(model.run_calls), 1)
            self.assertEqual(compile_calls, ["compile_initial_draft", "compile_final"])
            self.assertTrue(result.final_tex.is_file())
            self.assertTrue(result.final_pdf.is_file())
            self.assertFalse((run_dir / "latex_writeup" / "elegantpaper.cls").exists())

    def test_resume_after_layout_interruption_does_not_repeat_completed_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run_dir = root / "paper_orchestra_runs" / "run_001"
            materials_path, evidence_dir, template_dir = _inputs(root)
            checkpoint = PaperOrchestraCheckpoint.open(
                run_dir=run_dir,
                paper_orchestra_run_id="run_001",
                launch_id="launch",
                resolved_config={},
                model_identity={},
                stage_ids=PIPELINE_STAGES,
            )
            first_model = RecordingModel(
                text_responses=[
                    f"```latex\n{ADAPTIVE_PAPER}\n```",
                    f"```latex\n{ADAPTIVE_PAPER}\n```",
                ],
                json_responses=[
                    {
                        "paper_title": "Evidence-Grounded Paper",
                        "plotting_plan": [],
                        "intro_related_work_plan": {},
                        "section_plan": [],
                    },
                    REVIEW,
                ],
            )
            compiler = _fake_compiler([])

            with self.assertRaisesRegex(RuntimeError, "render interrupted"):
                asyncio.run(
                    run_writing_pipeline(
                        run_dir=run_dir,
                        materials_path=materials_path,
                        evidence_dir=evidence_dir,
                        template_dir=template_dir,
                        candidate_selection=None,
                        model=first_model,
                        image_generator=None,
                        plotting_max_critic_rounds=3,
                        max_content_refinement_iterations=0,
                        max_format_correction_iterations=1,
                        layout_review_enabled=True,
                        compile_document=compiler,
                        extract_text=lambda path: "PDF text",
                        render_pages=lambda pdf, out: (_ for _ in ()).throw(
                            RuntimeError("render interrupted")
                        ),
                        checkpoint=checkpoint,
                    )
                )

            resumed = PaperOrchestraCheckpoint.open(
                run_dir=run_dir,
                paper_orchestra_run_id="run_001",
                launch_id="launch",
                resolved_config={},
                model_identity={},
                stage_ids=PIPELINE_STAGES,
            )
            second_model = RecordingModel()
            asyncio.run(
                run_writing_pipeline(
                    run_dir=run_dir,
                    materials_path=materials_path,
                    evidence_dir=evidence_dir,
                    template_dir=template_dir,
                    candidate_selection=None,
                    model=second_model,
                    image_generator=None,
                    plotting_max_critic_rounds=3,
                    max_content_refinement_iterations=0,
                    max_format_correction_iterations=1,
                    layout_review_enabled=True,
                    compile_document=compiler,
                    extract_text=lambda path: "PDF text",
                    render_pages=_fake_renderer,
                    checkpoint=resumed,
                )
            )

            self.assertEqual(len(second_model.text_calls), 0)
            self.assertEqual(len(second_model.json_calls), 0)
            self.assertEqual(len(second_model.run_calls), 1)


def _inputs(root: Path) -> tuple[Path, Path, Path]:
    materials_path = root / "working_materials" / "paper_materials.md"
    materials_path.parent.mkdir(parents=True)
    materials_path.write_text("authoritative material", encoding="utf-8")
    evidence_dir = root / "evidence"
    figures_dir = evidence_dir / "figures"
    figures_dir.mkdir(parents=True)
    (evidence_dir / "citation_map.json").write_text("{}", encoding="utf-8")
    (evidence_dir / "references.bib").write_text(
        "% No approved references.\n", encoding="utf-8"
    )
    (figures_dir / "info.json").write_text("[]", encoding="utf-8")
    template_dir = root / "template"
    template_dir.mkdir()
    (template_dir / "template.tex").write_text(
        "\\documentclass{elegantpaper}", encoding="utf-8"
    )
    (template_dir / "guidelines.md").write_text("rules", encoding="utf-8")
    (template_dir / "elegantpaper.cls").write_text("class", encoding="utf-8")
    return materials_path, evidence_dir, template_dir


def _fake_compiler(calls: list[str]):
    def compile_document(**kwargs: object) -> Path:
        output_pdf = kwargs["output_pdf"]
        log_path = kwargs["log_path"]
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        output_pdf.write_bytes(b"%PDF-fake\n%%EOF")
        log_path.write_text("compiled", encoding="utf-8")
        calls.append(str(kwargs["stage"]))
        return output_pdf

    return compile_document


def _fake_renderer(pdf_path: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / "page.png"
    image_path.write_bytes(b"page")
    return [image_path]


if __name__ == "__main__":
    unittest.main()
