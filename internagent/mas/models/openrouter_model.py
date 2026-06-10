"""
OpenRouter Model Adapter for InternAgent.

OpenRouter exposes an OpenAI-compatible chat completions API. This adapter keeps
OpenRouter as a first-class provider while reusing the existing OpenAI-compatible
implementation.
"""

import os
from typing import Any, Dict, Optional

from .openai_model import OpenAIModel


class OpenRouterModel(OpenAIModel):
    """OpenRouter implementation backed by the OpenAI-compatible API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: str = "moonshotai/kimi-k2.6:free",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: int = 600,
        default_headers: Optional[Dict[str, str]] = None,
        site_url: Optional[str] = None,
        app_name: Optional[str] = None,
    ):
        api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        base_url = (
            base_url
            or os.environ.get("OPENROUTER_BASE_URL")
            or os.environ.get("OPENROUTER_API_BASE_URL")
            or "https://openrouter.ai/api/v1"
        )

        headers = dict(default_headers or {})
        site_url = site_url or os.environ.get("OPENROUTER_SITE_URL")
        app_name = app_name or os.environ.get("OPENROUTER_APP_NAME") or "InternAgent"

        if site_url:
            headers.setdefault("HTTP-Referer", site_url)
        if app_name:
            headers.setdefault("X-OpenRouter-Title", app_name)

        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            default_headers=headers or None,
            api_key_env_var="OPENROUTER_API_KEY",
            provider_name="OpenRouter",
        )

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "OpenRouterModel":
        """Create an OpenRouter model instance from a configuration dictionary."""
        return cls(
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
            model_name=config.get("model_name", "moonshotai/kimi-k2.6:free"),
            max_tokens=config.get("max_tokens", 4096),
            temperature=config.get("temperature", 0.7),
            timeout=config.get("timeout", 600),
            default_headers=config.get("default_headers"),
            site_url=config.get("site_url"),
            app_name=config.get("app_name"),
        )
