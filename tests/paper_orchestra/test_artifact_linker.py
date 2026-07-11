from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from internagent.paper_orchestra.artifact_linker import link_selected_artifacts
from internagent.paper_orchestra.data_types import DossierStageError


class ArtifactLinkerTest(unittest.TestCase):
    def test_links_selected_result_to_one_full_idea_by_exact_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            launch_dir = Path(temporary_directory) / "launch"
            session_dir = launch_dir / "session_1"
            candidate_dir = session_dir / "candidate-a"
            candidate_dir.mkdir(parents=True)
            method = {
                "name": "method_a",
                "title": "A precise method",
                "description": "Method overview",
                "statement": "Novelty statement",
                "method": "Exact method details",
            }
            full_idea = {
                "id": "idea-1",
                "text": "Research hypothesis",
                "rationale": "Motivation",
                "baseline_summary": "Baseline context",
                "refined_method_details": method,
                "evidence": [],
                "references": [],
            }
            (session_dir / "ideas.json").write_text(
                json.dumps([method]), encoding="utf-8"
            )
            (session_dir / "traj.json").write_text(
                json.dumps({"ideas": [full_idea], "top_ideas": ["idea-1"]}),
                encoding="utf-8",
            )
            selection = {
                "paper_candidate_round": {"session_id": "session_1"},
                "selected_candidate": {
                    "idea_name": "method_a",
                    "folder_name": "session_1/candidate-a",
                },
            }

            linked = link_selected_artifacts(
                launch_dir=launch_dir, selection=selection
            )

            self.assertEqual(linked.candidate_dir, candidate_dir.resolve())
            self.assertEqual(linked.selected_method, method)
            self.assertEqual(linked.full_idea, full_idea)

    def test_rejects_ambiguous_full_idea_join(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            launch_dir = Path(temporary_directory) / "launch"
            session_dir = launch_dir / "session_1"
            (session_dir / "candidate-a").mkdir(parents=True)
            method = {"name": "method_a", "method": "same method"}
            (session_dir / "ideas.json").write_text(
                json.dumps([method]), encoding="utf-8"
            )
            (session_dir / "traj.json").write_text(
                json.dumps(
                    {
                        "top_ideas": ["idea-1", "idea-2"],
                        "ideas": [
                            {"id": "idea-1", "refined_method_details": method},
                            {"id": "idea-2", "refined_method_details": method},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            selection = {
                "paper_candidate_round": {"session_id": "session_1"},
                "selected_candidate": {
                    "idea_name": "method_a",
                    "folder_name": "session_1/candidate-a",
                },
            }

            with self.assertRaises(DossierStageError) as raised:
                link_selected_artifacts(launch_dir=launch_dir, selection=selection)

            self.assertEqual(raised.exception.code, "artifact_link_failed")
            self.assertIn("exactly one top Idea", str(raised.exception))
