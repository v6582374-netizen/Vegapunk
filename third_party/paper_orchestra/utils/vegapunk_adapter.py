"""Translate upstream content containers to Vegapunk Runtime items."""

from __future__ import annotations

import base64
import io
from collections.abc import Iterable, Mapping
from typing import Any

from vegapunk.mas.models.runtime import ImageContent, MessageContent, TextContent
from vegapunk.paper_orchestra.responses_runtime import (
    generate_image_from_environment,
    generate_text_from_environment,
)
from pypdf import PdfReader


def call_responses_with_contents(
    *,
    contents: Any,
    model_name: str,
    generation_configs: Mapping[str, Any] | None = None,
    system_prompt: str | None = None,
) -> str:
    configs = dict(generation_configs or {})
    configured_instruction = configs.get("system_instruction")
    if system_prompt is None and configured_instruction is not None:
        system_prompt = str(configured_instruction)
    temperature = configs.get("temperature")
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
        temperature = None
    return generate_text_from_environment(
        model_name=model_name,
        content=tuple(_normalize_contents(contents)),
        system_prompt=system_prompt,
        temperature=float(temperature) if temperature is not None else None,
    )


def generate_image_base64(
    *, model_name: str, prompt: str, aspect_ratio: str
) -> str:
    image = generate_image_from_environment(
        model_name=model_name,
        prompt=prompt,
        aspect_ratio=aspect_ratio,
    )
    return base64.b64encode(image).decode("ascii")


def _normalize_contents(contents: Any) -> list[MessageContent]:
    normalized: list[MessageContent] = []
    for item in _flatten(contents):
        if isinstance(item, str):
            normalized.append(TextContent(item))
            continue
        if isinstance(item, Mapping):
            item_type = item.get("type")
            if item_type in {"text", "input_text"}:
                normalized.append(TextContent(str(item.get("text", ""))))
                continue
            if item_type in {"image_url", "input_image"}:
                image = item.get("image_url")
                if isinstance(image, Mapping):
                    image = image.get("url")
                if not isinstance(image, str):
                    raise TypeError("upstream image content is missing a URL")
                normalized.append(ImageContent(image, detail="original"))
                continue

        text = getattr(item, "text", None)
        inline_data = getattr(item, "inline_data", None)
        if isinstance(text, str) and text:
            normalized.append(TextContent(text))
        if inline_data is not None:
            data = getattr(inline_data, "data", None)
            mime_type = getattr(inline_data, "mime_type", None)
            if not isinstance(data, (bytes, bytearray)) or not isinstance(
                mime_type, str
            ):
                raise TypeError("upstream inline data is malformed")
            normalized.append(_binary_content(bytes(data), mime_type))
        if (isinstance(text, str) and text) or inline_data is not None:
            continue
        raise TypeError(f"unsupported upstream model content: {type(item).__name__}")
    if not normalized:
        raise ValueError("upstream model content is empty")
    return normalized


def _flatten(contents: Any) -> Iterable[Any]:
    if isinstance(contents, (str, bytes, bytearray, Mapping)):
        yield contents
        return
    parts = getattr(contents, "parts", None)
    if parts is not None:
        yield from _flatten(parts)
        return
    if isinstance(contents, Iterable):
        for item in contents:
            yield from _flatten(item)
        return
    yield contents


def _binary_content(data: bytes, mime_type: str) -> MessageContent:
    if mime_type == "application/pdf":
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if not text:
            text = "[The supplied PDF contained no extractable text.]"
        return TextContent(f"PDF Content:\n{text}")
    if mime_type.startswith("image/"):
        encoded = base64.b64encode(data).decode("ascii")
        return ImageContent(
            f"data:{mime_type};base64,{encoded}", detail="original"
        )
    if mime_type.startswith("text/"):
        return TextContent(data.decode("utf-8", errors="replace"))
    raise TypeError(f"unsupported upstream MIME type: {mime_type}")
