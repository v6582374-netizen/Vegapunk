from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from .data_types import PaperOrchestraStageError


@dataclass(frozen=True)
class PaperOrchestraConfig:
    """Host settings for one source-faithful vendored PaperOrchestra run."""

    vendor_root: Path
    template_dir: Path
    use_plotting: bool
    plotting_max_critic_rounds: int
    research_cutoff: str | None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["vendor_root"] = str(self.vendor_root)
        data["template_dir"] = str(self.template_dir)
        return data


def load_paper_config(
    path: Path, *, repository_root: Path | None = None
) -> PaperOrchestraConfig:
    root = (repository_root or Path(__file__).resolve().parents[2]).resolve()
    try:
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except (OSError, yaml.YAMLError) as error:
        _invalid(f"cannot load PaperOrchestra config: {error}")
    if not isinstance(data, dict):
        _invalid("PaperOrchestra config must contain a YAML mapping")

    legacy_model_keys = {
        "writer_model",
        "reflection_model",
        "plotting_model",
        "image_model",
        "max_concurrent_model_requests",
    }
    configured_legacy_keys = sorted(legacy_model_keys.intersection(data))
    if configured_legacy_keys:
        _invalid(
            "PaperOrchestra model overrides are retired; remove: "
            + ", ".join(configured_legacy_keys)
        )

    vendor_root = _resolve_directory(
        data=data,
        key="vendor_root",
        relative_to=root,
    )
    if not (vendor_root / "paper_writing_cli.py").is_file():
        _invalid(f"vendor_root is missing paper_writing_cli.py: {vendor_root}")

    template_dir = _resolve_directory(
        data=data,
        key="template_dir",
        relative_to=vendor_root,
    )
    for required_file in ("template.tex", "guidelines.md"):
        if not (template_dir / required_file).is_file():
            _invalid(f"template_dir is missing {required_file}")

    cutoff = data.get("research_cutoff")
    if cutoff is not None and (not isinstance(cutoff, str) or not cutoff.strip()):
        _invalid("research_cutoff must be null or a non-empty string")

    return PaperOrchestraConfig(
        vendor_root=vendor_root,
        template_dir=template_dir,
        use_plotting=_boolean(data, "use_plotting"),
        plotting_max_critic_rounds=_nonnegative_integer(
            data, "plotting_max_critic_rounds"
        ),
        research_cutoff=cutoff.strip() if isinstance(cutoff, str) else None,
    )


def _resolve_directory(
    *, data: dict[str, Any], key: str, relative_to: Path
) -> Path:
    raw_path = data.get(key)
    if not isinstance(raw_path, str) or not raw_path.strip():
        _invalid(f"{key} must be a non-empty path string")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = relative_to / path
    path = path.resolve()
    if not path.is_dir():
        _invalid(f"{key} does not exist: {path}")
    return path


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


def _nonempty_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        _invalid(f"{key} must be a non-empty string")
    return value.strip()


def _invalid(message: str) -> None:
    raise PaperOrchestraStageError(
        stage="validate_launch",
        code="invalid_paper_config",
        message=message,
    )
