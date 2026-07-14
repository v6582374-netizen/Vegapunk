"""Block-aligned ingestion of an unbounded Research Draft."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from internagent.mas.models.runtime import ReasoningConfig
from internagent.research_draft import DRAFT_BLOCK_DELIMITER

from .data_types import PaperOrchestraStageError


EXTRACTION_SYSTEM_PROMPT = """You prepare evidence for a publication-oriented paper.
Extract every potentially useful claim, result, method detail, formula, variable
definition, assumption, derivation, citation record, failed attempt, limitation,
decision, and artifact path from the supplied raw Research Draft blocks. Preserve
numbers and mathematical notation exactly. Do not perform online research, invent
evidence, or write the paper. Detailed redundancy is preferable to omission."""

MERGE_SYSTEM_PROMPT = """Merge these extracted research notes into one detailed
paper-working record. Preserve every distinct claim, measurement, formula,
definition, assumption, citation, negative result, limitation, and artifact path.
Remove only exact repetition. Do not add external knowledge or write paper prose."""


async def ingest_research_draft(
    *,
    draft_path: Path,
    launch_dir: Path,
    output_dir: Path,
    model: Any,
    max_batch_chars: int,
) -> Path:
    """Read the canonical Draft in batches and persist disposable working notes."""

    if max_batch_chars < 1:
        raise ValueError("max_batch_chars must be positive")
    try:
        draft_text = draft_path.read_text(encoding="utf-8")
    except OSError as error:
        _fail(f"cannot read Research Draft: {error}")
    blocks = [
        block.strip("\n")
        for block in draft_text.split(DRAFT_BLOCK_DELIMITER)
        if block.strip("\n")
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    batches_dir = output_dir / "batches"
    batches_dir.mkdir(parents=True, exist_ok=True)

    extracted: list[str] = []
    for index, batch in enumerate(_pack(blocks, max_batch_chars), start=1):
        response = await model.generate(
            prompt=(
                f"Discovery Launch root: {launch_dir.resolve()}\n\n"
                f"{batch}"
            ),
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            temperature=0,
            agent_role="paper_orchestra_material_ingestion",
            reasoning=ReasoningConfig(mode="pro"),
            background=True,
            checkpoint_key=f"ingest_research_draft_batch_{index:04d}",
        )
        response = _require_text(response, f"batch {index}")
        (batches_dir / f"batch_{index:04d}.md").write_text(
            response + "\n", encoding="utf-8"
        )
        extracted.append(response)

    merged = await _merge_notes(
        extracted,
        output_dir=output_dir,
        model=model,
        max_batch_chars=max_batch_chars,
    )
    material_path = output_dir / "paper_materials.md"
    material_path.write_text(merged + ("\n" if merged else ""), encoding="utf-8")
    return material_path


async def _merge_notes(
    notes: list[str], *, output_dir: Path, model: Any, max_batch_chars: int
) -> str:
    if not notes:
        return ""
    if len(notes) == 1:
        return notes[0]
    current = notes
    round_index = 1
    while len(current) > 1:
        groups = list(_pack(current, max_batch_chars, separator="\n\n"))
        if len(groups) >= len(current):
            groups = ["\n\n".join(current[index : index + 2]) for index in range(0, len(current), 2)]
        merged_round: list[str] = []
        for group_index, group in enumerate(groups, start=1):
            response = await model.generate(
                prompt=group,
                system_prompt=MERGE_SYSTEM_PROMPT,
                temperature=0,
                agent_role="paper_orchestra_material_merge",
                reasoning=ReasoningConfig(mode="pro"),
                background=True,
                checkpoint_key=(
                    f"merge_research_material_round_{round_index:02d}_"
                    f"{group_index:04d}"
                ),
            )
            response = _require_text(
                response, f"merge round {round_index} group {group_index}"
            )
            merge_dir = output_dir / "merges"
            merge_dir.mkdir(parents=True, exist_ok=True)
            (merge_dir / f"round_{round_index:02d}_{group_index:04d}.md").write_text(
                response + "\n", encoding="utf-8"
            )
            merged_round.append(response)
        current = merged_round
        round_index += 1
    return current[0]


def _pack(
    items: Iterable[str],
    max_chars: int,
    *,
    separator: str = f"\n{DRAFT_BLOCK_DELIMITER}\n",
) -> Iterable[str]:
    current: list[str] = []
    current_size = 0
    for item in items:
        added_size = len(item) + (len(separator) if current else 0)
        if current and current_size + added_size > max_chars:
            yield separator.join(current)
            current = []
            current_size = 0
            added_size = len(item)
        current.append(item)
        current_size += added_size
    if current:
        yield separator.join(current)


def _require_text(value: Any, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"material ingestion returned empty text for {source}")
    return value.strip()


def _fail(message: str) -> None:
    raise PaperOrchestraStageError(
        stage="ingest_research_draft",
        code="invalid_material_ingestion",
        message=message,
    )
