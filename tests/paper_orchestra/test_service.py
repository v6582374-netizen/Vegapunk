from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from internagent.paper_orchestra import run_dossier
from tests.paper_orchestra.test_agents import RecordingModel


class DossierServiceTest(unittest.TestCase):
    def test_disabled_configuration_creates_no_dossier_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            launch_dir = root / "launch"
            launch_dir.mkdir()
            template_dir = root / "template"
            template_dir.mkdir()
            (template_dir / "template.tex").write_text("template", encoding="utf-8")
            (template_dir / "guidelines.md").write_text("rules", encoding="utf-8")
            config_path = root / "paper_orchestra.yaml"
            config_path.write_text(
                f"""enabled: false
template_dir: {template_dir}
layout_review_enabled: true
max_content_refinement_iterations: 3
max_format_correction_iterations: 1
""",
                encoding="utf-8",
            )

            result = asyncio.run(
                run_dossier(
                    launch_dir=launch_dir,
                    internagent_config={},
                    paper_config_path=config_path,
                )
            )

            self.assertEqual(result.status, "succeeded")
            self.assertEqual(result.warnings, ("dossier_disabled_by_config",))
            self.assertFalse((launch_dir / "dossier_runs").exists())

    def test_runs_real_service_pipeline_with_one_factory_model(self) -> None:
        complete_latex = r"""\documentclass[lang=cn,a4paper,bibend=biber]{elegantpaper}
\title{Test Method}\author{}\institute{}\date{PAPER_DATE}
\addbibresource{references.bib}
\begin{document}\maketitle
\begin{abstract}这是可审查的摘要。\end{abstract}
\section{引言}研究背景。
\section{相关工作}相关证据见 \cite{ref001}。
\section{方法}记录的方法。
\section{实验}记录的结果。
\section{研究过程}\subsection{候选选择}由于第 2 轮无成功候选，系统回退到第 1 轮；本轮只有一个成功候选，直接选择。
\section{复现指南}依据实验日志复现。
\section{局限性与适用边界}未评估条件保持未知。
\section{结论}结论。
\printbibliography[heading=bibintoc,title=\ebibname]
\end{document}"""
        complete_latex = complete_latex.replace("PAPER_DATE", date.today().isoformat())
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
            launch_dir = root / "20260710_100000_launch"
            session_dir = launch_dir / "session_1"
            candidate_dir = session_dir / "candidate-a"
            run_zero = candidate_dir / "run_0"
            run_zero.mkdir(parents=True)
            (run_zero / "final_info.json").write_text(
                '{"loss": 0.5}', encoding="utf-8"
            )
            report_dir = run_zero / "report"
            images_dir = report_dir / "images"
            images_dir.mkdir(parents=True)
            (images_dir / "result.png").write_bytes(b"recorded image")
            (report_dir / "report.md").write_text(
                "![Recorded result](images/result.png)\n", encoding="utf-8"
            )
            method = {
                "name": "method_a",
                "title": "Test Method",
                "description": "Method overview",
                "statement": "Novelty",
                "method": "Method details",
            }
            full_idea = {
                "id": "idea-1",
                "text": "Hypothesis",
                "rationale": "Motivation",
                "baseline_summary": "Baseline",
                "refined_method_details": method,
                "references": [
                    {
                        "title": "Approved Reference",
                        "authors": ["Author One"],
                        "year": 2024,
                        "journal": "Journal",
                        "doi": "10.1000/test",
                    }
                ],
                "evidence": [
                    {
                        "title": "Approved Reference",
                        "doi": "https://doi.org/10.1000/TEST",
                        "content": "Approved abstract.",
                    }
                ],
            }
            (session_dir / "ideas.json").write_text(
                json.dumps([method]), encoding="utf-8"
            )
            (session_dir / "traj.json").write_text(
                json.dumps({"ideas": [full_idea], "top_ideas": ["idea-1"]}),
                encoding="utf-8",
            )
            failed_candidate_dir = launch_dir / "session_2" / "candidate-b"
            failed_candidate_dir.mkdir(parents=True)
            (failed_candidate_dir / "failure.log").write_text(
                "recorded failure", encoding="utf-8"
            )
            (launch_dir / "discovery_summary.json").write_text(
                json.dumps(
                    {
                        "launch_id": launch_dir.name,
                        "mode": "experiment",
                        "rounds": [
                            {
                                "round": 1,
                                "session_id": "session_1",
                                "results": [
                                    {
                                        "success": True,
                                        "idea_name": "method_a",
                                        "folder_name": "session_1/candidate-a",
                                    }
                                ],
                            },
                            {
                                "round": 2,
                                "session_id": "session_2",
                                "results": [
                                    {
                                        "success": False,
                                        "idea_name": "method_b",
                                    }
                                ],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            repository_root = Path(__file__).resolve().parents[2]
            config_path = root / "paper_orchestra.yaml"
            config_path.write_text(
                f"""enabled: true
template_dir: {repository_root / 'tex_templates' / 'elegantpaper'}
layout_review_enabled: true
max_content_refinement_iterations: 0
max_format_correction_iterations: 1
""",
                encoding="utf-8",
            )
            model = RecordingModel(
                text_responses=[
                    f"```latex\n{complete_latex}\n```",
                    f"```latex\n{complete_latex}\n```",
                    f"```latex\n{complete_latex}\n```",
                    f"```latex\n{complete_latex}\n```",
                ],
                json_responses=[
                    {"intro_related_work_plan": {}, "section_plan": []},
                    review,
                    {"intro_related_work_plan": {}, "section_plan": []},
                    review,
                ],
            )
            internagent_config = {
                "models": {
                    "default_provider": "openai",
                    "openai": {"model_name": "test-model"},
                }
            }
            artifact_hashes_before = _file_hashes(
                [candidate_dir, failed_candidate_dir]
            )

            with patch(
                "internagent.mas.models.model_factory.ModelFactory.create_model_for_agent",
                return_value=model,
            ) as create_model:
                result = asyncio.run(
                    run_dossier(
                        launch_dir=launch_dir,
                        internagent_config=internagent_config,
                        paper_config_path=config_path,
                    )
                )
                resumed_result = asyncio.run(
                    run_dossier(
                        launch_dir=launch_dir,
                        internagent_config=internagent_config,
                        paper_config_path=config_path,
                    )
                )
                self.assertEqual(create_model.call_count, 1)
                raw_dir = result.run_dir / "raw_materials"
                manifest_path = result.run_dir / "dossier_run.json"
                interrupted_manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
                interrupted_manifest["status"] = "failed"
                interrupted_manifest["error"] = {
                    "stage": "validate_final_outputs_and_disclosures",
                    "code": "simulated_interruption",
                    "message": "resume fixture",
                    "log_path": None,
                }
                manifest_path.write_text(
                    json.dumps(interrupted_manifest), encoding="utf-8"
                )
                (raw_dir / "references.bib").unlink()
                (raw_dir / "figures" / "result.png").unlink()
                recovered_raw_result = asyncio.run(
                    run_dossier(
                        launch_dir=launch_dir,
                        internagent_config=internagent_config,
                        paper_config_path=config_path,
                    )
                )
                final_pdf_bytes = result.final_pdf.read_bytes()
                result.final_pdf.write_bytes(
                    final_pdf_bytes.replace(
                        b"%%EOF", b"% valid replacement\n%%EOF", 1
                    )
                )
                recovered_result = asyncio.run(
                    run_dossier(
                        launch_dir=launch_dir,
                        internagent_config=internagent_config,
                        paper_config_path=config_path,
                    )
                )

            self.assertEqual(result.status, "succeeded", result.error)
            self.assertEqual(create_model.call_count, 3)
            self.assertEqual(result.warnings, ())
            self.assertEqual(len(model.message_calls), 2)
            self.assertTrue(result.final_pdf.is_file())
            self.assertTrue(result.final_tex.is_file())
            self.assertEqual(resumed_result.status, "succeeded")
            self.assertEqual(resumed_result.final_pdf, result.final_pdf)
            self.assertEqual(resumed_result.final_tex, result.final_tex)
            self.assertEqual(recovered_raw_result.status, "succeeded")
            self.assertTrue((raw_dir / "references.bib").is_file())
            self.assertTrue((raw_dir / "figures" / "result.png").is_file())
            self.assertEqual(recovered_result.status, "succeeded")
            self.assertGreater(recovered_result.final_pdf.stat().st_size, 100)
            self.assertEqual(
                _file_hashes([candidate_dir, failed_candidate_dir]),
                artifact_hashes_before,
            )
            manifest = json.loads(
                (result.run_dir / "dossier_run.json").read_text(encoding="utf-8")
            )
            self.assertTrue(
                all(stage["status"] == "succeeded" for stage in manifest["stages"])
            )


def _file_hashes(roots: list[Path]) -> dict[str, str]:
    hashes = {}
    for root in roots:
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes
