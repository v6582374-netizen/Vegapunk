"""Synchronous bridge from upstream PaperOrchestra to InternAgent Runtime."""

from __future__ import annotations

import base64
import json
import os
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.request import urlopen

from internagent.mas.models.runtime import (
    Message,
    MessageContent,
    ModelRunRequest,
)


ModelFactory = Callable[..., Any]
ImageClientFactory = Callable[..., Any]


class PaperOrchestraResponsesRuntime:
    """Route upstream synchronous calls through one configured relay provider."""

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        model_factory: ModelFactory | None = None,
        image_client_factory: ImageClientFactory | None = None,
    ) -> None:
        provider = config.get("provider")
        if not isinstance(provider, Mapping) or not provider.get("base_url"):
            raise ValueError("PaperOrchestra Runtime requires provider.base_url")
        self.provider_config = dict(provider)
        self.provider_config["provider"] = "openai"
        self.provider_config["api_mode"] = "responses"
        # The relay model used by PaperOrchestra rejects the Responses API
        # temperature parameter.  Keep this override local to the vendored
        # bridge so InternAgent's other model runtimes retain their settings.
        self.provider_config["temperature"] = None
        models = config.get("models", {})
        aliases = config.get("model_aliases", {})
        self.models = dict(models) if isinstance(models, Mapping) else {}
        self.model_aliases = dict(aliases) if isinstance(aliases, Mapping) else {}
        concurrency = config.get("max_concurrent_model_requests", 2)
        if (
            isinstance(concurrency, bool)
            or not isinstance(concurrency, int)
            or concurrency < 1
        ):
            raise ValueError(
                "PaperOrchestra max_concurrent_model_requests must be positive"
            )
        self.max_concurrent_model_requests = concurrency
        self._request_slots = threading.BoundedSemaphore(concurrency)
        self._model_cache_lock = threading.Lock()
        self._model_factory = model_factory or _default_model_factory
        self._image_client_factory = (
            image_client_factory or _default_image_client_factory
        )
        self._text_models: dict[str, Any] = {}

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
        resolved_model = self.resolve_model(model_name)
        model = self._text_models.get(resolved_model)
        if model is None:
            with self._model_cache_lock:
                model = self._text_models.get(resolved_model)
                if model is None:
                    model = self._model_factory(
                        model_name=resolved_model,
                        runtime_config=dict(self.provider_config),
                        agent_role="paper_orchestra",
                    )
                    self._text_models[resolved_model] = model
        with self._request_slots:
            result = model.run(
                ModelRunRequest(
                    instructions=system_prompt,
                    input=(Message(role="user", content=tuple(content)),),
                    temperature=None,
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
        resolved_model = self.resolve_model(
            model_name or str(self.models.get("image", ""))
        )
        if not resolved_model:
            raise ValueError("PaperOrchestra image model is not configured")
        provider = self.provider_config
        api_key = provider.get("api_key") or os.getenv("OPENAI_API_KEY")
        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "base_url": provider["base_url"],
        }
        for key in ("timeout", "default_headers"):
            if provider.get(key) is not None:
                client_kwargs[key] = provider[key]
        client = self._image_client_factory(**client_kwargs)
        with self._request_slots:
            response = client.images.generate(
                model=resolved_model,
                prompt=prompt,
                size=_image_size(aspect_ratio),
                response_format="b64_json",
            )
        data = _field(response, "data", None)
        if not data:
            raise ValueError("relay image endpoint returned no image data")
        first = data[0]
        encoded = _field(first, "b64_json", None)
        if isinstance(encoded, str) and encoded:
            return base64.b64decode(encoded)
        image_url = _field(first, "url", None)
        if isinstance(image_url, str) and image_url:
            with urlopen(image_url, timeout=120) as response_stream:
                return response_stream.read()
        raise ValueError("relay image endpoint returned neither b64_json nor url")

    def resolve_model(self, model_name: str) -> str:
        resolved = self.model_aliases.get(model_name, model_name)
        return str(resolved).strip()


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
    raw_path = os.getenv("PAPER_ORCHESTRA_RUNTIME_CONFIG")
    if not raw_path:
        raise ValueError("PAPER_ORCHESTRA_RUNTIME_CONFIG is not set")
    return _runtime_for_path(str(Path(raw_path).resolve()))


@lru_cache(maxsize=4)
def _runtime_for_path(path: str) -> PaperOrchestraResponsesRuntime:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("PaperOrchestra Runtime config must be a JSON object")
    return PaperOrchestraResponsesRuntime(data)


def _default_model_factory(**kwargs: Any) -> Any:
    from internagent.mas.agents.dr_agents.models.openai_model import (
        OpenAIModel as SynchronousOpenAIModel,
    )

    return SynchronousOpenAIModel(**kwargs)


def _default_image_client_factory(**kwargs: Any) -> Any:
    from openai import OpenAI

    return OpenAI(**kwargs)


def _image_size(aspect_ratio: str) -> str:
    normalized = aspect_ratio.strip()
    if normalized in {"9:16", "2:3", "3:4"}:
        return "1024x1536"
    if normalized in {"16:9", "3:2", "4:3"}:
        return "1536x1024"
    return "1024x1024"


def _field(value: Any, name: str, default: Any) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)
