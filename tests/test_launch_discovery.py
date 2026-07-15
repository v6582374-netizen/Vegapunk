from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import types
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import launch_discovery


class DiscoveryPaperHandoffTest(unittest.TestCase):
    def test_handoff_calls_paperorchestra_directly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            launch_dir = root / "launch"
            with patch(
                "launch_discovery._run_paper_orchestra"
            ) as run:
                launch_discovery._handoff_to_paper_orchestra(
                    launch_dir=launch_dir,
                    config={},
                    repository_root=root,
                    logger=logging.getLogger("handoff-test"),
                )

            run.assert_called_once()

    def test_project_test_suites_are_concrete_local_packages(self) -> None:
        import tests
        import tests.paper_orchestra

        repository_root = Path(__file__).parents[1]
        self.assertEqual(
            Path(tests.__file__).resolve(),
            repository_root / "tests" / "__init__.py",
        )
        self.assertEqual(
            Path(tests.paper_orchestra.__file__).resolve(),
            repository_root / "tests" / "paper_orchestra" / "__init__.py",
        )

    def test_new_discovery_launch_automatically_hands_off_without_draft(
        self,
    ) -> None:
        class ReportWriter:
            def __init__(self, *_: object) -> None:
                pass

            def generate_reports(self, **_: object) -> list[dict[str, object]]:
                return [
                    {
                        "idea_name": "measured idea",
                        "success": True,
                        "report_path": "report.md",
                    }
                ]

        stage_stub = types.ModuleType("internagent.stage")
        stage_stub.IdeaGenerator = object
        stage_stub.ExperimentRunner = object
        stage_stub.ReportWriter = ReportWriter

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            task_dir = root / "task"
            task_dir.mkdir()
            (task_dir / "prompt.json").write_text(
                '{"task": "derive x = A b"}', encoding="utf-8"
            )
            ideas_path = root / "session_123_ideas.json"
            ideas_path.write_text(
                '[{"id": "idea-1", "formula": "x = A b"}]',
                encoding="utf-8",
            )
            arguments = Namespace(
                resume=None,
                task=str(task_dir),
                ref_code_path=None,
                output_dir="paper-test",
                config=None,
                skip_idea_generation=True,
                idea_path=str(ideas_path),
                mode="report",
                exp_backend="claudecode",
            )

            previous_directory = Path.cwd()
            os.chdir(root)
            try:
                with patch.dict(sys.modules, {"internagent.stage": stage_stub}), patch(
                    "launch_discovery.parse_arguments", return_value=arguments
                ), patch(
                    "launch_discovery.setup_logging",
                    return_value=logging.getLogger("new-launch-test"),
                ), patch.object(
                    launch_discovery, "LONG_MEMORY_AVAILABLE", False
                ), patch(
                    "launch_discovery._run_paper_orchestra"
                ) as run:
                    launch_discovery.main()
            finally:
                os.chdir(previous_directory)

            launches = list((root / "results" / "paper-test").glob("*_launch"))
            self.assertEqual(len(launches), 1)
            draft_path = launches[0] / "manuscript" / "draft.md"
            self.assertFalse(draft_path.exists())
            run.assert_called_once()
            called_launch = root / run.call_args.kwargs["launch_dir"]
            self.assertEqual(called_launch.resolve(), launches[0].resolve())

    def test_completed_discovery_resumes_paperorchestra_without_opening_draft(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            task_dir = root / "task"
            task_dir.mkdir()
            (task_dir / "prompt.json").write_text("{}", encoding="utf-8")
            launch_dir = root / "existing_launch"
            launch_dir.mkdir()
            (launch_dir / "prompt.json").write_text("{}", encoding="utf-8")
            (launch_dir / "discovery_summary.json").write_text(
                json.dumps(
                    {
                        "total_rounds": 1,
                        "rounds": [
                            {
                                "round": 1,
                                "session_id": "session_1",
                                "results": [],
                                "successful": 0,
                                "failed": 0,
                            }
                        ],
                        "sessions": ["session_1"],
                        "loop_rounds": 1,
                        "loop_mode": "fresh",
                        "original_task_dir": str(task_dir),
                    }
                ),
                encoding="utf-8",
            )
            arguments = Namespace(
                resume=str(launch_dir),
                task=str(task_dir),
                ref_code_path=None,
                output_dir=None,
                config=None,
                skip_idea_generation=False,
            )

            with patch(
                "launch_discovery.parse_arguments", return_value=arguments
            ), patch(
                "launch_discovery.setup_logging",
                return_value=logging.getLogger("completed-launch-test"),
            ), patch("launch_discovery._run_paper_orchestra") as run:
                launch_discovery.main()

            self.assertFalse((launch_dir / "manuscript" / "draft.md").exists())
            run.assert_called_once()
            self.assertEqual(run.call_args.kwargs["launch_dir"], launch_dir)


if __name__ == "__main__":
    unittest.main()
