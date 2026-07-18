"""Fake Launch runner for Admin Console tests.

Behaves like a real Discovery Launch at the process boundary: writes logs
and artifacts into the launch directory, then records its outcome, without
calling any model. Behavior is controlled by environment variables:

- ``FAKE_RUNNER_SLEEP``: seconds to stay "running" (default 0).
- ``FAKE_RUNNER_OUTCOME``: ``completed`` (default) or ``failed``.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    task_dir = Path(sys.argv[1])
    launch_dir = Path(sys.argv[2])
    launch_dir.mkdir(parents=True, exist_ok=True)
    (launch_dir / "runner_argv.json").write_text(json.dumps(sys.argv[1:]))

    log = launch_dir / "console.log"
    with log.open("a", encoding="utf-8") as stream:
        stream.write(f"fake runner started for task {task_dir.name}\n")

    time.sleep(float(os.environ.get("FAKE_RUNNER_SLEEP", "0")))

    (launch_dir / "ideas.json").write_text(json.dumps([{"idea": "fake"}]))

    outcome = os.environ.get("FAKE_RUNNER_OUTCOME", "completed")
    (launch_dir / "launch_outcome.json").write_text(json.dumps({"outcome": outcome}))
    with log.open("a", encoding="utf-8") as stream:
        stream.write(f"fake runner finished with outcome {outcome}\n")
    return 0 if outcome == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
