#!/usr/bin/env python3
"""Run the inner loop on the simulated G1, and print what it opened.

This is the entry point for the profile's inner loop. It measures how fast this
configuration may be commanded, derives a goal pose from that measurement,
iterates the ladder's two simulated stages, and reports what still stands
between the result and a supervised hardware run. Nothing here judges anything:
every verdict printed was produced by the module that owns it.

The robot does not leave simulation and cannot. The embodiment profile this
evidence is scoped to is derived from the compiled MJCF model, so its digest
differs from any physical G1's, and no run collected here can be read as
evidence about hardware.

``--watch`` streams the simulated cameras to the GUI's camera panel while the
run advances. Watching happens outside the governed loop and on the loop's own
thread, so it changes the wall-clock pace of a run and never its physics.

Supervision must be declared. A simulated run cannot observe whether a guardian
is present or the workspace is clear, and the skill's preconditions require
both, so ``--declare-supervised`` is an explicit assertion by the operator
rather than a default: a simulator that assumed those facts would manufacture
exactly the preconditions the Safety Supervisor exists to check.

Security, when ``--watch`` is used: the camera endpoints are unauthenticated and
the TLS certificate is self-signed. Anyone who can reach the ports can watch.
The default bind host is loopback; exposing the preview is an explicit argument.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vegapunk.embodied.bench import (
    HALTED_COMPLETED,
    BenchPlan,
    BenchReport,
    run_bench,
)
from vegapunk.embodied.preview import (
    DEFAULT_CERT_DIR,
    PREVIEW_SECURITY_NOTICE,
    PreviewServer,
)
from vegapunk.embodied.safety import SafetyEnvelope
from vegapunk.embodied.simulation import (
    CAMERA_SLOTS,
    G1_LEFT_ARM_JOINTS,
    FrameBus,
    SimulatedG1,
    SimulatedSupervision,
)
from vegapunk.embodied.skill import SKILL_KIND_DETERMINISTIC, PhysicalSkill

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
"""The limits the supervisor enforces for this bench.

Declared here rather than derived, because an envelope is a statement about what
this laboratory permits and no measurement can produce one. The velocity and
force ceilings are the G1's published arm limits reduced to what a bench needs;
the workspace box contains the standing pose with room for the reviewed motion.
"""

CANDIDATE_RATES_RPS = (0.15, 0.3, 0.6)
"""The command rates to measure. The bench proposes none of its own."""

GOAL_OFFSETS_RAD = (0.0, 0.35, 0.0, 0.0, 0.0, 0.0, 0.0)
"""The reviewed target: raise the left shoulder roll, and nothing else.

Expressed as a departure from the model's standing keyframe so the motion is
readable as a pose change rather than as seven bare numbers.
"""

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
    """Read the bench's cadence, attempt count, and preview settings."""
    parser = argparse.ArgumentParser(
        prog="run_embodied_bench",
        description=(
            "Measure, iterate the simulated admission stages, and report what "
            "still blocks supervised hardware execution."
        ),
    )
    parser.add_argument(
        "--declare-supervised",
        action="store_true",
        help=(
            "assert that a guardian is present, the estop is reachable and "
            "the workspace is clear. Required: a simulation cannot observe "
            "these, and the skill's preconditions depend on them."
        ),
    )
    parser.add_argument(
        "--control-hz",
        type=float,
        default=50.0,
        help="cadence the simulation steps and commands at.",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=10,
        help="attempts per simulated stage. The ladder requires at least 10.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help=(
            "stream the simulated cameras to the GUI camera panel while the "
            "bench runs. The endpoints are unauthenticated."
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="address to bind the camera preview to, when --watch is used.",
    )
    parser.add_argument(
        "--cert-dir",
        type=Path,
        default=DEFAULT_CERT_DIR,
        help="directory holding the reusable self-signed cert.pem and key.pem.",
    )
    return parser.parse_args(argv)


def report_lines(report: BenchReport) -> tuple[str, ...]:
    """Render the report as the sequence of questions the bench answered."""
    lines = [
        "Embodied inner loop",
        f"  environment      {report.environment_id}",
        f"  skill            {report.skill_version_id}",
        f"  embodiment       {report.embodiment_digest} (simulated, not the G1)",
        "",
        "Calibration",
    ]
    for measurement in report.calibration.measurements:
        lines.append(
            f"  commanded {measurement.commanded_rate_rps:>5.2f} rad/s  peaked "
            f"{measurement.peak_joint_velocity_rps:>6.3f} rad/s  "
            f"(budget {report.calibration.budget_rps:.3f})"
        )
    for finding in report.calibration.findings:
        lines.append(f"  finding: {finding}")
    admitted = report.calibration.admitted
    lines.append(
        "  admitted         none"
        if admitted is None
        else f"  admitted         {admitted.commanded_rate_rps} rad/s"
    )
    if report.goal is not None:
        lines.append(
            f"  goal tolerance   {report.goal.tolerance_rad:.4f} rad"
        )
    if report.required_duration_s is not None:
        lines.append(
            f"  move duration    {report.required_duration_s:.2f} s"
        )

    lines.extend(["", "Stages"])
    if not report.stages:
        lines.append("  none attempted")
    for stage in report.stages:
        lines.append(
            f"  {stage.stage:<18} {stage.successes}/{stage.executed_attempts} "
            f"of {stage.planned_attempts} planned, halted {stage.halted}"
        )
        if not stage.next_stage_admitted:
            for reason in stage.next_stage_blocking_reasons:
                lines.append(f"    blocked: {reason}")

    lines.extend(["", f"Halted: {report.halted}", f"  {report.halt_detail}"])
    lines.extend(["", "Before a person stands next to a moving robot"])
    for reason in report.blocking_hardware:
        lines.append(f"  - {reason}")
    if report.stages:
        lines.extend(["", "What no simulated run covers"])
        for item in report.stages[-1].fidelity.unrepresented:
            lines.append(f"  - {item}")
    return tuple(lines)


def run(arguments: argparse.Namespace) -> int:
    """Assemble the environment, run the bench, print what it concluded."""
    if not arguments.declare_supervised:
        raise SystemExit(
            "refusing to run: the skill requires a guardian, a reachable "
            "estop and a clear workspace, and a simulation cannot observe "
            "any of them. Pass --declare-supervised to assert them yourself."
        )
    if arguments.control_hz <= 0:
        raise SystemExit("--control-hz must be positive")

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

    frames: Optional[FrameBus] = None
    server: Optional[PreviewServer] = None
    if arguments.watch:
        frames = FrameBus()
        server = PreviewServer(
            frames,
            tuple(CAMERA_SLOTS.values()),
            host=arguments.host,
            cert_dir=arguments.cert_dir,
        )
        try:
            server.run_in_thread()
        except OSError as error:
            robot.close()
            raise SystemExit(
                f"cannot serve the camera preview: {error}"
            ) from error
        print(f"GUI robot address: {arguments.host}")
        for endpoint in server.endpoints:
            print(f"  {endpoint.slot_id:<11} {endpoint.url}")
        print(f"\nWARNING: {PREVIEW_SECURITY_NOTICE}\n")

    plan = BenchPlan(
        skill=SKILL,
        goal_offsets_rad=GOAL_OFFSETS_RAD,
        satisfies=("at_reviewed_pose",),
        envelope=ENVELOPE,
        candidate_rates_rps=CANDIDATE_RATES_RPS,
        environment_id=ENVIRONMENT_ID,
        end_effector="dex1_1",
        control_authority="arm_and_gripper",
        camera_map=CAMERA_MAP,
        attempts_per_stage=arguments.attempts,
    )

    try:
        report = run_bench(robot, plan, frames=frames)
    finally:
        if server is not None:
            server.shutdown()
        robot.close()

    print("\n".join(report_lines(report)))
    return 0 if report.halted == HALTED_COMPLETED else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point."""
    return run(parse_arguments(argv))


if __name__ == "__main__":
    raise SystemExit(main())
