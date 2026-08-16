import importlib
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QAbstractButton
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QWidget

from base.BaseLanguage import BaseLanguage
from frontend.RenpyToolbox.LocalGlossaryPage import LocalGlossaryPage
from frontend.RenpyToolbox.TextPreservePage import TextPreservePage
from module.Config import Config
from module.Localizer.Localizer import Localizer


APP = QApplication.instance() or QApplication([])
glossary_module = importlib.import_module(
    "frontend.RenpyToolbox.LocalGlossaryPage"
)
preserve_module = importlib.import_module(
    "frontend.RenpyToolbox.TextPreservePage"
)


def _page_copy(page) -> list[str]:
    copy = [widget.text() for widget in page.findChildren(QLabel)]
    copy.extend(widget.text() for widget in page.findChildren(QAbstractButton))
    copy.extend(
        widget.toolTip()
        for widget in page.findChildren(QWidget)
        if widget.toolTip()
    )
    copy.extend(
        page.table.horizontalHeaderItem(column).text()
        for column in range(page.table.columnCount())
    )
    return [text for text in copy if text]


def test_glossary_and_text_preserve_english_ui_and_feedback(monkeypatch) -> None:
    config = Config()
    config.input_folder = ""
    config.output_folder = ""
    config.renpy_project_path = ""
    config.renpy_game_folder = ""
    config.renpy_tl_folder = ""
    config.glossary_data = []
    config.text_preserve_data = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    feedback = []
    for level in ("success", "info", "warning", "error"):
        monkeypatch.setattr(
            glossary_module.InfoBar,
            level,
            lambda title, content, *args, _level=level, **kwargs: feedback.append(
                (_level, title, content)
            ),
        )

    dialogs = []
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: dialogs.append(args) or ("", ""),
    )
    monkeypatch.setattr(glossary_module, "load_workbook", object())
    monkeypatch.setattr(preserve_module, "load_workbook", object())

    previous_language = Localizer.get_app_language()
    Localizer.set_app_language(BaseLanguage.Enum.EN)
    glossary_page = LocalGlossaryPage("local_glossary_page")
    preserve_page = TextPreservePage("text_preserve_page")
    try:
        glossary_copy = _page_copy(glossary_page)
        preserve_copy = _page_copy(preserve_page)

        assert "Project Glossary" in " ".join(glossary_copy)
        assert "Scan Term Candidates" in glossary_copy
        assert "Source" in glossary_copy
        assert "Translation" in glossary_copy
        assert "Do Not Translate" in " ".join(preserve_copy)
        assert "Rescan Variables" in preserve_copy
        assert "Notes" in preserve_copy
        assert not any(re.search(r"[\u4e00-\u9fff]", text) for text in glossary_copy)
        assert not any(re.search(r"[\u4e00-\u9fff]", text) for text in preserve_copy)

        glossary_page._remove_selected_rows()
        preserve_page._remove_selected_rows()
        glossary_page._on_import_excel()
        preserve_page._on_import_excel()

        assert feedback[-2:] == [
            ("warning", "Notice", "Select an entry to delete."),
            ("warning", "Notice", "Select an entry to delete."),
        ]
        assert not any(
            re.search(r"[\u4e00-\u9fff]", f"{title}{content}")
            for _, title, content in feedback
        )
        assert [args[1] for args in dialogs] == [
            "Select Glossary Excel File",
            "Select Excel File",
        ]
        assert [args[3] for args in dialogs] == [
            "Excel Files (*.xlsx)",
            "Excel Files (*.xlsx)",
        ]

        # 分类值和导出字段属于业务数据，不随界面语言切换。
        assert LocalGlossaryPage._categorize_term("Moon City") == "地名"
        assert LocalGlossaryPage.HEADERS[0] == "原文"
        assert TextPreservePage.HEADERS[0] == "原文"
    finally:
        glossary_page.close()
        preserve_page.close()
        glossary_page.deleteLater()
        preserve_page.deleteLater()
        APP.processEvents()
        Localizer.set_app_language(previous_language)
