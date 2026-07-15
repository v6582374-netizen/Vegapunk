from __future__ import annotations

import asyncio
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from internagent.paper_orchestra import run_paper_orchestra


class VendoredPaperOrchestraServiceTest(unittest.TestCase):
    def test_runs_vendored_cli_with_deterministic_native_materials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            launch_dir = root / "launch"
            _write_launch(launch_dir)
            vendor_root = _write_fake_vendor(root)
            config_path = _write_config(root, vendor_root)

            result = asyncio.run(
                run_paper_orchestra(
                    launch_dir=launch_dir,
                    internagent_config={
                        "models": {
                            "openai": {
                                "api_mode": "responses",
                                "api_key": "top-secret",
                                "base_url": "https://relay.example/v1",
                                "model_name": "default-text-model",
                                "temperature": 0.7,
                            }
                        }
                    },
                    paper_config_path=config_path,
                )
            )

            self.assertIsNone(result.error, result.error)
            self.assertEqual(result.paper_orchestra_run_id, "paper")
            self.assertEqual(result.final_pdf, result.run_dir / "final_paper.pdf")
            self.assertEqual(
                result.final_tex,
                result.run_dir
                / "content_refinement_workdir"
                / "final_refined_paper.tex",
            )

            idea = (result.run_dir / "raw_materials" / "idea_sparse.md").read_text(
                encoding="utf-8"
            )
            self.assertIn('"task": "measure the field"', idea)
            self.assertIn("Selected method notes with $B = Ax$.", idea)
            self.assertNotIn("stale baseline summary", idea)

            experiments = (
                result.run_dir / "raw_materials" / "experimental_log.md"
            ).read_text(encoding="utf-8")
            self.assertIn("Candidate-level experiment narrative", experiments)
            self.assertIn('"loss": 1.0', experiments)
            self.assertIn('"loss": 0.5', experiments)
            self.assertIn("recorded failure before recovery", experiments)
            self.assertNotIn("candidate root activity log", experiments)
            self.assertNotIn("duplicated run activity log", experiments)
            self.assertNotIn("stale baseline summary", experiments)
            self.assertNotIn("source code must stay out", experiments)

            observation = json.loads(
                (result.run_dir / "child_observation.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                Path(observation["cwd"]).resolve(), result.run_dir.resolve()
            )
            self.assertTrue(
                (result.run_dir / "relative-child-artifact.txt").is_file()
            )
            self.assertFalse(
                (vendor_root / "relative-child-artifact.txt").exists()
            )
            self.assertIn("--use_plotting", observation["argv"])
            plotting_index = observation["argv"].index("--use_plotting")
            self.assertEqual(observation["argv"][plotting_index + 1], "true")
            self.assertTrue(observation["api_key_present"])

            runtime_config = json.loads(
                (result.run_dir / "internagent_runtime.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                runtime_config["provider"]["base_url"],
                "https://relay.example/v1",
            )
            self.assertNotIn("api_key", runtime_config["provider"])
            self.assertNotIn("temperature", runtime_config["provider"])
            self.assertEqual(runtime_config["max_concurrent_model_requests"], 2)
            self.assertIn("fake child stdout", (result.run_dir / "stdout.log").read_text())
            self.assertIn("fake child stderr", (result.run_dir / "stderr.log").read_text())


def _write_launch(launch_dir: Path) -> None:
    launch_dir.mkdir(parents=True)
    (launch_dir / "prompt.json").write_text(
        '{"task": "measure the field", "metric": "loss"}\n',
        encoding="utf-8",
    )
    session_dir = launch_dir / "session_1"
    session_dir.mkdir()
    (session_dir / "traj.json").write_text("{}", encoding="utf-8")
    candidate_dir = session_dir / "candidate_1"
    candidate_dir.mkdir()
    (candidate_dir / "notes.txt").write_text(
        "Selected method notes with $B = Ax$.\n", encoding="utf-8"
    )
    (candidate_dir / "experiment_report.txt").write_text(
        "Candidate-level experiment narrative\n", encoding="utf-8"
    )
    (candidate_dir / "log.txt").write_text(
        "candidate root activity log\n", encoding="utf-8"
    )
    (candidate_dir / "code_summary.json").write_text(
        '{"summary": "stale baseline summary"}', encoding="utf-8"
    )
    for number, loss in ((0, 1.0), (1, 0.5)):
        run_dir = candidate_dir / f"run_{number}"
        (run_dir / "code").mkdir(parents=True)
        (run_dir / "final_info.json").write_text(
            json.dumps({"loss": loss}), encoding="utf-8"
        )
        (run_dir / "log.txt").write_text(
            "duplicated run activity log\n", encoding="utf-8"
        )
        (run_dir / "code" / "experiment.py").write_text(
            "# source code must stay out\n", encoding="utf-8"
        )
    (candidate_dir / "run_1" / "traceback.log").write_text(
        "recorded failure before recovery\n", encoding="utf-8"
    )
    (launch_dir / "discovery_summary.json").write_text(
        json.dumps(
            {
                "launch_id": launch_dir.name,
                "rounds": [
                    {
                        "round": 1,
                        "session_id": "session_1",
                        "results": [
                            {
                                "success": True,
                                "idea_name": "candidate_1",
                                "folder_name": "session_1/candidate_1",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_fake_vendor(root: Path) -> Path:
    vendor_root = root / "vendor"
    template_dir = vendor_root / "templates" / "iclr2025"
    template_dir.mkdir(parents=True)
    (template_dir / "template.tex").write_text("template", encoding="utf-8")
    (template_dir / "guidelines.md").write_text("guidelines", encoding="utf-8")
    (vendor_root / "paper_writing_cli.py").write_text(
        textwrap.dedent(
            """
            import argparse
            import json
            import os
            import sys
            from pathlib import Path

            parser = argparse.ArgumentParser()
            parser.add_argument("--output_dir", required=True)
            args, _ = parser.parse_known_args()
            output_dir = Path(args.output_dir)
            Path("relative-child-artifact.txt").write_text(
                "run-local", encoding="utf-8"
            )
            tex = output_dir / "content_refinement_workdir" / "final_refined_paper.tex"
            tex.parent.mkdir(parents=True, exist_ok=True)
            tex.write_text("final tex", encoding="utf-8")
            (output_dir / "final_paper.pdf").write_bytes(b"%PDF-1.4\\n%%EOF")
            (output_dir / "child_observation.json").write_text(
                json.dumps(
                    {
                        "cwd": os.getcwd(),
                        "argv": sys.argv[1:],
                        "api_key_present": bool(os.environ.get("OPENAI_API_KEY")),
                    }
                ),
                encoding="utf-8",
            )
            print("fake child stdout")
            print("fake child stderr", file=sys.stderr)
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return vendor_root


def _write_config(root: Path, vendor_root: Path) -> Path:
    config_path = root / "paper_orchestra.yaml"
    config_path.write_text(
        textwrap.dedent(
            f"""
            vendor_root: {vendor_root}
            template_dir: templates/iclr2025
            use_plotting: true
            writer_model: writer-model
            reflection_model: reflection-model
            plotting_model: plotting-model
            image_model: image-model
            max_concurrent_model_requests: 2
            plotting_max_critic_rounds: 2
            """
        ).lstrip(),
        encoding="utf-8",
    )
    return config_path


if __name__ == "__main__":
    unittest.main()
