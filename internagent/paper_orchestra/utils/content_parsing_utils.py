"""Response parsing adapted from PaperOrchestra provider-specific utilities."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_fenced_content(response: str, language: str) -> str:
    if not isinstance(response, str) or not response.strip():
        raise ValueError("model response is empty")
    match = re.search(
        rf"```{re.escape(language)}\s*(.*?)```",
        response,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return (match.group(1) if match else response).strip()


def extract_json_response(response: dict[str, Any]) -> dict[str, Any]:
    parsed = response.get("parsed_response")
    if isinstance(parsed, dict):
        return parsed
    content: Any = response.get("content")
    if content is None:
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            content = None
    if not isinstance(content, str):
        raise ValueError("multimodal model response has no text content")
    fenced = extract_fenced_content(content, "json")
    parsed = json.loads(fenced)
    if not isinstance(parsed, dict):
        raise ValueError("multimodal model response must contain a JSON object")
    return parsed
