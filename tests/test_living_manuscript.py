from __future__ import annotations

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess
from threading import Lock
from time import sleep
from unittest.mock import patch

from internagent.experiments_utils_claude import ClaudeCodeRunner
from internagent.living_manuscript import (
    AgentTaskContext,
    ClaudeCodeSculptor,
    ClaudeSessionTaskContext,
    LatexManuscriptValidator,
    LivingManuscript,
    ManuscriptValidationError,
    attach_living_manuscript_hook,
    clear_active_living_manuscript,
    set_active_living_manuscript,
)
from internagent.mas.models.base_model import BaseModel
from internagent.mas.models.runtime import ModelRunRequest, ModelRunResult


@dataclass
class RepairingSculptor:
    started_with: AgentTaskContext | None = None
    resumed_session_id: str | None = None
    diagnostics: str | None = None
    terminal_selection: dict[str, object] | None = None
    selected_candidate_path: Path | None = None

    def start_from_agent_task(
        self,
        *,
        manuscript: LivingManuscript,
        task: AgentTaskContext,
    ) -> str:
        self.started_with = task
        manuscript.tex_path.write_text("invalid draft", encoding="utf-8")
        return "sculptor-session-1"

    def resume(
        self,
        *,
        manuscript: LivingManuscript,
        session_id: str,
        diagnostics: str,
    ) -> None:
        self.resumed_session_id = session_id
        self.diagnostics = diagnostics
        manuscript.tex_path.write_text("valid draft", encoding="utf-8")

    def start_from_terminal_selection(
        self,
        *,
        manuscript: LivingManuscript,
        selection: dict[str, object],
        selected_candidate_path: Path,
    ) -> str:
        self.terminal_selection = selection
        self.selected_candidate_path = selected_candidate_path
        manuscript.tex_path.write_text("valid draft", encoding="utf-8")
        return "terminal-session-1"


@dataclass
class ClaudeTaskRecordingSculptor(RepairingSculptor):
    claude_task: ClaudeSessionTaskContext | None = None

    def start_from_claude_session(
        self,
        *,
        manuscript: LivingManuscript,
        task: ClaudeSessionTaskContext,
    ) -> str:
        self.claude_task = task
        manuscript.tex_path.write_text("valid draft", encoding="utf-8")
        return "forked-sculptor-session"


class ConcurrencyRecordingSculptor(RepairingSculptor):
    def __init__(self) -> None:
        super().__init__()
        self._counter_lock = Lock()
        self.active = 0
        self.maximum_active = 0

    def start_from_agent_task(
        self,
        *,
        manuscript: LivingManuscript,
        task: AgentTaskContext,
    ) -> str:
        with self._counter_lock:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
        sleep(0.03)
        with self._counter_lock:
            self.active -= 1
        return f"session-{task.agent_name}"


class DraftValidator:
    def validate(self, manuscript: LivingManuscript) -> None:
        if manuscript.tex_path.read_text(encoding="utf-8") != "valid draft":
            raise ManuscriptValidationError("main.tex is not valid")


class AlwaysValidValidator:
    def validate(self, manuscript: LivingManuscript) -> None:
        return None


@dataclass
class RecordedCommand:
    command: list[str]
    cwd: Path


class RecordingCommandRunner:
    def __init__(self) -> None:
        self.calls: list[RecordedCommand] = []

    def __call__(
        self,
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> CompletedProcess[str]:
        self.calls.append(RecordedCommand(command=command, cwd=cwd))
        return CompletedProcess(
            command,
            0,
            stdout='{"session_id":"sculptor-session","result":"done"}',
            stderr="",
        )


class LivingManuscriptTest(unittest.TestCase):
    def test_sculptor_prompt_grants_editorial_freedom_without_research_authority(
        self,
    ) -> None:
        prompt_path = (
            Path(__file__).parents[1]
            / "internagent"
            / "manuscript_sculptor_prompt.md"
        )

        prompt = prompt_path.read_text(encoding="utf-8").lower()

        self.assertIn("publication-oriented", prompt)
        self.assertIn("add, delete, rewrite, reorganize", prompt)
        self.assertIn("make no change", prompt)
        self.assertIn("do not initiate or request research", prompt)
        self.assertIn("do not alter authoritative", prompt)
        self.assertIn("no placeholders", prompt)
        self.assertIn("argument density", prompt)
        self.assertIn("internal multi-agent", prompt)
        self.assertIn("shared elegantpaper resources as read-only", prompt)

    def test_initializes_one_minimal_manuscript_without_copying_template(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            launch_dir = root / "launch"
            template_dir = root / "elegantpaper"
            template_dir.mkdir()
            (template_dir / "elegantpaper.cls").write_text(
                "shared class", encoding="utf-8"
            )

            manuscript = LivingManuscript.initialize(
                launch_dir=launch_dir,
                template_dir=template_dir,
            )

            self.assertEqual(
                manuscript.tex_path,
                (launch_dir / "manuscript" / "main.tex").resolve(),
            )
            self.assertEqual(
                manuscript.bibliography_path,
                (launch_dir / "manuscript" / "references.bib").resolve(),
            )
            self.assertEqual(
                manuscript.tex_path.read_text(encoding="utf-8"),
                "\\documentclass[lang=cn]{elegantpaper}\n\n"
                "\\begin{document}\n"
                "\\null\n"
                "\\end{document}\n",
            )
            self.assertEqual(
                manuscript.bibliography_path.read_text(encoding="utf-8"), ""
            )
            self.assertFalse(
                (launch_dir / "manuscript" / "elegantpaper.cls").exists()
            )
            self.assertEqual(
                (template_dir / "elegantpaper.cls").read_text(encoding="utf-8"),
                "shared class",
            )

    def test_latex_validation_uses_shared_template_and_returns_exact_diagnostics(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template_dir = root / "elegantpaper"
            template_dir.mkdir()
            (template_dir / "elegantpaper.cls").write_text(
                "shared class", encoding="utf-8"
            )
            recorded: dict[str, object] = {}

            def fail_compile(
                command: list[str],
                *,
                cwd: Path,
                env: dict[str, str],
                capture_output: bool,
                text: bool,
                timeout: int,
                check: bool,
            ) -> CompletedProcess[str]:
                recorded.update(command=command, cwd=cwd, env=env)
                return CompletedProcess(
                    command,
                    1,
                    stdout="main.tex:7: Undefined control sequence.",
                    stderr="latexmk: failure",
                )

            manuscript = LivingManuscript.initialize(
                launch_dir=root / "launch",
                template_dir=template_dir,
            )
            validator = LatexManuscriptValidator(run_command=fail_compile)

            with self.assertRaises(ManuscriptValidationError) as raised:
                validator.validate(manuscript)

            self.assertIn(
                "main.tex:7: Undefined control sequence.", str(raised.exception)
            )
            self.assertIn("latexmk: failure", str(raised.exception))
            self.assertEqual(recorded["cwd"], manuscript.manuscript_dir)
            self.assertIn("-pdfxe", recorded["command"])
            self.assertTrue(
                str(recorded["env"]["TEXINPUTS"]).startswith(
                    str(template_dir.resolve())
                )
            )
            self.assertIn(
                "Undefined control sequence",
                (manuscript.manuscript_dir / "validation.log").read_text(
                    encoding="utf-8"
                ),
            )

    def test_latex_validation_rejects_unresolved_citations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template_dir = root / "elegantpaper"
            template_dir.mkdir()
            (template_dir / "elegantpaper.cls").write_text("class", encoding="utf-8")
            manuscript = LivingManuscript.initialize(
                launch_dir=root / "launch",
                template_dir=template_dir,
            )

            def compile_with_warning(
                command: list[str], **kwargs: object
            ) -> CompletedProcess[str]:
                (manuscript.manuscript_dir / "main.log").write_text(
                    "LaTeX Warning: Citation `missing' undefined.",
                    encoding="utf-8",
                )
                return CompletedProcess(
                    command,
                    0,
                    stdout="latexmk completed",
                    stderr="",
                )

            validator = LatexManuscriptValidator(run_command=compile_with_warning)

            with self.assertRaises(ManuscriptValidationError) as raised:
                validator.validate(manuscript)

            self.assertIn(
                "UNRESOLVED CITATIONS OR REFERENCES", str(raised.exception)
            )

    def test_repairs_current_files_with_the_same_sculptor_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template_dir = root / "elegantpaper"
            template_dir.mkdir()
            (template_dir / "elegantpaper.cls").write_text(
                "shared class", encoding="utf-8"
            )
            sculptor = RepairingSculptor()
            manuscript = LivingManuscript.initialize(
                launch_dir=root / "launch",
                template_dir=template_dir,
                sculptor=sculptor,
                validator=DraftValidator(),
            )
            task = AgentTaskContext(
                agent_name="ScholarAgent",
                input={"query": "prior work"},
                output={"references": ["paper-a"]},
                error=None,
                model_interactions=({"response_id": "response-1"},),
            )

            manuscript.consider_agent_task(task)

            self.assertIs(sculptor.started_with, task)
            self.assertEqual(sculptor.resumed_session_id, "sculptor-session-1")
            self.assertEqual(sculptor.diagnostics, "main.tex is not valid")
            self.assertEqual(
                manuscript.tex_path.read_text(encoding="utf-8"), "valid draft"
            )

    def test_concurrent_task_completions_serialize_manuscript_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template_dir = root / "elegantpaper"
            template_dir.mkdir()
            (template_dir / "elegantpaper.cls").write_text("class", encoding="utf-8")
            sculptor = ConcurrencyRecordingSculptor()
            manuscript = LivingManuscript.initialize(
                launch_dir=root / "launch",
                template_dir=template_dir,
                sculptor=sculptor,
                validator=AlwaysValidValidator(),
            )
            tasks = [
                AgentTaskContext(
                    agent_name=f"agent-{index}",
                    input=index,
                    output=index,
                    error=None,
                )
                for index in range(2)
            ]

            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(manuscript.consider_agent_task, tasks))

            self.assertEqual(sculptor.maximum_active, 1)

    def test_final_selection_refocuses_the_existing_manuscript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template_dir = root / "elegantpaper"
            template_dir.mkdir()
            (template_dir / "elegantpaper.cls").write_text(
                "shared class", encoding="utf-8"
            )
            candidate_path = root / "launch" / "session_1" / "candidate-b"
            candidate_path.mkdir(parents=True)
            sculptor = RepairingSculptor()
            manuscript = LivingManuscript.initialize(
                launch_dir=root / "launch",
                template_dir=template_dir,
                sculptor=sculptor,
                validator=DraftValidator(),
            )
            selection: dict[str, object] = {
                "selected_candidate": {
                    "idea_name": "method_b",
                    "folder_name": "session_1/candidate-b",
                }
            }

            manuscript.finalize(
                selection=selection,
                selected_candidate_path=candidate_path,
            )

            self.assertIs(sculptor.terminal_selection, selection)
            self.assertEqual(
                sculptor.selected_candidate_path, candidate_path.resolve()
            )
            self.assertEqual(
                manuscript.tex_path.read_text(encoding="utf-8"), "valid draft"
            )

    def test_claude_task_forks_its_live_session_into_the_sculptor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template_dir = root / "elegantpaper"
            template_dir.mkdir()
            (template_dir / "elegantpaper.cls").write_text(
                "shared class", encoding="utf-8"
            )
            source_cwd = root / "candidate"
            source_cwd.mkdir()
            prompt_path = root / "sculptor.md"
            prompt_path.write_text("Sculpt the manuscript.", encoding="utf-8")
            commands = RecordingCommandRunner()
            sculptor = ClaudeCodeSculptor(
                model="claude-test",
                prompt_path=prompt_path,
                run_command=commands,
            )
            manuscript = LivingManuscript.initialize(
                launch_dir=root / "launch",
                template_dir=template_dir,
                sculptor=sculptor,
                validator=AlwaysValidValidator(),
            )

            manuscript.consider_claude_session(
                ClaudeSessionTaskContext(
                    agent_name="ClaudeCodeRunner",
                    source_session_id="source-session",
                    source_cwd=source_cwd,
                    output="implemented experiment",
                    error=None,
                )
            )

            self.assertEqual(len(commands.calls), 1)
            invocation = commands.calls[0]
            self.assertEqual(invocation.cwd, source_cwd.resolve())
            self.assertIn("--resume", invocation.command)
            self.assertEqual(
                invocation.command[invocation.command.index("--resume") + 1],
                "source-session",
            )
            self.assertIn("--fork-session", invocation.command)
            self.assertIn("--append-system-prompt-file", invocation.command)
            self.assertIn(str(prompt_path.resolve()), invocation.command)
            self.assertIn(str(manuscript.launch_dir), invocation.command)
            self.assertIn(str(manuscript.tex_path), invocation.command[-1])

    def test_mas_context_transfer_keeps_raw_provider_response_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template_dir = root / "elegantpaper"
            template_dir.mkdir()
            (template_dir / "elegantpaper.cls").write_text("class", encoding="utf-8")
            prompt_path = root / "sculptor.md"
            prompt_path.write_text("Sculpt.", encoding="utf-8")
            commands = RecordingCommandRunner()
            sculptor = ClaudeCodeSculptor(
                model="claude-test",
                prompt_path=prompt_path,
                run_command=commands,
            )
            manuscript = LivingManuscript.initialize(
                launch_dir=root / "launch",
                template_dir=template_dir,
            )
            request = ModelRunRequest(
                input=(), instructions="retain this exact instruction"
            )
            result = ModelRunResult(
                response_id="response-raw",
                status="completed",
                model="test-model",
                raw_response={"provider_event": "exact-provider-payload"},
            )

            sculptor.start_from_agent_task(
                manuscript=manuscript,
                task=AgentTaskContext(
                    agent_name="ResearchAgent",
                    input={"source": "exact-input"},
                    output={"finding": "exact-output"},
                    error=None,
                    model_interactions=(
                        {"request": request, "result": result, "error": None},
                    ),
                ),
            )

            transferred_prompt = commands.calls[0].command[-1]
            self.assertIn("retain this exact instruction", transferred_prompt)
            self.assertIn("exact-provider-payload", transferred_prompt)
            self.assertIn("exact-input", transferred_prompt)
            self.assertIn("exact-output", transferred_prompt)


class AgentTaskHookTest(unittest.IsolatedAsyncioTestCase):
    async def test_agent_completion_transfers_raw_input_and_output(self) -> None:
        class EchoAgent:
            async def execute(
                self,
                context: dict[str, object],
                params: dict[str, object],
            ) -> dict[str, object]:
                return {"context": context, "params": params}

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template_dir = root / "elegantpaper"
            template_dir.mkdir()
            (template_dir / "elegantpaper.cls").write_text(
                "shared class", encoding="utf-8"
            )
            sculptor = RepairingSculptor()
            manuscript = LivingManuscript.initialize(
                launch_dir=root / "launch",
                template_dir=template_dir,
                sculptor=sculptor,
                validator=DraftValidator(),
            )
            agent_type = "living_manuscript_test_echo"
            set_active_living_manuscript(manuscript)
            try:
                agent = attach_living_manuscript_hook(
                    EchoAgent(), agent_name=agent_type
                )
                context = {"question": "What changed?"}
                params = {"depth": 2}

                output = await agent.execute(context, params)
            finally:
                clear_active_living_manuscript(manuscript)

            self.assertIsNotNone(sculptor.started_with)
            task = sculptor.started_with
            self.assertEqual(task.agent_name, agent_type)
            self.assertIs(task.input["args"][0], context)
            self.assertIs(task.input["args"][1], params)
            self.assertIs(task.output, output)
            self.assertIsNone(task.error)

    async def test_agent_task_retains_each_observable_model_request_and_result(
        self,
    ) -> None:
        result = ModelRunResult(
            response_id="response-7",
            status="completed",
            model="test-model",
        )

        class RecordingModel(BaseModel):
            async def _run(self, request: ModelRunRequest) -> ModelRunResult:
                return result

            @classmethod
            def from_config(cls, config: dict[str, object]) -> "RecordingModel":
                return cls()

        request = ModelRunRequest(input=(), instructions="Analyze exact evidence")
        model = RecordingModel()

        class ModelAgent:
            async def execute(self) -> str:
                completed = await model.run(request)
                return completed.response_id

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template_dir = root / "elegantpaper"
            template_dir.mkdir()
            (template_dir / "elegantpaper.cls").write_text("class", encoding="utf-8")
            sculptor = RepairingSculptor()
            manuscript = LivingManuscript.initialize(
                launch_dir=root / "launch",
                template_dir=template_dir,
                sculptor=sculptor,
                validator=DraftValidator(),
            )
            set_active_living_manuscript(manuscript)
            try:
                agent = attach_living_manuscript_hook(
                    ModelAgent(), agent_name="model-agent"
                )
                await agent.execute()
            finally:
                clear_active_living_manuscript(manuscript)

        task = sculptor.started_with
        self.assertIsNotNone(task)
        self.assertEqual(len(task.model_interactions), 1)
        self.assertIs(task.model_interactions[0]["request"], request)
        self.assertIs(task.model_interactions[0]["result"], result)
        self.assertIsNone(task.model_interactions[0]["error"])

    async def test_terminal_agent_failure_triggers_once_then_propagates(self) -> None:
        class FailingAgent:
            async def execute(self, context: dict[str, object]) -> None:
                raise ValueError("exhausted after retries")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template_dir = root / "elegantpaper"
            template_dir.mkdir()
            (template_dir / "elegantpaper.cls").write_text("class", encoding="utf-8")
            sculptor = RepairingSculptor()
            manuscript = LivingManuscript.initialize(
                launch_dir=root / "launch",
                template_dir=template_dir,
                sculptor=sculptor,
                validator=DraftValidator(),
            )
            context = {"attempts": 3}
            set_active_living_manuscript(manuscript)
            try:
                agent = attach_living_manuscript_hook(
                    FailingAgent(), agent_name="failing-agent"
                )
                with self.assertRaisesRegex(ValueError, "exhausted after retries"):
                    await agent.execute(context)
            finally:
                clear_active_living_manuscript(manuscript)

        task = sculptor.started_with
        self.assertIsNotNone(task)
        self.assertIs(task.input["args"][0], context)
        self.assertIsNone(task.output)
        self.assertEqual(task.error, "ValueError: exhausted after retries")


class ClaudeCodeRunnerHookTest(unittest.TestCase):
    def test_runner_forks_structured_terminal_session_before_returning_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_cwd = root / "candidate"
            source_cwd.mkdir()
            template_dir = root / "elegantpaper"
            template_dir.mkdir()
            (template_dir / "elegantpaper.cls").write_text("class", encoding="utf-8")
            sculptor = ClaudeTaskRecordingSculptor()
            manuscript = LivingManuscript.initialize(
                launch_dir=root / "launch",
                template_dir=template_dir,
                sculptor=sculptor,
                validator=DraftValidator(),
            )
            completed = CompletedProcess(
                ["claude"],
                0,
                stdout=json.dumps(
                    {
                        "session_id": "research-session-9",
                        "result": "implemented experiment",
                    }
                ),
                stderr="",
            )
            set_active_living_manuscript(manuscript)
            try:
                with patch(
                    "internagent.experiments_utils_claude.subprocess.run",
                    return_value=completed,
                ) as run_command:
                    output = ClaudeCodeRunner(model="claude-test").run(
                        "perform the experiment", cwd=source_cwd
                    )
            finally:
                clear_active_living_manuscript(manuscript)

            self.assertEqual(output, "implemented experiment")
            command = run_command.call_args.args[0]
            self.assertIn("-p", command)
            self.assertIn("--output-format", command)
            self.assertEqual(
                command[command.index("--output-format") + 1], "json"
            )
            task = sculptor.claude_task
            self.assertIsNotNone(task)
            self.assertEqual(task.source_session_id, "research-session-9")
            self.assertEqual(task.source_cwd, source_cwd.resolve())
            self.assertEqual(task.output, "implemented experiment")
            self.assertIsNone(task.error)


class DiscoveryLaunchWiringTest(unittest.TestCase):
    def test_launch_activates_manuscript_before_agents_and_never_runs_dossier(self) -> None:
        launch_source = (
            Path(__file__).parents[1] / "launch_discovery.py"
        ).read_text(encoding="utf-8")

        activation = launch_source.index("set_active_living_manuscript(")
        first_agent = launch_source.index("IdeaGenerator(")

        self.assertLess(activation, first_agent)
        self.assertIn("living_manuscript.finalize(", launch_source)
        self.assertNotIn("run_dossier(", launch_source)


if __name__ == "__main__":
    unittest.main()
