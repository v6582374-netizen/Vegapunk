"""Prompt Library: disk-backed registry of every editable prompt text.

The catalog at ``config/prompts/catalog.yaml`` is the index; each entry
points at a text file under ``config/prompts/``. Chinese Prompt Mirrors live
alongside, but outside, the Prompt Library root so a Discovery Launch copies
only runtime English sources into its Launch Configuration Snapshot (ADR-0157).
Callers never hardcode prompt bodies.

Access:

    from vegapunk.prompt_library import prompts
    text = prompts.get("discovery.generation.system")
    text = prompts.render("experiment.coder_openhands", idea_description=...)

Override the root for tests or for a Launch snapshot via
``PromptLibrary.use(root)`` / ``configure_prompt_root(...)``.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from tempfile import NamedTemporaryFile
from typing import Iterator

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LIBRARY_ROOT = REPOSITORY_ROOT / "config" / "prompts"
CATALOG_NAME = "catalog.yaml"
ENV_LIBRARY_ROOT = "VEGAPUNK_PROMPT_LIBRARY_ROOT"
TEMPLATE_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:[.\[].*)?$")
MIRROR_FIELD_REFERENCE = re.compile(r"\{([^{}]*)\}")


@dataclass(frozen=True)
class PromptEntry:
    id: str
    name: str
    description: str
    workflow: str
    stage: str
    order: int
    invocation_type: str
    mutual_exclusion_group: str | None
    template_variables: tuple[str, ...]
    required_template_variables: tuple[str, ...]
    file: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "workflow": self.workflow,
            "stage": self.stage,
            "order": self.order,
            "invocation_type": self.invocation_type,
            "mutual_exclusion_group": self.mutual_exclusion_group,
            "template_variables": list(self.template_variables),
            "required_template_variables": list(self.required_template_variables),
            "file": self.file,
        }


@dataclass(frozen=True)
class ChinesePromptMirror:
    state: str
    file: str
    text: str | None

    def to_dict(self) -> dict:
        return {"state": self.state, "file": self.file, "text": self.text}


class UnknownPromptError(KeyError):
    pass


class InvalidPromptError(ValueError):
    pass


class PromptSourceChangedError(InvalidPromptError):
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
                workflow=item["workflow"],
                stage=item["stage"],
                order=item["order"],
                invocation_type=item["invocation_type"],
                mutual_exclusion_group=item["mutual_exclusion_group"],
                template_variables=tuple(item["template_variables"]),
                required_template_variables=tuple(item["required_template_variables"]),
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
        return sorted(
            self._catalog().values(),
            key=lambda entry: (entry.workflow, entry.stage, entry.order, entry.id),
        )

    def stages(self) -> list[str]:
        return sorted({entry.stage for entry in self._catalog().values()})

    def get_entry(self, prompt_id: str) -> PromptEntry:
        try:
            return self._catalog()[prompt_id]
        except KeyError as error:
            raise UnknownPromptError(prompt_id) from error

    def get(self, prompt_id: str) -> str:
        with self._lock:
            entry = self.get_entry(prompt_id)
            path = self._root / entry.file
            return path.read_text(encoding="utf-8")

    def describe(self, prompt_id: str) -> dict:
        with self._lock:
            entry = self.get_entry(prompt_id)
            text = self.get(prompt_id)
            return {
                **entry.to_dict(),
                "text": text,
                "source_revision": _source_revision(text),
                "chinese_mirror": self._chinese_mirror(entry, text).to_dict(),
            }

    def render(self, prompt_id: str, **kwargs: object) -> str:
        return self.get(prompt_id).format(**kwargs)

    def save(self, prompt_id: str, text: str) -> PromptEntry:
        with self._lock:
            entry = self.get_entry(prompt_id)
            self._validate_text(entry, text)
            path = self._root / entry.file
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path: Path | None = None
            try:
                with NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=path.parent,
                    prefix=f".{path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as temporary:
                    temporary.write(text)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                    temporary_path = Path(temporary.name)
                os.replace(temporary_path, path)
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
        return entry

    def save_chinese_mirror(
        self,
        prompt_id: str,
        text: str,
        *,
        source_revision: str,
    ) -> ChinesePromptMirror:
        """Persist a validated Chinese sidecar for the observed English source."""

        entry = self.get_entry(prompt_id)
        with self._lock:
            source_text = self.get(prompt_id)
            if _source_revision(source_text) != source_revision:
                raise PromptSourceChangedError(
                    f"English source changed while translating {prompt_id!r}"
                )
            self._validate_mirror_text(entry, text, source_text)
            relative_path, path = self._chinese_mirror_path(entry)
            path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
                mode="w",
                encoding="utf-8",
            ) as temporary:
                temporary_path = Path(temporary.name)
                yaml.safe_dump(
                    {"source_revision": source_revision, "text": text},
                    temporary,
                    allow_unicode=True,
                    sort_keys=False,
                )
                temporary.flush()
                os.fsync(temporary.fileno())
            try:
                os.replace(temporary_path, path)
            finally:
                temporary_path.unlink(missing_ok=True)
        return ChinesePromptMirror("ready", relative_path.as_posix(), text)

    def validate_chinese_mirror_draft(
        self,
        prompt_id: str,
        text: str,
        *,
        source_revision: str,
    ) -> tuple[PromptEntry, str]:
        """Validate a local Chinese draft against its observed English source."""

        entry = self.get_entry(prompt_id)
        with self._lock:
            source_text = self.get(prompt_id)
            if _source_revision(source_text) != source_revision:
                raise PromptSourceChangedError(
                    f"English source changed while editing {prompt_id!r}"
                )
            self._validate_mirror_text(entry, text, source_text)
            return entry, source_text

    def synchronize_chinese_mirror(
        self,
        prompt_id: str,
        chinese_text: str,
        english_text: str,
        *,
        source_revision: str,
    ) -> PromptEntry:
        """Commit an English prompt and its Chinese mirror with rollback on failure."""

        entry = self.get_entry(prompt_id)
        with self._lock:
            source_text = self.get(prompt_id)
            if _source_revision(source_text) != source_revision:
                raise PromptSourceChangedError(
                    f"English source changed while synchronizing {prompt_id!r}"
                )
            self._validate_mirror_text(entry, chinese_text, source_text)
            self._validate_mirror_text(entry, english_text, source_text)
            english_path = self._root / entry.file
            _, mirror_path = self._chinese_mirror_path(entry)
            mirror_path.parent.mkdir(parents=True, exist_ok=True)
            english_temporary = self._write_temporary(english_path, english_text)
            mirror_temporary = self._write_temporary(
                mirror_path,
                yaml.safe_dump(
                    {
                        "source_revision": _source_revision(english_text),
                        "text": chinese_text,
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
            )
            originals = {
                english_path: english_path.read_bytes() if english_path.exists() else None,
                mirror_path: mirror_path.read_bytes() if mirror_path.exists() else None,
            }
            try:
                os.replace(english_temporary, english_path)
                os.replace(mirror_temporary, mirror_path)
            except Exception:
                self._restore_path(english_path, originals[english_path])
                self._restore_path(mirror_path, originals[mirror_path])
                raise
            finally:
                english_temporary.unlink(missing_ok=True)
                mirror_temporary.unlink(missing_ok=True)
            return entry

    def _chinese_mirror(
        self, entry: PromptEntry, source_text: str
    ) -> ChinesePromptMirror:
        relative_path, path = self._chinese_mirror_path(entry)
        if not path.exists():
            return ChinesePromptMirror("missing", relative_path.as_posix(), None)

        values = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        mirror_text = values.get("text") if isinstance(values, dict) else None
        source_revision = (
            values.get("source_revision") if isinstance(values, dict) else None
        )
        if not isinstance(mirror_text, str) or not mirror_text.strip():
            return ChinesePromptMirror("missing", relative_path.as_posix(), None)
        if source_revision != _source_revision(source_text):
            return ChinesePromptMirror("stale", relative_path.as_posix(), None)
        return ChinesePromptMirror("ready", relative_path.as_posix(), mirror_text)

    def _chinese_mirror_path(self, entry: PromptEntry) -> tuple[Path, Path]:
        relative_path = Path("prompt_localizations") / "zh-CN" / Path(
            *entry.id.split(".")
        ).with_suffix(".yaml")
        return relative_path, self._root.parent / relative_path

    @staticmethod
    def _write_temporary(path: Path, content: str | bytes) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = content.encode("utf-8") if isinstance(content, str) else content
        with NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
            mode="wb",
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        return temporary_path

    @classmethod
    def _restore_path(cls, path: Path, original: bytes | None) -> None:
        if original is None:
            path.unlink(missing_ok=True)
            return
        temporary_path = cls._write_temporary(path, original)
        try:
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _validate_text(entry: PromptEntry, text: str) -> None:
        if not text.strip():
            raise InvalidPromptError("prompt text must not be empty")

        fields: set[str] = set()
        try:
            for _, field_name, format_spec, _ in Formatter().parse(text):
                if field_name is not None:
                    if not field_name:
                        raise InvalidPromptError(
                            "anonymous template variables are not supported"
                        )
                    if not TEMPLATE_FIELD_PATTERN.fullmatch(field_name):
                        raise InvalidPromptError(
                            f"invalid template variable: {field_name}"
                        )
                    fields.add(field_name.split(".", 1)[0].split("[", 1)[0])
                if format_spec:
                    for _, nested_name, _, _ in Formatter().parse(format_spec):
                        if nested_name is None:
                            continue
                        if not nested_name:
                            raise InvalidPromptError(
                                "anonymous template variables are not supported"
                            )
                        if not TEMPLATE_FIELD_PATTERN.fullmatch(nested_name):
                            raise InvalidPromptError(
                                f"invalid template variable: {nested_name}"
                            )
                        fields.add(
                            nested_name.split(".", 1)[0].split("[", 1)[0]
                        )
        except ValueError as error:
            raise InvalidPromptError(f"malformed template syntax: {error}") from error

        allowed = set(entry.template_variables)
        unknown = sorted(fields - allowed)
        if unknown:
            raise InvalidPromptError(
                f"unknown template variable(s): {', '.join(unknown)}"
            )

        missing = sorted(set(entry.required_template_variables) - fields)
        if missing:
            raise InvalidPromptError(
                f"required template variable(s) removed: {', '.join(missing)}"
            )

    @classmethod
    def _validate_mirror_text(
        cls,
        entry: PromptEntry,
        text: str,
        source_text: str,
    ) -> None:
        """Apply the contract without rejecting legacy literal JSON in sources."""

        try:
            cls._validate_text(entry, text)
            return
        except InvalidPromptError as target_error:
            try:
                cls._validate_text(entry, source_text)
            except InvalidPromptError:
                cls._validate_legacy_mirror_text(entry, text)
                return
            raise target_error

    @staticmethod
    def _validate_legacy_mirror_text(entry: PromptEntry, text: str) -> None:
        if not text.strip():
            raise InvalidPromptError("prompt text must not be empty")
        if text.count("{") != text.count("}"):
            raise InvalidPromptError("malformed template syntax: unbalanced braces")

        fields: set[str] = set()
        for match in MIRROR_FIELD_REFERENCE.finditer(text):
            field = match.group(1).strip()
            if not field or not re.match(r"^[A-Za-z_]", field):
                continue
            if not TEMPLATE_FIELD_PATTERN.fullmatch(field):
                raise InvalidPromptError(f"invalid template variable: {field}")
            fields.add(field.split(".", 1)[0].split("[", 1)[0])

        allowed = set(entry.template_variables)
        unknown = sorted(fields - allowed)
        if unknown:
            raise InvalidPromptError(
                f"unknown template variable(s): {', '.join(unknown)}"
            )
        missing = sorted(set(entry.required_template_variables) - fields)
        if missing:
            raise InvalidPromptError(
                f"required template variable(s) removed: {', '.join(missing)}"
            )

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


def _source_revision(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()
