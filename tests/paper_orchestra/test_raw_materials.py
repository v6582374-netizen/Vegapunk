from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from internagent.paper_orchestra.data_types import DossierStageError, LinkedArtifacts
from internagent.paper_orchestra.raw_materials import (
    prepare_raw_materials,
    validate_raw_materials,
)


class RawMaterialsTest(unittest.TestCase):
    def test_validation_requires_every_registered_figure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory) / "raw_materials"
            figures_dir = output_dir / "figures"
            figures_dir.mkdir(parents=True)
            for name, content in (
                ("idea.md", "# Idea\n"),
                ("experimental_log.md", "# Log\n"),
                ("references.bib", "% No approved references.\n"),
                ("citation_map.json", "{}\n"),
            ):
                (output_dir / name).write_text(content, encoding="utf-8")
            (figures_dir / "info.json").write_text(
                json.dumps(
                    [
                        {
                            "name": "result.png",
                            "caption": "Recorded result",
                            "source": "run_1/report/images/result.png",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            figure_path = figures_dir / "result.png"
            figure_path.write_bytes(b"recorded image")

            validate_raw_materials(output_dir)
            figure_path.unlink()

            with self.assertRaises(DossierStageError) as raised:
                validate_raw_materials(output_dir)
            self.assertEqual(raised.exception.code, "raw_material_render_failed")

    def test_renders_idea_markdown_from_exact_authoritative_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            candidate_dir = root / "candidate"
            candidate_dir.mkdir()
            method = {
                "name": "method_a",
                "title": "A precise method",
                "description": "Method overview",
                "statement": "Novel contribution",
                "method": "Exact implementation details",
                "score": 99,
            }
            linked = LinkedArtifacts(
                candidate_dir=candidate_dir,
                session_dir=root / "session",
                selected_method=method,
                full_idea={
                    "text": "Research hypothesis",
                    "rationale": "Recorded motivation",
                    "baseline_summary": "Recorded baseline context",
                    "score": 0.95,
                    "critiques": ["must not enter idea.md"],
                },
            )

            output_dir = root / "raw_materials"
            returned_root = prepare_raw_materials(
                linked=linked, output_dir=output_dir
            )

            self.assertEqual(returned_root, output_dir)
            self.assertEqual(
                (output_dir / "idea.md").read_text(encoding="utf-8"),
                """# A precise method

## Method name

method_a

## Research hypothesis

Research hypothesis

## Motivation

Recorded motivation

## Baseline context

Recorded baseline context

## Method overview

Method overview

## Novelty/theory

Novel contribution

## Method details

Exact implementation details
""",
            )

    def test_renders_all_numeric_runs_in_numeric_order_without_interpreting_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            candidate_dir = root / "candidate"
            for run_number in (0, 2, 3, 10):
                (candidate_dir / f"run_{run_number}").mkdir(parents=True)
            (candidate_dir / "run_0" / "final_info.json").write_text(
                '{"loss": 1.0}\n', encoding="utf-8"
            )
            (candidate_dir / "run_2" / "final_info.json").write_text(
                '{"loss": 0.5}\n', encoding="utf-8"
            )
            report_dir = candidate_dir / "run_2" / "report"
            report_dir.mkdir()
            (report_dir / "report.md").write_text(
                "Recorded report body.\n", encoding="utf-8"
            )
            (candidate_dir / "run_3" / "traceback.log").write_text(
                "SECRET STACK CONTENT\n", encoding="utf-8"
            )
            (candidate_dir / "run_10" / "final_info.json").write_text(
                '{"loss": 0.4}\n', encoding="utf-8"
            )
            linked = LinkedArtifacts(
                candidate_dir=candidate_dir,
                session_dir=root / "session",
                selected_method={
                    "name": "method_a",
                    "title": "Title",
                    "method": "Method",
                },
                full_idea={},
            )

            output_dir = root / "raw_materials"
            prepare_raw_materials(linked=linked, output_dir=output_dir)
            log = (output_dir / "experimental_log.md").read_text(encoding="utf-8")

            positions = [log.index(f"## Run {number}\n") for number in (0, 2, 3, 10)]
            self.assertEqual(positions, sorted(positions))
            self.assertIn("- Structure status: baseline", log)
            self.assertIn("- Structure status: successful", log)
            self.assertIn("- Structure status: failed", log)
            self.assertIn('{"loss": 0.5}\n', log)
            self.assertIn("Recorded report body.\n", log)
            self.assertIn("- Traceback: run_3/traceback.log", log)
            self.assertNotIn("SECRET STACK CONTENT", log)

    def test_copies_only_explicitly_referenced_figures_from_current_valid_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            candidate_dir = root / "candidate"
            run_dir = candidate_dir / "run_2"
            images_dir = run_dir / "report" / "images"
            images_dir.mkdir(parents=True)
            (run_dir / "final_info.json").write_text(
                '{"loss": 0.2}', encoding="utf-8"
            )
            (run_dir / "report" / "report.md").write_text(
                "Result: ![Recorded loss curve](images/loss.png)\n",
                encoding="utf-8",
            )
            (images_dir / "loss.png").write_bytes(b"referenced-image")
            (images_dir / "diagnostic.png").write_bytes(b"unreferenced-image")
            linked = LinkedArtifacts(
                candidate_dir=candidate_dir,
                session_dir=root / "session",
                selected_method={
                    "name": "method_a",
                    "title": "Title",
                    "method": "Method",
                },
                full_idea={},
            )

            output_dir = root / "raw_materials"
            prepare_raw_materials(linked=linked, output_dir=output_dir)

            figures_dir = output_dir / "figures"
            self.assertEqual(
                (figures_dir / "loss.png").read_bytes(), b"referenced-image"
            )
            self.assertFalse((figures_dir / "diagnostic.png").exists())
            self.assertEqual(
                json.loads((figures_dir / "info.json").read_text(encoding="utf-8")),
                [
                    {
                        "name": "loss.png",
                        "caption": "Recorded loss curve",
                        "source": "run_2/report/images/loss.png",
                    }
                ],
            )

    def test_builds_citation_files_from_exact_doi_then_exact_title_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            candidate_dir = root / "candidate"
            candidate_dir.mkdir()
            linked = LinkedArtifacts(
                candidate_dir=candidate_dir,
                session_dir=root / "session",
                selected_method={
                    "name": "method_a",
                    "title": "Title",
                    "method": "Method",
                },
                full_idea={
                    "references": [
                        {
                            "title": "First Paper",
                            "authors": ["Ada Lovelace", "Grace Hopper"],
                            "year": 2024,
                            "journal": "Journal One",
                            "doi": "https://doi.org/10.1000/ABC",
                            "url": "https://example.test/first",
                        },
                        {
                            "title": "Second   Paper",
                            "authors": ["Katherine Johnson"],
                            "year": 2023,
                            "journal": "Journal Two",
                            "doi": None,
                        },
                        {
                            "title": "Near Match",
                            "authors": ["Excluded Author"],
                            "year": 2022,
                        },
                    ],
                    "evidence": [
                        {
                            "title": "Different title is allowed for DOI match",
                            "doi": "doi:10.1000/abc",
                            "content": "First authoritative abstract.",
                        },
                        {
                            "title": "second paper",
                            "doi": "",
                            "content": "Second authoritative abstract.",
                        },
                        {
                            "title": "Near Matches",
                            "content": "Must not be fuzzy matched.",
                        },
                    ],
                },
            )

            output_dir = root / "raw_materials"
            prepare_raw_materials(linked=linked, output_dir=output_dir)

            citation_map = json.loads(
                (output_dir / "citation_map.json").read_text(encoding="utf-8")
            )
            self.assertEqual(list(citation_map), ["ref001", "ref002"])
            self.assertEqual(
                citation_map["ref001"]["abstract"],
                "First authoritative abstract.",
            )
            self.assertEqual(
                citation_map["ref002"]["abstract"],
                "Second authoritative abstract.",
            )
            bibliography = (output_dir / "references.bib").read_text(
                encoding="utf-8"
            )
            self.assertIn("@article{ref001,", bibliography)
            self.assertIn("author = {Ada Lovelace and Grace Hopper}", bibliography)
            self.assertIn("doi = {https://doi.org/10.1000/ABC}", bibliography)
            self.assertIn("@article{ref002,", bibliography)
            self.assertNotIn("Near Match", bibliography)
