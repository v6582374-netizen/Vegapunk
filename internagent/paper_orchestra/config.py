from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from .data_types import DossierStageError


@dataclass(frozen=True)
class PaperOrchestraConfig:
    enabled: bool
    template_dir: Path
    layout_review_enabled: bool
    max_content_refinement_iterations: int
    max_format_correction_iterations: int

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["template_dir"] = str(self.template_dir)
        return data


def load_paper_config(
    path: Path, *, repository_root: Path | None = None
) -> PaperOrchestraConfig:
    root = repository_root or Path(__file__).resolve().parents[2]
    try:
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except (OSError, yaml.YAMLError) as error:
        _invalid(f"cannot load PaperOrchestra config: {error}")
    if not isinstance(data, dict):
        _invalid("PaperOrchestra config must contain a YAML mapping")

    enabled = _boolean(data, "enabled")
    layout_enabled = _boolean(data, "layout_review_enabled")
    content_iterations = _nonnegative_integer(
        data, "max_content_refinement_iterations"
    )
    format_iterations = _nonnegative_integer(
        data, "max_format_correction_iterations"
    )
    if format_iterations > 1:
        _invalid("max_format_correction_iterations cannot exceed 1")
    raw_template_dir = data.get("template_dir")
    if not isinstance(raw_template_dir, str) or not raw_template_dir.strip():
        _invalid("template_dir must be a non-empty path string")
    template_dir = Path(raw_template_dir)
    if not template_dir.is_absolute():
        template_dir = root / template_dir
    template_dir = template_dir.resolve()
    if not template_dir.is_dir():
        _invalid(f"template_dir does not exist: {template_dir}")
    for required_file in ("template.tex", "guidelines.md"):
        if not (template_dir / required_file).is_file():
            _invalid(f"template_dir is missing {required_file}")
    return PaperOrchestraConfig(
        enabled=enabled,
        template_dir=template_dir,
        layout_review_enabled=layout_enabled,
        max_content_refinement_iterations=content_iterations,
        max_format_correction_iterations=format_iterations,
    )


def _boolean(data: dict[str, Any], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        _invalid(f"{key} must be a boolean")
    return value


def _nonnegative_integer(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _invalid(f"{key} must be a non-negative integer")
    return value


def _invalid(message: str) -> None:
    raise DossierStageError(
        stage="validate_launch",
        code="invalid_paper_config",
        message=message,
    )
