"""Native Desktop Discovery state and the first Preparation storage seam."""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import io
import json
import os
import sys
import tempfile
import threading
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import yaml


DISCOVERY_CONTEXTS = (
    {
        "id": "preparation",
        "label": "Preparation",
        "description": "Gather and review research inputs before a launch.",
    },
    {
        "id": "launch",
        "label": "Current Launch",
        "description": "Observe the active Discovery launch.",
    },
    {
        "id": "history",
        "label": "History",
        "description": "Review completed and interrupted Discovery launches.",
    },
)

SUPPORTED_SOURCE_EXTENSIONS = frozenset({".txt", ".md", ".pdf", ".docx", ".csv", ".zip"})


def _conversion_prompt_path() -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(bundled_root) / "config" / "discovery_input_conversion_prompt.yaml"
    return Path(__file__).resolve().parents[5] / "config" / "discovery_input_conversion_prompt.yaml"


DISCOVERY_INPUT_CONVERSION_PROMPT_PATH = _conversion_prompt_path()


class PreparationValidationError(ValueError):
    """Raised when a source batch or draft payload violates the intake contract."""


class DiscoveryConfigurationError(RuntimeError):
    """Raised when the configured conversion Prompt or default model is unavailable."""


class DiscoveryConversionError(RuntimeError):
    """Raised when the default text model cannot produce a formatted input."""


class DiscoverySourceContentError(ValueError):
    """Raised when an accepted source cannot be read during Conversion."""


def _empty_preparation() -> dict[str, Any]:
    return {"text": "", "sources": [], "revisions": []}


def _copy_preparation(preparation: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(preparation)


def _has_input(preparation: dict[str, Any]) -> bool:
    return bool(preparation["text"].strip() or preparation["sources"])


def _preparation_fingerprint(preparation: dict[str, Any]) -> str:
    material = {
        "text": preparation["text"],
        "sources": [
            {
                "source_id": source["source_id"],
                "filename": source["filename"],
                "size": source["size"],
                "sha256": source["sha256"],
            }
            for source in preparation["sources"]
        ],
    }
    return hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _public_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": source["source_id"],
        "filename": source["filename"],
        "extension": source["extension"],
        "size": source["size"],
        "sha256": source["sha256"],
    }


def _public_preparation(preparation: dict[str, Any]) -> dict[str, Any]:
    return {
        "text": preparation["text"],
        "sources": [_public_source(source) for source in preparation["sources"]],
    }


def _public_revision(
    revision: dict[str, Any], current_fingerprint: str, preparation_dirty: bool
) -> dict[str, Any]:
    return {
        "revision_id": revision["revision_id"],
        "created_at": revision["created_at"],
        "formatted_input": revision["formatted_input"],
        "model_id": revision.get("model_id"),
        "eligible": (
            not preparation_dirty
            and revision.get("preparation_fingerprint") == current_fingerprint
        ),
    }


class DiscoveryFacade:
    """Expose Discovery state from the existing sidecar process.

    The draft is deliberately process-local. Only the committed Preparation is written to
    the application-owned state root, so a sidecar restart discards unsaved intake changes.
    """

    def __init__(self, state_root: str | Path):
        self._state_path = Path(state_root) / "discovery" / "preparation.json"
        self._lock = threading.RLock()
        self._committed = self._load_committed()
        self._draft = _copy_preparation(self._committed)
        self._conversion_draft = ""
        self._conversion_model_id: str | None = None
        self._conversion_error: str | None = None
        self._conversion_base_fingerprint: str | None = None
        self._conversion_saved_revision_id: str | None = None

    def _invalidate_conversion(self) -> None:
        self._conversion_draft = ""
        self._conversion_model_id = None
        self._conversion_error = None
        self._conversion_base_fingerprint = None
        self._conversion_saved_revision_id = None

    def _record_conversion_failure(self, message: str, base_fingerprint: str) -> None:
        with self._lock:
            self._conversion_error = message
            self._conversion_draft = ""
            self._conversion_model_id = None
            self._conversion_base_fingerprint = base_fingerprint
            self._conversion_saved_revision_id = None

    def _conversion_snapshot(self, current_fingerprint: str, preparation_dirty: bool) -> dict[str, Any]:
        if self._conversion_error:
            status = "failed"
        elif self._conversion_draft:
            if self._conversion_saved_revision_id:
                saved = next(
                    (
                        revision
                        for revision in self._committed["revisions"]
                        if revision["revision_id"] == self._conversion_saved_revision_id
                    ),
                    None,
                )
                status = "saved" if saved and saved["formatted_input"] == self._conversion_draft else "dirty"
            else:
                status = "editing"
        else:
            status = "dirty" if preparation_dirty else "pending"
        return {
            "status": status,
            "draft": self._conversion_draft,
            "model_id": self._conversion_model_id,
            "error": self._conversion_error,
            "saved_revision_id": self._conversion_saved_revision_id,
            "base_fingerprint": self._conversion_base_fingerprint,
            "current_fingerprint": current_fingerprint,
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            dirty = (
                self._draft["text"] != self._committed["text"]
                or self._draft["sources"] != self._committed["sources"]
            )
            if dirty:
                status = "draft"
            elif _has_input(self._committed):
                status = "saved"
            else:
                status = "empty"
            current_fingerprint = _preparation_fingerprint(self._committed)
            preparation = {
                "status": status,
                "dirty": dirty,
                "draft": _public_preparation(self._draft),
                "saved": _public_preparation(self._committed),
                "revisions": [
                    _public_revision(revision, current_fingerprint, dirty)
                    for revision in self._committed["revisions"]
                ],
                "conversion": self._conversion_snapshot(current_fingerprint, dirty),
            }
        return {
            "module": "discovery",
            "schema_version": 1,
            "contexts": [dict(context) for context in DISCOVERY_CONTEXTS],
            "active_context": "preparation",
            "preparation": preparation,
            "current_launch": None,
            "history": [],
        }

    def intake(self, body: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise PreparationValidationError("intake payload must be an object")

        has_text = "text" in body
        text = body.get("text", "")
        if has_text and not isinstance(text, str):
            raise PreparationValidationError("text must be a string")

        files = body.get("files", [])
        if files is None:
            files = []
        if not isinstance(files, list):
            raise PreparationValidationError("files must be a list")
        if not has_text and not files:
            raise PreparationValidationError("intake requires text or at least one file")

        # Validate and decode every file before touching the in-memory draft. This is the
        # atomic batch boundary: one bad file rejects the complete intake attempt.
        sources = [self._source_from_payload(payload) for payload in files]
        with self._lock:
            draft = _copy_preparation(self._draft)
            if has_text:
                draft["text"] = text
            draft["sources"].extend(sources)
            self._draft = draft
            self._invalidate_conversion()
            return self.snapshot()

    def delete_source(self, source_id: str) -> dict[str, Any]:
        with self._lock:
            sources = self._draft["sources"]
            if not any(source["source_id"] == source_id for source in sources):
                raise KeyError(source_id)
            self._draft = {
                "text": self._draft["text"],
                "sources": [
                    source for source in sources if source["source_id"] != source_id
                ],
                "revisions": _copy_preparation(self._committed)["revisions"],
            }
            self._invalidate_conversion()
            return self.snapshot()

    def save(self, body: dict[str, Any] | None = None) -> dict[str, Any]:
        body = body or {}
        if not isinstance(body, dict):
            raise PreparationValidationError("save payload must be an object")
        if "text" in body and not isinstance(body["text"], str):
            raise PreparationValidationError("text must be a string")

        with self._lock:
            draft = _copy_preparation(self._draft)
            if "text" in body:
                draft["text"] = body["text"]
            self._write_committed(draft)
            self._committed = draft
            self._draft = _copy_preparation(draft)
            self._invalidate_conversion()
            return self.snapshot()

    def convert(
        self,
        provider: Any,
        model: str,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            dirty = (
                self._draft["text"] != self._committed["text"]
                or self._draft["sources"] != self._committed["sources"]
            )
            if dirty:
                raise PreparationValidationError(
                    "save the Preparation before Conversion"
                )
            if not _has_input(self._committed):
                raise PreparationValidationError(
                    "Conversion requires a non-empty saved Preparation"
                )
            preparation = _copy_preparation(self._committed)
            base_fingerprint = _preparation_fingerprint(preparation)

        try:
            instruction = self._conversion_instruction()
            sources = [self._source_material(source) for source in preparation["sources"]]
            request = json.dumps(
                {
                    "operation": "format_discovery_input",
                    "research_text": preparation["text"],
                    "sources": sources,
                },
                ensure_ascii=False,
            )
            turn = provider.complete(
                model=model,
                messages=[
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": request},
                ],
                **dict(settings or {}),
            )
            formatted_input = (getattr(turn, "text", None) or "").strip()
            if not formatted_input:
                raise DiscoveryConversionError(
                    "the default text model returned an empty Formatted Discovery Input"
                )
        except DiscoverySourceContentError as error:
            self._record_conversion_failure(str(error), base_fingerprint)
            raise
        except (DiscoveryConfigurationError, DiscoveryConversionError) as error:
            self._record_conversion_failure(str(error), base_fingerprint)
            raise
        except Exception as error:
            message = "the default text model could not generate a Formatted Discovery Input"
            self._record_conversion_failure(message, base_fingerprint)
            raise DiscoveryConversionError(message) from error

        with self._lock:
            current_fingerprint = _preparation_fingerprint(self._committed)
            dirty = (
                self._draft["text"] != self._committed["text"]
                or self._draft["sources"] != self._committed["sources"]
            )
            if dirty or current_fingerprint != base_fingerprint:
                raise PreparationValidationError(
                    "the Preparation changed during Conversion; save and convert again"
                )
            self._conversion_draft = formatted_input
            self._conversion_model_id = model
            self._conversion_error = None
            self._conversion_base_fingerprint = base_fingerprint
            self._conversion_saved_revision_id = None
            return self.snapshot()

    def save_revision(self, body: dict[str, Any] | None = None) -> dict[str, Any]:
        body = body or {}
        if not isinstance(body, dict):
            raise PreparationValidationError("revision payload must be an object")
        formatted_input = body.get("formatted_input")
        if not isinstance(formatted_input, str) or not formatted_input.strip():
            raise PreparationValidationError(
                "Formatted Discovery Input must not be empty"
            )

        with self._lock:
            dirty = (
                self._draft["text"] != self._committed["text"]
                or self._draft["sources"] != self._committed["sources"]
            )
            if dirty:
                raise PreparationValidationError(
                    "save the Preparation before saving a revision"
                )
            if not self._conversion_draft or not self._conversion_base_fingerprint:
                raise PreparationValidationError(
                    "convert the committed Preparation before saving a revision"
                )
            fingerprint = _preparation_fingerprint(self._committed)
            if fingerprint != self._conversion_base_fingerprint:
                raise PreparationValidationError(
                    "the Preparation changed; convert it again before saving a revision"
                )
            revision = {
                "revision_id": uuid.uuid4().hex,
                "created_at": datetime.now(UTC).isoformat(),
                "formatted_input": formatted_input,
                "model_id": self._conversion_model_id,
                "preparation_fingerprint": fingerprint,
            }
            committed = _copy_preparation(self._committed)
            committed["revisions"].append(revision)
            self._write_committed(committed)
            self._committed = committed
            self._draft = _copy_preparation(committed)
            self._conversion_draft = formatted_input
            self._conversion_error = None
            self._conversion_saved_revision_id = revision["revision_id"]
            return self.snapshot()

    @staticmethod
    def _conversion_instruction() -> str:
        try:
            raw = yaml.safe_load(
                DISCOVERY_INPUT_CONVERSION_PROMPT_PATH.read_text(encoding="utf-8")
            )
        except (OSError, yaml.YAMLError) as error:
            raise DiscoveryConfigurationError(
                "Discovery Input Conversion Prompt is not configured"
            ) from error
        instruction = raw.get("instruction") if isinstance(raw, dict) else None
        if not isinstance(instruction, str) or not instruction.strip():
            raise DiscoveryConfigurationError(
                "Discovery Input Conversion Prompt is not configured"
            )
        return instruction.strip()

    @staticmethod
    def _source_material(source: dict[str, Any]) -> dict[str, str]:
        extension = source["extension"]
        content = source["content"]
        try:
            if extension in {".txt", ".md", ".csv"}:
                text = content.decode("utf-8")
            elif extension == ".pdf":
                from pypdf import PdfReader

                text = "\n\n".join(
                    page.extract_text() or ""
                    for page in PdfReader(io.BytesIO(content)).pages
                )
            elif extension == ".docx":
                with zipfile.ZipFile(io.BytesIO(content)) as document:
                    root = ElementTree.fromstring(document.read("word/document.xml"))
                paragraphs = []
                for paragraph in root.iter():
                    if not paragraph.tag.endswith("}p"):
                        continue
                    paragraphs.append(
                        "".join(
                            node.text or ""
                            for node in paragraph.iter()
                            if node.tag.endswith("}t")
                        )
                    )
                text = "\n".join(paragraphs)
            elif extension == ".zip":
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    names = []
                    for member in archive.infolist():
                        member_path = member.filename.replace("\\", "/")
                        parts = [part for part in member_path.split("/") if part]
                        if member_path.startswith("/") or ".." in parts:
                            raise ValueError("zip entry escapes package")
                        if not member.is_dir():
                            names.append(member.filename)
                text = "Baseline code package files:\n" + "\n".join(names)
            else:
                raise ValueError("unsupported source type")
        except Exception as error:
            raise DiscoverySourceContentError(
                f"unable to read source: {source['filename']}"
            ) from error
        return {
            "name": source["filename"],
            "kind": "baseline_code" if extension == ".zip" else "reference",
            "content": text,
        }

    def _source_from_payload(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise PreparationValidationError("each file must be an object")
        if payload.get("is_directory") or payload.get("relative_path"):
            raise PreparationValidationError("folders are not supported as Discovery sources")

        filename = payload.get("filename")
        if not isinstance(filename, str) or not filename.strip():
            raise PreparationValidationError("filename is required")
        if (
            filename in {".", ".."}
            or "\x00" in filename
            or "/" in filename
            or "\\" in filename
        ):
            raise PreparationValidationError("folder paths are not supported as Discovery sources")

        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED_SOURCE_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_SOURCE_EXTENSIONS))
            raise PreparationValidationError(
                f"unsupported source type; supported extensions are {supported}"
            )

        encoded = payload.get("content_base64")
        if not isinstance(encoded, str):
            raise PreparationValidationError("content_base64 is required")
        size = payload.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise PreparationValidationError("size must be a non-negative integer")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise PreparationValidationError("content_base64 must contain valid bytes") from exc
        if not content:
            raise PreparationValidationError("empty source files are not supported")
        if len(content) != size:
            raise PreparationValidationError("received source bytes do not match the declared size")

        return {
            "source_id": uuid.uuid4().hex,
            "filename": filename,
            "extension": extension,
            "size": size,
            "sha256": hashlib.sha256(content).hexdigest(),
            "content": content,
        }

    def _load_committed(self) -> dict[str, Any]:
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return _empty_preparation()
        except (OSError, ValueError):
            return _empty_preparation()

        try:
            text = raw["text"]
            persisted_sources = raw["sources"]
            if not isinstance(text, str) or not isinstance(persisted_sources, list):
                raise ValueError("invalid Preparation manifest")
            persisted_revisions = raw.get("revisions", [])
            if not isinstance(persisted_revisions, list):
                raise ValueError("invalid Preparation revisions")
            sources = []
            for source in persisted_sources:
                encoded = source["content_base64"]
                content = base64.b64decode(encoded, validate=True)
                if not content or len(content) != source["size"]:
                    raise ValueError("invalid persisted source bytes")
                sources.append(
                    {
                        "source_id": source["source_id"],
                        "filename": source["filename"],
                        "extension": source["extension"],
                        "size": source["size"],
                        "sha256": source["sha256"],
                        "content": content,
                    }
                )
            revisions = []
            for revision in persisted_revisions:
                if not isinstance(revision, dict):
                    raise ValueError("invalid Preparation revision")
                revision_id = revision["revision_id"]
                created_at = revision["created_at"]
                formatted_input = revision["formatted_input"]
                fingerprint = revision["preparation_fingerprint"]
                if not all(
                    isinstance(value, str) and value.strip()
                    for value in (revision_id, created_at, formatted_input, fingerprint)
                ):
                    raise ValueError("invalid Preparation revision")
                model_id = revision.get("model_id")
                if model_id is not None and not isinstance(model_id, str):
                    raise ValueError("invalid Preparation revision model")
                revisions.append(
                    {
                        "revision_id": revision_id,
                        "created_at": created_at,
                        "formatted_input": formatted_input,
                        "model_id": model_id,
                        "preparation_fingerprint": fingerprint,
                    }
                )
            return {"text": text, "sources": sources, "revisions": revisions}
        except (KeyError, TypeError, ValueError, binascii.Error):
            return _empty_preparation()

    def _write_committed(self, preparation: dict[str, Any]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 2,
            "text": preparation["text"],
            "sources": [
                {
                    **_public_source(source),
                    "content_base64": base64.b64encode(source["content"]).decode("ascii"),
                }
                for source in preparation["sources"]
            ],
            "revisions": [
                {
                    "revision_id": revision["revision_id"],
                    "created_at": revision["created_at"],
                    "formatted_input": revision["formatted_input"],
                    "model_id": revision.get("model_id"),
                    "preparation_fingerprint": revision["preparation_fingerprint"],
                }
                for revision in preparation.get("revisions", [])
            ],
        }
        temporary_path: str | None = None
        try:
            descriptor, temporary_path = tempfile.mkstemp(
                prefix=".preparation-",
                suffix=".json",
                dir=self._state_path.parent,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._state_path)
            temporary_path = None
        finally:
            if temporary_path:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass
