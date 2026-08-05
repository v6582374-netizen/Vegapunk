"""Launch-owned Discovery artifact listing, preview, and native-open helpers.

Discovery artifacts deliberately use a smaller contract than conversation-session files.
The caller identifies one Launch and supplies only a Launch-relative path.  The resolver
rejects traversal and every symlink so the Native Desktop API cannot become a generic file
browser or cross Launch boundaries.
"""

from __future__ import annotations

import base64
import mimetypes
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

MAX_PREVIEW_BYTES = 5 * 1024 * 1024
MAX_PREVIEW_CHARACTERS = 500_000
ARTIFACT_LIST_LIMIT = 256

_MARKDOWN_SUFFIXES = {".md", ".markdown"}
_STRUCTURED_SUFFIXES = {".csv", ".json", ".ndjson", ".toml", ".tsv", ".xml", ".yaml", ".yml"}
_CODE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".py",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
}
_TEXT_SUFFIXES = {".log", ".text", ".txt"}
_IMAGE_MIME_TYPES = {
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}
_OFFICE_SUFFIXES = {
    ".doc",
    ".docm",
    ".docx",
    ".ppt",
    ".pptm",
    ".pptx",
    ".xls",
    ".xlsm",
    ".xlsx",
}


class DiscoveryArtifactPathError(ValueError):
    """Raised when an artifact path is unsafe or not available to the Launch."""


def artifact_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _MARKDOWN_SUFFIXES:
        return "markdown"
    if suffix in _STRUCTURED_SUFFIXES:
        return "structured"
    if suffix in _CODE_SUFFIXES:
        return "code"
    if suffix in _TEXT_SUFFIXES:
        return "text"
    if suffix in _IMAGE_MIME_TYPES:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    if suffix in _OFFICE_SUFFIXES:
        return "office"
    media_type, _ = mimetypes.guess_type(path.name)
    if media_type and media_type.startswith("text/"):
        return "text"
    return "binary"


def _validate_relative_path(relative_path: str) -> tuple[str, ...]:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise DiscoveryArtifactPathError("artifact path is required")
    if "\x00" in relative_path or "\\" in relative_path:
        raise DiscoveryArtifactPathError("artifact path must use Launch-relative separators")
    if PurePosixPath(relative_path).is_absolute() or PureWindowsPath(relative_path).is_absolute():
        raise DiscoveryArtifactPathError("absolute artifact paths are not allowed")
    windows_path = PureWindowsPath(relative_path)
    if windows_path.drive:
        raise DiscoveryArtifactPathError("absolute artifact paths are not allowed")
    parts = PurePosixPath(relative_path).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise DiscoveryArtifactPathError("artifact path must stay inside the Launch")
    return parts


def resolve_artifact(artifacts_root: Path, relative_path: str) -> Path:
    """Resolve one regular file without following symlinks or leaving the artifact root."""
    parts = _validate_relative_path(relative_path)
    if artifacts_root.is_symlink():
        raise DiscoveryArtifactPathError("symlink artifact roots are not available")
    root = artifacts_root.resolve()
    if not root.is_dir():
        raise DiscoveryArtifactPathError("artifact is not available")

    candidate = root.joinpath(*parts)
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise DiscoveryArtifactPathError("symlink artifacts are not available")

    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise DiscoveryArtifactPathError("artifact path leaves the Launch") from error
    if not resolved.is_file():
        raise DiscoveryArtifactPathError("artifact is not available")
    return resolved


def _artifact_info(path: Path, artifacts_root: Path) -> dict[str, Any]:
    stat = path.stat()
    kind = artifact_kind(path)
    return {
        "path": path.relative_to(artifacts_root).as_posix(),
        "name": path.name,
        "kind": kind,
        "size": stat.st_size,
        "modified_at": stat.st_mtime,
        "previewable": kind in {"markdown", "structured", "code", "text", "image"}
        and stat.st_size <= MAX_PREVIEW_BYTES,
    }


def artifact_list(artifacts_root: Path) -> list[dict[str, Any]]:
    """Return eligible regular files in stable Launch-relative order."""
    if artifacts_root.is_symlink():
        return []
    root = artifacts_root.resolve()
    if not root.is_dir():
        return []
    artifacts: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        try:
            artifacts.append(_artifact_info(path, root))
        except OSError:
            continue
        if len(artifacts) >= ARTIFACT_LIST_LIMIT:
            break
    return artifacts


def read_artifact(artifacts_root: Path, relative_path: str) -> dict[str, Any]:
    path = resolve_artifact(artifacts_root, relative_path)
    root = artifacts_root.resolve()
    info = _artifact_info(path, root)
    if not info["previewable"]:
        return {"ok": True, **info, "content": None, "data_url": None}

    kind = info["kind"]
    if kind == "image":
        mime_type = _IMAGE_MIME_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0]
        if not mime_type:
            raise DiscoveryArtifactPathError("image type is not available")
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return {
            "ok": True,
            **info,
            "data_url": f"data:{mime_type};base64,{data}",
            "content": None,
        }

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise DiscoveryArtifactPathError("binary artifact cannot be previewed") from error
    return {
        "ok": True,
        **info,
        "content": content[:MAX_PREVIEW_CHARACTERS],
        "data_url": None,
        "truncated": len(content) > MAX_PREVIEW_CHARACTERS,
    }


def reveal_artifact(
    artifacts_root: Path,
    relative_path: str,
    mode: str = "reveal",
) -> dict[str, Any]:
    """Open or reveal a validated Launch artifact using the native OS action."""
    if mode not in {"open", "reveal"}:
        raise DiscoveryArtifactPathError("artifact action must be open or reveal")
    path = resolve_artifact(artifacts_root, relative_path)
    if sys.platform == "darwin":
        args = ["open", "-R", str(path)] if mode == "reveal" else ["open", str(path)]
        try:
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as error:
            return {"ok": False, "path": relative_path, "error": str(error)}
    elif sys.platform == "win32":
        try:
            if mode == "reveal":
                subprocess.Popen(["explorer", f"/select,{path}"])
            else:
                os.startfile(str(path))  # type: ignore[attr-defined]
        except OSError as error:
            return {"ok": False, "path": relative_path, "error": str(error)}
    else:
        target = str(path.parent) if mode == "reveal" else str(path)
        try:
            subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as error:
            return {"ok": False, "path": relative_path, "error": str(error)}
    return {"ok": True, "path": relative_path, "mode": mode}
