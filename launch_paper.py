#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from vegapunk.paper_orchestra import run_paper_orchestra


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the single Paper owned by one Discovery Launch."
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
        help="Vegapunk configuration containing the relay provider.",
    )
    parser.add_argument(
        "--paper-config",
        type=Path,
        default=Path("config/paper_orchestra.yaml"),
        help="PaperOrchestra host configuration.",
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
    load_dotenv()
    args = parse_arguments()
    result = asyncio.run(
        run_paper_orchestra(
            launch_dir=args.launch_dir,
            vegapunk_config=load_config(args.config),
            paper_config_path=args.paper_config,
        )
    )
    print(f"PaperOrchestra Run: {result.paper_orchestra_run_id}")
    print(f"Directory: {result.run_dir}")
    if result.final_pdf is not None:
        print(f"PDF: {result.final_pdf}")
    if result.final_tex is not None:
        print(f"LaTeX: {result.final_tex}")
    for warning in result.warnings:
        print(f"Warning: {warning}")
    if result.error is not None:
        print(
            f"Error [{result.error.stage}/{result.error.code}]: "
            f"{result.error.message}"
        )
        return 1
    print("Status: succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
