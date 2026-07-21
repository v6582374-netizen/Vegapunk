# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
import json
from typing import Dict, Any

from utils import genai_types as types
import time
import os
import base64

from utils.vegapunk_adapter import (
    call_responses_with_contents,
    generate_image_base64,
)

# Kept only for source-level import compatibility with upstream helpers.
genai_client = None


def parse_gemini_json_results(response: str):
    if not response or not isinstance(response, str):
        return None

    json_pattern = r"```json(.*?)```"
    matches = re.findall(json_pattern, response, re.DOTALL)

    if not matches:
        json_pattern = r"(\{.*\}|\[.*\])"
        matches = re.findall(json_pattern, response, re.DOTALL)

    for json_string in matches:
        json_string = json_string.strip()
        try:
            parsed_json = json.loads(json_string)
            return parsed_json
        except json.JSONDecodeError:
            try:
                json_string_clean = re.sub(r"[\x00-\x1F\x7F]", "", json_string)
                json_string_clean = re.sub(r",\s*([\]}])", r"\1", json_string_clean)
                json_string_clean = re.sub(
                    r'\\(?![\\"/bfnrtu])', r"\\\\", json_string_clean
                )

                parsed_json = json.loads(json_string_clean)
                return parsed_json
            except json.JSONDecodeError:
                continue

    try:
        start_idx = response.find("{")
        end_idx = response.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_string = response[start_idx : end_idx + 1]
            json_string_clean = re.sub(r"[\x00-\x1F\x7F]", "", json_string)
            json_string_clean = re.sub(r",\s*([\]}])", r"\1", json_string_clean)
            json_string_clean = re.sub(
                r'\\(?![\\"/bfnrtu])', r"\\\\", json_string_clean
            )
            return json.loads(json_string_clean)
    except Exception:
        pass

    return None  # No valid JSON found


def parse_gemini_latex_results(response: str):
    match = re.search(r"```latex\s*(.*?)\s*```", response.strip(), re.DOTALL)
    if match:
        latex_string = match.group(1)
    else:
        latex_string = response
    return latex_string


def parse_gemini_json_latex_response(response_text: str) -> Dict[str, Any]:
    """
    Extracts the JSON worklog and the LaTeX code from the LLM response.
    Expected format:
      ... arbitrary text ...
      ```json
      { ... }
      ```
      ... arbitrary text ...
      ```latex
      ...
      ```
    """
    result = {"json": None, "latex": None}

    json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
    if json_match:
        try:
            result["json"] = json.loads(json_match.group(1))
        except json.JSONDecodeError:
            print(" >> Error: Failed to parse JSON worklog from response.")
            result["json"] = {"error": "Invalid JSON format returned"}

    latex_match = re.search(r"```latex\s*(.*?)\s*```", response_text, re.DOTALL)
    if latex_match:
        result["latex"] = latex_match.group(1)
    else:
        print(" >> Warning: No ```latex``` block found.")

    return json.dumps(result)


def call_gemini_with_contents(
    contents: types.Content,
    model_name: str,
    max_retries: int = 5,
    base_interval_sec: int = 5,
    result_parsing_func: callable = parse_gemini_json_results,
    generation_configs: dict = {},
    check_parsed_response_not_none: bool = True,
):
    """Provider-neutral compatibility wrapper over the Unified Runtime."""
    del max_retries, base_interval_sec
    raw_response = call_responses_with_contents(
        contents=contents,
        model_name=model_name,
        generation_configs=generation_configs,
    )
    parsed_response = result_parsing_func(raw_response)
    if check_parsed_response_not_none and parsed_response is None:
        raise ValueError(f"Parsed response is None, raw response: {raw_response}")
    return {"raw_response": raw_response, "parsed_response": parsed_response}


def call_gemini_with_text_prompt(
    prompt: str,
    model_name: str,
    result_parsing_func: callable = parse_gemini_json_results,
    generation_configs: dict = {},
    check_parsed_response_not_none: bool = True,
    max_retries: int = 5,
    base_interval_sec: int = 5,
):
    contents = [types.Part(text=prompt)]
    return call_gemini_with_contents(
        contents=contents,
        model_name=model_name,
        result_parsing_func=result_parsing_func,
        generation_configs=generation_configs,
        check_parsed_response_not_none=check_parsed_response_not_none,
        max_retries=max_retries,
        base_interval_sec=base_interval_sec,
    )


def call_gemini_with_images(
    prompt: str,
    images: list[str],
    model_name: str,
    result_parsing_func: callable = parse_gemini_json_results,
    generation_configs: dict = {},
    check_parsed_response_not_none: bool = True,
    max_retries: int = 5,
    base_interval_sec: int = 5,
):
    llm_contents = [
        types.Part.from_text(text=prompt),
    ]
    for image_path in images:
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        llm_contents.append(
            types.Part.from_bytes(data=img_bytes, mime_type="image/png")
        )

    response_dict = call_gemini_with_contents(
        contents=llm_contents,
        model_name=model_name,
        generation_configs=generation_configs,
        result_parsing_func=result_parsing_func,
        check_parsed_response_not_none=check_parsed_response_not_none,
        max_retries=max_retries,
        base_interval_sec=base_interval_sec,
    )
    return response_dict


def generate_image_with_gemini(
    model_name: str,
    prompt: str,
    aspect_ratio: str = "16:9",
    generation_configs: dict = None,
    max_retries: int = 5,
    base_interval_sec: int = 5,
    save_path: str = None,
) -> str:
    """
    Directly calls Gemini for image generation and returns base64.
    """
    if generation_configs is None:
        generation_configs = {}

    del generation_configs, max_retries, base_interval_sec
    img_base64 = generate_image_base64(
        model_name=model_name,
        prompt=prompt,
        aspect_ratio=aspect_ratio,
    )
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "wb") as fh:
            fh.write(base64.b64decode(img_base64))
    return img_base64
