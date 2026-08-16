import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QWidget

from base.BaseLanguage import BaseLanguage
from frontend.RenpyTranslationPage import RenpyTranslationPage
from frontend.RenpyToolbox.AddLanguageEntrancePage import AddLanguageEntrancePage
from frontend.RenpyToolbox.DirectRpyTranslatePage import DirectRpyTranslatePage
from frontend.RenpyToolbox.ExtractTab import ExtractTab
from frontend.RenpyToolbox.MaSuitePage import MaSuitePage
from frontend.RenpyToolbox.SetDefaultLanguagePage import SetDefaultLanguagePage
from module.Config import Config
from module.Localizer.Localizer import Localizer


APP = QApplication.instance() or QApplication([])


def _widget_texts(page: QWidget) -> set[str]:
    texts = set()
    for widget in page.findChildren(QWidget):
        text_getter = getattr(widget, "text", None)
        if callable(text_getter):
            value = text_getter()
            if isinstance(value, str) and value:
                texts.add(value)
    return texts


def test_translation_extraction_page_uses_english_copy(monkeypatch) -> None:
    config = Config()
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)

    page = RenpyTranslationPage()
    try:
        texts = _widget_texts(page)
        assert "Translation Extraction" in texts
        assert "Start Extraction" in texts
        assert "▶ Advanced Options" in texts
        assert page.game_dir_edit.placeholderText() == (
            "Select the game project folder that contains the game directory"
        )
        assert page.exe_edit.placeholderText() == (
            "Leave blank to find the .exe automatically"
        )
    finally:
        page.close()


def test_json_extraction_page_uses_english_copy(monkeypatch) -> None:
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)

    page = ExtractTab("extract_tab")
    try:
        texts = _widget_texts(page)
        assert "Text Extraction JSON" in texts
        assert "Extract & Export JSON" in texts
        assert "Import JSON & Apply to tl" in texts
        assert "Ready" in texts
        assert page.game_file_edit.placeholderText() == (
            "Select the game executable (.exe)"
        )
    finally:
        page.close()


def test_direct_rpy_translation_page_uses_english_copy(monkeypatch) -> None:
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)

    page = DirectRpyTranslatePage("direct_rpy_translate")
    try:
        texts = _widget_texts(page)
        assert "📄 Translate tl/.rpy Files (Engine Workflow)" in texts
        assert "Start Translation" in texts
        assert "Create a .bak Backup Before Writing" in texts
        assert [
            page.target_lang_combo.itemText(index)
            for index in range(page.target_lang_combo.count())
        ] == [
            "Simplified Chinese",
            "Traditional Chinese",
            "English",
            "Japanese",
            "Korean",
        ]
        assert page.status_label.text() == "Ready"
    finally:
        page.close()


def test_language_script_pages_use_english_copy(monkeypatch) -> None:
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)

    add_page = AddLanguageEntrancePage("add_language")
    default_page = SetDefaultLanguagePage("set_default_language")
    try:
        add_texts = _widget_texts(add_page)
        assert "🌐 Add Language Menu" in add_texts
        assert "Add Language Menu" in add_texts
        assert add_page.game_dir_edit.placeholderText() == (
            "Select the project's game folder"
        )

        default_texts = _widget_texts(default_page)
        assert "🌍 Set Default Language" in default_texts
        assert "Set Default Language" in default_texts
        assert default_page.custom_lang_edit.placeholderText() == (
            "Leave blank to use the selected language"
        )
        assert default_page.language_combo.currentText() == "chinese"
    finally:
        add_page.close()
        default_page.close()


def test_structured_export_page_uses_english_copy(monkeypatch) -> None:
    config = Config()
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)

    page = MaSuitePage("ma_suite")
    try:
        texts = _widget_texts(page)
        assert "Structured Translation Suite" in texts
        assert "Generate Structured Files" in texts
        assert "Emoji Replacement Helper (Batch Folder)" in texts
        assert [
            page.mode_combo.itemText(index)
            for index in range(page.mode_combo.count())
        ] == [
            "Standard Only (Stable)",
            "Standard + External Files (.json/.yml)",
            "Standard + External + Aggressive Scan (Use Carefully)",
        ]
        assert page.status_label.text() == "Ready"
    finally:
        page.close()
