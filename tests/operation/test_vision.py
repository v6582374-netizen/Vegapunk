from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vegapunk.operation.vision import (
    DEFAULT_INPUT_SIZE,
    RESNET18_FEATURE_DIM,
    ResNet18Trunk,
    ViewReference,
    VisionEncoder,
    load_view,
)


def _stereo_file(directory: Path) -> Path:
    """A 480x1280 frame whose two halves are deliberately different."""
    import numpy as np
    import cv2

    frame = np.zeros((480, 1280, 3), dtype=np.uint8)
    frame[:, :640] = 40          # left view: dark
    frame[:, 640:] = 200         # right view: bright
    frame[100:200, 100:200] = 255
    path = directory / "stereo.jpg"
    cv2.imwrite(str(path), frame)
    return path


class ViewReferenceTest(unittest.TestCase):
    def test_a_reference_carries_its_crop(self) -> None:
        view = ViewReference.parse("/tmp/a.jpg#640,0,1280,480")

        self.assertEqual(view.path, Path("/tmp/a.jpg"))
        self.assertEqual(view.box, (640, 0, 1280, 480))
        self.assertEqual((view.width, view.height), (640, 480))

    def test_a_bare_path_is_refused_rather_than_taken_whole(self) -> None:
        # The whole recorded file is a stereo pair. Defaulting to "the whole
        # image" is exactly the mistake that would feed two views to a trunk
        # expecting one.
        with self.assertRaisesRegex(ValueError, "not a view reference"):
            ViewReference.parse("/tmp/a.jpg")

    def test_an_empty_crop_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "empty crop"):
            ViewReference.parse("/tmp/a.jpg#100,0,100,480")


class LoadViewTest(unittest.TestCase):
    def test_a_view_decodes_to_normalised_chw(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _stereo_file(Path(tmp))

            array = load_view(f"{path}#0,0,640,480")

            self.assertEqual(array.shape, (3, DEFAULT_INPUT_SIZE, DEFAULT_INPUT_SIZE))
            self.assertEqual(str(array.dtype), "float32")
            self.assertGreaterEqual(float(array.min()), 0.0)
            self.assertLessEqual(float(array.max()), 1.0)

    def test_the_two_halves_decode_to_different_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _stereo_file(Path(tmp))

            left = load_view(f"{path}#0,0,640,480")
            right = load_view(f"{path}#640,0,1280,480")

            self.assertGreater(float(abs(left - right).mean()), 0.1)

    def test_a_crop_larger_than_the_file_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _stereo_file(Path(tmp))

            with self.assertRaisesRegex(ValueError, "too small for crop"):
                load_view(f"{path}#0,0,4000,480")

    def test_a_missing_file_is_refused(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_view("/tmp/definitely-not-here-4823.jpg#0,0,10,10")


class TrunkTest(unittest.TestCase):
    def test_the_trunk_reports_whether_it_loaded_pretrained_weights(self) -> None:
        trunk = ResNet18Trunk()

        # Honest either way: the identity says which, so a checkpoint trained on
        # random features can never be mistaken for one trained on ImageNet.
        self.assertIn("resnet18", trunk.identity)
        self.assertEqual(trunk.pretrained, "imagenet" in trunk.identity)

    def test_a_frozen_trunk_exposes_no_trainable_parameters(self) -> None:
        trunk = ResNet18Trunk(frozen=True)

        self.assertTrue(trunk.frozen)
        self.assertFalse(
            any(p.requires_grad for p in trunk.module.parameters())
        )

    def test_the_trunk_produces_one_feature_vector_per_image(self) -> None:
        import torch

        trunk = ResNet18Trunk()
        batch = torch.zeros(2, 3, DEFAULT_INPUT_SIZE, DEFAULT_INPUT_SIZE)

        features = trunk.features(batch)

        self.assertEqual(tuple(features.shape), (2, RESNET18_FEATURE_DIM))


class VisionEncoderTest(unittest.TestCase):
    def _encoder(self, cache: bool = True) -> VisionEncoder:
        return VisionEncoder(views=("head_left", "head_right"), cache=cache)

    def test_the_feature_dimension_is_one_vector_per_view(self) -> None:
        encoder = self._encoder()

        self.assertEqual(encoder.feature_dim, 2 * RESNET18_FEATURE_DIM)

    def test_an_encoder_with_no_views_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "encodes nothing"):
            VisionEncoder(views=())

    def test_both_views_reach_the_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _stereo_file(Path(tmp))
            encoder = self._encoder()

            features = encoder.encode(
                {
                    "head_left": f"{path}#0,0,640,480",
                    "head_right": f"{path}#640,0,1280,480",
                }
            )

            self.assertEqual(len(features), encoder.feature_dim)
            left = features[:RESNET18_FEATURE_DIM]
            right = features[RESNET18_FEATURE_DIM:]
            # If the crop were ignored, both halves would encode the same
            # pixels and these would be identical.
            self.assertNotEqual(left, right)

    def test_a_missing_view_is_refused_rather_than_zero_filled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _stereo_file(Path(tmp))
            encoder = self._encoder()

            # KeyError, not ValueError: a missing view is a lookup failure,
            # and the encoder names the view it needed.
            with self.assertRaisesRegex(KeyError, "head_right"):
                encoder.encode({"head_left": f"{path}#0,0,640,480"})

    def test_repeated_references_are_served_from_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _stereo_file(Path(tmp))
            encoder = self._encoder()
            images = {
                "head_left": f"{path}#0,0,640,480",
                "head_right": f"{path}#640,0,1280,480",
            }

            first = encoder.encode(images)
            second = encoder.encode(images)

            self.assertEqual(first, second)
            self.assertEqual(encoder.decoded_views, 2)
            self.assertEqual(encoder.cache_hits, 2)

    def test_the_identity_names_the_trunk_the_views_and_the_size(self) -> None:
        encoder = self._encoder()

        # The identity travels into the checkpoint manifest, so it has to be
        # enough to rebuild the same observation the policy learned on.
        self.assertIn("resnet18", encoder.identity)
        self.assertIn("x2", encoder.identity)
        self.assertIn(str(DEFAULT_INPUT_SIZE), encoder.identity)


if __name__ == "__main__":
    unittest.main()
