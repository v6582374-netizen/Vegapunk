from __future__ import annotations

import inspect
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable

from .data_types import DossierStageError


class DossierCheckpoint:
    def __init__(self, *, run_dir: Path, manifest: dict[str, Any]) -> None:
        self.run_dir = run_dir
        self.path = run_dir / "dossier_run.json"
        self.manifest = manifest

    @classmethod
    def open(
        cls,
        *,
        run_dir: Path,
        dossier_run_id: str,
        launch_id: str,
        resolved_config: dict[str, Any],
        model_identity: dict[str, Any],
        stage_ids: Iterable[str],
    ) -> "DossierCheckpoint":
        path = run_dir / "dossier_run.json"
        if path.exists():
            with path.open("r", encoding="utf-8") as file:
                manifest = json.load(file)
            if not isinstance(manifest, dict):
                raise ValueError("dossier_run.json must contain an object")
            if manifest.get("dossier_run_id") != dossier_run_id:
                raise ValueError("Dossier Run ID differs from existing checkpoint")
            if (
                manifest.get("resolved_config") != resolved_config
                or manifest.get("model") != model_identity
            ):
                raise DossierStageError(
                    stage="checkpoint",
                    code="resume_context_mismatch",
                    message=(
                        "resolved configuration or model identity differs from the "
                        "existing Dossier Run; use a new Dossier Run ID"
                    ),
                )
            checkpoint = cls(run_dir=run_dir, manifest=manifest)
            checkpoint._upgrade_manifest()
            checkpoint._normalize_interrupted_stages()
            return checkpoint

        run_dir.mkdir(parents=True, exist_ok=True)
        now = _now()
        manifest = {
            "schema_version": 2,
            "dossier_run_id": dossier_run_id,
            "launch_id": launch_id,
            "status": "running",
            "created_at": now,
            "updated_at": now,
            "resolved_config": resolved_config,
            "model": model_identity,
            "stages": [
                {
                    "id": stage_id,
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "outputs": [],
                    "error": None,
                }
                for stage_id in stage_ids
            ],
            "warnings": [],
            "final_outputs": _empty_final_outputs(),
            "error": None,
            "model_responses": {},
        }
        checkpoint = cls(run_dir=run_dir, manifest=manifest)
        checkpoint._save()
        return checkpoint

    def first_incomplete_stage(self) -> str | None:
        for stage in self.manifest["stages"]:
            if stage["status"] != "succeeded":
                return stage["id"]
        return None

    def stage_succeeded(self, stage_id: str) -> bool:
        return self._stage(stage_id)["status"] == "succeeded"

    def get_model_response(self, checkpoint_key: str) -> dict[str, str] | None:
        """Load a resumable provider response record by deterministic run key."""
        record = self.manifest["model_responses"].get(checkpoint_key)
        return dict(record) if isinstance(record, dict) else None

    def record_model_response(
        self, *, checkpoint_key: str, response_id: str, status: str
    ) -> None:
        """Atomically persist a background response before polling it."""
        if not checkpoint_key or not response_id or not status:
            raise ValueError("model response checkpoint fields must be non-empty")
        self.manifest["model_responses"][checkpoint_key] = {
            "response_id": response_id,
            "status": status,
        }
        self._save()

    @staticmethod
    def recorded_outputs_are_valid(
        *, run_dir: Path, manifest: dict[str, Any]
    ) -> bool:
        """Validate all outputs claimed by a completed checkpoint manifest."""
        stages = manifest.get("stages")
        if not isinstance(stages, list) or not stages:
            return False
        for stage in stages:
            if not isinstance(stage, dict) or stage.get("status") != "succeeded":
                return False
            outputs = stage.get("outputs")
            if not isinstance(outputs, list) or not all(
                isinstance(output, str) and _output_is_valid(run_dir / output)
                for output in outputs
            ):
                return False
        return True

    @staticmethod
    def final_outputs_match(*, run_dir: Path, manifest: dict[str, Any]) -> bool:
        outputs = manifest.get("final_outputs")
        if not isinstance(outputs, dict):
            return False
        pdf = outputs.get("pdf")
        tex = outputs.get("tex")
        if not isinstance(pdf, str) or not isinstance(tex, str):
            return False
        try:
            return (
                outputs.get("pdf_sha256") == _sha256(run_dir / pdf)
                and outputs.get("tex_sha256") == _sha256(run_dir / tex)
            )
        except OSError:
            return False

    async def run_stage(
        self,
        stage_id: str,
        operation: Callable[[], Awaitable[Any] | Any],
        *,
        outputs: tuple[str, ...] = (),
        immutable_outputs: bool = False,
    ) -> Any:
        stage = self._stage(stage_id)
        if stage["status"] == "succeeded":
            try:
                self._validate_outputs(outputs)
            except DossierStageError as error:
                if error.code != "stage_output_missing":
                    raise
                if immutable_outputs:
                    raise DossierStageError(
                        stage=stage_id,
                        code="immutable_stage_output_missing",
                        message=(
                            "immutable stage output is missing; use a new Dossier "
                            "Run ID instead of recomputing it"
                        ),
                    ) from error
                self.reset_from_stage(stage_id)
                stage = self._stage(stage_id)
            else:
                return None
        now = _now()
        stage.update(
            {
                "status": "running",
                "started_at": now,
                "completed_at": None,
                "outputs": [],
                "error": None,
            }
        )
        self.manifest["status"] = "running"
        self.manifest["error"] = None
        self._save()
        try:
            result = operation()
            if inspect.isawaitable(result):
                result = await result
            self._validate_outputs(outputs)
        except Exception as error:
            stage["status"] = "failed"
            stage["completed_at"] = _now()
            error_data = (
                error.error.to_dict()
                if isinstance(error, DossierStageError)
                else {
                    "stage": stage_id,
                    "code": "stage_failed",
                    "message": str(error),
                    "log_path": None,
                }
            )
            stage["error"] = error_data
            self.manifest["status"] = "failed"
            self.manifest["error"] = error_data
            self._save()
            raise
        stage["status"] = "succeeded"
        stage["completed_at"] = _now()
        stage["outputs"] = list(outputs)
        self._save()
        return result

    def complete(
        self,
        *,
        final_pdf: str,
        final_tex: str,
        warnings: Iterable[str] = (),
    ) -> None:
        if self.first_incomplete_stage() is not None:
            raise ValueError("cannot complete a Dossier Run with unfinished stages")
        self.manifest["status"] = "succeeded"
        self.manifest["warnings"] = list(warnings)
        pdf_path = self.run_dir / final_pdf
        tex_path = self.run_dir / final_tex
        self.manifest["final_outputs"] = {
            "pdf": final_pdf,
            "tex": final_tex,
            "pdf_sha256": _sha256(pdf_path),
            "tex_sha256": _sha256(tex_path),
        }
        self.manifest["error"] = None
        self._save()

    def fail(self, error: DossierStageError) -> None:
        self.manifest["status"] = "failed"
        self.manifest["error"] = error.error.to_dict()
        self._save()

    def reset_from_stage(self, stage_id: str) -> None:
        """Invalidate one stage and every dependent stage after it."""
        reset = False
        for stage in self.manifest["stages"]:
            if stage["id"] == stage_id:
                reset = True
            if reset:
                stage.update(
                    {
                        "status": "pending",
                        "started_at": None,
                        "completed_at": None,
                        "outputs": [],
                        "error": None,
                    }
                )
        if not reset:
            raise KeyError(f"unknown Dossier stage: {stage_id}")
        self.manifest["status"] = "running"
        self.manifest["final_outputs"] = _empty_final_outputs()
        self.manifest["error"] = None
        self._save()

    def _stage(self, stage_id: str) -> dict[str, Any]:
        for stage in self.manifest["stages"]:
            if stage["id"] == stage_id:
                return stage
        raise KeyError(f"unknown Dossier stage: {stage_id}")

    def _validate_outputs(self, outputs: tuple[str, ...]) -> None:
        missing = []
        for output in outputs:
            path = self.run_dir / output
            if not _output_is_valid(path):
                missing.append(output)
        if missing:
            raise DossierStageError(
                stage="checkpoint",
                code="stage_output_missing",
                message=f"stage output missing or empty: {', '.join(missing)}",
            )

    def _normalize_interrupted_stages(self) -> None:
        changed = False
        for stage in self.manifest.get("stages", []):
            if stage.get("status") == "running":
                stage["status"] = "pending"
                stage["completed_at"] = None
                changed = True
        if changed:
            self.manifest["status"] = "running"
            self.manifest["error"] = None
            self._save()

    def _upgrade_manifest(self) -> None:
        """Add resumable model state to checkpoints created before schema v2."""
        if "model_responses" in self.manifest:
            if not isinstance(self.manifest["model_responses"], dict):
                raise ValueError("dossier model_responses must contain an object")
            return
        self.manifest["schema_version"] = 2
        self.manifest["model_responses"] = {}
        self._save()

    def _save(self) -> None:
        self.manifest["updated_at"] = _now()
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(self.manifest, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, self.path)


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _output_is_valid(path: Path) -> bool:
    return path.exists() and (not path.is_file() or path.stat().st_size > 0)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _empty_final_outputs() -> dict[str, None]:
    return {
        "pdf": None,
        "tex": None,
        "pdf_sha256": None,
        "tex_sha256": None,
    }
