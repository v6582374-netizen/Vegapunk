from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vegapunk.operation.dataset import (
    ALIGNED_BY_CLOCK,
    ALIGNED_BY_INDEX,
    DROP_BAD_TARGET,
    DROP_MISSING_IMAGE,
    DROP_SHORT_TAIL,
    ConversionReport,
    VendoredEpisode,
    convert_episode,
    convert_vendored_tree,
)
from vegapunk.operation.target import BODY_DIM, HAND_DIM, STAND_BODY

_T0 = 1_766_838_846_271


def _item(index: int, *, clock: bool = True, body=None, hands7: bool = False):
    item = {
        "idx": index,
        "rgb": f"rgb/{index:06d}.jpg",
        "t_img": _T0 + index * 33,
        "state_body": [0.0] * 34,
        "state_hand_left": [0.0] * HAND_DIM,
        "state_hand_right": [0.0] * HAND_DIM,
        "state_neck": None,
        "t_state": (_T0 + index * 33) if clock else None,
        "action_body": list(body if body is not None else STAND_BODY),
        "action_hand_left": [0.0] * (7 if hands7 else HAND_DIM),
        "action_hand_right": [0.0] * (7 if hands7 else HAND_DIM),
        "action_neck": [0.0, 0.0],
        "t_action": _T0 + index * 33,
    }
    return item


def _write_episode(
    root: Path,
    name: str,
    items,
    *,
    with_images: bool = True,
) -> Path:
    directory = root / name
    (directory / "rgb").mkdir(parents=True, exist_ok=True)
    payload = {
        "info": {"version": "1.0.0", "image": {"fps": 30}},
        "text": {"goal": "walk ahead and pick a box."},
        "data": items,
    }
    (directory / "data.json").write_text(json.dumps(payload))
    if with_images:
        for item in items:
            (directory / str(item["rgb"])).write_bytes(b"\xff\xd8\xff")
    return directory


class ReadTest(unittest.TestCase):
    def test_a_vendored_episode_reports_its_own_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = _write_episode(
                Path(tmp), "20260101_1200/episode_0001", [_item(i) for i in range(4)]
            )

            episode = VendoredEpisode(directory)

            self.assertEqual(episode.frame_count, 4)
            self.assertEqual(episode.fps, 30)
            self.assertIn("walk ahead", episode.goal)
            self.assertTrue(episode.episode_id.endswith("episode_0001"))


class ChunkTest(unittest.TestCase):
    def test_each_sample_carries_a_chunk_of_the_requested_horizon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = _write_episode(
                Path(tmp), "ep", [_item(i) for i in range(10)]
            )
            report = ConversionReport()

            samples = convert_episode(
                VendoredEpisode(directory), horizon=4, report=report
            )

            self.assertEqual([s.horizon for s in samples], [4] * 7)
            self.assertEqual(report.samples, 7)

    def test_the_tail_that_cannot_fill_a_chunk_is_dropped_not_padded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = _write_episode(
                Path(tmp), "ep", [_item(i) for i in range(5)]
            )
            report = ConversionReport()

            samples = convert_episode(
                VendoredEpisode(directory), horizon=4, report=report
            )

            self.assertEqual(len(samples), 2)
            self.assertEqual(report.dropped[DROP_SHORT_TAIL], 3)

    def test_a_chunk_is_consecutive_and_strictly_ordered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = _write_episode(
                Path(tmp), "ep", [_item(i) for i in range(8)]
            )
            report = ConversionReport()

            samples = convert_episode(
                VendoredEpisode(directory), horizon=3, report=report
            )

            for sample in samples:
                sequences = [frame.sequence for frame in sample.chunk]
                self.assertEqual(
                    sequences, list(range(sequences[0], sequences[0] + 3))
                )


class AlignmentTest(unittest.TestCase):
    def test_a_missing_state_timestamp_is_recorded_as_index_alignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = _write_episode(
                Path(tmp), "ep", [_item(i, clock=False) for i in range(6)]
            )
            report = ConversionReport()

            samples = convert_episode(
                VendoredEpisode(directory), horizon=2, report=report
            )

            self.assertTrue(all(s.alignment == ALIGNED_BY_INDEX for s in samples))
            self.assertEqual(report.index_aligned_samples, len(samples))
            self.assertFalse(samples[0].aligned_by_clock)

    def test_a_full_set_of_timestamps_aligns_by_clock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = _write_episode(
                Path(tmp), "ep", [_item(i, clock=True) for i in range(6)]
            )
            report = ConversionReport()

            samples = convert_episode(
                VendoredEpisode(directory), horizon=2, report=report
            )

            self.assertTrue(all(s.alignment == ALIGNED_BY_CLOCK for s in samples))
            self.assertEqual(report.index_aligned_samples, 0)


class RefusalTest(unittest.TestCase):
    def test_a_frame_whose_target_cannot_be_built_is_dropped_not_repaired(
        self,
    ) -> None:
        broken = list(STAND_BODY)
        broken[6] = 9.0
        items = [_item(i) for i in range(6)]
        items[2] = _item(2, body=broken)
        with tempfile.TemporaryDirectory() as tmp:
            directory = _write_episode(Path(tmp), "ep", items)
            report = ConversionReport()

            samples = convert_episode(
                VendoredEpisode(directory), horizon=2, report=report
            )

            self.assertEqual(report.dropped[DROP_BAD_TARGET], 1)
            for sample in samples:
                self.assertNotIn(
                    2, [frame.sequence for frame in sample.chunk]
                )

    def test_a_missing_image_is_dropped_because_a_blind_sample_is_not_one(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = _write_episode(
                Path(tmp), "ep", [_item(i) for i in range(6)], with_images=False
            )
            report = ConversionReport()

            samples = convert_episode(
                VendoredEpisode(directory), horizon=2, report=report
            )

            self.assertEqual(samples, [])
            self.assertEqual(report.dropped[DROP_MISSING_IMAGE], 6)

    def test_a_seven_value_hand_is_sliced_to_what_the_robot_executed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = _write_episode(
                Path(tmp), "ep", [_item(i, hands7=True) for i in range(4)]
            )
            report = ConversionReport()

            samples = convert_episode(
                VendoredEpisode(directory), horizon=2, report=report
            )

            self.assertTrue(report.seven_value_hands > 0)
            for sample in samples:
                for frame in sample.chunk:
                    self.assertEqual(len(frame.left_hand), HAND_DIM)


class ProvenanceTest(unittest.TestCase):
    def test_the_vendored_tree_is_not_training_grade_and_says_why(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_episode(
                root, "20260101_1200/episode_0001", [_item(i, clock=False) for i in range(8)]
            )

            samples, report = convert_vendored_tree(root, horizon=2)

            self.assertTrue(samples)
            self.assertFalse(report.training_grade)
            joined = " ".join(report.provenance_gaps)
            self.assertIn("wrist", joined)
            self.assertIn("witness", joined)
            self.assertIn("outcome", joined)

    def test_the_summary_names_every_drop_reason_with_a_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_episode(root, "t/e", [_item(i) for i in range(5)])

            _, report = convert_vendored_tree(root, horizon=4)

            self.assertIn(f"dropped[{DROP_SHORT_TAIL}]=3", report.summary())
            self.assertIn("NOT training-grade", report.summary())


if __name__ == "__main__":
    unittest.main()
