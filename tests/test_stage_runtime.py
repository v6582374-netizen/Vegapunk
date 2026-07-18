from __future__ import annotations

import logging
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from internagent.stage import ExperimentRunner, IdeaGenerator


class ExperimentRunnerRuntimeTest(unittest.TestCase):
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
                    exp_backend="claudecode",
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
                "internagent.stage.perform_experiments_claudecode",
                return_value=False,
            ) as perform_experiments:
                success, _ = runner.run_claude_experiment(
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
            exp_backend="claudecode",
            task_dir="tasks/AutoClsSST",
            task_name="AutoClsSST",
        )

        with patch("internagent.stage.LONG_MEMORY_AVAILABLE", False), patch(
            "internagent.stage.InternAgentInterface"
        ) as interface:
            IdeaGenerator(
                args,
                logging.getLogger("idea-runtime-test"),
                config={},
                model_runtime=runtime,
            )

        self.assertIs(interface.call_args.kwargs["model_runtime"], runtime)


if __name__ == "__main__":
    unittest.main()
