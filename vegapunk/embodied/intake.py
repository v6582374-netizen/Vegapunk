"""What a sentence about a broken robot is allowed to authorise.

A user's entry point into this harness is prose: a description of something
the robot will not do. Turning that prose into an experiment is the one job
an AI Scientist genuinely owns, and it is also the one place where the whole
harness can be subverted, because prose is the only input that arrives
without provenance. This module converts a complaint into a typed brief and
refuses three things while doing it.

It refuses to let a sentence authorise physical change. A complaint is
routed, not executed. Routing walks an ordered ladder from the cheapest and
most reversible response to the most expensive and least reversible --
change the fixture, change the request, change the interface, add a
corrector, change the weights -- and Version 1 may search exactly one rung
of it unattended. Everything else comes back refused with the human act
named. A refusal here is the normal outcome, not a failure: most complaints
about a robot are complaints about a room or a request.

It refuses to default. An unrecognised symptom or route is an error rather
than a fallback, because the failure mode of a lenient parser is silent and
expensive: a garbled reply that decayed into the one searchable route would
start a physical search against a semantic problem, and every measurement
taken afterwards would be a valid measurement of the wrong question.

It refuses to let the brief assert a physical fact. The model has never seen
this robot; nothing in a complaint discloses its end effector, its cameras,
its degrees of freedom, or the cadence of its control loop. A guess about
any of those, written into an objective, becomes a premise that the campaign
and the admission ladder both inherit and neither can detect -- a wrong
number that looks exactly like a verified one. So such statements are moved
out of the objective and into ``unknowns``, where they read as questions for
a human instead of as findings.

What this module never does is decide whether an adaptation worked. It has
no evaluator, no runs, and no evidence. It only decides what question is
being asked and whether that question may be asked of a machine.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Optional, Sequence

from vegapunk.prompt_library import get_prompt_library

PROMPT_TRIAGE = "embodied.intake_triage"

PATH_ENVIRONMENT = "environment"
PATH_INSTRUCTION = "instruction"
PATH_INTERFACE = "interface"
PATH_RESIDUAL = "residual"
PATH_FINETUNE = "finetune"

ADAPTATION_PATH_ORDER = (
    PATH_ENVIRONMENT,
    PATH_INSTRUCTION,
    PATH_INTERFACE,
    PATH_RESIDUAL,
    PATH_FINETUNE,
)
"""Ordered cheapest and most reversible first.

The order is the module's actual claim: a fixture change costs an afternoon
and can be undone by moving the fixture back, while a checkpoint change
costs a training run and cannot be undone at all once anything is collected
against it. Reading the ladder outermost-first is therefore not thrift, it
is the order in which a wrong guess is survivable.
"""

AUTOMATABLE_PATHS = (PATH_INTERFACE,)
"""The only path Version 1 may search without a human in the loop.

The interface layer is searchable because a candidate is a typed value that
a simulated campaign can score and discard, and because a wrong candidate
leaves nothing behind. Every other rung either changes the physical world,
changes what was asked, or leaves an artifact -- a corrector, a checkpoint --
that outlives the search that produced it.
"""

SYMPTOM_ERRATIC_OR_INERT = "erratic_or_inert"
SYMPTOM_SYSTEMATIC_OFFSET = "systematic_offset"
SYMPTOM_COMPETENT_BUT_WRONG = "competent_but_wrong"
SYMPTOM_SCENE_SENSITIVE = "scene_sensitive"
SYMPTOM_UNCLASSIFIABLE = "unclassifiable"

SYMPTOM_ORDER = (
    SYMPTOM_ERRATIC_OR_INERT,
    SYMPTOM_SYSTEMATIC_OFFSET,
    SYMPTOM_COMPETENT_BUT_WRONG,
    SYMPTOM_SCENE_SENSITIVE,
    SYMPTOM_UNCLASSIFIABLE,
)

UNREADABLE_ROUTE = PATH_INSTRUCTION
"""Where a complaint nobody could classify goes.

Not the searchable rung, and not a null value that later code would have to
special-case. An unreadable report is a defect in what was asked, so the
next act belongs to the person who asked it.
"""

PHYSICAL_FACT_PATTERNS = (
    ("end effector", re.compile(r"end[\s-]?effector|gripper|dex\d", re.I)),
    (
        "camera layout",
        re.compile(r"camera|rgb[\s-]?d?\b|wrist[\s-]?cam|depth sensor", re.I),
    ),
    (
        "degrees of freedom",
        re.compile(
            r"\bdof\b|degrees? of freedom|\b\d+[\s-]*(?:dof|joints?)\b"
            r"|\bjoint count\b",
            re.I,
        ),
    ),
    (
        "control frequency",
        re.compile(
            r"\bcontrol (?:frequency|rate)\b|\b\d+\s*hz\b|\bhz\b"
            r"|\bsampling rate\b",
            re.I,
        ),
    ),
)
"""Classes of statement the brief may not make, only ask about.

Each of these is a fact about hardware that a reader would take as verified
and that nothing in a complaint could establish. The match is deliberately
crude and errs toward relocation: a real fact demoted to a question costs a
human one confirmation, while a guess promoted to a premise costs the
experiment.
"""

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;])\s+")

TRIAGE_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": [
        "symptom",
        "routed_path",
        "objective_statement",
        "observable_success",
        "unknowns",
        "rejected_paths",
    ],
    "properties": {
        "symptom": {"type": "string", "enum": list(SYMPTOM_ORDER)},
        "routed_path": {
            "type": "string",
            "enum": list(ADAPTATION_PATH_ORDER),
        },
        "objective_statement": {"type": "string"},
        "observable_success": {
            "type": "array",
            "items": {"type": "string"},
        },
        "unknowns": {"type": "array", "items": {"type": "string"}},
        "rejected_paths": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["path", "reason"],
                "properties": {
                    "path": {
                        "type": "string",
                        "enum": list(ADAPTATION_PATH_ORDER),
                    },
                    "reason": {"type": "string"},
                },
            },
        },
    },
}

_REFUSAL_BY_PATH = {
    PATH_ENVIRONMENT: (
        "routed to the {path!r} path: the next act is physical and belongs "
        "to a person. Someone must change the fixture, the scene, or the "
        "object placement and re-run the original request before any "
        "adaptation of the system is justified. Searching adaptations "
        "against a scene that is itself the fault would optimise a "
        "correction for a condition nobody intends to keep."
    ),
    PATH_INSTRUCTION: (
        "routed to the {path!r} path: the next act is editorial and belongs "
        "to a person. Someone must restate what the robot is being asked to "
        "do -- narrow it, decompose it, or specify what success means -- "
        "before there is a question a search could answer. A search over "
        "the system cannot repair an underspecified request; it can only "
        "find a candidate that satisfies a goal nobody agreed to."
    ),
    PATH_RESIDUAL: (
        "routed to the {path!r} path: the next act creates a learned "
        "artifact and belongs to a person. Someone must first confirm that "
        "the interface layer is correct, because a corrector trained "
        "against a mis-scaled or mis-framed interface learns to cancel that "
        "defect and then persists as a component nobody can interpret. "
        "Version 1 does not fit correctors unattended."
    ),
    PATH_FINETUNE: (
        "routed to the {path!r} path: refused unconditionally without a "
        "human. Someone must first verify the interface layer on the real "
        "robot and record that verification, because fine-tuning on an "
        "unverified interface bakes an interface bug into a checkpoint -- "
        "the defect stops being a configuration you can change and becomes "
        "weights you cannot inspect -- and it additionally contaminates "
        "every trajectory collected against that interface, so the dataset "
        "that would be used to diagnose the checkpoint carries the same "
        "fault. A wrong number in an interface is an afternoon; the same "
        "number trained in is a checkpoint and a corpus."
    ),
}


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _texts(value: object, field_name: str) -> tuple[str, ...]:
    """Accept a sequence of strings and nothing that merely looks like one."""
    if value is None:
        return ()
    if isinstance(value, str):
        raise ValueError(
            f"{field_name} must be a sequence of statements, not one string; "
            "a single string would silently become a list of characters"
        )
    if not isinstance(value, Sequence):
        raise ValueError(f"{field_name} must be a sequence of statements")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(
                f"{field_name} contains a non-string entry: {item!r}"
            )
        text = item.strip()
        if text:
            items.append(text)
    return tuple(items)


def physical_claims(statement: str) -> tuple[str, ...]:
    """Which classes of unverified hardware fact a statement asserts."""
    return tuple(
        name
        for name, pattern in PHYSICAL_FACT_PATTERNS
        if pattern.search(statement)
    )


def _split_sentences(statement: str) -> list[str]:
    return [
        part.strip()
        for part in _SENTENCE_BOUNDARY.split(statement.strip())
        if part.strip()
    ]


def _as_unknown(statement: str, claims: Sequence[str]) -> str:
    return (
        f"confirm on the real robot before relying on this ({', '.join(claims)}"
        f"): {statement}"
    )


@dataclass(frozen=True)
class PainPoint:
    """One person's report that the robot will not do something.

    Carries its submitter and time because a brief is traceable to a request,
    not to a prompt. The text is preserved verbatim: a summarised complaint
    loses the very wording a reviewer needs to judge whether the routing read
    it correctly.
    """

    text: str
    submitted_by: str
    submitted_at: datetime

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("a PainPoint must state what went wrong")
        if not self.submitted_by.strip():
            raise ValueError(
                "a PainPoint must name its submitter; an anonymous complaint "
                "cannot be taken back to anyone for the facts it omits"
            )

    def digest(self) -> str:
        return _digest(
            {
                "text": self.text.strip(),
                "submitted_by": self.submitted_by.strip(),
                "submitted_at": self.submitted_at.isoformat(),
            }
        )


@dataclass(frozen=True)
class AdaptationBrief:
    """A complaint, classified and routed, with its refusal if it has one.

    Frozen because a brief is the premise of everything downstream. If a
    search could widen its own objective or move an unknown into the
    objective mid-run, the record of what was asked would drift to match
    whatever was found.
    """

    pain_point: PainPoint
    symptom: str
    routed_path: str
    objective_statement: str
    observable_success: tuple[str, ...]
    unknowns: tuple[str, ...]
    rejected_paths: tuple[tuple[str, str], ...]
    searchable: bool
    refusal: str = ""

    def __post_init__(self) -> None:
        if self.symptom not in SYMPTOM_ORDER:
            raise ValueError(
                f"unknown symptom {self.symptom!r}; expected one of "
                f"{list(SYMPTOM_ORDER)!r}"
            )
        if self.routed_path not in ADAPTATION_PATH_ORDER:
            raise ValueError(
                f"unknown adaptation path {self.routed_path!r}; expected one "
                f"of {list(ADAPTATION_PATH_ORDER)!r}"
            )
        object.__setattr__(
            self,
            "observable_success",
            _texts(self.observable_success, "observable_success"),
        )
        object.__setattr__(
            self, "unknowns", _texts(self.unknowns, "unknowns")
        )
        object.__setattr__(
            self,
            "rejected_paths",
            tuple(
                (str(path), str(reason))
                for path, reason in self.rejected_paths
            ),
        )
        for path, _ in self.rejected_paths:
            if path not in ADAPTATION_PATH_ORDER:
                raise ValueError(
                    f"rejected path {path!r} is not on the ladder "
                    f"{list(ADAPTATION_PATH_ORDER)!r}"
                )
            if path == self.routed_path:
                raise ValueError(
                    f"path {path!r} is both the route and a rejection"
                )
        if not self.objective_statement.strip():
            raise ValueError(
                "a brief must state what a successful adaptation would "
                "demonstrate; an empty objective cannot be measured against"
            )
        # The two halves of the same sentence. A searchable brief with a
        # refusal, or a refused brief without a stated reason, are both
        # readable as permission by anything that checks only one field.
        if self.searchable and self.refusal.strip():
            raise ValueError(
                "a searchable brief cannot also carry a refusal"
            )
        if not self.searchable and not self.refusal.strip():
            raise ValueError(
                "a brief that is not searchable must say what a human must "
                "do first"
            )
        if self.searchable and self.routed_path not in AUTOMATABLE_PATHS:
            raise ValueError(
                f"path {self.routed_path!r} is not in "
                f"{list(AUTOMATABLE_PATHS)!r} and cannot be searched"
            )
        offending = physical_claims(self.objective_statement)
        if offending:
            raise ValueError(
                "the objective asserts unverified hardware facts "
                f"({', '.join(offending)}); such statements belong in "
                "unknowns"
            )
        for statement in self.observable_success:
            offending = physical_claims(statement)
            if offending:
                raise ValueError(
                    f"observable success {statement!r} asserts unverified "
                    f"hardware facts ({', '.join(offending)})"
                )

    def digest(self) -> str:
        return _digest(
            {
                "pain_point": self.pain_point.digest(),
                "symptom": self.symptom,
                "routed_path": self.routed_path,
                "objective_statement": self.objective_statement,
                "observable_success": list(self.observable_success),
                "unknowns": list(self.unknowns),
                "rejected_paths": [
                    [path, reason] for path, reason in self.rejected_paths
                ],
                "searchable": self.searchable,
                "refusal": self.refusal,
            }
        )

    def as_contract(self) -> dict[str, object]:
        return {
            "brief_digest": self.digest(),
            "pain_point_digest": self.pain_point.digest(),
            "submitted_by": self.pain_point.submitted_by,
            "submitted_at": self.pain_point.submitted_at.isoformat(),
            "pain_point_text": self.pain_point.text,
            "symptom": self.symptom,
            "routed_path": self.routed_path,
            "objective_statement": self.objective_statement,
            "observable_success": list(self.observable_success),
            "unknowns": list(self.unknowns),
            "rejected_paths": [
                {"path": path, "reason": reason}
                for path, reason in self.rejected_paths
            ],
            "searchable": self.searchable,
            "refusal": self.refusal,
        }


def _refusal_for(path: str) -> str:
    return _REFUSAL_BY_PATH[path].format(path=path)


def brief_from_classification(
    pain_point: PainPoint,
    classification: Mapping[str, object],
) -> AdaptationBrief:
    """Validate one classification into the only brief that may exist.

    Total in the sense that matters: for every input it either returns a
    brief whose invariants hold or raises. It never repairs a reply by
    choosing a value the model did not choose, because the value it would
    have to invent -- the route -- is the one that decides whether a machine
    may act.
    """
    symptom = classification.get("symptom")
    if not isinstance(symptom, str) or symptom not in SYMPTOM_ORDER:
        raise ValueError(
            f"classification carries symptom {symptom!r}, which is not one "
            f"of {list(SYMPTOM_ORDER)!r}"
        )
    routed_path = classification.get("routed_path")
    if (
        not isinstance(routed_path, str)
        or routed_path not in ADAPTATION_PATH_ORDER
    ):
        raise ValueError(
            f"classification carries routed_path {routed_path!r}, which is "
            f"not on the ladder {list(ADAPTATION_PATH_ORDER)!r}. A route "
            "that cannot be read is not a route to the searchable path"
        )

    objective_raw = classification.get("objective_statement")
    if not isinstance(objective_raw, str) or not objective_raw.strip():
        raise ValueError(
            "classification must state an objective a run could be measured "
            "against"
        )

    unknowns = list(_texts(classification.get("unknowns"), "unknowns"))

    # Relocation, not rejection. The model was told not to assert hardware
    # facts; when it does anyway, the sentence is usually a real question
    # about the robot wearing the grammar of an answer, so it is worth
    # keeping -- as a question.
    kept: list[str] = []
    for sentence in _split_sentences(objective_raw):
        claims = physical_claims(sentence)
        if claims:
            unknowns.append(_as_unknown(sentence, claims))
        else:
            kept.append(sentence)
    objective = " ".join(kept).strip()
    if not objective:
        objective = (
            f"demonstrate that the reported {symptom!r} behaviour no longer "
            "occurs on the original request, once the facts listed in "
            "unknowns have been confirmed by a human"
        )

    success: list[str] = []
    for statement in _texts(
        classification.get("observable_success"), "observable_success"
    ):
        claims = physical_claims(statement)
        if claims:
            unknowns.append(_as_unknown(statement, claims))
        else:
            success.append(statement)

    rejected: list[tuple[str, str]] = []
    raw_rejected = classification.get("rejected_paths") or ()
    if isinstance(raw_rejected, (str, bytes)) or not isinstance(
        raw_rejected, Sequence
    ):
        raise ValueError("rejected_paths must be a sequence of entries")
    for entry in raw_rejected:
        if isinstance(entry, Mapping):
            path = entry.get("path")
            reason = entry.get("reason")
        elif isinstance(entry, Sequence) and len(tuple(entry)) == 2:
            path, reason = tuple(entry)
        else:
            raise ValueError(f"unreadable rejected path entry: {entry!r}")
        if not isinstance(path, str) or path not in ADAPTATION_PATH_ORDER:
            raise ValueError(
                f"rejected path {path!r} is not on the ladder "
                f"{list(ADAPTATION_PATH_ORDER)!r}"
            )
        if path == routed_path:
            continue
        rejected.append((path, str(reason or "").strip()))

    searchable = routed_path in AUTOMATABLE_PATHS
    refusal = "" if searchable else _refusal_for(routed_path)

    # Deduplicated in first-seen order: the same unknown asked twice reads as
    # two open questions and inflates what a human is being asked to verify.
    seen: set[str] = set()
    ordered_unknowns: list[str] = []
    for item in unknowns:
        if item not in seen:
            seen.add(item)
            ordered_unknowns.append(item)

    return AdaptationBrief(
        pain_point=pain_point,
        symptom=symptom,
        routed_path=routed_path,
        objective_statement=objective,
        observable_success=tuple(success),
        unknowns=tuple(ordered_unknowns),
        rejected_paths=tuple(rejected),
        searchable=searchable,
        refusal=refusal,
    )


def unreadable_brief(pain_point: PainPoint, detail: str) -> AdaptationBrief:
    """The brief for a reply that could not be read, quoting what came back.

    A triage failure has to be visible as itself. Raising would put the
    harness's own malfunction into the same channel as a bad complaint, and
    defaulting would hide it entirely.
    """
    quoted = detail.strip() or "an empty reply"
    if len(quoted) > 600:
        quoted = quoted[:600] + "..."
    return AdaptationBrief(
        pain_point=pain_point,
        symptom=SYMPTOM_UNCLASSIFIABLE,
        routed_path=UNREADABLE_ROUTE,
        objective_statement=(
            "restate the complaint until a symptom and a route can be "
            "identified; nothing about the system is known to be at fault"
        ),
        observable_success=(),
        unknowns=(
            "everything: no symptom could be identified, so no physical "
            "fact about this robot has been established either",
        ),
        rejected_paths=(),
        searchable=False,
        refusal=(
            "triage could not classify this complaint, so it is routed to no "
            f"searchable path. The model returned: {quoted}"
        ),
    )


async def triage(
    pain_point: PainPoint,
    runtime,
    *,
    library=None,
    model_id: Optional[str] = None,
) -> AdaptationBrief:
    """Ask the model to classify one complaint, and survive any answer.

    The only asynchronous, non-deterministic, failure-prone step in intake,
    kept in one function so that everything which decides anything --
    ``brief_from_classification`` -- stays pure and testable without a model.
    """
    prompts = library or get_prompt_library()
    prompt = prompts.render(
        PROMPT_TRIAGE,
        pain_point_text=pain_point.text.strip(),
        submitted_by=pain_point.submitted_by.strip(),
        symptom_vocabulary=", ".join(SYMPTOM_ORDER),
        adaptation_path_ladder=", ".join(ADAPTATION_PATH_ORDER),
        automatable_paths=", ".join(AUTOMATABLE_PATHS),
    )
    try:
        reply = await runtime.generate_json(
            prompt, schema=TRIAGE_SCHEMA, model_id=model_id
        )
    except Exception as error:  # noqa: BLE001 - a triage failure is a brief
        return unreadable_brief(
            pain_point, f"{type(error).__name__}: {error}"
        )
    if not isinstance(reply, Mapping):
        return unreadable_brief(pain_point, repr(reply))
    try:
        return brief_from_classification(pain_point, reply)
    except (ValueError, TypeError) as error:
        return unreadable_brief(
            pain_point, f"{json.dumps(_jsonable(reply))} ({error})"
        )


def _jsonable(payload: Mapping[str, object]) -> dict[str, object]:
    """Quote a reply in the refusal without letting it raise on the way."""
    safe: dict[str, object] = {}
    for key, value in payload.items():
        try:
            json.dumps(value)
        except TypeError:
            safe[str(key)] = repr(value)
        else:
            safe[str(key)] = value
    return safe
