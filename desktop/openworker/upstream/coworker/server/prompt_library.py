"""Native sidecar facade for Vegapunk's source-backed Prompt Library."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _config_root(relative: str) -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(bundled_root) / "config" / relative
    return _repository_root() / "config" / relative


def default_prompt_roots() -> tuple[Path, Path]:
    return _config_root("prompts"), _config_root("prompt_baseline")


try:
    from vegapunk.prompt_library import (
        InvalidPromptError,
        PromptEntry,
        PromptLibrary,
        UnknownPromptError,
    )
except ModuleNotFoundError:
    # A source checkout does not install the repository root beside the editable
    # OpenWorker package. Add it only for this shared, dependency-light module.
    sys.path.insert(0, str(_repository_root()))
    from vegapunk.prompt_library import (
        InvalidPromptError,
        PromptEntry,
        PromptLibrary,
        UnknownPromptError,
    )


API_VERSION = "v1"


class PromptLibraryUnavailableError(RuntimeError):
    """The installed prompt catalog or its system-original bodies is unavailable."""


@dataclass(frozen=True)
class PromptLibraryViolation:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class DesktopPromptLibrary:
    """Expose active prompts and installed originals without leaking storage layout."""

    def __init__(self, library: PromptLibrary, baseline_root: Path) -> None:
        self._library = library
        self._baseline_root = baseline_root.resolve()

    def health(self) -> dict[str, str]:
        try:
            self._ensure_available()
        except (OSError, ValueError, KeyError, PromptLibraryUnavailableError):
            return {"api_version": API_VERSION, "status": "library_unavailable"}
        return {"api_version": API_VERSION, "status": "ready"}

    def list_catalogue(self) -> list[dict]:
        try:
            return [self._catalogue_record(entry) for entry in self._library.list()]
        except (OSError, ValueError, KeyError) as error:
            raise PromptLibraryUnavailableError("Prompt Library is unavailable") from error

    def detail(self, prompt_id: str) -> dict:
        try:
            entry = self._library.get_entry(prompt_id)
            return {
                **self._catalogue_record(entry),
                "system_original_text": self._baseline_text(entry),
            }
        except UnknownPromptError:
            raise
        except (OSError, ValueError, KeyError) as error:
            raise PromptLibraryUnavailableError("Prompt Library is unavailable") from error

    def save(self, prompt_id: str, text: str) -> dict:
        try:
            entry = self._library.save(prompt_id, text)
            return self._catalogue_record(entry)
        except (UnknownPromptError, InvalidPromptError):
            raise
        except (OSError, ValueError, KeyError) as error:
            raise PromptLibraryUnavailableError("Prompt Library is unavailable") from error

    def _ensure_available(self) -> None:
        for entry in self._library.list():
            self._library.get(entry.id)
            self._baseline_text(entry)

    def _catalogue_record(self, entry: PromptEntry) -> dict:
        active = self._library.get(entry.id)
        return {
            "id": entry.id,
            "name": entry.name,
            "description": entry.description,
            "workflow": entry.workflow,
            "stage": entry.stage,
            "order": entry.order,
            "invocation_type": entry.invocation_type,
            "mutual_exclusion_group": entry.mutual_exclusion_group,
            "template_variables": list(entry.template_variables),
            "required_template_variables": list(entry.required_template_variables),
            "text": active,
            "source_revision": self._source_revision(active),
        }

    def _baseline_text(self, entry: PromptEntry) -> str:
        path = self._baseline_root / entry.file
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            raise PromptLibraryUnavailableError(
                "The installed system-original Prompt baseline is unavailable"
            ) from error
        if not text.strip():
            raise PromptLibraryUnavailableError(
                "The installed system-original Prompt baseline is unavailable"
            )
        return text

    @staticmethod
    def _source_revision(text: str) -> str:
        import hashlib

        return hashlib.sha256(text.encode()).hexdigest()


def violation_for(error: InvalidPromptError) -> PromptLibraryViolation:
    message = str(error)
    if message.startswith("prompt text must not be empty"):
        code = "empty_prompt"
    elif message.startswith("malformed template syntax"):
        code = "malformed_template"
    elif message.startswith("required template variable"):
        code = "required_template_variable_removed"
    elif message.startswith("unknown template variable"):
        code = "unknown_template_variable"
    elif message.startswith("anonymous template variables"):
        code = "anonymous_template_variable"
    else:
        code = "invalid_template"
    return PromptLibraryViolation(code, message)


__all__ = [
    "DesktopPromptLibrary",
    "InvalidPromptError",
    "PromptLibrary",
    "PromptLibraryUnavailableError",
    "UnknownPromptError",
    "default_prompt_roots",
    "violation_for",
]
