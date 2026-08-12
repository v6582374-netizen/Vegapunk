"""Immutable dependency contracts for the long-lived Vegapunk runtime."""

from __future__ import annotations

import os
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from collections.abc import MutableMapping
from pathlib import Path


RUNTIME_CONSTRAINTS_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "runtime_constraints.txt"
)

# IdeaGraph spans these packages at import time. Treat their proven working
# versions as one runtime-owned contract, rather than independent optional
# dependencies that experiment installers may replace one at a time.
IDEAGRAPH_RUNTIME_REQUIREMENTS = frozenset(
    {
        "chromadb==1.5.9",
        "datasets==2.21.0",
        "pyarrow==20.0.0",
        "sentence-transformers==5.1.1",
        "transformers==4.57.6",
    }
)


def enforce_runtime_pip_constraint(
    environment: MutableMapping[str, str] | None = None,
) -> Path:
    """Bind package installation to the runtime-owned compatibility contract.

    """
    if not RUNTIME_CONSTRAINTS_PATH.is_file():
        raise RuntimeError(
            "Runtime dependency constraints are missing: "
            f"{RUNTIME_CONSTRAINTS_PATH}"
        )
    target = os.environ if environment is None else environment
    target["PIP_CONSTRAINT"] = str(RUNTIME_CONSTRAINTS_PATH)
    return RUNTIME_CONSTRAINTS_PATH


def verify_ideagraph_runtime() -> None:
    """Fail before a Launch when IdeaGraph's import contract is broken.

    This checks only the dependency boundary: loading an embedding model is a
    separate, launch-specific concern and may require network or GPU access.
    """
    constrained = {
        line.strip()
        for line in RUNTIME_CONSTRAINTS_PATH.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    missing_constraints = sorted(IDEAGRAPH_RUNTIME_REQUIREMENTS - constrained)
    if missing_constraints:
        raise RuntimeError(
            "IdeaGraph runtime compatibility contract is incomplete: "
            + ", ".join(missing_constraints)
        )

    for requirement in IDEAGRAPH_RUNTIME_REQUIREMENTS:
        package, expected = requirement.split("==", 1)
        try:
            installed = version(package)
        except PackageNotFoundError as exc:
            raise RuntimeError(
                f"IdeaGraph runtime dependency is missing: {requirement}"
            ) from exc
        if installed != expected:
            raise RuntimeError(
                "IdeaGraph runtime dependency version mismatch: "
                f"{package}=={installed}; expected {expected}"
            )

    try:
        import_module("chromadb")
        import_module("datasets")
        import_module("sentence_transformers")
    except ImportError as exc:
        raise RuntimeError(
            "IdeaGraph runtime dependency chain cannot be imported"
        ) from exc


__all__ = [
    "IDEAGRAPH_RUNTIME_REQUIREMENTS",
    "RUNTIME_CONSTRAINTS_PATH",
    "enforce_runtime_pip_constraint",
    "verify_ideagraph_runtime",
]
