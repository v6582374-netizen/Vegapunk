"""Prompt Library: disk-backed registry of every editable prompt text.

The catalog at ``config/prompts/catalog.yaml`` is the index; each entry
points at a text file under ``config/prompts/``. A Discovery Launch copies
the whole tree into its Launch Configuration Snapshot and runtime reads
only that copy (ADR-0157). Callers never hardcode prompt bodies.

Access:

    from vegapunk.prompt_library import prompts
    text = prompts.get("discovery.generation.system")
    text = prompts.render("experiment.coder_openhands", idea_description=...)

Override the root for tests or for a Launch snapshot via
``PromptLibrary.use(root)`` / ``configure_prompt_root(...)``.
"""

from __future__ import annotations

import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LIBRARY_ROOT = REPOSITORY_ROOT / "config" / "prompts"
CATALOG_NAME = "catalog.yaml"
ENV_LIBRARY_ROOT = "VEGAPUNK_PROMPT_LIBRARY_ROOT"


@dataclass(frozen=True)
class PromptEntry:
    id: str
    name: str
    description: str
    stage: str
    file: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "stage": self.stage,
            "file": self.file,
        }


class UnknownPromptError(KeyError):
    pass


class PromptLibrary:
    """Thread-safe reader/writer over one Prompt Library root."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = (root or DEFAULT_LIBRARY_ROOT).resolve()
        self._lock = threading.RLock()
        self._entries: dict[str, PromptEntry] | None = None

    @property
    def root(self) -> Path:
        return self._root

    def reload(self) -> None:
        with self._lock:
            self._entries = None

    def _load_catalog(self) -> dict[str, PromptEntry]:
        catalog_path = self._root / CATALOG_NAME
        payload = yaml.safe_load(catalog_path.read_text()) or {}
        entries: dict[str, PromptEntry] = {}
        for item in payload.get("prompts", []):
            entry = PromptEntry(
                id=item["id"],
                name=item["name"],
                description=item.get("description", ""),
                stage=item["stage"],
                file=item["file"],
            )
            entries[entry.id] = entry
        return entries

    def _catalog(self) -> dict[str, PromptEntry]:
        with self._lock:
            if self._entries is None:
                self._entries = self._load_catalog()
            return self._entries

    def list(self) -> list[PromptEntry]:
        return sorted(self._catalog().values(), key=lambda e: (e.stage, e.id))

    def stages(self) -> list[str]:
        return sorted({entry.stage for entry in self._catalog().values()})

    def get_entry(self, prompt_id: str) -> PromptEntry:
        try:
            return self._catalog()[prompt_id]
        except KeyError as error:
            raise UnknownPromptError(prompt_id) from error

    def get(self, prompt_id: str) -> str:
        entry = self.get_entry(prompt_id)
        path = self._root / entry.file
        return path.read_text(encoding="utf-8")

    def render(self, prompt_id: str, **kwargs: object) -> str:
        return self.get(prompt_id).format(**kwargs)

    def save(self, prompt_id: str, text: str) -> PromptEntry:
        entry = self.get_entry(prompt_id)
        path = self._root / entry.file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        with self._lock:
            # Text is already on disk; catalog metadata unchanged.
            pass
        return entry

    def copy_to(self, destination: Path) -> None:
        """Copy the entire library tree into ``destination`` (for snapshots)."""
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(self._root, destination)

    def use(self, root: Path) -> "PromptLibrary":
        """Point this instance at another root and drop the cached catalog."""
        with self._lock:
            self._root = root.resolve()
            self._entries = None
        return self


_process_library: PromptLibrary | None = None
_process_lock = threading.Lock()


def get_prompt_library() -> PromptLibrary:
    """Return the process-wide Prompt Library (env override wins)."""
    global _process_library
    with _process_lock:
        if _process_library is None:
            env_root = os.environ.get(ENV_LIBRARY_ROOT)
            root = Path(env_root) if env_root else DEFAULT_LIBRARY_ROOT
            _process_library = PromptLibrary(root)
        return _process_library


def configure_prompt_root(root: Path | None) -> PromptLibrary:
    """Replace the process-wide library root (used by Launch snapshots / tests)."""
    global _process_library
    with _process_lock:
        _process_library = PromptLibrary(root or DEFAULT_LIBRARY_ROOT)
        return _process_library


# Convenience facade used by migrated call sites.
class _PromptsFacade:
    def get(self, prompt_id: str) -> str:
        return get_prompt_library().get(prompt_id)

    def render(self, prompt_id: str, **kwargs: object) -> str:
        return get_prompt_library().render(prompt_id, **kwargs)

    def list(self) -> list[PromptEntry]:
        return get_prompt_library().list()


prompts = _PromptsFacade()
