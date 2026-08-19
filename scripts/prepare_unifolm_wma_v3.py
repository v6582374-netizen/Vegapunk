#!/usr/bin/env python3
"""Convert the local LeRobot v3 oil-pressure recordings to UnifoLM-WMA input.

The official WMA preparation script expects an older, per-episode LeRobot
layout.  The recordings we received are LeRobot v3: each dataset stores the
tabular data and each camera as a single chunk, with episode boundaries in
``meta/episodes``.  This adapter keeps the original data untouched and emits
the directory layout consumed by ``unifolm_wma.data.wma_data.WMAData``.

Only one camera is emitted because the released WMA training pipeline uses a
single main-view camera.  Wrist cameras remain in the source dataset.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import torch
from safetensors.torch import save_file


INSTRUCTIONS = {
    "open": "Press the yellow button to open the instrument lid.",
    "move-forward": "Lift the cup and move it into the opened instrument lid.",
    "move-back": "Return the cup to its home position.",
    "close": "Press the green button to close the instrument lid.",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--target-dir", type=Path, required=True)
    parser.add_argument(
        "--dataset",
        action="append",
        dest="datasets",
        help="Dataset directory name; repeat for multiple datasets. Default: all oilpressure-* directories.",
    )
    parser.add_argument(
        "--camera",
        default="cam_left_high",
        help="One main camera from the v3 dataset, without the observation.images. prefix.",
    )
    parser.add_argument(
        "--robot-name",
        default="Unitree G1 with BrainCo Revo2",
    )
    parser.add_argument(
        "--limit-episodes",
        type=int,
        help="Optional preflight limit; omit for the complete conversion.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def dataset_instruction(name: str) -> str:
    for key, instruction in INSTRUCTIONS.items():
        if key in name:
            return instruction
    raise ValueError(f"No neutral task instruction is defined for {name!r}")


def read_table(path: Path, pattern: str) -> pd.DataFrame:
    files = sorted(path.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No parquet files matched {path / pattern}")
    return pd.concat((pd.read_parquet(file) for file in files), ignore_index=True)


def video_source(dataset_dir: Path, camera: str, episode: pd.Series) -> Path:
    key = f"videos/observation.images.{camera}"
    chunk = int(episode[f"{key}/chunk_index"])
    file_index = int(episode[f"{key}/file_index"])
    return (
        dataset_dir
        / "videos"
        / f"observation.images.{camera}"
        / f"chunk-{chunk:03d}"
        / f"file-{file_index:03d}.mp4"
    )


def encode_episode_video(
    source: Path,
    target: Path,
    episode: pd.Series,
    camera: str,
    fps: float,
) -> None:
    key = f"videos/observation.images.{camera}"
    start = float(episode[f"{key}/from_timestamp"])
    length = int(episode["length"])
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.6f}",
        "-i",
        str(source),
        "-frames:v",
        str(length),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        str(target),
    ]
    subprocess.run(command, check=True)


def save_transition(target: Path, episode_data: pd.DataFrame, robot_name: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(target, "w") as file:
        file.create_dataset(
            "observation.state",
            data=np.asarray(episode_data["observation.state"].tolist(), dtype=np.float32),
        )
        file.create_dataset(
            "action",
            data=np.asarray(episode_data["action"].tolist(), dtype=np.float32),
        )
        file.attrs["action_type"] = "joint position"
        file.attrs["state_type"] = "joint position"
        file.attrs["robot_type"] = robot_name


def save_stats(target: Path, states: list[np.ndarray], actions: list[np.ndarray]) -> None:
    state_array = np.concatenate(states, axis=0)
    action_array = np.concatenate(actions, axis=0)

    def stats(array: np.ndarray) -> dict[str, torch.Tensor]:
        tensor = torch.from_numpy(array)
        return {
            "max": tensor.max(dim=0).values,
            "min": tensor.min(dim=0).values,
            "mean": tensor.mean(dim=0),
            "std": tensor.std(dim=0),
        }

    flattened = {
        f"{group}/{name}": value
        for group, values in {
            "action": stats(action_array),
            "observation.state": stats(state_array),
        }.items()
        for name, value in values.items()
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    save_file(flattened, str(target))


def convert_dataset(
    source: Path,
    target: Path,
    dataset_name: str,
    camera: str,
    robot_name: str,
    overwrite: bool,
    limit_episodes: int | None,
) -> dict[str, object]:
    dataset_dir = source / dataset_name
    info = json.loads((dataset_dir / "meta" / "info.json").read_text())
    if info.get("codebase_version") != "v3.0":
        raise ValueError(f"{dataset_name}: expected LeRobot v3.0")

    episodes = read_table(dataset_dir / "meta" / "episodes", "chunk-*/*.parquet")
    data = read_table(dataset_dir / "data", "chunk-*/*.parquet")
    data = data.sort_values(["episode_index", "frame_index"])

    feature_key = f"observation.images.{camera}"
    if feature_key not in info["features"]:
        raise ValueError(f"{dataset_name}: camera {camera!r} is not present")

    target_videos = target / "videos" / dataset_name / camera
    target_transitions = target / "transitions" / dataset_name
    rows: list[dict[str, object]] = []
    states: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    fps = float(info["fps"])
    instruction = dataset_instruction(dataset_name)

    ordered_episodes = episodes.sort_values("episode_index")
    if limit_episodes is not None:
        ordered_episodes = ordered_episodes.head(limit_episodes)

    for episode_index, episode in ordered_episodes.iterrows():
        episode_id = int(episode["episode_index"])
        episode_data = data[data["episode_index"] == episode_id]
        if len(episode_data) != int(episode["length"]):
            raise ValueError(
                f"{dataset_name} episode {episode_id}: metadata length {episode['length']} "
                f"does not match data rows {len(episode_data)}"
            )

        video_target = target_videos / f"{episode_id}.mp4"
        transition_target = target_transitions / f"{episode_id}.h5"
        if not overwrite and (video_target.exists() or transition_target.exists()):
            raise FileExistsError(
                f"Output already exists for {dataset_name} episode {episode_id}; use --overwrite"
            )

        encode_episode_video(
            video_source(dataset_dir, camera, episode),
            video_target,
            episode,
            camera,
            fps,
        )
        save_transition(transition_target, episode_data, robot_name)
        states.append(np.asarray(episode_data["observation.state"].tolist(), dtype=np.float32))
        actions.append(np.asarray(episode_data["action"].tolist(), dtype=np.float32))
        rows.append(
            {
                "videoid": episode_id,
                "contentUrl": "x",
                "duration": float(episode["length"]) / fps,
                "data_dir": f"{dataset_name}/{camera}",
                "instruction": instruction,
                "dynamic_confidence": "x",
                "dynamic_wording": "x",
                "dynamic_source_category": "x",
                "embodiment": robot_name,
            }
        )

    save_stats(target_transitions / "meta_data" / "stats.safetensors", states, actions)
    pd.DataFrame(rows).to_csv(target / f"{dataset_name}.csv", index=False)
    return {
        "dataset": dataset_name,
        "episodes": len(rows),
        "frames": int(sum(len(state) for state in states)),
        "camera": camera,
        "instruction": instruction,
    }


def main() -> None:
    args = parse_args()
    dataset_names = args.datasets or sorted(
        path.name for path in args.source_dir.glob("oilpressure-*") if path.is_dir()
    )
    if not dataset_names:
        raise SystemExit("No oilpressure-* LeRobot v3 datasets found")

    summaries = [
        convert_dataset(
            args.source_dir,
            args.target_dir,
            dataset_name,
            args.camera,
            args.robot_name,
            args.overwrite,
            args.limit_episodes,
        )
        for dataset_name in dataset_names
    ]
    manifest = {
        "source_dir": str(args.source_dir),
        "target_dir": str(args.target_dir),
        "camera": args.camera,
        "robot_name": args.robot_name,
        "datasets": summaries,
        "note": "Generated from LeRobot v3 without liquid-transfer semantics.",
    }
    args.target_dir.mkdir(parents=True, exist_ok=True)
    (args.target_dir / "conversion_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
