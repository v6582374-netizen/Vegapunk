#!/usr/bin/env python3
"""Watch the simulated G1's cameras in the GUI's camera panel.

This runs the simulation on the main thread, because MuJoCo renders only on the
thread owning its GL context, and streams from a background event loop that
reads finished frames from ``FrameBus``. Paste the printed host into the GUI's
robot-address field; the panel derives the three fixed camera ports itself.

The robot does not move. The loop commands the standing keyframe so the physics
and the cameras advance, and it never runs the governed execution loop, so this
session is not evidence about anything. Supervision is declared as unsupervised
for the same reason: a preview must not be able to satisfy a safety
precondition on a human's behalf.

Security: the camera endpoints are unauthenticated and the TLS certificate is
self-signed. Anyone who can reach the ports can watch. The default bind host is
loopback; exposing the preview to a network is an explicit argument.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vegapunk.embodied.preview import (
    DEFAULT_CERT_DIR,
    DEFAULT_PREVIEW_FPS,
    DEFAULT_PREVIEW_HOST,
    PREVIEW_SECURITY_NOTICE,
    PreviewServer,
)
from vegapunk.embodied.simulation import (
    CAMERA_SLOTS,
    FrameBus,
    SimulatedG1,
    SimulatedSupervision,
)

_UNSUPERVISED = SimulatedSupervision(
    guardian_present=False,
    estop_engaged=False,
    estop_reachable=False,
    workspace_clear=True,
)


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Read the preview's bind host, frame rate and certificate directory."""
    parser = argparse.ArgumentParser(
        prog="run_embodied_sim_preview",
        description="Stream the simulated G1's cameras to the GUI camera panel.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_PREVIEW_HOST,
        help=(
            "address to bind. Defaults to loopback; use the machine's LAN "
            "address only on a network you trust, since the cameras are "
            "unauthenticated."
        ),
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=DEFAULT_PREVIEW_FPS,
        help="frames per second to render and stream per camera.",
    )
    parser.add_argument(
        "--cert-dir",
        type=Path,
        default=DEFAULT_CERT_DIR,
        help="directory holding the reusable self-signed cert.pem and key.pem.",
    )
    parser.add_argument(
        "--control-hz",
        type=float,
        default=50.0,
        help="simulation control frequency.",
    )
    return parser.parse_args(argv)


def announce(server: PreviewServer, host: str) -> None:
    """Print the addresses to paste into the GUI, and the security warning."""
    print("Simulated G1 camera preview")
    for endpoint in server.endpoints:
        slot = CAMERA_SLOTS[endpoint.slot_id]
        print(
            f"  {endpoint.slot_id:<11} {slot.width}x{slot.height}  {endpoint.url}"
        )
    print(f"\nGUI robot address: {host}")
    print("The browser must accept the self-signed certificate once per port.")
    print(f"\nWARNING: {PREVIEW_SECURITY_NOTICE}\n")


def run(arguments: argparse.Namespace) -> int:
    """Stream until interrupted, rendering on the thread that owns MuJoCo."""
    if arguments.fps <= 0:
        raise SystemExit("--fps must be positive")
    frames = FrameBus()
    robot = SimulatedG1(
        supervision=_UNSUPERVISED,
        control_frequency_hz=arguments.control_hz,
    )
    server = PreviewServer(
        frames,
        tuple(CAMERA_SLOTS.values()),
        host=arguments.host,
        fps=arguments.fps,
        cert_dir=arguments.cert_dir,
    )
    try:
        server.run_in_thread()
    except OSError as error:
        robot.close()
        raise SystemExit(f"cannot serve the camera preview: {error}") from error

    announce(server, arguments.host)
    stand = robot.stand_positions_rad
    render_period_s = 1.0 / arguments.fps
    next_render = time.monotonic()
    try:
        while True:
            started = time.monotonic()
            robot.command_joint_positions(stand)
            if started >= next_render:
                robot.publish_frames(frames)
                next_render = started + render_period_s
            remaining = robot.control_period_s - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(remaining)
    except KeyboardInterrupt:
        print("Stopping the camera preview.")
    finally:
        server.shutdown()
        robot.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return run(parse_arguments(argv))


if __name__ == "__main__":
    raise SystemExit(main())
