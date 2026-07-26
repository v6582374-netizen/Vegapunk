"""Explicit Chinese-to-English Prompt synchronization."""

from __future__ import annotations

from pathlib import Path

from admin_console.prompt_mirror_batch import (
    PromptMirrorTranslator,
    PromptTranslationRequest,
    TranslationError,
)
from admin_console.prompt_translation_instruction import (
    read_prompt_translation_instruction,
)
from vegapunk.prompt_library import PromptEntry, PromptLibrary


class PromptMirrorSyncUnavailableError(RuntimeError):
    pass


class PromptMirrorSyncService:
    def __init__(
        self,
        prompt_library: PromptLibrary,
        instruction_path: Path,
        translator: PromptMirrorTranslator,
    ) -> None:
        self._prompt_library = prompt_library
        self._instruction_path = instruction_path
        self._translator = translator

    def synchronize(
        self,
        prompt_id: str,
        chinese_text: str,
        source_revision: str,
    ) -> PromptEntry:
        instruction = read_prompt_translation_instruction(self._instruction_path)
        if not instruction["configured"]:
            raise PromptMirrorSyncUnavailableError("请先配置 Prompt 翻译指令。")
        availability = self._translator.availability()
        if not availability.available:
            raise PromptMirrorSyncUnavailableError(
                availability.reason or "默认文本模型不可用。"
            )
        entry, _ = self._prompt_library.validate_chinese_mirror_draft(
            prompt_id,
            chinese_text,
            source_revision=source_revision,
        )
        try:
            english_text = self._translator.translate(
                PromptTranslationRequest(
                    instruction=instruction["instruction"],
                    direction="chinese_to_english",
                    prompt_id=entry.id,
                    template_variables=tuple(entry.template_variables),
                    source_body=chinese_text,
                )
            )
        except TranslationError:
            raise
        except Exception as error:
            raise TranslationError(str(error)) from error
        if not isinstance(english_text, str):
            raise TranslationError("模型没有返回有效的英文 Prompt 正文。")
        return self._prompt_library.synchronize_chinese_mirror(
            prompt_id,
            chinese_text,
            english_text,
            source_revision=source_revision,
        )
