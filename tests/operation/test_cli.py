from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vegapunk.operation.target import HAND_DIM, STAND_BODY

_REPO = Path(__file__).resolve().parents[2]
_T0 = 1_766_838_846_271


def _load_cli():
    """Load the operator entry point by path.

    The repository's own ``scripts`` directory is shadowed on this machine by a
    ROS-installed package of the same name, so a plain import would resolve to
    the wrong one. Loading by path is not a workaround for a defect here -- it
    is the only correct way to reach this file.
    """
    path = _REPO / "scripts" / "run_operation.py"
    spec = importlib.util.spec_from_file_location("_run_operation_cli", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _item(index: int):
    stamp = _T0 + index * 33
    return {
        "idx": index,
        "rgb": f"rgb/{index:06d}.jpg",
        "t_img": stamp,
        "state_body": [0.0] * 34,
        "state_hand_left": [0.0] * HAND_DIM,
        "state_hand_right": [0.0] * HAND_DIM,
        "state_neck": None,
        "t_state": None,
        "action_body": list(STAND_BODY),
        "action_hand_left": [0.0] * HAND_DIM,
        "action_hand_right": [0.0] * HAND_DIM,
        "action_neck": [0.0, 0.0],
        "t_action": stamp,
    }


def _tree(root: Path, frames: int = 60) -> Path:
    directory = root / "session" / "episode_0000"
    (directory / "rgb").mkdir(parents=True, exist_ok=True)
    items = [_item(index) for index in range(frames)]
    (directory / "data.json").write_text(
        json.dumps(
            {
                "info": {"version": "1.0.0", "image": {"fps": 30}},
                "text": {"goal": "walk ahead and pick a box."},
                "data": items,
            }
        )
    )
    for item in items:
        (directory / str(item["rgb"])).write_bytes(b"\xff\xd8\xff")
    return root


def _run(argv: list[str]) -> tuple[int, str]:
    cli = _load_cli()
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli.main(argv)
    return code, buffer.getvalue()


class ConvertCommandTest(unittest.TestCase):
    def test_convert_reports_the_provenance_gaps_rather_than_a_score(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree = _tree(Path(tmp) / "tree")

            code, output = _run(["convert", "--tree", str(tree)])

            self.assertEqual(code, 0)
            self.assertIn("NOT training-grade", output)
            self.assertIn("wrist", output)


class DryRunTest(unittest.TestCase):
    """The dry run is the end-to-end proof that the seams meet."""

    def test_a_dry_run_executes_every_tick_with_no_robot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree = _tree(Path(tmp) / "tree")
            out = Path(tmp) / "episodes"

            code, output = _run(
                [
                    "dryrun",
                    "--tree",
                    str(tree),
                    "--out",
                    str(out),
                    "--episode-id",
                    "e2e",
                    "--ticks",
                    "40",
                ]
            )

            self.assertEqual(code, 0)
            self.assertIn("ticks executed: 40", output)
            self.assertIn("safety events: none", output)

    def test_the_dry_run_leaves_a_replayable_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree = _tree(Path(tmp) / "tree")
            out = Path(tmp) / "episodes"

            _run(
                [
                    "dryrun",
                    "--tree",
                    str(tree),
                    "--out",
                    str(out),
                    "--episode-id",
                    "e2e",
                    "--ticks",
                    "20",
                ]
            )

            directory = out / "e2e"
            manifest = json.loads((directory / "manifest.json").read_text())
            frames = [
                json.loads(line)
                for line in (directory / "frames.jsonl").read_text().splitlines()
                if line.strip()
            ]

            self.assertEqual(manifest["frame_count"], 20)
            self.assertEqual(len(frames), 20)
            # 'unobserved', not 'open': the witness is consulted only when the
            # gate is in play, so an approach frame records that nobody looked
            # at the lid rather than claiming a reading that was never taken.
            self.assertEqual(frames[0]["lid"], "unobserved")
            self.assertEqual(frames[0]["monitor_decision"], "pass")
            self.assertFalse(frames[0]["holding"])


class PourGateTest(unittest.TestCase):
    """The one gate, proven in both directions.

    The recorded episodes never reach a pour posture -- they are 'walk ahead and
    pick a box' -- so the CLI injects one. Without the injection a passing test
    here would only prove that a run which never pours is never vetoed.
    """

    def _run_gate(self, tmp: Path, *, lid_closed: bool) -> str:
        tree = _tree(Path(tmp) / "tree")
        argv = [
            "dryrun",
            "--tree",
            str(tree),
            "--out",
            str(Path(tmp) / "episodes"),
            "--episode-id",
            "gate",
            "--ticks",
            "40",
            "--inject-pour-at",
            "10",
        ]
        if lid_closed:
            argv.append("--lid-closed")
        code, output = _run(argv)
        self.assertEqual(code, 0)
        return output

    def test_a_closed_lid_vetoes_the_injected_pour(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = self._run_gate(Path(tmp), lid_closed=True)

            self.assertIn("hold_monitor_veto", output)
            self.assertIn("the lid is closed", output)
            self.assertIn("ticks executed: 10", output)

    def test_an_open_lid_lets_the_same_pour_through(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = self._run_gate(Path(tmp), lid_closed=False)

            self.assertIn("ticks executed: 40", output)
            self.assertIn("safety events: none", output)


class ReadinessTest(unittest.TestCase):
    def test_readiness_names_the_physical_acts_it_is_waiting_on(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree = _tree(Path(tmp) / "tree")

            code, output = _run(["readiness", "--tree", str(tree)])

            self.assertEqual(code, 0)
            self.assertIn("NEEDS A HUMAN", output)
            self.assertIn("patch_twist2_deadman", output)
            # The instrument reports nothing, so the witness item names the
            # physical act -- placing and calibrating a bench camera -- rather
            # than a class the operator would have to go look up.
            self.assertIn("bench camera", output)


if __name__ == "__main__":
    unittest.main()
