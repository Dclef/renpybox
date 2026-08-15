from types import SimpleNamespace

from frontend.RenpyToolbox.LocalGlossaryPage import LocalGlossaryPage
from frontend.Workbench.RenpyWorkbenchPage import RenpyWorkbenchPage
from module.Workbench.WorkbenchData import create_default_character_card


def test_glossary_candidate_merge_preserves_identity_and_suggested_translation() -> None:
    existing = {
        "record_id": "candidate-1",
        "src": "Alice",
        "dst": "爱丽丝",
        "type": "候选 / 角色",
        "comment": "runtime suggestion",
        "candidate": True,
        "case_sensitive": False,
    }
    scan = {
        "src": "Alice",
        "dst": "",
        "type": "候选 / 人名",
        "comment": "scan",
        "candidate": True,
        "case_sensitive": False,
    }

    merged = LocalGlossaryPage._merge_entries(existing, scan)

    assert merged["record_id"] == "candidate-1"
    assert merged["candidate"] is True
    assert merged["dst"] == "爱丽丝"


def test_candidate_scan_does_not_turn_existing_formal_row_back_into_candidate() -> None:
    formal = {
        "record_id": "formal-1",
        "src": "Alice",
        "dst": "爱丽丝",
        "candidate": False,
    }
    scan = {"src": "Alice", "candidate": True}

    merged = LocalGlossaryPage._merge_entries(formal, scan)

    assert merged["record_id"] == "formal-1"
    assert merged["candidate"] is False


def test_character_sync_merge_preserves_newer_draft_edits() -> None:
    current = create_default_character_card("Alice")
    current["name_translation"] = "爱丽丝"
    current["prompt_notes"] = "newer edit"
    stale = create_default_character_card("Alice")
    stale["name_translation"] = "旧译名"
    stale["prompt_notes"] = "stale payload"
    config = SimpleNamespace(
        renpy_workbench_generated_character_drafts = [current],
    )

    merged, added = RenpyWorkbenchPage._merge_candidates_into_cards(
        object(),
        config,
        [stale],
    )

    assert added == 0
    assert merged[0]["name_translation"] == "爱丽丝"
    assert merged[0]["prompt_notes"] == "newer edit"


def test_partial_import_draft_is_completed_from_existing_formal_card() -> None:
    """部分导入先以正式卡补全，应用时不会清空既有人设。"""
    formal = create_default_character_card("Alice")
    formal["identity"] = "侦探"
    config = SimpleNamespace(
        renpy_workbench_character_cards = [formal],
        renpy_workbench_generated_character_drafts = [],
    )

    drafts = RenpyWorkbenchPage._merge_imported_cards_as_drafts(
        object(),
        config,
        [{"name": "Alice", "prompt_notes": "固定译作爱丽丝"}],
    )

    assert drafts[0]["identity"] == "侦探"
    assert drafts[0]["prompt_notes"] == "固定译作爱丽丝"


def test_apply_drafts_keeps_manual_reference_notes_and_enables_assets() -> None:
    """AI 草稿晋升时保留人工总结，并开启实际提示词注入。"""
    draft = create_default_character_card("Alice")
    config = SimpleNamespace(
        renpy_workbench_worldbook_data = {"reference_notes": "人工总结"},
        renpy_workbench_generated_worldbook_draft = {"genre": "悬疑"},
        renpy_workbench_worldbook_enable = False,
        renpy_workbench_character_cards = [],
        renpy_workbench_generated_character_drafts = [draft],
        renpy_workbench_character_cards_enable = False,
    )

    applied = RenpyWorkbenchPage._apply_drafts_to_config(object(), config)

    assert applied is True
    assert config.renpy_workbench_worldbook_data["genre"] == "悬疑"
    assert config.renpy_workbench_worldbook_data["reference_notes"] == "人工总结"
    assert config.renpy_workbench_worldbook_enable is True
    assert config.renpy_workbench_character_cards_enable is True
    assert config.renpy_workbench_character_cards[0]["name"] == "Alice"
    assert config.renpy_workbench_generated_character_drafts == []
