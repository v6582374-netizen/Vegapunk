"""Continuous, launch-local manuscript authoring."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import traceback
from contextvars import ContextVar
from dataclasses import dataclass, field, fields, is_dataclass
from functools import wraps
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Protocol

from internagent.paper_orchestra.utils.pdf_utils import is_openable_pdf


MINIMAL_ELEGANTPAPER_DOCUMENT = (
    "\\documentclass[lang=cn]{elegantpaper}\n\n"
    "\\begin{document}\n"
    "\\null\n"
    "\\end{document}\n"
)


class ManuscriptValidationError(RuntimeError):
    """A deterministic manuscript validator rejected the current files."""


@dataclass(frozen=True)
class AgentTaskContext:
    """The complete observable context of one terminal Agent task."""

    agent_name: str
    input: Any
    output: Any
    error: str | None
    model_interactions: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ClaudeSessionTaskContext:
    """A terminal Claude Code task whose live session can be forked natively."""

    agent_name: str
    source_session_id: str
    source_cwd: Path
    output: str
    error: str | None


class ManuscriptSculptor(Protocol):
    def start_from_agent_task(
        self,
        *,
        manuscript: "LivingManuscript",
        task: AgentTaskContext,
    ) -> str: ...

    def resume(
        self,
        *,
        manuscript: "LivingManuscript",
        session_id: str,
        diagnostics: str,
    ) -> None: ...

    def start_from_terminal_selection(
        self,
        *,
        manuscript: "LivingManuscript",
        selection: dict[str, Any],
        selected_candidate_path: Path,
    ) -> str: ...

    def start_from_claude_session(
        self,
        *,
        manuscript: "LivingManuscript",
        task: ClaudeSessionTaskContext,
    ) -> str: ...


class ManuscriptValidator(Protocol):
    def validate(self, manuscript: "LivingManuscript") -> None: ...


@dataclass
class LivingManuscript:
    """The single canonical manuscript owned by one Discovery Launch."""

    launch_dir: Path
    manuscript_dir: Path
    template_dir: Path
    tex_path: Path
    bibliography_path: Path
    _sculptor: ManuscriptSculptor | None = field(default=None, repr=False)
    _validator: ManuscriptValidator | None = field(default=None, repr=False)
    _write_lock: Lock = field(default_factory=Lock, repr=False)

    @classmethod
    def initialize(
        cls,
        *,
        launch_dir: Path,
        template_dir: Path,
        sculptor: ManuscriptSculptor | None = None,
        validator: ManuscriptValidator | None = None,
    ) -> "LivingManuscript":
        launch_root = launch_dir.resolve()
        template_root = template_dir.resolve()
        if not (template_root / "elegantpaper.cls").is_file():
            raise FileNotFoundError(
                f"ElegantPaper class not found: {template_root / 'elegantpaper.cls'}"
            )

        manuscript_dir = launch_root / "manuscript"
        manuscript_dir.mkdir(parents=True, exist_ok=True)
        tex_path = manuscript_dir / "main.tex"
        bibliography_path = manuscript_dir / "references.bib"
        if not tex_path.exists():
            tex_path.write_text(MINIMAL_ELEGANTPAPER_DOCUMENT, encoding="utf-8")
        if not bibliography_path.exists():
            bibliography_path.write_text("", encoding="utf-8")

        return cls(
            launch_dir=launch_root,
            manuscript_dir=manuscript_dir,
            template_dir=template_root,
            tex_path=tex_path,
            bibliography_path=bibliography_path,
            _sculptor=sculptor,
            _validator=validator,
        )

    def consider_agent_task(self, task: AgentTaskContext) -> None:
        """Synchronously sculpt and validate one completed Agent task."""

        sculptor = self._require_sculptor()
        validator = self._require_validator()
        with self._write_lock:
            session_id = sculptor.start_from_agent_task(
                manuscript=self,
                task=task,
            )
            self._validate_and_repair(sculptor, validator, session_id)

    def consider_claude_session(self, task: ClaudeSessionTaskContext) -> None:
        """Fork one completed Claude Code task into a Sculptor Invocation."""

        sculptor = self._require_sculptor()
        validator = self._require_validator()
        with self._write_lock:
            session_id = sculptor.start_from_claude_session(
                manuscript=self,
                task=task,
            )
            self._validate_and_repair(sculptor, validator, session_id)

    def finalize(
        self,
        *,
        selection: dict[str, Any],
        selected_candidate_path: Path,
    ) -> None:
        """Refocus the manuscript after Terminal Candidate Selection."""

        sculptor = self._require_sculptor()
        validator = self._require_validator()
        with self._write_lock:
            session_id = sculptor.start_from_terminal_selection(
                manuscript=self,
                selection=selection,
                selected_candidate_path=selected_candidate_path.resolve(),
            )
            self._validate_and_repair(sculptor, validator, session_id)

    def _validate_and_repair(
        self,
        sculptor: ManuscriptSculptor,
        validator: ManuscriptValidator,
        session_id: str,
    ) -> None:
        while True:
            try:
                validator.validate(self)
                return
            except ManuscriptValidationError as error:
                sculptor.resume(
                    manuscript=self,
                    session_id=session_id,
                    diagnostics=str(error),
                )

    def _require_sculptor(self) -> ManuscriptSculptor:
        if self._sculptor is None:
            raise RuntimeError("Living Manuscript has no Sculptor configured")
        return self._sculptor

    def _require_validator(self) -> ManuscriptValidator:
        if self._validator is None:
            raise RuntimeError("Living Manuscript has no validator configured")
        return self._validator


_active_manuscript: LivingManuscript | None = None
_active_manuscript_lock = Lock()
_task_model_interactions: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "living_manuscript_task_model_interactions",
    default=None,
)


def set_active_living_manuscript(manuscript: LivingManuscript) -> None:
    """Make one launch-local manuscript visible to Agent task exit hooks."""

    global _active_manuscript
    with _active_manuscript_lock:
        if _active_manuscript is not None and _active_manuscript is not manuscript:
            raise RuntimeError("A different Living Manuscript is already active")
        _active_manuscript = manuscript


def get_active_living_manuscript() -> LivingManuscript | None:
    with _active_manuscript_lock:
        return _active_manuscript


def clear_active_living_manuscript(
    manuscript: LivingManuscript | None = None,
) -> None:
    """Clear the active manuscript without disturbing a newer launch."""

    global _active_manuscript
    with _active_manuscript_lock:
        if manuscript is None or _active_manuscript is manuscript:
            _active_manuscript = None


def record_task_model_interaction(
    *,
    request: Any,
    result: Any,
    error: Exception | None,
) -> None:
    """Retain exact observable model traffic inside the current Agent task."""

    interactions = _task_model_interactions.get()
    if interactions is not None:
        interactions.append(
            {
                "request": request,
                "result": result,
                "error": error,
            }
        )


def attach_living_manuscript_hook(agent: Any, *, agent_name: str) -> Any:
    """Wrap one Agent task exit with the synchronous Sculptor barrier."""

    if getattr(agent, "_living_manuscript_hook_attached", False):
        return agent

    execute = agent.execute

    @wraps(execute)
    async def execute_with_sculptor(*args: Any, **kwargs: Any) -> Any:
        manuscript = get_active_living_manuscript()
        if manuscript is None:
            return await execute(*args, **kwargs)

        interactions: list[dict[str, Any]] = []
        token = _task_model_interactions.set(interactions)
        try:
            try:
                output = await execute(*args, **kwargs)
            except Exception as error:
                task = AgentTaskContext(
                    agent_name=agent_name,
                    input={"args": args, "kwargs": kwargs},
                    output=None,
                    error=traceback.format_exc(),
                    model_interactions=tuple(interactions),
                )
                await asyncio.to_thread(manuscript.consider_agent_task, task)
                raise

            task = AgentTaskContext(
                agent_name=agent_name,
                input={"args": args, "kwargs": kwargs},
                output=output,
                error=_structured_terminal_error(output),
                model_interactions=tuple(interactions),
            )
            await asyncio.to_thread(manuscript.consider_agent_task, task)
            return output
        finally:
            _task_model_interactions.reset(token)

    agent.execute = execute_with_sculptor
    agent._living_manuscript_hook_attached = True
    return agent


def attach_sync_living_manuscript_hook(agent: Any, *, agent_name: str) -> Any:
    """Wrap a synchronous Agent task exit with the same Sculptor barrier."""

    if getattr(agent, "_living_manuscript_hook_attached", False):
        return agent

    execute = agent.execute

    @wraps(execute)
    def execute_with_sculptor(*args: Any, **kwargs: Any) -> Any:
        manuscript = get_active_living_manuscript()
        if manuscript is None:
            return execute(*args, **kwargs)

        interactions: list[dict[str, Any]] = []
        token = _task_model_interactions.set(interactions)
        try:
            try:
                output = execute(*args, **kwargs)
            except Exception:
                manuscript.consider_agent_task(
                    AgentTaskContext(
                        agent_name=agent_name,
                        input={"args": args, "kwargs": kwargs},
                        output=None,
                        error=traceback.format_exc(),
                        model_interactions=tuple(interactions),
                    )
                )
                raise

            manuscript.consider_agent_task(
                AgentTaskContext(
                    agent_name=agent_name,
                    input={"args": args, "kwargs": kwargs},
                    output=output,
                    error=_structured_terminal_error(output),
                    model_interactions=tuple(interactions),
                )
            )
            return output
        finally:
            _task_model_interactions.reset(token)

    agent.execute = execute_with_sculptor
    agent._living_manuscript_hook_attached = True
    return agent


def _structured_terminal_error(output: Any) -> str | None:
    if not isinstance(output, dict):
        return None
    if output.get("success") is not False and output.get("completed") is not False:
        return None
    return (
        "Agent returned a structured terminal failure:\n"
        + json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
            default=_observable_json_default,
        )
    )


def preflight_living_manuscript_runtime(
    *,
    experiment_backend: str | None,
    find_executable: Callable[[str], str | None] = shutil.which,
    run_command: CommandRunner | None = None,
) -> None:
    """Fail before research when the configured runtime cannot fork and validate."""

    if experiment_backend not in (None, "claudecode"):
        raise RuntimeError(
            "Living Manuscript experiment launches currently require the "
            "claudecode backend for native context forks"
        )

    required = ("claude", "latexmk", "xelatex", "biber")
    missing = [name for name in required if find_executable(name) is None]
    if missing:
        raise RuntimeError(
            "Living Manuscript runtime is missing executable(s): "
            + ", ".join(missing)
        )

    command_runner = run_command or subprocess.run
    completed = command_runner(
        ["claude", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Claude Code capability preflight failed: " + completed.stderr.strip()
        )
    help_text = completed.stdout + "\n" + completed.stderr
    required_flags = (
        ("--resume",),
        ("--fork-session",),
        ("--append-system-prompt-file", "--append-system-prompt[-file]"),
        ("--output-format",),
    )
    for alternatives in required_flags:
        if not any(flag in help_text for flag in alternatives):
            raise RuntimeError(
                "Claude Code does not support required Sculptor flag: "
                + alternatives[0]
            )


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class LatexManuscriptValidator:
    """Compile the canonical TeX against the shared ElegantPaper resources."""

    def __init__(
        self,
        *,
        timeout: int = 180,
        run_command: CommandRunner = subprocess.run,
    ) -> None:
        self.timeout = timeout
        self._run_command = run_command

    def validate(self, manuscript: LivingManuscript) -> None:
        command = [
            "latexmk",
            "-pdfxe",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            manuscript.tex_path.name,
        ]
        env = os.environ.copy()
        env["TEXINPUTS"] = (
            str(manuscript.template_dir)
            + os.pathsep
            + env.get("TEXINPUTS", "")
        )
        log_path = manuscript.manuscript_dir / "validation.log"
        try:
            completed = self._run_command(
                command,
                cwd=manuscript.manuscript_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            diagnostics = (
                "$ "
                + " ".join(command)
                + "\n\nSTDOUT\n"
                + completed.stdout
                + "\n\nSTDERR\n"
                + completed.stderr
            )
        except subprocess.TimeoutExpired as error:
            diagnostics = (
                f"$ {' '.join(command)}\n\nTIMEOUT after {self.timeout}s\n{error}"
            )
            log_path.write_text(diagnostics, encoding="utf-8")
            raise ManuscriptValidationError(diagnostics) from error

        tex_log_path = manuscript.manuscript_dir / f"{manuscript.tex_path.stem}.log"
        try:
            tex_log = tex_log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            tex_log = ""
        if tex_log:
            diagnostics += "\n\nFINAL TEX LOG\n" + tex_log

        unresolved_pattern = re.compile(
            r"(?:citation|reference)[^\n]*undefined|"
            r"undefined (?:citations|references)",
            re.IGNORECASE,
        )
        if unresolved_pattern.search(tex_log):
            diagnostics += "\n\nUNRESOLVED CITATIONS OR REFERENCES"
            log_path.write_text(diagnostics, encoding="utf-8")
            raise ManuscriptValidationError(diagnostics)

        log_path.write_text(diagnostics, encoding="utf-8")
        pdf_path = manuscript.manuscript_dir / f"{manuscript.tex_path.stem}.pdf"
        if completed.returncode != 0 or not is_openable_pdf(pdf_path):
            raise ManuscriptValidationError(diagnostics)


class ClaudeCodeSculptor:
    """Claude Code adapter for direct, file-editing Sculptor Invocations."""

    def __init__(
        self,
        *,
        model: str,
        prompt_path: Path,
        env_overrides: dict[str, str] | None = None,
        run_command: CommandRunner = subprocess.run,
    ) -> None:
        self.model = model
        self.prompt_path = prompt_path.resolve()
        self.env_overrides = dict(env_overrides or {})
        self._run_command = run_command
        if not self.prompt_path.is_file():
            raise FileNotFoundError(f"Sculptor prompt not found: {self.prompt_path}")

    def start_from_claude_session(
        self,
        *,
        manuscript: LivingManuscript,
        task: ClaudeSessionTaskContext,
    ) -> str:
        prompt = self._task_prompt(
            manuscript,
            agent_name=task.agent_name,
            outcome=task.output,
            error=task.error,
        )
        return self._invoke(
            manuscript=manuscript,
            cwd=task.source_cwd.resolve(),
            prompt=prompt,
            resume_session_id=task.source_session_id,
            fork_session=True,
        )

    def start_from_agent_task(
        self,
        *,
        manuscript: LivingManuscript,
        task: AgentTaskContext,
    ) -> str:
        raw_context = json.dumps(
            {
                "agent_name": task.agent_name,
                "input": task.input,
                "output": task.output,
                "error": task.error,
                "model_interactions": task.model_interactions,
            },
            ensure_ascii=False,
            indent=2,
            default=_observable_json_default,
        )
        prompt = self._task_prompt(
            manuscript,
            agent_name=task.agent_name,
            outcome=raw_context,
            error=task.error,
        )
        return self._invoke(
            manuscript=manuscript,
            cwd=manuscript.manuscript_dir,
            prompt=prompt,
        )

    def start_from_terminal_selection(
        self,
        *,
        manuscript: LivingManuscript,
        selection: dict[str, Any],
        selected_candidate_path: Path,
    ) -> str:
        prompt = (
            self._manuscript_paths(manuscript)
            + "\nTerminal Candidate Selection is now authoritative. Refocus the entire "
            "manuscript around the selected candidate.\n"
            f"Selected candidate artifacts: {selected_candidate_path}\n"
            "Exact selection result:\n"
            + json.dumps(selection, ensure_ascii=False, indent=2, default=str)
        )
        return self._invoke(
            manuscript=manuscript,
            cwd=manuscript.manuscript_dir,
            prompt=prompt,
        )

    def resume(
        self,
        *,
        manuscript: LivingManuscript,
        session_id: str,
        diagnostics: str,
    ) -> None:
        prompt = (
            self._manuscript_paths(manuscript)
            + "\nThe current files failed deterministic validation. Repair the files "
            "forward without rolling back correct editorial work.\n"
            f"Validation diagnostics:\n{diagnostics}"
        )
        self._invoke(
            manuscript=manuscript,
            cwd=manuscript.manuscript_dir,
            prompt=prompt,
            resume_session_id=session_id,
        )

    def _invoke(
        self,
        *,
        manuscript: LivingManuscript,
        cwd: Path,
        prompt: str,
        resume_session_id: str | None = None,
        fork_session: bool = False,
    ) -> str:
        command = [
            "claude",
            "-p",
            "--permission-mode",
            "acceptEdits",
            "--model",
            self.model,
            "--output-format",
            "json",
            "--append-system-prompt-file",
            str(self.prompt_path),
            "--add-dir",
            str(manuscript.manuscript_dir),
            "--add-dir",
            str(manuscript.launch_dir),
            "--add-dir",
            str(manuscript.template_dir),
        ]
        if resume_session_id is not None:
            command.extend(["--resume", resume_session_id])
        if fork_session:
            command.append("--fork-session")
        env = os.environ.copy()
        env.update(self.env_overrides)
        completed = self._run_command(
            command,
            cwd=cwd,
            env=env,
            input=prompt,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Claude Code Sculptor failed with exit code "
                f"{completed.returncode}: {completed.stderr.strip()}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("Claude Code Sculptor returned invalid JSON") from error
        session_id = payload.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise RuntimeError("Claude Code Sculptor returned no session_id")
        return session_id

    @classmethod
    def _task_prompt(
        cls,
        manuscript: LivingManuscript,
        *,
        agent_name: str,
        outcome: str,
        error: str | None,
    ) -> str:
        status = "final failure" if error else "success"
        return (
            cls._manuscript_paths(manuscript)
            + f"\nThe {agent_name} task reached terminal {status}. Decide whether "
            "the Living Manuscript should change, then edit the canonical files directly.\n"
            f"Terminal outcome:\n{outcome}"
        )

    @staticmethod
    def _manuscript_paths(manuscript: LivingManuscript) -> str:
        return (
            f"Canonical TeX source: {manuscript.tex_path}\n"
            f"Canonical bibliography: {manuscript.bibliography_path}\n"
            f"Shared ElegantPaper resources: {manuscript.template_dir}\n"
        )


def _observable_json_default(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: getattr(value, item.name) for item in fields(value)}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Exception):
        return {"type": type(value).__name__, "message": str(value)}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    attributes = getattr(value, "__dict__", None)
    if isinstance(attributes, dict):
        return attributes
    return repr(value)
