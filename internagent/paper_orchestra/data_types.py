from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LinkedArtifacts:
    candidate_dir: Path
    session_dir: Path
    selected_method: dict[str, Any]
    full_idea: dict[str, Any]


@dataclass(frozen=True)
class RefinementResult:
    tex_path: Path
    pdf_path: Path
    review: dict[str, Any]


@dataclass(frozen=True)
class PipelineResult:
    final_tex: Path
    final_pdf: Path
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class DossierRunResult:
    dossier_run_id: str
    status: str
    run_dir: Path
    final_pdf: Path | None
    final_tex: Path | None
    warnings: tuple[str, ...]
    error: DossierError | None


@dataclass(frozen=True)
class DossierError:
    stage: str
    code: str
    message: str
    log_path: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


class DossierStageError(RuntimeError):
    def __init__(
        self,
        *,
        stage: str,
        code: str,
        message: str,
        log_path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error = DossierError(
            stage=stage,
            code=code,
            message=message,
            log_path=log_path,
        )
        self.stage = stage
        self.code = code
        self.log_path = log_path
