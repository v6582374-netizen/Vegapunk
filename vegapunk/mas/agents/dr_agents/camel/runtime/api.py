# ========= Copyright 2023-2024 @ CAMEL-AI.org. All Rights Reserved. =========
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ========= Copyright 2023-2024 @ CAMEL-AI.org. All Rights Reserved. =========
import contextlib
import importlib
import io
import json
import logging
import os
import re
import sys
import threading
from typing import Any, Dict, Iterable, List

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from vegapunk.mas.agents.dr_agents.camel.toolkits import BaseToolkit

logger = logging.getLogger(__name__)

modules_functions = sys.argv[1:]

_DEFAULT_ALLOWED_MODULE_PREFIXES = (
    "camel.",
    "vegapunk.mas.agents.dr_agents.camel.",
)
_FUNCTION_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _max_stdout_chars() -> int:
    try:
        return max(1, int(os.environ.get("CAMEL_RUNTIME_MAX_STDOUT_CHARS", "65536")))
    except ValueError:
        return 65_536


_MAX_STDOUT_CHARS = _max_stdout_chars()
_STDOUT_REDIRECT_LOCK = threading.Lock()


def _allowed_module_prefixes() -> tuple[str, ...]:
    configured = os.environ.get("CAMEL_RUNTIME_ALLOWED_MODULES", "")
    extra = tuple(
        prefix.strip()
        for prefix in configured.split(",")
        if prefix.strip()
    )
    return _DEFAULT_ALLOWED_MODULE_PREFIXES + extra


def _parse_entrypoint(spec: str) -> tuple[str, str, Dict[str, Any]]:
    module_spec, separator, params_json = spec.partition("{")
    init_params: Dict[str, Any] = {}
    if separator:
        try:
            parsed = json.loads("{" + params_json)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid toolkit initialization parameters") from exc
        if not isinstance(parsed, dict):
            raise ValueError("toolkit initialization parameters must be an object")
        init_params = parsed

    try:
        module_name, function_name = module_spec.rsplit(".", 1)
    except ValueError as exc:
        raise ValueError("entrypoint must be a dotted module and attribute") from exc

    if not any(
        module_name.startswith(prefix)
        for prefix in _allowed_module_prefixes()
    ):
        raise ValueError(f"module is outside the runtime allowlist: {module_name}")
    if not _FUNCTION_NAME_PATTERN.fullmatch(function_name):
        raise ValueError("entrypoint attribute must be a simple identifier")
    return module_name, function_name, init_params


def _as_function_tools(candidate: Any) -> List[Any]:
    functions: Iterable[Any] = candidate if isinstance(candidate, list) else [candidate]
    result = list(functions)
    if not result or any(
        not callable(getattr(item, "func", None))
        or not callable(getattr(item, "get_function_name", None))
        for item in result
    ):
        raise ValueError("entrypoint does not expose callable FunctionTool objects")
    return result


class _LimitedStringIO(io.StringIO):
    """StringIO that bounds captured output without breaking ``print``."""

    def __init__(self, max_chars: int):
        super().__init__()
        self.max_chars = max_chars
        self._captured_chars = 0
        self.truncated = False

    def write(self, value: str) -> int:  # type: ignore[override]
        remaining = self.max_chars - self._captured_chars
        if remaining > 0:
            super().write(value[:remaining])
            self._captured_chars += min(len(value), remaining)
        if len(value) > remaining:
            self.truncated = True
        # TextIOBase.write returns the input length, even when a sink chooses
        # to truncate it; this keeps print() and logging handlers well-behaved.
        return len(value)

    def value(self) -> str:
        output = self.getvalue()
        if self.truncated:
            output += f"\n[stdout truncated after {self.max_chars} characters]"
        return output

logger.info(f"Modules and functions: {modules_functions}")

app = FastAPI()


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal Server Error",
            "error_message": str(exc),
        },
    )


for module_function in modules_functions:
    try:
        module_name, function_name, init_params = _parse_entrypoint(
            module_function
        )

        logger.info(f"Importing {module_name} and function {function_name}")

        module = importlib.import_module(module_name)
        function = getattr(module, function_name)
        if isinstance(function, type) and issubclass(function, BaseToolkit):
            function = function(**init_params).get_tools()

        function = _as_function_tools(function)

        for func in function:

            @app.post(f"/{func.get_function_name()}")
            async def dynamic_function(data: Dict, func=func):
                redirect_stdout = bool(data.get("redirect_stdout", False))
                output_buffer = (
                    _LimitedStringIO(_MAX_STDOUT_CHARS)
                    if redirect_stdout
                    else None
                )
                try:
                    stdout_context = (
                        contextlib.redirect_stdout(output_buffer)
                        if output_buffer is not None
                        else contextlib.nullcontext()
                    )
                    capture_lock = (
                        _STDOUT_REDIRECT_LOCK
                        if output_buffer is not None
                        else contextlib.nullcontext()
                    )
                    with capture_lock, stdout_context:
                        response_data = func.func(
                            *data["args"], **data["kwargs"]
                        )
                    payload = {
                        "output": json.dumps(
                            response_data, ensure_ascii=False
                        )
                    }
                    if output_buffer is not None:
                        payload["stdout"] = output_buffer.value()
                    return payload
                finally:
                    if output_buffer is not None:
                        output_buffer.close()

    except (ImportError, AttributeError, ValueError) as e:
        logger.error(f"Error importing {module_function}: {e}")


if __name__ == "__main__":
    uvicorn.run("__main__:app", host="0.0.0.0", port=8000, reload=True)
