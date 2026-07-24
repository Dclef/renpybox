from typing import Any

from base.BaseLanguage import BaseLanguage
from module.Config import Config


PROMPT_MODE_VALUES: tuple[str, ...] = (
    Config.PROMPT_MODE_COMMON,
    Config.PROMPT_MODE_COT,
    Config.PROMPT_MODE_THINK,
    Config.PROMPT_MODE_LOCAL,
    Config.PROMPT_MODE_CUSTOM,
)

WRITING_STYLE_VALUES: tuple[str, ...] = (
    Config.STYLE_NONE,
    Config.STYLE_LITERARY,
    Config.STYLE_CLASSICAL,
    Config.STYLE_R18,
    Config.STYLE_CUSTOM,
)

OUTPUT_PROTOCOL_VALUES: tuple[str, ...] = (
    Config.OUTPUT_PROTOCOL_STRUCTURED,
    Config.OUTPUT_PROTOCOL_JSONLINE,
    Config.OUTPUT_PROTOCOL_SINGLE_TEXT,
)

CUSTOM_PROMPT_LANGUAGES: tuple[str, ...] = (
    BaseLanguage.Enum.ZH.value,
    BaseLanguage.Enum.EN.value,
)


def choice_index(value: object, choices: tuple[str, ...]) -> int:
    normalized = str(value).strip().upper() if isinstance(value, str) else ""
    try:
        return choices.index(normalized)
    except ValueError:
        return 0


def _require_choice(value: object, choices: tuple[str, ...], field_name: str) -> str:
    normalized = str(value).strip().upper() if isinstance(value, str) else ""
    if normalized not in choices:
        raise ValueError(f"Unsupported {field_name}: {value!r}")
    return normalized


def set_prompt_mode(config: Any, mode: str) -> None:
    normalized = _require_choice(mode, PROMPT_MODE_VALUES, "prompt mode")
    previous = getattr(config, "translation_prompt_mode", Config.PROMPT_MODE_COMMON)
    config.translation_prompt_mode = normalized

    # A fresh CUSTOM selection is global. A legacy per-language scope remains
    # untouched until the user explicitly switches into CUSTOM.
    if normalized == Config.PROMPT_MODE_CUSTOM and previous != normalized:
        config.translation_custom_prompt_enabled_languages = None


def get_custom_prompt(config: Any, language: BaseLanguage.Enum | str) -> str:
    language_value = language.value if isinstance(language, BaseLanguage.Enum) else str(language)
    normalized = _require_choice(
        language_value,
        CUSTOM_PROMPT_LANGUAGES,
        "custom prompt language",
    )
    prompts = getattr(config, "translation_custom_prompts", {})
    if not isinstance(prompts, dict):
        return ""
    value = prompts.get(normalized, "")
    return value if isinstance(value, str) else ""


def set_custom_prompt(
    config: Any,
    language: BaseLanguage.Enum | str,
    text: str,
) -> None:
    language_value = language.value if isinstance(language, BaseLanguage.Enum) else str(language)
    normalized = _require_choice(
        language_value,
        CUSTOM_PROMPT_LANGUAGES,
        "custom prompt language",
    )
    prompts = getattr(config, "translation_custom_prompts", {})
    updated = dict(prompts) if isinstance(prompts, dict) else {}
    updated[normalized] = str(text)
    config.translation_custom_prompts = updated
    if (
        getattr(config, "translation_prompt_mode", None)
        == Config.PROMPT_MODE_CUSTOM
    ):
        config.translation_custom_prompt_enabled_languages = None


def set_writing_style(config: Any, style_id: str) -> None:
    config.translation_style_id = _require_choice(
        style_id,
        WRITING_STYLE_VALUES,
        "writing style",
    )


def set_output_protocol(config: Any, protocol: str) -> None:
    normalized = _require_choice(protocol, OUTPUT_PROTOCOL_VALUES, "output protocol")
    config.translation_output_protocol = normalized
    config.single_line_translation_enable = (
        normalized == Config.OUTPUT_PROTOCOL_SINGLE_TEXT
    )


def set_single_line_translation(config: Any, enabled: bool) -> None:
    config.single_line_translation_enable = bool(enabled)
    if enabled:
        config.translation_output_protocol = Config.OUTPUT_PROTOCOL_SINGLE_TEXT
    elif (
        getattr(config, "translation_output_protocol", None)
        == Config.OUTPUT_PROTOCOL_SINGLE_TEXT
    ):
        config.translation_output_protocol = Config.OUTPUT_PROTOCOL_STRUCTURED


def normalize_output_protocol_controls(config: Any) -> None:
    """Preserve legacy single-line behavior while enforcing one valid UI state."""
    protocol = getattr(
        config,
        "translation_output_protocol",
        Config.OUTPUT_PROTOCOL_STRUCTURED,
    )
    protocol = _require_choice(protocol, OUTPUT_PROTOCOL_VALUES, "output protocol")
    if getattr(config, "single_line_translation_enable", False) is True:
        protocol = Config.OUTPUT_PROTOCOL_SINGLE_TEXT

    set_output_protocol(config, protocol)
