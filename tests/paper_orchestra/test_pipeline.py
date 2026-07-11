from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from tests.paper_orchestra.test_agents import RecordingModel

from internagent.paper_orchestra.checkpoint import DossierCheckpoint
from internagent.paper_orchestra.pipeline import (
    run_writing_pipeline,
    validate_candidate_disclosures,
)


class PipelineTest(unittest.TestCase):
    def test_disclosure_validation_requires_exact_selection_facts(self) -> None:
        selection = {
            "paper_candidate_round": {
                "round": 1,
                "skipped_later_rounds": [2],
                "skipped_later_round_facts": [
                    {
                        "round": 2,
                        "session_id": "session_2",
                        "result_count": 1,
                        "successful_candidate_count": 0,
                    }
                ],
            },
            "criterion": {
                "source": "model_inference",
                "primary_metric": "validation_loss",
                "optimization_direction": "minimize",
                "source_paths": ["prompt.json"],
            },
            "successful_candidates": [
                {
                    "idea_name": "method_a",
                    "exclusion_reason": "primary_metric_missing_or_non_finite",
                },
                {
                    "idea_name": "method_b",
                    "primary_metric_value": 0.42,
                    "exclusion_reason": None,
                },
            ],
            "selection_method": "random_tie",
            "fallback_reason": "exact_primary_metric_tie",
            "fallback_pool": [
                {"idea_name": "method_b"},
                {"idea_name": "method_c"},
            ],
            "selected_candidate": {"idea_name": "method_b"},
        }
        incomplete = r"""\section{研究过程}\subsection{候选选择}
模型的主观判断是使用 validation\_loss，并从 method\_b 与 method\_c 中随机选择。
"""
        with self.assertRaises(ValueError):
            validate_candidate_disclosures(incomplete, selection)

        complete = r"""\section{研究过程}\subsection{候选选择}
由于第 2 轮无成功候选，系统回退到第 1 轮。
模型的主观判断依据 prompt.json，使用 validation\_loss，方向为 minimize；method\_b 的比较值为 0.42。
method\_a 因 primary\_metric\_missing\_or\_non\_finite 被排除。
method\_b 与 method\_c 形成并列集合，因 exact\_primary\_metric\_tie 随机选择。
"""
        validate_candidate_disclosures(complete, selection)

    def test_complete_async_pipeline_uses_one_shared_model(self) -> None:
        complete_latex = r"""\documentclass[lang=cn]{elegantpaper}
\title{Exact title}\author{}\institute{}
\begin{document}\begin{abstract}摘要。\end{abstract}
\section{引言}A\section{相关工作}B\section{方法}C\section{实验}D
\section{研究过程}\subsection{候选选择}E\section{复现指南}F
\section{局限性与适用边界}G\section{结论}H\end{document}"""
        outline = {
            "intro_related_work_plan": {},
            "section_plan": [],
        }
        review = {
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
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run_dir = root / "dossier_runs" / "primary"
            raw_dir = run_dir / "raw_materials"
            figures_dir = raw_dir / "figures"
            figures_dir.mkdir(parents=True)
            (raw_dir / "idea.md").write_text("# Exact title\n", encoding="utf-8")
            (raw_dir / "experimental_log.md").write_text(
                "# Experimental log\n", encoding="utf-8"
            )
            (raw_dir / "citation_map.json").write_text("{}", encoding="utf-8")
            (raw_dir / "references.bib").write_text("", encoding="utf-8")
            (figures_dir / "info.json").write_text("[]", encoding="utf-8")
            template_dir = root / "template"
            template_dir.mkdir()
            (template_dir / "template.tex").write_text(
                "\\documentclass{article}", encoding="utf-8"
            )
            (template_dir / "guidelines.md").write_text(
                "guidelines", encoding="utf-8"
            )
            model = RecordingModel(
                text_responses=[
                    "```latex\n\\documentclass{article}\n```",
                    f"```latex\n{complete_latex}\n```",
                ],
                json_responses=[outline, review],
            )
            compile_calls: list[str] = []

            def fake_compile(**kwargs: object) -> Path:
                output_pdf = kwargs["output_pdf"]
                log_path = kwargs["log_path"]
                output_pdf.parent.mkdir(parents=True, exist_ok=True)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                output_pdf.write_bytes(b"%PDF-fake\n%%EOF")
                log_path.write_text("compiled", encoding="utf-8")
                compile_calls.append(kwargs["stage"])
                return output_pdf

            def fake_render(pdf_path: Path, output_dir: Path) -> list[Path]:
                output_dir.mkdir(parents=True, exist_ok=True)
                image_path = output_dir / "page_001.png"
                image_path.write_bytes(b"page")
                return [image_path]

            result = asyncio.run(
                run_writing_pipeline(
                    run_dir=run_dir,
                    raw_materials_dir=raw_dir,
                    template_dir=template_dir,
                    candidate_selection={"selection_method": "sole_success"},
                    paper_title="Exact title",
                    model=model,
                    max_content_refinement_iterations=0,
                    max_format_correction_iterations=1,
                    layout_review_enabled=True,
                    compile_document=fake_compile,
                    extract_text=lambda path: f"PDF TEXT {path.name}",
                    render_pages=fake_render,
                )
            )

            self.assertEqual(len(model.json_calls), 2)
            self.assertEqual(len(model.text_calls), 2)
            self.assertEqual(len(model.message_calls), 1)
            self.assertEqual(compile_calls, ["compile_initial_draft", "compile_final"])
            self.assertEqual(result.final_tex.name, "final_refined_paper.tex")
            self.assertEqual(result.final_pdf.name, "final_paper.pdf")
            self.assertTrue(result.final_tex.is_file())
            self.assertTrue(result.final_pdf.is_file())

    def test_resume_after_layout_failure_does_not_rerun_outline(self) -> None:
        complete_latex = r"""\documentclass[lang=cn]{elegantpaper}
\title{Exact title}\author{}\institute{}
\begin{document}\begin{abstract}摘要。\end{abstract}
\section{引言}A\section{相关工作}B\section{方法}C\section{实验}D
\section{研究过程}\subsection{候选选择}E\section{复现指南}F
\section{局限性与适用边界}G\section{结论}H\end{document}"""
        review = {
            "Strengths": [], "Weaknesses": [], "Questions": [],
            "Originality": 7, "Quality": 7, "Clarity": 7,
            "Significance": 7, "Soundness": 7, "Presentation": 7,
            "Contribution": 7, "Overall": 7, "Confidence": 4,
        }
        pipeline_stages = (
            "prepare_latex_workspace", "generate_outline",
            "write_introduction_and_related_work", "write_remaining_sections",
            "compile_initial_draft", "refine_content",
            "review_layout_and_optionally_correct", "compile_final",
            "validate_final_outputs_and_disclosures",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run_dir = root / "primary"
            raw_dir = run_dir / "raw_materials"
            (raw_dir / "figures").mkdir(parents=True)
            for name, content in (
                ("idea.md", "# Exact title\n"),
                ("experimental_log.md", "# Experimental log\n"),
                ("citation_map.json", "{}"),
                ("references.bib", ""),
                ("figures/info.json", "[]"),
            ):
                (raw_dir / name).write_text(content, encoding="utf-8")
            template_dir = root / "template"
            template_dir.mkdir()
            (template_dir / "template.tex").write_text("\\documentclass{article}", encoding="utf-8")
            (template_dir / "guidelines.md").write_text("rules", encoding="utf-8")

            def fake_compile(**kwargs: object) -> Path:
                output_pdf = kwargs["output_pdf"]
                log_path = kwargs["log_path"]
                output_pdf.parent.mkdir(parents=True, exist_ok=True)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                output_pdf.write_bytes(b"%PDF-fake\n%%EOF")
                log_path.write_text("compiled", encoding="utf-8")
                return output_pdf

            checkpoint = DossierCheckpoint.open(
                run_dir=run_dir,
                dossier_run_id="primary",
                launch_id="launch",
                resolved_config={},
                model_identity={},
                stage_ids=pipeline_stages,
            )
            first_model = RecordingModel(
                text_responses=[
                    "```latex\n\\documentclass{article}\n```",
                    f"```latex\n{complete_latex}\n```",
                ],
                json_responses=[
                    {"intro_related_work_plan": {}, "section_plan": []}, review,
                ],
            )

            with self.assertRaises(RuntimeError):
                asyncio.run(
                    run_writing_pipeline(
                        run_dir=run_dir, raw_materials_dir=raw_dir,
                        template_dir=template_dir,
                        candidate_selection={"selection_method": "sole_success"},
                        paper_title="Exact title", model=first_model,
                        max_content_refinement_iterations=0,
                        max_format_correction_iterations=1,
                        layout_review_enabled=True,
                        compile_document=fake_compile,
                        extract_text=lambda path: "PDF text",
                        render_pages=lambda pdf, out: (_ for _ in ()).throw(
                            RuntimeError("render interrupted")
                        ),
                        checkpoint=checkpoint,
                    )
                )

            resumed = DossierCheckpoint.open(
                run_dir=run_dir, dossier_run_id="primary", launch_id="launch",
                resolved_config={}, model_identity={}, stage_ids=pipeline_stages,
            )
            second_model = RecordingModel()

            def render_pages(pdf_path: Path, output_dir: Path) -> list[Path]:
                output_dir.mkdir(parents=True, exist_ok=True)
                image_path = output_dir / "page.png"
                image_path.write_bytes(b"page")
                return [image_path]

            asyncio.run(
                run_writing_pipeline(
                    run_dir=run_dir, raw_materials_dir=raw_dir,
                    template_dir=template_dir,
                    candidate_selection={"selection_method": "sole_success"},
                    paper_title="Exact title", model=second_model,
                    max_content_refinement_iterations=0,
                    max_format_correction_iterations=1,
                    layout_review_enabled=True,
                    compile_document=fake_compile,
                    extract_text=lambda path: "PDF text",
                    render_pages=render_pages,
                    checkpoint=resumed,
                )
            )

            self.assertEqual(len(second_model.text_calls), 0)
            self.assertEqual(len(second_model.json_calls), 0)
            self.assertEqual(len(second_model.message_calls), 1)
