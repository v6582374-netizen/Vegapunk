"""Dedicated OpenAI-compatible image generation adapter for PaperOrchestra."""

from __future__ import annotations

import base64
import os
from typing import Any, Mapping

import httpx
from openai import AsyncOpenAI

from .config import ImageGenerationConfig
from .data_types import PaperOrchestraStageError


class OpenAIImageGenerationAdapter:
    def __init__(
        self, *, config: ImageGenerationConfig, api_key: str, client: Any
    ) -> None:
        self.config = config
        self._api_key = api_key
        self._client = client

    @classmethod
    def from_environment(
        cls,
        *,
        config: ImageGenerationConfig,
        environ: Mapping[str, str] | None = None,
        client_factory: Any = AsyncOpenAI,
    ) -> "OpenAIImageGenerationAdapter":
        environment = environ if environ is not None else os.environ
        api_key = environment.get(config.api_key_env)
        if not api_key:
            raise PaperOrchestraStageError(
                stage="generate_figures",
                code="missing_image_api_key",
                message=(
                    "image generation requires environment variable "
                    f"{config.api_key_env}"
                ),
            )
        client = client_factory(api_key=api_key, base_url=config.base_url)
        return cls(config=config, api_key=api_key, client=client)

    async def generate(self, *, prompt: str, aspect_ratio: str) -> bytes:
        try:
            response = await self._client.images.generate(
                model=self.config.model,
                prompt=prompt,
                n=1,
                response_format="b64_json",
                extra_body={"aspect_ratio": aspect_ratio},
            )
            data = getattr(response, "data", None)
            first = data[0] if isinstance(data, list) and data else None
            encoded = getattr(first, "b64_json", None)
            if isinstance(encoded, str) and encoded:
                return base64.b64decode(encoded)
            url = getattr(first, "url", None)
            if isinstance(url, str) and url:
                async with httpx.AsyncClient(timeout=120) as client:
                    downloaded = await client.get(url)
                    downloaded.raise_for_status()
                    return downloaded.content
        except PaperOrchestraStageError:
            raise
        except Exception as error:
            raise PaperOrchestraStageError(
                stage="generate_figures",
                code="image_generation_failed",
                message=str(error),
            ) from error
        raise PaperOrchestraStageError(
            stage="generate_figures",
            code="invalid_image_response",
            message="image provider returned no image bytes",
        )


class EnvironmentImageGenerator:
    """Resolve the configured image client only when a diagram is requested."""

    def __init__(self, *, config: ImageGenerationConfig) -> None:
        self.config = config
        self._adapter: OpenAIImageGenerationAdapter | None = None

    async def generate(self, *, prompt: str, aspect_ratio: str) -> bytes:
        if self._adapter is None:
            self._adapter = OpenAIImageGenerationAdapter.from_environment(
                config=self.config
            )
        return await self._adapter.generate(
            prompt=prompt, aspect_ratio=aspect_ratio
        )
