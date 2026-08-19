"""The patch script is the one thing here that edits code we do not own.

So it is tested harder than its size suggests: a script that half-patches the
loop keeping a biped upright produces a file that fails to import, and the
place that gets discovered is next to a live robot.
"""

from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "patch_twist2_deadman.py"

_VENDORED = """\
class RealTimePolicyController(object):
    def __init__(self, policy_path, config_path):
        self.redis_client = None
        try:
            self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
            self.redis_pipeline = self.redis_client.pipeline()
        except Exception as e:
            print(f"Error connecting to Redis: {e}")
            exit()

        self.config = Config(config_path)

    def run(self):
        while True:
            self.redis_pipeline.execute()

            keys = ["action_body_unitree_g1_with_hands", "action_hand_left_unitree_g1_with_hands", "action_hand_right_unitree_g1_with_hands", "action_neck_unitree_g1_with_hands"]
            for key in keys:
                self.redis_pipeline.get(key)
            redis_results = self.redis_pipeline.execute()
            action_mimic = json.loads(redis_results[0])
            action_hand_left = json.loads(redis_results[1])
            action_hand_right = json.loads(redis_results[2])
            action_neck = json.loads(redis_results[3])

            if self.use_hand:
                action_hand_left = np.array(action_hand_left, dtype=np.float32)[:6]
                action_hand_right = np.array(action_hand_right, dtype=np.float32)[:6]
                #action_hand_left = np.zeros(6, dtype=np.float32)
                #action_hand_right = np.zeros(6, dtype=np.float32)
            else:
                #action_hand_left = np.zeros(7, dtype=np.float32) brainco
                #action_hand_right = np.zeros(7, dtype=np.float32)
                action_hand_left = np.zeros(6, dtype=np.float32)
                action_hand_right = np.zeros(6, dtype=np.float32)

            obs_full = np.concatenate([action_mimic, obs_proprio])
"""


def _load():
    spec = importlib.util.spec_from_file_location("patch_twist2_deadman", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load()

    def test_the_patched_source_is_valid_python(self) -> None:
        patched = self.module.patch(_VENDORED)

        ast.parse(patched)

    def test_the_dangerous_read_block_is_gone(self) -> None:
        patched = self.module.patch(_VENDORED)

        self.assertNotIn("json.loads(redis_results", patched)
        self.assertIn("self.target_adapter.next_target()", patched)

    def test_the_adapter_is_built_outside_the_redis_try_block(self) -> None:
        """An ImportError must not be reported as a Redis connection failure."""
        patched = self.module.patch(_VENDORED)
        tree = ast.parse(patched)

        tries = [node for node in ast.walk(tree) if isinstance(node, ast.Try)]
        for node in tries:
            body = ast.dump(ast.Module(body=node.body, type_ignores=[]))
            self.assertNotIn("TrackerLoopAdapter", body)
        self.assertIn("TrackerLoopAdapter", patched)

    def test_both_hand_branches_are_replaced_together(self) -> None:
        """A dangling ``else`` is a syntax error, so the whole statement moves."""
        patched = self.module.patch(_VENDORED)

        self.assertIn("adapter_hand_left", patched)
        self.assertNotIn("np.array(action_hand_left", patched)
        # exactly one use_hand statement survives
        self.assertEqual(patched.count("if self.use_hand:"), 1)

    def test_a_commented_out_statement_is_never_matched(self) -> None:
        self.assertFalse(
            self.module._is_code(
                "                    #action_hand_right = np.zeros(6, dtype=np.float32)",
                "action_hand_right = np.zeros(6",
            )
        )
        self.assertTrue(
            self.module._is_code(
                "                action_hand_right = np.zeros(6, dtype=np.float32)",
                "action_hand_right = np.zeros(6",
            )
        )

    def test_a_moved_anchor_fails_loudly_rather_than_patching_blindly(self) -> None:
        without_anchor = _VENDORED.replace(
            'keys = ["action_body_unitree_g1_with_hands"', "keys = RENAMED_ELSEWHERE"
        )

        with self.assertRaises(SystemExit):
            self.module.patch(without_anchor)

    def test_patching_is_idempotent_via_its_marker(self) -> None:
        patched = self.module.patch(_VENDORED)

        self.assertIn(self.module.MARKER, patched)

    def test_the_real_vendored_file_still_matches_the_anchors(self) -> None:
        """If the vendored checkout drifts, this fails here rather than on hardware."""
        target = self.module.DEFAULT_TARGET
        if not target.exists():
            self.skipTest(f"vendored checkout not present: {target}")

        patched = self.module.patch(target.read_text())

        ast.parse(patched)


if __name__ == "__main__":
    unittest.main()
