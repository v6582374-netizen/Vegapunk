#!/usr/bin/env python3
"""Install the automatic dead-man into the vendored TWIST2 real-robot loop.

The Embodied Operation Harness makes one guarantee it cannot make from outside
the vendored checkout: that the 50 Hz loop keeping this robot upright always has
a frame to execute, and never exits because a producer stopped.

As shipped, that loop does the opposite. It reads four Redis keys and calls
``json.loads`` on whatever came back. A missing key returns ``None``,
``json.loads(None)`` raises ``TypeError``, the blanket handler around the loop
catches it, and the path out is a ``close()`` whose implementation is ``exit()``.
So a producer that dies does not stop the robot -- it kills the process that was
balancing it. On a standing biped that is a fall.

This script replaces exactly that read block with one call to
``vegapunk.operation.deploy.TrackerLoopAdapter``, which resolves an absent,
expired, out-of-order or unreadable frame to the Safe Hold Target instead: the
vendored stand pose for the body, the last commanded aperture for the hands.
Everything downstream of the replaced lines is untouched, because the adapter
returns the vendored shapes -- 35 body values and six per hand.

It is idempotent, it writes a ``.orig`` backup, and ``--check`` reports without
writing. Run it against the checkout that ``sim2real.sh`` launches.

    python3 scripts/patch_twist2_deadman.py --check
    python3 scripts/patch_twist2_deadman.py
    python3 scripts/patch_twist2_deadman.py --revert
"""

from __future__ import annotations

import argparse
import difflib
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vegapunk.operation.deploy import PATCH_ANCHOR  # noqa: E402

DEFAULT_TARGET = Path.home() / "TWIST2-master" / "deploy_real" / "server_low_level_g1_real.py"

MARKER = "# --- vegapunk.operation dead-man ---"

CONSTRUCTION = """\
# --- vegapunk.operation dead-man ---
# The guard runs here, inside the loop that balances the robot, because a
# watchdog living in the publisher cannot fire when the publisher is what
# failed. See vegapunk/operation/deploy.py.
import sys as _sys
if {repo!r} not in _sys.path:
    _sys.path.insert(0, {repo!r})
from vegapunk.operation.deploy import TrackerLoopAdapter
self.target_adapter = TrackerLoopAdapter(self.redis_client)
# --- end vegapunk.operation dead-man ---
"""

REPLACEMENT = """\
# --- vegapunk.operation dead-man ---
# Was: four bare Redis reads fed straight into json.loads, where a missing key
# raised and the loop's blanket handler exited the process that was keeping this
# robot standing. The adapter never raises and never returns nothing: a lapsed,
# expired, reordered or unreadable frame becomes the Safe Hold Target.
(
    action_mimic,
    adapter_hand_left,
    adapter_hand_right,
    target_holding,
) = self.target_adapter.next_target()
action_neck = [0.0, 0.0]
if target_holding and self.target_adapter.hold_ticks % 50 == 1:
    print(f"[dead-man] holding: {self.target_adapter.hold_reason}")
# --- end vegapunk.operation dead-man ---
"""

HAND_REPLACEMENT = """\
if self.use_hand:
    action_hand_left = np.array(adapter_hand_left, dtype=np.float32)[:6]
    action_hand_right = np.array(adapter_hand_right, dtype=np.float32)[:6]
else:
    action_hand_left = np.zeros(6, dtype=np.float32)
    action_hand_right = np.zeros(6, dtype=np.float32)
"""


def _find_read_block(lines: list[str]) -> tuple[int, int]:
    """Locate the vendored target-read block by its anchor."""
    start = None
    for index, line in enumerate(lines):
        if PATCH_ANCHOR in line:
            start = index
            break
    if start is None:
        raise SystemExit(
            f"could not find the vendored read block (anchor: {PATCH_ANCHOR!r}).\n"
            "The vendored file has changed. Re-read it and update "
            "PATCH_ANCHOR in vegapunk/operation/deploy.py rather than "
            "loosening this search."
        )
    end = start
    for index in range(start, min(start + 20, len(lines))):
        if "action_neck = json.loads" in lines[index]:
            end = index
            break
    else:
        raise SystemExit(
            "found the anchor but not the end of the read block "
            "('action_neck = json.loads'). Refusing to guess."
        )
    return start, end


def _indent_of(line: str) -> str:
    """The leading whitespace of a line of vendored code.

    Replacement blocks are stored at zero indent and re-indented to match the
    code they replace. Hardcoding an indent would silently produce an
    ``IndentationError`` the first time the vendored file's nesting changes --
    in a file that is only ever run beside a live robot.
    """
    return line[: len(line) - len(line.lstrip())]


def _reindent(block: str, indent: str) -> str:
    out = []
    for line in block.splitlines():
        out.append(indent + line if line.strip() else line)
    return "\n".join(out) + "\n"


def _is_code(line: str, statement: str) -> bool:
    """Whether ``line`` is that statement as live code rather than a comment.

    The vendored block carries commented-out copies of the very statements this
    script searches for -- ``#action_hand_right = np.zeros(6, ...)`` sits three
    lines above the real one. Matching a comment ends the replaced range early
    and orphans the ``else:`` that follows, which is a syntax error in a file
    that is only ever run next to a live robot. So the search matches code only.
    """
    return line.lstrip().startswith(statement)


def _find_hand_block(lines: list[str]) -> tuple[int, int]:
    """Locate the whole vendored ``if self.use_hand:`` / ``else:`` statement.

    Both branches are replaced together. Replacing only the ``if`` body would
    leave a dangling ``else`` whose two live statements assign the same values
    the replacement already assigns, and the duplication would drift.
    """
    for index, line in enumerate(lines):
        if not _is_code(line, "action_hand_left = np.array(action_hand_left"):
            continue
        start = index
        while start > 0 and "if self.use_hand:" not in lines[start]:
            start -= 1
        end = index
        for probe in range(index, min(index + 14, len(lines))):
            if _is_code(lines[probe], "action_hand_right = np.zeros(6"):
                end = probe
                break
        else:
            raise SystemExit(
                "found the hand block's if-branch but not the end of its "
                "else-branch. Refusing to guess: a partial replacement here "
                "produces a file that will not import."
            )
        return start, end
    raise SystemExit("could not find the vendored hand-slicing block")


def _find_construction_point(lines: list[str]) -> int:
    """Where to build the adapter: after the Redis try/except, not inside it.

    The vendored constructor wraps its Redis setup in ``try/except Exception``
    whose handler prints "Error connecting to Redis" and exits. Building the
    adapter inside that block would report an ImportError from this repository
    as a Redis connection failure, and someone would spend an afternoon
    debugging a network problem that does not exist.

    ``self.config = Config(config_path)`` is the first statement after the
    block, and ``self.redis_client`` is live by then.
    """
    for index, line in enumerate(lines):
        if "self.config = Config(config_path)" in line:
            return index
    raise SystemExit(
        "could not find the vendored constructor's Config line, which is the "
        "insertion point after its Redis try/except. Refusing to guess."
    )


def patch(text: str) -> str:
    lines = text.splitlines(keepends=True)

    hand_start, hand_end = _find_hand_block(lines)
    hand_indent = _indent_of(lines[hand_start])
    lines[hand_start : hand_end + 1] = [_reindent(HAND_REPLACEMENT, hand_indent)]

    read_start, read_end = _find_read_block(lines)
    read_indent = _indent_of(lines[read_start])
    lines[read_start : read_end + 1] = [_reindent(REPLACEMENT, read_indent)]

    build_at = _find_construction_point(lines)
    build_indent = _indent_of(lines[build_at])
    lines.insert(
        build_at,
        _reindent(CONSTRUCTION.format(repo=str(REPO_ROOT)), build_indent),
    )

    return "".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(prog="patch_twist2_deadman")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--check", action="store_true", help="show the diff, write nothing")
    parser.add_argument("--revert", action="store_true", help="restore the .orig backup")
    args = parser.parse_args()

    target: Path = args.target
    backup = target.with_suffix(target.suffix + ".orig")

    if not target.exists():
        print(f"no such file: {target}", file=sys.stderr)
        return 2

    if args.revert:
        if not backup.exists():
            print(f"no backup to restore: {backup}", file=sys.stderr)
            return 2
        shutil.copy2(backup, target)
        print(f"restored {target} from {backup.name}")
        return 0

    original = target.read_text()
    if MARKER in original:
        print(f"already patched: {target}")
        return 0

    patched = patch(original)

    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=str(target),
            tofile=f"{target} (patched)",
        )
    )
    print(diff)

    if args.check:
        print("--check: nothing written")
        return 0

    if not backup.exists():
        shutil.copy2(target, backup)
        print(f"backup written: {backup}")
    target.write_text(patched)
    print(f"patched: {target}")
    print(
        "\nThe dead-man now runs inside the 50 Hz loop. Before trusting it on\n"
        "hardware, verify on a secured robot what actually happens when\n"
        "commanding stops -- that fact is still unmeasured."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
