"""Responses-native orchestration for application-owned model tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Protocol

from ..models.runtime import (
    FunctionCallOutput,
    FunctionTool,
    Message,
    ModelRunRequest,
    ModelRunResult,
    ReasoningConfig,
)


class RuntimeModel(Protocol):
    async def run(self, request: ModelRunRequest) -> ModelRunResult: ...


ExecuteTool = Callable[[str, dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class ExecutedToolCall:
    call_id: str
    name: str
    arguments: Mapping[str, Any]
    output: Any
    error: str | None = None


@dataclass(frozen=True)
class ToolLoopResult:
    content: str
    tool_calls: tuple[ExecutedToolCall, ...] = field(default_factory=tuple)
    iterations: int = 0

    @property
    def total_tool_calls(self) -> int:
        return len(self.tool_calls)


class ModelToolLoop:
    """Drive a complete function-calling loop behind one small interface."""

    def __init__(self, *, model: RuntimeModel, execute_tool: ExecuteTool) -> None:
        self._model = model
        self._execute_tool = execute_tool

    async def run(
        self,
        *,
        instructions: str,
        prompt: str,
        tools: tuple[FunctionTool, ...],
        max_iterations: int,
        max_tool_calls: int,
        temperature: float | None = None,
        prompt_cache_key: str | None = None,
    ) -> ToolLoopResult:
        request = ModelRunRequest(
            instructions=instructions,
            input=(Message.user(prompt),),
            tools=tools,
            temperature=temperature,
            prompt_cache_key=prompt_cache_key,
            reasoning=ReasoningConfig(context="all_turns"),
        )
        executed: list[ExecutedToolCall] = []
        last_content = ""

        for iteration in range(1, max_iterations + 1):
            response = await self._model.run(request)
            last_content = response.text or last_content
            calls = response.tool_calls
            if not calls:
                return ToolLoopResult(
                    content=last_content,
                    tool_calls=tuple(executed),
                    iterations=iteration,
                )
            if len(executed) + len(calls) > max_tool_calls:
                break

            outputs = []
            for call in calls:
                arguments = dict(call.arguments)
                error = None
                try:
                    output = await self._execute_tool(call.name, arguments)
                except Exception as exc:  # tool failure becomes model-visible evidence
                    error = str(exc)
                    output = {"error": error}
                executed.append(
                    ExecutedToolCall(
                        call_id=call.call_id,
                        name=call.name,
                        arguments=arguments,
                        output=output,
                        error=error,
                    )
                )
                outputs.append(
                    FunctionCallOutput(call_id=call.call_id, output=output)
                )

            request = ModelRunRequest(
                instructions=instructions,
                input=tuple(outputs),
                tools=tools,
                temperature=temperature,
                prompt_cache_key=prompt_cache_key,
                previous_response_id=response.response_id,
                reasoning=ReasoningConfig(context="all_turns"),
            )

        return ToolLoopResult(
            content=last_content or "Reached limits without final answer.",
            tool_calls=tuple(executed),
            iterations=max_iterations,
        )
