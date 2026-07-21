"""Create a Simplified Chinese companion for a completed English Paper."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from vegapunk.mas.models.runtime import TextContent
from vegapunk.mas.models.unified_runtime import UnifiedModelRuntime

from .responses_runtime import PaperOrchestraResponsesRuntime


ENGLISH_TEX_RELATIVE_PATH = Path(
    "content_refinement_workdir/final_refined_paper.tex"
)
CHINESE_TEX_RELATIVE_PATH = Path(
    "content_refinement_workdir/final_paper.zh-CN.tex"
)
CHINESE_PDF_RELATIVE_PATH = Path("final_paper.zh-CN.pdf")

_COMPILE_JOB_NAME = "final_paper_zh_CN"
_CTEX_PACKAGE = r"\usepackage[UTF8,fontset=fandol]{ctex}"
_TRANSLATION_SYSTEM_PROMPT = r"""
You translate finalized machine-learning papers from English to Simplified
Chinese. Return exactly one complete, compilable LaTeX document and no prose or
Markdown fences.

Translate all editable manuscript prose, including the title, abstract, body,
section headings, figure captions, table text, reproducibility statements, and
appendices. Preserve the scientific meaning, claim scope, evidence boundaries,
section structure, and formatting exactly. Do not add, remove, strengthen, or
reinterpret content.

Do not translate or modify LaTeX commands, environments, labels, references,
citation keys, bibliography commands or entries, equations, inline math,
numerical values, code, URLs, file paths, or raster figure contents. Keep
bibliographic titles in their original language. Preserve established proper
names, model names, dataset names, acronyms, and identifiers when translation
would make them less precise. Preserve the existing preamble; the host program
adds Chinese typesetting support after translation.
""".strip()


def generate_chinese_companion(
    *,
    run_dir: Path,
    runtime: UnifiedModelRuntime,
    model_name: str,
) -> None:
    """Translate the final English TeX and compile its Chinese companion."""

    source_tex_path = run_dir / ENGLISH_TEX_RELATIVE_PATH
    source_tex = source_tex_path.read_text(encoding="utf-8")
    bridge = PaperOrchestraResponsesRuntime(runtime=runtime)
    response = bridge.generate_text(
        model_name=model_name,
        content=(
            TextContent(
                "Translate the following complete final LaTeX paper.\n\n"
                f"<latex_document>\n{source_tex}\n</latex_document>"
            ),
        ),
        system_prompt=_TRANSLATION_SYSTEM_PROMPT,
        temperature=None,
    )
    chinese_tex = _ensure_chinese_preamble(_extract_latex_document(response))

    chinese_tex_path = run_dir / CHINESE_TEX_RELATIVE_PATH
    chinese_tex_path.write_text(chinese_tex.rstrip() + "\n", encoding="utf-8")
    compiled_pdf = _compile_chinese_pdf(chinese_tex_path)
    shutil.copy2(compiled_pdf, run_dir / CHINESE_PDF_RELATIVE_PATH)


def _extract_latex_document(response: str) -> str:
    fenced = re.search(
        r"```(?:latex|tex)?\s*(.*?)```",
        response,
        flags=re.IGNORECASE | re.DOTALL,
    )
    candidate = fenced.group(1) if fenced else response
    start = candidate.find(r"\documentclass")
    end_marker = r"\end{document}"
    end = candidate.rfind(end_marker)
    if start < 0 or end < start:
        raise ValueError(
            "translation backend did not return a complete LaTeX document"
        )
    document_end = end + len(end_marker)
    return candidate[start:document_end].strip()


def _ensure_chinese_preamble(tex: str) -> str:
    if re.search(
        r"\\(?:documentclass|usepackage)(?:\[[^]]*\])?\{[^}]*ctex[^}]*\}",
        tex,
        flags=re.IGNORECASE,
    ):
        return tex
    document_class = re.search(
        r"\\documentclass(?:\[[^]]*\])?\{[^}]+\}[^\n]*",
        tex,
    )
    if document_class is None:
        raise ValueError("translated LaTeX is missing its document class")
    insertion_point = document_class.end()
    return "".join(
        (
            tex[:insertion_point],
            "\n",
            _CTEX_PACKAGE,
            tex[insertion_point:],
        )
    )


def _compile_chinese_pdf(tex_path: Path) -> Path:
    for executable in ("xelatex", "bibtex"):
        if shutil.which(executable) is None:
            raise RuntimeError(
                f"Chinese Paper compilation requires {executable}"
            )

    work_dir = tex_path.parent
    generated_pdf = work_dir / f"{_COMPILE_JOB_NAME}.pdf"
    generated_pdf.unlink(missing_ok=True)
    commands = [
        [
            "xelatex",
            f"-jobname={_COMPILE_JOB_NAME}",
            "-interaction=nonstopmode",
            tex_path.name,
        ]
    ]
    _run_latex_commands(commands, work_dir)

    aux_path = work_dir / f"{_COMPILE_JOB_NAME}.aux"
    if aux_path.is_file() and r"\bibdata" in aux_path.read_text(
        encoding="utf-8", errors="ignore"
    ):
        _run_latex_commands([["bibtex", _COMPILE_JOB_NAME]], work_dir)

    _run_latex_commands(commands * 2, work_dir)
    if not _valid_pdf(generated_pdf):
        raise RuntimeError(
            "XeLaTeX did not produce a complete Chinese companion PDF; "
            f"inspect {work_dir / (_COMPILE_JOB_NAME + '.log')}"
        )
    return generated_pdf


def _run_latex_commands(commands: list[list[str]], work_dir: Path) -> None:
    environment = dict(os.environ)
    for variable in (
        "TEXINPUTS",
        "TEXMFHOME",
        "TEXMF",
        "TEXMFVAR",
        "TEXMFCONFIG",
    ):
        environment.pop(variable, None)
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=work_dir,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            output = "\n".join(
                part
                for part in (completed.stdout, completed.stderr)
                if part
            ).strip()
            if len(output) > 2000:
                output = output[-2000:]
            detail = output or "no process output"
            raise RuntimeError(
                "LaTeX command failed with exit code "
                f"{completed.returncode}: {' '.join(command)}\n{detail}"
            )


def _valid_pdf(path: Path) -> bool:
    try:
        pdf = path.read_bytes()
    except OSError:
        return False
    return all(
        (
            len(pdf) > 8,
            pdf.startswith(b"%PDF-"),
            pdf.rstrip().endswith(b"%%EOF"),
        )
    )
