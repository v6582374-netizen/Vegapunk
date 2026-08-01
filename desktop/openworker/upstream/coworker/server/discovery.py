"""Native Desktop Discovery state and the first Preparation storage seam."""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import os
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any


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


class PreparationValidationError(ValueError):
    """Raised when a source batch or draft payload violates the intake contract."""


def _empty_preparation() -> dict[str, Any]:
    return {"text": "", "sources": []}


def _copy_preparation(preparation: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(preparation)


def _has_input(preparation: dict[str, Any]) -> bool:
    return bool(preparation["text"].strip() or preparation["sources"])


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

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            dirty = self._draft != self._committed
            if dirty:
                status = "draft"
            elif _has_input(self._committed):
                status = "saved"
            else:
                status = "empty"
            preparation = {
                "status": status,
                "dirty": dirty,
                "draft": _public_preparation(self._draft),
                "saved": _public_preparation(self._committed),
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
            }
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
            return self.snapshot()

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
            return {"text": text, "sources": sources}
        except (KeyError, TypeError, ValueError, binascii.Error):
            return _empty_preparation()

    def _write_committed(self, preparation: dict[str, Any]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "text": preparation["text"],
            "sources": [
                {
                    **_public_source(source),
                    "content_base64": base64.b64encode(source["content"]).decode("ascii"),
                }
                for source in preparation["sources"]
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
