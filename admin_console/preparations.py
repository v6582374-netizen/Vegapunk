"""Durable source material for an Autonomous Discovery preparation."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

_SUPPORTED_SOURCE_TYPES = {
    ".txt": "reference",
    ".md": "reference",
    ".pdf": "reference",
    ".docx": "reference",
    ".csv": "reference",
    ".zip": "baseline_code",
}


class InvalidPreparationError(ValueError):
    pass


class UnknownPreparationError(KeyError):
    pass


class DiscoveryPreparationStore:
    def __init__(self, results_root: Path) -> None:
        self._root = results_root / "workspace" / "discovery-preparations"

    def list(self) -> list[dict]:
        if not self._root.is_dir():
            return []
        preparations = [
            self._read(path.name)
            for path in self._root.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ]
        return sorted(preparations, key=lambda preparation: preparation["created_at"], reverse=True)

    def get(self, preparation_id: str) -> dict:
        return self._read(preparation_id)

    def create(self, research_text: str, sources: list[tuple[str, bytes]]) -> dict:
        normalized_sources = self._validate_sources(sources)
        if not research_text.strip() and not normalized_sources:
            raise InvalidPreparationError(
                "add research text or at least one supported source file"
            )

        preparation_id = uuid4().hex
        preparation_dir = self._root / preparation_id
        temporary_dir = self._root / f".{preparation_id}.tmp"
        created_at = datetime.now(UTC).isoformat()
        source_metadata = [
            {
                "name": source["name"],
                "kind": source["kind"],
                "extension": source["extension"],
            }
            for source in normalized_sources
        ]
        preparation = {
            "id": preparation_id,
            "created_at": created_at,
            "research_text": research_text,
            "sources": source_metadata,
        }

        self._root.mkdir(parents=True, exist_ok=True)
        try:
            temporary_dir.mkdir()
            sources_dir = temporary_dir / "sources"
            sources_dir.mkdir()
            for index, source in enumerate(normalized_sources, start=1):
                stored_name = f"{index:03d}{source['extension']}"
                (sources_dir / stored_name).write_bytes(source["content"])
            (temporary_dir / "preparation.json").write_text(
                json.dumps(preparation, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary_dir.replace(preparation_dir)
        except Exception:
            shutil.rmtree(temporary_dir, ignore_errors=True)
            raise
        return preparation

    def _read(self, preparation_id: str) -> dict:
        if not preparation_id or Path(preparation_id).name != preparation_id:
            raise UnknownPreparationError(preparation_id)
        document_path = self._root / preparation_id / "preparation.json"
        if not document_path.is_file():
            raise UnknownPreparationError(preparation_id)
        return json.loads(document_path.read_text(encoding="utf-8"))

    @staticmethod
    def _validate_sources(sources: list[tuple[str, bytes]]) -> list[dict]:
        normalized_sources: list[dict] = []
        for name, content in sources:
            if not name or Path(name).name != name:
                raise InvalidPreparationError("source filenames must be plain filenames")
            extension = Path(name).suffix.lower()
            kind = _SUPPORTED_SOURCE_TYPES.get(extension)
            if kind is None:
                raise InvalidPreparationError(f"unsupported source type: {name}")
            normalized_sources.append(
                {
                    "name": name,
                    "kind": kind,
                    "extension": extension,
                    "content": content,
                }
            )
        return normalized_sources
