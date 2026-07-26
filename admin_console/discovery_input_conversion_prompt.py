"""Source configuration for the independent Discovery Input Conversion Prompt."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

from admin_console.configuration_files import source_configuration_transaction


def read_discovery_input_conversion_prompt(path: Path) -> dict:
    with source_configuration_transaction():
        return _document(path)


def save_discovery_input_conversion_prompt(path: Path, instruction: str) -> dict:
    if not instruction.strip():
        raise ValueError("Discovery Input Conversion Prompt must not be empty")

    with source_configuration_transaction():
        temporary = _temporary_path(path)
        try:
            temporary.write_text(
                yaml.safe_dump(
                    {"instruction": instruction},
                    allow_unicode=True,
                    sort_keys=False,
                )
            )
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return _document(path)


def _document(path: Path) -> dict:
    if not path.exists():
        return {"instruction": "", "configured": False}
    values = yaml.safe_load(path.read_text()) or {}
    if not isinstance(values, dict) or not isinstance(values.get("instruction", ""), str):
        raise ValueError("Discovery Input Conversion Prompt must contain a string instruction")
    instruction = values.get("instruction", "")
    return {"instruction": instruction, "configured": bool(instruction.strip())}


def _temporary_path(path: Path) -> Path:
    with NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    if path.exists():
        temporary_path.chmod(path.stat().st_mode)
    return temporary_path
