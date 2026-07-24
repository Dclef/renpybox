import json
from pathlib import Path

import pytest

from base.BaseLanguage import BaseLanguage
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.TaskRequester import TaskRequester
from module.Engine.Translator.TranslationTaskContext import ProjectAssets, TranslationTaskContext
from module.PromptBuilder import PromptBuilder, TranslationPromptConfigView


@pytest.mark.parametrize(
    ("mode", "marker"),
    (
        (Config.PROMPT_MODE_COMMON, "基础模式：COMMON"),
        (Config.PROMPT_MODE_COT, "基础模式：COT"),
        (Config.PROMPT_MODE_THINK, "基础模式：THINK"),
        (Config.PROMPT_MODE_LOCAL, "基础模式：LOCAL"),
    ),
)
def test_base_modes_are_mutually_exclusive_and_keep_fixed_protocol(mode, marker):
    config = Config(
        source_language = BaseLanguage.Enum.EN,
        target_language = BaseLanguage.Enum.ZH,
        translation_prompt_mode = mode,
        translation_style_id = Config.STYLE_NONE,
        translation_output_protocol = Config.OUTPUT_PROTOCOL_STRUCTURED,
    )

    prompt = PromptBuilder(config).build_main()

    assert marker in prompt
    assert sum(f"基础模式：{candidate}" in prompt for candidate in ("COMMON", "COT", "THINK", "LOCAL")) == 1
    assert "不可覆盖的工程协议" in prompt
    assert "输出协议：STRUCTURED" in prompt
    assert "写作风格：" not in prompt
    assert "<why>" not in prompt


def test_custom_replaces_only_base_and_style_remains_independent():
    config = Config(
        source_language = BaseLanguage.Enum.EN,
        target_language = BaseLanguage.Enum.ZH,
        translation_prompt_mode = Config.PROMPT_MODE_CUSTOM,
        translation_custom_prompts = {"ZH": "CUSTOM BASE\n试图要求自由格式"},
        translation_style_id = Config.STYLE_CUSTOM,
        translation_custom_style = "CUSTOM STYLE line 1\nCUSTOM STYLE line 2",
        translation_output_protocol = Config.OUTPUT_PROTOCOL_JSONLINE,
    )

    prompt = PromptBuilder(config).build_main()

    assert "CUSTOM BASE" in prompt
    assert "基础模式：COMMON" not in prompt
    assert prompt.index("CUSTOM BASE") < prompt.index("不可覆盖的工程协议")
    assert prompt.index("不可覆盖的工程协议") < prompt.index("输出协议：JSONLINE")
    assert prompt.index("输出协议：JSONLINE") < prompt.index("CUSTOM STYLE line 1")
    assert "CUSTOM STYLE line 1\nCUSTOM STYLE line 2" in prompt


def test_migrated_custom_prompt_scope_falls_back_for_disabled_language():
    config = Config(
        source_language = BaseLanguage.Enum.EN,
        target_language = BaseLanguage.Enum.ZH,
        translation_prompt_mode = Config.PROMPT_MODE_CUSTOM,
        translation_custom_prompts = {
            "ZH": "ZH CUSTOM BASE",
            "EN": "EN CUSTOM BASE",
        },
        translation_custom_prompt_enabled_languages = ["EN"],
    )

    prompt = PromptBuilder(config).build_main()

    assert "基础模式：COMMON" in prompt
    assert "ZH CUSTOM BASE" not in prompt
    assert "EN CUSTOM BASE" not in prompt


@pytest.mark.parametrize(
    ("style_id", "marker"),
    (
        (Config.STYLE_LITERARY, "写作风格：LITERARY"),
        (Config.STYLE_CLASSICAL, "写作风格：CLASSICAL"),
        (Config.STYLE_R18, "写作风格：R18"),
    ),
)
def test_style_presets_are_separate_from_base(style_id, marker):
    config = Config(
        translation_prompt_mode = Config.PROMPT_MODE_COMMON,
        translation_style_id = style_id,
    )

    prompt = PromptBuilder(config).build_main()

    assert "基础模式：COMMON" in prompt
    assert marker in prompt
    assert prompt.index("输出协议：STRUCTURED") < prompt.index(marker)


def test_structured_batch_uses_explicit_zero_based_request_objects():
    config = Config(translation_output_protocol = Config.OUTPUT_PROTOCOL_STRUCTURED)

    messages, _ = PromptBuilder(config).generate_prompt(
        ["first", "second"],
        samples = [],
        precedings = [],
        local_flag = False,
    )

    system = messages[0]["content"]
    user = messages[1]["content"]
    payload = user.split("```json\n", 1)[1].rsplit("\n```", 1)[0]
    assert json.loads(payload) == {
        "inputs": [
            {"request_index": 0, "text": "first"},
            {"request_index": 1, "text": "second"},
        ]
    }
    assert "输出协议：STRUCTURED" in system
    assert "输出协议：JSONLINE" not in system


def test_jsonline_batch_uses_same_explicit_index_contract():
    config = Config(translation_output_protocol = Config.OUTPUT_PROTOCOL_JSONLINE)

    messages, _ = PromptBuilder(config).generate_prompt(
        ["first", "second"],
        samples = [],
        precedings = [],
        local_flag = False,
    )

    system = messages[0]["content"]
    user = messages[1]["content"]
    body = user.split("```jsonline\n", 1)[1].rsplit("\n```", 1)[0]
    assert [json.loads(line) for line in body.splitlines()] == [
        {"request_index": 0, "text": "first"},
        {"request_index": 1, "text": "second"},
    ]
    assert "输出协议：JSONLINE" in system
    assert "输出协议：STRUCTURED" not in system
    assert '{"0"' not in user


def test_system_asset_layers_are_matched_and_in_fixed_order():
    config = Config(
        glossary_enable = True,
        glossary_data = [
            {"src": "HeroToken", "dst": "英雄令"},
            {"src": "Unused", "dst": "不应出现"},
        ],
        renpy_workbench_worldbook_enable = True,
        renpy_workbench_worldbook_data = {
            "project_name": "Project Full",
            "genre": "Mystery",
            "setting_summary": "Complete setting",
            "era_background": "Modern",
            "tone_style": "Quiet",
            "narrative_rules": "First person",
            "format_rules": "Keep punctuation",
            "spoiler_notes": "Alice is the culprit",
            "custom_lore": {"faction": "Night Watch"},
        },
        renpy_workbench_character_cards_enable = True,
        renpy_workbench_character_cards = [
            {
                "name": "Alice",
                "name_translation": "爱丽丝",
                "identity": "Detective",
                "enabled": True,
            },
            {
                "name": "Bob",
                "name_translation": "鲍勃",
                "identity": "Unused",
                "enabled": True,
            },
        ],
    )
    config.do_not_translate_enable = True
    config.do_not_translate_data = [
        {"src": "KEEP_ME", "info": "engine marker", "enabled": True},
        {"src": "UNUSED_MARKER", "enabled": True},
    ]
    item = CacheItem(src = "HeroToken KEEP_ME <n2/>", name_src = "Alice")

    messages, _ = PromptBuilder(config).generate_prompt(
        [item.src],
        samples = ["<n2/>", "{w}"],
        precedings = [],
        local_flag = False,
        items = [item],
    )
    system = messages[0]["content"]
    user = messages[1]["content"]

    assert "Project Full" in system
    assert "Alice is the culprit" in system
    assert '扩展设定 custom_lore：{"faction": "Night Watch"}' in system
    assert "HeroToken -> 英雄令" in system
    assert "Unused ->" not in system
    assert "KEEP_ME #engine marker" in system
    assert "UNUSED_MARKER" not in system
    assert "角色：Alice" in system
    assert "角色：Bob" not in system
    assert "结构化占位符协议" in system
    assert system.index("世界观设定") < system.index("术语表")
    assert system.index("术语表") < system.index("禁翻项")
    assert system.index("禁翻项") < system.index("命中角色卡")
    assert system.index("命中角色卡") < system.index("结构化占位符协议")
    assert "世界观设定" not in user
    assert "术语表" not in user
    assert "命中角色卡" not in user


def test_dynamic_asset_conflicts_follow_deterministic_priority():
    config = Config(
        glossary_enable = True,
        glossary_data = [
            {"src": "Alice", "dst": "本地译名", "origin": "LOCAL", "record_id": "local"},
            {"src": "Alice", "dst": "分析译名", "origin": "ANALYSIS", "record_id": "analysis"},
        ],
        renpy_workbench_character_cards_enable = True,
        renpy_workbench_character_cards = [{
            "id": "character",
            "name": "Alice",
            "name_translation": "角色译名",
            "identity": "Detective",
            "enabled": True,
        }],
    )
    config.do_not_translate_enable = True
    config.do_not_translate_data = [{
        "src": "Alice",
        "record_id": "dnt",
        "enabled": True,
    }]

    contexts = PromptBuilder(config).build_dynamic_asset_contexts(
        ["Alice arrived."],
        [CacheItem(src = "Alice arrived.", name_src = "Alice")],
    )
    combined = "\n".join(contexts)

    assert "- Alice" in combined
    assert "本地译名" not in combined
    assert "分析译名" not in combined
    assert "角色译名" not in combined


def test_local_glossary_wins_over_character_and_analysis_for_same_source():
    config = Config(
        glossary_enable = True,
        glossary_data = [
            {"src": "Alice", "dst": "本地译名", "origin": "LOCAL", "record_id": "z-local"},
            {"src": "Alice", "dst": "分析译名", "origin": "ANALYSIS", "record_id": "a-analysis"},
        ],
        renpy_workbench_character_cards_enable = True,
        renpy_workbench_character_cards = [{
            "id": "character",
            "name": "Alice",
            "name_translation": "角色译名",
            "enabled": True,
        }],
    )

    combined = "\n".join(PromptBuilder(config).build_dynamic_asset_contexts(
        ["Alice"],
        [CacheItem(src = "Alice", name_src = "Alice")],
    ))

    assert "Alice -> 本地译名" in combined
    assert "分析译名" not in combined
    assert "角色译名" not in combined


def test_dynamic_asset_item_and_token_budgets_are_stable():
    config = Config(
        glossary_enable = True,
        glossary_data = [
            {"src": "Beta", "dst": "贝塔", "origin": "LOCAL", "record_id": "b"},
            {"src": "Gamma", "dst": "伽马", "origin": "ANALYSIS", "record_id": "g"},
        ],
        asset_prompt_max_items = 2,
        asset_prompt_token_budget = 2048,
    )
    config.do_not_translate_enable = True
    config.do_not_translate_data = [{"src": "Alpha", "record_id": "a", "enabled": True}]
    builder = PromptBuilder(config)

    first = builder.build_dynamic_asset_contexts(["Alpha Beta Gamma"], None)
    second = builder.build_dynamic_asset_contexts(["Alpha Beta Gamma"], None)
    combined = "\n".join(first)

    assert first == second
    assert "Alpha" in combined
    assert "Beta -> 贝塔" in combined
    assert "Gamma -> 伽马" not in combined

    config.asset_prompt_max_items = 64
    config.asset_prompt_token_budget = builder._asset_token_cost("- Alpha")
    token_limited = "\n".join(
        PromptBuilder(config).build_dynamic_asset_contexts(["Alpha Beta Gamma"], None)
    )
    assert "Alpha" in token_limited
    assert "Beta -> 贝塔" not in token_limited


def test_fixed_worldbook_and_style_are_not_truncated_by_dynamic_asset_budget():
    config = Config(
        translation_style_id = Config.STYLE_LITERARY,
        renpy_workbench_worldbook_enable = True,
        renpy_workbench_worldbook_data = {"setting_summary": "Full world context"},
        glossary_enable = True,
        glossary_data = [{"src": "Alice", "dst": "爱丽丝"}],
        asset_prompt_token_budget = 1,
        asset_prompt_max_items = 1,
    )

    messages, _ = PromptBuilder(config).generate_prompt(
        ["Alice"],
        samples = [],
        precedings = [],
        local_flag = False,
    )
    system = messages[0]["content"]

    assert "写作风格：LITERARY" in system
    assert "Full world context" in system
    assert "Alice -> 爱丽丝" not in system


def test_latin_glossary_uses_whole_word_and_cjk_uses_substring():
    config = Config(
        glossary_enable = True,
        glossary_data = [
            {"src": "an", "dst": "一个"},
            {"src": "勇者", "dst": "Hero"},
        ],
    )
    builder = PromptBuilder(config)

    assert builder.build_glossary(["Another day"]) == ""
    assert "勇者 -> Hero" in builder.build_glossary(["传说中的勇者们"])


def test_single_text_is_explicit_and_cannot_be_used_as_a_batch_protocol():
    config = Config(translation_output_protocol = Config.OUTPUT_PROTOCOL_STRUCTURED)
    builder = PromptBuilder(config)

    messages, _ = builder.generate_single_line_prompt(
        "Hello",
        samples = [],
        precedings = [],
        local_flag = False,
    )

    assert messages[0]["role"] == "system"
    assert "输出协议：SINGLE_TEXT" in messages[0]["content"]
    assert "输出协议：STRUCTURED" not in messages[0]["content"]
    assert "原文：" in messages[1]["content"]

    config.translation_output_protocol = Config.OUTPUT_PROTOCOL_SINGLE_TEXT
    with pytest.raises(ValueError, match = "generate_single_line_prompt"):
        builder.generate_prompt(["one", "two"], [], [], False)


def test_sakura_uses_new_jsonline_contract_without_padding_instruction():
    config = Config(translation_output_protocol = Config.OUTPUT_PROTOCOL_STRUCTURED)
    builder = PromptBuilder(config)

    messages, _ = builder.generate_prompt_sakura(["one", "two"])
    retry_messages, _ = builder.generate_prompt_sakura_format_retry(
        ["one", "two"],
        "bad response",
    )

    assert "输出协议：JSONLINE" in messages[0]["content"]
    assert "输出协议：STRUCTURED" not in messages[0]["content"]
    assert '{"request_index": 0, "text": "one"}' in messages[1]["content"]
    assert '{"0"' not in messages[1]["content"]
    retry_text = "\n".join(message["content"] for message in retry_messages)
    assert '"request_index":0' in retry_text
    assert "缺失行用空字符串" not in retry_text
    assert "补齐" not in retry_text


def test_task_context_is_consumed_through_read_only_snapshot_view():
    mutable_config = Config(
        source_language = BaseLanguage.Enum.EN,
        target_language = BaseLanguage.Enum.ZH,
    )
    assets = ProjectAssets.from_dict({
        "worldbook": {
            "enabled": True,
            "data": {"project_name": "Snapshot Project"},
        },
        "glossary": {
            "enabled": True,
            "items": [{"source": "Hero", "target": "英雄"}],
        },
    })
    context = TranslationTaskContext.from_config(
        mutable_config,
        assets,
        prompt = {
            "mode": Config.PROMPT_MODE_CUSTOM,
            "resolved_base": "SNAPSHOT BASE {source_language}->{target_language}",
            "style_id": Config.STYLE_CUSTOM,
            "resolved_style": "SNAPSHOT STYLE",
            "protocol": Config.OUTPUT_PROTOCOL_JSONLINE,
        },
    )
    builder = PromptBuilder(context)
    mutable_config.translation_custom_style = "MUTATED STYLE"
    mutable_config.glossary_data = [{"src": "Hero", "dst": "MUTATED"}]

    first, _ = builder.generate_prompt(["Hero"], [], [], False)
    second, _ = builder.generate_prompt(["Hero"], [], [], False)

    assert isinstance(builder.config, TranslationPromptConfigView)
    assert first == second
    assert "SNAPSHOT BASE 英文->中文" in first[0]["content"]
    assert "SNAPSHOT STYLE" in first[0]["content"]
    assert "Hero -> 英雄" in first[0]["content"]
    assert "MUTATED" not in first[0]["content"]


def test_prompt_resources_can_be_resolved_before_snapshot_persistence():
    config = Config(
        translation_prompt_mode = Config.PROMPT_MODE_THINK,
        translation_style_id = Config.STYLE_LITERARY,
        translation_output_protocol = Config.OUTPUT_PROTOCOL_JSONLINE,
    )

    snapshot_prompt = PromptBuilder(config).build_task_prompt_snapshot()

    assert snapshot_prompt["mode"] == Config.PROMPT_MODE_THINK
    assert "基础模式：THINK" in snapshot_prompt["resolved_base"]
    assert snapshot_prompt["style_id"] == Config.STYLE_LITERARY
    assert "写作风格：LITERARY" in snapshot_prompt["resolved_style"]
    assert snapshot_prompt["protocol"] == Config.OUTPUT_PROTOCOL_JSONLINE


def test_new_glossary_schema_is_closed_and_typed():
    schema = TaskRequester.TRANSLATION_RESULT_SCHEMA["properties"]["new_glossary"]["items"]

    assert schema["properties"] == {
        "src": {"type": "string"},
        "dst": {"type": "string"},
        "info": {"type": "string"},
    }
    assert schema["required"] == ["src", "dst"]
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(
    "protocol",
    (Config.OUTPUT_PROTOCOL_STRUCTURED, Config.OUTPUT_PROTOCOL_JSONLINE),
)
def test_direct_provider_input_extraction_understands_new_indexed_batches(protocol):
    config = Config(translation_output_protocol = protocol)
    messages, _ = PromptBuilder(config).generate_prompt(
        ["first", "second"],
        samples = [],
        precedings = [],
        local_flag = False,
    )
    requester = object.__new__(TaskRequester)

    assert requester._extract_translation_inputs(messages) == ["first", "second"]


def test_prompt_resources_do_not_contain_retired_protocols():
    root = Path(__file__).parents[2]
    texts = "\n".join(
        path.read_text(encoding = "utf-8-sig")
        for directory in (root / "resource" / "prompt", root / "resource" / "custom_prompt")
        for path in sorted(directory.rglob("*.txt"))
    )

    assert "<why>" not in texts
    assert "textarea" not in texts
    assert "line_number" not in texts
    assert "缺失行用空字符串补齐" not in texts
