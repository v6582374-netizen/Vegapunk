from admin_console.app import (
    DEFAULT_DISCOVERY_INPUT_CONVERSION_PROMPT_PATH,
    DEFAULT_PROMPT_TRANSLATION_INSTRUCTION_PATH,
)
from admin_console.discovery_input_conversion_prompt import (
    read_discovery_input_conversion_prompt,
)
from admin_console.prompt_translation_instruction import (
    read_prompt_translation_instruction,
)


def test_researcher_tool_instructions_are_configured_outside_the_prompt_library() -> None:
    translation = read_prompt_translation_instruction(
        DEFAULT_PROMPT_TRANSLATION_INSTRUCTION_PATH
    )
    conversion = read_discovery_input_conversion_prompt(
        DEFAULT_DISCOVERY_INPUT_CONVERSION_PROMPT_PATH
    )

    assert translation["configured"]
    assert "target_body" in translation["instruction"]
    assert conversion["configured"]
    assert "Formatted Discovery Input" in conversion["instruction"]
