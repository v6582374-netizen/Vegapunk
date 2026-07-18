"""Artifact Explorer: expose every file a Launch persists (no blind spot).

Structured views are navigational overlays elsewhere; this module guarantees
that any file under a launch directory is reachable through the tree and
file endpoints, with path traversal confined to that directory.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path


class ArtifactPathError(Exception):
    """The requested path escapes or leaves the launch directory."""


def resolve_launch_dir(results_root: Path, launch_id: str) -> Path | None:
    launch_dir = (results_root / launch_id).resolve()
    try:
        launch_dir.relative_to(results_root.resolve())
    except ValueError:
        return None
    if not launch_dir.is_dir():
        return None
    return launch_dir


def artifact_tree(launch_dir: Path) -> list[dict]:
    def walk(directory: Path, prefix: str) -> list[dict]:
        nodes: list[dict] = []
        for child in sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name)):
            rel = f"{prefix}{child.name}"
            if child.is_dir():
                nodes.append(
                    {
                        "path": rel,
                        "name": child.name,
                        "kind": "directory",
                        "children": walk(child, f"{rel}/"),
                    }
                )
            else:
                nodes.append(
                    {
                        "path": rel,
                        "name": child.name,
                        "kind": "file",
                        "size": child.stat().st_size,
                    }
                )
        return nodes

    return walk(launch_dir, "")


def resolve_artifact(launch_dir: Path, relative_path: str) -> Path:
    candidate = (launch_dir / relative_path).resolve()
    try:
        candidate.relative_to(launch_dir)
    except ValueError:
        raise ArtifactPathError(relative_path)
    return candidate


def guess_media_type(path: Path) -> str:
    media_type, _ = mimetypes.guess_type(path.name)
    return media_type or "application/octet-stream"
