"""Response parsing adapted from PaperOrchestra provider-specific utilities."""

from __future__ import annotations

import json
import re

from internagent.mas.models.runtime import ModelRunResult


def extract_fenced_content(response: str, language: str) -> str:
    if not isinstance(response, str) or not response.strip():
        raise ValueError("model response is empty")
    match = re.search(
        rf"```{re.escape(language)}\s*(.*?)```",
        response,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return (match.group(1) if match else response).strip()


def extract_json_response(response: ModelRunResult) -> dict[str, object]:
    if not isinstance(response, ModelRunResult):
        raise TypeError("expected an InternAgent ModelRunResult")
    content = response.text
    if not content:
        raise ValueError("multimodal model response has no text content")
    fenced = extract_fenced_content(content, "json")
    parsed = json.loads(fenced)
    if not isinstance(parsed, dict):
        raise ValueError("multimodal model response must contain a JSON object")
    return parsed
