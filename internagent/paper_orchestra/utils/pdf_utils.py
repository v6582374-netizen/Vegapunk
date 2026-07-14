"""PDF utilities adapted from PaperOrchestra for XeLaTeX/Biber and local review."""

from __future__ import annotations

import shutil
import subprocess
import os
from pathlib import Path

from ..data_types import PaperOrchestraStageError


REQUIRED_TEX_BINARIES = ("latexmk", "xelatex", "biber")


def preflight_tex_toolchain() -> None:
    missing = [name for name in REQUIRED_TEX_BINARIES if shutil.which(name) is None]
    if missing:
        raise PaperOrchestraStageError(
            stage="prepare_latex_workspace",
            code="missing_tex_toolchain",
            message=f"missing required executable(s): {', '.join(missing)}",
        )


def compile_latex(
    *,
    work_dir: Path,
    tex_path: Path,
    output_pdf: Path,
    log_path: Path,
    stage: str,
    timeout: int,
    template_dir: Path | None = None,
) -> Path:
    preflight_tex_toolchain()
    work_root = work_dir.resolve()
    source = tex_path.resolve()
    if not source.is_relative_to(work_root) or not source.is_file():
        raise PaperOrchestraStageError(
            stage=stage,
            code="latex_compile_failed",
            message="LaTeX source must exist inside its writing workspace",
            log_path=str(log_path),
        )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "latexmk",
        "-pdfxe",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        source.name,
    ]
    try:
        environment = os.environ.copy()
        if template_dir is not None:
            existing_texinputs = environment.get("TEXINPUTS", "")
            environment["TEXINPUTS"] = (
                str(template_dir.resolve()) + os.pathsep + existing_texinputs
            )
        completed = subprocess.run(
            command,
            cwd=work_root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        log_text = (
            "$ " + " ".join(command) + "\n\nSTDOUT\n" + completed.stdout
            + "\n\nSTDERR\n" + completed.stderr
        )
    except subprocess.TimeoutExpired as error:
        log_text = f"$ {' '.join(command)}\n\nTIMEOUT after {timeout}s\n{error}"
        log_path.write_text(log_text, encoding="utf-8")
        raise PaperOrchestraStageError(
            stage=stage,
            code="latex_compile_failed",
            message=f"XeLaTeX/Biber compilation timed out after {timeout}s",
            log_path=str(log_path),
        ) from error
    log_path.write_text(log_text, encoding="utf-8")

    built_pdf = work_root / f"{source.stem}.pdf"
    if completed.returncode != 0 or not is_openable_pdf(built_pdf):
        raise PaperOrchestraStageError(
            stage=stage,
            code="latex_compile_failed",
            message=f"XeLaTeX/Biber compilation failed with exit code {completed.returncode}",
            log_path=str(log_path),
        )
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    if built_pdf.resolve() != output_pdf.resolve():
        shutil.copy2(built_pdf, output_pdf)
    if not is_openable_pdf(output_pdf):
        raise PaperOrchestraStageError(
            stage=stage,
            code="latex_compile_failed",
            message="compiled PDF is missing or invalid",
            log_path=str(log_path),
        )
    return output_pdf


def extract_pdf_text(pdf_path: Path) -> str:
    try:
        import pdfplumber

        with pdfplumber.open(pdf_path) as document:
            text = "\n\n".join(page.extract_text() or "" for page in document.pages)
    except Exception as error:
        raise PaperOrchestraStageError(
            stage="refine_content",
            code="pdf_text_extraction_failed",
            message=f"could not extract PDF text: {error}",
        ) from error
    if not text.strip():
        raise PaperOrchestraStageError(
            stage="refine_content",
            code="pdf_text_extraction_failed",
            message="compiled PDF contains no extractable text",
        )
    return text


def render_pdf_pages(pdf_path: Path, output_dir: Path, *, scale: float = 1.5) -> list[Path]:
    try:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(pdf_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        image_paths: list[Path] = []
        for page_number in range(len(document)):
            image_path = output_dir / f"page_{page_number + 1:03d}.png"
            page = document[page_number]
            page.render(scale=scale).to_pil().save(image_path, format="PNG")
            image_paths.append(image_path)
            page.close()
        document.close()
    except Exception as error:
        raise PaperOrchestraStageError(
            stage="review_layout_and_optionally_correct",
            code="pdf_page_render_failed",
            message=f"could not render PDF pages: {error}",
        ) from error
    if not image_paths:
        raise PaperOrchestraStageError(
            stage="review_layout_and_optionally_correct",
            code="pdf_page_render_failed",
            message="compiled PDF has no renderable pages",
        )
    return image_paths


def is_openable_pdf(path: Path) -> bool:
    """Return whether a non-empty PDF can be parsed and has at least one page."""
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if not (
        len(data) > 8
        and data.startswith(b"%PDF-")
        and data.rstrip().endswith(b"%%EOF")
    ):
        return False
    try:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(path)
        has_pages = len(document) > 0
        document.close()
    except Exception:
        return False
    return has_pages
