from __future__ import annotations

import json
import math
import os
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from numbers import Real
from pathlib import Path
from typing import Any, NoReturn

from internagent.mas.models.runtime import ReasoningConfig

from .data_types import PaperOrchestraStageError
from .utils.experiment_runs import find_current_valid_run
from .utils.path_utils import resolve_launch_directory


SOLE_SUCCESS_METHOD = "sole_success"
METRIC_METHOD = "metric"
RANDOM_TIE_METHOD = "random_tie"
RANDOM_FALLBACK_METHOD = "random_fallback"
SELECTION_METHODS = frozenset(
    {
        SOLE_SUCCESS_METHOD,
        METRIC_METHOD,
        RANDOM_TIE_METHOD,
        RANDOM_FALLBACK_METHOD,
    }
)
RANDOM_SELECTION_METHODS = frozenset(
    {RANDOM_TIE_METHOD, RANDOM_FALLBACK_METHOD}
)


@dataclass(frozen=True)
class _CandidateDecision:
    candidate_records: list[dict[str, Any]]
    selection_method: str
    deterministic_selection: dict[str, Any] | None
    fallback_reason: str | None
    fallback_candidates: list[dict[str, Any]]


@dataclass(frozen=True)
class _CriterionContext:
    prompt: dict[str, Any] | None
    configured_primary: str | None
    configured_direction: str | None
    reported_metric_names: set[str]
    missing_fields: list[str]
    model_input: dict[str, Any] | None
    source_paths: list[str]


async def select_candidate(
    *,
    launch_dir: Path,
    run_dir: Path,
    model: Any | None = None,
    random_source: Any | None = None,
) -> dict[str, Any]:
    """Select and persist the terminal paper candidate for a Discovery Launch."""
    selection_path = run_dir / "candidate_selection.json"
    temporary_path = selection_path.with_suffix(selection_path.suffix + ".tmp")
    if selection_path.exists():
        return load_candidate_selection(launch_dir=launch_dir, run_dir=run_dir)
    if temporary_path.exists():
        selection = _load_and_validate_selection(
            path=temporary_path,
            launch_dir=launch_dir,
            run_dir=run_dir,
        )
        os.replace(temporary_path, selection_path)
        return selection

    summary = _read_json_object(launch_dir / "discovery_summary.json")
    rounds, candidate_round, successful_candidates = _terminal_candidate_context(summary)
    candidate_paths = [
        _resolve_candidate_path(launch_dir, candidate)
        for candidate in successful_candidates
    ]
    candidate_round_number = _round_number(candidate_round)
    skipped_rounds, skipped_round_facts = _skipped_round_provenance(
        rounds, candidate_round_number
    )

    criterion = _empty_criterion()
    criterion_fallback_reason: str | None = None
    if len(successful_candidates) > 1:
        criterion_error: Exception | None = None
        try:
            criterion = await _resolve_criterion(
                launch_dir / "prompt.json", candidate_paths, model
            )
        except PaperOrchestraStageError as error:
            if error.code == "criterion_inference_requires_model":
                raise
            criterion_error = error
        except Exception as error:
            criterion_error = error

        if criterion_error is not None:
            criterion = _unavailable_criterion(
                launch_dir / "prompt.json", criterion_error
            )
            criterion_fallback_reason = _criterion_fallback_reason(criterion_error)

    decision = _expected_decision(
        successful_candidates=successful_candidates,
        candidate_paths=candidate_paths,
        criterion=criterion,
        criterion_fallback_reason=criterion_fallback_reason,
    )
    selected = decision.deterministic_selection
    if selected is None:
        choice_source = random_source or random.SystemRandom()
        selected = choice_source.choice(decision.fallback_candidates)

    selection = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "launch_id": summary.get("launch_id", launch_dir.name),
        "paper_orchestra_run_id": run_dir.name,
        "paper_candidate_round": {
            "round": candidate_round_number,
            "session_id": candidate_round.get("session_id"),
            "skipped_later_rounds": skipped_rounds,
            "skipped_later_round_facts": skipped_round_facts,
        },
        "successful_candidates": decision.candidate_records,
        "criterion": criterion,
        "selection_method": decision.selection_method,
        "fallback_reason": decision.fallback_reason,
        "fallback_pool": [
            _candidate_identity(candidate)
            for candidate in decision.fallback_candidates
        ],
        "selected_candidate": _candidate_identity(selected),
    }
    _write_json_atomically(selection_path, selection)
    return selection


def load_candidate_selection(*, launch_dir: Path, run_dir: Path) -> dict[str, Any]:
    """Load an immutable selection only after checking it against its Launch."""
    return _load_and_validate_selection(
        path=run_dir / "candidate_selection.json",
        launch_dir=launch_dir,
        run_dir=run_dir,
    )


def _load_and_validate_selection(
    *, path: Path, launch_dir: Path, run_dir: Path
) -> dict[str, Any]:
    summary = _read_json_object(launch_dir / "discovery_summary.json")
    rounds, candidate_round, successful_candidates = _terminal_candidate_context(summary)
    selection = _read_persisted_selection(path)
    _validate_persisted_selection(
        selection=selection,
        launch_dir=launch_dir,
        run_dir=run_dir,
        summary=summary,
        rounds=rounds,
        candidate_round=candidate_round,
        successful_candidates=successful_candidates,
    )
    return selection


def _terminal_candidate_context(
    summary: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    rounds = summary.get("rounds")
    if not isinstance(rounds, list) or not rounds or not all(
        isinstance(round_data, dict) for round_data in rounds
    ):
        raise ValueError("discovery_summary.json must contain non-empty object rounds")
    for round_data in sorted(rounds, key=_round_number, reverse=True):
        results = round_data.get("results")
        if not isinstance(results, list):
            raise ValueError("each Discovery Round must contain a results list")
        successful = [
            result
            for result in results
            if isinstance(result, dict) and result.get("success") is True
        ]
        if successful:
            return rounds, round_data, successful
    raise PaperOrchestraStageError(
        stage="terminal_candidate_selection",
        code="no_successful_candidate",
        message="Discovery Launch has no successful Candidate Experiment",
    )


def _skipped_round_provenance(
    rounds: list[dict[str, Any]], candidate_round_number: int
) -> tuple[list[int], list[dict[str, Any]]]:
    later_rounds = sorted(
        (
            round_data
            for round_data in rounds
            if _round_number(round_data) > candidate_round_number
        ),
        key=_round_number,
        reverse=True,
    )
    numbers = [_round_number(round_data) for round_data in later_rounds]
    facts = []
    for round_data in later_rounds:
        results = round_data.get("results")
        if not isinstance(results, list):
            raise ValueError("each Discovery Round must contain a results list")
        facts.append(
            {
                "round": _round_number(round_data),
                "session_id": round_data.get("session_id"),
                "result_count": len(results),
                "successful_candidate_count": sum(
                    isinstance(result, dict) and result.get("success") is True
                    for result in results
                ),
            }
        )
    return numbers, facts


def _read_persisted_selection(path: Path) -> dict[str, Any]:
    try:
        return _read_json_object(path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError) as error:
        _invalid_selection(f"cannot read immutable candidate selection: {error}")


def _validate_persisted_selection(
    *,
    selection: dict[str, Any],
    launch_dir: Path,
    run_dir: Path,
    summary: dict[str, Any],
    rounds: list[dict[str, Any]],
    candidate_round: dict[str, Any],
    successful_candidates: list[dict[str, Any]],
) -> None:
    expected_round_number = _round_number(candidate_round)
    skipped_rounds, skipped_facts = _skipped_round_provenance(
        rounds, expected_round_number
    )
    round_record = selection.get("paper_candidate_round")
    if not isinstance(round_record, dict) or round_record != {
        "round": expected_round_number,
        "session_id": candidate_round.get("session_id"),
        "skipped_later_rounds": skipped_rounds,
        "skipped_later_round_facts": skipped_facts,
    }:
        _invalid_selection("paper candidate round differs from Discovery summary")
    if selection.get("schema_version") != 1:
        _invalid_selection("unsupported candidate selection schema version")
    if selection.get("launch_id") != summary.get("launch_id", launch_dir.name):
        _invalid_selection("candidate selection launch ID differs from its Launch")
    if selection.get("paper_orchestra_run_id") != run_dir.name:
        _invalid_selection("candidate selection PaperOrchestra Run ID differs from its directory")

    expected_identities = [
        _candidate_identity(candidate) for candidate in successful_candidates
    ]
    candidate_records = selection.get("successful_candidates")
    if not isinstance(candidate_records, list):
        _invalid_selection("successful candidate provenance must be a list")
    recorded_identities = [_record_identity(record) for record in candidate_records]
    if recorded_identities != expected_identities:
        _invalid_selection("successful candidate pool differs from Discovery summary")

    selected = _record_identity(selection.get("selected_candidate"))
    if selected not in expected_identities:
        _invalid_selection("selected candidate is not successful in the candidate round")
    try:
        _resolve_candidate_path(launch_dir, selected)
    except (ValueError, KeyError) as error:
        _invalid_selection(f"selected candidate artifact is inconsistent: {error}")

    _validate_persisted_decision(
        selection=selection,
        launch_dir=launch_dir,
        successful_candidates=successful_candidates,
        candidate_records=candidate_records,
        selected=selected,
    )


def _record_identity(record: Any) -> dict[str, str]:
    if not isinstance(record, dict):
        _invalid_selection("candidate identity must be an object")
    idea_name = record.get("idea_name")
    folder_name = record.get("folder_name")
    if not isinstance(idea_name, str) or not idea_name:
        _invalid_selection("candidate identity has an invalid idea_name")
    if not isinstance(folder_name, str) or not folder_name:
        _invalid_selection("candidate identity has an invalid folder_name")
    return {"idea_name": idea_name, "folder_name": folder_name}


def _expected_decision(
    *,
    successful_candidates: list[dict[str, Any]],
    candidate_paths: list[Path],
    criterion: dict[str, Any],
    criterion_fallback_reason: str | None,
) -> _CandidateDecision:
    base_records = [
        _candidate_record(candidate) for candidate in successful_candidates
    ]
    if len(successful_candidates) == 1:
        return _CandidateDecision(
            candidate_records=base_records,
            selection_method=SOLE_SUCCESS_METHOD,
            deterministic_selection=successful_candidates[0],
            fallback_reason=None,
            fallback_candidates=[],
        )
    if criterion.get("source") == "unavailable":
        if not isinstance(criterion_fallback_reason, str) or not (
            criterion_fallback_reason.strip()
        ):
            _invalid_selection("unavailable criterion has no fallback reason")
        return _CandidateDecision(
            candidate_records=base_records,
            selection_method=RANDOM_FALLBACK_METHOD,
            deterministic_selection=None,
            fallback_reason=criterion_fallback_reason,
            fallback_candidates=successful_candidates,
        )

    primary_metric = criterion.get("primary_metric")
    direction = criterion.get("optimization_direction")
    if not isinstance(primary_metric, str) or direction not in {
        "minimize",
        "maximize",
    }:
        _invalid_selection("comparison criterion is incomplete")
    candidate_records, comparable = _evaluate_candidate_metrics(
        successful_candidates=successful_candidates,
        candidate_paths=candidate_paths,
        primary_metric=primary_metric,
    )
    if not comparable:
        return _CandidateDecision(
            candidate_records=candidate_records,
            selection_method=RANDOM_FALLBACK_METHOD,
            deterministic_selection=None,
            fallback_reason="no_comparable_primary_metric",
            fallback_candidates=successful_candidates,
        )
    optimal = _optimal_candidates(comparable, direction)
    if len(optimal) == 1:
        return _CandidateDecision(
            candidate_records=candidate_records,
            selection_method=METRIC_METHOD,
            deterministic_selection=optimal[0],
            fallback_reason=None,
            fallback_candidates=[],
        )
    return _CandidateDecision(
        candidate_records=candidate_records,
        selection_method=RANDOM_TIE_METHOD,
        deterministic_selection=None,
        fallback_reason="exact_primary_metric_tie",
        fallback_candidates=optimal,
    )


def _build_criterion_context(
    *,
    path: Path,
    candidate_paths: list[Path],
    allow_prompt_error: bool,
) -> _CriterionContext:
    try:
        prompt = _read_json_object(path)
    except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError):
        if not allow_prompt_error:
            raise
        prompt = None
    metrics = prompt.get("metrics") if isinstance(prompt, dict) else None
    metrics = metrics if isinstance(metrics, dict) else {}
    configured_primary = metrics.get("primary")
    configured_primary = (
        configured_primary
        if isinstance(configured_primary, str) and configured_primary
        else None
    )
    configured_direction = metrics.get("optimization_direction")
    configured_direction = (
        configured_direction
        if configured_direction in {"minimize", "maximize"}
        else None
    )
    reported_metric_names: set[str] = set()
    for candidate_path in candidate_paths:
        current_run = find_current_valid_run(candidate_path)
        if current_run is not None:
            reported_metric_names.update(
                _reported_metric_names(current_run.final_info)
            )
    missing_fields = [
        field
        for field, value in (
            ("primary_metric", configured_primary),
            ("optimization_direction", configured_direction),
        )
        if value is None
    ]
    model_input = (
        {
            "task_prompt": prompt,
            "reported_metric_names": sorted(reported_metric_names),
            "missing_fields": missing_fields,
        }
        if prompt is not None
        else None
    )
    return _CriterionContext(
        prompt=prompt,
        configured_primary=configured_primary,
        configured_direction=configured_direction,
        reported_metric_names=reported_metric_names,
        missing_fields=missing_fields,
        model_input=model_input,
        source_paths=[path.name] if path.is_file() else [],
    )


def _validate_criterion_against_prompt(
    *,
    criterion: dict[str, Any],
    launch_dir: Path,
    successful_candidates: list[dict[str, Any]],
) -> str | None:
    prompt_path = launch_dir / "prompt.json"
    candidate_paths = [
        _resolve_candidate_path(launch_dir, candidate)
        for candidate in successful_candidates
    ]
    context = _build_criterion_context(
        path=prompt_path,
        candidate_paths=candidate_paths,
        allow_prompt_error=True,
    )
    prompt = context.prompt
    configured_primary = context.configured_primary
    configured_direction = context.configured_direction
    reported_metric_names = context.reported_metric_names
    source = criterion.get("source")
    primary_metric = criterion.get("primary_metric")
    direction = criterion.get("optimization_direction")
    if criterion.get("source_paths") != context.source_paths:
        _invalid_selection("criterion source paths differ from the Launch")

    if source == "task_config":
        if (
            prompt is None
            or configured_primary is None
            or configured_direction is None
            or primary_metric != configured_primary
            or direction != configured_direction
            or criterion.get("model_input") is not None
            or criterion.get("model_output") is not None
            or criterion.get("reasoning") is not None
        ):
            _invalid_selection("task criterion differs from prompt.json.metrics")
        return None

    if source == "model_inference":
        model_input = criterion.get("model_input")
        model_output = criterion.get("model_output")
        reasoning = criterion.get("reasoning")
        if (
            prompt is None
            or not context.missing_fields
            or not isinstance(model_input, dict)
            or not isinstance(model_output, dict)
            or not isinstance(reasoning, str)
            or not reasoning.strip()
            or model_input != context.model_input
            or model_output.get("primary_metric") not in reported_metric_names
            or model_output.get("optimization_direction")
            not in {"minimize", "maximize"}
            or model_output.get("reasoning") != reasoning
            or primary_metric
            != (configured_primary or model_output.get("primary_metric"))
            or direction
            != (configured_direction or model_output.get("optimization_direction"))
        ):
            _invalid_selection("model criterion differs from prompt and model provenance")
        return None

    if source != "unavailable" or primary_metric is not None or direction is not None:
        _invalid_selection("unavailable criterion has invalid comparison fields")
    reasoning = criterion.get("reasoning")
    if not isinstance(reasoning, str) or ":" not in reasoning:
        _invalid_selection("unavailable criterion omits its failure provenance")
    fallback_reason = reasoning.split(":", 1)[0]
    if prompt is None:
        expected_reasons = {"criterion_source_unavailable"}
    elif configured_primary is not None and configured_direction is not None:
        expected_reasons = set()
    elif not reported_metric_names:
        expected_reasons = {"no_reported_metric_names"}
    else:
        expected_reasons = {"invalid_model_criterion", "criterion_inference_failed"}
    if fallback_reason not in expected_reasons:
        _invalid_selection("criterion failure reason conflicts with prompt and artifacts")
    model_input = criterion.get("model_input")
    model_output = criterion.get("model_output")
    if fallback_reason in {"invalid_model_criterion", "criterion_inference_failed"}:
        if model_input != context.model_input:
            _invalid_selection("failed model criterion input differs from the Launch")
        if fallback_reason == "invalid_model_criterion" and _model_criterion_is_valid(
            model_output, reported_metric_names
        ):
            _invalid_selection("recorded invalid model criterion is actually valid")
        if fallback_reason == "criterion_inference_failed" and model_output is not None:
            _invalid_selection("failed criterion call cannot contain a model output")
    elif model_input is not None or model_output is not None:
        _invalid_selection("criterion without a model call contains model provenance")
    return fallback_reason


def _validate_persisted_decision(
    *,
    selection: dict[str, Any],
    launch_dir: Path,
    successful_candidates: list[dict[str, Any]],
    candidate_records: list[Any],
    selected: dict[str, str],
) -> None:
    method = selection.get("selection_method")
    criterion = selection.get("criterion")
    if not isinstance(criterion, dict):
        _invalid_selection("candidate selection criterion must be an object")
    if len(successful_candidates) == 1:
        if criterion != _empty_criterion():
            _invalid_selection("sole-success selection must not record a criterion")
        criterion_fallback_reason = None
    else:
        criterion_fallback_reason = _validate_criterion_against_prompt(
            criterion=criterion,
            launch_dir=launch_dir,
            successful_candidates=successful_candidates,
        )

    candidate_paths = [
        _resolve_candidate_path(launch_dir, candidate)
        for candidate in successful_candidates
    ]
    expected = _expected_decision(
        successful_candidates=successful_candidates,
        candidate_paths=candidate_paths,
        criterion=criterion,
        criterion_fallback_reason=criterion_fallback_reason,
    )
    _validate_candidate_record_facts(candidate_records, expected.candidate_records)
    fallback_pool = selection.get("fallback_pool")
    if not isinstance(fallback_pool, list):
        _invalid_selection("candidate selection fallback pool must be a list")
    pool_identities = [_record_identity(record) for record in fallback_pool]
    expected_pool = [
        _candidate_identity(candidate) for candidate in expected.fallback_candidates
    ]
    if expected.deterministic_selection is not None:
        if (
            method != expected.selection_method
            or selected != _candidate_identity(expected.deterministic_selection)
            or selection.get("fallback_reason") is not None
            or pool_identities
        ):
            _invalid_selection("persisted deterministic decision is inconsistent")
        return
    if (
        method != expected.selection_method
        or selection.get("fallback_reason") != expected.fallback_reason
        or pool_identities != expected_pool
        or selected not in pool_identities
    ):
        _invalid_selection("persisted random decision is inconsistent")


def _validate_candidate_record_facts(
    actual_records: list[Any], expected_records: list[dict[str, Any]]
) -> None:
    fields = ("metric_source", "primary_metric_value", "exclusion_reason")
    if len(actual_records) != len(expected_records):
        _invalid_selection("candidate metric record count is inconsistent")
    for actual, expected in zip(actual_records, expected_records, strict=True):
        if not isinstance(actual, dict) or any(
            actual.get(field) != expected.get(field) for field in fields
        ):
            _invalid_selection("candidate metric provenance differs from artifacts")


def _invalid_selection(message: str) -> NoReturn:
    raise PaperOrchestraStageError(
        stage="terminal_candidate_selection",
        code="invalid_candidate_selection",
        message=message,
    )


def _round_number(round_data: dict[str, Any]) -> int:
    number = round_data.get("round")
    if isinstance(number, bool) or not isinstance(number, int):
        raise ValueError("Discovery Round number must be an integer")
    return number


def _resolve_candidate_path(
    launch_dir: Path, selected: dict[str, Any]
) -> Path:
    idea_name = selected.get("idea_name")
    folder_name = selected.get("folder_name")
    if not isinstance(idea_name, str) or not idea_name:
        raise ValueError("successful candidate must have a non-empty idea_name")
    if not isinstance(folder_name, str) or not folder_name:
        raise ValueError("successful candidate must have a non-empty folder_name")

    return resolve_launch_directory(launch_dir, folder_name)


def _empty_criterion() -> dict[str, Any]:
    return {
        "source": "unavailable",
        "primary_metric": None,
        "optimization_direction": None,
        "source_paths": [],
        "model_input": None,
        "model_output": None,
        "reasoning": None,
    }


def _unavailable_criterion(path: Path, error: Exception) -> dict[str, Any]:
    criterion = _empty_criterion()
    criterion["source_paths"] = [path.name] if path.is_file() else []
    criterion["reasoning"] = f"{_criterion_fallback_reason(error)}: {error}"
    provenance = getattr(error, "criterion_provenance", None)
    if isinstance(provenance, dict):
        criterion["model_input"] = provenance.get("model_input")
        criterion["model_output"] = provenance.get("model_output")
    return criterion


def _criterion_fallback_reason(error: Exception) -> str:
    if isinstance(error, PaperOrchestraStageError):
        return error.code
    if isinstance(error, (FileNotFoundError, json.JSONDecodeError, ValueError, OSError)):
        return "criterion_source_unavailable"
    return "criterion_inference_failed"


async def _resolve_criterion(
    path: Path, candidate_paths: list[Path], model: Any | None
) -> dict[str, Any]:
    context = _build_criterion_context(
        path=path,
        candidate_paths=candidate_paths,
        allow_prompt_error=False,
    )
    prompt = context.prompt
    primary_metric = context.configured_primary
    direction = context.configured_direction
    if primary_metric is not None and direction is not None:
        return {
            "source": "task_config",
            "primary_metric": primary_metric,
            "optimization_direction": direction,
            "source_paths": context.source_paths,
            "model_input": None,
            "model_output": None,
            "reasoning": None,
        }

    reported_metric_names = context.reported_metric_names
    if not reported_metric_names:
        raise PaperOrchestraStageError(
            stage="terminal_candidate_selection",
            code="no_reported_metric_names",
            message="successful candidates report no finite metric names",
        )
    if model is None:
        raise PaperOrchestraStageError(
            stage="terminal_candidate_selection",
            code="criterion_inference_requires_model",
            message="missing terminal selection criterion requires the shared model",
        )
    model_input = context.model_input
    if prompt is None or model_input is None:
        raise ValueError("criterion prompt context is unavailable")
    schema = {
        "type": "object",
        "properties": {
            "primary_metric": {"type": "string"},
            "optimization_direction": {
                "type": "string",
                "enum": ["minimize", "maximize"],
            },
            "reasoning": {"type": "string"},
        },
        "required": ["primary_metric", "optimization_direction", "reasoning"],
        "additionalProperties": False,
    }
    try:
        model_output = await model.generate_json(
            prompt=json.dumps(model_input, ensure_ascii=False, sort_keys=True),
            schema=schema,
            system_prompt=(
                "Infer only the missing terminal paper-selection criterion fields from "
                "the supplied task prompt and reported metric names."
            ),
            temperature=0,
            agent_role="paper_orchestra_criterion_inference",
            reasoning=ReasoningConfig(context="current_turn"),
        )
    except Exception as cause:
        error = PaperOrchestraStageError(
            stage="terminal_candidate_selection",
            code="criterion_inference_failed",
            message=f"criterion model call failed: {cause}",
        )
        error.criterion_provenance = {
            "model_input": model_input,
            "model_output": None,
        }
        raise error from cause
    if not isinstance(model_output, dict):
        error = PaperOrchestraStageError(
            stage="terminal_candidate_selection",
            code="invalid_model_criterion",
            message=f"criterion model output must be a JSON object: {model_output!r}",
        )
        error.criterion_provenance = {
            "model_input": model_input,
            "model_output": model_output,
        }
        raise error
    inferred_primary = model_output.get("primary_metric")
    inferred_direction = model_output.get("optimization_direction")
    reasoning = model_output.get("reasoning")
    if not _model_criterion_is_valid(model_output, reported_metric_names):
        error = PaperOrchestraStageError(
            stage="terminal_candidate_selection",
            code="invalid_model_criterion",
            message=(
                "model criterion must name a reported metric, direction, and reason: "
                + json.dumps(model_output, ensure_ascii=False, sort_keys=True)
            ),
        )
        error.criterion_provenance = {
            "model_input": model_input,
            "model_output": model_output,
        }
        raise error
    primary_metric = primary_metric or inferred_primary
    direction = direction or inferred_direction
    return {
        "source": "model_inference",
        "primary_metric": primary_metric,
        "optimization_direction": direction,
        "source_paths": ["prompt.json"],
        "model_input": model_input,
        "model_output": model_output,
        "reasoning": reasoning,
    }


def _model_criterion_is_valid(
    model_output: Any, reported_metric_names: set[str]
) -> bool:
    return (
        isinstance(model_output, dict)
        and model_output.get("primary_metric") in reported_metric_names
        and model_output.get("optimization_direction") in {"minimize", "maximize"}
        and isinstance(model_output.get("reasoning"), str)
        and bool(model_output["reasoning"].strip())
    )


def _evaluate_candidate_metrics(
    *,
    successful_candidates: list[dict[str, Any]],
    candidate_paths: list[Path],
    primary_metric: str,
) -> tuple[
    list[dict[str, Any]],
    list[tuple[dict[str, Any], dict[str, Any]]],
]:
    records = [_candidate_record(candidate) for candidate in successful_candidates]
    comparable = []
    for candidate, candidate_path, record in zip(
        successful_candidates, candidate_paths, records, strict=True
    ):
        current_run = find_current_valid_run(candidate_path)
        if current_run is None:
            record["exclusion_reason"] = "no_valid_experiment_run"
            continue
        record["metric_source"] = f"{current_run.path.name}/final_info.json"
        metric_value = _find_metric(current_run.final_info, primary_metric)
        if not _is_finite_number(metric_value):
            record["exclusion_reason"] = "primary_metric_missing_or_non_finite"
            continue
        record["primary_metric_value"] = metric_value
        comparable.append((candidate, record))
    return records, comparable


def _optimal_candidates(
    comparable: list[tuple[dict[str, Any], dict[str, Any]]], direction: str
) -> list[dict[str, Any]]:
    values = [record["primary_metric_value"] for _, record in comparable]
    optimal_value = min(values) if direction == "minimize" else max(values)
    return [
        candidate
        for candidate, record in comparable
        if record["primary_metric_value"] == optimal_value
    ]


def _candidate_record(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "idea_name": candidate["idea_name"],
        "folder_name": candidate["folder_name"],
        "metric_source": None,
        "primary_metric_value": None,
        "exclusion_reason": None,
    }


def _candidate_identity(candidate: dict[str, Any]) -> dict[str, str]:
    return {
        "idea_name": candidate["idea_name"],
        "folder_name": candidate["folder_name"],
    }


def _find_metric(data: dict[str, Any], metric_name: str) -> Any:
    if metric_name in data:
        return data[metric_name]
    matches = [
        value[metric_name]
        for value in data.values()
        if isinstance(value, dict) and metric_name in value
    ]
    return matches[0] if len(matches) == 1 else None


def _reported_metric_names(data: dict[str, Any]) -> set[str]:
    names = {name for name, value in data.items() if _is_finite_number(value)}
    for value in data.values():
        if isinstance(value, dict):
            names.update(
                name
                for name, nested_value in value.items()
                if _is_finite_number(nested_value)
            )
    return names


def _is_finite_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, Real) and math.isfinite(value)


def _read_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def _write_json_atomically(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("x", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary_path, path)
