"""Synchronous bridge from upstream PaperOrchestra to Vegapunk Runtime."""

from __future__ import annotations

import asyncio
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

from vegapunk.mas.models.runtime import (
    ImageContent,
    Message,
    MessageContent,
    ModelRunRequest,
)
from vegapunk.mas.models.unified_runtime import UnifiedModelRuntime


class PaperOrchestraResponsesRuntime:
    """Expose the upstream synchronous calls through one injected Runtime.

    The vendored package still uses synchronous worker functions, so this
    adapter owns only the sync-to-async conversion. Provider clients, model
    resolution, retries, and concurrency remain inside ``UnifiedModelRuntime``.
    """

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        *,
        runtime: UnifiedModelRuntime | None = None,
    ) -> None:
        config = dict(config or {})
        catalog_path = config.get("catalog_path")
        if runtime is None:
            if not isinstance(catalog_path, str) or not catalog_path:
                raise ValueError(
                    "PaperOrchestra Runtime requires catalog_path or an injected Runtime"
                )
            runtime = UnifiedModelRuntime.from_catalog_path(catalog_path)
        self.runtime = runtime
        models = config.get("models", {})
        self.models = dict(models) if isinstance(models, Mapping) else {}

    def generate_text(
        self,
        *,
        model_name: str,
        content: Sequence[MessageContent],
        system_prompt: str | None = None,
        temperature: float | None = None,
    ) -> str:
        if not content:
            raise ValueError("PaperOrchestra model content cannot be empty")
        model_id = self.resolve_model(model_name)
        capability = "vision" if any(
            isinstance(item, ImageContent) for item in content
        ) else "text"
        if capability == "vision":
            # PaperOrchestra's fixed vision binding covers image review while
            # ordinary writing and reflection remain on active_text_model.
            model_id = self.runtime.catalog.binding_for("vision").canonical_id
        result = _run_sync(
            self.runtime.run(
                ModelRunRequest(
                    instructions=system_prompt,
                    input=(Message(role="user", content=tuple(content)),),
                    temperature=temperature,
                ),
                model_id=model_id,
                capability=capability,
            )
        )
        text = result.text
        if not isinstance(text, str) or not text:
            raise ValueError("PaperOrchestra Runtime returned empty text")
        return text

    def generate_image(
        self,
        *,
        model_name: str,
        prompt: str,
        aspect_ratio: str,
    ) -> bytes:
        configured_model = model_name or str(self.models.get("image", ""))
        model_id = self.resolve_model(configured_model)
        return _run_sync(
            self.runtime.generate_image(
                prompt,
                aspect_ratio=aspect_ratio,
                model_id=model_id,
            )
        )

    def resolve_model(self, model_name: str) -> str:
        model_id = str(model_name).strip()
        if not model_id:
            raise ValueError("PaperOrchestra model identity cannot be empty")
        # ModelCatalog deliberately rejects aliases and implicit provider names.
        return self.runtime.catalog.resolve_model(model_id).canonical_id


def generate_text_from_environment(
    *,
    model_name: str,
    content: Sequence[MessageContent],
    system_prompt: str | None = None,
    temperature: float | None = None,
) -> str:
    return runtime_from_environment().generate_text(
        model_name=model_name,
        content=content,
        system_prompt=system_prompt,
        temperature=temperature,
    )


def generate_image_from_environment(
    *, model_name: str, prompt: str, aspect_ratio: str
) -> bytes:
    return runtime_from_environment().generate_image(
        model_name=model_name,
        prompt=prompt,
        aspect_ratio=aspect_ratio,
    )


def runtime_from_environment() -> PaperOrchestraResponsesRuntime:
    raw_path = os.getenv("PAPER_ORCHESTRA_CATALOG_PATH")
    if not raw_path:
        raise ValueError("PAPER_ORCHESTRA_CATALOG_PATH is not set")
    return _runtime_for_path(str(Path(raw_path).resolve()))


@lru_cache(maxsize=4)
def _runtime_for_path(path: str) -> PaperOrchestraResponsesRuntime:
    return PaperOrchestraResponsesRuntime({"catalog_path": path})


def _run_sync(coroutine):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    # A synchronous PaperOrchestra worker can be called from an async host.
    import threading

    result: list[Any] = []
    error: list[BaseException] = []

    def runner() -> None:
        try:
            result.append(asyncio.run(coroutine))
        except BaseException as exc:  # pragma: no cover - defensive bridge
            error.append(exc)

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0]


__all__ = [
    "PaperOrchestraResponsesRuntime",
    "generate_image_from_environment",
    "generate_text_from_environment",
    "runtime_from_environment",
]
