"""Explicit conversion of a Discovery Preparation into editable input."""

from __future__ import annotations

import asyncio
import copy
import io
import json
import zipfile
from dataclasses import dataclass
from typing import Protocol

from admin_console.configuration_files import source_configuration_transaction
from admin_console.model_catalog import load_catalog
from admin_console.provider_connections import (
    InvalidProviderConnectionError,
    ProviderConnectionNotReadyError,
    ProviderConnectionService,
    SecretStoreUnavailableError,
    UnknownProviderError,
)
from vegapunk.mas.models.unified_runtime import ModelCatalog, UnifiedModelRuntime
from vegapunk.mas.models.runtime import ReasoningConfig


class DiscoveryConversionError(RuntimeError):
    pass


class DiscoveryConfigurationError(DiscoveryConversionError):
    """The current Prompt/Model settings cannot perform conversion."""


class DiscoverySourceContentError(ValueError):
    pass


@dataclass(frozen=True)
class DiscoverySourceMaterial:
    name: str
    kind: str
    content: str


@dataclass(frozen=True)
class DiscoveryInputConversionRequest:
    instruction: str
    research_text: str
    sources: tuple[DiscoverySourceMaterial, ...]


@dataclass(frozen=True)
class ConversionResult:
    formatted_input: str
    model_id: str


class DiscoveryInputConverter(Protocol):
    def convert(self, request: DiscoveryInputConversionRequest) -> ConversionResult: ...


class DefaultDiscoveryInputConverter:
    """Convert through the configured default text model without persisting a key."""

    def __init__(
        self,
        catalog_path,
        provider_connections: ProviderConnectionService,
    ) -> None:
        self._catalog_path = catalog_path
        self._provider_connections = provider_connections

    def convert(self, request: DiscoveryInputConversionRequest) -> ConversionResult:
        try:
            with source_configuration_transaction():
                runtime_catalog = copy.deepcopy(load_catalog(self._catalog_path))
                catalog = ModelCatalog.from_mapping(runtime_catalog)
                model = catalog.resolve_model(
                    catalog.active_text_model,
                    capability="text",
                )
        except Exception as error:
            raise DiscoveryConfigurationError(
                "系统设置中的默认文本模型不可用，无法执行 Discovery Input Conversion。"
            ) from error

        try:
            connection = self._provider_connections.resolve_for_execution(model.provider)
            provider = runtime_catalog["providers"][model.provider]
            provider["base_url"] = connection.base_url
            provider["api_key"] = connection.credential
            reasoning_values = provider.get("reasoning")
            if reasoning_values is not None and not isinstance(reasoning_values, dict):
                raise ValueError("default text model reasoning settings must be a mapping")
            reasoning = ReasoningConfig(**reasoning_values) if reasoning_values else None
            temperature = provider.get("temperature")
            max_output_tokens = provider.get("max_output_tokens")
            runtime = UnifiedModelRuntime(
                ModelCatalog.from_mapping(runtime_catalog),
                adapter_factory=UnifiedModelRuntime._default_adapter_factory,
            )
        except (
            InvalidProviderConnectionError,
            ProviderConnectionNotReadyError,
            SecretStoreUnavailableError,
            UnknownProviderError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise DiscoveryConfigurationError(
                "默认文本模型的 Provider Connection 不可用，请先检查系统设置。"
            ) from error

        try:
            formatted_input = asyncio.run(
                runtime.generate_text(
                    json.dumps(
                        {
                            "operation": "format_discovery_input",
                            "research_text": request.research_text,
                            "sources": [
                                {
                                    "name": source.name,
                                    "kind": source.kind,
                                    "content": source.content,
                                }
                                for source in request.sources
                            ],
                        },
                        ensure_ascii=False,
                    ),
                    system_prompt=request.instruction,
                    model_id=model.canonical_id,
                    reasoning=reasoning,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                )
            )
        except Exception as error:
            raise DiscoveryConversionError(
                "默认文本模型未能生成 Formatted Discovery Input。"
            ) from error
        if not formatted_input.strip():
            raise DiscoveryConversionError("默认文本模型返回了空的 Formatted Discovery Input。")
        return ConversionResult(formatted_input=formatted_input, model_id=model.canonical_id)


def source_materials(source_files: list[dict]) -> tuple[DiscoverySourceMaterial, ...]:
    return tuple(
        DiscoverySourceMaterial(
            name=source["name"],
            kind=source["kind"],
            content=_source_text(source),
        )
        for source in source_files
    )


def _source_text(source: dict) -> str:
    extension = source["extension"]
    content = source["content"]
    try:
        if extension in {".txt", ".md", ".csv"}:
            return content.decode("utf-8")
        if extension == ".pdf":
            from pypdf import PdfReader

            return "\n\n".join(
                page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages
            )
        if extension == ".docx":
            from docx import Document

            return "\n".join(
                paragraph.text for paragraph in Document(io.BytesIO(content)).paragraphs
            )
        if extension == ".zip":
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = []
                for member in archive.infolist():
                    member_path = member.filename.replace("\\", "/")
                    parts = [part for part in member_path.split("/") if part]
                    if member_path.startswith("/") or ".." in parts:
                        raise DiscoverySourceContentError(
                            f"unable to read source: {source['name']} (zip entry escapes package)"
                        )
                    if member.is_dir():
                        continue
                    names.append(member.filename)
            return "Baseline code package files:\n" + "\n".join(names)
    except Exception as error:
        raise DiscoverySourceContentError(f"unable to read source: {source['name']}") from error
    raise DiscoverySourceContentError(f"unsupported source type: {source['name']}")
