from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .data_types import DossierStageError, LinkedArtifacts
from .utils.path_utils import resolve_launch_directory


def link_selected_artifacts(
    *, launch_dir: Path, selection: dict[str, Any]
) -> LinkedArtifacts:
    """Join a selected experiment to its full Idea using exact structured data."""
    round_record = selection.get("paper_candidate_round")
    selected_record = selection.get("selected_candidate")
    if not isinstance(round_record, dict) or not isinstance(selected_record, dict):
        _fail("candidate selection is missing round or selected candidate data")

    session_id = round_record.get("session_id")
    idea_name = selected_record.get("idea_name")
    folder_name = selected_record.get("folder_name")
    if not all(isinstance(value, str) and value for value in (session_id, idea_name, folder_name)):
        _fail("candidate selection contains invalid artifact identifiers")

    launch_root = launch_dir.resolve()
    session_dir = (launch_dir / session_id).resolve()
    try:
        candidate_dir = resolve_launch_directory(launch_dir, folder_name)
    except ValueError as error:
        _fail(str(error))
    if (
        not session_dir.is_relative_to(launch_root)
        or not candidate_dir.is_relative_to(launch_root)
        or not session_dir.is_dir()
        or not candidate_dir.is_dir()
    ):
        _fail("selected session and candidate must exist inside the launch")

    methods = _read_json(session_dir / "ideas.json")
    if not isinstance(methods, list):
        _fail("ideas.json must contain a list of execution methods")
    method_matches = [
        method
        for method in methods
        if isinstance(method, dict) and method.get("name") == idea_name
    ]
    if len(method_matches) != 1:
        _fail("idea_name must match exactly one execution method in ideas.json")
    selected_method = method_matches[0]

    trajectory = _read_json(session_dir / "traj.json")
    if not isinstance(trajectory, dict):
        _fail("traj.json must contain a JSON object")
    top_ideas = trajectory.get("top_ideas")
    ideas = trajectory.get("ideas")
    if not isinstance(top_ideas, list) or not isinstance(ideas, list):
        _fail("traj.json must contain ideas and top_ideas lists")
    top_idea_ids = {idea_id for idea_id in top_ideas if isinstance(idea_id, str)}
    idea_matches = [
        idea
        for idea in ideas
        if isinstance(idea, dict)
        and idea.get("id") in top_idea_ids
        and idea.get("refined_method_details") == selected_method
    ]
    if len(idea_matches) != 1:
        _fail("selected method must match exactly one top Idea in traj.json")

    return LinkedArtifacts(
        candidate_dir=candidate_dir,
        session_dir=session_dir,
        selected_method=selected_method,
        full_idea=idea_matches[0],
    )


def _read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as error:
        _fail(f"cannot read {path.name}: {error}")


def _fail(message: str) -> None:
    raise DossierStageError(
        stage="link_selected_artifacts",
        code="artifact_link_failed",
        message=message,
    )
