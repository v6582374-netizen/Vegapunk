from __future__ import annotations

import io
import logging
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from internagent.research_draft import (
    ResearchDraft,
    attach_research_draft_hook,
    attach_sync_research_draft_hook,
    record_research_event,
    start_research_draft_capture,
    stop_research_draft_capture,
)
from internagent.mas.models.base_model import BaseModel
from internagent.mas.models.runtime import ModelRunRequest, ModelRunResult, OutputText
from internagent.experiments_utils_claude import ClaudeCodeRunner


class ResearchDraftTest(unittest.TestCase):
    def test_reopening_a_launch_appends_blocks_without_rewriting_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            launch_dir = Path(temporary_directory) / "launch"

            draft = ResearchDraft.open(launch_dir)
            draft.append("first observation")

            resumed = ResearchDraft.open(launch_dir)
            resumed.append("second observation")

            self.assertEqual(
                resumed.path,
                (launch_dir / "manuscript" / "draft.md").resolve(),
            )
            self.assertEqual(
                resumed.path.read_text(encoding="utf-8"),
                "first observation\n"
                "<!-- draft-block -->\n"
                "second observation\n",
            )

    def test_structured_blocks_preserve_formula_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            draft = ResearchDraft.open(Path(temporary_directory) / "launch")

            draft.append(
                {
                    "formula": r"\[\mathcal{L}=\sum_i w_i\ell_i\]",
                    "assumptions": ["w_i >= 0", r"\sum_i w_i = 1"],
                }
            )

            content = draft.path.read_text(encoding="utf-8")
            self.assertIn(r"\[\mathcal{L}=\sum_i w_i\ell_i\]", content)
            self.assertIn(r"\sum_i w_i = 1", content)

    def test_concurrent_appends_never_interleave_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            draft = ResearchDraft.open(Path(temporary_directory) / "launch")
            observations = [f"begin-{index}\nend-{index}" for index in range(20)]

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(draft.append, observations))

            blocks = draft.path.read_text(encoding="utf-8").split(
                "<!-- draft-block -->\n"
            )
            self.assertCountEqual(
                [block.rstrip("\n") for block in blocks], observations
            )

    def test_activation_scopes_runtime_event_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            draft = ResearchDraft.open(Path(temporary_directory) / "launch")

            record_research_event("before activation")
            with draft.activate():
                record_research_event("captured event")
            record_research_event("after deactivation")

            self.assertEqual(
                draft.path.read_text(encoding="utf-8"), "captured event\n"
            )

    def test_activation_mirrors_logs_stdout_and_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            draft = ResearchDraft.open(Path(temporary_directory) / "launch")
            stdout = io.StringIO()
            stderr = io.StringIO()
            logger = logging.getLogger("research-draft-test")
            logger.setLevel(logging.INFO)

            with redirect_stdout(stdout), redirect_stderr(stderr):
                with draft.activate():
                    print("visible stdout")
                    sys.stderr.write("visible stderr\n")
                    logger.info("visible log")

            content = draft.path.read_text(encoding="utf-8")
            self.assertIn("visible stdout", content)
            self.assertIn("visible stderr", content)
            self.assertIn("visible log", content)
            self.assertIn("visible stdout", stdout.getvalue())
            self.assertIn("visible stderr", stderr.getvalue())

    def test_process_level_capture_can_stop_before_paperorchestra(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            draft = ResearchDraft.open(Path(temporary_directory) / "launch")

            start_research_draft_capture(draft)
            record_research_event("discovery event")
            stop_research_draft_capture()
            record_research_event("paper event")

            self.assertEqual(
                draft.path.read_text(encoding="utf-8"), "discovery event\n"
            )


class ResearchDraftAgentHookTest(unittest.IsolatedAsyncioTestCase):
    async def test_async_agent_input_and_output_append_directly(self) -> None:
        class EchoAgent:
            async def execute(
                self, question: str, params: dict[str, object]
            ) -> dict[str, object]:
                return {"question": question, "formula": params["formula"]}

        with tempfile.TemporaryDirectory() as temporary_directory:
            draft = ResearchDraft.open(Path(temporary_directory) / "launch")
            agent = attach_research_draft_hook(EchoAgent())

            with draft.activate():
                output = await agent.execute(
                    "derive the objective", {"formula": r"\min_\theta L(\theta)"}
                )

            content = draft.path.read_text(encoding="utf-8")
            self.assertIn("derive the objective", content)
            self.assertIn(r"\min_\theta L(\theta)", content)
            self.assertEqual(
                output,
                {
                    "question": "derive the objective",
                    "formula": r"\min_\theta L(\theta)",
                },
            )

    async def test_sync_agent_uses_the_same_direct_capture(self) -> None:
        class SyncAgent:
            def execute(self, observation: str) -> str:
                return observation.upper()

        with tempfile.TemporaryDirectory() as temporary_directory:
            draft = ResearchDraft.open(Path(temporary_directory) / "launch")
            agent = attach_sync_research_draft_hook(SyncAgent())

            with draft.activate():
                output = agent.execute("measured result")

            content = draft.path.read_text(encoding="utf-8")
            self.assertIn("measured result", content)
            self.assertIn("MEASURED RESULT", content)
            self.assertEqual(output, "MEASURED RESULT")

    async def test_model_runtime_appends_request_and_raw_response(self) -> None:
        class RecordingModel(BaseModel):
            async def _run(self, request: ModelRunRequest) -> ModelRunResult:
                return ModelRunResult(
                    response_id="response-17",
                    status="completed",
                    model="test-model",
                    items=(OutputText(text=r"Derived \(z = Ax\)"),),
                    raw_response={"provider_payload": "exact raw response"},
                )

            @classmethod
            def from_config(cls, config: dict[str, object]) -> "RecordingModel":
                return cls()

        with tempfile.TemporaryDirectory() as temporary_directory:
            draft = ResearchDraft.open(Path(temporary_directory) / "launch")
            request = ModelRunRequest(
                input=(), instructions="derive the complete equation"
            )

            with draft.activate():
                await RecordingModel().run(request)

            content = draft.path.read_text(encoding="utf-8")
            self.assertIn("derive the complete equation", content)
            self.assertIn(r"Derived \(z = Ax\)", content)
            self.assertIn("exact raw response", content)


class ClaudeCodeDraftCaptureTest(unittest.TestCase):
    def test_runner_keeps_json_mode_and_records_exact_process_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            draft = ResearchDraft.open(root / "launch")
            completed = CompletedProcess(
                ["claude"],
                0,
                stdout='{"session_id":"session-4","result":"finished"}',
                stderr="provider warning",
            )

            with draft.activate(), patch(
                "internagent.experiments_utils_claude.subprocess.run",
                return_value=completed,
            ) as run_command:
                output = ClaudeCodeRunner(model="claude-test").run(
                    "run the exact experiment", cwd=root
                )

            command = run_command.call_args.args[0]
            self.assertEqual(
                command[command.index("--output-format") + 1], "json"
            )
            content = draft.path.read_text(encoding="utf-8")
            self.assertIn("--output-format", content)
            self.assertIn("run the exact experiment", content)
            self.assertIn(completed.stdout, content)
            self.assertIn(completed.stderr, content)
            self.assertEqual(output, "finished")


if __name__ == "__main__":
    unittest.main()
