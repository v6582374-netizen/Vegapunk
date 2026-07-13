"""InternS1 adapter for the InternAgent Model Runtime."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .chat_compatible_model import ChatCompatibleModel


class S1Model(ChatCompatibleModel):
    """InternS1 provider using its supported Chat-compatible subset."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: str = "intern-s1",
        max_output_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: int = 60,
        api_mode: str = "chat_completions",
        client: Optional[Any] = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            timeout=timeout,
            api_mode=api_mode,
            api_key_env_var="INS1_API_KEY",
            base_url_env_var="INS1_API_BASE_URL",
            provider_name="InternS1",
            strip_reasoning_tags=True,
            client=client,
        )

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "S1Model":
        return cls(
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
            model_name=config.get("model_name", "intern-s1"),
            max_output_tokens=config.get("max_output_tokens", 4096),
            temperature=config.get("temperature", 0.7),
            timeout=config.get("timeout", 60),
            api_mode=config.get("api_mode", "chat_completions"),
        )
