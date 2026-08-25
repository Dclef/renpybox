import dataclasses
import json

from module.Config import Config


def test_migrate_legacy_config_preserves_custom_prompt_replacement_semantics():
    raw = {
        "custom_prompt_zh_enable": True,
        "custom_prompt_zh_data": "Translate with the project prompt.",
        "custom_prompt_en_enable": False,
        "custom_prompt_en_data": "English project prompt.",
        "structured_output_enable": False,
        "single_line_translation_enable": True,
    }

    migrated = Config.migrate_dict(raw)

    assert migrated["config_version"] == Config.CURRENT_CONFIG_VERSION
    assert migrated["translation_prompt_mode"] == Config.PROMPT_MODE_CUSTOM
    assert migrated["translation_custom_prompts"] == {
        "ZH": "Translate with the project prompt.",
        "EN": "English project prompt.",
    }
    assert migrated["translation_custom_prompt_enabled_languages"] == ["ZH"]
    assert migrated["translation_style_id"] == Config.STYLE_NONE
    assert migrated["translation_custom_style"] == ""
    assert migrated["translation_output_protocol"] == Config.OUTPUT_PROTOCOL_JSONLINE
    assert migrated["single_line_translation_enable"] is True
    assert migrated["asset_regex_enable"] is False
    assert migrated["asset_prompt_token_budget"] > 0
    assert migrated["asset_prompt_max_items"] > 0
    assert raw.get("config_version") is None


def test_migration_is_idempotent_and_does_not_override_current_fields():
    raw = {
        "custom_prompt_zh_enable": True,
        "custom_prompt_zh_data": "legacy",
        "structured_output_enable": False,
        "translation_prompt_mode": Config.PROMPT_MODE_THINK,
        "translation_custom_prompts": {"ZH": "current"},
        "translation_style_id": Config.STYLE_LITERARY,
        "translation_custom_style": "measured prose",
        "translation_output_protocol": Config.OUTPUT_PROTOCOL_SINGLE_TEXT,
        "asset_regex_enable": True,
        "asset_prompt_token_budget": 512,
        "asset_prompt_max_items": 12,
    }

    migrated = Config.migrate_dict(raw)

    assert Config.migrate_dict(migrated) == migrated
    assert migrated["translation_prompt_mode"] == Config.PROMPT_MODE_THINK
    assert migrated["translation_custom_prompts"] == {"ZH": "current"}
    assert migrated["translation_output_protocol"] == Config.OUTPUT_PROTOCOL_SINGLE_TEXT
    assert migrated["asset_prompt_token_budget"] == 512
    assert migrated["asset_prompt_max_items"] == 12


def test_invalid_or_missing_budgets_use_finite_positive_defaults():
    migrated = Config.migrate_dict(
        {
            "config_version": Config.CURRENT_CONFIG_VERSION,
            "asset_prompt_token_budget": 0,
            "asset_prompt_max_items": True,
        }
    )

    assert (
        migrated["asset_prompt_token_budget"]
        == Config.DEFAULT_ASSET_PROMPT_TOKEN_BUDGET
    )
    assert migrated["asset_prompt_max_items"] == Config.DEFAULT_ASSET_PROMPT_MAX_ITEMS


def test_agent_platform_uses_negative_sentinel_without_hiding_platform_zero():
    assert Config().agent_platform == -1
    assert Config.migrate_dict({})["agent_platform"] == -1
    assert Config.migrate_dict({"agent_platform": 0})["agent_platform"] == 0


def test_default_concurrency_is_sixteen_and_old_zero_is_migrated():
    assert Config().max_workers == 16

    migrated = Config.migrate_dict({"config_version": 1, "max_workers": 0})

    assert migrated["config_version"] == Config.CURRENT_CONFIG_VERSION
    assert migrated["max_workers"] == 16


def test_explicit_auto_concurrency_remains_zero_after_v2():
    migrated = Config.migrate_dict(
        {"config_version": Config.CURRENT_CONFIG_VERSION, "max_workers": 0}
    )

    assert migrated["max_workers"] == 0


def test_invalid_pipeline_enums_are_normalized_at_migration_boundary():
    migrated = Config.migrate_dict(
        {
            "config_version": Config.CURRENT_CONFIG_VERSION,
            "translation_prompt_mode": "invalid",
            "translation_style_id": 123,
            "translation_output_protocol": "plain-json",
        }
    )

    assert migrated["translation_prompt_mode"] == Config.PROMPT_MODE_COMMON
    assert migrated["translation_style_id"] == Config.STYLE_NONE
    assert (
        migrated["translation_output_protocol"]
        == Config.OUTPUT_PROTOCOL_STRUCTURED
    )


def test_legacy_language_switches_remain_independent():
    config = Config()
    migrated = Config.migrate_dict(
        {
            "custom_prompt_zh_enable": False,
            "custom_prompt_en_enable": True,
            "custom_prompt_zh_data": "zh prompt",
            "custom_prompt_en_data": "en prompt",
        }
    )
    for key, value in migrated.items():
        if hasattr(config, key):
            setattr(config, key, value)

    assert config.translation_prompt_mode == Config.PROMPT_MODE_CUSTOM
    assert config.custom_prompt_zh_enable is False
    assert config.custom_prompt_en_enable is True

    config.custom_prompt_zh_enable = True
    config.custom_prompt_en_enable = False

    assert config.custom_prompt_zh_enable is True
    assert config.custom_prompt_en_enable is False


def test_load_migrates_before_assigning_fields(tmp_path):
    path = tmp_path / "legacy-config.json"
    path.write_text(
        json.dumps(
            {
                "custom_prompt_en_enable": True,
                "custom_prompt_en_data": "Use this as the base prompt.",
                "structured_output_enable": False,
            }
        ),
        encoding="utf-8",
    )

    config = Config().load(str(path))

    assert config.config_version == Config.CURRENT_CONFIG_VERSION
    assert config.translation_prompt_mode == Config.PROMPT_MODE_CUSTOM
    assert config.translation_custom_prompts == {
        "EN": "Use this as the base prompt."
    }
    assert config.translation_output_protocol == Config.OUTPUT_PROTOCOL_JSONLINE
    assert config.custom_prompt_en_enable is True
    assert config.custom_prompt_en_data == "Use this as the base prompt."
    assert config.structured_output_enable is False


def test_legacy_properties_write_through_to_current_fields():
    config = Config()

    config.custom_prompt_zh_data = "replacement base prompt"
    config.custom_prompt_zh_enable = True
    config.structured_output_enable = False

    assert config.translation_custom_prompts == {
        "ZH": "replacement base prompt"
    }
    assert config.translation_prompt_mode == Config.PROMPT_MODE_CUSTOM
    assert config.translation_output_protocol == Config.OUTPUT_PROTOCOL_JSONLINE


def test_save_writes_only_current_translation_schema(tmp_path):
    path = tmp_path / "config.json"
    config = Config(
        translation_prompt_mode=Config.PROMPT_MODE_CUSTOM,
        translation_custom_prompts={"ZH": "custom base"},
        translation_output_protocol=Config.OUTPUT_PROTOCOL_JSONLINE,
    )

    config.save(str(path))
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved["config_version"] == Config.CURRENT_CONFIG_VERSION
    assert saved["translation_prompt_mode"] == Config.PROMPT_MODE_CUSTOM
    assert saved["translation_custom_prompts"] == {"ZH": "custom base"}
    assert saved["translation_output_protocol"] == Config.OUTPUT_PROTOCOL_JSONLINE
    assert "custom_prompt_zh_enable" not in saved
    assert "custom_prompt_zh_data" not in saved
    assert "custom_prompt_en_enable" not in saved
    assert "custom_prompt_en_data" not in saved
    assert "structured_output_enable" not in saved
    assert "translation_prompt_mode" in {
        field.name for field in dataclasses.fields(Config)
    }


def test_save_does_not_persist_project_scoped_workbench_view(tmp_path):
    """项目世界观、角色卡和草稿不能随普通设置保存到全局配置。"""
    path = tmp_path / "config.json"
    config = Config(
        renpy_workbench_worldbook_enable=True,
        renpy_workbench_worldbook_data={"genre": "旧项目"},
        renpy_workbench_character_cards_enable=True,
        renpy_workbench_character_cards=[{"name": "旧角色"}],
        renpy_workbench_generated_worldbook_draft={"genre": "旧草稿"},
        renpy_workbench_generated_character_drafts=[{"name": "旧角色草稿"}],
    )

    config.save(str(path))
    saved = json.loads(path.read_text(encoding="utf-8"))

    for key, expected in Config.PROJECT_SCOPED_WORKBENCH_DEFAULTS.items():
        assert saved[key] == expected
