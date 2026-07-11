#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import yaml

from internagent.paper_orchestra import run_dossier


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate or resume a Research Dossier for one Discovery Launch."
    )
    parser.add_argument(
        "--launch-dir",
        type=Path,
        required=True,
        help="Completed experiment-mode Discovery Launch directory.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/default_config.yaml"),
        help="InternAgent configuration used to create the shared model.",
    )
    parser.add_argument(
        "--paper-config",
        type=Path,
        default=Path("config/paper_orchestra.yaml"),
        help="Isolated PaperOrchestra configuration.",
    )
    parser.add_argument(
        "--dossier-run-id",
        default="primary",
        help="Use primary to resume the canonical attempt, or a new ID for a fresh attempt.",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        if path.suffix.casefold() in {".yaml", ".yml"}:
            config = yaml.safe_load(file)
        else:
            config = json.load(file)
    if not isinstance(config, dict):
        raise ValueError(f"{path} must contain a configuration object")
    return config


def main() -> int:
    args = parse_arguments()
    result = asyncio.run(
        run_dossier(
            launch_dir=args.launch_dir,
            internagent_config=load_config(args.config),
            paper_config_path=args.paper_config,
            dossier_run_id=args.dossier_run_id,
        )
    )
    print(f"Dossier Run: {result.dossier_run_id}")
    print(f"Status: {result.status}")
    print(f"Directory: {result.run_dir}")
    if result.final_pdf is not None:
        print(f"PDF: {result.final_pdf}")
    if result.final_tex is not None:
        print(f"LaTeX: {result.final_tex}")
    for warning in result.warnings:
        print(f"Warning: {warning}")
    if result.error is not None:
        print(f"Error [{result.error.stage}/{result.error.code}]: {result.error.message}")
    return 0 if result.status == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
