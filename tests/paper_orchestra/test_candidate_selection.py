from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from vegapunk.paper_orchestra.candidate_selection import select_candidate
from vegapunk.paper_orchestra.data_types import PaperOrchestraStageError


class CandidateSelectionTest(unittest.TestCase):
    def test_selects_sole_success_from_most_recent_successful_round(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            launch_dir = Path(temporary_directory) / "20260710_100000_launch"
            candidate_dir = launch_dir / "session_1" / "candidate-a"
            candidate_dir.mkdir(parents=True)
            summary = {
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
                                "folder_name": "session_2/candidate-b",
                            }
                        ],
                    },
                ],
            }
            (launch_dir / "discovery_summary.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )
            run_dir = launch_dir / "paper_orchestra_runs" / "primary"

            selection = asyncio.run(
                select_candidate(launch_dir=launch_dir, run_dir=run_dir)
            )

            self.assertEqual(selection["selection_method"], "sole_success")
            self.assertEqual(
                selection["paper_candidate_round"],
                {
                    "round": 1,
                    "session_id": "session_1",
                    "skipped_later_rounds": [2],
                    "skipped_later_round_facts": [
                        {
                            "round": 2,
                            "session_id": "session_2",
                            "result_count": 1,
                            "successful_candidate_count": 0,
                        }
                    ],
                },
            )
            self.assertEqual(
                selection["selected_candidate"],
                {
                    "idea_name": "method_a",
                    "folder_name": "session_1/candidate-a",
                },
            )
            persisted = json.loads(
                (run_dir / "candidate_selection.json").read_text(encoding="utf-8")
            )
            self.assertEqual(persisted, selection)

    def test_fails_with_stable_code_when_launch_has_no_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            launch_dir = Path(temporary_directory) / "launch"
            launch_dir.mkdir()
            summary = {
                "launch_id": "launch",
                "mode": "experiment",
                "rounds": [
                    {
                        "round": 1,
                        "session_id": "session_1",
                        "results": [
                            {
                                "success": False,
                                "idea_name": "method_a",
                                "folder_name": "session_1/candidate-a",
                            }
                        ],
                    }
                ],
            }
            (launch_dir / "discovery_summary.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )
            run_dir = launch_dir / "paper_orchestra_runs" / "primary"

            with self.assertRaises(PaperOrchestraStageError) as raised:
                asyncio.run(
                    select_candidate(launch_dir=launch_dir, run_dir=run_dir)
                )

            self.assertEqual(raised.exception.stage, "terminal_candidate_selection")
            self.assertEqual(raised.exception.code, "no_successful_candidate")
            self.assertFalse((run_dir / "candidate_selection.json").exists())

    def test_uses_explicit_primary_metric_and_direction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            launch_dir = Path(temporary_directory) / "launch"
            for candidate, score in (("candidate-a", 0.2), ("candidate-b", 0.1)):
                run_dir = launch_dir / "session_1" / candidate / "run_1"
                run_dir.mkdir(parents=True)
                (run_dir / "final_info.json").write_text(
                    json.dumps({"loss": score}), encoding="utf-8"
                )
            summary = {
                "launch_id": "launch",
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
                            },
                            {
                                "success": True,
                                "idea_name": "method_b",
                                "folder_name": "session_1/candidate-b",
                            },
                        ],
                    }
                ],
            }
            (launch_dir / "discovery_summary.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )
            (launch_dir / "prompt.json").write_text(
                json.dumps(
                    {
                        "metrics": {
                            "primary": "loss",
                            "optimization_direction": "minimize",
                        }
                    }
                ),
                encoding="utf-8",
            )

            selection = asyncio.run(
                select_candidate(
                    launch_dir=launch_dir,
                    run_dir=launch_dir / "paper_orchestra_runs" / "primary",
                )
            )

            self.assertEqual(selection["selection_method"], "metric")
            self.assertEqual(
                selection["criterion"],
                {
                    "source": "task_config",
                    "primary_metric": "loss",
                    "optimization_direction": "minimize",
                    "source_paths": ["prompt.json"],
                    "model_input": None,
                    "model_output": None,
                    "reasoning": None,
                },
            )
            self.assertEqual(
                selection["selected_candidate"]["idea_name"], "method_b"
            )
            self.assertEqual(
                [
                    (item["idea_name"], item["primary_metric_value"])
                    for item in selection["successful_candidates"]
                ],
                [("method_a", 0.2), ("method_b", 0.1)],
            )
            self.assertTrue(
                all(
                    item["metric_source"] == "run_1/final_info.json"
                    for item in selection["successful_candidates"]
                )
            )
            selection_path = (
                launch_dir / "paper_orchestra_runs" / "primary" / "candidate_selection.json"
            )
            forged_fallback = json.loads(json.dumps(selection))
            forged_fallback["criterion"] = {
                "source": "unavailable",
                "primary_metric": None,
                "optimization_direction": None,
                "source_paths": ["prompt.json"],
                "model_input": None,
                "model_output": None,
                "reasoning": "criterion_inference_failed: forged",
            }
            forged_fallback["selection_method"] = "random_fallback"
            forged_fallback["fallback_reason"] = "criterion_inference_failed"
            forged_fallback["fallback_pool"] = [
                {
                    "idea_name": item["idea_name"],
                    "folder_name": item["folder_name"],
                }
                for item in forged_fallback["successful_candidates"]
            ]
            selection_path.write_text(
                json.dumps(forged_fallback), encoding="utf-8"
            )
            with self.assertRaises(PaperOrchestraStageError) as forged_error:
                asyncio.run(
                    select_candidate(
                        launch_dir=launch_dir,
                        run_dir=launch_dir / "paper_orchestra_runs" / "primary",
                    )
                )
            self.assertEqual(
                forged_error.exception.code, "invalid_candidate_selection"
            )

            selection["selected_candidate"] = {
                "idea_name": "method_a",
                "folder_name": "session_1/candidate-a",
            }
            selection_path.write_text(json.dumps(selection), encoding="utf-8")
            with self.assertRaises(PaperOrchestraStageError) as raised:
                asyncio.run(
                    select_candidate(
                        launch_dir=launch_dir,
                        run_dir=launch_dir / "paper_orchestra_runs" / "primary",
                    )
                )
            self.assertEqual(raised.exception.code, "invalid_candidate_selection")

    def test_infers_only_missing_criterion_fields_once(self) -> None:
        class CriterionModel:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            async def generate_json(self, **kwargs: object) -> dict[str, str]:
                self.calls.append(kwargs)
                return {
                    "primary_metric": "loss",
                    "optimization_direction": "maximize",
                    "reasoning": "任务描述把准确率作为最终质量指标。",
                }

        with tempfile.TemporaryDirectory() as temporary_directory:
            launch_dir = Path(temporary_directory) / "launch"
            for candidate, accuracy in (("candidate-a", 0.8), ("candidate-b", 0.9)):
                run_dir = launch_dir / "session_1" / candidate / "run_1"
                run_dir.mkdir(parents=True)
                (run_dir / "final_info.json").write_text(
                    json.dumps({"accuracy": accuracy, "loss": 1 - accuracy}),
                    encoding="utf-8",
                )
            summary = {
                "launch_id": "launch",
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
                            },
                            {
                                "success": True,
                                "idea_name": "method_b",
                                "folder_name": "session_1/candidate-b",
                            },
                        ],
                    }
                ],
            }
            (launch_dir / "discovery_summary.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )
            (launch_dir / "prompt.json").write_text(
                json.dumps(
                    {
                        "description": "选择准确率最高的方法。",
                        "metrics": {"primary": "accuracy"},
                    }
                ),
                encoding="utf-8",
            )
            model = CriterionModel()

            selection = asyncio.run(
                select_candidate(
                    launch_dir=launch_dir,
                    run_dir=launch_dir / "paper_orchestra_runs" / "primary",
                    model=model,
                )
            )

            self.assertEqual(len(model.calls), 1)
            self.assertEqual(selection["criterion"]["source"], "model_inference")
            self.assertEqual(selection["criterion"]["primary_metric"], "accuracy")
            self.assertEqual(
                selection["criterion"]["optimization_direction"], "maximize"
            )
            self.assertEqual(
                selection["criterion"]["model_input"]["missing_fields"],
                ["optimization_direction"],
            )
            self.assertEqual(
                selection["criterion"]["model_input"]["reported_metric_names"],
                ["accuracy", "loss"],
            )
            self.assertEqual(
                selection["criterion"]["model_output"]["primary_metric"], "loss"
            )
            self.assertEqual(
                selection["selected_candidate"]["idea_name"], "method_b"
            )

    def test_randomly_selects_from_successes_when_no_metric_is_comparable(self) -> None:
        class FirstChoice:
            def __init__(self) -> None:
                self.calls = 0

            def choice(self, values: list[dict[str, object]]) -> dict[str, object]:
                self.calls += 1
                return values[0]

        with tempfile.TemporaryDirectory() as temporary_directory:
            launch_dir = Path(temporary_directory) / "launch"
            final_infos = (("candidate-a", {"loss": float("nan")}), ("candidate-b", {}))
            for candidate, final_info in final_infos:
                run_dir = launch_dir / "session_1" / candidate / "run_1"
                run_dir.mkdir(parents=True)
                (run_dir / "final_info.json").write_text(
                    json.dumps(final_info), encoding="utf-8"
                )
            summary = {
                "launch_id": "launch",
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
                            },
                            {
                                "success": True,
                                "idea_name": "method_b",
                                "folder_name": "session_1/candidate-b",
                            },
                        ],
                    }
                ],
            }
            (launch_dir / "discovery_summary.json").write_text(
                json.dumps(summary), encoding="utf-8"
            )
            (launch_dir / "prompt.json").write_text(
                json.dumps(
                    {
                        "metrics": {
                            "primary": "loss",
                            "optimization_direction": "minimize",
                        }
                    }
                ),
                encoding="utf-8",
            )
            random_source = FirstChoice()

            selection = asyncio.run(
                select_candidate(
                    launch_dir=launch_dir,
                    run_dir=launch_dir / "paper_orchestra_runs" / "primary",
                    random_source=random_source,
                )
            )

            self.assertEqual(random_source.calls, 1)
            self.assertEqual(selection["selection_method"], "random_fallback")
            self.assertEqual(
                selection["fallback_reason"], "no_comparable_primary_metric"
            )
            self.assertEqual(
                [item["idea_name"] for item in selection["fallback_pool"]],
                ["method_a", "method_b"],
            )
            self.assertEqual(
                selection["selected_candidate"]["idea_name"], "method_a"
            )
            self.assertTrue(
                all(
                    item["exclusion_reason"] is not None
                    for item in selection["successful_candidates"]
                )
            )

    def test_randomly_breaks_an_exact_metric_tie_within_tie_pool(self) -> None:
        class LastChoice:
            def choice(self, values: list[dict[str, object]]) -> dict[str, object]:
                return values[-1]

        with tempfile.TemporaryDirectory() as temporary_directory:
            launch_dir = Path(temporary_directory) / "launch"
            candidates = (
                ("candidate-a", "method_a", 0.1),
                ("candidate-b", "method_b", 0.1),
                ("candidate-c", "method_c", 0.2),
            )
            results = []
            for candidate, idea_name, score in candidates:
                run_dir = launch_dir / "session_1" / candidate / "run_1"
                run_dir.mkdir(parents=True)
                (run_dir / "final_info.json").write_text(
                    json.dumps({"loss": score}), encoding="utf-8"
                )
                results.append(
                    {
                        "success": True,
                        "idea_name": idea_name,
                        "folder_name": f"session_1/{candidate}",
                    }
                )
            (launch_dir / "discovery_summary.json").write_text(
                json.dumps(
                    {
                        "launch_id": "launch",
                        "mode": "experiment",
                        "rounds": [
                            {
                                "round": 1,
                                "session_id": "session_1",
                                "results": results,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (launch_dir / "prompt.json").write_text(
                json.dumps(
                    {
                        "metrics": {
                            "primary": "loss",
                            "optimization_direction": "minimize",
                        }
                    }
                ),
                encoding="utf-8",
            )

            selection = asyncio.run(
                select_candidate(
                    launch_dir=launch_dir,
                    run_dir=launch_dir / "paper_orchestra_runs" / "primary",
                    random_source=LastChoice(),
                )
            )

            self.assertEqual(selection["selection_method"], "random_tie")
            self.assertEqual(selection["fallback_reason"], "exact_primary_metric_tie")
            self.assertEqual(
                [item["idea_name"] for item in selection["fallback_pool"]],
                ["method_a", "method_b"],
            )
            self.assertEqual(
                selection["selected_candidate"]["idea_name"], "method_b"
            )
            selection["fallback_reason"] = ""
            selection["fallback_pool"].append(
                {
                    "idea_name": "method_c",
                    "folder_name": "session_1/candidate-c",
                }
            )
            selection_path = (
                launch_dir / "paper_orchestra_runs" / "primary" / "candidate_selection.json"
            )
            selection_path.write_text(json.dumps(selection), encoding="utf-8")
            with self.assertRaises(PaperOrchestraStageError) as raised:
                asyncio.run(
                    select_candidate(
                        launch_dir=launch_dir,
                        run_dir=launch_dir / "paper_orchestra_runs" / "primary",
                    )
                )
            self.assertEqual(raised.exception.code, "invalid_candidate_selection")

    def test_randomly_falls_back_and_records_invalid_model_criterion(self) -> None:
        class InvalidCriterionModel:
            async def generate_json(self, **kwargs: object) -> dict[str, str]:
                return {
                    "primary_metric": "invented_metric",
                    "optimization_direction": "maximize",
                    "reasoning": "The requested metric was not reported.",
                }

        class FailingCriterionModel:
            async def generate_json(self, **kwargs: object) -> dict[str, str]:
                raise RuntimeError("provider unavailable")

        class FirstChoice:
            def choice(self, values: list[dict[str, object]]) -> dict[str, object]:
                return values[0]

        class LastChoice:
            def choice(self, values: list[dict[str, object]]) -> dict[str, object]:
                return values[-1]

        with tempfile.TemporaryDirectory() as temporary_directory:
            launch_dir = Path(temporary_directory) / "launch"
            results = []
            for candidate, idea_name, score in (
                ("candidate-a", "method_a", 0.1),
                ("candidate-b", "method_b", 0.2),
            ):
                run_dir = launch_dir / "session_1" / candidate / "run_1"
                run_dir.mkdir(parents=True)
                (run_dir / "final_info.json").write_text(
                    json.dumps({"loss": score}), encoding="utf-8"
                )
                results.append(
                    {
                        "success": True,
                        "idea_name": idea_name,
                        "folder_name": f"session_1/{candidate}",
                    }
                )
            (launch_dir / "discovery_summary.json").write_text(
                json.dumps(
                    {
                        "launch_id": "launch",
                        "mode": "experiment",
                        "rounds": [
                            {
                                "round": 1,
                                "session_id": "session_1",
                                "results": results,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (launch_dir / "prompt.json").write_text(
                json.dumps({"description": "Choose the best result."}),
                encoding="utf-8",
            )

            selection = asyncio.run(
                select_candidate(
                    launch_dir=launch_dir,
                    run_dir=launch_dir / "paper_orchestra_runs" / "primary",
                    model=InvalidCriterionModel(),
                    random_source=LastChoice(),
                )
            )

            self.assertEqual(selection["selection_method"], "random_fallback")
            self.assertEqual(
                selection["fallback_reason"], "invalid_model_criterion"
            )
            self.assertEqual(
                selection["selected_candidate"]["idea_name"], "method_b"
            )
            self.assertIn(
                "invented_metric", selection["criterion"]["reasoning"]
            )
            self.assertEqual(
                selection["criterion"]["model_input"]["reported_metric_names"],
                ["loss"],
            )
            self.assertEqual(
                selection["criterion"]["model_output"]["primary_metric"],
                "invented_metric",
            )
            resumed = asyncio.run(
                select_candidate(
                    launch_dir=launch_dir,
                    run_dir=launch_dir / "paper_orchestra_runs" / "primary",
                )
            )
            self.assertEqual(resumed, selection)

            selection["criterion"]["model_input"] = None
            selection_path = (
                launch_dir / "paper_orchestra_runs" / "primary" / "candidate_selection.json"
            )
            selection_path.write_text(json.dumps(selection), encoding="utf-8")
            with self.assertRaises(PaperOrchestraStageError) as raised:
                asyncio.run(
                    select_candidate(
                        launch_dir=launch_dir,
                        run_dir=launch_dir / "paper_orchestra_runs" / "primary",
                    )
                )
            self.assertEqual(raised.exception.code, "invalid_candidate_selection")

            failure_run_dir = launch_dir / "paper_orchestra_runs" / "provider-failure"
            failed_inference = asyncio.run(
                select_candidate(
                    launch_dir=launch_dir,
                    run_dir=failure_run_dir,
                    model=FailingCriterionModel(),
                    random_source=FirstChoice(),
                )
            )
            self.assertEqual(
                failed_inference["fallback_reason"], "criterion_inference_failed"
            )
            self.assertIsNotNone(failed_inference["criterion"]["model_input"])
            self.assertIsNone(failed_inference["criterion"]["model_output"])
            self.assertEqual(
                asyncio.run(
                    select_candidate(
                        launch_dir=launch_dir,
                        run_dir=failure_run_dir,
                    )
                ),
                failed_inference,
            )

    def test_randomly_falls_back_when_prompt_is_missing(self) -> None:
        class FirstChoice:
            def choice(self, values: list[dict[str, object]]) -> dict[str, object]:
                return values[0]

        class LastChoice:
            def choice(self, values: list[dict[str, object]]) -> dict[str, object]:
                return values[-1]

        with tempfile.TemporaryDirectory() as temporary_directory:
            launch_dir = Path(temporary_directory) / "launch"
            results = []
            for candidate, idea_name in (
                ("candidate-a", "method_a"),
                ("candidate-b", "method_b"),
            ):
                (launch_dir / "session_1" / candidate).mkdir(parents=True)
                results.append(
                    {
                        "success": True,
                        "idea_name": idea_name,
                        "folder_name": f"session_1/{candidate}",
                    }
                )
            (launch_dir / "discovery_summary.json").write_text(
                json.dumps(
                    {
                        "launch_id": "launch",
                        "mode": "experiment",
                        "rounds": [
                            {
                                "round": 1,
                                "session_id": "session_1",
                                "results": results,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            selection = asyncio.run(
                select_candidate(
                    launch_dir=launch_dir,
                    run_dir=launch_dir / "paper_orchestra_runs" / "primary",
                    random_source=FirstChoice(),
                )
            )

            self.assertEqual(selection["selection_method"], "random_fallback")
            self.assertEqual(
                selection["fallback_reason"], "criterion_source_unavailable"
            )
            self.assertEqual(selection["criterion"]["source"], "unavailable")
            self.assertIn(
                "prompt.json", selection["criterion"]["reasoning"]
            )
            resumed = asyncio.run(
                select_candidate(
                    launch_dir=launch_dir,
                    run_dir=launch_dir / "paper_orchestra_runs" / "primary",
                    random_source=LastChoice(),
                )
            )
            self.assertEqual(resumed, selection)
            selection_path = (
                launch_dir / "paper_orchestra_runs" / "primary" / "candidate_selection.json"
            )
            temporary_path = selection_path.with_suffix(".json.tmp")
            selection_path.replace(temporary_path)

            recovered = asyncio.run(
                select_candidate(
                    launch_dir=launch_dir,
                    run_dir=launch_dir / "paper_orchestra_runs" / "primary",
                    random_source=LastChoice(),
                )
            )

            self.assertEqual(recovered, selection)
            self.assertTrue(selection_path.is_file())
            self.assertFalse(temporary_path.exists())

    def test_rejects_persisted_selection_outside_successful_candidate_pool(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            launch_dir = Path(temporary_directory) / "launch"
            for candidate in ("candidate-a", "candidate-b"):
                (launch_dir / "session_1" / candidate).mkdir(parents=True)
            (launch_dir / "discovery_summary.json").write_text(
                json.dumps(
                    {
                        "launch_id": "launch",
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
                                    },
                                    {
                                        "success": False,
                                        "idea_name": "method_b",
                                        "folder_name": "session_1/candidate-b",
                                    },
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            run_dir = launch_dir / "paper_orchestra_runs" / "primary"
            selection = asyncio.run(
                select_candidate(launch_dir=launch_dir, run_dir=run_dir)
            )
            selection["selected_candidate"] = {
                "idea_name": "method_b",
                "folder_name": "session_1/candidate-b",
            }
            (run_dir / "candidate_selection.json").write_text(
                json.dumps(selection), encoding="utf-8"
            )

            with self.assertRaises(PaperOrchestraStageError) as raised:
                asyncio.run(
                    select_candidate(launch_dir=launch_dir, run_dir=run_dir)
                )

            self.assertEqual(raised.exception.code, "invalid_candidate_selection")

    def test_resolves_vegapunk_repo_relative_candidate_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            launch_dir = Path(temporary_directory) / "launch"
            (launch_dir / "session_1" / "candidate-a").mkdir(parents=True)
            folder_name = "results/task/launch/session_1/candidate-a"
            (launch_dir / "discovery_summary.json").write_text(
                json.dumps(
                    {
                        "launch_id": "launch",
                        "mode": "experiment",
                        "rounds": [
                            {
                                "round": 1,
                                "session_id": "session_1",
                                "results": [
                                    {
                                        "success": True,
                                        "idea_name": "method_a",
                                        "folder_name": folder_name,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            selection = asyncio.run(
                select_candidate(
                    launch_dir=launch_dir,
                    run_dir=launch_dir / "paper_orchestra_runs" / "primary",
                )
            )

            self.assertEqual(selection["selected_candidate"]["folder_name"], folder_name)
