import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QWidget

from base.BaseLanguage import BaseLanguage
from frontend.RenpyToolbox.BatchCorrectionPage import BatchCorrectionPage
from frontend.RenpyToolbox.ErrorRepairPage import ErrorRepairPage
from frontend.RenpyToolbox.FormatterPage import FormatterPage
from frontend.RenpyToolbox.GameModPage import GameModPage
from frontend.RenpyToolbox.HookSupplementPage import HookSupplementPage
from frontend.RenpyToolbox.HookTranslatePage import HookTranslatePage
from frontend.RenpyToolbox.HtmlImportPage import HtmlImportPage
from frontend.RenpyToolbox.HonorificPlaceholderPage import HonorificPlaceholderPage
from frontend.RenpyToolbox.NameExtractionPage import NameExtractionPage
from frontend.RenpyToolbox.SourceTranslatePage import SourceTranslatePage
from frontend.RenpyToolbox.TranslationReusePage import TranslationReusePage
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


def test_remaining_asset_and_engineering_tools_use_english_copy(monkeypatch) -> None:
    config = Config()
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Config, "save", lambda self, path=None: None)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)

    pages = [
        FormatterPage("formatter"),
        ErrorRepairPage("error_repair"),
        TranslationReusePage("translation_reuse"),
        HonorificPlaceholderPage("honorific_placeholder"),
        BatchCorrectionPage("batch_correction"),
        NameExtractionPage("name_extraction"),
        HtmlImportPage("html_import"),
        HookTranslatePage("hook_translate"),
        SourceTranslatePage("source_translate"),
        HookSupplementPage("hook_supplement"),
    ]
    try:
        texts = set().union(*(_widget_texts(page) for page in pages))
        assert "🎨 Code Formatter" in texts
        assert "🔧 Error Repair" in texts
        assert "Reuse Updated Translations" in texts
        assert "Honorific Variable Bridge" in texts
        assert "Batch Corrections" in texts
        assert "Name Extraction" in texts
        assert "HTML Import / Conversion" in texts
        assert pages[0].game_dir_edit.placeholderText() == (
            "Select the game folder containing .rpy files"
        )
        assert pages[2].summary_label.text() == "Not previewed"
        assert pages[6].excel_column_combo.currentText() == "Translation"
        assert pages[6].excel_column_combo.currentData() == "译文"
        assert "HOOK Translation" in texts
        assert "🔧 Source Translation" in texts
        assert "Supplement Translation" in texts
        for page in pages[7:]:
            assert page.source_lang_combo.currentData() == BaseLanguage.Enum.EN
            assert page.target_lang_combo.currentData() == BaseLanguage.Enum.ZH
    finally:
        for page in pages:
            page.close()


def test_game_mod_page_uses_english_copy(monkeypatch) -> None:
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)
    shown = []
    monkeypatch.setattr(
        "frontend.RenpyToolbox.GameModPage.InfoBar.success",
        lambda title, content, **kwargs: shown.append((title, content)),
    )
    monkeypatch.setattr(
        "frontend.RenpyToolbox.GameModPage.InfoBar.error",
        lambda title, content, **kwargs: shown.append((title, content)),
    )

    page = GameModPage("game_mod")
    try:
        texts = _widget_texts(page)
        assert "Game Mod Injection" in texts
        assert "Game Folder" in texts
        assert "Install" in texts
        assert "Uninstall" in texts
        assert page.gallery_status_label.text() == (
            "Gallery unlocker: no game folder selected"
        )
        page._on_operation_done("install", "gallery_unlock", "安装成功")
        page._on_operation_failed("install", "gallery_unlock", "模组资源不存在")
        assert shown == [
            ("Installation Complete", "The mod was installed successfully."),
            ("Installation Failed", "The operation failed. Check the logs for details."),
        ]
    finally:
        page.close()


def test_english_batch_workbook_can_be_exported_by_html_tool(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)
    monkeypatch.setattr(
        "frontend.RenpyToolbox.BatchCorrectionPage.InfoBar.success",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "frontend.RenpyToolbox.HtmlImportPage.InfoBar.success",
        lambda *args, **kwargs: None,
    )

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "result_check_dialogue.json").write_text(
        '{"game/script.rpy": {"Hello": "\u4f60\u597d"}}', encoding="utf-8"
    )

    batch_page = BatchCorrectionPage("batch_correction")
    html_page = HtmlImportPage("html_import")
    try:
        batch_page.input_folder = str(input_dir)
        batch_page.output_folder = str(output_dir)
        batch_page._step_01_clicked()

        workbook = output_dir / "批量修正.xlsx"
        exported = output_dir / "translation.txt"
        assert workbook.is_file()

        html_page.excel_input_edit.setText(str(workbook))
        html_page.excel_txt_output_edit.setText(str(exported))
        html_page.excel_column_combo.setCurrentIndex(0)
        html_page._convert_excel_to_txt()

        assert exported.read_text(encoding="utf-8") == "你好"
    finally:
        batch_page.close()
        html_page.close()
