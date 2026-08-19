"""The vision encoder: recorded views become the features a policy sees.

``learn.ImageEncoder`` is a seam with an inert default, and an inert default was
the right thing to ship first -- it keeps the network shape honest before an
encoder exists, and it is obviously producing nothing. But a blind policy cannot
author root motion from vision, and root motion from vision is the premise of
this whole loop. This module closes that gap.

``ViewReference``   one named view inside one recorded file, with its crop
``load_view``       reference -> pixels; the only place decoding happens
``ResNet18Trunk``   the trunk, in plain torch, from cached ImageNet weights
``VisionEncoder``   the ``ImageEncoder`` the dataset and the served policy share

Three decisions worth stating.

**One decoder, both paths.** Training reads JPEGs from disk; serving reads frames
from a camera. The classic way a policy that trained well fails on the robot is
that those two paths preprocess differently and nothing raises. So both arrive
here: ``load_view`` is the only place a reference becomes pixels, and ``encode``
accepts either references or arrays already in memory.

**The trunk is frozen by default.** Six episodes of one room is far too little to
fine-tune 11M parameters without memorising the carpet, and that failure is
invisible: training loss falls and the policy has learned this room. Frozen
ImageNet features are weaker and honest, and unfreezing becomes a decision with a
number attached rather than a default.

**ResNet-18 is written out here rather than imported.** ``torchvision`` is not
installed on this machine, and the cached checkpoint is a plain state dict, so
the trunk is defined against ``torch.nn`` alone. That costs about forty lines and
removes a dependency from the one path that has to run next to a robot; the
alternative is a policy that cannot be served because an unrelated package is
missing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

DEFAULT_RESNET18_CACHE = (
    Path.home() / ".cache/torch/hub/checkpoints/resnet18-f37072fd.pth"
)
"""Where torch's hub cache holds ImageNet ResNet-18 on this machine.

Named rather than downloaded. The actuation path must not require network
access, and weights that appear by download are weights whose provenance nobody
recorded.
"""

RESNET18_FEATURE_DIM = 512

DEFAULT_INPUT_SIZE = 224

_REFERENCE = re.compile(
    r"^(?P<path>.+?)#(?P<x0>\d+),(?P<y0>\d+),(?P<x1>\d+),(?P<y1>\d+)$"
)


def _require_torch():
    try:
        import torch  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "the vision encoder requires torch. The contract, bridge, monitor "
            "and session do not."
        ) from exc
    return torch


@dataclass(frozen=True)
class ViewReference:
    """One view: a file, and the box inside it that is this view.

    Parsing is strict. A reference with no crop raises rather than defaulting to
    the whole image, because on this recorder the whole image is a stereo pair
    and treating it as one view is precisely the mistake this type prevents.
    """

    path: Path
    box: tuple[int, int, int, int]

    @classmethod
    def parse(cls, reference: str) -> "ViewReference":
        match = _REFERENCE.match(str(reference))
        if match is None:
            raise ValueError(
                f"{reference!r} is not a view reference. Expected "
                "'path#x0,y0,x1,y1': a bare path is ambiguous because one "
                "recorded file holds two views side by side."
            )
        box = (
            int(match.group("x0")),
            int(match.group("y0")),
            int(match.group("x1")),
            int(match.group("y1")),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError(f"{reference!r} carries an empty crop")
        return cls(path=Path(match.group("path")), box=box)

    @property
    def width(self) -> int:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]


def load_view(reference: str, *, size: int = DEFAULT_INPUT_SIZE):
    """Decode one view and return it as CHW float32 in [0, 1].

    Resizing uses area interpolation because these views are being shrunk by
    roughly a factor of three, and area is the resampling that does not alias
    high-frequency detail into the features. A policy trained on aliased edges
    and served on differently-aliased edges is a policy that fails for a reason
    nobody can see in the loss.
    """
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    view = ViewReference.parse(reference)
    image = cv2.imread(str(view.path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"could not read {view.path}")
    x0, y0, x1, y1 = view.box
    if image.shape[0] < y1 or image.shape[1] < x1:
        raise ValueError(
            f"{view.path} is {image.shape[1]}x{image.shape[0]}, too small for "
            f"crop {view.box}"
        )
    crop = image[y0:y1, x0:x1]
    resized = cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)
    rgb = resized[:, :, ::-1].astype(np.float32) / 255.0
    return np.ascontiguousarray(rgb.transpose(2, 0, 1))


class ResNet18Trunk:
    """ImageNet ResNet-18 up to global pooling, built from ``torch.nn`` alone.

    Only the trunk: the 1000-class head is dropped, so the output is the 512
    features that follow global average pooling. Those are what a control policy
    wants -- the classifier's job was to collapse them into categories, which is
    the opposite of what is needed here.
    """

    def __init__(
        self,
        *,
        weights: Optional[Path] = DEFAULT_RESNET18_CACHE,
        frozen: bool = True,
    ) -> None:
        torch = _require_torch()
        from torch import nn  # noqa: PLC0415

        def block(inp: int, out: int, stride: int) -> nn.Module:
            class Basic(nn.Module):
                def __init__(self) -> None:
                    super().__init__()
                    self.conv1 = nn.Conv2d(
                        inp, out, 3, stride=stride, padding=1, bias=False
                    )
                    self.bn1 = nn.BatchNorm2d(out)
                    self.conv2 = nn.Conv2d(out, out, 3, padding=1, bias=False)
                    self.bn2 = nn.BatchNorm2d(out)
                    self.relu = nn.ReLU(inplace=True)
                    self.downsample = (
                        nn.Sequential(
                            nn.Conv2d(inp, out, 1, stride=stride, bias=False),
                            nn.BatchNorm2d(out),
                        )
                        if stride != 1 or inp != out
                        else None
                    )

                def forward(self, x):  # noqa: ANN001, ANN201
                    identity = x if self.downsample is None else self.downsample(x)
                    y = self.relu(self.bn1(self.conv1(x)))
                    y = self.bn2(self.conv2(y))
                    return self.relu(y + identity)

            return Basic()

        model = nn.Module()
        model.conv1 = nn.Conv2d(3, 64, 7, stride=2, padding=3, bias=False)
        model.bn1 = nn.BatchNorm2d(64)
        model.relu = nn.ReLU(inplace=True)
        model.maxpool = nn.MaxPool2d(3, stride=2, padding=1)
        model.layer1 = nn.Sequential(block(64, 64, 1), block(64, 64, 1))
        model.layer2 = nn.Sequential(block(64, 128, 2), block(128, 128, 1))
        model.layer3 = nn.Sequential(block(128, 256, 2), block(256, 256, 1))
        model.layer4 = nn.Sequential(block(256, 512, 2), block(512, 512, 1))
        model.avgpool = nn.AdaptiveAvgPool2d(1)

        def forward(x):  # noqa: ANN001, ANN201
            y = model.maxpool(model.relu(model.bn1(model.conv1(x))))
            y = model.layer4(model.layer3(model.layer2(model.layer1(y))))
            return torch.flatten(model.avgpool(y), 1)

        model.forward = forward  # type: ignore[assignment]

        self._loaded_from = ""
        if weights is not None and Path(weights).exists():
            state = torch.load(Path(weights), map_location="cpu", weights_only=True)
            state = {
                key: value
                for key, value in state.items()
                if not key.startswith("fc.")
            }
            missing, unexpected = model.load_state_dict(state, strict=False)
            if unexpected:
                raise ValueError(
                    f"{weights} carries unexpected parameters for this trunk: "
                    f"{sorted(unexpected)[:4]}"
                )
            if missing:
                raise ValueError(
                    f"{weights} is missing parameters this trunk needs: "
                    f"{sorted(missing)[:4]}"
                )
            self._loaded_from = str(weights)

        model.eval()
        if frozen:
            for parameter in model.parameters():
                parameter.requires_grad_(False)
        self._model = model
        self._frozen = frozen

    @property
    def module(self):  # noqa: ANN201
        return self._model

    @property
    def frozen(self) -> bool:
        return self._frozen

    @property
    def pretrained(self) -> bool:
        return bool(self._loaded_from)

    @property
    def identity(self) -> str:
        origin = "imagenet" if self.pretrained else "random"
        state = "frozen" if self._frozen else "finetuned"
        return f"resnet18[{origin},{state}]"

    def features(self, batch):  # noqa: ANN001, ANN201
        torch = _require_torch()
        with torch.no_grad() if self._frozen else _nullcontext():
            return self._model.forward(batch)


class _nullcontext:
    def __enter__(self):  # noqa: ANN204
        return None

    def __exit__(self, *exc: object) -> bool:
        return False


class VisionEncoder:
    """The ``ImageEncoder`` the dataset and the served policy both use.

    Views are encoded in a fixed order and concatenated, because a policy that
    received its left and right views in varying order would have to learn both
    arrangements and would get neither right. The order is part of the
    checkpoint's identity for the same reason the normalizer is.
    """

    def __init__(
        self,
        views: Sequence[str],
        *,
        trunk: Optional[ResNet18Trunk] = None,
        size: int = DEFAULT_INPUT_SIZE,
        cache: bool = True,
    ) -> None:
        if not views:
            raise ValueError("an encoder with no views encodes nothing")
        self._views = tuple(views)
        self._trunk = trunk or ResNet18Trunk()
        self._size = size
        self._cache: dict[str, list[float]] = {} if cache else {}
        self._caching = cache
        self._decoded = 0
        self._cache_hits = 0

    @property
    def views(self) -> tuple[str, ...]:
        return self._views

    @property
    def input_size(self) -> int:
        """The square size every view is resized to before the trunk.

        Part of the checkpoint's identity: a policy trained on 224 px crops and
        served 128 px ones receives a different observation than it learned, and
        every tensor shape still matches.
        """
        return self._size

    @property
    def feature_dim(self) -> int:
        return RESNET18_FEATURE_DIM * len(self._views)

    @property
    def identity(self) -> str:
        return f"{self._trunk.identity}x{len(self._views)}@{self._size}"

    @property
    def decoded_views(self) -> int:
        return self._decoded

    @property
    def cache_hits(self) -> int:
        return self._cache_hits

    def _normalize(self, array):  # noqa: ANN001, ANN201
        import numpy as np  # noqa: PLC0415

        mean = np.asarray(IMAGENET_MEAN, dtype=np.float32).reshape(3, 1, 1)
        std = np.asarray(IMAGENET_STD, dtype=np.float32).reshape(3, 1, 1)
        return (array - mean) / std

    def encode(self, images) -> list[float]:  # noqa: ANN001
        """Features for one observation, in this encoder's view order.

        A missing view is an error rather than a zero vector. Silently encoding
        absence as zeros would let a wrist camera fail mid-episode and produce a
        dataset in which "camera dead" and "nothing there" are the same input.
        """
        torch = _require_torch()
        import numpy as np  # noqa: PLC0415

        row: list[float] = []
        for name in self._views:
            if name not in images:
                raise KeyError(
                    f"this encoder needs view {name!r}; the observation carries "
                    f"{sorted(images)}"
                )
            value = images[name]
            if isinstance(value, str):
                if self._caching and value in self._cache:
                    self._cache_hits += 1
                    row.extend(self._cache[value])
                    continue
                array = load_view(value, size=self._size)
                self._decoded += 1
            else:
                array = np.asarray(value, dtype=np.float32)
                if array.ndim != 3 or array.shape[0] != 3:
                    raise ValueError(
                        f"view {name!r} must be CHW with 3 channels, got "
                        f"{array.shape}"
                    )
            batch = torch.tensor(
                self._normalize(array)[None, ...], dtype=torch.float32
            )
            features = self._trunk.features(batch)[0].tolist()
            if isinstance(value, str) and self._caching:
                self._cache[value] = features
            row.extend(features)
        return row
