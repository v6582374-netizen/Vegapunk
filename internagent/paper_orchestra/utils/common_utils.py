from __future__ import annotations

import hashlib
import re


def validate_citation_keys(latex: str, approved_keys: set[str]) -> None:
    used_keys: set[str] = set()
    for match in re.finditer(r"\\cite(?:\[[^\]]*\])?\{([^}]*)\}", latex):
        used_keys.update(key.strip() for key in match.group(1).split(",") if key.strip())
    unknown = sorted(used_keys - approved_keys)
    if unknown:
        raise ValueError(f"LaTeX contains unapproved citation keys: {', '.join(unknown)}")


def validate_narrative_contract(
    latex: str, paper_title: str, paper_date: str | None = None
) -> None:
    if "\\documentclass" not in latex or "\\begin{document}" not in latex:
        raise ValueError("model output is not a complete LaTeX document")
    if "\\begin{abstract}" not in latex or "\\end{abstract}" not in latex:
        raise ValueError("Paper must contain an abstract")
    title_match = re.search(r"\\title\{([^{}]*)\}", latex)
    if title_match is None or title_match.group(1) != paper_title:
        raise ValueError("Paper title differs from the planned title")
    for command in ("author", "institute"):
        match = re.search(rf"\\{command}\{{([^{{}}]*)\}}", latex)
        if match is None or match.group(1).strip():
            raise ValueError(f"Paper {command} must remain empty")
    if paper_date is not None:
        date_match = re.search(r"\\date\{([^{}]*)\}", latex)
        if date_match is None or date_match.group(1) != paper_date:
            raise ValueError("Paper date differs from PaperOrchestra Run creation date")
    sections = tuple(re.findall(r"\\section\*?\{([^{}]+)\}", latex))
    if not sections or any(not section.strip() for section in sections):
        raise ValueError("Paper must contain non-empty top-level sections")


def scientific_content_fingerprint(latex: str) -> str:
    """Fingerprint visible/scientific LaTeX content while ignoring layout commands."""
    normalized = re.sub(r"(?<!\\)%.*", "", latex)
    normalized = re.sub(
        r"\\(?:vspace|hspace|setlength|addtolength|fontsize|linespread)\*?"
        r"(?:\[[^\]]*\])?(?:\{[^{}]*\}){1,2}",
        "",
        normalized,
    )
    normalized = re.sub(
        r"(\\includegraphics)\*?\[[^\]]*\]",
        r"\1",
        normalized,
    )
    normalized = re.sub(
        r"(\\begin\{(?:figure|table)\})\[[^\]]*\]",
        r"\1",
        normalized,
    )
    formatting_wrappers = (
        "textbf|textit|texttt|textrm|textsf|textnormal|emph|underline|"
        "mathbf|mathit|mathrm|mathsf|mathnormal"
    )
    wrapper_pattern = re.compile(rf"\\(?:{formatting_wrappers})\{{([^{{}}]*)\}}")
    while wrapper_pattern.search(normalized):
        normalized = wrapper_pattern.sub(r"\1", normalized)
    normalized = re.sub(
        r"\\(?:small|footnotesize|scriptsize|tiny|normalsize|large|Large|"
        r"LARGE|huge|Huge)\b",
        "",
        normalized,
    )
    normalized = re.sub(
        r"\\(?:quad|qquad|smallskip|medskip|bigskip|noindent|centering|"
        r"raggedright|raggedleft|clearpage|newpage|pagebreak)\b",
        "",
        normalized,
    )
    normalized = re.sub(r"\\(?:[,;:! ]|\\)", "", normalized)
    normalized = re.sub(r"\\([%&#_$])", r"\1", normalized)
    normalized = normalized.replace("~", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
