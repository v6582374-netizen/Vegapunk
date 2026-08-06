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
    def test_experience_generation_uses_the_shared_runtime(self) -> None:
        observed = {}

        class Memory:
            def load_idea_generation_output(self, _: str) -> None:
                pass

            def load_all_notes_from_directory(self, *_: object) -> None:
                pass

            def get_memory_summary(self) -> dict[str, int]:
                return {"total_ideas": 1, "total_experiments": 1}

        class ExperienceGenerator:
            def __init__(self, *, logger, config, runtime) -> None:
                observed["logger"] = logger
                observed["config"] = config
                observed["runtime"] = runtime

            async def generate_experiences_from_memory(self, **_: object) -> dict[str, list]:
                return {"new_experiences": [], "updated_library": []}

        long_memory_stub = types.ModuleType("vegapunk.mas.memory.long_memory")
        long_memory_stub.ExperienceGenerator = ExperienceGenerator

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            prompt_path = root / "prompt.json"
            prompt_path.write_text('{"domain": "testing"}', encoding="utf-8")
            args = Namespace(
                prompt_path=str(prompt_path),
                task_dir=str(root),
                output_dir=str(root),
                base_output_dir=str(root),
                task_name="runtime-test",
                config={"agents": {"experience": {"temperature": 0.1}}},
            )
            runtime = object()
            logger = logging.getLogger("experience-runtime-test")

            with patch.dict(sys.modules, {"vegapunk.mas.memory.long_memory": long_memory_stub}):
                result = launch_discovery._generate_experiences_for_round(
                    args,
                    Memory(),
                    "session_1",
                    logger,
                    model_runtime=runtime,
                    config=args.config,
                )

        self.assertTrue(result)
        self.assertIs(observed["runtime"], runtime)
        self.assertIs(observed["config"], args.config)

    def test_experience_generation_skips_without_a_runtime(self) -> None:
        class Memory:
            def load_idea_generation_output(self, _: str) -> None:
                pass

            def load_all_notes_from_directory(self, *_: object) -> None:
                pass

            def get_memory_summary(self) -> dict[str, int]:
                return {"total_ideas": 1, "total_experiments": 1}

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            prompt_path = root / "prompt.json"
            prompt_path.write_text("{}", encoding="utf-8")
            args = Namespace(
                prompt_path=str(prompt_path),
                task_dir=str(root),
                output_dir=str(root),
                task_name="runtime-test",
                config={},
            )

            result = launch_discovery._generate_experiences_for_round(
                args,
                Memory(),
                "session_1",
                logging.getLogger("experience-runtime-missing-test"),
                config=args.config,
            )

        self.assertFalse(result)

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

    def test_new_discovery_launch_automatically_hands_off(
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

        stage_stub = types.ModuleType("vegapunk.stage")
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
                exp_backend="codex",
            )

            previous_directory = Path.cwd()
            os.chdir(root)
            try:
                with patch.dict(sys.modules, {"vegapunk.stage": stage_stub}), patch(
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
            run.assert_called_once()
            called_launch = root / run.call_args.kwargs["launch_dir"]
            self.assertEqual(called_launch.resolve(), launches[0].resolve())

    def test_experiment_launch_shares_one_runtime_with_both_stages(self) -> None:
        observed_runtimes = []

        class IdeaGenerator:
            def __init__(
                self, *_: object, model_runtime: object, **__: object
            ) -> None:
                observed_runtimes.append(model_runtime)
                self.session_id = "session_1"

            async def generate_ideas(self) -> tuple[list[dict[str, str]], str]:
                return (
                    [{"refined_method_details": {"name": "measured idea"}}],
                    "session.json",
                )

        class ExperimentRunner:
            def __init__(self, *_: object, model_runtime: object, **__: object) -> None:
                observed_runtimes.append(model_runtime)

            def run_experiments(self, **_: object) -> list[dict[str, object]]:
                return [{"idea_name": "measured idea", "success": False}]

        stage_stub = types.ModuleType("vegapunk.stage")
        stage_stub.IdeaGenerator = IdeaGenerator
        stage_stub.ExperimentRunner = ExperimentRunner

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            task_dir = root / "task"
            task_dir.mkdir()
            (task_dir / "prompt.json").write_text("{}", encoding="utf-8")
            runtime = object()
            arguments = Namespace(
                resume=None,
                task=str(task_dir),
                ref_code_path=None,
                output_dir="runtime-test",
                config=None,
                skip_idea_generation=False,
                idea_path=None,
                mode="experiment",
                exp_backend="codex",
            )

            previous_directory = Path.cwd()
            os.chdir(root)
            try:
                with patch.dict(sys.modules, {"vegapunk.stage": stage_stub}), patch(
                    "launch_discovery.parse_arguments", return_value=arguments
                ), patch(
                    "launch_discovery.setup_logging",
                    return_value=logging.getLogger("runtime-launch-test"),
                ), patch.object(
                    launch_discovery, "LONG_MEMORY_AVAILABLE", False
                ), patch.object(
                    launch_discovery,
                    "create_model_runtime",
                    return_value=runtime,
                ) as create_runtime, patch(
                    "launch_discovery._handoff_to_paper_orchestra"
                ):
                    launch_discovery.main()
            finally:
                os.chdir(previous_directory)

        create_runtime.assert_called_once_with({})
        self.assertEqual(observed_runtimes, [runtime, runtime])

    def test_skipped_idea_generation_still_injects_runtime_into_experiments(self) -> None:
        observed_runtimes = []

        class ExperimentRunner:
            def __init__(self, *_: object, model_runtime: object, **__: object) -> None:
                observed_runtimes.append(model_runtime)

            def run_experiments(self, **_: object) -> list[dict[str, object]]:
                return [{"idea_name": "reused idea", "success": False}]

        stage_stub = types.ModuleType("vegapunk.stage")
        stage_stub.IdeaGenerator = object
        stage_stub.ExperimentRunner = ExperimentRunner

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            task_dir = root / "task"
            task_dir.mkdir()
            (task_dir / "prompt.json").write_text("{}", encoding="utf-8")
            ideas_path = root / "session_1_ideas.json"
            ideas_path.write_text(
                json.dumps([{"name": "reused idea"}]), encoding="utf-8"
            )
            runtime = object()
            arguments = Namespace(
                resume=None,
                task=str(task_dir),
                ref_code_path=None,
                output_dir="runtime-skip-test",
                config=None,
                skip_idea_generation=True,
                idea_path=str(ideas_path),
                mode="experiment",
                exp_backend="codex",
            )

            previous_directory = Path.cwd()
            os.chdir(root)
            try:
                with patch.dict(sys.modules, {"vegapunk.stage": stage_stub}), patch(
                    "launch_discovery.parse_arguments", return_value=arguments
                ), patch(
                    "launch_discovery.setup_logging",
                    return_value=logging.getLogger("runtime-skip-launch-test"),
                ), patch.object(
                    launch_discovery, "LONG_MEMORY_AVAILABLE", False
                ), patch(
                    "launch_discovery.create_model_runtime", return_value=runtime
                ) as create_runtime, patch(
                    "launch_discovery._handoff_to_paper_orchestra"
                ):
                    launch_discovery.main()
            finally:
                os.chdir(previous_directory)

        create_runtime.assert_called_once_with({})
        self.assertEqual(observed_runtimes, [runtime])

    def test_completed_discovery_resumes_paperorchestra(
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

            run.assert_called_once()
            self.assertEqual(run.call_args.kwargs["launch_dir"], launch_dir)


if __name__ == "__main__":
    unittest.main()
