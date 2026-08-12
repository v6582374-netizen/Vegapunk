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

from .discovery_artifacts import artifact_list, read_artifact, reveal_artifact
from .discovery_launch import (
    DiscoveryLaunchStore,
    LaunchValidationError,
)

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
SUPPORTED_TASK_TYPES = frozenset({"auto", "sci"})

EXECUTION_INPUT_FIELDS = (
    "task_description",
    "domain",
    "background",
    "constraints",
    "task_type",
)


def _conversion_prompt_path() -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(bundled_root) / "config" / "discovery_input_conversion_prompt.yaml"
    return Path(__file__).resolve().parents[5] / "config" / "discovery_input_conversion_prompt.yaml"


DISCOVERY_INPUT_CONVERSION_PROMPT_PATH = _conversion_prompt_path()


def _read_conversion_prompt(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"instruction": "", "configured": False}
    try:
        values = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise ValueError("Discovery Input Conversion Prompt contains invalid YAML") from error
    if not isinstance(values, dict) or not isinstance(values.get("instruction", ""), str):
        raise ValueError("Discovery Input Conversion Prompt must contain a string instruction")
    instruction = values.get("instruction", "")
    return {"instruction": instruction, "configured": bool(instruction.strip())}


class PreparationValidationError(ValueError):
    """Raised when a source batch or draft payload violates the intake contract."""


class DiscoveryConfigurationError(RuntimeError):
    """Raised when the configured conversion Prompt or default model is unavailable."""


class DiscoveryConversionError(RuntimeError):
    """Raised when the default text model cannot produce structured inputs."""


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


def _public_execution_input(execution_input: dict[str, Any]) -> dict[str, Any]:
    public = {
        "task_description": execution_input["task_description"],
        "domain": execution_input["domain"],
        "background": execution_input["background"],
        "constraints": list(execution_input["constraints"]),
    }
    # ``task_type`` was added after the first Web Launches shipped.  Keep it
    # optional at the wire boundary so old saved revisions remain readable,
    # while preserving it whenever a reviewer explicitly selects a type.
    if "task_type" in execution_input:
        public["task_type"] = execution_input["task_type"]
    return public


def _normalize_execution_input(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Discovery Execution Input must be an object")

    task_description = value.get("task_description")
    domain = value.get("domain")
    background = value.get("background", "")
    constraints = value.get("constraints", [])
    task_type = value.get("task_type")
    if not isinstance(task_description, str) or not task_description.strip():
        raise ValueError("task_description is required")
    if not isinstance(domain, str) or not domain.strip():
        raise ValueError("domain is required")
    if not isinstance(background, str):
        raise ValueError("background must be a string")
    if not isinstance(constraints, list):
        raise ValueError("constraints must be a list")
    if any(not isinstance(item, str) for item in constraints):
        raise ValueError("constraints must contain only strings")
    normalized = {
        "task_description": task_description.strip(),
        "domain": domain.strip(),
        "background": background.strip(),
        "constraints": [item.strip() for item in constraints if item.strip()],
    }
    if task_type is not None:
        if (
            not isinstance(task_type, str)
            or task_type.strip().lower() not in SUPPORTED_TASK_TYPES
        ):
            supported = ", ".join(sorted(SUPPORTED_TASK_TYPES))
            raise ValueError(f"task_type must be one of: {supported}")
        normalized["task_type"] = task_type.strip().lower()
    return normalized


def _public_revision(
    revision: dict[str, Any], current_fingerprint: str, preparation_dirty: bool
) -> dict[str, Any]:
    public = {
        "revision_id": revision["revision_id"],
        "created_at": revision["created_at"],
        "model_id": revision.get("model_id"),
        "eligible": (
            not preparation_dirty
            and revision.get("preparation_fingerprint") == current_fingerprint
        ),
    }
    if "execution_input" in revision:
        public["execution_input"] = _public_execution_input(revision["execution_input"])
    return public


class DiscoveryFacade:
    """Expose Discovery state from the existing sidecar process.

    The draft is deliberately process-local. Only the committed Preparation is written to
    the application-owned state root, so a sidecar restart discards unsaved intake changes.
    """

    def __init__(
        self,
        state_root: str | Path,
        *,
        conversion_prompt_path: str | Path | None = None,
        runner_mode: str = "fake",
        repository_root: str | Path | None = None,
    ):
        self._state_path = Path(state_root) / "discovery" / "preparation.json"
        self._source_store_root = self._state_path.parent / "sources"
        self._conversion_prompt_path = Path(
            conversion_prompt_path or DISCOVERY_INPUT_CONVERSION_PROMPT_PATH
        )
        self._lock = threading.RLock()
        self._launches = DiscoveryLaunchStore(
            Path(state_root) / "discovery",
            runner_mode=runner_mode,
            repository_root=repository_root,
        )
        self._committed = self._load_committed()
        self._draft = _copy_preparation(self._committed)
        self._conversion_draft: dict[str, Any] | None = None
        self._conversion_model_id: str | None = None
        self._conversion_error: str | None = None
        self._conversion_base_fingerprint: str | None = None
        self._conversion_saved_revision_id: str | None = None

    def _invalidate_conversion(self) -> None:
        self._conversion_draft = None
        self._conversion_model_id = None
        self._conversion_error = None
        self._conversion_base_fingerprint = None
        self._conversion_saved_revision_id = None

    def _record_conversion_failure(self, message: str, base_fingerprint: str) -> None:
        with self._lock:
            self._conversion_error = message
            self._conversion_draft = None
            self._conversion_model_id = None
            self._conversion_base_fingerprint = base_fingerprint
            self._conversion_saved_revision_id = None

    def _conversion_snapshot(self, current_fingerprint: str, preparation_dirty: bool) -> dict[str, Any]:
        if self._conversion_error:
            status = "failed"
        elif self._conversion_draft is not None:
            if self._conversion_saved_revision_id:
                saved = next(
                    (
                        revision
                        for revision in self._committed["revisions"]
                        if revision["revision_id"] == self._conversion_saved_revision_id
                    ),
                    None,
                )
                if saved and "execution_input" in saved:
                    status = (
                        "saved"
                        if saved["execution_input"] == self._conversion_draft
                        else "dirty"
                    )
                else:
                    status = "dirty"
            else:
                status = "editing"
        else:
            status = "dirty" if preparation_dirty else "pending"
        snapshot = {
            "status": status,
            "model_id": self._conversion_model_id,
            "error": self._conversion_error,
            "saved_revision_id": self._conversion_saved_revision_id,
            "base_fingerprint": self._conversion_base_fingerprint,
            "current_fingerprint": current_fingerprint,
        }
        if self._conversion_draft is not None:
            snapshot["execution_input"] = _public_execution_input(self._conversion_draft)
        return snapshot

    def snapshot(self, active_context: str = "preparation") -> dict[str, Any]:
        with self._lock:
            dirty = self._is_dirty()
            if dirty:
                status = "draft"
            elif _has_input(self._committed):
                status = "saved"
            else:
                status = "empty"
            current_fingerprint = _preparation_fingerprint(self._committed)
            current_launch, history = self._launches.snapshot()
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
            "active_context": active_context,
            "preparation": preparation,
            "current_launch": current_launch,
            "history": history,
        }

    def _is_dirty(self) -> bool:
        return (
            self._draft["text"] != self._committed["text"]
            or self._draft["sources"] != self._committed["sources"]
        )

    def start_launch(
        self,
        body: dict[str, Any],
        *,
        idempotency_key: str,
        model_id: str,
        settings: dict[str, Any],
        discovery_preferences: dict[str, Any] | None = None,
        external_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise LaunchValidationError("Launch payload must be an object")
        if not idempotency_key:
            raise LaunchValidationError("Idempotency-Key is required to start a Launch")
        if len(idempotency_key) > 256:
            raise LaunchValidationError("Idempotency-Key is too long")

        unexpected_fields = set(body) - {"preparation_id", "revision_id"}
        if unexpected_fields:
            raise LaunchValidationError(
                "Run accepts only the saved Preparation revision identity"
            )

        preparation_id = body.get("preparation_id", "preparation")
        revision_id = body.get("revision_id")
        if preparation_id != "preparation":
            raise LaunchValidationError("unknown Preparation identity")
        if not isinstance(revision_id, str) or not revision_id.strip():
            raise LaunchValidationError("revision_id is required to start a Launch")

        try:
            request_fingerprint = hashlib.sha256(
                json.dumps(
                    {"preparation_id": preparation_id, "revision_id": revision_id},
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
        except (TypeError, ValueError) as error:
            raise LaunchValidationError("Launch payload is not valid JSON") from error

        with self._lock:
            replay = self._launches.replay_idempotent(
                idempotency_key,
                request_fingerprint,
                response_builder=lambda: self.snapshot(active_context="launch"),
            )
            if replay is not None:
                return replay
            dirty = self._is_dirty()
            current_fingerprint = _preparation_fingerprint(self._committed)
            revision = next(
                (
                    item
                    for item in self._committed["revisions"]
                    if item.get("revision_id") == revision_id
                ),
                None,
            )
            if (
                dirty
                or revision is None
                or revision.get("preparation_fingerprint") != current_fingerprint
            ):
                raise LaunchValidationError(
                    "the saved Preparation and revision must be current before Run"
                )
            execution_input = revision.get("execution_input")
            if execution_input is not None:
                try:
                    execution_input = _normalize_execution_input(execution_input)
                except ValueError as error:
                    raise LaunchValidationError(
                        "the saved Discovery Execution Input is invalid"
                    ) from error
            else:
                raise LaunchValidationError(
                    "the selected Discovery revision has no structured Execution Input"
                )
            if (
                self._conversion_error
                or self._conversion_saved_revision_id != revision_id
                or self._conversion_base_fingerprint != current_fingerprint
                or (
                    execution_input is not None
                    and self._conversion_draft != execution_input
                )
            ):
                raise LaunchValidationError(
                    "run requires a successful current Conversion for the selected revision"
                )
            input_sources: list[dict[str, Any]] = []
            for source in self._committed["sources"]:
                input_sources.append(
                    {
                        **_public_source(source),
                        # The worker resolves this content-addressed reference
                        # inside the private sidecar state root. No source bytes
                        # travel in the per-Launch JSON snapshot anymore.
                        "content_ref": source["sha256"],
                    }
                )
            input_snapshot = {
                "preparation_id": preparation_id,
                "revision_id": revision_id,
                "preparation_fingerprint": current_fingerprint,
                "research_text": self._committed["text"],
                "sources": input_sources,
            }
            input_snapshot["execution_input"] = _public_execution_input(execution_input)
            created_digests: list[str] = []

            def materialize_input_snapshot() -> dict[str, Any]:
                try:
                    for source in self._committed["sources"]:
                        _, created = self._ensure_source_blob(source)
                        if created:
                            created_digests.append(source["sha256"])
                    return input_snapshot
                except Exception:
                    # This callback runs under DiscoveryLaunchStore's shared
                    # admission lock, so partial materialization can be cleaned
                    # without racing another sidecar's pending Launch.
                    cleanup_materialized_sources()
                    raise

            def cleanup_materialized_sources() -> None:
                for digest in set(created_digests):
                    if self._source_blob_is_referenced(digest):
                        continue
                    try:
                        (self._source_store_root / digest).unlink(missing_ok=True)
                    except OSError:
                        continue

            configuration_snapshot = {
                "model_id": model_id,
                "settings": copy.deepcopy(settings),
            }
            if discovery_preferences is not None:
                # The Launch owns a complete copy of the validated defaults.  The
                # Discovery runner and every Resume attempt read this snapshot rather
                # than observing later Settings edits.
                configuration_snapshot["discovery_launch_preferences"] = copy.deepcopy(
                    discovery_preferences
                )
            if external_data is not None:
                # Only the non-sensitive API registry and provider status are frozen
                # into the Launch. API credentials remain in SecretStore and are
                # resolved by the worker.
                configuration_snapshot["external_data"] = copy.deepcopy(external_data)
            return self._launches.admit(
                request_fingerprint=request_fingerprint,
                idempotency_key=idempotency_key,
                input_snapshot=input_snapshot,
                configuration_snapshot=configuration_snapshot,
                response_builder=lambda: self.snapshot(active_context="launch"),
                input_snapshot_factory=materialize_input_snapshot,
                input_snapshot_cleanup=cleanup_materialized_sources,
            )

    def launch(self, launch_id: str) -> dict[str, Any]:
        return self._launches.get(launch_id)

    def status(self, launch_id: str) -> dict[str, Any]:
        return self._launches.status(launch_id)

    def events(self, launch_id: str, after: int = 0) -> dict[str, Any]:
        return self._launches.events(launch_id, after)

    def stream_log(self, launch_id: str):
        return self._launches.stream_log(launch_id)

    def artifacts(self, launch_id: str) -> dict[str, Any]:
        root = self._launches.artifacts_root(launch_id)
        return {"launch_id": launch_id, "artifacts": artifact_list(root)}

    def read_artifact(self, launch_id: str, relative_path: str) -> dict[str, Any]:
        root = self._launches.artifacts_root(launch_id)
        return read_artifact(root, relative_path)

    def reveal_artifact(
        self,
        launch_id: str,
        relative_path: str,
        mode: str = "reveal",
    ) -> dict[str, Any]:
        root = self._launches.artifacts_root(launch_id)
        return reveal_artifact(root, relative_path, mode)

    def get_conversion_prompt(self) -> dict[str, Any]:
        return _read_conversion_prompt(self._conversion_prompt_path)

    def save_conversion_prompt(self, instruction: str) -> dict[str, Any]:
        if not instruction.strip():
            raise ValueError("Discovery Input Conversion Prompt must not be empty")

        path = self._conversion_prompt_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(
                    yaml.safe_dump(
                        {"instruction": instruction},
                        allow_unicode=True,
                        sort_keys=False,
                    )
                )
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return _read_conversion_prompt(path)

    def list_launches(self, active_context: str = "history") -> dict[str, Any]:
        return self.snapshot(active_context=active_context)

    def stop_launch(self, launch_id: str) -> dict[str, Any]:
        with self._lock:
            self._launches.stop(launch_id)
            return self.snapshot(active_context="launch")

    def resume_launch(
        self,
        launch_id: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if not idempotency_key:
            raise LaunchValidationError("Idempotency-Key is required to resume a Launch")
        if len(idempotency_key) > 256:
            raise LaunchValidationError("Idempotency-Key is too long")
        request_fingerprint = hashlib.sha256(
            json.dumps({"launch_id": launch_id}, sort_keys=True).encode("utf-8")
        ).hexdigest()
        with self._lock:
            return self._launches.resume(
                launch_id,
                request_fingerprint=request_fingerprint,
                idempotency_key=idempotency_key,
                response_builder=lambda: self.snapshot(active_context="launch"),
            )

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
        if not files and (not has_text or not text.strip()):
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

    def reset(self) -> dict[str, Any]:
        """Atomically replace the editable Preparation with an Empty Preparation."""
        with self._lock:
            empty = _empty_preparation()
            self._write_committed(empty)
            self._committed = empty
            self._draft = _copy_preparation(empty)
            self._invalidate_conversion()
            return self.snapshot()

    def convert(
        self,
        provider: Any,
        model: str,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            dirty = self._is_dirty()
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
            model_output = (getattr(turn, "text", None) or "").strip()
            if not model_output:
                raise DiscoveryConversionError(
                    "the default text model returned an empty Discovery Execution Input"
                )
            try:
                execution_input = self._parse_conversion_output(model_output)
            except ValueError as error:
                raise DiscoveryConversionError(str(error)) from error
        except DiscoverySourceContentError as error:
            self._record_conversion_failure(str(error), base_fingerprint)
            raise
        except (DiscoveryConfigurationError, DiscoveryConversionError) as error:
            self._record_conversion_failure(str(error), base_fingerprint)
            raise
        except Exception as error:
            message = "the default text model could not generate a structured Discovery Execution Input"
            self._record_conversion_failure(message, base_fingerprint)
            raise DiscoveryConversionError(message) from error

        with self._lock:
            current_fingerprint = _preparation_fingerprint(self._committed)
            dirty = self._is_dirty()
            if dirty or current_fingerprint != base_fingerprint:
                raise PreparationValidationError(
                    "the Preparation changed during Conversion; save and convert again"
                )
            self._conversion_draft = execution_input
            self._conversion_model_id = model
            self._conversion_error = None
            self._conversion_base_fingerprint = base_fingerprint
            self._conversion_saved_revision_id = None
            return self.snapshot()

    def save_revision(self, body: dict[str, Any] | None = None) -> dict[str, Any]:
        body = body or {}
        if not isinstance(body, dict):
            raise PreparationValidationError("revision payload must be an object")
        raw_execution_input = body.get("execution_input")
        if raw_execution_input is None:
            raise PreparationValidationError("Discovery Execution Input must not be empty")
        try:
            execution_input = (
                _normalize_execution_input(raw_execution_input)
                if raw_execution_input is not None
                else None
            )
        except ValueError as error:
            raise PreparationValidationError(str(error)) from error

        with self._lock:
            dirty = (
                self._draft["text"] != self._committed["text"]
                or self._draft["sources"] != self._committed["sources"]
            )
            if dirty:
                raise PreparationValidationError(
                    "save the Preparation before saving a revision"
                )
            if self._conversion_draft is None or not self._conversion_base_fingerprint:
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
                "model_id": self._conversion_model_id,
                "preparation_fingerprint": fingerprint,
            }
            if execution_input is not None:
                revision["execution_input"] = execution_input
            committed = _copy_preparation(self._committed)
            committed["revisions"].append(revision)
            self._write_committed(committed)
            self._committed = committed
            self._draft = _copy_preparation(committed)
            self._conversion_draft = execution_input
            self._conversion_error = None
            self._conversion_saved_revision_id = revision["revision_id"]
            return self.snapshot()

    @staticmethod
    def _parse_conversion_output(model_output: str) -> dict[str, Any]:
        candidate = model_output.strip()
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if lines and lines[0].lstrip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            candidate = "\n".join(lines).strip()
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as error:
            raise ValueError("Conversion must return one JSON Discovery Execution Input object") from error
        return _normalize_execution_input(payload)

    def _conversion_instruction(self) -> str:
        try:
            raw = _read_conversion_prompt(self._conversion_prompt_path)
        except (OSError, ValueError, yaml.YAMLError) as error:
            raise DiscoveryConfigurationError(
                "Discovery Input Conversion Prompt is not configured"
            ) from error
        instruction = raw.get("instruction") if isinstance(raw, dict) else None
        if not isinstance(instruction, str) or not instruction.strip():
            raise DiscoveryConfigurationError(
                "Discovery Input Conversion Prompt is not configured"
            )
        return instruction.strip()

    def _ensure_source_blob(self, source: dict[str, Any]) -> tuple[Path, bool]:
        """Persist one source by digest for private Launch worker consumption."""
        digest = source.get("sha256")
        content = source.get("content")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not isinstance(content, bytes)
        ):
            raise OSError("Discovery source manifest is invalid")
        if hashlib.sha256(content).hexdigest() != digest:
            raise OSError("Discovery source digest does not match its content")
        destination = self._source_store_root / digest
        destination_existed = destination.exists()
        try:
            if destination.is_file() and destination.stat().st_size == len(content):
                if hashlib.sha256(destination.read_bytes()).hexdigest() == digest:
                    return destination, False
        except OSError:
            pass
        self._source_store_root.mkdir(parents=True, exist_ok=True)
        temporary_path: str | None = None
        try:
            descriptor, temporary_path = tempfile.mkstemp(
                prefix=f".{digest}.", suffix=".tmp", dir=self._source_store_root
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, destination)
            temporary_path = None
        finally:
            if temporary_path is not None:
                Path(temporary_path).unlink(missing_ok=True)
        return destination, not destination_existed

    def _source_blob_is_referenced(self, digest: str) -> bool:
        """Check durable Launch manifests while the admission lock is held."""
        launches_root = self._source_store_root.parent / "launches"
        try:
            launch_dirs = list(launches_root.iterdir())
        except OSError:
            return False
        for launch_dir in launch_dirs:
            record_path = launch_dir / "record.json"
            input_path = launch_dir / "input_snapshot.json"
            if not record_path.is_file() or not input_path.is_file():
                continue
            try:
                record = json.loads(record_path.read_text(encoding="utf-8"))
                payload = json.loads(input_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(record, dict) or record.get("launch_id") != launch_dir.name:
                continue
            sources = payload.get("sources") if isinstance(payload, dict) else None
            if not isinstance(sources, list):
                continue
            if any(
                isinstance(source, dict)
                and (source.get("content_ref") == digest or source.get("sha256") == digest)
                for source in sources
            ):
                return True
        return False

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
                normalized_revision = self._normalize_persisted_revision(revision)
                if normalized_revision is not None:
                    revisions.append(normalized_revision)
            return {"text": text, "sources": sources, "revisions": revisions}
        except (KeyError, TypeError, ValueError, binascii.Error):
            return _empty_preparation()

    @staticmethod
    def _normalize_persisted_revision(revision: Any) -> dict[str, Any] | None:
        """Load only revisions that can be represented by the current backend contract.

        Older builds persisted either a Markdown ``formatted_input`` or an
        ``execution_inputs`` array. A malformed legacy revision must not invalidate the
        text and sources that were committed alongside it, so each revision is isolated
        at this boundary. A legacy array is migrated only when it contains exactly one
        valid backend Execution Input; multi-input and otherwise incompatible revisions
        are intentionally dropped rather than exposed through the current API.
        """
        if not isinstance(revision, dict):
            return None
        try:
            revision_id = revision["revision_id"]
            created_at = revision["created_at"]
            fingerprint = revision["preparation_fingerprint"]
            if not all(
                isinstance(value, str) and value.strip()
                for value in (revision_id, created_at, fingerprint)
            ):
                return None
            model_id = revision.get("model_id")
            if model_id is not None and not isinstance(model_id, str):
                return None
            normalized_revision = {
                "revision_id": revision_id,
                "created_at": created_at,
                "model_id": model_id,
                "preparation_fingerprint": fingerprint,
            }
            if "execution_input" in revision:
                normalized_revision["execution_input"] = _normalize_execution_input(
                    revision["execution_input"]
                )
            elif "execution_inputs" in revision:
                legacy_inputs = revision["execution_inputs"]
                if not isinstance(legacy_inputs, list) or len(legacy_inputs) != 1:
                    return None
                normalized_revision["execution_input"] = _normalize_execution_input(
                    legacy_inputs[0]
                )
            else:
                return None
            return normalized_revision
        except (KeyError, TypeError, ValueError):
            return None

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
            "revisions": [],
        }
        for revision in preparation.get("revisions", []):
            persisted_revision = {
                "revision_id": revision["revision_id"],
                "created_at": revision["created_at"],
                "model_id": revision.get("model_id"),
                "preparation_fingerprint": revision["preparation_fingerprint"],
            }
            if "execution_input" in revision:
                persisted_revision["execution_input"] = _public_execution_input(
                    revision["execution_input"]
                )
            payload["revisions"].append(persisted_revision)
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
