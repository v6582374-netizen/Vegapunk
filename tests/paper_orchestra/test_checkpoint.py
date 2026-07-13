from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from internagent.paper_orchestra.checkpoint import DossierCheckpoint
from internagent.paper_orchestra.data_types import DossierStageError


class CheckpointTest(unittest.TestCase):
    def test_persists_background_response_ids_for_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory) / "primary"
            checkpoint = DossierCheckpoint.open(
                run_dir=run_dir,
                dossier_run_id="primary",
                launch_id="launch",
                resolved_config={},
                model_identity={"provider": "openai", "name": "gpt-5.6-sol"},
                stage_ids=("generate_outline",),
            )

            checkpoint.record_model_response(
                checkpoint_key="generate_outline",
                response_id="resp_outline",
                status="submitted",
            )
            resumed = DossierCheckpoint.open(
                run_dir=run_dir,
                dossier_run_id="primary",
                launch_id="launch",
                resolved_config={},
                model_identity={"provider": "openai", "name": "gpt-5.6-sol"},
                stage_ids=("generate_outline",),
            )

            self.assertEqual(
                resumed.get_model_response("generate_outline"),
                {
                    "response_id": "resp_outline",
                    "status": "submitted",
                },
            )

    def test_resume_rejects_changed_configuration_or_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory) / "primary"
            DossierCheckpoint.open(
                run_dir=run_dir,
                dossier_run_id="primary",
                launch_id="launch",
                resolved_config={"layout_review_enabled": True},
                model_identity={"provider": "shared", "name": "model-a"},
                stage_ids=("first",),
            )

            with self.assertRaises(DossierStageError) as raised:
                DossierCheckpoint.open(
                    run_dir=run_dir,
                    dossier_run_id="primary",
                    launch_id="launch",
                    resolved_config={"layout_review_enabled": False},
                    model_identity={"provider": "shared", "name": "model-a"},
                    stage_ids=("first",),
                )

            self.assertEqual(raised.exception.code, "resume_context_mismatch")

    def test_persists_stage_success_and_completes_three_state_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory) / "primary"
            checkpoint = DossierCheckpoint.open(
                run_dir=run_dir,
                dossier_run_id="primary",
                launch_id="launch",
                resolved_config={"enabled": True},
                model_identity={"provider": "openai", "name": "model"},
                stage_ids=("first", "second"),
            )

            async def write_first_output() -> None:
                (run_dir / "first.txt").write_text("done", encoding="utf-8")

            asyncio.run(
                checkpoint.run_stage(
                    "first", write_first_output, outputs=("first.txt",)
                )
            )

            resumed = DossierCheckpoint.open(
                run_dir=run_dir,
                dossier_run_id="primary",
                launch_id="launch",
                resolved_config={"enabled": True},
                model_identity={"provider": "openai", "name": "model"},
                stage_ids=("first", "second"),
            )
            self.assertEqual(resumed.first_incomplete_stage(), "second")
            self.assertEqual(resumed.manifest["status"], "running")

            async def write_second_output() -> None:
                (run_dir / "second.txt").write_text("done", encoding="utf-8")

            asyncio.run(
                resumed.run_stage(
                    "second", write_second_output, outputs=("second.txt",)
                )
            )
            (run_dir / "final.pdf").write_bytes(b"pdf")
            (run_dir / "final.tex").write_text("tex", encoding="utf-8")
            resumed.complete(final_pdf="final.pdf", final_tex="final.tex")

            manifest = json.loads(
                (run_dir / "dossier_run.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "succeeded")
            self.assertTrue(
                all(stage["status"] == "succeeded" for stage in manifest["stages"])
            )
            self.assertFalse((run_dir / "dossier_run.json.tmp").exists())

    def test_missing_succeeded_output_resets_that_stage_and_all_later_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory) / "primary"
            checkpoint = DossierCheckpoint.open(
                run_dir=run_dir,
                dossier_run_id="primary",
                launch_id="launch",
                resolved_config={},
                model_identity={},
                stage_ids=("first", "second"),
            )
            calls: list[str] = []

            async def write_first() -> None:
                calls.append("first")
                (run_dir / "first.txt").write_text("first", encoding="utf-8")

            async def write_second() -> None:
                calls.append("second")
                (run_dir / "second.txt").write_text("second", encoding="utf-8")

            asyncio.run(
                checkpoint.run_stage("first", write_first, outputs=("first.txt",))
            )
            asyncio.run(
                checkpoint.run_stage("second", write_second, outputs=("second.txt",))
            )
            (run_dir / "final.pdf").write_bytes(b"pdf")
            (run_dir / "final.tex").write_text("tex", encoding="utf-8")
            checkpoint.complete(final_pdf="final.pdf", final_tex="final.tex")
            (run_dir / "first.txt").unlink()

            resumed = DossierCheckpoint.open(
                run_dir=run_dir,
                dossier_run_id="primary",
                launch_id="launch",
                resolved_config={},
                model_identity={},
                stage_ids=("first", "second"),
            )
            asyncio.run(
                resumed.run_stage("first", write_first, outputs=("first.txt",))
            )

            self.assertEqual(calls, ["first", "second", "first"])
            self.assertEqual(resumed.first_incomplete_stage(), "second")
            self.assertEqual(resumed.manifest["status"], "running")
            self.assertEqual(
                resumed.manifest["final_outputs"],
                {
                    "pdf": None,
                    "tex": None,
                    "pdf_sha256": None,
                    "tex_sha256": None,
                },
            )

    def test_missing_immutable_output_fails_without_recomputing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory) / "primary"
            checkpoint = DossierCheckpoint.open(
                run_dir=run_dir,
                dossier_run_id="primary",
                launch_id="launch",
                resolved_config={},
                model_identity={},
                stage_ids=("selection", "writing"),
            )
            calls = 0

            async def write_selection() -> None:
                nonlocal calls
                calls += 1
                (run_dir / "selection.json").write_text("{}", encoding="utf-8")

            asyncio.run(
                checkpoint.run_stage(
                    "selection",
                    write_selection,
                    outputs=("selection.json",),
                    immutable_outputs=True,
                )
            )
            (run_dir / "selection.json").unlink()

            with self.assertRaises(DossierStageError) as raised:
                asyncio.run(
                    checkpoint.run_stage(
                        "selection",
                        write_selection,
                        outputs=("selection.json",),
                        immutable_outputs=True,
                    )
                )

            self.assertEqual(raised.exception.code, "immutable_stage_output_missing")
            self.assertEqual(calls, 1)
