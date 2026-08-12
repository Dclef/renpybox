import importlib
import os
import re
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QWidget

from base.BaseLanguage import BaseLanguage
from frontend.RenpyToolbox.AndroidBuildPage import AndroidBuildPage
from frontend.RenpyToolbox.FontReplacePage import FontReplacePage
from module.Config import Config
from module.Localizer.Localizer import Localizer


APP = QApplication.instance() or QApplication([])
android_module = importlib.import_module(
    "frontend.RenpyToolbox.AndroidBuildPage"
)
font_module = importlib.import_module(
    "frontend.RenpyToolbox.FontReplacePage"
)


def _page_copy(page: QWidget) -> list[str]:
    copy = []
    for widget in [page, *page.findChildren(QWidget)]:
        for getter_name in ("text", "placeholderText", "toolTip"):
            getter = getattr(widget, getter_name, None)
            if callable(getter):
                value = getter()
                if isinstance(value, str) and value:
                    copy.append(value)

        count = getattr(widget, "count", None)
        item_text = getattr(widget, "itemText", None)
        if callable(count) and callable(item_text):
            copy.extend(
                value
                for index in range(count())
                if (value := item_text(index))
            )
    return copy


def _clean_android_config() -> Config:
    config = Config()
    config.renpy_sdk_path = ""
    config.renpy_project_path = ""
    config.android_app_name = ""
    config.android_package_name = ""
    config.android_version = ""
    config.android_archive_source_dir = ""
    config.android_shell_remove_dirs = "images,audio,video"
    config.android_dname = ""
    return config


def test_android_and_font_pages_use_english_copy(monkeypatch) -> None:
    config = _clean_android_config()
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)

    android_page = AndroidBuildPage("android_build_page")
    font_page = FontReplacePage("font_replace_page")
    try:
        assert android_page.check_env_button.text() == "Check Environment"
        assert android_page.build_button.text() == "Start Build"
        assert android_page.make_shell_button.text() == (
            "Generate archive.rpa + Clean Resources"
        )
        assert android_page.sdk_path_edit.placeholderText() == (
            "Select the renpy-sdk folder"
        )

        assert font_page.action_button.text() == "✨ Inject Fonts"
        assert font_page.toggle_advanced_btn.text() == "Expand"
        assert font_page.rescan_btn.text() == "Scan All Fonts"
        assert font_page.target_lang_combo.itemText(0) == "Auto Detect"
        assert font_page.detected_font_combo.itemText(0) == "Not Scanned"

        copy = _page_copy(android_page) + _page_copy(font_page)
        assert not any(re.search(r"[\u4e00-\u9fff]", text) for text in copy)
    finally:
        android_page.close()
        font_page.close()
        android_page.deleteLater()
        font_page.deleteLater()
        APP.processEvents()


def test_android_and_font_feedback_and_dialogs_use_english_copy(monkeypatch) -> None:
    config = _clean_android_config()
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)

    feedback = []
    for level in ("success", "warning", "error"):
        monkeypatch.setattr(
            android_module.InfoBar,
            level,
            lambda title, content, *args, _level=level, **kwargs: feedback.append(
                (_level, title, content)
            ),
        )

    folder_dialogs = []
    monkeypatch.setattr(
        android_module.QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: folder_dialogs.append(args[1]) or "",
    )
    file_dialogs = []
    monkeypatch.setattr(
        font_module.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: file_dialogs.append((args[1], args[3]))
        or ("", ""),
    )

    confirmations = []

    class MessageBoxStub:
        def __init__(self, title, content, _parent) -> None:
            confirmations.append((title, content))

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(android_module, "MessageBox", MessageBoxStub)

    android_page = AndroidBuildPage("android_build_page")
    font_page = FontReplacePage("font_replace_page")
    try:
        assert android_page._get_builder() is None
        font_page._manual_rescan()
        android_page._on_worker_finished(False, "")

        android_page._browse_sdk_path()
        android_page._browse_project_path()
        android_page._browse_archive_source_dir()
        font_page._browse_game_dir()
        font_page._browse_custom_font()
        android_page._make_shell_only()

        assert feedback == [
            ("warning", "Notice", "Select the Ren'Py SDK folder first."),
            ("warning", "Notice", "Select the game folder first."),
            ("error", "Failed", "Task failed."),
        ]
        assert folder_dialogs == [
            "Select the Ren'Py SDK Folder",
            "Select the Ren'Py Project Folder",
            "Select a Package Folder",
            "Select the Game Folder",
        ]
        assert file_dialogs == [
            ("Select a Font File", "Font Files (*.ttf *.otf);;All Files (*)")
        ]
        assert confirmations == [
            (
                "Confirm Shell Processing",
                "This will build archive.rpa in the project root and clean the configured resource folders.\n"
                "The operation modifies project files. Back up the project first.",
            )
        ]
    finally:
        android_page.close()
        font_page.close()
        android_page.deleteLater()
        font_page.deleteLater()
        APP.processEvents()


def test_font_dynamic_copy_and_auto_detect_semantics(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)
    feedback = []
    for level in ("success", "warning", "error"):
        monkeypatch.setattr(
            font_module.InfoBar,
            level,
            lambda title, content, *args, _level=level, **kwargs: feedback.append(
                (_level, title, content)
            ),
        )

    deployed_languages = []
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    page = FontReplacePage("font_replace_page")
    page.replacer = SimpleNamespace(
        deploy_builtin_font_pack=lambda _game_dir, language: (
            deployed_languages.append(language) or (True, "字体包已注入")
        ),
        scan_fonts=lambda _game_dir: [],
        discover_font_files=lambda _game_dir: [
            ("fonts/example.ttf", game_dir / "fonts" / "example.ttf")
        ],
        get_translation_languages=lambda _game_dir: ["spanish"],
    )
    try:
        page.game_dir_edit.setText(str(game_dir))
        page._one_click_inject()

        assert deployed_languages == ["chinese"]
        assert feedback == [
            (
                "success",
                "Done",
                "The font pack was injected into tl/chinese.",
            )
        ]

        page._scan_game_dir(str(game_dir))
        assert page.detected_font_combo.itemText(0) == (
            "No font references detected (1 font file(s) found)"
        )
        assert page.target_lang_combo.itemText(0) == (
            "Default Language (Global Replacement)"
        )
        assert "Scan complete" in page.status_label.text()
        assert not re.search(r"[\u4e00-\u9fff]", page.status_label.text())
        assert not re.search(
            r"[\u4e00-\u9fff]", page.font_scan_summary_label.text()
        )
    finally:
        page.close()
        page.deleteLater()
        APP.processEvents()
