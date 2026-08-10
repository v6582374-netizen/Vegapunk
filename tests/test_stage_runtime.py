from __future__ import annotations

import logging
import tempfile
import unittest
import asyncio
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from vegapunk.stage import ExperimentRunner, IdeaGenerator


class ExperimentRunnerRuntimeTest(unittest.TestCase):
    def test_empty_auto_task_defers_mcts_until_a_measured_baseline_exists(self) -> None:
        logger = logging.getLogger("stage-bootstrap-test")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline = root / "baseline"
            baseline.mkdir()
            results = root / "results"
            results.mkdir()
            runner = ExperimentRunner(
                Namespace(
                    exp_backend="codex",
                    task_dir=str(baseline),
                    task_type="auto",
                ),
                logger,
                config={
                    "experiment": {
                        "gpu_per_experiment": 1.0,
                        "max_parallel_experiments": 1,
                        "max_runs": 1,
                        "use_mcts": True,
                    }
                },
                model_runtime=object(),
            )

            with patch(
                "vegapunk.stage.perform_experiments_codex",
                return_value=False,
            ) as normal, patch(
                "vegapunk.stage.perform_experiments_mcts_codex"
            ) as mcts:
                runner.run_codex_experiment(
                    str(baseline),
                    str(results),
                    {
                        "name": "bootstrap-test",
                        "title": "Bootstrap test",
                        "description": "Create a baseline first",
                        "method": "No-op",
                    },
                )

        normal.assert_called_once()
        mcts.assert_not_called()

    def test_empty_auto_task_enters_mcts_after_the_baseline_stage(self) -> None:
        logger = logging.getLogger("stage-bootstrap-mcts-test")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline = root / "baseline"
            baseline.mkdir()
            results = root / "results"
            results.mkdir()
            runner = ExperimentRunner(
                Namespace(
                    exp_backend="codex",
                    task_dir=str(baseline),
                    task_type="auto",
                ),
                logger,
                config={
                    "experiment": {
                        "gpu_per_experiment": 1.0,
                        "max_parallel_experiments": 1,
                        "max_runs": 1,
                        "use_mcts": True,
                    }
                },
                model_runtime=object(),
            )

            with patch(
                "vegapunk.stage.perform_experiments_codex",
                return_value=True,
            ) as normal, patch(
                "vegapunk.stage.perform_experiments_mcts_codex",
                return_value=True,
            ) as mcts:
                runner.run_codex_experiment(
                    str(baseline),
                    str(results),
                    {
                        "name": "bootstrap-mcts-test",
                        "title": "Bootstrap MCTS test",
                        "description": "Create a baseline then use MCTS",
                        "method": "No-op",
                    },
                )

        self.assertTrue(normal.call_args.kwargs["stop_after_baseline"])
        mcts.assert_called_once()

    def test_claude_experiment_passes_the_injected_runtime_to_the_adapter(self) -> None:
        logger = logging.getLogger("stage-runtime-test")
        runtime = object()

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline = root / "baseline"
            (baseline / "code").mkdir(parents=True)
            (baseline / "code" / "experiment.py").write_text(
                "print('baseline')\n", encoding="utf-8"
            )
            results = root / "results"
            results.mkdir()
            runner = ExperimentRunner(
                Namespace(
                    exp_backend="codex",
                    task_dir=str(baseline),
                    task_type="auto",
                ),
                logger,
                config={
                    "experiment": {
                        "gpu_per_experiment": 1.0,
                        "max_parallel_experiments": 1,
                        "max_runs": 1,
                        "use_mcts": False,
                    }
                },
                model_runtime=runtime,
            )

            with patch(
                "vegapunk.stage.perform_experiments_codex",
                return_value=False,
            ) as perform_experiments:
                success, _ = runner.run_codex_experiment(
                    str(baseline),
                    str(results),
                    {
                        "name": "runtime-test",
                        "title": "Runtime test",
                        "description": "Verify runtime forwarding",
                        "method": "No-op",
                    },
                )

        self.assertFalse(success)
        self.assertIs(perform_experiments.call_args.kwargs["runtime"], runtime)


class IdeaGeneratorRuntimeTest(unittest.TestCase):
    def test_idea_generator_passes_the_injected_runtime_to_its_interface(self) -> None:
        runtime = object()
        args = Namespace(
            config="config/default_config.yaml",
            exp_backend="codex",
            task_dir="tasks/AutoClsSST",
            task_name="AutoClsSST",
        )

        with patch("vegapunk.stage.LONG_MEMORY_AVAILABLE", False), patch(
            "vegapunk.stage.VegapunkInterface"
        ) as interface:
            IdeaGenerator(
                args,
                logging.getLogger("idea-runtime-test"),
                config={},
                model_runtime=runtime,
            )

        self.assertIs(interface.call_args.kwargs["model_runtime"], runtime)

    def test_idea_generation_surfaces_workflow_error_details(self) -> None:
        class FailedSessionInterface:
            async def get_session_status(self, _session_id: str) -> dict[str, object]:
                return {
                    "state": "error",
                    "iterations_completed": 0,
                    "error": "Ranking phase cannot continue: no ideas were produced for iteration 1",
                }

        generator = object.__new__(IdeaGenerator)
        generator.session_id = "session-failed"
        generator.status = None
        generator.interface = FailedSessionInterface()
        generator.logger = logging.getLogger("idea-error-test")
        generator.args = type("Args", (), {})()

        with self.assertRaisesRegex(
            RuntimeError,
            "Ranking phase cannot continue: no ideas were produced for iteration 1",
        ):
            asyncio.run(generator.generate_ideas())


if __name__ == "__main__":
    unittest.main()
