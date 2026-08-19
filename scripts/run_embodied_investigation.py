#!/usr/bin/env python3
"""Version 1: a complaint about the G1 becomes ranked, measured adaptations.

This is the whole product in one command. A person says what the robot will not
do; the system routes that complaint, searches for an adaptation that fixes it,
measures every candidate across a band of simulated worlds, ranks what it found,
and prints what a human must still do before anything physical moves.

    python3 scripts/run_embodied_investigation.py \
        --complaint "左臂抬起时到不了评审位姿，动作系统性地偏" \
        --submitted-by loongge

The five stages it runs, and what each refuses:

``intake``       routes the complaint. Three of the five paths are refused
                 outright: a machine may search an interface or an instruction,
                 but changing the room, training a checkpoint, or fitting a
                 residual are decisions with a human in them.
``calibration``  measures how fast this configuration may be commanded. Nothing
                 downstream may command a rate no probe measured.
``regime``       gives every attempt a different world. Ten replays of one world
                 are one measurement reported ten times.
``search``       explores typed candidates, scored by robustness across that
                 band rather than by a nominal best case.
``handoff``      states what is still unproven. It never ends in a robot moving.

The robot never leaves simulation, and cannot. The evaluator drives a
``PerturbableRobot`` -- a physical G1 structurally is not one, because hardware
cannot be teleported to a chosen initial condition -- so the worst outcome of a
runaway search is wasted CPU. Everything this command produces is a *proposal*.
Promotion to hardware stays where the admission ladder put it: a named human, a
fresh approval pinned to the evidence they actually reviewed, one run at a time.

``--symptom`` and ``--route`` skip the model call and state the classification
directly. That exists for offline and reproducible runs; without them the
complaint is classified by the configured model, and a reply that cannot be read
is reported as an unreadable brief rather than repaired into a guess.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vegapunk.embodied.bench import embodiment_for
from vegapunk.embodied.calibration import (
    CommandRateProbe,
    ProbeMotion,
    calibrate_command_rate,
)
from vegapunk.embodied.harness import (
    DEFAULT_SEARCH_BUDGET,
    CampaignEvaluator,
    InvestigationReport,
    investigate,
)
from vegapunk.embodied.intake import (
    ADAPTATION_PATH_ORDER,
    SYMPTOM_ORDER,
    PainPoint,
    brief_from_classification,
    triage,
)
from vegapunk.embodied.regime import DEFAULT_CONTACT_REGIME
from vegapunk.embodied.runtime import JointPoseGoal
from vegapunk.embodied.safety import SafetyEnvelope
from vegapunk.embodied.simulation import (
    G1_LEFT_ARM_JOINTS,
    SimulatedG1,
    SimulatedSupervision,
)
from vegapunk.embodied.skill import SKILL_KIND_DETERMINISTIC, PhysicalSkill
from vegapunk.embodied.store import DEFAULT_LEDGER_ROOT, LedgerStore

ENVIRONMENT_ID = "sim-g1-left-arm"

CAMERA_MAP = {
    "observation.images.head": "head",
    "observation.images.left_wrist": "leftWrist",
    "observation.images.right_wrist": "rightWrist",
}

ENVELOPE = SafetyEnvelope(
    max_duration_s=20.0,
    max_joint_velocity_rps=1.5,
    max_end_effector_force_n=20.0,
    workspace_bounds_m=((-1.0, 1.0), (-1.0, 1.0), (0.0, 2.0)),
)
"""What this laboratory permits. Declared, because no measurement yields it."""

CANDIDATE_RATES_RPS = (0.15, 0.3, 0.6)

GOAL_OFFSETS_RAD = (0.0, 0.35, 0.0, 0.0, 0.0, 0.0, 0.0)
"""The reviewed target: raise the left shoulder roll, and nothing else."""

SKILL = PhysicalSkill(
    skill_id="raise_left_shoulder",
    revision=1,
    kind=SKILL_KIND_DETERMINISTIC,
    summary="Raise the left shoulder roll to a reviewed joint pose.",
    parameters=(),
    preconditions=("workspace_clear", "guardian_present", "estop_reachable"),
    postconditions=("at_reviewed_pose",),
    abort_conditions=("force_exceeded", "human_stop"),
    max_duration_s=10.0,
    reviewed_by="loongge",
)


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_embodied_investigation",
        description=(
            "Turn one natural-language complaint about the G1 into a ranked "
            "set of measured adaptation candidates."
        ),
    )
    parser.add_argument(
        "--complaint",
        required=True,
        help="what the robot will not do, in the reporter's own words.",
    )
    parser.add_argument(
        "--submitted-by",
        required=True,
        help=(
            "who is reporting it. Recorded because a brief is traceable to a "
            "person, not to a prompt."
        ),
    )
    parser.add_argument(
        "--symptom",
        choices=SYMPTOM_ORDER,
        help=(
            "state the symptom instead of asking the model. Use with --route "
            "for an offline, reproducible run."
        ),
    )
    parser.add_argument(
        "--route",
        choices=ADAPTATION_PATH_ORDER,
        help="state the adaptation path instead of asking the model.",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=DEFAULT_SEARCH_BUDGET,
        help=(
            "how many candidates to evaluate. Each one is a full campaign of "
            "--attempts governed runs."
        ),
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=10,
        help="runs per candidate. The ladder requires at least 10 for evidence.",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--control-hz",
        type=float,
        default=50.0,
        help="cadence the simulation steps and commands at.",
    )
    parser.add_argument(
        "--ledger-root",
        type=Path,
        default=DEFAULT_LEDGER_ROOT,
        help="directory the durable record and the report artifact live in.",
    )
    return parser.parse_args(argv)


def _brief(arguments: argparse.Namespace) -> object:
    """Classify the complaint, by hand if told to and by model otherwise."""
    pain_point = PainPoint(
        text=arguments.complaint,
        submitted_by=arguments.submitted_by,
        submitted_at=datetime.now(timezone.utc),
    )
    if arguments.symptom and arguments.route:
        return brief_from_classification(
            pain_point,
            {
                "symptom": arguments.symptom,
                "routed_path": arguments.route,
                "objective_statement": (
                    "demonstrate that the reported behaviour no longer occurs "
                    "on the original request"
                ),
                "observable_success": (
                    "the skill's declared postconditions are measured true in "
                    "every sampled world",
                ),
                "unknowns": (),
                "rejected_paths": (),
            },
        )
    if arguments.symptom or arguments.route:
        raise SystemExit(
            "--symptom and --route must be given together: a half-stated "
            "classification would be completed by a guess, and the guess "
            "would be the part that decides whether a machine may act."
        )

    from vegapunk.mas.models.unified_runtime import create_model_runtime

    runtime = create_model_runtime()
    return asyncio.run(triage(pain_point, runtime))


def report_lines(report: InvestigationReport) -> tuple[str, ...]:
    """Render the investigation as the questions it answered, in order."""
    brief = report.brief
    lines = [
        "Complaint",
        f"  from             {brief.pain_point.submitted_by}",
        f"  text             {brief.pain_point.text}",
        "",
        "Triage",
        f"  symptom          {brief.symptom}",
        f"  routed path      {brief.routed_path}",
        f"  searchable       {brief.searchable}",
        f"  objective        {brief.objective_statement}",
    ]
    for path, reason in brief.rejected_paths:
        lines.append(f"  rejected {path:<12} {reason}")
    for unknown in brief.unknowns:
        lines.append(f"  unknown          {unknown}")
    if brief.refusal:
        lines.extend(["", "Refused", f"  {brief.refusal}"])

    if report.search is None:
        lines.extend(["", "Search", "  not run", f"  {report.halt_detail}"])
        return tuple(lines)

    search = report.search
    lines.extend(
        [
            "",
            "Search",
            f"  evaluated        {search.evaluated} candidates",
            f"  halted           {search.halted}",
            f"  detail           {search.halt_detail}",
        ]
    )

    baseline = search.baseline
    if baseline is not None and baseline.score is not None:
        score = baseline.score
        lines.append(
            f"  identity         mean {score.regime_success_rate:.2f}  "
            f"score {_score(score)}"
        )

    lines.extend(["", "Ranking"])
    if not search.ranking:
        lines.append("  nothing was rankable")
    for position, node in enumerate(search.ranking[:5], start=1):
        score = node.score
        worst = score.worst_bucket
        lines.append(
            f"  {position}. score {_score(score):>10}  "
            f"mean {score.regime_success_rate:.2f}  "
            f"sens {score.sensitivity:.3f}  "
            f"worst {worst.label if worst is not None else 'n/a':<28} "
            f"{'DISQUALIFIED' if score.disqualified else ''}"
        )
    for finding in _findings(search):
        lines.append(f"  finding: {finding}")

    best = report.best
    lines.extend(["", "Best adaptation"])
    if best is None:
        lines.append("  none: no candidate outranked doing nothing")
    else:
        lines.append(f"  digest           {best.candidate_digest}")
        for name, value in _genes(search):
            lines.append(f"  {name:<16} {value:+.4f}")
    lines.append(f"  improved         {report.improved}")

    lines.extend(
        [
            "",
            "Before anything physical moves",
            "  This search ran entirely in simulation. Its evidence is scoped",
            "  to a simulated embodiment whose digest differs from the real",
            "  G1's, so none of it is evidence about hardware. What remains is",
            "  laboratory work, in this order:",
            "",
            "  1. Record the real inventory. The hand on this G1 is a BrainCo",
            "     Revo 2, not the Dex1-1 the published checkpoint expects, so",
            "     compatibility will report adaptation rather than a match.",
            "  2. Verify the interface contract against the real robot before",
            "     considering any fine-tuning. An interface fault trained into",
            "     a checkpoint stops being a configuration you can change.",
            "  3. Earn shadow_mode evidence, then a named human approval",
            "     pinned to that evidence, before hardware_supervised runs.",
        ]
    )
    return tuple(lines)


def _score(score: object) -> str:
    return "disqualified" if score.disqualified else f"{score.score:+.4f}"


def _findings(search: object) -> tuple[str, ...]:
    seen: list[str] = []
    for node in search.ranking[:5]:
        for finding in node.score.findings:
            if finding not in seen:
                seen.append(finding)
    return tuple(seen)


def _genes(search: object) -> tuple[tuple[str, float], ...]:
    best = search.best
    if best is None:
        return ()
    return tuple(sorted(best.candidate.values.items()))


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = parse_arguments(argv)
    brief = _brief(arguments)

    robot = SimulatedG1(
        controlled_joints=G1_LEFT_ARM_JOINTS,
        supervision=SimulatedSupervision(
            guardian_present=True,
            estop_engaged=False,
            estop_reachable=True,
            workspace_clear=True,
        ),
        control_frequency_hz=arguments.control_hz,
    )
    try:
        embodiment = embodiment_for(
            robot,
            end_effector="dex1_1",
            control_authority="arm_only",
            camera_map=CAMERA_MAP,
        )
        target = tuple(
            stand + offset
            for stand, offset in zip(
                robot.stand_positions_rad, GOAL_OFFSETS_RAD
            )
        )
        calibration = calibrate_command_rate(
            CommandRateProbe(
                robot=robot,
                motion=ProbeMotion(target_joint_positions_rad=target),
                envelope=ENVELOPE,
                control_frequency_hz=robot.control_frequency_hz,
                measured_on=f"{ENVIRONMENT_ID} at {arguments.control_hz:g}Hz",
            ),
            CANDIDATE_RATES_RPS,
        )
        admitted = calibration.admitted
        if admitted is None:
            print(
                "no candidate command rate fits the envelope, so nothing may "
                "be commanded; the search cannot start."
            )
            return 1

        goal = JointPoseGoal(
            skill_version_id=SKILL.version_id,
            target_joint_positions_rad=target,
            satisfies=("at_reviewed_pose",),
            tolerance_rad=max(0.02, admitted.minimum_goal_tolerance_rad),
        )
        evaluator = CampaignEvaluator(
            robot=robot,
            skill=SKILL,
            embodiment=embodiment,
            configuration=robot.describe_configuration(
                environment_id=ENVIRONMENT_ID,
                end_effector="dex1_1",
                control_authority="arm_only",
                represented_camera_keys=tuple(CAMERA_MAP),
            ),
            goal=goal,
            command_rate=admitted,
            envelope=ENVELOPE,
            regime=DEFAULT_CONTACT_REGIME,
            attempts=arguments.attempts,
        )
        report = investigate(
            brief=brief,
            evaluator=evaluator,
            budget=arguments.budget,
            seed=arguments.seed,
        )
    finally:
        robot.close()

    for line in report_lines(report):
        print(line)

    store = LedgerStore(root=arguments.ledger_root)
    name = f"investigation-{brief.pain_point.digest()}.json"
    path = store.write_artifact(name, report.as_contract())
    print("")
    print(f"Record written to {path}")
    return 0 if report.completed else 2


if __name__ == "__main__":
    raise SystemExit(main())
