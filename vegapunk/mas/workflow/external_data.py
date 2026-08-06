"""Local-workspace and manifest contracts for external data evidence."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


MANIFEST_FILENAME = "idea_evidence_manifest.json"
CONNECTOR_ACQUISITION_FILENAME = "connector_acquisition.json"
NON_API_MARKER = "non_api"
_REQUIRED_ENTRY_FIELDS = (
    "artifact_path",
    "source",
    "api_id",
    "request",
    "retrieved_at",
)


@dataclass(frozen=True)
class ManifestValidationResult:
    """The complete admission decision for one Idea Evidence Manifest."""

    entries: list[dict[str, Any]]
    errors: list[str]

    @property
    def valid(self) -> bool:
        return not self.errors


def allocate_idea_data_workspace(
    root: str | Path,
    session_id: str,
    idea_id: str,
) -> Path:
    """Create and return one deterministic, non-shared workspace per Idea."""
    workspace = (
        Path(root).expanduser().resolve()
        / _safe_path_component(session_id)
        / _safe_path_component(idea_id)
    )
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def validate_idea_evidence_manifest(workspace: str | Path) -> ManifestValidationResult:
    """Admit only complete provenance records for real files inside *workspace*."""
    workspace_path = Path(workspace).expanduser().resolve()
    manifest_path = workspace_path / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return ManifestValidationResult([], [f"Manifest is missing: {manifest_path}"])

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return ManifestValidationResult([], [f"Manifest is unreadable: {error}"])

    artifacts = payload.get("artifacts") if isinstance(payload, Mapping) else None
    if not isinstance(artifacts, list) or not artifacts:
        return ManifestValidationResult([], ["Manifest must contain a non-empty artifacts list"])

    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, artifact in enumerate(artifacts):
        entry, entry_errors = _validate_manifest_entry(artifact, workspace_path, index)
        if entry_errors:
            errors.extend(entry_errors)
        elif entry is not None:
            entries.append(entry)

    # A malformed manifest is a failed evidence boundary, not a partially trusted
    # source. A later acquisition may rewrite a complete manifest and retry.
    if errors:
        return ManifestValidationResult([], errors)
    return ManifestValidationResult(entries, [])


def manifest_entries_as_evidence(
    entries: Sequence[Mapping[str, Any]],
    manifest_path: str | Path,
    *,
    acquired_by: str,
) -> list[dict[str, Any]]:
    """Convert validated artifact entries into the shared ``Idea.evidence`` shape."""
    return [
        {
            **dict(entry),
            "source_type": "external_data",
            "acquired_by": acquired_by,
            "manifest_path": str(Path(manifest_path).resolve()),
        }
        for entry in entries
    ]


def _validate_manifest_entry(
    artifact: Any,
    workspace: Path,
    index: int,
) -> tuple[dict[str, Any] | None, list[str]]:
    label = f"Manifest artifact {index}"
    if not isinstance(artifact, Mapping):
        return None, [f"{label} must be an object"]

    errors = [
        f"{label} is missing {field}"
        for field in _REQUIRED_ENTRY_FIELDS
        if not isinstance(artifact.get(field), str) or not artifact[field].strip()
    ]
    api_id = artifact.get("api_id")
    docs_url = artifact.get("docs_url")
    if api_id != NON_API_MARKER and (
        not isinstance(docs_url, str) or not docs_url.strip()
    ):
        errors.append(f"{label} is missing docs_url for API artifact")

    retrieved_at = artifact.get("retrieved_at")
    if isinstance(retrieved_at, str) and retrieved_at.strip():
        try:
            datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"{label} has an invalid retrieved_at timestamp")

    artifact_path = artifact.get("artifact_path")
    resolved_path: Path | None = None
    if isinstance(artifact_path, str) and artifact_path.strip():
        candidate = Path(artifact_path)
        resolved_path = (
            candidate.resolve()
            if candidate.is_absolute()
            else (workspace / candidate).resolve()
        )
        try:
            resolved_path.relative_to(workspace)
        except ValueError:
            errors.append(f"{label} path is outside the Idea workspace")
        else:
            if not resolved_path.is_file():
                errors.append(f"{label} file does not exist: {resolved_path}")

    if errors or resolved_path is None:
        return None, errors

    entry = dict(artifact)
    entry["artifact_path"] = str(resolved_path)
    entry["source"] = entry["source"].strip()
    entry["api_id"] = entry["api_id"].strip()
    entry["request"] = entry["request"].strip()
    entry["retrieved_at"] = entry["retrieved_at"].strip()
    if isinstance(entry.get("docs_url"), str):
        entry["docs_url"] = entry["docs_url"].strip()
    return entry, []


def _safe_path_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned or "unnamed"
