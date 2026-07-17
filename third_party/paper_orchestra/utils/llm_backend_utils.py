"""Provider-neutral helpers retained for upstream PaperOrchestra imports."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from utils.openai_utils import (
    call_openai_models_with_content,
    call_openai_models_with_text_prompt,
    get_openai_image_part_from_path,
    parse_openai_json_results,
)
from utils.pdf_utils import load_paper


def identity_parse(response: str):
    return response


def get_llm_parser(model_name: str, return_json: bool = True) -> Callable:
    del model_name
    return parse_openai_json_results if return_json else identity_parse


def call_llm_with_text_prompt(
    prompt: str,
    model_name: str,
    generation_configs: Optional[Dict[str, Any]] = None,
    check_parsed_response_not_none: bool = True,
    return_json: bool = True,
    result_parsing_func: Optional[Callable] = None,
) -> Dict[str, Any]:
    configs = dict(generation_configs or {})
    parser = result_parsing_func or get_llm_parser(model_name, return_json)
    system_prompt = configs.get("system_instruction")
    return call_openai_models_with_text_prompt(
        prompt=prompt,
        model_name=model_name,
        generation_configs=configs,
        result_parsing_func=parser,
        check_parsed_response_not_none=check_parsed_response_not_none,
        system_prompt=system_prompt,
    )


def call_llm_with_images(
    prompt: str,
    images: list[str],
    model_name: str,
    generation_configs: Optional[Dict[str, Any]] = None,
    check_parsed_response_not_none: bool = True,
    return_json: bool = True,
    result_parsing_func: Optional[Callable] = None,
) -> Dict[str, Any]:
    configs = dict(generation_configs or {})
    parser = result_parsing_func or get_llm_parser(model_name, return_json)
    content = [{"type": "text", "text": prompt}]
    for image_path in images:
        content.extend(get_openai_image_part_from_path(image_path))
    return call_openai_models_with_content(
        content=content,
        model_name=model_name,
        generation_configs=configs,
        result_parsing_func=parser,
        check_parsed_response_not_none=check_parsed_response_not_none,
        system_prompt=configs.get("system_instruction"),
    )


def call_llm_with_pdf(
    pdf_path: str,
    prompt: str,
    model_name: str,
    system_instruction: Optional[str] = None,
    temperature: float = 0.7,
    check_parsed_response_not_none: bool = True,
    return_json: bool = True,
    result_parsing_func: Optional[Callable] = None,
) -> Dict[str, Any]:
    parser = result_parsing_func or get_llm_parser(model_name, return_json)
    paper_text = load_paper(pdf_path, min_size=100)
    return call_openai_models_with_text_prompt(
        prompt=f"Paper Content:\n{paper_text}\n\nTask:\n{prompt}",
        model_name=model_name,
        generation_configs={"temperature": temperature},
        result_parsing_func=parser,
        check_parsed_response_not_none=check_parsed_response_not_none,
        system_prompt=system_instruction,
    )
