"""Explicit, observable batch generation for Chinese Prompt Mirrors."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from admin_console.configuration_files import source_configuration_transaction
from admin_console.model_catalog import load_catalog
from admin_console.prompt_translation_instruction import (
    read_prompt_translation_instruction,
)
from admin_console.provider_connections import ProviderConnectionService
from vegapunk.mas.models.unified_runtime import ModelCatalog, UnifiedModelRuntime
from vegapunk.prompt_library import (
    InvalidPromptError,
    PromptLibrary,
    PromptSourceChangedError,
)


BatchItemState = Literal["pending", "success", "failure", "skipped"]
BatchState = Literal["running", "completed"]


class BatchUnavailableError(RuntimeError):
    pass


class UnknownBatchError(KeyError):
    pass


class TranslationError(RuntimeError):
    pass


@dataclass(frozen=True)
class BatchAvailability:
    available: bool
    reason: str | None
    model_id: str | None

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "reason": self.reason,
            "model_id": self.model_id,
        }


@dataclass(frozen=True)
class PromptTranslationRequest:
    instruction: str
    direction: Literal["english_to_chinese", "chinese_to_english"]
    prompt_id: str
    template_variables: tuple[str, ...]
    source_body: str


class PromptMirrorTranslator(Protocol):
    def availability(self) -> BatchAvailability: ...

    def translate(self, request: PromptTranslationRequest) -> str: ...


class DefaultPromptMirrorTranslator:
    """Translate through the configured default text model without persisting a key."""

    def __init__(
        self,
        catalog_path: Path,
        provider_connections: ProviderConnectionService,
    ) -> None:
        self._catalog_path = catalog_path
        self._provider_connections = provider_connections

    def availability(self) -> BatchAvailability:
        try:
            catalog = ModelCatalog.from_mapping(load_catalog(self._catalog_path))
            model = catalog.resolve_model(catalog.active_text_model, capability="text")
        except Exception:
            return BatchAvailability(False, "默认文本模型不可用。", None)
        if "json" not in model.capabilities:
            return BatchAvailability(
                False,
                "默认文本模型不支持结构化翻译输出。",
                model.canonical_id,
            )
        if model.provider == "local":
            return BatchAvailability(
                False,
                "默认文本模型不支持远程结构化翻译。",
                model.canonical_id,
            )
        try:
            connection = self._provider_connections.get(model.provider)
        except Exception:
            return BatchAvailability(False, "默认文本模型不可用。", model.canonical_id)
        if connection["verification_status"] != "valid":
            return BatchAvailability(
                False,
                "默认文本模型尚未验证或无法连接。",
                model.canonical_id,
            )
        return BatchAvailability(True, None, model.canonical_id)

    def translate(self, request: PromptTranslationRequest) -> str:
        try:
            with source_configuration_transaction():
                runtime_catalog = copy.deepcopy(load_catalog(self._catalog_path))
                catalog = ModelCatalog.from_mapping(runtime_catalog)
                model = catalog.resolve_model(
                    catalog.active_text_model,
                    capability="text",
                )
            if "json" not in model.capabilities:
                raise TranslationError("默认文本模型不支持结构化翻译输出。")
            if model.provider == "local":
                raise TranslationError("默认文本模型不支持远程结构化翻译。")
            connection = self._provider_connections.resolve_for_execution(model.provider)
            provider = runtime_catalog["providers"][model.provider]
            provider["base_url"] = connection.base_url
            provider["api_key"] = connection.credential
            runtime = UnifiedModelRuntime(
                ModelCatalog.from_mapping(runtime_catalog),
                adapter_factory=UnifiedModelRuntime._default_adapter_factory,
            )
            response = asyncio.run(
                runtime.generate_json(
                    json.dumps(
                        {
                            "operation": "generate_prompt_mirror",
                            "direction": request.direction,
                            "prompt_id": request.prompt_id,
                            "template_variables": list(request.template_variables),
                            "source_body": request.source_body,
                        },
                        ensure_ascii=False,
                    ),
                    system_prompt=request.instruction,
                    model_id=model.canonical_id,
                    schema={
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["target_body"],
                        "properties": {"target_body": {"type": "string"}},
                    },
                )
            )
        except TranslationError:
            raise
        except Exception as error:
            raise TranslationError("默认文本模型未能生成结构化 Prompt 译文。") from error
        if set(response) != {"target_body"} or not isinstance(
            response["target_body"], str
        ):
            raise TranslationError("模型没有返回唯一且有效的目标 Prompt 正文。")
        return response["target_body"]


@dataclass
class BatchItem:
    prompt_id: str
    name: str
    state: BatchItemState
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "prompt_id": self.prompt_id,
            "name": self.name,
            "state": self.state,
            "error": self.error,
        }


@dataclass
class PromptMirrorBatch:
    id: str
    state: BatchState
    items: list[BatchItem]

    def to_dict(self) -> dict:
        counts = {
            state: sum(item.state == state for item in self.items)
            for state in ("pending", "success", "failure", "skipped")
        }
        return {
            "id": self.id,
            "state": self.state,
            "items": [item.to_dict() for item in self.items],
            "progress": {"total": len(self.items), **counts},
        }


class PromptMirrorBatchService:
    def __init__(
        self,
        prompt_library: PromptLibrary,
        instruction_path: Path,
        translator: PromptMirrorTranslator,
    ) -> None:
        self._prompt_library = prompt_library
        self._instruction_path = instruction_path
        self._translator = translator
        self._lock = threading.RLock()
        self._batches: dict[str, PromptMirrorBatch] = {}
        self._active_batch_id: str | None = None

    def availability(self) -> BatchAvailability:
        instruction = read_prompt_translation_instruction(self._instruction_path)
        if not instruction["configured"]:
            return BatchAvailability(False, "请先配置 Prompt 翻译指令。", None)
        return self._translator.availability()

    def start(self) -> dict:
        return self._create_batch(retry_batch_id=None)

    def retry(self, batch_id: str) -> dict:
        return self._create_batch(retry_batch_id=batch_id)

    def get(self, batch_id: str) -> dict:
        with self._lock:
            try:
                return self._batches[batch_id].to_dict()
            except KeyError as error:
                raise UnknownBatchError(batch_id) from error

    def _create_batch(self, retry_batch_id: str | None) -> dict:
        availability = self.availability()
        if not availability.available:
            raise BatchUnavailableError(availability.reason or "翻译操作不可用。")
        with self._lock:
            if self._active_batch_id is not None:
                raise BatchUnavailableError("已有中文镜像批处理正在运行。")
            retry_ids = self._retry_ids(retry_batch_id)
            batch = self._new_batch(retry_ids)
            self._batches[batch.id] = batch
            if any(item.state == "pending" for item in batch.items):
                self._active_batch_id = batch.id
                threading.Thread(
                    target=self._run,
                    args=(batch.id,),
                    name=f"prompt-mirror-batch-{batch.id}",
                    daemon=True,
                ).start()
            else:
                batch.state = "completed"
            return batch.to_dict()

    def _retry_ids(self, batch_id: str | None) -> set[str] | None:
        if batch_id is None:
            return None
        try:
            previous = self._batches[batch_id]
        except KeyError as error:
            raise UnknownBatchError(batch_id) from error
        return {item.prompt_id for item in previous.items if item.state == "failure"}

    def _new_batch(self, retry_ids: set[str] | None) -> PromptMirrorBatch:
        items: list[BatchItem] = []
        for entry in self._prompt_library.list():
            mirror_state = self._prompt_library.describe(entry.id)["chinese_mirror"][
                "state"
            ]
            selected = (
                entry.id in retry_ids
                if retry_ids is not None
                else mirror_state in {"missing", "stale"}
            )
            state: BatchItemState = "pending" if selected else "skipped"
            if selected and mirror_state == "ready":
                state = "skipped"
            if retry_ids is not None and entry.id not in retry_ids:
                continue
            items.append(BatchItem(entry.id, entry.name, state))
        return PromptMirrorBatch(uuid.uuid4().hex, "running", items)

    def _run(self, batch_id: str) -> None:
        try:
            instruction = read_prompt_translation_instruction(self._instruction_path)[
                "instruction"
            ]
            for item in self._pending_items(batch_id):
                self._translate_item(batch_id, item.prompt_id, instruction)
        finally:
            with self._lock:
                batch = self._batches[batch_id]
                batch.state = "completed"
                self._active_batch_id = None

    def _pending_items(self, batch_id: str) -> list[BatchItem]:
        with self._lock:
            return [
                item
                for item in self._batches[batch_id].items
                if item.state == "pending"
            ]

    def _translate_item(self, batch_id: str, prompt_id: str, instruction: str) -> None:
        try:
            entry = self._prompt_library.get_entry(prompt_id)
            source_body = self._prompt_library.get(prompt_id)
            target_body = self._translator.translate(
                PromptTranslationRequest(
                    instruction=instruction,
                    direction="english_to_chinese",
                    prompt_id=entry.id,
                    template_variables=tuple(entry.template_variables),
                    source_body=source_body,
                )
            )
            self._prompt_library.save_chinese_mirror(
                prompt_id,
                target_body,
                source_revision=hashlib.sha256(source_body.encode()).hexdigest(),
            )
        except PromptSourceChangedError:
            self._set_item(
                batch_id,
                prompt_id,
                "failure",
                "英文 Prompt 在翻译期间发生变化，请重新生成中文镜像。",
            )
        except InvalidPromptError as error:
            self._set_item(batch_id, prompt_id, "failure", str(error))
        except Exception as error:
            self._set_item(batch_id, prompt_id, "failure", str(error))
        else:
            self._set_item(batch_id, prompt_id, "success", None)

    def _set_item(
        self,
        batch_id: str,
        prompt_id: str,
        state: BatchItemState,
        error: str | None,
    ) -> None:
        with self._lock:
            item = next(
                item
                for item in self._batches[batch_id].items
                if item.prompt_id == prompt_id
            )
            item.state = state
            item.error = error
