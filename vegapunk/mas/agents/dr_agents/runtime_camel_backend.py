"""Small CAMEL adapter backed by Vegapunk's Unified Model Runtime."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Type

from vegapunk.mas.models.runtime import (
    FunctionTool,
    Message,
    ModelRunRequest,
    TextContent,
)
from vegapunk.mas.models.unified_runtime import UnifiedModelRuntime


class RuntimeCamelBackend:
    """Implement the subset of CAMEL's model backend used by DR toolkits."""

    def __init__(self, runtime: UnifiedModelRuntime, model_id: str | None = None) -> None:
        self.runtime = runtime
        self.model_id = model_id or runtime.catalog.active_text_model
        runtime.catalog.resolve_model(self.model_id, capability="text")
        from camel.types import ModelType

        self.model_type = ModelType.GPT_5_5

    @property
    def token_counter(self):
        from camel.models.stub_model import StubTokenCounter

        return StubTokenCounter()

    def run(
        self,
        messages: List[Dict[str, Any]],
        response_format: Optional[Type[Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        coroutine = self._run_async(messages, response_format, tools)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)
        import threading

        result: list[Any] = []
        error: list[BaseException] = []

        def runner() -> None:
            try:
                result.append(asyncio.run(coroutine))
            except BaseException as exc:
                error.append(exc)

        thread = threading.Thread(target=runner)
        thread.start()
        thread.join()
        if error:
            raise error[0]
        return result[0]

    async def arun(
        self,
        messages: List[Dict[str, Any]],
        response_format: Optional[Type[Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        return await self._run_async(messages, response_format, tools)

    @property
    def token_limit(self) -> int:
        return 128000

    @property
    def stream(self) -> bool:
        return False

    async def _run_async(
        self,
        messages: List[Dict[str, Any]],
        response_format: Optional[Type[Any]],
        tools: Optional[List[Dict[str, Any]]],
    ) -> Any:
        runtime_tools = tuple(_runtime_tool(tool) for tool in tools or [])
        runtime_messages: list[Message] = []
        instructions: str | None = None
        for message in messages:
            role = message.get("role", "user")
            text = message.get("content", "")
            if isinstance(text, list):
                text = "\n".join(str(item.get("text", item)) for item in text)
            text = str(text)
            if role in {"system", "developer"}:
                instructions = f"{instructions}\n{text}".strip() if instructions else text
            else:
                runtime_role = role if role in {"user", "assistant"} else "user"
                runtime_messages.append(
                    Message(role=runtime_role, content=(TextContent(text),))
                )
        request = ModelRunRequest(
            instructions=instructions,
            input=tuple(runtime_messages or [Message.user("")]),
            tools=runtime_tools,
            response_format="json_object" if response_format else "text",
        )
        result = await self.runtime.run(
            request,
            model_id=self.model_id,
            capability="json" if response_format else "text",
        )
        from camel.types import ChatCompletion, ChatCompletionMessage, Choice, CompletionUsage

        tool_calls = [
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": __import__("json").dumps(call.arguments),
                },
            }
            for call in result.tool_calls
        ]
        message = ChatCompletionMessage(
            role="assistant",
            content=result.text or None,
            tool_calls=tool_calls or None,
        )
        return ChatCompletion(
            id=result.response_id,
            model=result.model,
            object="chat.completion",
            created=0,
            choices=[Choice(index=0, message=message, finish_reason="stop", logprobs=None)],
            usage=CompletionUsage(
                completion_tokens=result.usage.output_tokens,
                prompt_tokens=result.usage.input_tokens,
                total_tokens=result.usage.total_tokens,
            ),
        )


def _runtime_tool(tool: Dict[str, Any]) -> FunctionTool:
    if not isinstance(tool, dict):
        function = getattr(tool, "func", tool)
        return FunctionTool(
            name=getattr(function, "__name__", "tool"),
            description=getattr(function, "__doc__", "") or "",
            parameters={},
        )
    function = tool.get("function", tool)
    return FunctionTool(
        name=str(function.get("name", "tool")),
        description=str(function.get("description", "")),
        parameters=function.get("parameters", {}),
    )
