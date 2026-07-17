"""Catalog-driven Unified Model Runtime.

The Runtime is the single seam between active callers and Provider adapters.
Callers choose canonical ``provider/model`` identities; adapters own SDK and
HTTP details, while this module owns capability validation, retries, and
Provider concurrency.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Protocol, Sequence
from urllib.parse import urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import yaml

from .base_model import (
    AuthenticationError,
    BaseModel,
    ModelError,
    ModelRunTerminalError,
    RateLimitError,
    ServiceUnavailableError,
    TokenLimitError,
    UnsupportedModelCapabilityError,
)
from .embedding_models import EmbeddingModel
from .openai_model import OpenAIModel
from .runtime import (
    ImageContent,
    Message,
    MessageContent,
    ModelRunRequest,
    ModelRunResult,
    ReasoningConfig,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderDefinition:
    name: str
    protocol: str
    settings: Mapping[str, Any]


@dataclass(frozen=True)
class ModelDefinition:
    canonical_id: str
    provider: str
    model: str
    protocol: str
    capabilities: frozenset[str]
    settings: Mapping[str, Any]


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 8
    max_elapsed_seconds: float = 900.0
    initial_backoff_seconds: float = 2.0
    max_backoff_seconds: float = 60.0


class ModelAdapter(Protocol):
    async def run(self, request: ModelRunRequest) -> ModelRunResult:
        """Execute one typed text/vision/JSON/tool request."""


class ImageAdapter(Protocol):
    async def generate_image(self, *, prompt: str, aspect_ratio: str) -> bytes:
        """Generate and return image bytes."""


class EmbeddingAdapter(Protocol):
    def encode(self, texts: Sequence[str]) -> Any:
        """Encode text into vectors."""


class ModelCatalog:
    """Immutable, validated vocabulary of Providers and model identities."""

    def __init__(
        self,
        *,
        version: int,
        active_text_model: str,
        capability_models: Mapping[str, str],
        providers: Mapping[str, ProviderDefinition],
        models: Mapping[str, ModelDefinition],
        retry: RetryPolicy,
        concurrency: Mapping[str, int],
    ) -> None:
        self.version = version
        self.active_text_model = active_text_model
        self.capability_models = dict(capability_models)
        self.providers = dict(providers)
        self.models = dict(models)
        self.retry = retry
        self.concurrency = dict(concurrency)
        self._validate()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ModelCatalog":
        if not isinstance(raw, Mapping):
            raise ValueError("Model catalog must be a mapping")
        providers_raw = raw.get("providers")
        models_raw = raw.get("models")
        if not isinstance(providers_raw, Mapping) or not isinstance(models_raw, Mapping):
            raise ValueError("Model catalog requires providers and models mappings")

        providers: dict[str, ProviderDefinition] = {}
        for name, value in providers_raw.items():
            if not isinstance(name, str) or not isinstance(value, Mapping):
                raise ValueError("Provider definitions must be named mappings")
            settings = dict(value)
            protocol = str(settings.pop("protocol", ""))
            if not protocol:
                raise ValueError(f"Provider {name!r} must declare protocol")
            providers[name] = ProviderDefinition(name, protocol, settings)

        models: dict[str, ModelDefinition] = {}
        for canonical_id, value in models_raw.items():
            if not isinstance(canonical_id, str) or not isinstance(value, Mapping):
                raise ValueError("Model definitions must be named mappings")
            if "/" not in canonical_id:
                raise ValueError(
                    "Every model must use a canonical provider/model identity"
                )
            settings = dict(value)
            provider = str(settings.pop("provider", canonical_id.split("/", 1)[0]))
            model = str(settings.pop("model", canonical_id.split("/", 1)[1]))
            canonical_provider = canonical_id.split("/", 1)[0]
            if provider != canonical_provider:
                raise ValueError(
                    f"Model {canonical_id!r} provider must match its canonical identity"
                )
            protocol = str(settings.pop("protocol", ""))
            capabilities = settings.pop("capabilities", ())
            if not isinstance(capabilities, (list, tuple, set)):
                raise ValueError(f"Model {canonical_id!r} capabilities must be a list")
            if not protocol:
                provider_def = providers.get(provider)
                protocol = provider_def.protocol if provider_def else ""
            models[canonical_id] = ModelDefinition(
                canonical_id=canonical_id,
                provider=provider,
                model=model,
                protocol=protocol,
                capabilities=frozenset(str(item) for item in capabilities),
                settings=settings,
            )

        retry_raw = raw.get("retry", {})
        if not isinstance(retry_raw, Mapping):
            raise ValueError("Model catalog retry must be a mapping")
        retry = RetryPolicy(
            max_attempts=int(retry_raw.get("max_attempts", 8)),
            max_elapsed_seconds=float(retry_raw.get("max_elapsed_seconds", 900)),
            initial_backoff_seconds=float(
                retry_raw.get("initial_backoff_seconds", 2)
            ),
            max_backoff_seconds=float(retry_raw.get("max_backoff_seconds", 60)),
        )
        concurrency_raw = raw.get("concurrency", {})
        if not isinstance(concurrency_raw, Mapping):
            raise ValueError("Model catalog concurrency must be a mapping")
        concurrency = {str(key): int(value) for key, value in concurrency_raw.items()}
        capability_models = raw.get("capability_models", {})
        if not isinstance(capability_models, Mapping):
            raise ValueError("Model catalog capability_models must be a mapping")
        return cls(
            version=int(raw.get("version", 1)),
            active_text_model=str(raw.get("active_text_model", "")),
            capability_models={str(k): str(v) for k, v in capability_models.items()},
            providers=providers,
            models=models,
            retry=retry,
            concurrency=concurrency,
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ModelCatalog":
        catalog_path = Path(path)
        try:
            raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
        except OSError as error:
            raise ValueError(f"Unable to read model catalog {catalog_path}: {error}") from error
        except yaml.YAMLError as error:
            raise ValueError(f"Unable to parse model catalog {catalog_path}: {error}") from error
        return cls.from_mapping(raw)

    def _validate(self) -> None:
        if self.version < 1:
            raise ValueError("Model catalog version must be positive")
        if not self.active_text_model:
            raise ValueError("Model catalog requires active_text_model")
        self.resolve_model(self.active_text_model)
        active_text = self.resolve_model(self.active_text_model, capability="text")
        for capability, canonical_id in self.capability_models.items():
            self.resolve_model(canonical_id, capability=capability)
        image_model_id = self.capability_models.get("image_generation")
        if image_model_id is not None:
            image_model = self.resolve_model(image_model_id, capability="image_generation")
            if image_model.provider != active_text.provider:
                raise ValueError(
                    "Text and image-generation bindings must use the same Provider"
                )
        for canonical_id, model_def in self.models.items():
            provider = self.providers.get(model_def.provider)
            if provider is None:
                raise ValueError(
                    f"Model {canonical_id!r} references unknown Provider "
                    f"{model_def.provider!r}"
                )
            if model_def.protocol != provider.protocol and model_def.protocol not in {
                "dashscope_multimodal",
                "openai_images",
                "local_embedding",
            }:
                raise ValueError(
                    f"Model {canonical_id!r} protocol {model_def.protocol!r} "
                    f"does not match Provider protocol {provider.protocol!r}"
                )
            if not model_def.capabilities:
                raise ValueError(f"Model {canonical_id!r} must declare capabilities")
            if model_def.provider not in {"relay", "qwen", "local"}:
                raise ValueError(
                    f"Provider {model_def.provider!r} is not in the active Provider set"
                )
            if model_def.provider == "local" and model_def.capabilities != {"embedding"}:
                raise ValueError("The local Provider is reserved for embeddings")
            if model_def.settings.get("background") is not None:
                raise ValueError(
                    f"Model {canonical_id!r} cannot configure background execution"
                )
            if model_def.protocol == "dashscope_multimodal":
                native_base_url = (
                    model_def.settings.get("native_base_url")
                    or provider.settings.get("native_base_url")
                    or provider.settings.get("base_url")
                )
                if (
                    not isinstance(native_base_url, str)
                    or urlparse(native_base_url).scheme not in {"http", "https"}
                ):
                    raise ValueError(
                        f"Model {canonical_id!r} must declare an HTTP(S) native_base_url"
                    )
                endpoint = model_def.settings.get(
                    "endpoint",
                    "/api/v1/services/aigc/multimodal-generation/generation",
                )
                if not isinstance(endpoint, str) or not endpoint.startswith("/"):
                    raise ValueError(
                        f"Model {canonical_id!r} must declare an absolute native endpoint"
                    )
        for provider in self.providers.values():
            if provider.protocol == "local_embedding":
                continue
            endpoint = provider.settings.get("base_url")
            if not isinstance(endpoint, str) or urlparse(endpoint).scheme not in {
                "http",
                "https",
            }:
                raise ValueError(
                    f"Provider {provider.name!r} must declare an HTTP(S) base_url"
                )
            if not provider.settings.get("api_key") and not provider.settings.get(
                "api_key_env"
            ):
                raise ValueError(
                    f"Provider {provider.name!r} must declare api_key or api_key_env"
                )
        for provider, limit in self.concurrency.items():
            if limit < 1:
                raise ValueError(f"Concurrency limit for {provider!r} must be positive")
        if self.retry.max_attempts < 1:
            raise ValueError("retry.max_attempts must be positive")
        if self.retry.max_elapsed_seconds <= 0:
            raise ValueError("retry.max_elapsed_seconds must be positive")

    def resolve_model(
        self, canonical_id: str, *, capability: str | None = None
    ) -> ModelDefinition:
        if "/" not in canonical_id:
            raise ValueError(
                "Use a canonical provider/model identity; implicit Provider "
                "resolution is not supported"
            )
        model_def = self.models.get(canonical_id)
        if model_def is None:
            raise ValueError(f"Unknown canonical model identity: {canonical_id}")
        if capability and capability not in model_def.capabilities:
            raise ValueError(
                f"Model {canonical_id!r} does not declare capability {capability!r}"
            )
        return model_def

    def provider_for(self, model_def: ModelDefinition) -> ProviderDefinition:
        return self.providers[model_def.provider]

    def binding_for(self, capability: str) -> ModelDefinition:
        canonical_id = self.capability_models.get(capability)
        if canonical_id is None:
            raise ValueError(f"No model binding configured for capability {capability!r}")
        return self.resolve_model(canonical_id, capability=capability)


class _DashScopeImageAdapter:
    def __init__(self, model_def: ModelDefinition, provider: ProviderDefinition) -> None:
        self.model_def = model_def
        self.provider = provider

    async def generate_image(self, *, prompt: str, aspect_ratio: str) -> bytes:
        return await asyncio.to_thread(
            self._generate_sync, prompt=prompt, aspect_ratio=aspect_ratio
        )

    def _generate_sync(self, *, prompt: str, aspect_ratio: str) -> bytes:
        base_url = str(
            self.model_def.settings.get("native_base_url")
            or self.provider.settings.get("native_base_url")
            or self.provider.settings.get("base_url")
            or "https://dashscope.aliyuncs.com"
        ).rstrip("/")
        endpoint = str(
            self.model_def.settings.get("endpoint")
            or "/api/v1/services/aigc/multimodal-generation/generation"
        )
        api_key = _read_api_key(self.provider.settings)
        if not api_key:
            raise AuthenticationError(
                f"Missing API key for Provider {self.provider.name!r}"
            )
        payload = {
            "model": self.model_def.model,
            "input": {
                "messages": [
                    {"role": "user", "content": [{"text": prompt}]}
                ]
            },
            "parameters": {
                "size": _image_size(aspect_ratio),
                "prompt_extend": False,
                "watermark": False,
            },
        }
        request = Request(
            f"{base_url}{endpoint}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=float(self.provider.settings.get("timeout", 600))) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise _http_error(error) from error
        except OSError as error:
            raise ServiceUnavailableError(str(error)) from error
        choices = data.get("output", {}).get("choices", [])
        content = choices[0].get("message", {}).get("content", []) if choices else []
        image_url = next(
            (item.get("image") for item in content if isinstance(item, Mapping)),
            None,
        )
        if not image_url:
            raise ModelRunTerminalError("DashScope image response did not include an image URL")
        try:
            with urlopen(image_url, timeout=120) as image_response:
                return image_response.read()
        except HTTPError as error:
            raise _http_error(error) from error
        except OSError as error:
            raise ServiceUnavailableError(str(error)) from error


class _OpenAIImageAdapter:
    def __init__(self, model_def: ModelDefinition, provider: ProviderDefinition) -> None:
        from openai import OpenAI

        settings = provider.settings
        api_key = _read_api_key(settings)
        if not api_key:
            raise AuthenticationError(
                f"Missing API key for Provider {provider.name!r}"
            )
        self.model_def = model_def
        self.client = OpenAI(
            api_key=api_key,
            base_url=settings.get("base_url"),
            timeout=float(settings.get("timeout", 600)),
        )

    async def generate_image(self, *, prompt: str, aspect_ratio: str) -> bytes:
        response = await asyncio.to_thread(
            self.client.images.generate,
            model=self.model_def.model,
            prompt=prompt,
            size=_openai_image_size(aspect_ratio),
            response_format="b64_json",
        )
        data = getattr(response, "data", None) or []
        first = data[0] if data else None
        encoded = getattr(first, "b64_json", None) if first else None
        if isinstance(encoded, str) and encoded:
            return base64.b64decode(encoded)
        image_url = getattr(first, "url", None) if first else None
        if isinstance(image_url, str) and image_url:
            return await asyncio.to_thread(_download_image, image_url)
        raise ModelRunTerminalError("OpenAI image response did not include image data")


class _LocalEmbeddingAdapter:
    def __init__(self, model_def: ModelDefinition, provider: ProviderDefinition) -> None:
        del provider
        model_name = model_def.model
        self.model = EmbeddingModel(model_type="local", model_name=model_name)

    def encode(self, texts: Sequence[str]) -> Any:
        return self.model.encode(list(texts))

    @property
    def model_name(self) -> str:
        return self.model.model_name

    @property
    def model_type(self) -> str:
        return self.model.model_type

    @property
    def dimension(self) -> int:
        return self.model.dimension


class _RuntimeEmbeddingModel:
    """Synchronous embedding seam for the legacy FAISS retriever."""

    def __init__(self, runtime: "UnifiedModelRuntime", model_id: str) -> None:
        self.runtime = runtime
        self.model_id = model_id
        model_def = runtime.catalog.resolve_model(model_id, capability="embedding")
        self.model_name = model_def.model
        self.model_type = model_def.provider
        adapter = runtime._adapter_for(model_def)
        self.dimension = adapter.dimension

    def encode(self, texts: Sequence[str] | str, **_: Any) -> Any:
        values = [texts] if isinstance(texts, str) else list(texts)
        return _run_sync(self.runtime.embed(values, model_id=self.model_id))


class _RuntimeBoundModel(BaseModel):
    def __init__(self, runtime: "UnifiedModelRuntime", model_id: str, capability: str) -> None:
        super().__init__()
        self.runtime = runtime
        self.model_id = model_id
        self.capability = capability
        self.model_name = runtime.catalog.resolve_model(model_id).model
        self.supports_prompt_cache = runtime.catalog.resolve_model(model_id).protocol == "responses"

    async def _run(self, request: ModelRunRequest) -> ModelRunResult:
        return await self.runtime.run(
            request, model_id=self.model_id, capability=self.capability
        )

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "_RuntimeBoundModel":
        raise TypeError("Runtime-bound models must be created by UnifiedModelRuntime")


class UnifiedModelRuntime:
    """Deep model module that centralizes catalog resolution and request policy."""

    def __init__(
        self,
        catalog: ModelCatalog,
        *,
        adapter_factory: Callable[[ModelDefinition, ProviderDefinition], Any] | None = None,
    ) -> None:
        self.catalog = catalog
        if adapter_factory is None:
            self._validate_runtime_environment()
        self._adapter_factory = adapter_factory or self._default_adapter_factory
        self._adapters: dict[str, Any] = {}
        self._models: dict[tuple[str, str], _RuntimeBoundModel] = {}
        self._adapter_lock = threading.Lock()
        self._slots = {
            provider: threading.BoundedSemaphore(limit)
            for provider, limit in catalog.concurrency.items()
        }

    @classmethod
    def from_catalog_path(cls, path: str | Path, **kwargs: Any) -> "UnifiedModelRuntime":
        return cls(ModelCatalog.from_yaml(path), **kwargs)

    @classmethod
    def from_default_catalog(cls, **kwargs: Any) -> "UnifiedModelRuntime":
        path = Path(__file__).resolve().parents[3] / "config" / "model_catalog.yaml"
        return cls.from_catalog_path(path, **kwargs)

    def model_for(self, model_id: str | None = None, *, capability: str = "text") -> BaseModel:
        model_def = self._resolve(model_id, capability=capability)
        key = (model_def.canonical_id, capability)
        if key not in self._models:
            self._models[key] = _RuntimeBoundModel(self, model_def.canonical_id, capability)
        return self._models[key]

    def embedding_model(self, model_id: str | None = None) -> _RuntimeEmbeddingModel:
        """Return the configured embedding binding at the memory seam."""

        model_def = self._resolve(model_id, capability="embedding")
        return _RuntimeEmbeddingModel(self, model_def.canonical_id)

    def create_model_for_agent(self, agent_type: str, config: Mapping[str, Any]) -> BaseModel:
        del agent_type
        del config
        return self.model_for(capability="text")

    async def run(
        self,
        request: ModelRunRequest,
        *,
        model_id: str | None = None,
        capability: str = "text",
    ) -> ModelRunResult:
        model_def = self._resolve_request_model(
            request, model_id=model_id, capability=capability
        )
        adapter = self._adapter_for(model_def)
        result = await self._execute(
            model_def.provider,
            lambda: adapter.run(request),
        )
        if not isinstance(result, ModelRunResult):
            raise TypeError("Runtime adapter returned a non-ModelRunResult")
        return result

    async def generate_text(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model_id: str | None = None,
        capability: str = "text",
        reasoning: ReasoningConfig | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        result = await self.run(
            ModelRunRequest(
                instructions=system_prompt,
                input=(Message.user(prompt),),
                reasoning=reasoning,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            ),
            model_id=model_id,
            capability=capability,
        )
        return result.text

    async def generate_json(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any] | None = None,
        system_prompt: str | None = None,
        model_id: str | None = None,
        reasoning: ReasoningConfig | None = None,
    ) -> dict[str, Any]:
        instructions = system_prompt or ""
        if schema is not None:
            instructions = (
                f"{instructions}\n\nRespond with JSON matching this schema: "
                f"{json.dumps(schema, ensure_ascii=False)}"
            ).strip()
        result = await self.run(
            ModelRunRequest(
                instructions=instructions or None,
                input=(Message.user(prompt),),
                response_format="json_object",
                reasoning=reasoning,
            ),
            model_id=model_id,
            capability="json",
        )
        parsed = json.loads(result.text)
        if not isinstance(parsed, dict):
            raise ModelRunTerminalError("Runtime JSON operation requires an object")
        return parsed

    async def generate_image(
        self,
        prompt: str,
        *,
        aspect_ratio: str = "1:1",
        model_id: str | None = None,
    ) -> bytes:
        model_def = self._resolve(model_id, capability="image_generation")
        adapter = self._adapter_for(model_def)
        if not hasattr(adapter, "generate_image"):
            raise UnsupportedModelCapabilityError(
                f"Adapter for {model_def.canonical_id} cannot generate images"
            )
        return await self._execute(
            model_def.provider,
            lambda: adapter.generate_image(
                prompt=prompt, aspect_ratio=aspect_ratio
            ),
        )

    async def embed(
        self,
        texts: str | Sequence[str],
        *,
        model_id: str | None = None,
    ) -> Any:
        model_def = self._resolve(model_id, capability="embedding")
        adapter = self._adapter_for(model_def)
        if not hasattr(adapter, "encode"):
            raise UnsupportedModelCapabilityError(
                f"Adapter for {model_def.canonical_id} cannot create embeddings"
            )
        values = [texts] if isinstance(texts, str) else list(texts)
        encoded = await self._execute(
            model_def.provider,
            lambda: asyncio.to_thread(adapter.encode, values),
        )
        if isinstance(texts, str):
            return encoded[0]
        return encoded

    def _resolve(self, model_id: str | None, *, capability: str) -> ModelDefinition:
        if model_id is None:
            if capability in self.catalog.capability_models:
                return self.catalog.binding_for(capability)
            return self.catalog.resolve_model(
                self.catalog.active_text_model, capability=capability
            )
        return self.catalog.resolve_model(model_id, capability=capability)

    def _resolve_request_model(
        self,
        request: ModelRunRequest,
        *,
        model_id: str | None,
        capability: str,
    ) -> ModelDefinition:
        required = {capability}
        if request.response_format == "json_object":
            required.add("json")
        if request.tools:
            required.add("tools")
        if request.previous_response_id:
            required.add("continuation")
        if request.reasoning is not None:
            required.add("reasoning")
        if any(
            isinstance(item, Message)
            and any(isinstance(content, ImageContent) for content in item.content)
            for item in request.input
        ):
            required.add("vision")

        resolved = self._resolve(model_id, capability=capability)
        missing = sorted(required.difference(resolved.capabilities))
        if missing:
            raise UnsupportedModelCapabilityError(
                f"Model {resolved.canonical_id!r} does not declare required "
                f"capabilities: {', '.join(missing)}"
            )
        return resolved

    def _validate_runtime_environment(self) -> None:
        required_provider_names = {
            self.catalog.resolve_model(self.catalog.active_text_model).provider
        }
        for model_id in self.catalog.capability_models.values():
            required_provider_names.add(self.catalog.resolve_model(model_id).provider)
        for provider_name in required_provider_names:
            provider = self.catalog.providers[provider_name]
            if provider.protocol == "local_embedding":
                continue
            api_key = _read_api_key(provider.settings)
            if not api_key:
                env_name = provider.settings.get("api_key_env")
                raise AuthenticationError(
                    f"Missing API key for Provider {provider.name!r}"
                    + (f" (expected {env_name})" if env_name else "")
                )

    def _adapter_for(self, model_def: ModelDefinition) -> Any:
        with self._adapter_lock:
            adapter = self._adapters.get(model_def.canonical_id)
            if adapter is None:
                adapter = self._adapter_factory(
                    model_def, self.catalog.provider_for(model_def)
                )
                self._adapters[model_def.canonical_id] = adapter
            return adapter

    async def _execute(self, provider: str, operation: Callable[[], Awaitable[Any]]) -> Any:
        slot = self._slots.get(provider)
        if slot is None:
            raise ValueError(f"No concurrency limit configured for Provider {provider!r}")
        await asyncio.to_thread(slot.acquire)
        try:
            started = time.monotonic()
            delay = self.catalog.retry.initial_backoff_seconds
            last_error: Exception | None = None
            for attempt in range(1, self.catalog.retry.max_attempts + 1):
                try:
                    return await operation()
                except Exception as error:
                    last_error = error
                    if not _is_retryable(error):
                        raise
                    elapsed = time.monotonic() - started
                    if attempt >= self.catalog.retry.max_attempts or elapsed >= self.catalog.retry.max_elapsed_seconds:
                        raise
                    remaining = self.catalog.retry.max_elapsed_seconds - elapsed
                    await asyncio.sleep(min(delay, self.catalog.retry.max_backoff_seconds, remaining))
                    delay = min(
                        max(delay * 2, self.catalog.retry.initial_backoff_seconds),
                        self.catalog.retry.max_backoff_seconds,
                    )
            assert last_error is not None
            raise last_error
        finally:
            slot.release()

    @staticmethod
    def _default_adapter_factory(
        model_def: ModelDefinition, provider: ProviderDefinition
    ) -> Any:
        if model_def.protocol == "responses":
            settings = dict(provider.settings)
            settings.update(model_def.settings)
            settings.pop("native_base_url", None)
            settings.pop("endpoint", None)
            settings.update(
                {
                    "provider": provider.name,
                    "provider_name": provider.name,
                    "model_name": model_def.model,
                    "api_mode": "responses",
                }
            )
            return OpenAIModel.from_config(settings)
        if model_def.protocol == "dashscope_multimodal":
            return _DashScopeImageAdapter(model_def, provider)
        if model_def.protocol == "openai_images":
            return _OpenAIImageAdapter(model_def, provider)
        if model_def.protocol == "local_embedding":
            return _LocalEmbeddingAdapter(model_def, provider)
        raise ValueError(
            f"Unsupported declared protocol {model_def.protocol!r} for "
            f"{model_def.canonical_id}"
        )


def _read_api_key(settings: Mapping[str, Any]) -> str:
    value = settings.get("api_key")
    if isinstance(value, str) and value:
        return value
    env_name = settings.get("api_key_env")
    return os.getenv(str(env_name), "") if env_name else ""


def _is_retryable(error: Exception) -> bool:
    if isinstance(
        error,
        (
            AuthenticationError,
            TokenLimitError,
            UnsupportedModelCapabilityError,
            ModelRunTerminalError,
        ),
    ):
        return False
    if isinstance(error, (RateLimitError, ServiceUnavailableError, TimeoutError, OSError)):
        return True
    status_code = getattr(error, "status_code", None)
    return status_code in {408, 409, 425, 429, 500, 502, 503, 504}


def _http_error(error: HTTPError) -> Exception:
    if error.code in {401, 403}:
        return AuthenticationError(f"Provider rejected credentials (HTTP {error.code})")
    if error.code == 429:
        return RateLimitError(f"Provider rate limited the request (HTTP {error.code})")
    if error.code >= 500:
        return ServiceUnavailableError(f"Provider unavailable (HTTP {error.code})")
    return ModelRunTerminalError(f"Provider rejected the request (HTTP {error.code})")


def _image_size(aspect_ratio: str) -> str:
    normalized = aspect_ratio.strip()
    if normalized in {"9:16", "2:3", "3:4"}:
        return "1024*1536"
    if normalized in {"16:9", "3:2", "4:3"}:
        return "1536*1024"
    return "1024*1024"


def _openai_image_size(aspect_ratio: str) -> str:
    normalized = aspect_ratio.strip()
    if normalized in {"9:16", "2:3", "3:4"}:
        return "1024x1536"
    if normalized in {"16:9", "3:2", "4:3"}:
        return "1536x1024"
    return "1024x1024"


def _download_image(url: str) -> bytes:
    try:
        with urlopen(url, timeout=120) as response:
            return response.read()
    except OSError as error:
        raise ServiceUnavailableError(str(error)) from error


def _run_sync(coroutine: Awaitable[Any]) -> Any:
    """Bridge synchronous memory code to the Runtime's async operations."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
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


__all__ = ["ModelCatalog", "ModelDefinition", "ProviderDefinition", "RetryPolicy", "UnifiedModelRuntime"]
