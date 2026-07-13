from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from internagent.paper_orchestra.data_types import DossierStageError
from internagent.mas.models.runtime import (
    ImageContent,
    ModelRunRequest,
    ModelRunResult,
    OutputText,
)
from internagent.paper_orchestra.autoraters.agent_review import review_paper
from internagent.paper_orchestra.methods.agents.literature_review_agent import (
    LiteratureReviewAgent,
)
from internagent.paper_orchestra.methods.agents.content_refinement_agent import (
    ContentRefinementAgent,
)
from internagent.paper_orchestra.methods.agents.outline_agent import OutlineAgent
from internagent.paper_orchestra.methods.agents.section_writing_agent import (
    SectionWritingAgent,
)


class RecordingModel:
    def __init__(
        self,
        *,
        text_response: str | None = None,
        text_responses: list[str] | None = None,
        json_responses: list[dict[str, object]] | None = None,
    ) -> None:
        self.json_calls: list[dict[str, object]] = []
        self.text_calls: list[dict[str, object]] = []
        self.run_calls: list[ModelRunRequest] = []
        self.json_responses = list(json_responses or [])
        self.text_responses = list(text_responses or [])
        self.text_response = text_response or (
            "```latex\n\\documentclass{article}\n"
            "Approved citation: \\cite{ref001}\n```"
        )

    async def generate_json(self, **kwargs: object) -> dict[str, object]:
        self.json_calls.append(kwargs)
        if self.json_responses:
            return self.json_responses.pop(0)
        return {
            "intro_related_work_plan": {
                "introduction": ["Grounded motivation"],
                "related_work": ["Use approved citations"],
            },
            "section_plan": [
                {"section_title": "方法", "content_bullets": ["Exact method"]}
            ],
        }

    async def generate(self, **kwargs: object) -> str:
        self.text_calls.append(kwargs)
        if self.text_responses:
            return self.text_responses.pop(0)
        return self.text_response

    async def run(self, request: ModelRunRequest) -> ModelRunResult:
        self.run_calls.append(request)
        return ModelRunResult(
            response_id="resp_layout",
            status="completed",
            model="recording-model",
            items=(
                OutputText(
                    text='{"figure_and_tables": {}, "other_issues": []}'
                ),
            ),
        )

    def make_prompt_cache_key(
        self, *, agent_role: str, stable_prefix: str
    ) -> str:
        return f"test:{agent_role}:{len(stable_prefix)}"


class AgentTest(unittest.TestCase):
    def test_layout_correction_rejects_scientific_content_changes(self) -> None:
        original = r"""\documentclass{article}
\title{Exact title}\author{}\institute{}
\begin{document}\begin{abstract}摘要。\end{abstract}
\section{引言}A\section{相关工作}B\section{方法}$x^{10}$\section{实验}D
\section{研究过程}E\section{复现指南}F
\section{局限性与适用边界}G\section{结论}H\end{document}"""
        changed = original.replace(r"x^{10}", r"x^10")
        model = RecordingModel(text_response=f"```latex\n{changed}\n```")
        agent = ContentRefinementAgent(model=model)

        with self.assertRaises(DossierStageError) as raised:
            asyncio.run(
                agent.correct_layout(
                    latex=original,
                    layout_review={"other_issues": []},
                    guidelines="layout only",
                    paper_title="Exact title",
                    citation_map={},
                )
            )

        self.assertEqual(raised.exception.code, "invalid_model_output")

    def test_outline_agent_uses_structured_shared_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            inputs = {}
            for name, content in (
                ("idea.md", "authoritative idea"),
                ("experimental_log.md", "authoritative experiment"),
                ("template.tex", "latex skeleton"),
                ("guidelines.md", "writing constraints"),
            ):
                path = root / name
                path.write_text(content, encoding="utf-8")
                inputs[name] = path
            selection = {"selection_method": "random_fallback"}
            output_path = root / "outline.json"
            model = RecordingModel()
            agent = OutlineAgent(model=model)

            outline = asyncio.run(
                agent.run(
                    idea_file=inputs["idea.md"],
                    experimental_log_file=inputs["experimental_log.md"],
                    latex_template_file=inputs["template.tex"],
                    guidelines_file=inputs["guidelines.md"],
                    candidate_selection=selection,
                    output_path=output_path,
                )
            )

            self.assertIs(agent.model, model)
            self.assertEqual(len(model.json_calls), 1)
            self.assertEqual(
                model.json_calls[0]["checkpoint_key"], "generate_outline"
            )
            self.assertIn(
                "authoritative experiment", model.json_calls[0]["prompt"]
            )
            self.assertIn(
                '"selection_method": "random_fallback"',
                model.json_calls[0]["prompt"],
            )
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), outline)

    def test_literature_agent_writes_only_from_approved_citation_library(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            files = {
                "outline.json": {"intro_related_work_plan": {"introduction": []}},
                "citation_map.json": {
                    "ref001": {
                        "title": "Approved paper",
                        "abstract": "Approved evidence content",
                    }
                },
            }
            for name, value in files.items():
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            for name, content in (
                ("idea.md", "idea"),
                ("experimental_log.md", "experiment"),
                ("template.tex", "template"),
                ("guidelines.md", "guidelines"),
            ):
                (root / name).write_text(content, encoding="utf-8")
            output_path = root / "literature_draft.tex"
            model = RecordingModel()
            agent = LiteratureReviewAgent(model=model)

            latex = asyncio.run(
                agent.run(
                    outline_path=root / "outline.json",
                    idea_path=root / "idea.md",
                    experimental_log_path=root / "experimental_log.md",
                    template_path=root / "template.tex",
                    citation_map_path=root / "citation_map.json",
                    guidelines_path=root / "guidelines.md",
                    output_path=output_path,
                )
            )

            self.assertIs(agent.model, model)
            self.assertEqual(len(model.text_calls), 1)
            self.assertEqual(
                model.text_calls[0]["checkpoint_key"],
                "write_introduction_and_related_work",
            )
            self.assertIn("Approved evidence content", model.text_calls[0]["prompt"])
            self.assertEqual(
                latex,
                "\\documentclass{article}\nApproved citation: \\cite{ref001}",
            )
            self.assertEqual(output_path.read_text(encoding="utf-8"), latex + "\n")

    def test_section_agent_preserves_fixed_narrative_contract(self) -> None:
        complete_latex = r"""\documentclass[lang=cn]{elegantpaper}
\title{Exact research title}
\author{}
\institute{}
\begin{document}
\begin{abstract}摘要内容。\end{abstract}
\section{引言}引言。
\section{相关工作}相关工作 \cite{ref001}。
\section{方法}方法。
\section{实验}实验。
\section{研究过程}使用记录的 random fallback。
\section{复现指南}复现。
\section{局限性与适用边界}局限。
\section{结论}结论。
\end{document}"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            json_files = {
                "outline.json": {"section_plan": []},
                "citation_map.json": {"ref001": {"title": "Approved"}},
                "info.json": [],
            }
            for name, value in json_files.items():
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            for name, content in (
                ("idea.md", "# Exact research title\n"),
                ("experimental_log.md", "experiment"),
                ("literature_draft.tex", "draft"),
                ("guidelines.md", "guidelines"),
            ):
                (root / name).write_text(content, encoding="utf-8")
            model = RecordingModel(text_response=f"```latex\n{complete_latex}\n```")
            agent = SectionWritingAgent(model=model)
            output_path = root / "raw_draft_paper.tex"

            latex = asyncio.run(
                agent.run(
                    outline_path=root / "outline.json",
                    template_path=root / "literature_draft.tex",
                    idea_path=root / "idea.md",
                    experimental_log_path=root / "experimental_log.md",
                    citation_map_path=root / "citation_map.json",
                    figures_info_path=root / "info.json",
                    guidelines_path=root / "guidelines.md",
                    candidate_selection={"selection_method": "random_fallback"},
                    paper_title="Exact research title",
                    output_path=output_path,
                )
            )

            self.assertIs(agent.model, model)
            self.assertIn(
                '"selection_method": "random_fallback"',
                model.text_calls[0]["prompt"],
            )
            self.assertEqual(latex, complete_latex)
            self.assertEqual(output_path.read_text(encoding="utf-8"), latex + "\n")

    def test_agent_review_uses_full_latex_and_extracted_pdf_text(self) -> None:
        expected_review: dict[str, object] = {
            "Strengths": ["Grounded method"],
            "Weaknesses": [],
            "Questions": [],
            "Originality": 7,
            "Quality": 8,
            "Clarity": 7,
            "Significance": 6,
            "Soundness": 8,
            "Presentation": 7,
            "Contribution": 7,
            "Overall": 7,
            "Confidence": 4,
        }
        model = RecordingModel(json_responses=[expected_review])

        review = asyncio.run(
            review_paper(
                model=model,
                latex="FULL LATEX SOURCE",
                pdf_text="FULL EXTRACTED PDF TEXT",
                experimental_log="AUTHORITATIVE EXPERIMENT LOG",
                citation_map={"ref001": {"title": "Approved"}},
            )
        )

        self.assertEqual(review, expected_review)
        self.assertEqual(len(model.json_calls), 1)
        prompt = model.json_calls[0]["prompt"]
        self.assertIn("FULL LATEX SOURCE", prompt)
        self.assertIn("FULL EXTRACTED PDF TEXT", prompt)
        self.assertIn("AUTHORITATIVE EXPERIMENT LOG", prompt)

    def test_layout_review_sends_page_images_through_multimodal_model_api(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            image_path = Path(temporary_directory) / "page-1.png"
            image_path.write_bytes(b"png page bytes")
            model = RecordingModel()
            agent = ContentRefinementAgent(model=model)

            review = asyncio.run(
                agent.review_layout(
                    image_paths=[image_path],
                    guidelines="ElegantPaper layout constraints",
                )
            )

            self.assertEqual(
                review, {"figure_and_tables": {}, "other_issues": []}
            )
            self.assertIs(agent.model, model)
            self.assertEqual(len(model.run_calls), 1)
            request = model.run_calls[0]
            image_part = request.input[0].content[1]
            self.assertIsInstance(image_part, ImageContent)
            self.assertTrue(
                image_part.image_url.startswith("data:image/png;base64,")
            )

    def test_content_refinement_accepts_only_non_degrading_revision(self) -> None:
        initial_latex = r"""\documentclass{article}
\title{Exact title}\author{}\institute{}
\begin{document}\begin{abstract}摘要。\end{abstract}
\section{引言}A\section{相关工作}B\section{方法}C\section{实验}D
\section{研究过程}E\section{复现指南}F
\section{局限性与适用边界}G\section{结论}H\end{document}"""
        revised_latex = initial_latex.replace(
            r"\section{方法}C", r"\section{方法}改进后的表达"
        )

        def review(score: int) -> dict[str, object]:
            return {
                "Strengths": [],
                "Weaknesses": [],
                "Questions": [],
                "Originality": score,
                "Quality": score,
                "Clarity": score,
                "Significance": score,
                "Soundness": score,
                "Presentation": score,
                "Contribution": score,
                "Overall": score,
                "Confidence": 4,
            }

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            initial_tex_path = root / "initial.tex"
            initial_pdf_path = root / "initial.pdf"
            initial_tex_path.write_text(initial_latex, encoding="utf-8")
            initial_pdf_path.write_bytes(b"%PDF-initial\n%%EOF")
            (root / "experimental_log.md").write_text("experiment", encoding="utf-8")
            (root / "citation_map.json").write_text("{}", encoding="utf-8")
            (root / "guidelines.md").write_text("guidelines", encoding="utf-8")
            model = RecordingModel(
                text_responses=[f"```latex\n{revised_latex}\n```"],
                json_responses=[review(6), review(7)],
            )

            def fake_compile(**kwargs: object) -> Path:
                output_pdf = kwargs["output_pdf"]
                output_pdf.write_bytes(b"%PDF-revised\n%%EOF")
                return output_pdf

            agent = ContentRefinementAgent(model=model)
            result = asyncio.run(
                agent.refine_content(
                    initial_tex_path=initial_tex_path,
                    initial_pdf_path=initial_pdf_path,
                    experimental_log_path=root / "experimental_log.md",
                    citation_map_path=root / "citation_map.json",
                    guidelines_path=root / "guidelines.md",
                    paper_title="Exact title",
                    work_dir=root / "refinement",
                    max_iterations=1,
                    compile_document=fake_compile,
                    extract_text=lambda path: f"PDF TEXT {path.name}",
                )
            )

            self.assertEqual(result.tex_path.read_text(encoding="utf-8"), revised_latex + "\n")
            self.assertEqual(result.review["Overall"], 7)
            self.assertEqual(len(model.json_calls), 2)
            self.assertEqual(len(model.text_calls), 1)
