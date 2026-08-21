"""Deterministic Isaac Lab admission for the Golden Qualified Replay.

This is deliberately a task scene, not a digital twin: it names only the G1,
Dex3 end effector, policy camera, instrument objects, required contacts, and
the visibility of the independent witness.  It consumes the existing
``WholeBodyTarget`` replay contract and emits simulator-scoped facts only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from vegapunk.embodied.episode import QualifiedReplay
from vegapunk.embodied.promotion import (
    GOLDEN_EMBODIMENT,
    GOLDEN_PROMOTION_CONFIGURATION,
    CandidateBundle,
)
from vegapunk.operation.target import WholeBodyTarget
from vegapunk.operation.witness import LID_CLOSED, LID_INDETERMINATE, LID_OPEN

ISAAC_LAB_SOURCE = "isaac_lab"
ISAAC_LAB_VERSION = "isaac-lab-golden-v1"
CONTRACT_RUNTIME_SOURCE = "isaac_lab_contract"
CONTRACT_RUNTIME_VERSION = "deterministic-contract-v1"

VERDICT_SUCCEEDED = "succeeded"
VERDICT_FAILED = "failed"
_VERDICTS = frozenset({VERDICT_SUCCEEDED, VERDICT_FAILED})
_WITNESS_VALUES = frozenset({LID_OPEN, LID_CLOSED, LID_INDETERMINATE})
MAX_WITNESS_AGE_NS = 500_000_000


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class IsaacLabGoldenScene:
    """The minimum scene whose results say something about the Golden Skill."""

    scene_id: str
    robot_model: str
    end_effector: str
    policy_camera_key: str
    task_objects: tuple[str, ...]
    required_contacts: tuple[tuple[str, str], ...]
    independent_witness_visible: bool
    control_frequency_hz: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_objects", tuple(self.task_objects))
        object.__setattr__(
            self,
            "required_contacts",
            tuple(tuple(contact) for contact in self.required_contacts),
        )
        if not self.scene_id.strip():
            raise ValueError("an Isaac Lab scene must name its build")
        if self.robot_model != "unitree_g1" or self.end_effector != "dex3":
            raise ValueError("the Golden Scene represents the G1 with Dex3")
        if not self.policy_camera_key.strip():
            raise ValueError("the Golden Scene exposes the policy camera")
        required_objects = {"instrument", "cup", "receiving_vessel"}
        if not required_objects.issubset(self.task_objects):
            raise ValueError("the Golden Scene contains every task object")
        required_contacts = {("dex3", "cup"), ("cup", "instrument")}
        if not required_contacts.issubset(self.required_contacts):
            raise ValueError("the Golden Scene declares its critical contacts")
        if not self.independent_witness_visible:
            raise ValueError("the Independent Witness must remain visible in scene")
        if self.control_frequency_hz <= 0:
            raise ValueError("the Isaac Lab control frequency must be positive")

    def as_payload(self) -> dict[str, object]:
        return {
            "scene_id": self.scene_id,
            "robot_model": self.robot_model,
            "end_effector": self.end_effector,
            "policy_camera_key": self.policy_camera_key,
            "task_objects": list(self.task_objects),
            "required_contacts": [list(contact) for contact in self.required_contacts],
            "independent_witness_visible": self.independent_witness_visible,
            "control_frequency_hz": self.control_frequency_hz,
        }

    def digest(self) -> str:
        return _digest(self.as_payload())


GOLDEN_ISAAC_SCENE = IsaacLabGoldenScene(
    scene_id="golden-instrument-operation-v1",
    robot_model="unitree_g1",
    end_effector="dex3",
    policy_camera_key="observation.images.top",
    task_objects=("instrument", "cup", "receiving_vessel"),
    required_contacts=(("dex3", "cup"), ("cup", "instrument")),
    independent_witness_visible=True,
    control_frequency_hz=GOLDEN_EMBODIMENT.control_frequency_hz,
)


@dataclass(frozen=True)
class IsaacLabEpisode:
    """One simulator-only rendering of the shared Episode semantics."""

    source: str
    simulator_version: str
    scene_digest: str
    replay_digest: str
    seed: int
    target_sequences: tuple[int, ...]
    policy_camera_observations: tuple[str, ...]
    observed_contacts: tuple[tuple[str, str], ...]
    witness_value: str
    witness_age_ns: int
    verdict: str
    trace_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_sequences", tuple(self.target_sequences))
        if self.source not in {ISAAC_LAB_SOURCE, CONTRACT_RUNTIME_SOURCE}:
            raise ValueError("an Isaac Episode is simulator-scoped, never real")
        if not self.simulator_version.strip() or not self.scene_digest.strip():
            raise ValueError("a simulator episode names its exact world")
        if not self.replay_digest.strip() or not self.trace_digest.strip():
            raise ValueError("a simulator episode binds its replay and trace")
        if not self.target_sequences:
            raise ValueError("an Isaac Episode records WholeBodyTarget sequences")
        if not self.policy_camera_observations:
            raise ValueError("an Isaac Episode records its policy camera")
        if self.witness_value not in _WITNESS_VALUES:
            raise ValueError("an Isaac Episode records an Independent Witness value")
        if self.witness_age_ns < 0:
            raise ValueError("a witness age cannot be negative")
        if self.verdict not in _VERDICTS:
            raise ValueError("an Isaac Episode has a simulator verdict")

    @property
    def succeeded(self) -> bool:
        return self.verdict == VERDICT_SUCCEEDED


@dataclass(frozen=True)
class IsaacLabRun:
    """The task-relevant facts observed by an Isaac Lab runtime.

    The adapter does not manufacture contacts or witness readings.  A concrete
    runtime owns the simulator API and returns what its scene observed; the
    adapter only checks those facts against the frozen Golden contract.
    """

    target_sequences: tuple[int, ...]
    policy_camera_observations: tuple[str, ...]
    observed_contacts: tuple[tuple[str, str], ...]
    witness_value: str
    witness_age_ns: int
    completed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_sequences", tuple(self.target_sequences))
        object.__setattr__(
            self,
            "policy_camera_observations",
            tuple(self.policy_camera_observations),
        )
        object.__setattr__(
            self,
            "observed_contacts",
            tuple(tuple(contact) for contact in self.observed_contacts),
        )
        if not self.target_sequences:
            raise ValueError("an Isaac run records every consumed target")
        if self.witness_value not in _WITNESS_VALUES:
            raise ValueError("an Isaac run records an Independent Witness value")
        if self.witness_age_ns < 0:
            raise ValueError("an Isaac run cannot have a negative witness age")


@dataclass(frozen=True)
class IsaacRuntimeProvenance:
    """What runtime made the scene observations, and what it may certify."""

    source: str
    simulator_version: str
    admission_capable: bool

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.simulator_version.strip():
            raise ValueError("an Isaac runtime names its source and version")
        if self.admission_capable and self.source != ISAAC_LAB_SOURCE:
            raise ValueError("only an Isaac Lab host may certify admission evidence")


class IsaacLabRuntime(Protocol):
    """The narrow production seam implemented by the actual Isaac Lab host."""

    @property
    def provenance(self) -> IsaacRuntimeProvenance:
        """The host identity carried into every simulator episode."""

    def run(
        self,
        scene: IsaacLabGoldenScene,
        targets: tuple[WholeBodyTarget, ...],
        *,
        seed: int,
    ) -> IsaacLabRun:
        """Execute targets and return scene-observed task facts."""


class DeterministicIsaacLabRuntime:
    """A deterministic Golden-scene runtime for contract and admission tests.

    It is intentionally a stand-in for the Isaac Lab host, not a second
    control path: it receives the same whole-body targets and reports the
    scene's camera, contacts, witness and completion facts through the runtime
    seam above.  It is deliberately ineligible to certify admission evidence;
    a deployment replaces it with the actual Isaac Lab host integration.
    """

    @property
    def provenance(self) -> IsaacRuntimeProvenance:
        return IsaacRuntimeProvenance(
            source=CONTRACT_RUNTIME_SOURCE,
            simulator_version=CONTRACT_RUNTIME_VERSION,
            admission_capable=False,
        )

    def run(
        self,
        scene: IsaacLabGoldenScene,
        targets: tuple[WholeBodyTarget, ...],
        *,
        seed: int,
    ) -> IsaacLabRun:
        del seed
        return IsaacLabRun(
            target_sequences=tuple(target.sequence for target in targets),
            policy_camera_observations=(scene.policy_camera_key,),
            observed_contacts=scene.required_contacts,
            witness_value=LID_CLOSED,
            witness_age_ns=0,
            completed=True,
        )


class IsaacLabAdapter:
    """The sole adapter from Qualified Replay to Isaac Lab Episode semantics."""

    def __init__(self, scene: IsaacLabGoldenScene, runtime: IsaacLabRuntime) -> None:
        if scene.digest() != GOLDEN_ISAAC_SCENE.digest():
            raise ValueError("Isaac admission accepts only the named Golden Scene")
        self._scene = scene
        self._runtime = runtime

    @property
    def admission_capable(self) -> bool:
        return self._runtime.provenance.admission_capable

    def run(self, replay: QualifiedReplay, *, seed: int) -> IsaacLabEpisode:
        """Run the frozen targets deterministically against one frozen scene."""
        if replay.control_frequency_hz != self._scene.control_frequency_hz:
            raise ValueError("the replay control frequency differs from the scene")
        if not all(isinstance(target, WholeBodyTarget) for target in replay.targets):
            raise TypeError("Isaac consumes WholeBodyTarget values, not commands")
        run = self._runtime.run(self._scene, replay.targets, seed=seed)
        target_sequences = tuple(target.sequence for target in replay.targets)
        if run.target_sequences != target_sequences:
            raise ValueError("Isaac runtime did not execute the Qualified Replay targets")
        camera_complete = set(run.policy_camera_observations) == {
            self._scene.policy_camera_key
        }
        contacts_complete = set(self._scene.required_contacts).issubset(
            run.observed_contacts
        )
        witness_fresh_and_closed = (
            run.witness_value == LID_CLOSED
            and run.witness_age_ns <= MAX_WITNESS_AGE_NS
        )
        succeeded = (
            run.completed
            and camera_complete
            and contacts_complete
            and witness_fresh_and_closed
            and not any(target.saturated for target in replay.targets)
        )
        verdict = VERDICT_SUCCEEDED if succeeded else VERDICT_FAILED
        trace_digest = _digest(
            {
                "scene": self._scene.digest(),
                "replay": replay.digest(),
                "seed": seed,
                "targets": [target.as_payload() for target in replay.targets],
                "policy_camera_observations": list(run.policy_camera_observations),
                "observed_contacts": [list(contact) for contact in run.observed_contacts],
                "witness_value": run.witness_value,
                "witness_age_ns": run.witness_age_ns,
                "completed": run.completed,
                "verdict": verdict,
            }
        )
        return IsaacLabEpisode(
            source=self._runtime.provenance.source,
            simulator_version=self._runtime.provenance.simulator_version,
            scene_digest=self._scene.digest(),
            replay_digest=replay.digest(),
            seed=seed,
            target_sequences=target_sequences,
            policy_camera_observations=run.policy_camera_observations,
            observed_contacts=run.observed_contacts,
            witness_value=run.witness_value,
            witness_age_ns=run.witness_age_ns,
            verdict=verdict,
            trace_digest=trace_digest,
        )


@dataclass(frozen=True)
class IsaacLabEvidence:
    """A sealed verdict that can never be confused with real-world evidence."""

    source: str
    simulator_version: str
    scene_digest: str
    candidate_digest: str
    replay_digest: str
    seed: int
    verdict: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        if self.source != ISAAC_LAB_SOURCE:
            raise ValueError("Isaac evidence is simulator-scoped and never real")
        if not all(
            value.strip()
            for value in (
                self.simulator_version,
                self.scene_digest,
                self.candidate_digest,
                self.replay_digest,
            )
        ):
            raise ValueError("simulator evidence names every frozen input")
        if self.verdict not in _VERDICTS:
            raise ValueError("simulator evidence records a known verdict")

    @property
    def succeeded(self) -> bool:
        return self.verdict == VERDICT_SUCCEEDED

    def as_payload(self) -> dict[str, object]:
        return {
            "source": self.source,
            "simulator_version": self.simulator_version,
            "scene_digest": self.scene_digest,
            "candidate_digest": self.candidate_digest,
            "replay_digest": self.replay_digest,
            "seed": self.seed,
            "verdict": self.verdict,
            "recorded_at": self.recorded_at.isoformat(),
        }

    def digest(self) -> str:
        return _digest(self.as_payload())


class IsaacEvidenceLedger:
    """Append-only simulator evidence, intentionally separate from real ledgers."""

    def __init__(self) -> None:
        self._evidence: dict[str, IsaacLabEvidence] = {}

    def seal(self, evidence: IsaacLabEvidence) -> IsaacLabEvidence:
        return self._evidence.setdefault(evidence.digest(), evidence)

    def evidence_for(self, digest: str) -> IsaacLabEvidence | None:
        return self._evidence.get(digest)

    def evidence(self) -> tuple[IsaacLabEvidence, ...]:
        return tuple(self._evidence.values())


def admit_qualified_replay(
    replay: QualifiedReplay,
    *,
    candidate: CandidateBundle,
    adapter: IsaacLabAdapter,
    seed: int,
    ledger: IsaacEvidenceLedger,
    now: datetime,
) -> IsaacLabEvidence:
    """Seal one Isaac verdict for the exact Candidate and Qualified Replay."""
    if candidate.embodiment_digest != GOLDEN_EMBODIMENT.digest():
        raise ValueError("Isaac Golden Scene admits only the Golden embodiment")
    if candidate.configuration_digest != GOLDEN_PROMOTION_CONFIGURATION.digest():
        raise ValueError("Isaac Golden Scene admits only the Golden configuration")
    if (
        candidate.action_schema_digest
        != GOLDEN_PROMOTION_CONFIGURATION.action_protocol_digest
    ):
        raise ValueError("the Candidate does not use the WholeBodyTarget contract")
    if candidate.configuration_digest != replay.initial_state_envelope.configuration_digest:
        raise ValueError("the Candidate and replay name different configurations")
    episode = adapter.run(replay, seed=seed)
    if not adapter.admission_capable or episode.source != ISAAC_LAB_SOURCE:
        raise ValueError("Isaac admission evidence requires an Isaac Lab host runtime")
    return ledger.seal(
        IsaacLabEvidence(
            source=episode.source,
            simulator_version=episode.simulator_version,
            scene_digest=episode.scene_digest,
            candidate_digest=candidate.digest(),
            replay_digest=episode.replay_digest,
            seed=episode.seed,
            verdict=episode.verdict,
            recorded_at=now,
        )
    )
