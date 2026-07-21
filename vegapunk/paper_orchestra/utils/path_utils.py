from __future__ import annotations

from pathlib import Path


def resolve_launch_directory(launch_dir: Path, raw_path: str) -> Path:
    """Resolve absolute, launch-relative, or Vegapunk repo-relative artifact paths."""
    launch_root = launch_dir.resolve()
    raw = Path(raw_path)
    candidates: list[Path] = [raw] if raw.is_absolute() else [launch_dir / raw, Path.cwd() / raw]
    if not raw.is_absolute():
        parts = raw.parts
        for index, part in enumerate(parts):
            if part == launch_dir.name:
                candidates.append(launch_dir.joinpath(*parts[index + 1 :]))
    valid = {
        candidate.resolve()
        for candidate in candidates
        if candidate.resolve().is_relative_to(launch_root)
        and candidate.resolve().is_dir()
    }
    if len(valid) != 1:
        raise ValueError("artifact path must resolve to one directory inside the launch")
    return valid.pop()
