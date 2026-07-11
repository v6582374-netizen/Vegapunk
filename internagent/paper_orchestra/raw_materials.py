from __future__ import annotations

import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any

from .data_types import DossierStageError, LinkedArtifacts
from .utils.experiment_runs import find_current_valid_run


RAW_MATERIAL_PATHS = {
    "idea": Path("idea.md"),
    "experimental_log": Path("experimental_log.md"),
    "citation_map": Path("citation_map.json"),
    "references": Path("references.bib"),
    "figures_info": Path("figures/info.json"),
}
RAW_MATERIAL_CHECKPOINT_OUTPUTS = tuple(
    (Path("raw_materials") / path).as_posix()
    for path in RAW_MATERIAL_PATHS.values()
)


def prepare_raw_materials(
    *, linked: LinkedArtifacts, output_dir: Path
) -> Path:
    """Render authoritative experiment artifacts into PaperOrchestra inputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    idea_markdown = _render_idea_markdown(
        method=linked.selected_method,
        idea=linked.full_idea,
    )
    (output_dir / RAW_MATERIAL_PATHS["idea"]).write_text(
        idea_markdown, encoding="utf-8"
    )
    experimental_log = _render_experimental_log(linked.candidate_dir)
    (output_dir / RAW_MATERIAL_PATHS["experimental_log"]).write_text(
        experimental_log, encoding="utf-8"
    )
    _prepare_figures(linked.candidate_dir, output_dir / "figures")
    _prepare_citations(linked.full_idea, output_dir)
    validate_raw_materials(output_dir)
    return output_dir


def validate_raw_materials(output_dir: Path) -> None:
    """Validate the deterministic Dossier inputs, including dynamic figures."""
    for relative_path in RAW_MATERIAL_PATHS.values():
        path = output_dir / relative_path
        if not path.is_file() or path.stat().st_size == 0:
            _raw_fail(f"raw material is missing or empty: {relative_path}")

    try:
        citation_map = json.loads(
            (output_dir / RAW_MATERIAL_PATHS["citation_map"]).read_text(
                encoding="utf-8"
            )
        )
        figures_info = json.loads(
            (output_dir / RAW_MATERIAL_PATHS["figures_info"]).read_text(
                encoding="utf-8"
            )
        )
    except (FileNotFoundError, json.JSONDecodeError, OSError) as error:
        _raw_fail(f"cannot read raw-material index: {error}")
    if not isinstance(citation_map, dict) or not isinstance(figures_info, list):
        _raw_fail("citation_map.json and figures/info.json have invalid shapes")
    for figure in figures_info:
        name = figure.get("name") if isinstance(figure, dict) else None
        if (
            not isinstance(name, str)
            or not name
            or Path(name).name != name
            or not (output_dir / "figures" / name).is_file()
            or (output_dir / "figures" / name).stat().st_size == 0
        ):
            _raw_fail(f"registered figure is missing or invalid: {name!r}")


def _render_idea_markdown(
    *, method: dict[str, Any], idea: dict[str, Any]
) -> str:
    title = method.get("title")
    method_name = method.get("name")
    method_details = method.get("method")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (title, method_name, method_details)
    ):
        raise DossierStageError(
            stage="prepare_raw_materials",
            code="raw_material_render_failed",
            message="selected method must contain non-empty title, name, and method",
        )

    sections = [
        ("Method name", method_name),
        ("Research hypothesis", idea.get("text")),
        ("Motivation", idea.get("rationale")),
        ("Baseline context", idea.get("baseline_summary")),
        ("Method overview", method.get("description")),
        ("Novelty/theory", method.get("statement")),
        ("Method details", method_details),
    ]
    blocks = [f"# {title}"]
    blocks.extend(
        f"## {heading}\n\n{value}"
        for heading, value in sections
        if isinstance(value, str) and value.strip()
    )
    return "\n\n".join(blocks) + "\n"


def _render_experimental_log(candidate_dir: Path) -> str:
    numbered_runs: list[tuple[int, Path]] = []
    for child in candidate_dir.iterdir():
        match = re.fullmatch(r"run_(\d+)", child.name)
        if child.is_dir() and match:
            numbered_runs.append((int(match.group(1)), child))

    blocks = ["# Experimental log"]
    for run_number, run_dir in sorted(numbered_runs):
        final_info_path = run_dir / "final_info.json"
        report_path = run_dir / "report" / "report.md"
        traceback_path = run_dir / "traceback.log"
        final_info = (
            final_info_path.read_text(encoding="utf-8")
            if final_info_path.is_file()
            else ""
        )
        if run_number == 0:
            status = "baseline"
        elif traceback_path.is_file():
            status = "failed"
        elif final_info.strip():
            status = "successful"
        else:
            status = "no metrics produced"

        run_blocks = [
            f"## Run {run_number}",
            f"- ID: {run_dir.name}\n"
            f"- Relative path: {run_dir.name}\n"
            f"- Structure status: {status}",
        ]
        if final_info:
            run_blocks.append(
                "### final_info.json\n\n```json\n" + final_info + "```"
            )
        if report_path.is_file():
            report = report_path.read_text(encoding="utf-8")
            run_blocks.append("### report/report.md\n\n" + report.rstrip("\n"))
        if traceback_path.is_file():
            run_blocks.append(f"- Traceback: {run_dir.name}/traceback.log")
        blocks.append("\n\n".join(run_blocks))

    return "\n\n".join(blocks) + "\n"


def _prepare_figures(candidate_dir: Path, figures_dir: Path) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)
    figures_info: list[dict[str, str]] = []
    current_run = find_current_valid_run(candidate_dir)
    if current_run is not None:
        report_dir = current_run.path / "report"
        report_path = report_dir / "report.md"
        images_root = (report_dir / "images").resolve()
        if report_path.is_file():
            report = report_path.read_text(encoding="utf-8")
            references = re.findall(r"!\[([^\]]*)\]\(([^)\s]+)\)", report)
            copied_sources: set[Path] = set()
            copied_names: set[str] = set()
            for alt_text, raw_reference in references:
                reference = raw_reference.strip("<>")
                source = (report_dir / reference).resolve()
                if (
                    not source.is_relative_to(images_root)
                    or not source.is_file()
                ):
                    _raw_fail(
                        f"referenced figure must exist inside report/images: {reference}"
                    )
                if source in copied_sources:
                    continue
                if source.name in copied_names:
                    _raw_fail(f"referenced figures have duplicate filename: {source.name}")
                copied_sources.add(source)
                copied_names.add(source.name)
                shutil.copy2(source, figures_dir / source.name)
                figures_info.append(
                    {
                        "name": source.name,
                        "caption": alt_text or source.name,
                        "source": (
                            f"{current_run.path.name}/report/images/"
                            f"{source.relative_to(images_root).as_posix()}"
                        ),
                    }
                )
    (figures_dir / RAW_MATERIAL_PATHS["figures_info"].name).write_text(
        json.dumps(figures_info, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _raw_fail(message: str) -> None:
    raise DossierStageError(
        stage="prepare_raw_materials",
        code="raw_material_render_failed",
        message=message,
    )


def _prepare_citations(idea: dict[str, Any], output_dir: Path) -> None:
    references = idea.get("references")
    evidence_items = idea.get("evidence")
    references = references if isinstance(references, list) else []
    evidence_items = evidence_items if isinstance(evidence_items, list) else []

    evidence_by_doi: dict[str, list[dict[str, Any]]] = {}
    evidence_by_title: dict[str, list[dict[str, Any]]] = {}
    for evidence in evidence_items:
        if not isinstance(evidence, dict) or not _evidence_content(evidence):
            continue
        doi = _normalize_doi(evidence.get("doi"))
        title = _normalize_title(evidence.get("title"))
        if doi:
            evidence_by_doi.setdefault(doi, []).append(evidence)
        if title:
            evidence_by_title.setdefault(title, []).append(evidence)

    citation_map: dict[str, dict[str, Any]] = {}
    bib_entries: list[str] = []
    for reference in references:
        if not isinstance(reference, dict):
            continue
        doi = _normalize_doi(reference.get("doi"))
        title = _normalize_title(reference.get("title"))
        if doi:
            evidence_matches = evidence_by_doi.get(doi, [])
            match_type = "doi"
            match_value = doi
        else:
            evidence_matches = evidence_by_title.get(title, []) if title else []
            match_type = "title"
            match_value = title
        if len(evidence_matches) != 1:
            continue

        citation_key = f"ref{len(citation_map) + 1:03d}"
        evidence = evidence_matches[0]
        authors = _reference_authors(reference.get("authors"))
        venue = reference.get("journal") or reference.get("venue") or ""
        citation_map[citation_key] = {
            "citation_key": citation_key,
            "title": reference.get("title", ""),
            "authors": authors,
            "venue": venue,
            "year": reference.get("year"),
            "abstract": _evidence_content(evidence),
            "doi": reference.get("doi"),
            "url": reference.get("url"),
            "match": {"type": match_type, "value": match_value},
        }
        bib_entries.append(_bib_entry(citation_key, reference, authors, venue))

    (output_dir / RAW_MATERIAL_PATHS["citation_map"]).write_text(
        json.dumps(citation_map, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    bibliography = "\n\n".join(bib_entries)
    if bibliography:
        bibliography += "\n"
    else:
        bibliography = "% No approved references.\n"
    (output_dir / RAW_MATERIAL_PATHS["references"]).write_text(
        bibliography, encoding="utf-8"
    )


def _normalize_doi(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return normalized.strip()


def _normalize_title(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def _evidence_content(evidence: dict[str, Any]) -> str:
    for field in ("content", "abstract"):
        value = evidence.get(field)
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
    citation_key: str,
    reference: dict[str, Any],
    authors: list[str],
    venue: Any,
) -> str:
    entry_type = "article" if venue else "misc"
    fields: list[tuple[str, Any]] = [
        ("title", reference.get("title")),
        ("author", " and ".join(authors)),
        ("year", reference.get("year")),
    ]
    if venue:
        fields.append(("journal", venue))
    fields.extend(
        (("doi", reference.get("doi")), ("url", reference.get("url")))
    )
    rendered_fields = [
        f"  {name} = {{{value}}}"
        for name, value in fields
        if value is not None and str(value).strip()
    ]
    return f"@{entry_type}{{{citation_key},\n" + ",\n".join(rendered_fields) + "\n}"
