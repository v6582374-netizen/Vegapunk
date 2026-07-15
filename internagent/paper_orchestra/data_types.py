from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class PaperOrchestraRunResult:
    paper_orchestra_run_id: str
    run_dir: Path
    final_pdf: Path | None
    final_tex: Path | None
    warnings: tuple[str, ...]
    error: PaperOrchestraError | None


@dataclass(frozen=True)
class PaperOrchestraError:
    stage: str
    code: str
    message: str
    log_path: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


class PaperOrchestraStageError(RuntimeError):
    def __init__(
        self,
        *,
        stage: str,
        code: str,
        message: str,
        log_path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error = PaperOrchestraError(
            stage=stage,
            code=code,
            message=message,
            log_path=log_path,
        )
        self.stage = stage
        self.code = code
        self.log_path = log_path
