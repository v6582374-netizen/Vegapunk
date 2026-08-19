"""
Workflow Models for Vegapunk

This module contains all data models and enums used throughout the workflow system,
including Ideas, Tasks, WorkflowSessions,
and WorkflowStates.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional


EXTERNAL_DATA_FALLBACK_REASON = (
    "External data requirement was missing or invalid; acquisition is disabled by default."
)
EXTERNAL_DATA_POLICY_FORBIDDEN_REASON = (
    "The research Task forbids externally acquired data; acquisition is closed for every Idea."
)
EXTERNAL_DATA_POLICY_ALLOWED = "allowed"
EXTERNAL_DATA_POLICY_FORBIDDEN = "forbidden"
EXTERNAL_DATA_POLICIES = (
    EXTERNAL_DATA_POLICY_ALLOWED,
    EXTERNAL_DATA_POLICY_FORBIDDEN,
)


@dataclass(frozen=True)
class ExternalDataDeclaration:
    """One branch of an Idea's external-data decision.

    The decision is a choice, not a table.  An open declaration carries the
    concrete ``request`` it needs; a closed one carries the ``reason`` it does
    not.  Neither branch has to invent the other branch's payload, so a record
    can no longer contradict itself by construction.
    """

    required: bool = False
    request: str = ""
    reason: str = ""


def resolve_external_data_declaration(
    raw: Any,
    *,
    policy: str = EXTERNAL_DATA_POLICY_ALLOWED,
    inherited: Optional[ExternalDataDeclaration] = None,
) -> tuple[ExternalDataDeclaration, Optional[str]]:
    """Resolve one declaration against the Task-level policy.

    This is the single customs house for every entrance that can create an
    Idea.  An Idea may only narrow what its Task already permits; it can never
    widen it.  A missing declaration inherits its parent's decision whole,
    rather than blending fields into a record nobody chose.
    """
    if policy == EXTERNAL_DATA_POLICY_FORBIDDEN:
        claimed = isinstance(raw, Mapping) and raw.get("required") is True
        return (
            ExternalDataDeclaration(reason=EXTERNAL_DATA_POLICY_FORBIDDEN_REASON),
            "the Task forbids external data; the Idea's request was refused"
            if claimed
            else None,
        )

    if raw is None and inherited is not None:
        return inherited, None

    if not isinstance(raw, Mapping):
        return (
            ExternalDataDeclaration(reason=EXTERNAL_DATA_FALLBACK_REASON),
            "external_data must be an object declaring required; acquisition was disabled",
        )

    required = raw.get("required")
    request = raw.get("request")
    reason = raw.get("reason")
    request = request.strip() if isinstance(request, str) else ""
    reason = reason.strip() if isinstance(reason, str) else ""

    if not isinstance(required, bool):
        return (
            ExternalDataDeclaration(reason=EXTERNAL_DATA_FALLBACK_REASON),
            "external_data.required must be a boolean; acquisition was disabled",
        )

    if required:
        if not request:
            return (
                ExternalDataDeclaration(reason=EXTERNAL_DATA_FALLBACK_REASON),
                "external_data.required was true without a concrete request; "
                "acquisition was disabled",
            )
        return ExternalDataDeclaration(required=True, request=request), None

    warning = None
    if request:
        warning = "external_data.request was ignored because required is false"
    if not reason:
        reason = EXTERNAL_DATA_FALLBACK_REASON
        warning = warning or "external_data.reason was empty; acquisition remains disabled"
    return ExternalDataDeclaration(reason=reason), warning


# 这些状态就是发现流程的路线图：先产生想法，再批评、查证、改进、排序，
# 最后把最好的想法发展成可执行方法。
class WorkflowState(Enum):
    """Enumeration of workflow states."""
    INITIAL = "initial"
    GENERATING = "generating"
    REFLECTING = "reflecting"
    EVOLVING = "evolving"
    METHOD_DEVELOPMENT = "method_development"
    REFINING = "refining"
    RANKING = "ranking"
    AWAITING_FEEDBACK = "awaiting_feedback"
    EXTERNAL_DATA = "external_data"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class Idea:
    """Data class for research ideas (formerly hypotheses)."""
    # 一个想法会在流程里逐步长出评分、证据、方法细节和父子关系；
    # 所以这里看起来字段很多，本质上是在保存它一路被加工过的痕迹。
    id: str
    text: str
    score: float = 0.0
    rationale: str = ""
    external_data: ExternalDataDeclaration = field(
        default_factory=ExternalDataDeclaration
    )
    data_workspace: str = ""
    baseline_summary: str = ""
    critiques: List[str] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    refine_evidence: List[Dict[str, Any]] = field(default_factory=list)
    acquisition_events: List[Dict[str, Any]] = field(default_factory=list)
    iteration: int = 0
    scores: Dict[str, float] = field(default_factory=dict)
    references: List[Dict[str, Any]] = field(default_factory=list)
    experimental_approach: str = ""
    detailed_ideas: Dict[str, Any] = field(default_factory=dict)
    method_details: Dict[str, Any] = field(default_factory=dict)
    method_critiques: List[str] = field(default_factory=list)
    refined_method_details: Dict[str, Any] = field(default_factory=dict)
    parent_id: Optional[str] = None
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "text": self.text,
            "score": self.score,
            "rationale": self.rationale,
            "external_data": {
                "required": self.external_data.required,
                "request": self.external_data.request,
                "reason": self.external_data.reason,
            },
            "data_workspace": self.data_workspace,
            "baseline_summary": self.baseline_summary,
            "critiques": self.critiques,
            "evidence": self.evidence,
            "refine_evidence": self.refine_evidence,
            "acquisition_events": self.acquisition_events,
            "iteration": self.iteration,
            "scores": self.scores,
            "references": self.references,
            "experimental_approach": self.experimental_approach,
            "detailed_ideas": self.detailed_ideas,
            "method_details": self.method_details,
            "refined_method_details": self.refined_method_details,
            "method_critiques": self.method_critiques,
            "parent_id": self.parent_id,
            "generated_at": self.generated_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Idea':
        """Create an Idea from a dictionary."""
        data = dict(data)
        if isinstance(data.get("generated_at"), str):
            data["generated_at"] = datetime.fromisoformat(data["generated_at"])
        declaration = data.get("external_data")
        if isinstance(declaration, Mapping):
            data["external_data"] = ExternalDataDeclaration(
                required=bool(declaration.get("required")),
                request=str(declaration.get("request") or ""),
                reason=str(declaration.get("reason") or ""),
            )
        return cls(**data)


@dataclass
class Task:
    """Data class for research tasks (formerly research goals)."""
    # 任务对象把人的目标、领域、约束和参考代码放在一起，
    # 让每个代理拿到的是同一份上下文，而不是各自解析命令行。
    id: str
    description: str
    domain: str
    constraints: List[str] = field(default_factory=list)
    background: str = ""
    ref_code_path: str = ""
    # The authority an Idea-level declaration may only narrow, never widen.
    external_data_policy: str = EXTERNAL_DATA_POLICY_ALLOWED
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "description": self.description,
            "domain": self.domain,
            "constraints": self.constraints,
            "background": self.background,
            "ref_code_path": self.ref_code_path,
            "external_data_policy": self.external_data_policy,
            "created_at": self.created_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        """Create a Task from a dictionary."""
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)


@dataclass
class WorkflowSession:
    """Data class for workflow sessions."""
    # 会话是一次研究运行的账本：当前走到哪个状态、产生了哪些想法、
    # 哪些想法被选中、用户反馈了什么，都在这里汇总。
    id: str
    task: Task
    ideas: List[Idea] = field(default_factory=list)
    iterations_completed: int = 0
    max_iterations: int = 4
    state: WorkflowState = WorkflowState.INITIAL
    feedback_history: List[Dict[str, Any]] = field(default_factory=list)
    top_ideas: List[str] = field(default_factory=list)
    tool_usage: Dict[str, int] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    method_phase: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "task": self.task.to_dict(),
            "ideas": [idea.to_dict() for idea in self.ideas],
            "iterations_completed": self.iterations_completed,
            "max_iterations": self.max_iterations,
            "state": self.state.value,
            "feedback_history": self.feedback_history,
            "top_ideas": self.top_ideas,
            "tool_usage": self.tool_usage,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }
