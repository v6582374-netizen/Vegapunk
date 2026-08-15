"""Process entry for one BabelDOC translation run.

The worker is deliberately thin: it reads the run request the sidecar already
validated, drives one translation engine, projects the engine's own event stream into
the run's durable ``events.jsonl`` / ``state.json`` / ``runner.log``, and performs the
bundling move that makes a finished run a single folder.

``run_translation`` takes the engine as an argument.  Production passes the BabelDOC
engine; tests pass an engine that emits the same event shapes without a model call.
The bundling, cancellation, and state-projection logic is therefore identical in both
cases — there is no test-only branch inside it.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import AsyncIterator, Callable, Mapping
from pathlib import Path
from typing import Any

from .translation import (
    RunEventLog,
    TRANSLATE_STAGE_TABLE,
    _atomic_write_json,
    _read_json,
    bundle_dir_for,
    stage_index,
    unique_path,
)

# Closing an engine generator is best-effort: a third-party teardown that blocks must not be
# able to hold a finished run open.
ENGINE_CLOSE_TIMEOUT = 10.0
# How long a progress wait blocks before re-checking whether the pipeline returned.
PROGRESS_POLL_SECONDS = 0.1

# One engine call: given the run's values, source document, and bundle directory, yield
# BabelDOC's own progress events (``progress_start`` / ``progress_update`` /
# ``progress_end`` / ``finish`` / ``error``).
TranslationEngine = Callable[
    [Mapping[str, Any], Path, Path, Callable[[str], None]], AsyncIterator[dict[str, Any]]
]

_RESULT_PATH_FIELDS = (
    "original_pdf_path",
    "mono_pdf_path",
    "dual_pdf_path",
    "no_watermark_mono_pdf_path",
    "no_watermark_dual_pdf_path",
    "auto_extracted_glossary_path",
)
_RESULT_SCALAR_FIELDS = (
    "total_seconds",
    "peak_memory_usage",
    "total_valid_character_count",
    "total_valid_text_token_count",
)


def _serialize_result(result: Any) -> dict[str, Any]:
    """JSON-ready view of a ``TranslateResult``: paths become strings."""
    payload: dict[str, Any] = {}
    for field in _RESULT_PATH_FIELDS:
        value = getattr(result, field, None)
        payload[field] = str(value) if value else None
    for field in _RESULT_SCALAR_FIELDS:
        value = getattr(result, field, None)
        payload[field] = value if isinstance(value, (int, float)) else None
    return payload


class RunJournal:
    """The run's durable projection: state document, event log, and raw console."""

    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.events = RunEventLog(self.run_dir / "events.jsonl")
        self._log_path = self.run_dir / "runner.log"
        self._state: dict[str, Any] = _read_json(self.run_dir / "state.json") or {}

    @property
    def state(self) -> dict[str, Any]:
        return dict(self._state)

    def log(self, message: str) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{message.rstrip()}\n")
            handle.flush()
            os.fsync(handle.fileno())

    def update_state(self, **changes: Any) -> dict[str, Any]:
        self._state.update(changes)
        _atomic_write_json(self.run_dir / "state.json", self._state)
        return dict(self._state)

    def cancelled(self) -> bool:
        return (self.run_dir / "cancel").exists()


def _stage_changes(event: Mapping[str, Any]) -> dict[str, Any]:
    stage = event.get("stage")
    changes: dict[str, Any] = {
        "stage": stage if isinstance(stage, str) else None,
        "stage_index": stage_index(stage),
        "stage_current": event.get("stage_current", 0),
        "stage_total": event.get("stage_total", 0),
        "stage_progress": event.get("stage_progress", 0.0),
    }
    if "overall_progress" in event:
        changes["overall_progress"] = event["overall_progress"]
    return changes


def _bundle(journal: RunJournal, source_path: Path, bundle_dir: Path) -> Path:
    """Move the original document into the bundle and return its new location.

    This is the run's closing invariant: after a successful translation the original and
    every artifact share one folder.  A name collision inside the bundle takes a
    numbered variant so existing user data is never overwritten.
    """
    bundle_dir.mkdir(parents=True, exist_ok=True)
    destination = bundle_dir / source_path.name
    if destination.exists() and destination.samefile(source_path):
        return destination
    destination = unique_path(destination)
    shutil.move(str(source_path), str(destination))
    journal.log(f"[bundle] original moved to {destination}")
    return destination


def _prepare_bundle_dir(request: Mapping[str, Any], source_path: Path) -> Path:
    """Resolve the writable bundle directory for one run.

    Reusing an existing directory is intended — a re-run adds to the same bundle.  A
    non-directory occupying the name takes a numbered variant instead of failing.
    """
    declared = request.get("bundle_dir")
    candidate = (
        Path(declared)
        if isinstance(declared, str) and declared
        else bundle_dir_for(source_path, source_path.name)
    )
    if candidate.exists() and not candidate.is_dir():
        candidate = unique_path(candidate)
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def run_translation(run_dir: str | Path, engine: TranslationEngine) -> dict[str, Any]:
    """Execute one prepared run to a terminal state and return its final state."""
    run_dir = Path(run_dir)
    request = _read_json(run_dir / "request.json")
    if not request:
        raise ValueError(f"translation run request is missing: {run_dir}")
    journal = RunJournal(run_dir)
    source_path = Path(request["source_path"])
    values = request.get("values") or {}

    if journal.cancelled():
        journal.events.append("run.cancelled", {"message": "cancelled before execution"})
        return journal.update_state(
            state="cancelled", finished_at=time.time(), stage=None
        )

    bundle_dir = _prepare_bundle_dir(request, source_path)
    started_at = time.time()
    journal.update_state(
        state="running",
        pid=os.getpid(),
        started_at=started_at,
        finished_at=None,
        error=None,
        stage=None,
        stage_index=-1,
        stage_current=0,
        stage_total=0,
        stage_progress=0.0,
        overall_progress=0.0,
        source_path=str(source_path),
        bundle_dir=str(bundle_dir),
        result=None,
    )
    journal.events.append("run.started", {"message": f"translating {source_path.name}"})
    journal.log(f"[run] {source_path} -> {bundle_dir}")

    async def consume() -> dict[str, Any]:
        result: Any = None
        failure: str | None = None
        stream = engine(values, source_path, bundle_dir, journal.log)
        try:
            async for event in stream:
                if journal.cancelled():
                    failure = "__cancelled__"
                    break
                kind = event.get("type")
                if kind in {"progress_start", "progress_update", "progress_end"}:
                    changes = _stage_changes(event)
                    journal.update_state(**changes)
                    journal.events.append(kind, {**changes, "stage": event.get("stage")})
                elif kind == "finish":
                    # A finish IS the terminal fact, so stop reading here rather than waiting
                    # for the engine's generator to end on its own. BabelDOC's async_translate
                    # keeps its own bookkeeping alive past the last event, and a run that has
                    # already produced its result must not be hostage to that teardown.
                    result = event.get("translate_result")
                    journal.log("[run] engine reported finish")
                    break
                elif kind == "error":
                    failure = str(event.get("error") or "translation failed")
                    break
        finally:
            # Closing the engine is best-effort and time-boxed. The result above is already
            # the terminal fact; a third-party generator whose teardown blocks (BabelDOC waits
            # on its own finish bookkeeping) must not be able to hold a finished run open.
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                with contextlib.suppress(Exception, asyncio.TimeoutError):
                    await asyncio.wait_for(aclose(), timeout=ENGINE_CLOSE_TIMEOUT)

        if failure == "__cancelled__" or journal.cancelled():
            journal.events.append("run.cancelled", {"message": "cancelled during execution"})
            journal.log("[run] cancelled")
            return journal.update_state(
                state="cancelled", finished_at=time.time(), stage=None
            )
        if failure is not None:
            journal.events.append("error", {"error": failure})
            journal.log(f"[error] {failure}")
            return journal.update_state(
                state="error", error=failure, finished_at=time.time()
            )
        if result is None:
            message = "translation finished without a result"
            journal.events.append("error", {"error": message})
            return journal.update_state(
                state="error", error=message, finished_at=time.time()
            )

        bundled_source = _bundle(journal, source_path, bundle_dir)
        payload = _serialize_result(result)
        payload["original_pdf_path"] = str(bundled_source)
        payload["bundle_dir"] = str(bundle_dir)
        finished_at = time.time()
        payload.setdefault("total_seconds", None)
        if payload.get("total_seconds") is None:
            payload["total_seconds"] = finished_at - started_at
        journal.events.append("finish", {"translate_result": payload})
        journal.log("[run] done")
        return journal.update_state(
            state="done",
            finished_at=finished_at,
            source_path=str(bundled_source),
            result=payload,
            stage=None,
            overall_progress=100.0,
        )

    try:
        return asyncio.run(consume())
    except BaseException as error:  # SIGTERM lands here as KeyboardInterrupt/SystemExit
        if journal.cancelled():
            journal.events.append("run.cancelled", {"message": "cancelled during execution"})
            return journal.update_state(
                state="cancelled", finished_at=time.time(), stage=None
            )
        message = f"{type(error).__name__}: {error}"
        journal.events.append("error", {"error": message})
        journal.log(f"[error] {message}")
        journal.update_state(state="error", error=message, finished_at=time.time())
        raise


async def babeldoc_engine(
    values: Mapping[str, Any],
    source_path: Path,
    bundle_dir: Path,
    log: Callable[[str], None],
) -> AsyncIterator[dict[str, Any]]:
    """Drive the real BabelDOC pipeline for one document.

    Every neutral sidecar spelling ("" / 0 / "auto") is translated back into BabelDOC's
    own "let me decide" value (``None``) here, so the settings surface never has to
    encode ``None`` in JSON.
    """
    import babeldoc.format.pdf.high_level as high_level
    from babeldoc.docvision.doclayout import DocLayoutModel
    from babeldoc.format.pdf.translation_config import (
        TranslationConfig,
        WatermarkOutputMode,
    )
    from babeldoc.progress_monitor import ProgressMonitor
    from babeldoc.translator.translator import OpenAITranslator, set_translate_rate_limiter

    from ..providers.openai_provider import resolve_api_key
    from ..providers.registry import ProviderNotUsable, resolve_openai_compatible
    from ..secrets import SecretStore

    high_level.init()
    log("[babeldoc] initialized")

    def optional(key: str) -> str | None:
        value = values.get(key)
        return value if isinstance(value, str) and value.strip() else None

    # Credentials come from the same place the chat router reads them, so a provider the
    # user already set up in Settings ▸ Models needs no second key. `provider` empty keeps
    # the original behavior (the OpenAI slot: env OPENAI_API_KEY, else its stored profile).
    provider = optional("provider")
    secrets = SecretStore()
    provider_base_url: str | None = None
    if provider:
        try:
            api_key, provider_base_url, descriptor = resolve_openai_compatible(
                provider, secrets
            )
        except ProviderNotUsable as exc:
            yield {"type": "error", "error": str(exc)}
            return
        log(f"[babeldoc] provider {descriptor.title}")
    else:
        api_key = resolve_api_key(secrets)
        if not api_key:
            yield {
                "type": "error",
                "error": (
                    "No model API key configured. Choose a provider in Document "
                    "Translation settings, set OPENAI_API_KEY in the environment, "
                    "or save an OpenAI key in Settings."
                ),
            }
            return

    # An explicit Base URL is an override the user typed for this module; otherwise the
    # provider's own endpoint (prefilled default, or Ollama's normalized /v1) applies.
    base_url = optional("openai_base_url") or provider_base_url

    qps = int(values.get("qps") or 1)
    set_translate_rate_limiter(qps)
    translator = OpenAITranslator(
        lang_in=values.get("lang_in") or "en",
        lang_out=values.get("lang_out") or "zh",
        model=values.get("openai_model") or "gpt-4o-mini",
        base_url=base_url,
        api_key=api_key,
        ignore_cache=bool(values.get("ignore_cache")),
    )

    # Preflight: one real round trip before the pipeline starts.
    #
    # BabelDOC treats a per-paragraph translation failure as non-fatal — it logs the error and
    # keeps the source text — so a bad key or a model the vendor does not serve produces a run
    # that reports 100% success and returns the untranslated original. That silent outcome is
    # worse than a hard failure, so we spend one request to turn it into one.
    try:
        # ignore_cache: a cached probe answer would defeat the point of asking.
        translator.translate("ok", ignore_cache=True)
    except Exception as exc:  # vendor errors are the whole point of asking
        yield {
            "type": "error",
            "error": f"{translator.model} rejected a test request: {exc}",
        }
        return

    table_model = None
    if values.get("translate_table_text"):
        from babeldoc.docvision.table_detection.rapidocr import RapidOCRModel

        table_model = RapidOCRModel()

    max_pages_per_part = int(values.get("max_pages_per_part") or 0)
    split_strategy = (
        TranslationConfig.create_max_pages_per_part_split_strategy(max_pages_per_part)
        if max_pages_per_part > 0
        else None
    )
    primary_font_family = values.get("primary_font_family")
    pool_max_workers = int(values.get("pool_max_workers") or 0)

    config = TranslationConfig(
        translator=translator,
        input_file=str(source_path),
        lang_in=values.get("lang_in") or "en",
        lang_out=values.get("lang_out") or "zh",
        doc_layout_model=DocLayoutModel.load_onnx(),
        output_dir=str(bundle_dir),
        pages=optional("pages"),
        no_dual=bool(values.get("no_dual")),
        no_mono=bool(values.get("no_mono")),
        watermark_output_mode=WatermarkOutputMode(
            values.get("watermark_output_mode") or "watermarked"
        ),
        split_short_lines=bool(values.get("split_short_lines")),
        short_line_split_factor=float(values.get("short_line_split_factor") or 0.8),
        enhance_compatibility=bool(values.get("enhance_compatibility")),
        skip_clean=bool(values.get("skip_clean")),
        disable_rich_text_translate=bool(values.get("disable_rich_text_translate")),
        dual_translate_first=bool(values.get("dual_translate_first")),
        use_alternating_pages_dual=bool(values.get("use_alternating_pages_dual")),
        min_text_length=int(values.get("min_text_length", 5)),
        skip_scanned_detection=bool(values.get("skip_scanned_detection")),
        ocr_workaround=bool(values.get("ocr_workaround")),
        auto_enable_ocr_workaround=bool(values.get("auto_enable_ocr_workaround")),
        auto_extract_glossary=bool(values.get("auto_extract_glossary")),
        save_auto_extracted_glossary=bool(values.get("save_auto_extracted_glossary")),
        primary_font_family=(
            primary_font_family
            if isinstance(primary_font_family, str) and primary_font_family != "auto"
            else None
        ),
        formular_font_pattern=optional("formular_font_pattern"),
        formular_char_pattern=optional("formular_char_pattern"),
        only_include_translated_page=bool(values.get("only_include_translated_page")),
        merge_alternating_line_numbers=bool(
            values.get("merge_alternating_line_numbers", True)
        ),
        remove_non_formula_lines=bool(values.get("remove_non_formula_lines")),
        skip_form_render=bool(values.get("skip_form_render")),
        skip_curve_render=bool(values.get("skip_curve_render")),
        table_model=table_model,
        split_strategy=split_strategy,
        qps=qps,
        pool_max_workers=pool_max_workers or None,
        custom_system_prompt=optional("custom_system_prompt"),
        use_rich_pbar=False,
    )

    # Drive BabelDOC's own pipeline function directly instead of its async_translate
    # wrapper.
    #
    # async_translate reports completion through a cross-thread handshake (an
    # AsyncCallback whose `finished` flag and an asyncio finish_event, both set from the
    # worker thread). When that handshake does not fire — observed on real runs that had
    # already written their output — the generator never ends and the run stays `running`
    # forever with a finished document on disk.
    #
    # A function call has no such failure mode: `do_translate` returning IS the result and
    # raising IS the error. Progress still comes from BabelDOC's own ProgressMonitor, so
    # the event stream we yield is unchanged; only the terminal fact changed hands.
    loop = asyncio.get_running_loop()
    events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def on_progress(**event: Any) -> None:
        loop.call_soon_threadsafe(events.put_nowait, event)

    monitor = ProgressMonitor(
        high_level.get_translation_stage(config),
        progress_change_callback=on_progress,
        # BabelDOC calls this on completion and again while tearing down; we take the
        # function's own outcome as authoritative, so these are deliberately dropped.
        finish_callback=lambda **_: None,
        report_interval=config.report_interval,
    )
    config.progress_monitor = monitor
    if monitor.cancel_event is None:
        monitor.cancel_event = threading.Event()

    pipeline = loop.run_in_executor(None, high_level.do_translate, monitor, config)
    try:
        while not pipeline.done():
            try:
                yield await asyncio.wait_for(events.get(), timeout=PROGRESS_POLL_SECONDS)
            except (TimeoutError, asyncio.TimeoutError):
                continue
        while not events.empty():
            yield events.get_nowait()
        try:
            result = pipeline.result()
        except Exception as exc:
            yield {"type": "error", "error": str(exc)}
            return
        yield {"type": "finish", "translate_result": result}
    finally:
        # A consumer that stops reading (a cancelled run) must not leave the pipeline
        # thread translating a document nobody will collect.
        if not pipeline.done():
            monitor.cancel()


def spawn_worker(run_dir: str | Path) -> subprocess.Popen:
    """Start the worker for one run in its own session, logging into the run folder."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    log_handle = (run_dir / "runner.log").open("a", encoding="utf-8")
    try:
        return subprocess.Popen(
            [sys.executable, "-m", __spec__.name, "--run-dir", str(run_dir)],
            cwd=str(Path(__file__).resolve().parents[2]),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_handle.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one BabelDOC translation.")
    parser.add_argument("--run-dir", required=True)
    arguments = parser.parse_args(argv)
    state = run_translation(Path(arguments.run_dir), babeldoc_engine)
    return 0 if state.get("state") == "done" else 1


if __name__ == "__main__":  # pragma: no cover - process entry
    raise SystemExit(main())


__all__ = [
    "RunJournal",
    "TRANSLATE_STAGE_TABLE",
    "TranslationEngine",
    "babeldoc_engine",
    "main",
    "run_translation",
    "spawn_worker",
]
