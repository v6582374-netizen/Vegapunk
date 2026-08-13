"""Registered Physical Skills and the catalog they are selected from.

Version 1 executes a selectable catalog of already implemented physical
actions rather than interpreting natural language. This module owns the
boundary that makes such a catalog reviewable: a Skill Definition is an
immutable, revision-identified contract with closed parameters, declared
preconditions and postconditions, a bounded duration, and a named human
reviewer. A Skill Selection is one bound, reproducible request derived from a
definition; it carries no execution state.

Parameters are closed by construction. A parameter with neither an allowed set
nor numeric bounds would let a caller widen physical behaviour without a
contract revision, so it is rejected at definition time.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from numbers import Real
from types import MappingProxyType
from typing import Mapping, Optional

from vegapunk.embodied.embodiment import PolicyCheckpoint

SKILL_KIND_DETERMINISTIC = "deterministic"
SKILL_KIND_VLA = "vla"
_SKILL_KINDS = frozenset({SKILL_KIND_DETERMINISTIC, SKILL_KIND_VLA})


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ParameterSpec:
    """One closed input of a Physical Skill."""

    name: str
    allowed_values: tuple[object, ...] = ()
    minimum: Optional[float] = None
    maximum: Optional[float] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_values", tuple(self.allowed_values))
        if not self.name:
            raise ValueError("a ParameterSpec requires a name")
        bounded = self.minimum is not None and self.maximum is not None
        if not self.allowed_values and not bounded:
            raise ValueError(
                f"parameter {self.name!r} must declare allowed_values or both "
                "minimum and maximum; an unconstrained physical input cannot "
                "be reviewed"
            )
        if bounded and self.minimum > self.maximum:  # type: ignore[operator]
            raise ValueError(
                f"parameter {self.name!r} has minimum above maximum"
            )

    def validate(self, value: object) -> None:
        if self.allowed_values and value not in self.allowed_values:
            raise ValueError(
                f"parameter {self.name!r} value {value!r} is not one of "
                f"{list(self.allowed_values)!r}"
            )
        if self.minimum is None or self.maximum is None:
            return
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(
                f"parameter {self.name!r} requires a numeric value, got "
                f"{value!r}"
            )
        if not (self.minimum <= float(value) <= self.maximum):
            raise ValueError(
                f"parameter {self.name!r} value {value!r} is outside the "
                f"declared range [{self.minimum}, {self.maximum}]"
            )

    def as_contract(self) -> dict[str, object]:
        return {
            "name": self.name,
            "allowed_values": [repr(value) for value in self.allowed_values],
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


@dataclass(frozen=True)
class SkillSelection:
    """One bound request to run a specific skill revision.

    This is a request, not a run: it can be recorded, reviewed, and compared
    before any preflight or hardware activity exists.
    """

    skill_version_id: str
    contract_digest: str
    arguments: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "arguments", MappingProxyType(dict(self.arguments))
        )

    def selection_digest(self) -> str:
        return _digest(
            {
                "skill_version_id": self.skill_version_id,
                "contract_digest": self.contract_digest,
                "arguments": {
                    key: repr(value)
                    for key, value in sorted(self.arguments.items())
                },
            }
        )


@dataclass(frozen=True)
class PhysicalSkill:
    """An already implemented, reviewed physical action and its contract.

    ``policy`` is present exactly for VLA-driven skills. A deterministic skill
    carrying a checkpoint would blur which component authored the motion, so
    the combination is rejected.
    """

    skill_id: str
    revision: int
    kind: str
    summary: str
    parameters: tuple[ParameterSpec, ...]
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...]
    abort_conditions: tuple[str, ...]
    max_duration_s: float
    reviewed_by: str
    policy: Optional[PolicyCheckpoint] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", tuple(self.parameters))
        object.__setattr__(self, "preconditions", tuple(self.preconditions))
        object.__setattr__(self, "postconditions", tuple(self.postconditions))
        object.__setattr__(
            self, "abort_conditions", tuple(self.abort_conditions)
        )

        if not self.skill_id:
            raise ValueError("a PhysicalSkill requires a skill_id")
        if self.revision < 1:
            raise ValueError("a PhysicalSkill revision starts at 1")
        if self.kind not in _SKILL_KINDS:
            raise ValueError(
                f"unknown skill kind {self.kind!r}; expected one of "
                f"{sorted(_SKILL_KINDS)!r}"
            )
        if not self.preconditions:
            raise ValueError(
                f"skill {self.skill_id!r} must declare at least one "
                "precondition; an unguarded physical action cannot be admitted"
            )
        if not self.postconditions:
            raise ValueError(
                f"skill {self.skill_id!r} must declare at least one "
                "postcondition; success would otherwise be unverifiable"
            )
        if self.max_duration_s <= 0:
            raise ValueError(
                f"skill {self.skill_id!r} must declare a positive "
                "max_duration_s so a run cannot continue indefinitely"
            )
        if not self.reviewed_by:
            raise ValueError(
                f"skill {self.skill_id!r} must name the human review owner"
            )
        if self.kind == SKILL_KIND_VLA and self.policy is None:
            raise ValueError(
                f"skill {self.skill_id!r} is VLA-driven and must name the "
                "policy checkpoint it was validated against"
            )
        if self.kind == SKILL_KIND_DETERMINISTIC and self.policy is not None:
            raise ValueError(
                f"skill {self.skill_id!r} is deterministic and must not carry "
                "a policy checkpoint"
            )

        names = [spec.name for spec in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError(
                f"skill {self.skill_id!r} declares a duplicate parameter name"
            )

    @property
    def version_id(self) -> str:
        return f"{self.skill_id}@{self.revision}"

    def contract_digest(self) -> str:
        return _digest(
            {
                "skill_id": self.skill_id,
                "revision": self.revision,
                "kind": self.kind,
                "summary": self.summary,
                "parameters": [
                    spec.as_contract() for spec in self.parameters
                ],
                "preconditions": sorted(self.preconditions),
                "postconditions": sorted(self.postconditions),
                "abort_conditions": sorted(self.abort_conditions),
                "max_duration_s": self.max_duration_s,
                "reviewed_by": self.reviewed_by,
                "policy": None if self.policy is None else self.policy.digest(),
            }
        )

    def bind(self, arguments: Mapping[str, object]) -> SkillSelection:
        """Validate one caller's arguments against the closed contract."""
        declared = {spec.name: spec for spec in self.parameters}

        unknown = sorted(set(arguments) - set(declared))
        if unknown:
            raise ValueError(
                f"skill {self.version_id!r} does not declare parameters: "
                + ", ".join(unknown)
            )

        missing = sorted(set(declared) - set(arguments))
        if missing:
            raise ValueError(
                f"skill {self.version_id!r} requires parameters: "
                + ", ".join(missing)
            )

        for name, spec in declared.items():
            spec.validate(arguments[name])

        return SkillSelection(
            skill_version_id=self.version_id,
            contract_digest=self.contract_digest(),
            arguments=dict(arguments),
        )


class SkillRegistry:
    """The append-only catalog of selectable Physical Skills.

    Revisions accumulate instead of overwriting each other so recorded
    evidence keeps pointing at the exact contract that produced it.
    """

    def __init__(self) -> None:
        self._skills: dict[tuple[str, int], PhysicalSkill] = {}

    def register(self, skill: PhysicalSkill) -> PhysicalSkill:
        key = (skill.skill_id, skill.revision)
        existing = self._skills.get(key)
        if existing is not None:
            if existing.contract_digest() == skill.contract_digest():
                return existing
            raise ValueError(
                f"skill {skill.version_id!r} is already registered with a "
                "different contract; publish a new revision instead of "
                "mutating a reviewed one"
            )
        self._skills[key] = skill
        return skill

    def revisions(self, skill_id: str) -> tuple[int, ...]:
        return tuple(
            sorted(
                revision
                for registered_id, revision in self._skills
                if registered_id == skill_id
            )
        )

    def get(
        self, skill_id: str, revision: Optional[int] = None
    ) -> PhysicalSkill:
        available = self.revisions(skill_id)
        if not available:
            raise KeyError(f"skill {skill_id!r} is not registered")
        resolved = available[-1] if revision is None else revision
        try:
            return self._skills[(skill_id, resolved)]
        except KeyError as error:
            raise KeyError(
                f"skill {skill_id!r} has no revision {resolved}"
            ) from error

    def select(
        self,
        skill_id: str,
        arguments: Mapping[str, object],
        revision: Optional[int] = None,
    ) -> SkillSelection:
        return self.get(skill_id, revision).bind(arguments)

    def catalog(self) -> tuple[str, ...]:
        latest: dict[str, int] = {}
        for skill_id, revision in self._skills:
            latest[skill_id] = max(latest.get(skill_id, 0), revision)
        return tuple(
            f"{skill_id}@{revision}"
            for skill_id, revision in sorted(latest.items())
        )
