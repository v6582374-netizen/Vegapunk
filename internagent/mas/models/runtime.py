"""Project-native types for model inference runs.

The Runtime uses typed request and output items instead of exposing any
provider SDK response shape to agents. OpenAI Responses is the reference
semantics; provider adapters may implement only the capabilities they
actually support.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Mapping, Protocol, TypeAlias


MessageRole: TypeAlias = Literal["developer", "user", "assistant"]


class ModelResponseCheckpoint(Protocol):
    """Persistence seam for resumable provider response IDs."""

    def get_model_response(self, checkpoint_key: str) -> Mapping[str, str] | None:
        """Return the response record associated with a deterministic run key."""

    def record_model_response(
        self, *, checkpoint_key: str, response_id: str, status: str
    ) -> None:
        """Atomically persist the provider response ID and its latest status."""


@dataclass(frozen=True)
class TextContent:
    """Text carried by a Runtime message."""

    text: str


@dataclass(frozen=True)
class ImageContent:
    """Image input carried by a Runtime message."""

    image_url: str
    detail: Literal["low", "high", "auto", "original"] = "auto"


MessageContent: TypeAlias = TextContent | ImageContent


@dataclass(frozen=True)
class Message:
    """A typed conversational input item."""

    role: MessageRole
    content: tuple[MessageContent, ...]

    @classmethod
    def user(cls, text: str) -> "Message":
        return cls(role="user", content=(TextContent(text=text),))

    @classmethod
    def developer(cls, text: str) -> "Message":
        return cls(role="developer", content=(TextContent(text=text),))


@dataclass(frozen=True)
class FunctionTool:
    """An application-owned function available to a model run."""

    name: str
    description: str
    parameters: Mapping[str, Any]
    strict: bool = False


@dataclass(frozen=True)
class ReasoningConfig:
    """Per-run reasoning overrides merged with provider defaults."""

    effort: Literal["none", "low", "medium", "high", "xhigh", "max"] | None = None
    context: Literal["auto", "current_turn", "all_turns"] | None = None
    mode: Literal["standard", "pro"] | None = None


@dataclass(frozen=True)
class FunctionCallOutput:
    """Application result associated with the model's original call ID."""

    call_id: str
    output: Any


ModelInputItem: TypeAlias = Message | FunctionCallOutput


@dataclass(frozen=True)
class ModelRunRequest:
    """Everything needed for one inference run at the Runtime seam."""

    input: tuple[ModelInputItem, ...]
    instructions: str | None = None
    tools: tuple[FunctionTool, ...] = field(default_factory=tuple)
    response_format: Literal["text", "json_object"] = "text"
    previous_response_id: str | None = None
    prompt_cache_key: str | None = None
    reasoning: ReasoningConfig | None = None
    background: bool = False
    checkpoint_key: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class OutputText:
    """Visible model text returned by a run."""

    text: str


@dataclass(frozen=True)
class FunctionCall:
    """A model request to execute one application-owned function."""

    call_id: str
    name: str
    arguments: Mapping[str, Any]
    status: str | None = None


ModelOutputItem: TypeAlias = OutputText | FunctionCall


@dataclass(frozen=True)
class ModelUsage:
    """Provider-reported token accounting for a completed run."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0


@dataclass(frozen=True)
class ModelRunResult:
    """Typed, lossless-enough result consumed by InternAgent callers."""

    response_id: str
    status: str
    model: str
    items: tuple[ModelOutputItem, ...] = field(default_factory=tuple)
    usage: ModelUsage = field(default_factory=ModelUsage)
    reasoning_context: str | None = None
    raw_response: Any = field(default=None, repr=False, compare=False)

    @property
    def text(self) -> str:
        return "\n".join(
            item.text for item in self.items if isinstance(item, OutputText)
        )

    @property
    def tool_calls(self) -> tuple[FunctionCall, ...]:
        return tuple(
            item for item in self.items if isinstance(item, FunctionCall)
        )


@dataclass(frozen=True)
class ModelRunHandle:
    """Provider-independent control surface for an accepted model run."""

    response_id: str
    _wait: Callable[[], Awaitable[ModelRunResult]] = field(
        repr=False, compare=False
    )
    _cancel: Callable[[], Awaitable[ModelRunResult]] = field(
        repr=False, compare=False
    )

    async def wait(self) -> ModelRunResult:
        return await self._wait()

    async def cancel(self) -> ModelRunResult:
        return await self._cancel()


def build_prompt_cache_key(
    *, model: str, agent_role: str, stable_prefix: str
) -> str:
    """Build a stable, bounded cache-routing key for an Agent prompt prefix."""

    def component(value: str) -> str:
        normalized = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")
        return normalized[:18] or "unknown"

    prefix_hash = hashlib.sha256(stable_prefix.encode("utf-8")).hexdigest()[:16]
    return (
        f"internagent:v1:{component(model)}:{component(agent_role)}:"
        f"{prefix_hash}"
    )
