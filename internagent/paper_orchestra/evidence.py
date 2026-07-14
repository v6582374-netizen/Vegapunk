"""Collect citation evidence and reusable figures from a Discovery Launch."""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class PreparedEvidence:
    references: Path
    citation_map: Path
    figures_info: Path


def prepare_launch_evidence(
    *, launch_dir: Path, output_dir: Path
) -> PreparedEvidence:
    launch_root = launch_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    references, evidence_items = _collect_citation_records(launch_root)
    references_path = output_dir / "references.bib"
    citation_map_path = output_dir / "citation_map.json"
    _write_citations(
        references=references,
        evidence_items=evidence_items,
        references_path=references_path,
        citation_map_path=citation_map_path,
    )
    figures_dir = output_dir / "figures"
    figures_info_path = figures_dir / "info.json"
    _collect_figures(
        launch_root=launch_root,
        figures_dir=figures_dir,
        figures_info_path=figures_info_path,
    )
    return PreparedEvidence(
        references=references_path,
        citation_map=citation_map_path,
        figures_info=figures_info_path,
    )


def _collect_citation_records(
    launch_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    references: list[dict[str, Any]] = []
    evidence_items: list[dict[str, Any]] = []
    seen_references: set[tuple[str, str]] = set()
    seen_evidence: set[tuple[str, str, str]] = set()
    for path in sorted(launch_root.rglob("*.json")):
        if "paper_orchestra_runs" in path.parts:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for record in _records_with_citations(data):
            for reference in record.get("references", []):
                if not isinstance(reference, dict):
                    continue
                identity = (
                    _normalize_doi(reference.get("doi")),
                    _normalize_title(reference.get("title")),
                )
                if identity != ("", "") and identity not in seen_references:
                    seen_references.add(identity)
                    references.append(reference)
            for evidence in record.get("evidence", []):
                if not isinstance(evidence, dict):
                    continue
                identity = (
                    _normalize_doi(evidence.get("doi")),
                    _normalize_title(evidence.get("title")),
                    _evidence_content(evidence),
                )
                if identity[2] and identity not in seen_evidence:
                    seen_evidence.add(identity)
                    evidence_items.append(evidence)
    return references, evidence_items


def _records_with_citations(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if isinstance(value.get("references"), list) or isinstance(
            value.get("evidence"), list
        ):
            yield value
        for child in value.values():
            yield from _records_with_citations(child)
    elif isinstance(value, list):
        for child in value:
            yield from _records_with_citations(child)


def _write_citations(
    *,
    references: list[dict[str, Any]],
    evidence_items: list[dict[str, Any]],
    references_path: Path,
    citation_map_path: Path,
) -> None:
    evidence_by_doi: dict[str, list[dict[str, Any]]] = {}
    evidence_by_title: dict[str, list[dict[str, Any]]] = {}
    for evidence in evidence_items:
        doi = _normalize_doi(evidence.get("doi"))
        title = _normalize_title(evidence.get("title"))
        if doi:
            evidence_by_doi.setdefault(doi, []).append(evidence)
        if title:
            evidence_by_title.setdefault(title, []).append(evidence)

    citation_map: dict[str, dict[str, Any]] = {}
    bib_entries: list[str] = []
    for reference in references:
        doi = _normalize_doi(reference.get("doi"))
        title = _normalize_title(reference.get("title"))
        matches = evidence_by_doi.get(doi, []) if doi else evidence_by_title.get(title, [])
        if len(matches) != 1:
            continue
        key = f"ref{len(citation_map) + 1:03d}"
        authors = _reference_authors(reference.get("authors"))
        venue = reference.get("journal") or reference.get("venue") or ""
        citation_map[key] = {
            "citation_key": key,
            "title": reference.get("title", ""),
            "authors": authors,
            "venue": venue,
            "year": reference.get("year"),
            "abstract": _evidence_content(matches[0]),
            "doi": reference.get("doi"),
            "url": reference.get("url"),
        }
        bib_entries.append(_bib_entry(key, reference, authors, venue))
    citation_map_path.write_text(
        json.dumps(citation_map, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    bibliography = "\n\n".join(bib_entries)
    references_path.write_text(
        bibliography + ("\n" if bibliography else "% No approved references.\n"),
        encoding="utf-8",
    )


def _collect_figures(
    *, launch_root: Path, figures_dir: Path, figures_info_path: Path
) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)
    figures: list[dict[str, str]] = []
    copied: set[Path] = set()
    for report_path in sorted(launch_root.rglob("report.md")):
        if "paper_orchestra_runs" in report_path.parts:
            continue
        try:
            report = report_path.read_text(encoding="utf-8")
        except OSError:
            continue
        for caption, raw_reference in re.findall(
            r"!\[([^\]]*)\]\(([^)\s]+)\)", report
        ):
            source = (report_path.parent / raw_reference.strip("<>")).resolve()
            if (
                source in copied
                or not source.is_file()
                or not source.is_relative_to(launch_root)
            ):
                continue
            copied.add(source)
            relative = source.relative_to(launch_root)
            name = "__".join(relative.parts)
            shutil.copy2(source, figures_dir / name)
            figures.append(
                {
                    "name": name,
                    "caption": caption or source.name,
                    "source": relative.as_posix(),
                }
            )
    figures_info_path.write_text(
        json.dumps(figures, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _normalize_doi(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip().casefold()
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "http://dx.doi.org/",
        "doi:",
    ):
        if normalized.startswith(prefix):
            return normalized[len(prefix) :].strip()
    return normalized


def _normalize_title(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _evidence_content(evidence: dict[str, Any]) -> str:
    for key in ("content", "abstract"):
        value = evidence.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _reference_authors(value: Any) -> list[str]:
    if isinstance(value, list):
        return [author for author in value if isinstance(author, str) and author]
    if isinstance(value, str) and value:
        return [value]
    return []


def _bib_entry(
    key: str, reference: dict[str, Any], authors: list[str], venue: Any
) -> str:
    entry_type = "article" if venue else "misc"
    fields: list[tuple[str, Any]] = [
        ("title", reference.get("title")),
        ("author", " and ".join(authors)),
        ("year", reference.get("year")),
    ]
    if venue:
        fields.append(("journal", venue))
    fields.extend((("doi", reference.get("doi")), ("url", reference.get("url"))))
    rendered = [
        f"  {name} = {{{value}}}"
        for name, value in fields
        if value is not None and str(value).strip()
    ]
    return f"@{entry_type}{{{key},\n" + ",\n".join(rendered) + "\n}"
