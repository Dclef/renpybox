import importlib
import os
import sqlite3
from contextlib import closing

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QWidget

from base.BaseLanguage import BaseLanguage
from frontend.Workbench.RenpyWorkbenchPage import RenpyWorkbenchPage
from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.Workbench.WorkbenchData import create_default_character_card


APP = QApplication.instance() or QApplication([])
workbench_module = importlib.import_module("frontend.Workbench.RenpyWorkbenchPage")


@pytest.mark.parametrize("cache_kind, text_key, item_count", [
    ("sqlite", "workbench_cache_sqlite", 2),
    ("legacy", "workbench_cache_json", 2),
    ("missing", "workbench_not_set", 0),
    ("broken_sqlite", "workbench_cache_unreadable", 0),
    ("empty_sqlite", "workbench_cache_unreadable", 0),
    ("invalid_json", "workbench_cache_unreadable", 0),
    ("invalid_shape", "workbench_cache_unreadable", 0),
])
def test_workbench_cache_summary_is_read_only(monkeypatch, tmp_path, cache_kind, text_key, item_count) -> None:
    config = Config()
    config.output_folder = str(tmp_path)
    monkeypatch.setattr(workbench_module.RenpyProjectPaths, "from_config", lambda config: None)
    monkeypatch.setattr(RenpyWorkbenchPage, "_load_config", lambda self: config)
    monkeypatch.setattr(RenpyWorkbenchPage, "_save_config", lambda self, current: None)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    database = cache_dir / "cache.db"
    if cache_kind in {"sqlite", "empty_sqlite"}:
        with closing(sqlite3.connect(database)) as connection:
            if cache_kind == "sqlite":
                connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, data TEXT NOT NULL)")
                connection.executemany("INSERT INTO items (data) VALUES (?)", [("unparsed item",), ("unparsed item",)])
                connection.commit()
    elif cache_kind == "broken_sqlite":
        database.write_bytes(b"not a SQLite database")
    elif cache_kind != "missing":
        payloads = {"legacy": "[{}, {}]", "invalid_json": "[", "invalid_shape": "{}"}
        (cache_dir / "items.json").write_text(payloads[cache_kind], encoding="utf-8-sig")
    original_files = {path.name: path.read_bytes() for path in cache_dir.iterdir()}
    page = RenpyWorkbenchPage("workbench")
    try:
        expected = getattr(Localizer.get(), text_key).format(item_count=item_count)
        assert page.summary_labels["cache"].text() == expected
        assert page.summary_labels["cache"].toolTip() == expected
        assert {path.name: path.read_bytes() for path in cache_dir.iterdir()} == original_files
    finally:
        page.close()
        page.deleteLater()


@pytest.mark.parametrize("action", ["_apply_worldbook_draft", "_apply_current_character_draft", "_apply_all_drafts"])
def test_applying_drafts_preserves_pending_manual_edits(monkeypatch, action) -> None:
    config = Config()
    character = create_default_character_card("Alice")
    config.renpy_workbench_worldbook_data = {"project_name": "Story"}
    config.renpy_workbench_generated_worldbook_draft = {"genre": "Fantasy"}
    config.renpy_workbench_character_cards = [character]
    config.renpy_workbench_generated_character_drafts = [dict(character, identity="Historian")]
    monkeypatch.setattr(RenpyWorkbenchPage, "_load_config", lambda self: config)
    monkeypatch.setattr(RenpyWorkbenchPage, "_save_config", lambda self, current: None)
    monkeypatch.setattr(workbench_module.InfoBar, "success", lambda *args, **kwargs: None)
    page = RenpyWorkbenchPage("workbench")
    try:
        page.worldbook_widgets["reference_notes"].setPlainText("Manual notes\n" * 20)
        page.character_widgets["aliases"].setPlainText("Recently edited alias")
        assert page._edit_save_timer.isActive()
        assert page._pending_worldbook_fields == {"reference_notes"}
        assert page._pending_character_fields == {"aliases"}

        getattr(page, action)()

        assert config.renpy_workbench_worldbook_data["reference_notes"] == ("Manual notes\n" * 20).strip()
        assert "Recently edited alias" in config.renpy_workbench_character_cards[0]["aliases"]
        assert not page._pending_worldbook_fields
        assert not page._pending_character_fields
        assert not page._edit_save_timer.isActive()
        if action != "_apply_current_character_draft":
            assert config.renpy_workbench_worldbook_enable
            assert config.renpy_workbench_generated_worldbook_draft == {}
        if action != "_apply_worldbook_draft":
            assert config.renpy_workbench_character_cards_enable
            assert config.renpy_workbench_generated_character_drafts == []
            assert config.renpy_workbench_character_cards[0]["identity"] == "Historian"
    finally:
        page.close()
        page.deleteLater()


def test_workbench_english_static_dynamic_and_feedback_copy(monkeypatch) -> None:
    config = Config()
    config.get_platform = lambda _platform_id: None
    config.input_folder = ""
    config.output_folder = ""
    config.renpy_game_folder = ""
    config.renpy_tl_folder = ""
    config.renpy_workbench_worldbook_enable = False
    config.renpy_workbench_worldbook_data = {}
    config.renpy_workbench_generated_worldbook_draft = {
        "project_name": "Demo",
        "genre": "Fantasy",
    }
    character_draft = create_default_character_card("Alice")
    character_draft["identity"] = "Mage"
    config.renpy_workbench_character_cards_enable = False
    config.renpy_workbench_character_cards = []
    config.renpy_workbench_generated_character_drafts = [character_draft]

    monkeypatch.setattr(RenpyWorkbenchPage, "_load_config", lambda self: config)
    monkeypatch.setattr(RenpyWorkbenchPage, "_save_config", lambda self, current: None)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)

    warnings = []
    monkeypatch.setattr(
        workbench_module.InfoBar,
        "warning",
        lambda *args, **kwargs: warnings.append((args, kwargs)),
    )

    window = QWidget()
    page = RenpyWorkbenchPage("renpy_workbench_page", window)
    try:
        assert [text for _key, text in page.panel_order] == [
            "Overview",
            "Worldbuilding",
            "Character Cards",
            "Prompt Preview",
        ]
        assert page.btn_generate_current.text() == "Generate Current-Scope Drafts"
        assert page.btn_open_glossary.text() == "Open Local Glossary"
        assert page.btn_apply_all.text() == "Apply All & Enable"
        assert page.character_search_edit.placeholderText() == (
            "Search names, aliases, or keywords"
        )
        assert page.worldbook_enable.text() == "Inject Worldbuilding Context"
        assert page.character_cards_enable.text() == "Inject Character Card Context"
        assert page.preview_input_edit.placeholderText() == (
            "Enter one or more lines of sample source text."
        )

        assert page.summary_labels["platform"].text() == "Not configured"
        assert page.summary_labels["characters"].text() == "0 total, 0 enabled"
        assert "Worldbuilding draft: Available" in page.summary_labels["drafts"].text()
        assert "Project name: Demo" in page.worldbook_draft_preview.toPlainText()
        assert page.character_list.item(0).text() == "Alice [Draft]"
        assert "Character name: Alice" in page.character_draft_preview.toPlainText()
        assert page.overview_status_label.text().startswith(
            "The current API does not support AI analysis."
        )

        config.renpy_workbench_generated_worldbook_draft = {}
        page._apply_worldbook_draft()
        assert warnings[0][0][:2] == (
            "Notice",
            "There is no worldbuilding draft to apply.",
        )
    finally:
        page.close()
        window.close()


def test_character_ui_reuses_snapshot_and_debounces_edits(monkeypatch) -> None:
    """搜索、筛选、切换和连续编辑都复用快照，并只批量保存一次。"""
    config = Config()
    config.get_platform = lambda _platform_id: None
    config.input_folder = ""
    config.output_folder = ""
    config.renpy_game_folder = ""
    config.renpy_tl_folder = ""
    config.renpy_workbench_worldbook_enable = False
    config.renpy_workbench_worldbook_data = {}
    config.renpy_workbench_generated_worldbook_draft = {}
    alice = create_default_character_card("Alice")
    bob = create_default_character_card("Bob")
    bob["aliases"] = ["Doctor"]
    carol = create_default_character_card("Carol")
    config.renpy_workbench_character_cards_enable = False
    config.renpy_workbench_character_cards = [alice, bob]
    config.renpy_workbench_generated_character_drafts = [carol]

    loads = []
    saves = []
    monkeypatch.setattr(
        RenpyWorkbenchPage,
        "_load_config",
        lambda self: loads.append(True) or config,
    )
    monkeypatch.setattr(
        RenpyWorkbenchPage,
        "_save_config",
        lambda self, current: saves.append(current),
    )
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)

    window = QWidget()
    page = RenpyWorkbenchPage("renpy_workbench_page", window)
    try:
        assert len(loads) == 1
        assert page.character_list.item(0).text() == "Carol [Draft]"

        page.character_list.setCurrentRow(1)
        page.character_search_edit.setText("doctor")
        assert len(loads) == 1
        assert page.character_count_label.text() == "Showing 1 of 3"
        assert page.character_list.item(2).isHidden() is False

        page.character_search_edit.clear()
        page._set_character_filter("pending")
        assert page.character_count_label.text() == "Showing 1 of 3"
        assert page.character_list.currentItem().text() == "Carol [Draft]"
        assert len(loads) == 1

        page._set_character_filter("all")
        page.character_list.setCurrentRow(1)
        page.character_widgets["name"].setText("A")
        page.character_widgets["name"].setText("Ali")
        page.character_widgets["name"].setText("Alice Updated")

        assert len(loads) == 1
        assert saves == []
        assert page._pending_character_fields == {"name"}
        assert page.character_list.currentItem().text() == "Alice Updated"

        page._flush_pending_edits()

        assert len(loads) == 1
        assert saves == [config]
        assert next(
            card
            for card in config.renpy_workbench_character_cards
            if card["id"] == alice["id"]
        )["name"] == "Alice Updated"
    finally:
        page.close()
        window.close()
