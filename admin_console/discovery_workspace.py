"""Workspace-facing views over persisted Discovery Launch artifacts.

The Unified Workspace intentionally exposes human-readable artifacts only.
The existing Admin Console explorer remains unchanged and continues to expose
the complete on-disk tree for operator diagnostics.
"""

from __future__ import annotations

from pathlib import Path

from admin_console.artifacts import ArtifactPathError, resolve_artifact

_MACHINE_ONLY_SUFFIXES = {
    ".bin",
    ".cache",
    ".db",
    ".gz",
    ".joblib",
    ".npy",
    ".npz",
    ".pkl",
    ".pickle",
    ".pt",
    ".pth",
    ".safetensors",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".tgz",
    ".whl",
    ".zip",
}
_MACHINE_ONLY_DIRECTORIES = {"config_snapshot", "__pycache__", ".git"}


def is_workspace_artifact(path: Path, launch_dir: Path) -> bool:
    """Return whether a file is suitable for the researcher-facing archive."""
    try:
        relative = path.relative_to(launch_dir)
    except ValueError:
        return False
    if any(part in _MACHINE_ONLY_DIRECTORIES for part in relative.parts[:-1]):
        return False
    if path.name.startswith("."):
        return False
    return path.suffix.lower() not in _MACHINE_ONLY_SUFFIXES


def workspace_artifact_tree(launch_dir: Path) -> list[dict]:
    def walk(directory: Path, prefix: str) -> list[dict]:
        nodes: list[dict] = []
        for child in sorted(directory.iterdir(), key=lambda item: (item.is_file(), item.name)):
            if child.is_symlink():
                continue
            rel = f"{prefix}{child.name}"
            if child.is_dir():
                children = walk(child, f"{rel}/")
                if children:
                    nodes.append(
                        {
                            "path": rel,
                            "name": child.name,
                            "kind": "directory",
                            "children": children,
                        }
                    )
            elif is_workspace_artifact(child, launch_dir):
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


def resolve_workspace_artifact(launch_dir: Path, relative_path: str) -> Path:
    try:
        artifact = resolve_artifact(launch_dir, relative_path)
    except ArtifactPathError:
        raise
    if not artifact.is_file() or not is_workspace_artifact(artifact, launch_dir):
        raise ArtifactPathError(relative_path)
    return artifact
