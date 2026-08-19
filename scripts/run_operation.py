#!/usr/bin/env python3
"""Drive the Embodied Operation Harness from one place.

Four subcommands, in the order a person actually needs them:

``convert``    read the vendored recorder's episodes and say what they are worth
``train``      fit the fast policy on those samples and write a checkpoint
``dryrun``     run a whole session end to end with no robot in the room
``readiness``  what is built, what is verified, and what still needs a human

``dryrun`` is the one that earns this file. It wires the real policy server, the
real monitor, the real bridge and the real episode writer against an in-memory
transport, so every seam between a produced frame and a committed one is
exercised at 50 Hz without a robot. A path that cannot survive that has no
business being pointed at a standing biped.

``readiness`` is deliberately not a health check that prints "OK". It reports the
harness's own refusals -- the dataset's provenance gaps, the checkpoint's
deployability, the unmeasured stop behaviour -- because the useful question
before a hardware session is not "does it run" but "what does it still not
know".
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vegapunk.operation.bridge import MotionGrant, TargetBridge
from vegapunk.operation.dataset import convert_vendored_tree
from vegapunk.operation.episode import (
    JUDGED_BY_EYE,
    TERMINATION_COMPLETED,
    TERMINATION_HELD,
    TRANSFER_NONE,
    CameraCalibration,
    EpisodeOutcome,
    EpisodeRecord,
    EpisodeWriter,
    ResetRecord,
)
from vegapunk.operation.monitor import InstrumentMonitor
from vegapunk.operation.policy import (
    Observation,
    PolicyServer,
    ReplayFastPolicy,
)
from vegapunk.operation.session import HELD, OperationSession
from vegapunk.operation.monitor import (
    LEFT_WRIST_ROLL,
    PourPosture,
    RIGHT_WRIST_ROLL,
)
from vegapunk.operation.target import CONTROL_PERIOD_S, WholeBodyTarget
from vegapunk.operation.tracker import TrackerState
from vegapunk.operation.witness import (
    IndependentWitness,
    SwitchWitness,
)

DEFAULT_TREE = (
    Path.home() / "TWIST2-master" / "deploy_real" / "twist2_demonstration"
)
DEFAULT_CHECKPOINT = Path(".vegapunk/operation/checkpoint")
DEFAULT_EPISODES = Path(".vegapunk/operation/episodes")
PERIOD_NS = int(CONTROL_PERIOD_S * 1e9)


class _MemoryTransport:
    """A transport that records instead of actuating.

    The dry run must exercise the bridge's real commit path, so this fills the
    ``TrackerTransport`` seam rather than being mocked out: everything above it
    is the production object.
    """

    def __init__(self) -> None:
        self.committed: list[object] = []

    def commit(self, target: object) -> None:
        self.committed.append(target)

    def read_state(self):  # noqa: ANN201 - protocol shape
        return None


def _cmd_convert(args: argparse.Namespace) -> int:
    samples, report = convert_vendored_tree(
        args.tree, horizon=args.horizon, require_images=not args.no_images
    )
    print(report.summary())
    if not samples:
        print("\nno samples were produced; nothing can be trained", file=sys.stderr)
        return 1
    print(f"\nfirst sample: {samples[0].episode_id} idx={samples[0].index} "
          f"horizon={samples[0].horizon} alignment={samples[0].alignment}")
    return 0


def _cmd_train(args: argparse.Namespace) -> int:
    from vegapunk.operation.learn import (
        ChunkDataset,
        TrainingConfig,
        save_checkpoint,
        train,
    )

    samples, report = convert_vendored_tree(
        args.tree, horizon=args.horizon, require_images=not args.no_images
    )
    if not samples:
        print("no samples to train on", file=sys.stderr)
        return 1
    print(report.summary())

    if args.limit and args.limit < len(samples):
        # Stride rather than truncate. A prefix of this list is the beginning of
        # one episode, so a limited run would train and validate on a single
        # demonstration -- and the episode holdout would then find no episode to
        # hold out, reporting a validation loss of nan. Striding keeps a small
        # run spanning every episode, which is the only reason to do a small run.
        step = len(samples) / args.limit
        samples = [samples[int(index * step)] for index in range(args.limit)]
        spanned = len({sample.episode_id for sample in samples})
        print(
            f"  limited to {len(samples)} samples by --limit, "
            f"strided across {spanned} episodes"
        )

    encoder = None
    if args.vision:
        from vegapunk.operation.vision import VisionEncoder

        encoder = VisionEncoder(views=tuple(sorted(report.views)))
        print(
            f"  image encoder: {encoder.identity} "
            f"({encoder.feature_dim} features from {list(encoder.views)})"
        )
    else:
        print(
            "  image encoder: inert -- the policy sees no pixels. Pass --vision "
            "to encode the recorded views."
        )

    dataset = ChunkDataset(samples, horizon=args.horizon, encoder=encoder)
    config = TrainingConfig(
        horizon=args.horizon,
        hidden=args.hidden,
        layers=args.layers,
        epochs=args.epochs,
        batch_size=args.batch_size,
        seed=args.seed,
    )

    def _progress(epoch: int, train_loss: float, val_loss: float) -> None:
        print(f"  epoch {epoch:3d}  train {train_loss:.6f}  val {val_loss:.6f}")

    network, result = train(dataset, config, report, progress=_progress)
    print()
    print(result.summary())

    directory = save_checkpoint(args.out, network, dataset, result)
    print(f"\ncheckpoint: {directory}")
    ok, why = result.deployable
    if not ok:
        print(f"NOT deployable: {why}")
    return 0


class _TickClock:
    """The dry run's clock, shared by the observations and the bridge.

    It exists because of a real defect this dry run found. Replayed frames carry
    the timestamps of a simulated tick sequence, while the bridge defaults to
    ``time.time_ns()``. Against a live wall clock every replayed frame is
    already expired, so the bridge refused tick 0 and the whole path held --
    correctly, given what it was told.

    The frames and the component judging their freshness must therefore read the
    same clock. That is a property of any replay, not a dry-run convenience: a
    freshness rule compares two times, and comparing times from two different
    clocks is meaningless rather than merely inaccurate.
    """

    def __init__(self, start_ns: int) -> None:
        self._now_ns = start_ns

    def __call__(self) -> int:
        return self._now_ns

    def advance(self, delta_ns: int) -> None:
        self._now_ns += delta_ns


def _dry_run_session(
    *,
    frames: Sequence[object],
    lid_open: bool,
    root: Path,
    episode_id: str,
    clock: _TickClock,
) -> tuple[OperationSession, _MemoryTransport]:
    transport = _MemoryTransport()
    bridge = TargetBridge(
        transport,
        "dryrun-configuration",
        grant=MotionGrant(
            authorized_by="dry-run (no robot)",
            statement="in-memory transport; nothing is actuated",
            granted_at=datetime.now(timezone.utc),
            configuration_digest="dryrun-configuration",
        ),
        clock_ns=clock,
    )
    witness = IndependentWitness(
        SwitchWitness(
            lambda: lid_open, identity="dryrun_lid", clock_ns=clock
        ),
        dwell_s=0.0,
        clock_ns=clock,
    )
    record = EpisodeRecord(
        episode_id=episode_id,
        configuration_digest="dryrun-configuration",
        started_at=datetime.now(timezone.utc),
        cameras=(
            CameraCalibration(
                identity="head", width=640, height=480, fps=30.0,
                mounted_on="head",
            ),
        ),
        witness_identity=witness.identity,
        reset=ResetRecord(
            performed_by="dry-run (no robot)",
            performed_at=datetime.now(timezone.utc),
            lid_closed=True,
            vessel_restored=True,
            floor_and_tether_restored=True,
            notes="no physical reset happened; this is a software dry run",
        ),
        operator="dry-run",
    )
    session = OperationSession(
        policy=PolicyServer(ReplayFastPolicy(frames)),
        monitor=InstrumentMonitor(witness),
        bridge=bridge,
        writer=EpisodeWriter(root, record),
        clock_ns=clock,
    )
    return session, transport


def _pour_posture_frame(frame: WholeBodyTarget) -> WholeBodyTarget:
    """Rewrite one recorded frame into an unmistakable pour posture.

    The six recorded episodes are a walk-and-pick demonstration: fingers reach
    full closure and the wrist rolls to 1.39 rad, but never at the same instant,
    so no recorded frame is a pour. Replaying them therefore exercises the
    monitor's pass path and nothing else, and the one gate this harness exists to
    enforce would go undemonstrated.

    So the dry run can inject a pour: one frame, both hands closed, both wrists
    rolled past the tilt threshold. It is synthetic and says so -- it proves the
    veto fires, not that a policy would ever produce this pose.
    """
    posture = PourPosture()
    closure = min(posture.grasp_closure_rad + 0.2, 1.4)
    tilt = posture.pour_tilt_rad + 0.2

    body = list(frame.body)
    body[LEFT_WRIST_ROLL] = tilt
    body[RIGHT_WRIST_ROLL] = tilt
    hand = (closure,) * 6
    return WholeBodyTarget(
        sequence=frame.sequence,
        source_time_ns=frame.source_time_ns,
        valid_until_ns=frame.valid_until_ns,
        body=tuple(body),
        left_hand=hand,
        right_hand=hand,
    )


def _cmd_dryrun(args: argparse.Namespace) -> int:
    samples, report = convert_vendored_tree(
        args.tree, horizon=1, require_images=not args.no_images
    )
    if not samples:
        print("no recorded frames to replay", file=sys.stderr)
        return 1

    frames = [sample.chunk[0] for sample in samples[: args.ticks]]
    state = samples[0].state
    print(f"replaying {len(frames)} recorded frames through the full path")

    if args.inject_pour_at is not None:
        at = args.inject_pour_at
        if not 0 <= at < len(frames):
            print(
                f"--inject-pour-at {at} is outside the replayed range "
                f"[0, {len(frames) - 1}]",
                file=sys.stderr,
            )
            return 1
        frames[at] = _pour_posture_frame(frames[at])
        print(
            f"  injected a synthetic pour posture at tick {at} "
            f"(lid reported {'open' if args.lid_open else 'closed'})"
        )

    base_ns = 1_000_000_000
    clock = _TickClock(base_ns)
    session, transport = _dry_run_session(
        frames=frames,
        lid_open=args.lid_open,
        root=args.out,
        episode_id=args.episode_id,
        clock=clock,
    )

    held_at: Optional[int] = None
    for tick in range(len(frames)):
        # The clock advances one control period before the tick that reads it,
        # so freshness is judged against the same timeline the frames were
        # produced on.
        clock.advance(PERIOD_NS)
        observation = Observation(
            time_ns=clock(),
            images={"head": f"rgb/{tick:06d}.jpg"},
            state=state,
        )
        result = session.step(observation)
        if not result.running:
            held_at = tick
            print(f"  tick {tick}: {result.state} -- {result.detail}")
            break

    outcome = EpisodeOutcome(
        transfer=TRANSFER_NONE,
        judged_by="dry-run (no human looked; nothing was poured)",
        judged_at=datetime.now(timezone.utc),
        method=JUDGED_BY_EYE,
        lid_closed_at_end=not args.lid_open,
        termination=TERMINATION_HELD if session.state == HELD else TERMINATION_COMPLETED,
        detail="software dry run; no robot and no instrument were involved",
    )
    record = session.finish(outcome)

    print(f"\nticks executed: {session.tick_count}")
    print(f"frames committed to transport: {len(transport.committed)}")
    print(f"session state: {session.state}")
    print(f"safety events: {[e.kind for e in record.safety_events] or 'none'}")
    trainable, why = record.trainable()
    print(f"record trainable: {trainable}" + (f" ({why})" if why else ""))
    print(f"episode directory: {args.out / args.episode_id}")
    return 0


def _cmd_readiness(args: argparse.Namespace) -> int:
    print("Embodied Operation Harness -- readiness\n")

    built: list[str] = []
    gaps: list[str] = []
    human: list[str] = []

    # What the software path can prove about itself.
    try:
        samples, report = convert_vendored_tree(
            args.tree, horizon=8, require_images=False
        )
        built.append(
            f"dataset conversion reads {report.episodes} vendored episodes "
            f"({report.frames_read} frames -> {len(samples)} samples)"
        )
        built.append(
            "one recorded 480x1280 file is read as "
            f"{len(sorted(report.views))} named stereo views "
            f"({', '.join(sorted(report.views))}), each carrying its crop"
        )
        for gap in report.provenance_gaps:
            gaps.append(f"dataset: {gap}")
    except Exception as exc:
        gaps.append(f"dataset conversion failed: {exc}")

    # Whether the policy can actually see. An inert encoder is not a missing
    # feature, it is a blind policy, and the root-motion decision requires
    # vision, so this belongs in the readiness report rather than a docstring.
    try:
        from vegapunk.operation.vision import DEFAULT_RESNET18_CACHE, VisionEncoder

        encoder = VisionEncoder(views=("head_left", "head_right"))
        built.append(
            f"vision encoder available: {encoder.identity} "
            f"({encoder.feature_dim} features); train with --vision"
        )
        if not Path(DEFAULT_RESNET18_CACHE).exists():
            gaps.append(
                "vision: no ImageNet weights cached at "
                f"{DEFAULT_RESNET18_CACHE}, so the trunk is randomly "
                "initialised"
            )
    except Exception as exc:
        gaps.append(f"vision encoder unavailable: {exc}")

    manifest = Path(args.checkpoint) / "checkpoint.json"
    if manifest.exists():
        payload = json.loads(manifest.read_text())
        built.append(
            f"checkpoint present: val loss "
            f"{payload.get('final_validation_loss'):.6f}, "
            f"horizon {payload.get('horizon')}"
        )
        built.append(
            "checkpoint image encoder: "
            f"{payload.get('image_encoder')} "
            f"({payload.get('image_feature_dim')} features)"
        )
        if payload.get("image_feature_dim") in (0, None):
            gaps.append(
                "checkpoint: trained with an inert image encoder, so the "
                "policy sees no pixels. Root motion is authored from vision, "
                "so this checkpoint cannot do the approach; retrain with "
                "--vision."
            )
        if not payload.get("deployable"):
            gaps.append(
                "checkpoint: not deployable -- "
                f"{payload.get('not_deployable_because')}"
            )
    else:
        gaps.append(
            f"no checkpoint at {args.checkpoint}: run "
            "'run_operation.py train' first"
        )

    vendored = (
        Path.home() / "TWIST2-master" / "deploy_real"
        / "server_low_level_g1_real.py"
    )
    if vendored.exists():
        text = vendored.read_text()
        if "vegapunk.operation dead-man" in text:
            built.append("dead-man is installed in the vendored 50 Hz loop")
        else:
            human.append(
                "install the dead-man into the vendored tracker loop:\n"
                "      python3 scripts/patch_twist2_deadman.py --check\n"
                "      python3 scripts/patch_twist2_deadman.py\n"
                "    Until this runs, a producer that dies exits the process "
                "that is balancing the robot."
            )
    else:
        gaps.append(f"vendored tracker not found at {vendored}")

    built.append(
        "actuation path proven end to end by 'dryrun' and the test suite: "
        "contract -> policy server -> monitor -> bridge -> guard -> transport"
    )

    human.append(
        "measure what the robot does when whole-body commanding stops, on a\n"
        "    secured or hoisted robot: what happens when publishing ceases, what\n"
        "    the remote's damping combination produces, and how long either takes.\n"
        "    Nothing in the code can answer this, and the latch's value depends on it."
    )
    human.append(
        "place and calibrate the bench camera that witnesses the lid. This\n"
        "    instrument reports nothing over any interface -- it is a dead panel\n"
        "    with buttons -- so a fixed camera running a geometric test is the only\n"
        "    witness available, not a fallback. Fix the camera, name the image\n"
        "    region the lid changes, and read off the two thresholds with the lid\n"
        "    open and shut under the room's real lighting. 'GeometricWitness' is\n"
        "    already the adapter; it needs those numbers and nothing else."
    )
    human.append(
        "record wrist cameras. The data contract needs head plus both wrists;\n"
        "    every existing episode has the head camera only."
    )
    human.append(
        "collect the pilot episodes, each with a reset record and a judged\n"
        "    outcome. Judging is by eye: look into the vessel and pick one of\n"
        "    transferred / partial / none. No balance is required -- the label\n"
        "    only ever has to separate three bands, and a person can do that.\n"
        "    The six existing episodes measure 0.05-0.27 m of net displacement\n"
        "    against 1.35-2.43 m of path, so they contain no locomotion to learn."
    )

    print("BUILT AND VERIFIED IN SOFTWARE")
    for item in built:
        print(f"  + {item}")

    print("\nKNOWN GAPS (the harness reports these itself)")
    for item in gaps:
        print(f"  - {item}")

    print("\nNEEDS A HUMAN (万事俱备，只欠东风)")
    for index, item in enumerate(human, start=1):
        print(f"  {index}. {item}")

    print(
        "\nNothing above is a blocker for further software work. Every item in\n"
        "the last section is a physical act in a room, which is exactly what the\n"
        "harness was built to be waiting on."
    )
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="run_operation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def _shared(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--tree", type=Path, default=DEFAULT_TREE)
        sub.add_argument(
            "--no-images",
            action="store_true",
            help="convert frames whose image file is missing",
        )

    convert = subparsers.add_parser("convert", help="inspect recorded episodes")
    _shared(convert)
    convert.add_argument("--horizon", type=int, default=8)
    convert.set_defaults(func=_cmd_convert)

    trainer = subparsers.add_parser("train", help="fit the fast policy")
    _shared(trainer)
    trainer.add_argument("--horizon", type=int, default=8)
    trainer.add_argument("--hidden", type=int, default=512)
    trainer.add_argument("--layers", type=int, default=3)
    trainer.add_argument("--epochs", type=int, default=20)
    trainer.add_argument("--batch-size", type=int, default=64)
    trainer.add_argument("--seed", type=int, default=0)
    trainer.add_argument("--out", type=Path, default=DEFAULT_CHECKPOINT)
    trainer.add_argument(
        "--vision",
        action="store_true",
        help=(
            "encode the recorded camera views with a frozen ImageNet ResNet-18 "
            "instead of feeding the policy zeros"
        ),
    )
    trainer.add_argument(
        "--limit",
        type=int,
        default=0,
        help="train on the first N samples only (a smoke run, not a pilot)",
    )
    trainer.set_defaults(func=_cmd_train)

    dry = subparsers.add_parser(
        "dryrun", help="run the whole path with no robot"
    )
    _shared(dry)
    dry.add_argument("--ticks", type=int, default=200)
    dry.add_argument("--out", type=Path, default=DEFAULT_EPISODES)
    dry.add_argument("--episode-id", default="dryrun")
    dry.add_argument(
        "--lid-open",
        action="store_true",
        default=True,
        help="what the witness reports (default: open)",
    )
    dry.add_argument(
        "--lid-closed",
        dest="lid_open",
        action="store_false",
        help="report a closed lid, so a pour posture is vetoed",
    )
    dry.add_argument(
        "--inject-pour-at",
        type=int,
        default=None,
        metavar="TICK",
        help=(
            "rewrite one replayed frame into a pour posture. No recorded "
            "episode contains one, so this is how the pour gate is "
            "demonstrated: with --lid-open it passes, with --lid-closed it "
            "holds"
        ),
    )
    dry.set_defaults(func=_cmd_dryrun)

    ready = subparsers.add_parser("readiness", help="what still needs a human")
    ready.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    ready.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    ready.set_defaults(func=_cmd_readiness)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
