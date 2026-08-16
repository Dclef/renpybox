import pytest

from module.Workbench.WorkbenchData import (
    create_default_character_card,
    merge_imported_character_cards,
    merge_imported_worldbook,
    parse_workbench_exchange,
)


def test_partial_character_import_preserves_fields_not_present_in_file() -> None:
    """部分角色资料只能覆盖显式字段，不能清空已有设定。"""
    alice = create_default_character_card("Alice")
    alice["identity"] = "侦探"
    alice["aliases"] = ["A"]

    merged = merge_imported_character_cards(
        [alice],
        [{"name": "Alice", "prompt_notes": "固定译作爱丽丝"}],
    )

    assert len(merged) == 1
    assert merged[0]["identity"] == "侦探"
    assert merged[0]["aliases"] == ["A"]
    assert merged[0]["prompt_notes"] == "固定译作爱丽丝"


def test_exchange_parser_accepts_export_object_and_character_array() -> None:
    worldbook, cards = parse_workbench_exchange({
        "worldbook": {"data": {"setting_summary": "浮空城"}},
        "character_cards": {"items": [{"name": "Alice"}]},
        "character_drafts": [{"name": "Bob", "identity": "医生"}],
    })

    assert worldbook == {"setting_summary": "浮空城"}
    assert [card["name"] for card in cards] == ["Alice", "Bob"]

    empty_worldbook, array_cards = parse_workbench_exchange([
        {"name": "Carol", "aliases": ["C"]},
    ])
    assert empty_worldbook == {}
    assert array_cards[0]["name"] == "Carol"


def test_worldbook_import_only_overwrites_explicit_fields() -> None:
    merged = merge_imported_worldbook(
        {"genre": "悬疑", "reference_notes": "旧总结"},
        {"reference_notes": "新总结"},
    )

    assert merged["genre"] == "悬疑"
    assert merged["reference_notes"] == "新总结"


def test_exchange_parser_rejects_empty_payload() -> None:
    with pytest.raises(ValueError, match="没有可导入"):
        parse_workbench_exchange({"character_cards": []})
