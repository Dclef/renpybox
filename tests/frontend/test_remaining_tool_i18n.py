import os

import pytest
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
        assert "Web / AI Translation Wizard" in texts
        assert pages[1].game_dir_edit.placeholderText() == (
            "Select game/tl/<language> or a folder containing generated .rpy files"
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


@pytest.mark.parametrize("approve", [False, True])
def test_batch_export_requires_overwrite_confirmation(tmp_path, monkeypatch, approve):
    from PyQt5.QtWidgets import QMessageBox

    module = "frontend.RenpyToolbox.BatchCorrectionPage"
    folder = tmp_path / "checks"
    folder.mkdir()
    (folder / "result_check_dialogue.json").write_text('{"script.rpy":{"Hello":"你好"}}', encoding="utf-8")
    workbook = folder / "批量修正.xlsx"
    workbook.write_bytes(b"existing workbook")
    shown = []
    questions = []
    monkeypatch.setattr(f"{module}.InfoBar.success", lambda *args, **kwargs: shown.append(args))
    monkeypatch.setattr(f"{module}.InfoBar.error", lambda *args, **kwargs: pytest.fail(str(args)))
    monkeypatch.setattr(f"{module}.QMessageBox.question", lambda *args: questions.append(args[2]) or (QMessageBox.Yes if approve else QMessageBox.No))
    page = BatchCorrectionPage("batch_overwrite")
    try:
        page.input_folder = page.output_folder = str(folder)
        page._step_01_clicked()
        assert str(workbook) in questions[0]
        if approve:
            assert workbook.read_bytes().startswith(b"PK")
            assert list(folder.glob("批量修正.xlsx.bak_*"))[0].read_bytes() == b"existing workbook"
            assert shown
        else:
            assert workbook.read_bytes() == b"existing workbook"
            assert not list(folder.glob("*.bak_*"))
            assert not shown
    finally:
        page.close()


def test_batch_apply_requires_confirmation_each_time(tmp_path, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox

    module = "frontend.RenpyToolbox.BatchCorrectionPage"
    workbook = tmp_path / "批量修正.xlsx"
    workbook.touch()
    calls = []
    questions = []
    answers = iter([QMessageBox.No, QMessageBox.Yes, QMessageBox.No])
    monkeypatch.setattr(f"{module}.QMessageBox.question", lambda *args: questions.append(args[2]) or next(answers))
    monkeypatch.setattr(f"{module}.InfoBar.info", lambda *args, **kwargs: None)
    monkeypatch.setattr(f"{module}.InfoBar.success", lambda *args, **kwargs: None)
    monkeypatch.setattr(f"{module}.apply_batch_corrections", lambda *args, **kwargs: calls.append((args, kwargs)) or {"applied_changes": 1, "message": "done"})
    page = BatchCorrectionPage("batch_confirm")
    try:
        page.workbook_path = str(workbook)
        page.translation_root = str(tmp_path)
        for _ in range(3):
            page._step_02_clicked()
        assert len(calls) == 1
        assert calls[0][1] == {"confirm": True}
        assert len(questions) == 3
        assert all(str(tmp_path) in question and str(workbook) in question for question in questions)
    finally:
        page.close()


@pytest.mark.parametrize("level,applied,expected", [("warning", 1, "warning"), ("error", 0, "error")])
def test_batch_apply_displays_partial_and_failed_results(tmp_path, monkeypatch, level, applied, expected):
    from PyQt5.QtWidgets import QMessageBox

    module = "frontend.RenpyToolbox.BatchCorrectionPage"
    workbook = tmp_path / "批量修正.xlsx"
    workbook.touch()
    shown = []
    monkeypatch.setattr(f"{module}.QMessageBox.question", lambda *args: QMessageBox.Yes)
    for tone in ("success", "warning", "error"):
        monkeypatch.setattr(f"{module}.InfoBar.{tone}", lambda title, detail, _tone=tone, **kwargs: shown.append((_tone, detail)))
    monkeypatch.setattr(f"{module}.apply_batch_corrections", lambda *args, **kwargs: {
        "applied_changes": applied, "level": level, "partial": bool(applied), "message": "result",
        "warnings": ["read failed"], "backups": ["script.rpy.bak"],
        "unmatched": [{"path": "missing.rpy", "items": [{}], "reason": "missing"}],
    })
    page = BatchCorrectionPage("batch_result")
    try:
        page.workbook_path = str(workbook)
        page.translation_root = str(tmp_path)
        page._step_02_clicked()
        assert shown[0][0] == expected
        assert all(value in shown[0][1] for value in ("read failed", "script.rpy.bak", "missing.rpy"))
    finally:
        page.close()


@pytest.mark.parametrize("empty", [False, True])
def test_name_extraction_displays_warnings_and_keeps_existing_draft(tmp_path, monkeypatch, empty):
    module = "frontend.RenpyToolbox.NameExtractionPage"
    shown = []
    monkeypatch.setattr(f"{module}.InfoBar.warning", lambda title, detail, **kwargs: shown.append(detail))
    monkeypatch.setattr(f"{module}.InfoBar.success", lambda *args, **kwargs: pytest.fail("warnings must not show success"))
    entries = [] if empty else [{"src": "Alice", "context": "context"}]
    monkeypatch.setattr(f"{module}.extract_character_names", lambda *args: {
        "empty": empty, "entries": entries, "count": len(entries), "warnings": ["bad.json failed"],
    })
    page = NameExtractionPage("name_warnings")
    try:
        page.input_folder = str(tmp_path)
        page.extracted_entries = [{"src": "Previous", "context": "old"}]
        page._step_01_clicked()
        assert "bad.json failed" in shown[0]
        assert page.extracted_entries[0]["src"] == ("Previous" if empty else "Alice")
    finally:
        page.close()


def test_name_export_confirms_final_path_after_adding_extension(tmp_path, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox

    module = "frontend.RenpyToolbox.NameExtractionPage"
    target = tmp_path / "glossary.json"
    target.write_text("existing", encoding="utf-8")
    questions = []
    monkeypatch.setattr(f"{module}.QFileDialog.getSaveFileName", lambda *args: (str(tmp_path / "glossary"), "JSON Files (*.json)"))
    monkeypatch.setattr(f"{module}.QMessageBox.question", lambda *args: questions.append(args[2]) or QMessageBox.No)
    monkeypatch.setattr(f"{module}.export_name_glossary", lambda *args, **kwargs: pytest.fail("cancelled export must not write"))
    page = NameExtractionPage("name_overwrite")
    try:
        page.extracted_entries = [{"src": "Alice", "context": "context"}]
        page._step_02_clicked()
        assert str(target) in questions[0]
        assert target.read_text(encoding="utf-8") == "existing"
    finally:
        page.close()
