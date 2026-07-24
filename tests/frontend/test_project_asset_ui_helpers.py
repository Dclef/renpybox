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
