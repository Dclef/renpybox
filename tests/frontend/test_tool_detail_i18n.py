import os

import pytest
from types import SimpleNamespace

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
from module.Extract.UnifiedExtractor import ExtractionResult


APP = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))


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


def test_translation_extraction_page_creates_missing_tl_folder(tmp_path, monkeypatch) -> None:
    config = Config()
    config.extract_use_official = False
    config.extract_use_custom = True
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.ZH)

    project = tmp_path / "DemoGame"
    (project / "game").mkdir(parents=True)
    calls = []

    class ExtractorStub:
        def extract_regular(self, project_root, tl_name, exe_path, *, use_official):
            calls.append((project_root, tl_name, exe_path, use_official))
            return ExtractionResult(success=True, tl_dir=project_root / "game" / "tl" / tl_name)

    store = SimpleNamespace(
        set_game_folder=lambda *_args, **_kwargs: None,
        persist=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr("frontend.RenpyTranslationPage.ProjectStore.get", lambda: store)
    monkeypatch.setattr("frontend.RenpyTranslationPage.InfoBar.info", lambda *args, **kwargs: None)
    monkeypatch.setattr("frontend.RenpyTranslationPage.InfoBar.success", lambda *args, **kwargs: None)
    monkeypatch.setattr("frontend.RenpyTranslationPage.InfoBar.warning", lambda *args, **kwargs: None)
    monkeypatch.setattr("frontend.RenpyTranslationPage.InfoBar.error", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "frontend.RenpyTranslationPage.RenpyTranslationExtractionWorker.start",
        lambda self: self.run(),
    )

    page = RenpyTranslationPage()
    try:
        page.unified_extractor = ExtractorStub()
        page.game_dir_edit.setText(str(project))
        page.tl_name_edit.setText("chinese")
        page.chk_official.setChecked(False)
        page.chk_custom.setChecked(True)

        page._do_extract()

        assert (project / "game" / "tl" / "chinese").is_dir()
        assert calls == [(project, "chinese", None, False)]
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


@pytest.mark.parametrize("approve", [False, True])
def test_structured_export_confirms_existing_output(tmp_path, monkeypatch, approve):
    from PyQt5.QtWidgets import QMessageBox
    from module.Extract.HakimiSuiteRunner import HakimiResult

    module = "frontend.RenpyToolbox.MaSuitePage"
    (tmp_path / "game").mkdir()
    output = tmp_path / "translate_output"
    output.mkdir()
    (output / "manual.txt").write_text("manual", encoding="utf-8")
    questions, calls, shown = [], [], []
    monkeypatch.setattr(Config, "load", lambda self, path=None: self)
    monkeypatch.setattr(Config, "save", lambda self, path=None: None)
    monkeypatch.setattr(f"{module}.QMessageBox.question", lambda *args: questions.append(args[2]) or (QMessageBox.Yes if approve else QMessageBox.No))
    monkeypatch.setattr(f"{module}.InfoBar.success", lambda *args, **kwargs: pytest.fail("partial result must not show success"))
    monkeypatch.setattr(f"{module}.InfoBar.warning", lambda title, detail, **kwargs: shown.append((title, detail)))
    result = HakimiResult(base_dir=output)
    result.warnings = ["Emoji mapping failed"]
    result.backup_path = "output_backup"
    page = MaSuitePage("structure_confirm")
    try:
        page.path_edit.setText(str(tmp_path))
        page.hakimi_runner.run = lambda *args, **kwargs: calls.append(kwargs) or result
        page._run_suite()
        assert str(output) in questions[0]
        assert len(calls) == int(approve)
        if approve:
            assert calls[0]["confirm_overwrite"] is True
            assert "Emoji mapping failed" in shown[0][1]
            assert "output_backup" in shown[0][1]
    finally:
        page.close()


def test_structured_export_invalid_project_never_runs(tmp_path, monkeypatch):
    module = "frontend.RenpyToolbox.MaSuitePage"
    errors = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: self)
    monkeypatch.setattr(f"{module}.InfoBar.error", lambda *args, **kwargs: errors.append(args))
    page = MaSuitePage("structure_invalid")
    try:
        page.path_edit.setText(str(tmp_path))
        page.hakimi_runner.run = lambda *args, **kwargs: pytest.fail("invalid path must not authorize overwriting")
        page._run_suite()
        assert errors
    finally:
        page.close()


@pytest.mark.parametrize("counts,expected", [((0, 2, 0), "error"), ((1, 1, 1), "warning"), ((0, 0, 0), "warning"), ((1, 0, 0), "warning"), ((1, 0, 1), "success")])
def test_emoji_result_uses_real_completion_status(tmp_path, monkeypatch, counts, expected):
    from PyQt5.QtWidgets import QMessageBox

    module = "frontend.RenpyToolbox.MaSuitePage"
    (tmp_path / "game").mkdir()
    shown = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: self)
    monkeypatch.setattr(f"{module}.QMessageBox.question", lambda *args: QMessageBox.Yes)
    monkeypatch.setattr(f"{module}.load_default_mapping", lambda *args: {"a": "b"})
    monkeypatch.setattr(f"{module}.backup_folder", lambda *args, **kwargs: tmp_path / "backup")
    monkeypatch.setattr(f"{module}.apply_replacements_dir", lambda *args, **kwargs: counts)
    for tone in ("success", "warning", "error"):
        monkeypatch.setattr(f"{module}.InfoBar.{tone}", lambda title, detail, _tone=tone, **kwargs: shown.append((_tone, detail)))
    page = MaSuitePage("emoji_result")
    try:
        page.path_edit.setText(str(tmp_path))
        page.emoji_dir_edit.setText(str(tmp_path / "game"))
        page._run_emoji_dir("prepare")
        assert shown[0][0] == expected
        assert str(tmp_path / "backup") in shown[0][1]
    finally:
        page.close()
