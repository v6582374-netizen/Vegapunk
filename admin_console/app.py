"""FastAPI application factory for the Admin Console."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from admin_console.launches import scan_launches

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def create_app(results_root: Path | None = None) -> FastAPI:
    resolved_results_root = results_root or (REPOSITORY_ROOT / "results")

    app = FastAPI(title="InternAgent Admin Console")

    @app.get("/api/launches")
    def list_launches() -> dict:
        launches = scan_launches(resolved_results_root)
        return {"launches": [launch.to_dict() for launch in launches]}

    return app
