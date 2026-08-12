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
