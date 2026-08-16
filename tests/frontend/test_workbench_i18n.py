import importlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QWidget

from base.BaseLanguage import BaseLanguage
from frontend.Workbench.RenpyWorkbenchPage import RenpyWorkbenchPage
from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.Workbench.WorkbenchData import create_default_character_card


APP = QApplication.instance() or QApplication([])
workbench_module = importlib.import_module("frontend.Workbench.RenpyWorkbenchPage")


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
