from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from internagent.paper_orchestra import run_paper_orchestra
from internagent.paper_orchestra.data_types import PipelineResult
from tests.paper_orchestra.test_agents import RecordingModel


class PaperOrchestraServiceTest(unittest.TestCase):
    def test_same_handoff_resumes_same_run_and_expanded_discovery_creates_next_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            launch_dir = root / "launch"
            _write_launch(launch_dir, rounds=2)
            config_path = _write_config(root)

            calls: list[Path] = []

            async def fake_pipeline(**kwargs: object) -> PipelineResult:
                run_dir = kwargs["run_dir"]
                calls.append(run_dir)
                checkpoint = kwargs["checkpoint"]
                for stage in checkpoint.manifest["stages"]:
                    stage["status"] = "succeeded"
                    stage["outputs"] = []
                tex = run_dir / "latex_writeup" / "final_refined_paper.tex"
                pdf = run_dir / "final_paper.pdf"
                tex.parent.mkdir(parents=True, exist_ok=True)
                tex.write_text("paper", encoding="utf-8")
                pdf.write_bytes(b"%PDF-paper\n%%EOF")
                return PipelineResult(final_tex=tex, final_pdf=pdf, warnings=())

            with patch(
                "internagent.paper_orchestra.service.run_writing_pipeline",
                side_effect=fake_pipeline,
            ), patch(
                "internagent.paper_orchestra.service._final_outputs_are_valid",
                return_value=True,
            ), patch(
                "internagent.mas.models.model_factory.ModelFactory.create_model_for_agent",
                return_value=RecordingModel(text_responses=["material"]),
            ):
                first = asyncio.run(
                    run_paper_orchestra(
                        launch_dir=launch_dir,
                        internagent_config={},
                        paper_config_path=config_path,
                    )
                )
                resumed = asyncio.run(
                    run_paper_orchestra(
                        launch_dir=launch_dir,
                        internagent_config={},
                        paper_config_path=config_path,
                    )
                )
                _write_launch(launch_dir, rounds=3)
                expanded = asyncio.run(
                    run_paper_orchestra(
                        launch_dir=launch_dir,
                        internagent_config={},
                        paper_config_path=config_path,
                    )
                )

            self.assertEqual(first.paper_orchestra_run_id, "round_0002")
            self.assertEqual(resumed.run_dir, first.run_dir)
            self.assertEqual(expanded.paper_orchestra_run_id, "round_0003")
            self.assertEqual(calls, [first.run_dir, expanded.run_dir])
            self.assertTrue(first.final_pdf.is_file())
            self.assertTrue(expanded.final_pdf.is_file())

    def test_no_successful_candidate_still_starts_paperorchestra(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            launch_dir = root / "launch"
            _write_launch(launch_dir, rounds=1, successful=False)
            config_path = _write_config(root)
            observed: dict[str, object] = {}

            async def fake_pipeline(**kwargs: object) -> PipelineResult:
                observed["selection"] = kwargs["candidate_selection"]
                run_dir = kwargs["run_dir"]
                checkpoint = kwargs["checkpoint"]
                for stage in checkpoint.manifest["stages"]:
                    stage["status"] = "succeeded"
                    stage["outputs"] = []
                tex = run_dir / "latex_writeup" / "final_refined_paper.tex"
                pdf = run_dir / "final_paper.pdf"
                tex.parent.mkdir(parents=True, exist_ok=True)
                tex.write_text("negative-results paper", encoding="utf-8")
                pdf.write_bytes(b"%PDF-paper\n%%EOF")
                return PipelineResult(final_tex=tex, final_pdf=pdf, warnings=())

            with patch(
                "internagent.paper_orchestra.service.run_writing_pipeline",
                side_effect=fake_pipeline,
            ), patch(
                "internagent.paper_orchestra.service._final_outputs_are_valid",
                return_value=True,
            ), patch(
                "internagent.mas.models.model_factory.ModelFactory.create_model_for_agent",
                return_value=RecordingModel(text_responses=["material"]),
            ):
                result = asyncio.run(
                    run_paper_orchestra(
                        launch_dir=launch_dir,
                        internagent_config={},
                        paper_config_path=config_path,
                    )
                )

            self.assertIsNone(result.error, result.error)
            self.assertIsNone(observed["selection"])
            self.assertTrue(result.final_pdf.is_file())

    def test_candidate_selection_runtime_error_does_not_block_paper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            launch_dir = root / "launch"
            _write_launch(launch_dir, rounds=1)
            config_path = _write_config(root)
            observed: dict[str, object] = {}

            async def fake_pipeline(**kwargs: object) -> PipelineResult:
                observed["selection"] = kwargs["candidate_selection"]
                run_dir = kwargs["run_dir"]
                checkpoint = kwargs["checkpoint"]
                for stage in checkpoint.manifest["stages"]:
                    stage["status"] = "succeeded"
                    stage["outputs"] = []
                tex = run_dir / "latex_writeup" / "final_refined_paper.tex"
                pdf = run_dir / "final_paper.pdf"
                tex.parent.mkdir(parents=True, exist_ok=True)
                tex.write_text("paper from full Draft", encoding="utf-8")
                pdf.write_bytes(b"%PDF-paper\n%%EOF")
                return PipelineResult(final_tex=tex, final_pdf=pdf, warnings=())

            with patch(
                "internagent.paper_orchestra.service.select_candidate",
                side_effect=RuntimeError("selection backend unavailable"),
            ), patch(
                "internagent.paper_orchestra.service.run_writing_pipeline",
                side_effect=fake_pipeline,
            ), patch(
                "internagent.paper_orchestra.service._final_outputs_are_valid",
                return_value=True,
            ), patch(
                "internagent.mas.models.model_factory.ModelFactory.create_model_for_agent",
                return_value=RecordingModel(text_responses=["material"]),
            ):
                result = asyncio.run(
                    run_paper_orchestra(
                        launch_dir=launch_dir,
                        internagent_config={},
                        paper_config_path=config_path,
                    )
                )

            self.assertIsNone(result.error, result.error)
            self.assertIsNone(observed["selection"])
            self.assertTrue(result.final_pdf.is_file())


def _write_launch(launch_dir: Path, *, rounds: int, successful: bool = True) -> None:
    launch_dir.mkdir(parents=True, exist_ok=True)
    manuscript = launch_dir / "manuscript"
    manuscript.mkdir(exist_ok=True)
    (manuscript / "draft.md").write_text(
        "research observation\n", encoding="utf-8"
    )
    round_records = []
    for number in range(1, rounds + 1):
        session_dir = launch_dir / f"session_{number}"
        session_dir.mkdir(exist_ok=True)
        (session_dir / "traj.json").write_text("{}", encoding="utf-8")
        result = {
            "success": successful,
            "idea_name": f"method_{number}",
        }
        if successful:
            candidate = session_dir / f"candidate_{number}"
            run_zero = candidate / "run_0"
            run_zero.mkdir(parents=True, exist_ok=True)
            (run_zero / "final_info.json").write_text(
                '{"loss": 1}', encoding="utf-8"
            )
            result["folder_name"] = f"session_{number}/candidate_{number}"
        round_records.append(
            {"round": number, "session_id": f"session_{number}", "results": [result]}
        )
    (launch_dir / "discovery_summary.json").write_text(
        json.dumps(
            {
                "launch_id": launch_dir.name,
                "mode": "experiment",
                "rounds": round_records,
            }
        ),
        encoding="utf-8",
    )


def _write_config(root: Path) -> Path:
    template = root / "template"
    template.mkdir(exist_ok=True)
    (template / "template.tex").write_text("template", encoding="utf-8")
    (template / "guidelines.md").write_text("rules", encoding="utf-8")
    config = root / "paper_orchestra.yaml"
    config.write_text(
        f"""template_dir: {template}
layout_review_enabled: true
max_content_refinement_iterations: 0
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
    return config


if __name__ == "__main__":
    unittest.main()
