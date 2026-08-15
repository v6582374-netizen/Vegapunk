"""BabelDOC document translation: validated settings, documents, runs, and bundling.

The module owns one invariant that the rest of the surface depends on: when a
translation succeeds, the original document and every produced artifact live in the
same folder, created next to the original and named after it.  ``TranslationConfig``
writes its outputs into that folder and the original is moved in afterwards, so a
finished run is a single self-describing bundle a user can move or share as a unit.

Progress is dual-tracked exactly like Discovery Launch: an append-only
``events.jsonl`` with a monotonic per-run ``sequence`` for cursor polling, and a raw
``runner.log`` tailed over SSE.  The worker is a separate process; this module only
stores its PID and reads the state the worker atomically replaces, so a sidecar
restart never invents progress it did not observe.
"""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import math
import os
import re
import shutil
import signal
import tempfile
import threading
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

# BabelDOC's own stage table (babeldoc.format.pdf.high_level.TRANSLATE_STAGES, 0.6.4).
# Mirrored as a literal so the sidecar can describe a run without importing the
# translation engine; ``tests/test_translation.py`` pins it against the real table.
TRANSLATE_STAGE_TABLE: tuple[tuple[str, float], ...] = (
    ("Parse PDF and Create Intermediate Representation", 14.12),
    ("DetectScannedFile", 2.45),
    ("Parse Page Layout", 14.03),
    ("Parse Table", 1.0),
    ("Parse Paragraphs", 6.26),
    ("Parse Formulas and Styles", 1.66),
    ("Automatic Term Extraction", 30.0),
    ("Translate Paragraphs", 46.96),
    ("Typesetting", 4.71),
    ("Add Fonts", 0.61),
    ("Generate drawing instructions", 1.96),
    ("Subset font", 0.92),
    ("Save PDF", 6.34),
)
STAGE_NAMES: tuple[str, ...] = tuple(name for name, _ in TRANSLATE_STAGE_TABLE)

SUPPORTED_DOCUMENT_EXTENSIONS = frozenset({".pdf"})
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
RUN_LIST_LIMIT = 50
EVENT_PAGE_LIMIT = 512
EVENT_LOG_TAIL_BYTES = 2 * 1024 * 1024
EVENT_LINE_MAX_BYTES = 256 * 1024
RAW_LOG_MAX_BYTES = 512 * 1024
ACTIVE_RUN_STATES = frozenset({"queued", "running"})
TERMINAL_RUN_STATES = frozenset({"done", "error", "cancelled"})

_PAGES_PATTERN = re.compile(r"^(?:\d+|\d+-\d*|-\d+)(?:,(?:\d+|\d+-\d*|-\d+))*$")


class TranslationValidationError(ValueError):
    """Raised when a settings, document, or run request is not usable."""

    def __init__(self, message: str, violations: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.violations = violations or []

    def to_dict(self) -> dict[str, Any]:
        return {"message": str(self), "violations": copy.deepcopy(self.violations)}


class TranslationArtifactError(LookupError):
    """Raised when a requested artifact name is not part of a run's bundle."""


def _violation(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}


# The complete user-editable parameter set for document translation.  Values map onto
# babeldoc's TranslationConfig/OpenAITranslator arguments; the neutral spellings
# ("" / 0 / "auto") are the sidecar's way of saying "let BabelDOC decide".
DEFAULT_TRANSLATION_SETTINGS: dict[str, Any] = {
    "lang_in": "en",
    "lang_out": "zh",
    # Which configured model provider translates. Empty = the legacy path: whatever
    # `resolve_api_key` finds for OpenAI (env var, then the stored openai profile). A
    # provider name here makes the choice explicit and carries its endpoint with it.
    "provider": "",
    "openai_model": "gpt-4o-mini",
    "openai_base_url": "",
    "qps": 4,
    "pool_max_workers": 0,
    "ignore_cache": False,
    "pages": "",
    "only_include_translated_page": False,
    "max_pages_per_part": 0,
    "watermark_output_mode": "watermarked",
    "no_dual": False,
    "no_mono": False,
    "use_alternating_pages_dual": False,
    "dual_translate_first": False,
    "split_short_lines": False,
    "short_line_split_factor": 0.8,
    "translate_table_text": False,
    "merge_alternating_line_numbers": True,
    "remove_non_formula_lines": False,
    "skip_form_render": False,
    "skip_curve_render": False,
    "enhance_compatibility": False,
    "skip_clean": False,
    "disable_rich_text_translate": False,
    "skip_scanned_detection": False,
    "auto_enable_ocr_workaround": False,
    "ocr_workaround": False,
    "primary_font_family": "auto",
    "formular_font_pattern": "",
    "formular_char_pattern": "",
    "auto_extract_glossary": True,
    "save_auto_extracted_glossary": True,
    "min_text_length": 5,
    "custom_system_prompt": "",
}

_PARAMETER_DEFINITIONS: dict[str, dict[str, Any]] = {
    "lang_in": {
        "type": "string",
        "description": "Source language code passed to BabelDOC.",
    },
    "lang_out": {
        "type": "string",
        "description": "Target language code passed to BabelDOC.",
    },
    "provider": {
        "type": "string",
        "description": (
            "Configured model provider that performs the translation; empty uses the "
            "OpenAI key from the environment or Settings."
        ),
    },
    "openai_model": {
        "type": "string",
        "description": "OpenAI-compatible model used to translate paragraphs.",
    },
    "openai_base_url": {
        "type": "string",
        "description": "OpenAI-compatible endpoint; empty uses the official API.",
    },
    "qps": {
        "type": "integer",
        "minimum": 1,
        "maximum": 100,
        "description": "Translation requests per second allowed against the model.",
    },
    "pool_max_workers": {
        "type": "integer",
        "minimum": 0,
        "maximum": 256,
        "description": "Worker pool size for translation; 0 lets BabelDOC choose.",
    },
    "ignore_cache": {
        "type": "boolean",
        "description": "Bypass the translation cache and retranslate every paragraph.",
    },
    "pages": {
        "type": "string",
        "description": "Page selection such as 1-5,8; empty translates every page.",
    },
    "only_include_translated_page": {
        "type": "boolean",
        "description": "Keep only the selected pages in the output documents.",
    },
    "max_pages_per_part": {
        "type": "integer",
        "minimum": 0,
        "maximum": 10000,
        "description": "Split the document into parts of at most this many pages; 0 disables splitting.",
    },
    "watermark_output_mode": {
        "type": "enum",
        "values": ["watermarked", "no_watermark", "both"],
        "description": "Whether BabelDOC writes watermarked outputs, clean outputs, or both.",
    },
    "no_dual": {
        "type": "boolean",
        "description": "Skip the bilingual (dual) PDF output.",
    },
    "no_mono": {
        "type": "boolean",
        "description": "Skip the translated-only (mono) PDF output.",
    },
    "use_alternating_pages_dual": {
        "type": "boolean",
        "description": "Interleave original and translated pages instead of side-by-side.",
    },
    "dual_translate_first": {
        "type": "boolean",
        "description": "Place the translated page before the original in the dual PDF.",
    },
    "split_short_lines": {
        "type": "boolean",
        "description": "Force short lines to be split into separate paragraphs.",
    },
    "short_line_split_factor": {
        "type": "number",
        "minimum": 0.1,
        "maximum": 1.0,
        "description": "Threshold factor used when splitting short lines.",
    },
    "translate_table_text": {
        "type": "boolean",
        "description": "Detect and translate text inside tables (loads the OCR table model).",
    },
    "merge_alternating_line_numbers": {
        "type": "boolean",
        "description": "Merge alternating line-number columns back into the paragraph flow.",
    },
    "remove_non_formula_lines": {
        "type": "boolean",
        "description": "Remove decorative lines that are not part of a formula.",
    },
    "skip_form_render": {
        "type": "boolean",
        "description": "Do not render interactive form fields into the output.",
    },
    "skip_curve_render": {
        "type": "boolean",
        "description": "Do not render vector curves into the output.",
    },
    "enhance_compatibility": {
        "type": "boolean",
        "description": "Enable the compatibility bundle (skip clean, plain text, no rich text).",
    },
    "skip_clean": {
        "type": "boolean",
        "description": "Skip the PDF cleaning pass.",
    },
    "disable_rich_text_translate": {
        "type": "boolean",
        "description": "Translate plain text only, dropping inline rich-text markup.",
    },
    "skip_scanned_detection": {
        "type": "boolean",
        "description": "Do not test whether the document is a scan.",
    },
    "auto_enable_ocr_workaround": {
        "type": "boolean",
        "description": "Turn the OCR workaround on automatically for scanned documents.",
    },
    "ocr_workaround": {
        "type": "boolean",
        "description": "Always apply the OCR workaround.",
    },
    "primary_font_family": {
        "type": "enum",
        "values": ["auto", "serif", "sans-serif", "script"],
        "description": "Preferred output font family; auto keeps BabelDOC's choice.",
    },
    "formular_font_pattern": {
        "type": "string",
        "description": "Regex of font names to treat as formula fonts.",
    },
    "formular_char_pattern": {
        "type": "string",
        "description": "Regex of characters to treat as formula characters.",
    },
    "auto_extract_glossary": {
        "type": "boolean",
        "description": "Extract terminology automatically before translating paragraphs.",
    },
    "save_auto_extracted_glossary": {
        "type": "boolean",
        "description": "Write the automatically extracted glossary into the bundle.",
    },
    "min_text_length": {
        "type": "integer",
        "minimum": 0,
        "maximum": 50,
        "description": "Shortest text length that is still sent for translation.",
    },
    "custom_system_prompt": {
        "type": "string",
        "description": "Extra system prompt appended to the translation instructions.",
    },
}

_REQUIRED_NON_EMPTY = ("lang_in", "lang_out", "openai_model")


def _selectable_provider_names() -> frozenset[str]:
    """Provider names a translation run may name. Empty set if the registry cannot be
    imported, which keeps settings validation working in isolation (tests, tooling)."""
    try:
        from ..providers.registry import openai_compatible_providers
    except Exception:  # pragma: no cover - registry import is not a settings concern
        return frozenset()
    return frozenset(d.name for d in openai_compatible_providers())


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_values(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Return the normalized complete value set or raise with every violation."""
    violations: list[dict[str, Any]] = []
    for unknown in sorted(set(candidate) - set(DEFAULT_TRANSLATION_SETTINGS)):
        violations.append(_violation(unknown, "unknown parameter"))
    for missing in sorted(set(DEFAULT_TRANSLATION_SETTINGS) - set(candidate)):
        violations.append(_violation(missing, "parameter is required"))
    if violations:
        raise TranslationValidationError(
            "Translation settings contain unknown or missing parameters", violations
        )

    normalized: dict[str, Any] = {}
    for key, definition in _PARAMETER_DEFINITIONS.items():
        value = candidate[key]
        kind = definition["type"]
        if kind == "boolean":
            if not isinstance(value, bool):
                violations.append(_violation(key, "must be a boolean"))
                continue
        elif kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                violations.append(_violation(key, "must be an integer"))
                continue
            if value < definition["minimum"] or value > definition["maximum"]:
                violations.append(
                    _violation(
                        key,
                        f"must be between {definition['minimum']} and {definition['maximum']}",
                    )
                )
                continue
        elif kind == "number":
            if not _is_number(value) or not math.isfinite(float(value)):
                violations.append(_violation(key, "must be a finite number"))
                continue
            value = float(value)
            if value < definition["minimum"] or value > definition["maximum"]:
                violations.append(
                    _violation(
                        key,
                        f"must be between {definition['minimum']} and {definition['maximum']}",
                    )
                )
                continue
        elif kind == "enum":
            if value not in definition["values"]:
                allowed = ", ".join(definition["values"])
                violations.append(_violation(key, f"must be one of: {allowed}"))
                continue
        else:  # string
            if not isinstance(value, str):
                violations.append(_violation(key, "must be a string"))
                continue
            if key in _REQUIRED_NON_EMPTY and not value.strip():
                violations.append(_violation(key, "must not be empty"))
                continue
            if key == "pages" and value.strip() and not _PAGES_PATTERN.match(value.strip()):
                violations.append(
                    _violation(key, "must be a page selection such as 1-5,8")
                )
                continue
            if key == "provider" and value.strip():
                # Reject an unusable provider at save time rather than mid-run. Only the
                # OpenAI-compatible set can drive BabelDOC's OpenAITranslator; the registry
                # is the single source of truth for which those are.
                if value.strip() not in _selectable_provider_names():
                    violations.append(
                        _violation(
                            key,
                            "must be a provider that speaks the OpenAI-compatible API",
                        )
                    )
                    continue
                value = value.strip()
            value = value.strip() if key in _REQUIRED_NON_EMPTY else value
        normalized[key] = value

    if violations:
        raise TranslationValidationError(
            "Translation settings failed validation", violations
        )
    return normalized


class TranslationSettings:
    """Own the validated translation defaults and their atomic storage."""

    schema_version = 1

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._values = copy.deepcopy(DEFAULT_TRANSLATION_SETTINGS)
        self._load()

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        stored_version = payload.get("schema_version")
        if stored_version is not None and stored_version != self.schema_version:
            return
        values = payload.get("values", payload)
        if not isinstance(values, Mapping):
            return
        merged = copy.deepcopy(DEFAULT_TRANSLATION_SETTINGS)
        merged.update({k: v for k, v in values.items() if k in merged})
        try:
            self._values = _validate_values(merged)
        except TranslationValidationError:
            # A damaged or stale file must not make the module unusable.  Installed
            # defaults stay authoritative until a valid save replaces the file.
            self._values = copy.deepcopy(DEFAULT_TRANSLATION_SETTINGS)

    def get(self) -> dict[str, Any]:
        return copy.deepcopy(self._values)

    def save(self, proposed: Mapping[str, Any]) -> dict[str, Any]:
        """Validate and atomically replace the complete settings document."""
        if not isinstance(proposed, Mapping):
            raise TranslationValidationError(
                "Translation settings must be an object",
                [_violation("", "an object is required")],
            )
        if "values" in proposed:
            unknown = set(proposed) - {"values", "schema_version", "defaults", "parameters"}
            if unknown:
                raise TranslationValidationError(
                    "Translation settings contain unknown fields",
                    [_violation(key, "unknown settings document field") for key in sorted(unknown)],
                )
            supplied_version = proposed.get("schema_version")
            if supplied_version is not None and supplied_version != self.schema_version:
                raise TranslationValidationError(
                    "Translation settings use an unsupported schema version",
                    [_violation("schema_version", "must match the installed schema version")],
                )
        payload = proposed.get("values", proposed)
        if not isinstance(payload, Mapping):
            raise TranslationValidationError(
                "Translation settings values must be an object",
                [_violation("values", "an object is required")],
            )
        candidate = self.get()
        candidate.update(payload)
        normalized = _validate_values(candidate)
        self._atomic_write(normalized)
        self._values = normalized
        return self.document()

    def resolve(self, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
        """Return validated effective values for one run without persisting them."""
        if overrides is None:
            return self.get()
        if not isinstance(overrides, Mapping):
            raise TranslationValidationError(
                "Translation overrides must be an object",
                [_violation("overrides", "an object is required")],
            )
        candidate = self.get()
        candidate.update(overrides)
        return _validate_values(candidate)

    def document(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "values": self.get(),
            "defaults": copy.deepcopy(DEFAULT_TRANSLATION_SETTINGS),
            "parameters": copy.deepcopy(_PARAMETER_DEFINITIONS),
        }

    def _atomic_write(self, values: dict[str, Any]) -> None:
        _atomic_write_json(
            self.path, {"schema_version": self.schema_version, "values": values}
        )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Durably replace one JSON document; a crash leaves the previous file intact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _sse_data(payload: str) -> str:
    """Frame one raw-log payload without losing embedded line breaks."""
    return "".join(f"data: {line}\n" for line in payload.split("\n")) + "\n"


def safe_filename(filename: str) -> str:
    """Return an upload filename that cannot escape its staging directory."""
    if (
        not isinstance(filename, str)
        or not filename.strip()
        or filename in {".", ".."}
        or "\x00" in filename
        or "/" in filename
        or "\\" in filename
    ):
        raise TranslationValidationError(
            "filename must be a bare file name, not a path",
            [_violation("filename", "must be a bare file name")],
        )
    return filename.strip()


def _document_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_DOCUMENT_EXTENSIONS))
        raise TranslationValidationError(
            f"unsupported document type; supported extensions are {supported}",
            [_violation("filename", f"must be one of: {supported}")],
        )
    return extension


def _page_count(path: Path) -> int | None:
    """Best-effort page count; a document that cannot be probed reports null."""
    try:
        import pymupdf

        with pymupdf.open(path) as document:
            return int(document.page_count)
    except Exception:
        pass
    try:
        from pypdf import PdfReader

        return int(len(PdfReader(str(path)).pages))
    except Exception:
        return None


def unique_path(candidate: Path) -> Path:
    """Return ``candidate`` or the first ` (n)` variant that does not exist.

    User data is never overwritten by bundling: both the bundle folder and the moved
    original take a numbered variant when the name is already taken.
    """
    if not candidate.exists():
        return candidate
    stem = candidate.stem if candidate.suffix else candidate.name
    suffix = candidate.suffix
    for index in range(2, 1000):
        alternative = candidate.with_name(f"{stem} ({index}){suffix}")
        if not alternative.exists():
            return alternative
    return candidate.with_name(f"{stem} ({uuid.uuid4().hex[:8]}){suffix}")


def bundle_dir_for(source_path: Path, filename: str) -> Path:
    """The bundle folder for one document: sibling of the original, named after it."""
    return Path(source_path).parent / Path(filename).stem


class RunEventLog:
    """Append-only per-run event log with a monotonic sequence.

    Both the sidecar and the worker process append here.  Each record is one line so a
    partially written tail can never corrupt earlier events, and every append is fsynced
    so a cursor-polling client never sees a sequence it can later lose.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, event_type: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {
            "sequence": self.latest_sequence() + 1,
            "at": time.time(),
            "type": event_type,
        }
        for key, value in (payload or {}).items():
            if key not in {"sequence", "at", "type"}:
                record[key] = value
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return record

    def latest_sequence(self) -> int:
        latest = 0
        for event in self._read_tail():
            sequence = event.get("sequence")
            if isinstance(sequence, int) and not isinstance(sequence, bool):
                latest = max(latest, sequence)
        return latest

    def page(self, after: int = 0) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        latest = 0
        for event in self._read_tail():
            sequence = event.get("sequence")
            if not isinstance(sequence, int) or isinstance(sequence, bool):
                continue
            latest = max(latest, sequence)
            if sequence > after and len(events) < EVENT_PAGE_LIMIT:
                events.append(event)
        sequences = [event["sequence"] for event in events]
        return {
            "events": events,
            "oldest_sequence": min(sequences) if sequences else None,
            "latest_sequence": latest,
            "truncated_before_sequence": (min(sequences) - 1) if sequences else 0,
        }

    def _read_tail(self) -> Iterable[dict[str, Any]]:
        """Yield parsed records from a bounded tail of the log."""
        try:
            with self.path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                start = max(0, size - EVENT_LOG_TAIL_BYTES)
                handle.seek(start)
                if start:
                    handle.readline()  # discard the partial first line
                raw = handle.read()
        except (FileNotFoundError, OSError):
            return
        for line in raw.split(b"\n"):
            if not line or len(line) > EVENT_LINE_MAX_BYTES:
                continue
            try:
                event = json.loads(line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                yield event


def stage_index(stage: Any) -> int:
    if isinstance(stage, str) and stage in STAGE_NAMES:
        return STAGE_NAMES.index(stage)
    return -1


def _float(value: Any, default: float = 0.0) -> float:
    if _is_number(value) and math.isfinite(float(value)):
        return float(value)
    return default


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def _artifact_role(name: str, source_filename: str, result: Mapping[str, Any] | None) -> str:
    if name == "runner.log":
        return "log"
    if name == source_filename:
        return "source"
    if result:
        for key, role in (
            ("mono_pdf_path", "mono"),
            ("no_watermark_mono_pdf_path", "mono"),
            ("dual_pdf_path", "dual"),
            ("no_watermark_dual_pdf_path", "dual"),
            ("auto_extracted_glossary_path", "glossary"),
        ):
            value = result.get(key)
            if isinstance(value, str) and Path(value).name == name:
                return role
    lowered = name.lower()
    if lowered.endswith(".csv") or "glossary" in lowered:
        return "glossary"
    if lowered.endswith(".log"):
        return "log"
    if ".dual" in lowered:
        return "dual"
    if ".mono" in lowered or lowered.endswith(".pdf"):
        return "mono"
    return "log"


class TranslationFacade:
    """The module's only seam: settings, documents, runs, artifacts, and streams.

    Runs are executed one at a time by a single drain thread.  ``runner`` is the one
    injection point: it receives a prepared run directory and returns when that run has
    reached a terminal state.  Production spawns the worker process; tests supply a
    runner that drives the same worker core with a fake translation engine, so no
    production code path carries test-only branching.
    """

    schema_version = 1

    def __init__(
        self,
        data_base: str | Path,
        *,
        runner: Callable[[Path], None] | None = None,
    ):
        self._root = Path(data_base) / "translation"
        self._runs_root = self._root / "runs"
        self._inbox_root = self._root / "inbox"
        self._documents_path = self._root / "documents.json"
        self.settings = TranslationSettings(self._root / "settings.json")
        self._runner = runner or _spawn_worker_process
        self._lock = threading.Lock()
        self._queue: deque[str] = deque()
        self._drain_thread: threading.Thread | None = None

    # -- settings ----------------------------------------------------------------

    def settings_document(self) -> dict[str, Any]:
        return self.settings.document()

    def save_settings(self, body: Mapping[str, Any]) -> dict[str, Any]:
        return self.settings.save(body)

    # -- documents ---------------------------------------------------------------

    def register_documents(self, body: Mapping[str, Any]) -> dict[str, Any]:
        """Register uploaded bytes and/or already-local absolute paths."""
        if not isinstance(body, Mapping):
            raise TranslationValidationError(
                "translation document request must be an object",
                [_violation("", "an object is required")],
            )
        files = body.get("files") or []
        paths = body.get("paths") or []
        if not isinstance(files, list) or not isinstance(paths, list):
            raise TranslationValidationError(
                "files and paths must be arrays",
                [_violation("files", "an array is required")],
            )
        if not files and not paths:
            raise TranslationValidationError(
                "at least one file or path is required",
                [_violation("files", "at least one document is required")],
            )
        registered = [self._document_from_upload(entry) for entry in files]
        registered.extend(self._document_from_path(entry) for entry in paths)
        with self._lock:
            stored = self._load_documents()
            stored.extend(registered)
            self._store_documents(stored)
        return {"documents": [self._public_document(record) for record in registered]}

    def list_documents(self) -> dict[str, Any]:
        with self._lock:
            stored = self._load_documents()
        moved = self._bundled_sources()
        return {
            "documents": [
                self._public_document(record, moved.get(record["document_id"]))
                for record in stored
            ]
        }

    def forget_document(self, document_id: str) -> dict[str, Any]:
        """Remove one document from the queue, with its runs, and report what was deleted.

        Deletion is deliberately asymmetric about whose bytes they are.  This module owns its
        own bookkeeping (the registry entry and the per-run folders: state, events, raw log),
        so those always go.  The user's documents are another matter:

        * a document registered BY PATH is never deleted — it lives wherever the user keeps it,
          and forgetting a queue entry must not reach outside this module's storage;
        * an UPLOAD's staged copy is ours, so it goes — unless a finished run already bundled
          artifacts beside it, in which case the folder holds translations the user has not
          seen yet and only the bookkeeping is dropped.

        An active run for the document is cancelled first, so nothing keeps writing into a
        folder that is being removed.
        """
        with self._lock:
            stored = self._load_documents()
            record = next(
                (item for item in stored if item["document_id"] == document_id), None
            )
        if record is None:
            raise KeyError(document_id)

        # Stop the work before removing what it writes into.
        cancelled: list[str] = []
        for run_id in self._runs_for_document(document_id):
            run_dir = self._runs_root / run_id
            state = self._reconcile_dead_run(run_dir, _read_json(run_dir / "state.json") or {})
            if state.get("state") not in TERMINAL_RUN_STATES:
                self.cancel(run_id)
                cancelled.append(run_id)
        # A cancelled worker needs a moment to observe the marker and stop touching its run
        # directory; removing it underneath a live process would only strand files.
        for run_id in cancelled:
            self._await_terminal(run_id)

        bundled = self._bundled_sources().get(document_id)
        removed_runs = 0
        for run_id in self._runs_for_document(document_id):
            shutil.rmtree(self._runs_root / run_id, ignore_errors=True)
            removed_runs += 1

        with self._lock:
            remaining = [
                item for item in self._load_documents() if item["document_id"] != document_id
            ]
            self._store_documents(remaining)

        source_deleted = self._discard_staged_upload(record, bundled)
        return {
            "document_id": document_id,
            "filename": record["filename"],
            "removed_runs": removed_runs,
            "cancelled_runs": cancelled,
            "source_deleted": source_deleted,
            "bundle_dir": (bundled or {}).get("bundle_dir") or "",
        }

    def _runs_for_document(self, document_id: str) -> list[str]:
        matched: list[str] = []
        for run_id in self._run_ids():
            request = _read_json(self._runs_root / run_id / "request.json") or {}
            if request.get("document_id") == document_id:
                matched.append(run_id)
        return matched

    def _await_terminal(self, run_id: str, timeout: float = 5.0) -> None:
        """Wait briefly for a cancelled run to actually stop writing."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run_dir = self._runs_root / run_id
            state = self._reconcile_dead_run(run_dir, _read_json(run_dir / "state.json") or {})
            if state.get("state") in TERMINAL_RUN_STATES:
                return
            time.sleep(0.05)

    def _discard_staged_upload(
        self, record: Mapping[str, Any], bundled: Mapping[str, str] | None
    ) -> bool:
        """Delete an upload's staged copy when it is ours alone to delete.

        Returns whether anything was removed.  The guard is containment: only paths inside
        this module's own inbox qualify, which is exactly the set of copies uploads created.
        A bundle beside the copy means a finished run produced translations there, so the
        folder stays and the user keeps their artifacts.
        """
        if bundled is not None:
            return False
        try:
            staged = Path(record["source_path"]).resolve()
            inbox = self._inbox_root.resolve()
        except OSError:
            return False
        if not staged.is_relative_to(inbox):
            return False  # registered by path: the user's own file, never ours to delete
        # One staging directory per upload (see _document_from_upload), so the parent is a
        # folder this module created and nothing else lives in it.
        target = staged.parent if staged.parent != inbox else staged
        if not target.exists():
            return False
        shutil.rmtree(target, ignore_errors=True)
        return not target.exists()

    def _document_from_upload(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise TranslationValidationError(
                "each uploaded file must be an object",
                [_violation("files", "an object is required")],
            )
        filename = safe_filename(payload.get("filename"))
        _document_extension(filename)
        encoded = payload.get("content_base64")
        if not isinstance(encoded, str):
            raise TranslationValidationError(
                "content_base64 is required",
                [_violation("content_base64", "a base64 string is required")],
            )
        size = payload.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise TranslationValidationError(
                "size must be a non-negative integer",
                [_violation("size", "must be a non-negative integer")],
            )
        if size > MAX_DOCUMENT_BYTES:
            raise TranslationValidationError(
                f"documents larger than {MAX_DOCUMENT_BYTES} bytes are not supported",
                [_violation("size", "document is too large")],
            )
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise TranslationValidationError(
                "content_base64 must be valid base64",
                [_violation("content_base64", "must be valid base64")],
            ) from error
        if not content:
            raise TranslationValidationError(
                "empty documents are not supported",
                [_violation("content_base64", "document is empty")],
            )
        if len(content) != size:
            raise TranslationValidationError(
                "received document bytes do not match the declared size",
                [_violation("size", "does not match the uploaded bytes")],
            )
        if len(content) > MAX_DOCUMENT_BYTES:
            raise TranslationValidationError(
                f"documents larger than {MAX_DOCUMENT_BYTES} bytes are not supported",
                [_violation("content_base64", "document is too large")],
            )
        # One staging directory per document keeps the bundle folder unambiguous.
        staging = self._inbox_root / f"{time.time_ns()}-{filename}"
        staging.mkdir(parents=True, exist_ok=True)
        source_path = staging / filename
        source_path.write_bytes(content)
        return {
            "document_id": uuid.uuid4().hex,
            "filename": filename,
            "source_path": str(source_path),
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "pages": _page_count(source_path),
            "registered_at": time.time(),
        }

    def _document_from_path(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, str) or not value.strip():
            raise TranslationValidationError(
                "each path must be a non-empty string",
                [_violation("paths", "a non-empty absolute path is required")],
            )
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            raise TranslationValidationError(
                "document paths must be absolute",
                [_violation("paths", "must be an absolute path")],
            )
        candidate = candidate.resolve()
        _document_extension(candidate.name)
        if not candidate.is_file():
            raise TranslationValidationError(
                f"document not found: {value}",
                [_violation("paths", "file does not exist")],
            )
        size = candidate.stat().st_size
        if size == 0:
            raise TranslationValidationError(
                "empty documents are not supported",
                [_violation("paths", "document is empty")],
            )
        if size > MAX_DOCUMENT_BYTES:
            raise TranslationValidationError(
                f"documents larger than {MAX_DOCUMENT_BYTES} bytes are not supported",
                [_violation("paths", "document is too large")],
            )
        digest = hashlib.sha256()
        with candidate.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return {
            "document_id": uuid.uuid4().hex,
            "filename": candidate.name,
            "source_path": str(candidate),
            "size": size,
            "sha256": digest.hexdigest(),
            "pages": _page_count(candidate),
            "registered_at": time.time(),
        }

    def _public_document(
        self, record: Mapping[str, Any], bundled: Mapping[str, str] | None = None
    ) -> dict[str, Any]:
        source_path = (bundled or {}).get("source_path") or record["source_path"]
        bundle_dir = (bundled or {}).get("bundle_dir") or str(
            bundle_dir_for(Path(record["source_path"]), record["filename"])
        )
        return {
            "document_id": record["document_id"],
            "filename": record["filename"],
            "source_path": source_path,
            "size": _int(record.get("size")),
            "sha256": record.get("sha256") or "",
            "pages": record.get("pages") if isinstance(record.get("pages"), int) else None,
            "bundle_dir": bundle_dir,
        }

    def _bundled_sources(self) -> dict[str, dict[str, str]]:
        """Where finished runs left each document: its moved original and its bundle.

        Bundling moves the original, so a document's registered ``source_path`` goes
        stale the moment its first run completes.  The worker is the only party that
        knows the bundle it could actually write to (a name collision forces a numbered
        variant), so a completed run is the authority for both facts.  The most recent
        completed run wins, which is what a re-run of the same document should follow.
        """
        moved: dict[str, dict[str, str]] = {}
        latest: dict[str, float] = {}
        for run_id in self._run_ids():
            request = _read_json(self._runs_root / run_id / "request.json") or {}
            state = _read_json(self._runs_root / run_id / "state.json") or {}
            document_id = request.get("document_id")
            source_path = state.get("source_path")
            bundle_dir = state.get("bundle_dir") or request.get("bundle_dir")
            if (
                state.get("state") != "done"
                or not isinstance(document_id, str)
                or not isinstance(source_path, str)
                or not isinstance(bundle_dir, str)
            ):
                continue
            finished_at = _float(state.get("finished_at"))
            if document_id in latest and finished_at < latest[document_id]:
                continue
            latest[document_id] = finished_at
            moved[document_id] = {"source_path": source_path, "bundle_dir": bundle_dir}
        return moved

    def _load_documents(self) -> list[dict[str, Any]]:
        payload = _read_json(self._documents_path)
        if not payload or payload.get("schema_version") != self.schema_version:
            return []
        documents = payload.get("documents")
        if not isinstance(documents, list):
            return []
        return [
            record
            for record in documents
            if isinstance(record, dict)
            and isinstance(record.get("document_id"), str)
            and isinstance(record.get("filename"), str)
            and isinstance(record.get("source_path"), str)
        ]

    def _store_documents(self, documents: list[dict[str, Any]]) -> None:
        _atomic_write_json(
            self._documents_path,
            {"schema_version": self.schema_version, "documents": documents},
        )

    # -- runs --------------------------------------------------------------------

    def start_runs(self, body: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(body, Mapping):
            raise TranslationValidationError(
                "translation run request must be an object",
                [_violation("", "an object is required")],
            )
        document_ids = body.get("document_ids")
        if not isinstance(document_ids, list) or not document_ids:
            raise TranslationValidationError(
                "document_ids must be a non-empty array",
                [_violation("document_ids", "at least one document id is required")],
            )
        values = self.settings.resolve(body.get("overrides"))
        with self._lock:
            known = {record["document_id"]: record for record in self._load_documents()}
        missing = [
            identifier
            for identifier in document_ids
            if not isinstance(identifier, str) or identifier not in known
        ]
        if missing:
            raise TranslationValidationError(
                "unknown translation document",
                [_violation("document_ids", f"unknown document id: {item}") for item in missing],
            )

        bundled = self._bundled_sources()
        created: list[dict[str, Any]] = []
        for identifier in document_ids:
            created.append(
                self._create_run(known[identifier], values, bundled.get(identifier))
            )
        self._ensure_drain()
        return {"runs": created}

    def _create_run(
        self,
        document: Mapping[str, Any],
        values: Mapping[str, Any],
        bundled: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        run_dir = self._runs_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        # A document that has already been bundled lives inside its bundle now: follow it
        # there and keep writing into the same folder instead of nesting a new one.
        source_path = Path((bundled or {}).get("source_path") or document["source_path"])
        bundle_dir = (bundled or {}).get("bundle_dir") or str(
            bundle_dir_for(Path(document["source_path"]), document["filename"])
        )
        request = {
            "schema_version": self.schema_version,
            "run_id": run_id,
            "document_id": document["document_id"],
            "filename": document["filename"],
            "source_path": str(source_path),
            "bundle_dir": bundle_dir,
            "created_at": time.time(),
            "values": dict(values),
        }
        _atomic_write_json(run_dir / "request.json", request)
        _atomic_write_json(
            run_dir / "state.json",
            {
                "state": "queued",
                "source_path": str(source_path),
                "started_at": None,
                "finished_at": None,
            },
        )
        (run_dir / "runner.log").touch()
        RunEventLog(run_dir / "events.jsonl").append(
            "run.queued", {"message": f"queued {document['filename']}"}
        )
        with self._lock:
            self._queue.append(run_id)
        return self._snapshot(run_id)

    def list_runs(self) -> dict[str, Any]:
        snapshots = [self._snapshot(run_id) for run_id in self._run_ids()]
        snapshots.sort(key=lambda run: run["created_at"], reverse=True)
        return {"runs": snapshots[:RUN_LIST_LIMIT]}

    def run(self, run_id: str) -> dict[str, Any]:
        return self._snapshot(self._validated_run_id(run_id))

    def events(self, run_id: str, after: int = 0) -> dict[str, Any]:
        validated = self._validated_run_id(run_id)
        page = RunEventLog(self._runs_root / validated / "events.jsonl").page(after)
        return {"run_id": validated, **page}

    def cancel(self, run_id: str) -> dict[str, Any]:
        validated = self._validated_run_id(run_id)
        run_dir = self._runs_root / validated
        state = self._reconcile_dead_run(run_dir, _read_json(run_dir / "state.json") or {})
        current = state.get("state")
        if current in TERMINAL_RUN_STATES:
            return self._snapshot(validated)
        # The marker is the single cancellation fact both processes read; the signal is
        # only an accelerator so a long-running engine call stops promptly.
        (run_dir / "cancel").write_text(str(time.time()), encoding="utf-8")
        with self._lock:
            queued = validated in self._queue
            if queued:
                self._queue.remove(validated)
        if current == "queued":
            self._write_state(
                run_dir,
                {
                    **state,
                    "state": "cancelled",
                    "finished_at": time.time(),
                    "stage": None,
                },
            )
            RunEventLog(run_dir / "events.jsonl").append(
                "run.cancelled", {"message": "cancelled before execution"}
            )
            return self._snapshot(validated)
        # The marker above is the authoritative cancellation fact; the signal is only an
        # accelerator for a worker blocked in a long engine call.  Never signal ourselves:
        # an in-process runner records this process's own pid, and signalling it would take
        # down the sidecar instead of the run.
        pid = state.get("pid")
        if isinstance(pid, int) and pid > 0 and pid != os.getpid():
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        return self._snapshot(validated)

    async def stream_log(self, run_id: str, poll_interval: float = 0.05) -> AsyncIterator[str]:
        """Replay one run's raw log, then follow it while the run is active."""
        import asyncio

        validated = self._validated_run_id(run_id)
        log_path = self._runs_root / validated / "runner.log"
        position = 0
        pending = ""
        while True:
            run_dir = self._runs_root / validated
            state = self._reconcile_dead_run(run_dir, _read_json(run_dir / "state.json") or {})
            active = state.get("state") in ACTIVE_RUN_STATES
            if log_path.is_file():
                with log_path.open("r", encoding="utf-8", errors="replace") as stream:
                    if position == 0:
                        try:
                            size = log_path.stat().st_size
                        except OSError:
                            size = 0
                        if size > RAW_LOG_MAX_BYTES:
                            position = size - RAW_LOG_MAX_BYTES
                            stream.seek(position)
                            stream.readline()
                            yield _sse_data("[raw log truncated to the most recent 512 KiB]\n")
                        else:
                            stream.seek(position)
                    else:
                        stream.seek(position)
                    chunk = stream.read()
                    position = stream.tell()
                pending += chunk
                lines = pending.split("\n")
                pending = lines.pop() or ""
                for line in lines:
                    yield _sse_data(f"{line}\n")
            if not active:
                if pending:
                    yield _sse_data(pending)
                return
            await asyncio.sleep(poll_interval)

    def artifact_path(self, run_id: str, name: str) -> Path:
        """Resolve one artifact by exact basename against the run's own artifact list."""
        validated = self._validated_run_id(run_id)
        if (
            not isinstance(name, str)
            or not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or "\x00" in name
            or name != Path(name).name
        ):
            raise TranslationArtifactError("translation artifact is not available")
        for artifact in self._snapshot(validated)["artifacts"]:
            if artifact["name"] == name:
                path = Path(artifact["path"])
                if path.is_file():
                    return path
                break
        raise TranslationArtifactError("translation artifact is not available")

    def reveal_bundle(self, run_id: str, mode: str = "reveal") -> dict[str, Any]:
        """Show one run's bundle folder in the OS file manager.

        The target is derived from the run's own snapshot, never from the caller: a
        caller-supplied path would turn this into an arbitrary-path launcher.  Any ``mode``
        other than ``open`` is treated as ``reveal`` so a stale client can never fail here.
        The server runs on the user's machine in both desktop and browser builds, so this is
        local, and it mirrors ``SessionManager.reveal_artifact``'s platform handling.
        """
        import os
        import subprocess
        import sys

        validated = self._validated_run_id(run_id)
        target = Path(self._snapshot(validated)["bundle_dir"] or "")
        if not target.is_dir():
            return {"ok": False, "error": "translation bundle folder is not available"}
        try:
            if sys.platform == "darwin":
                args = ["open", str(target)] if mode == "open" else ["open", "-R", str(target)]
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif sys.platform == "win32":
                if mode == "open":
                    os.startfile(str(target))  # type: ignore[attr-defined]  # open in default app
                else:
                    # Explorer wants the path glued to the switch: /select,<path>
                    subprocess.Popen(["explorer", f"/select,{target}"])
            else:  # Linux/BSD
                # The target is already a directory, so revealing and opening it collapse to
                # the same act — unlike a file, there is no parent to select it in.
                subprocess.Popen(
                    ["xdg-open", str(target)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "path": str(target)}

    # -- run projection ----------------------------------------------------------

    def _run_ids(self) -> list[str]:
        try:
            return [entry.name for entry in self._runs_root.iterdir() if entry.is_dir()]
        except (FileNotFoundError, OSError):
            return []

    def _validated_run_id(self, run_id: str) -> str:
        if (
            not isinstance(run_id, str)
            or not re.fullmatch(r"[0-9a-f]{32}", run_id)
            or not (self._runs_root / run_id / "request.json").is_file()
        ):
            raise KeyError(run_id)
        return run_id

    def _write_state(self, run_dir: Path, state: Mapping[str, Any]) -> None:
        _atomic_write_json(run_dir / "state.json", dict(state))

    def _reconcile_dead_run(self, run_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
        """Turn an abandoned run into a terminal one.

        Only the worker writes `state.json`, so a worker that dies without reaching a terminal
        state (SIGKILL, a crash, a machine that went down mid-run) leaves the run reading
        `running` forever — it can never be cancelled again and never reports a result. The
        liveness of the recorded pid is the fact that settles it, so every projection checks it.
        """
        if state.get("state") not in ACTIVE_RUN_STATES:
            return state
        pid = state.get("pid")
        if not isinstance(pid, int) or pid <= 0 or pid == os.getpid():
            return state
        try:
            os.kill(pid, 0)
            return state
        except PermissionError:  # alive, just not ours to signal
            return state
        except OSError:
            pass
        cancelled = (run_dir / "cancel").is_file()
        settled = {
            **state,
            "state": "cancelled" if cancelled else "error",
            "finished_at": time.time(),
            "stage": None,
        }
        if not cancelled:
            settled["error"] = "the translation worker stopped without finishing"
        self._write_state(run_dir, settled)
        RunEventLog(run_dir / "events.jsonl").append(
            "run.cancelled" if cancelled else "error",
            {"message": "worker stopped"} if cancelled else {"error": settled["error"]},
        )
        return settled

    def _snapshot(self, run_id: str) -> dict[str, Any]:
        run_dir = self._runs_root / run_id
        request = _read_json(run_dir / "request.json") or {}
        state = self._reconcile_dead_run(run_dir, _read_json(run_dir / "state.json") or {})
        values = request.get("values") or {}
        result = state.get("result") if isinstance(state.get("result"), dict) else None
        run_state = state.get("state")
        if run_state not in ACTIVE_RUN_STATES | TERMINAL_RUN_STATES:
            run_state = "queued"
        started_at = state.get("started_at") if _is_number(state.get("started_at")) else None
        finished_at = state.get("finished_at") if _is_number(state.get("finished_at")) else None
        if started_at is None:
            elapsed = 0.0
        else:
            elapsed = (finished_at or time.time()) - started_at
        source_path = state.get("source_path") or request.get("source_path") or ""
        filename = request.get("filename") or Path(source_path).name
        # The worker resolves the bundle it could actually write to, so its state is
        # authoritative over the directory the sidecar predicted when queueing the run.
        bundle_dir = state.get("bundle_dir") or request.get("bundle_dir") or ""
        return {
            "run_id": run_id,
            "document_id": request.get("document_id") or "",
            "filename": filename,
            "source_path": source_path,
            "bundle_dir": bundle_dir,
            "state": run_state,
            "stage": state.get("stage") if isinstance(state.get("stage"), str) else None,
            "stage_index": _int(state.get("stage_index"), -1),
            "stage_total_count": len(TRANSLATE_STAGE_TABLE),
            "stage_current": _int(state.get("stage_current")),
            "stage_total": _int(state.get("stage_total")),
            "stage_progress": _float(state.get("stage_progress")),
            "overall_progress": _float(state.get("overall_progress")),
            "created_at": _float(request.get("created_at")),
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_seconds": max(0.0, elapsed),
            "error": state.get("error") if isinstance(state.get("error"), str) else None,
            "lang_in": values.get("lang_in") or "",
            "lang_out": values.get("lang_out") or "",
            "stages": [{"name": name, "weight": weight} for name, weight in TRANSLATE_STAGE_TABLE],
            "artifacts": self._artifacts(run_dir, bundle_dir, filename, result),
            "result": result,
        }

    def _artifacts(
        self,
        run_dir: Path,
        bundle_dir: str,
        source_filename: str,
        result: Mapping[str, Any] | None,
    ) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        try:
            entries = sorted(
                Path(bundle_dir or run_dir).iterdir(), key=lambda path: path.name
            )
        except (FileNotFoundError, OSError, NotADirectoryError):
            entries = []
        for entry in entries:
            if not entry.is_file():
                continue
            artifacts.append(
                {
                    "name": entry.name,
                    "role": _artifact_role(entry.name, source_filename, result),
                    "size": entry.stat().st_size,
                    "path": str(entry),
                }
            )
        log_path = run_dir / "runner.log"
        if log_path.is_file():
            artifacts.append(
                {
                    "name": "runner.log",
                    "role": "log",
                    "size": log_path.stat().st_size,
                    "path": str(log_path),
                }
            )
        return artifacts

    # -- execution ---------------------------------------------------------------

    def _ensure_drain(self) -> None:
        with self._lock:
            if self._drain_thread is not None and self._drain_thread.is_alive():
                return
            thread = threading.Thread(
                target=self._drain, name="translation-runs", daemon=True
            )
            self._drain_thread = thread
        thread.start()

    def _drain(self) -> None:
        """Execute queued runs strictly one at a time."""
        while True:
            with self._lock:
                if not self._queue:
                    self._drain_thread = None
                    return
                run_id = self._queue.popleft()
            run_dir = self._runs_root / run_id
            if (run_dir / "cancel").exists():
                continue
            try:
                self._runner(run_dir)
            except Exception as error:  # a runner failure must still land a state
                state = _read_json(run_dir / "state.json") or {}
                if state.get("state") not in TERMINAL_RUN_STATES:
                    self._write_state(
                        run_dir,
                        {
                            **state,
                            "state": "error",
                            "error": f"translation runner failed: {error}",
                            "finished_at": time.time(),
                        },
                    )
                    RunEventLog(run_dir / "events.jsonl").append(
                        "error", {"error": f"translation runner failed: {error}"}
                    )


def _spawn_worker_process(run_dir: Path) -> None:
    """Start the worker in its own session and wait for it to finish."""
    from .translation_worker import spawn_worker

    process = spawn_worker(run_dir)
    process.wait()


__all__ = [
    "DEFAULT_TRANSLATION_SETTINGS",
    "MAX_DOCUMENT_BYTES",
    "RunEventLog",
    "STAGE_NAMES",
    "TRANSLATE_STAGE_TABLE",
    "TranslationArtifactError",
    "TranslationFacade",
    "TranslationSettings",
    "TranslationValidationError",
    "bundle_dir_for",
    "stage_index",
    "unique_path",
]
