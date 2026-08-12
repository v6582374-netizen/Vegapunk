"""
Workflow Models for Vegapunk

This module contains all data models and enums used throughout the workflow system,
including Ideas, Tasks, WorkflowSessions,
and WorkflowStates.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any


EXTERNAL_DATA_FALLBACK_REASON = (
    "External data requirement was missing or invalid; acquisition is disabled by default."
)
EXTERNAL_DATA_ROUTE_REGISTERED_API = "registered_api"
EXTERNAL_DATA_ROUTE_PUBLIC_WEB = "public_web"
EXTERNAL_DATA_ROUTE_NONE = "none"
_EXTERNAL_DATA_ROUTES = {
    EXTERNAL_DATA_ROUTE_REGISTERED_API,
    EXTERNAL_DATA_ROUTE_PUBLIC_WEB,
}


def normalize_external_data_requirement(
    requires_external_data: Any,
    external_data_request: Any,
    external_data_reason: Any,
    external_data_route: Any = "",
) -> tuple[bool, str, str, str, Optional[str]]:
    """Normalize an Idea's explicit external-data declaration.

    The declaration is deliberately closed by default.  A missing/non-boolean
    switch or a true switch without a concrete request cannot authorize a
    future data acquisition step.  Returning a warning separately lets the
    workflow log the normalization without adding an ``uncertain`` state to
    the persisted model.
    """
    request = external_data_request.strip() if isinstance(external_data_request, str) else ""
    reason = external_data_reason.strip() if isinstance(external_data_reason, str) else ""
    route = external_data_route.strip() if isinstance(external_data_route, str) else ""

    if not isinstance(requires_external_data, bool):
        return (
            False,
            "",
            EXTERNAL_DATA_FALLBACK_REASON,
            EXTERNAL_DATA_ROUTE_NONE,
            "requires_external_data must be a boolean; acquisition was disabled",
        )

    if requires_external_data and not request:
        return (
            False,
            "",
            EXTERNAL_DATA_FALLBACK_REASON,
            EXTERNAL_DATA_ROUTE_NONE,
            "requires_external_data was true without a concrete external_data_request; acquisition was disabled",
        )

    if requires_external_data and not route:
        return (
            True,
            request,
            reason,
            EXTERNAL_DATA_ROUTE_PUBLIC_WEB,
            "external_data_route was omitted; defaulting to public_web rather than an unrelated registered API",
        )

    if requires_external_data and route not in _EXTERNAL_DATA_ROUTES:
        return (
            False,
            "",
            EXTERNAL_DATA_FALLBACK_REASON,
            EXTERNAL_DATA_ROUTE_NONE,
            "external_data_route must be registered_api or public_web; acquisition was disabled",
        )

    if not requires_external_data:
        warning = None
        if request:
            warning = "external_data_request was ignored because requires_external_data is false"
        if not reason:
            reason = EXTERNAL_DATA_FALLBACK_REASON
            warning = warning or "external_data_reason was empty; acquisition remains disabled"
        return False, "", reason, EXTERNAL_DATA_ROUTE_NONE, warning

    return True, request, reason, route, None


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
    requires_external_data: bool = False
    external_data_request: str = ""
    external_data_reason: str = ""
    external_data_route: str = ""
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
            "requires_external_data": self.requires_external_data,
            "external_data_request": self.external_data_request,
            "external_data_reason": self.external_data_reason,
            "external_data_route": self.external_data_route,
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
        if isinstance(data.get("generated_at"), str):
            data["generated_at"] = datetime.fromisoformat(data["generated_at"])
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
