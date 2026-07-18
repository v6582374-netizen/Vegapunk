"""Fake Launch runner for Admin Console tests.

Behaves like a real Discovery Launch at the process boundary: writes logs
and artifacts into the launch directory, then records its outcome, without
calling any model. Behavior is controlled by environment variables:

- ``FAKE_RUNNER_SLEEP``: seconds to stay "running" (default 0).
- ``FAKE_RUNNER_OUTCOME``: ``completed`` (default) or ``failed``.
- ``FAKE_RUNNER_IGNORE_SIGTERM``: refuse graceful stop when set to ``1``.

On SIGTERM (graceful stop) it finishes its current smallest unit of work:
persists ``checkpoint.json`` and exits with code 130, like the real runner
checkpointing at an Experiment Run boundary.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path


def main() -> int:
    task_dir = Path(sys.argv[1])
    launch_dir = Path(sys.argv[2])
    launch_dir.mkdir(parents=True, exist_ok=True)
    (launch_dir / "runner_argv.json").write_text(json.dumps(sys.argv[1:]))

    log = launch_dir / "console.log"

    def write_log(text: str) -> None:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(text + "\n")

    def on_sigterm(_signum, _frame) -> None:
        if os.environ.get("FAKE_RUNNER_IGNORE_SIGTERM") == "1":
            write_log("fake runner ignoring SIGTERM")
            return
        (launch_dir / "checkpoint.json").write_text(json.dumps({"checkpoint": "unit-boundary"}))
        write_log("fake runner stopped gracefully at unit boundary")
        sys.exit(130)

    signal.signal(signal.SIGTERM, on_sigterm)

    write_log(f"fake runner started for task {task_dir.name}")

    deadline = time.monotonic() + float(os.environ.get("FAKE_RUNNER_SLEEP", "0"))
    while time.monotonic() < deadline:
        time.sleep(0.05)

    (launch_dir / "ideas.json").write_text(json.dumps([{"idea": "fake"}]))

    outcome = os.environ.get("FAKE_RUNNER_OUTCOME", "completed")
    (launch_dir / "launch_outcome.json").write_text(json.dumps({"outcome": outcome}))
    write_log(f"fake runner finished with outcome {outcome}")
    return 0 if outcome == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
