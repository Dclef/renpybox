import os
import re
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import qfluentwidgets
from PyQt5.QtWidgets import QApplication, QWidget
from qfluentwidgets import TitleLabel

from base.BaseLanguage import BaseLanguage
from frontend.RenpyToolbox import OneKeyTranslatePage as page_module
from module.Config import Config
from module.Localizer.Localizer import Localizer
from widget.ItemCard import ItemCard


APP = QApplication.instance() or QApplication([])


def test_onekey_wizard_uses_english_ui(monkeypatch) -> None:
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)
    monkeypatch.setattr(Config, "load", lambda self: self)

    page = page_module.YiJianFanyiPage()
    titles = {label.text() for label in page.findChildren(TitleLabel)}

    assert "Step 1/5: Select Game" in titles
    assert "Step 2/5: Extract Text" in titles
    assert "Step 3/5: Terms and Translation Context" in titles
    assert "Step 4/5: Run AI Translation" in titles
    assert "Step 5/5: Review, Export, and Post-process" in titles
    assert page.game_path_edit.placeholderText().startswith(
        "Enter or paste a game folder path"
    )
    assert page.browse_btn.text() == "Browse..."
    assert page.incremental_rb.text() == "Incremental extraction (recommended)"
    assert page.full_extract_rb.text() == "Full extraction (start over)"
    assert page.src_lang_combo.itemText(0) == "English"
    assert page.tgt_lang_combo.itemText(0) == "Simplified Chinese"
    assert page.step1_next_btn.text() == "Extract Text →"
    assert page.step2_retry_btn.text() == "Extract Again"
    assert page.step2_unpack_btn.text() == "Open RPA Unpacker"
    assert page.open_glossary_btn.text() == "📂 Open Local Glossary"
    assert page.start_trans_btn.text() == "🚀 Start Translation"
    assert page.skip_trans_btn.text() == "Skip Translation →"

    card_titles = {
        card.title_label.text() for card in page.findChildren(ItemCard)
    }
    assert {
        "Review, Polish, and Export",
        "Recover Missed Text",
        "Detect / Repair Errors",
        "Set Default Language",
        "Add Language Switch",
        "Inject Fonts",
        "Open Game Folder",
        "Export Language Patch",
    }.issubset(card_titles)

    page.deleteLater()


def test_onekey_visible_english_pages_do_not_expose_chinese(monkeypatch) -> None:
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)
    monkeypatch.setattr(Config, "load", lambda self: self)
    page = page_module.YiJianFanyiPage()
    page.resize(1280, 800)
    page.show()
    APP.processEvents()
    leaks = []

    for index in range(page.stacked.count()):
        page.stacked.setCurrentIndex(index)
        APP.processEvents()
        current = page.stacked.currentWidget()
        for widget in [current, *current.findChildren(QWidget)]:
            if not widget.isVisibleTo(current):
                continue
            for attribute in ("text", "placeholderText", "toolTip", "windowTitle"):
                getter = getattr(widget, attribute, None)
                if not callable(getter):
                    continue
                value = getter()
                if isinstance(value, str) and re.search(r"[\u4e00-\u9fff]", value):
                    leaks.append((index + 1, type(widget).__name__, attribute, value))

    assert leaks == []
    page.close()
    page.deleteLater()


def test_onekey_dynamic_statuses_use_english(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)
    monkeypatch.setattr(Config, "load", lambda self: self)
    page = page_module.YiJianFanyiPage()
    monkeypatch.setattr(page, "_sync_game_dir_to_config", lambda path: None)
    monkeypatch.setattr(page, "_check_old_translation", lambda path: None)

    project_dir = tmp_path / "project"
    game_dir = project_dir / "game"
    game_dir.mkdir(parents=True)
    page._on_path_text_changed(str(project_dir))
    assert page.path_status_label.text() == "✓ Valid Ren'Py game folder detected"

    (game_dir / "archive.rpa").write_bytes(b"RPA-3.0")
    status, message = page._detect_game_status(str(project_dir))
    assert status == "need_unpack"
    assert message == "Found 1 RPA archives that must be unpacked"

    status_texts = []
    start_texts = []
    skip_texts = []
    completed_page = SimpleNamespace(
        _onekey_translation_completed=True,
        _translation_output_completed=lambda: False,
        step4_status=SimpleNamespace(
            setText=status_texts.append,
            setStyleSheet=lambda value: None,
        ),
        start_trans_btn=SimpleNamespace(
            setText=start_texts.append,
            setEnabled=lambda value: None,
        ),
        skip_trans_btn=SimpleNamespace(setText=skip_texts.append),
    )
    page_module.YiJianFanyiPage._refresh_step4_state(completed_page)
    assert "Translation is complete" in status_texts[-1]
    assert start_texts[-1] == "Translate Again"
    assert skip_texts[-1] == "Continue to Post-processing →"

    page.deleteLater()


def test_onekey_english_dialog_and_feedback(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)
    dialog_data = {}
    feedback = []

    class FakeButton:
        def __init__(self, key: str) -> None:
            self.key = key

        def setText(self, value: str) -> None:
            dialog_data[self.key] = value

    class FakeMessageBox:
        def __init__(self, title, message, parent) -> None:
            dialog_data["title"] = title
            dialog_data["message"] = message
            self.yesButton = FakeButton("yes")
            self.cancelButton = FakeButton("cancel")

        def exec(self) -> bool:
            return True

    monkeypatch.setattr(qfluentwidgets, "MessageBox", FakeMessageBox)
    monkeypatch.setattr(
        "module.Extract.ReplaceGenerator.clear_declined_candidates",
        lambda game_dir, tl_name: 2,
    )
    monkeypatch.setattr(
        page_module,
        "InfoBar",
        SimpleNamespace(
            success=lambda title, message, **kwargs: feedback.append(
                ("success", title, message)
            ),
            info=lambda title, message, **kwargs: feedback.append(
                ("info", title, message)
            ),
            warning=lambda title, message, **kwargs: feedback.append(
                ("warning", title, message)
            ),
        ),
    )
    page = SimpleNamespace(
        game_dir=str(tmp_path),
        tl_folder_edit=SimpleNamespace(text=lambda: "chinese"),
    )

    page_module.YiJianFanyiPage._clear_declined_candidates(page)

    assert dialog_data == {
        "title": "Clear Skipped Candidates",
        "message": "These terms will be retried for translation during the next run.",
        "yes": "Clear",
        "cancel": "Cancel",
    }
    assert feedback[-1] == (
        "success",
        "Cleared",
        "Cleared 2 skipped candidates",
    )


def test_extraction_worker_preserves_details_without_leaking_chinese(
    monkeypatch,
) -> None:
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)

    class ExtractorStub:
        def set_progress_callback(self, callback) -> None:
            self.callback = callback

        def extract_regular(self, *args, **kwargs):
            self.callback("正在执行官方抽取...", 20)
            return SimpleNamespace(
                success=False,
                message="抽取失败；已自动恢复原翻译目录",
                total_files=0,
                incremental_dir=None,
                preserved_count=0,
            )

    progress = []
    finished = []
    worker = page_module.ExtractionWorker(
        ExtractorStub(), "game", "chinese", None
    )
    worker.progress.connect(lambda message, percent: progress.append((message, percent)))
    worker.finished.connect(
        lambda success, message, result: finished.append((success, message, result))
    )

    worker.run()

    assert progress == [("Running official extraction...", 20)]
    assert finished[0][0:2] == (
        False,
        "Text extraction failed. The original translation folder was restored. Check the logs for details.",
    )
    assert re.search(r"[\u4e00-\u9fff]", finished[0][1]) is None


def test_incremental_merge_failure_keeps_recovery_state_in_english(
    monkeypatch,
) -> None:
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)

    class ExtractorStub:
        def merge_incremental_folder(self, *args, **kwargs):
            return SimpleNamespace(
                success=False,
                message="增量合并未完成，已保留增量目录：缺少 1 条 strings",
            )

    finished = []
    worker = page_module.ApplyTranslationWorker(
        ExtractorStub(),
        incremental_mode=True,
        game_dir="game",
        tl_name="chinese",
        output_dir="output",
        main_output="main",
        config=SimpleNamespace(),
    )
    worker.finished.connect(
        lambda success, message, payload: finished.append(
            (success, message, payload)
        )
    )

    worker._run_incremental()

    assert finished == [
        (
            False,
            "The incremental merge did not complete. The incremental folder was preserved. Check the logs for details.",
            {"warning": True},
        )
    ]
