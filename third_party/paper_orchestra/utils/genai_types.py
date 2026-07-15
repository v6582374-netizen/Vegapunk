"""Small local subset of google.genai.types used by upstream prompts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InlineData:
    data: bytes
    mime_type: str


@dataclass(frozen=True)
class Part:
    text: str | None = None
    inline_data: InlineData | None = None

    @classmethod
    def from_text(cls, *, text: str) -> "Part":
        return cls(text=text)

    @classmethod
    def from_bytes(cls, *, data: bytes, mime_type: str) -> "Part":
        return cls(inline_data=InlineData(data=data, mime_type=mime_type))


@dataclass(frozen=True)
class GoogleSearch:
    pass


@dataclass(frozen=True)
class Tool:
    google_search: GoogleSearch | None = None


Content = Any
