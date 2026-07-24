import pytest

from frontend.Setting.TranslationSettingsBinding import OUTPUT_PROTOCOL_VALUES
from frontend.Setting.TranslationSettingsBinding import PROMPT_MODE_VALUES
from frontend.Setting.TranslationSettingsBinding import WRITING_STYLE_VALUES
from frontend.Setting.TranslationSettingsBinding import choice_index
from frontend.Setting.TranslationSettingsBinding import get_custom_prompt
from frontend.Setting.TranslationSettingsBinding import normalize_output_protocol_controls
from frontend.Setting.TranslationSettingsBinding import set_custom_prompt
from frontend.Setting.TranslationSettingsBinding import set_output_protocol
from frontend.Setting.TranslationSettingsBinding import set_prompt_mode
from frontend.Setting.TranslationSettingsBinding import set_single_line_translation
from frontend.Setting.TranslationSettingsBinding import set_writing_style
from module.Config import Config


def test_prompt_mode_and_style_bind_to_independent_config_fields():
    config = Config(
        translation_prompt_mode = Config.PROMPT_MODE_COMMON,
        translation_style_id = Config.STYLE_NONE,
        translation_custom_prompt_enabled_languages = ["EN"],
    )

    set_prompt_mode(config, Config.PROMPT_MODE_CUSTOM)
    set_writing_style(config, Config.STYLE_CLASSICAL)

    assert config.translation_prompt_mode == Config.PROMPT_MODE_CUSTOM
    assert config.translation_style_id == Config.STYLE_CLASSICAL
    assert config.translation_custom_prompt_enabled_languages is None


def test_custom_prompt_editors_store_prompt_languages_independently():
    config = Config(
        translation_prompt_mode = Config.PROMPT_MODE_CUSTOM,
        translation_custom_prompts = {"EN": "old English"},
        translation_custom_prompt_enabled_languages = ["EN"],
    )

    set_custom_prompt(config, "ZH", "中文基础提示")
    set_custom_prompt(config, "EN", "English base prompt")

    assert get_custom_prompt(config, "ZH") == "中文基础提示"
    assert get_custom_prompt(config, "EN") == "English base prompt"
    assert config.translation_custom_prompt_enabled_languages is None


def test_output_protocol_and_single_line_switch_are_bidirectional():
    config = Config(
        translation_output_protocol = Config.OUTPUT_PROTOCOL_STRUCTURED,
        single_line_translation_enable = False,
    )

    set_single_line_translation(config, True)
    assert config.translation_output_protocol == Config.OUTPUT_PROTOCOL_SINGLE_TEXT
    assert config.single_line_translation_enable is True

    set_output_protocol(config, Config.OUTPUT_PROTOCOL_JSONLINE)
    assert config.translation_output_protocol == Config.OUTPUT_PROTOCOL_JSONLINE
    assert config.single_line_translation_enable is False

    set_output_protocol(config, Config.OUTPUT_PROTOCOL_SINGLE_TEXT)
    set_single_line_translation(config, False)
    assert config.translation_output_protocol == Config.OUTPUT_PROTOCOL_STRUCTURED
    assert config.single_line_translation_enable is False


@pytest.mark.parametrize(
    ("protocol", "single_line", "expected_protocol"),
    (
        (Config.OUTPUT_PROTOCOL_JSONLINE, True, Config.OUTPUT_PROTOCOL_SINGLE_TEXT),
        (Config.OUTPUT_PROTOCOL_SINGLE_TEXT, False, Config.OUTPUT_PROTOCOL_SINGLE_TEXT),
        (Config.OUTPUT_PROTOCOL_STRUCTURED, False, Config.OUTPUT_PROTOCOL_STRUCTURED),
    ),
)
def test_output_control_normalization_preserves_any_explicit_single_line_state(
    protocol,
    single_line,
    expected_protocol,
):
    config = Config(
        translation_output_protocol = protocol,
        single_line_translation_enable = single_line,
    )

    normalize_output_protocol_controls(config)

    assert config.translation_output_protocol == expected_protocol
    assert config.single_line_translation_enable == (
        expected_protocol == Config.OUTPUT_PROTOCOL_SINGLE_TEXT
    )


def test_choice_orders_match_the_public_config_contract():
    assert PROMPT_MODE_VALUES == (
        "COMMON",
        "COT",
        "THINK",
        "LOCAL",
        "CUSTOM",
    )
    assert WRITING_STYLE_VALUES == (
        "NONE",
        "LITERARY",
        "CLASSICAL",
        "R18",
        "CUSTOM",
    )
    assert OUTPUT_PROTOCOL_VALUES == (
        "STRUCTURED",
        "JSONLINE",
        "SINGLE_TEXT",
    )
    assert choice_index("jsonline", OUTPUT_PROTOCOL_VALUES) == 1


def test_binding_rejects_unknown_enum_values():
    config = Config()

    with pytest.raises(ValueError, match = "prompt mode"):
        set_prompt_mode(config, "UNKNOWN")
    with pytest.raises(ValueError, match = "writing style"):
        set_writing_style(config, "UNKNOWN")
    with pytest.raises(ValueError, match = "output protocol"):
        set_output_protocol(config, "UNKNOWN")
