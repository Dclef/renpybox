"""角色发现与简单双语校对的用户操作回归。"""

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QBoxLayout, QWidget
from qfluentwidgets import Theme, qconfig, setTheme

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from frontend.Workbench.RenpyWorkbenchPage import RenpyWorkbenchPage
from frontend.Proofreading.ProofreadingPage import ProofreadingPage
from frontend.Proofreading.TextEditDialog import TextEditDialog
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.Engine import Engine
from module.Localizer.Localizer import Localizer
from module.Renpy.ProjectPaths import RenpyProjectPaths, apply_to_config
from module.ResultChecker import WarningType
from module.Workbench.WorkbenchData import create_default_character_card
from widget.ThemeHelper import get_current_stylesheet


APP = QApplication.instance() or QApplication([])


@pytest.fixture(scope="session", autouse=True)
def layout_fonts():
    """字体随 QApplication 保留，避免延迟销毁的控件引用已卸载字体。"""
    if not QFontDatabase().families():
        for name in ("segoeui.ttf", "msyh.ttc"):
            QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name))


def test_character_scan_search_and_apply_without_ai(monkeypatch, tmp_path):
    """从游戏脚本发现角色，审核后可按译名查找，整个扫描不需要 AI 接口。"""
    root = tmp_path / "Project"
    (root / "game" / "tl" / "chinese").mkdir(parents=True)
    (root / "game" / "script.rpy").write_text(
        'define e = Character("Eileen")\nlabel start:\n    e "Welcome, my friend."\n',
        encoding="utf-8",
    )
    config = Config()
    config.platforms = []
    apply_to_config(config, RenpyProjectPaths.from_path(root, "chinese"))
    monkeypatch.setattr(Config, "load", lambda *args, **kwargs: config)
    monkeypatch.setattr(Config, "save", lambda self: self)
    monkeypatch.setattr(RenpyWorkbenchPage, "_load_config", lambda self: config)
    monkeypatch.setattr(RenpyWorkbenchPage, "_save_config", lambda self, current: None)
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    engine = Engine()
    import importlib
    module = importlib.import_module("frontend.Workbench.RenpyWorkbenchPage")
    monkeypatch.setattr(module.threading, "Thread", lambda *, target, daemon: SimpleNamespace(start=target))
    monkeypatch.setattr(module.InfoBar, "success", lambda *args, **kwargs: None)
    page = RenpyWorkbenchPage("workbench")
    try:
        page.resize(1200, 800)
        page.switch_panel("characters")
        page.show()
        QTest.qWait(30)
        assert page.btn_sync_characters.isVisible()
        assert page.btn_sync_characters.isEnabled()
        page.btn_sync_characters.click()
        assert [card["name"] for card in config.renpy_workbench_generated_character_drafts] == ["Eileen"]
        assert page.character_detail_stack.currentIndex() == 1
        page._apply_current_character_draft()
        assert page.character_detail_stack.currentIndex() == 0
        page.character_widgets["name_translation"].setText("艾琳")
        page._flush_pending_edits()
        page.character_search_edit.setText("艾琳")
        assert not page.character_list.item(0).isHidden()
        page.character_search_edit.setText("不存在的角色")
        assert page.character_list.item(0).isHidden()
        assert page.character_splitter.count() == 2
        assert page.character_extra_fields.isHidden()
        page.character_more_toggle.click()
        assert not page.character_extra_fields.isHidden()
        page.character_detail_tabs.items["draft"].click()
        assert page.character_detail_stack.currentIndex() == 1
    finally:
        page.close()
        page.deleteLater()


def test_issue_filter_updates_after_background_check():
    page = ProofreadingPage("proofreading", QWidget())
    clean = CacheItem(src="Hello", dst="你好", status=Base.TranslationStatus.TRANSLATED)
    problem = CacheItem(src="Hello [name]", dst="你好", status=Base.TranslationStatus.TRANSLATED)
    page.items = [clean, problem]
    try:
        page.only_issues_check.setChecked(True)
        assert page.filtered_items == []
        page.warning_map[id(problem)] = [WarningType.TEXT_PRESERVE]
        page._on_warnings_check_done_ui(page._warning_check_id)
        assert page.filtered_items == [problem]
        page.only_issues_check.setChecked(False)
        assert page.filtered_items == [clean, problem]
    finally:
        page.close()
        page.deleteLater()


def test_bilingual_table_and_editor_fit_wide_and_narrow_windows(monkeypatch):
    config = Config()
    monkeypatch.setattr(Config, "load", lambda *args, **kwargs: config)
    window = QWidget()
    page = ProofreadingPage("proofreading", window)
    source = "A long sentence for comparison. " * 30 + "\nA second paragraph."
    target = "这是一段用于双语对照的长译文。" * 20 + "\n第二段。"
    item = CacheItem(src=source, dst=target, status=Base.TranslationStatus.TRANSLATED)
    page.items = page.filtered_items = [item]
    page.table_widget.set_items([item], {})
    dialog = None
    try:
        heights = []
        for width in (1200, 680):
            window.resize(width, 640)
            page.setGeometry(window.rect())
            window.show()
            QTest.qWait(50)
            table = page.table_widget
            assert table.item(0, table.COL_SRC).text() == source
            assert table.item(0, table.COL_DST).text() == target
            assert table.horizontalScrollBar().maximum() == 0
            heights.append(table.rowHeight(0))
            for button in (page.btn_load, page.btn_save, page.btn_export):
                assert not button.visibleRegion().isEmpty()
            assert page.pagination_bar.isVisible()
            assert page.inline_search_edit.placeholderText() == Localizer.get().proofreading_page_search_placeholder
        assert heights[0] > 42
        assert heights[1] > heights[0]
        for width in (1200, 680):
            window.resize(width, 640)
            dialog = TextEditDialog(source, target, window)
            dialog.show()
            QTest.qWait(230)
            assert dialog.rect().contains(dialog.widget.geometry())
            assert dialog.src_text_edit.isReadOnly()
            assert dialog.get_dst_text() == target
            assert dialog.editor_layout.direction() == (
                QBoxLayout.LeftToRight if width >= 760 else QBoxLayout.TopToBottom
            )
            assert not dialog.src_card.geometry().intersects(dialog.dst_card.geometry())
            dialog.reject()
            QTest.qWait(130)
            assert not dialog.isVisible()
            dialog.deleteLater()
            dialog = None
    finally:
        if dialog is not None:
            dialog.reject()
            QTest.qWait(130)
        window.close()
        window.deleteLater()


@pytest.mark.parametrize("language", [BaseLanguage.Enum.ZH, BaseLanguage.Enum.EN])
def test_character_filters_find_draft_names_and_keep_unsaved_edits(monkeypatch, language):
    """同一角色切换待审核视图、检索新译名时，正式资料的未保存编辑仍保留。"""
    config = Config()
    config.platforms = []
    formal = create_default_character_card("Alice")
    config.renpy_workbench_character_cards = [formal]
    config.renpy_workbench_generated_character_drafts = [dict(formal, name_translation="爱丽丝")]
    monkeypatch.setattr(Config, "load", lambda *args, **kwargs: config)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", language)
    monkeypatch.setattr(RenpyWorkbenchPage, "_load_config", lambda self: config)
    monkeypatch.setattr(RenpyWorkbenchPage, "_save_config", lambda self, current: None)
    page = RenpyWorkbenchPage("workbench")
    try:
        assert page.character_detail_stack.currentIndex() == 0
        page.character_widgets["identity"].setPlainText("手动补充的身份")
        page.character_filter_buttons["pending"].click()
        assert page.character_detail_stack.currentIndex() == 1
        assert config.renpy_workbench_character_cards[0]["identity"] == "手动补充的身份"
        page.character_search_edit.setText("爱丽丝")
        assert not page.character_list.item(0).isHidden()
        page.character_filter_buttons["all"].click()
        assert page.character_detail_stack.currentIndex() == 0
        assert page.character_widgets["identity"].toPlainText() == "手动补充的身份"
        page.character_search_edit.setText("不存在")
        assert not page.character_empty_label.isHidden()
        assert page.character_empty_label.text() == Localizer.get().workbench_character_no_match
        page.character_search_edit.clear()
        assert page.character_empty_label.isHidden()
    finally:
        page.close()
        page.deleteLater()


def test_worldbook_simplified_fields_save_and_restore(monkeypatch, tmp_path):
    """简化后折叠的字段仍随项目落盘，应用草稿后可在提示词中读取。"""
    config = Config()
    config.platforms = []
    root = tmp_path / "Project"
    (root / "game" / "tl" / "chinese").mkdir(parents=True)
    apply_to_config(config, RenpyProjectPaths.from_path(root, "chinese"))
    monkeypatch.setattr(Config, "load", lambda *args, **kwargs: config)
    monkeypatch.setattr(Config, "save", lambda self: self)
    import importlib
    module = importlib.import_module("frontend.Workbench.RenpyWorkbenchPage")
    monkeypatch.setattr(module.InfoBar, "success", lambda *args, **kwargs: None)
    page = RenpyWorkbenchPage("workbench")
    try:
        assert page.worldbook_extra_fields.isHidden()
        page.worldbook_widgets["setting_summary"].setPlainText("故事发生在银月王国。")
        page.worldbook_widgets["reference_notes"].setPlainText("地名统一使用银月。")
        page._flush_pending_edits()
        current = page._get_config_snapshot()
        current.renpy_workbench_generated_worldbook_draft = {"tone_style": "温和、自然"}
        page._apply_worldbook_draft()
        restored = page._load_config()
        assert restored.renpy_workbench_worldbook_enable
        assert restored.renpy_workbench_worldbook_data["setting_summary"] == "故事发生在银月王国。"
        assert restored.renpy_workbench_worldbook_data["reference_notes"] == "地名统一使用银月。"
        assert restored.renpy_workbench_worldbook_data["tone_style"] == "温和、自然"
        assert not any(restored.renpy_workbench_generated_worldbook_draft.values())
        page.refresh_from_config(restored)
        page._refresh_prompt_preview(restored)
        assert "银月王国" in page.preview_world_context.toPlainText()
    finally:
        page.close()
        page.deleteLater()


@pytest.mark.parametrize("theme", [Theme.LIGHT, Theme.DARK])
def test_bilingual_row_actions_follow_wrapped_rows(monkeypatch, theme):
    """实际主题下，宽窄切换后每行状态和操作按钮必须留在所属行内。"""
    monkeypatch.setattr(Config, "load", lambda *args, **kwargs: Config())
    previous_theme, previous_style = qconfig.theme, APP.styleSheet()
    setTheme(theme)
    APP.setStyleSheet(get_current_stylesheet())
    window = QWidget()
    page = ProofreadingPage("proofreading", window)
    table = page.table_widget
    items = [CacheItem(src="A long sentence. " * n, dst="一段较长的译文。" * n, status=Base.TranslationStatus.TRANSLATED) for n in (1, 8, 20)]
    page.items = page.filtered_items = items
    table.set_items(items, {})
    try:
        for width in (1200, 680, 1200):
            window.resize(width, 800)
            page.setGeometry(window.rect())
            window.show()
            QTest.qWait(100)
            for row in range(len(items)):
                for col in (table.COL_STATUS, table.COL_ACTION):
                    assert table.cellWidget(row, col).geometry() == table.visualRect(table.model().index(row, col))
    finally:
        window.close()
        window.deleteLater()
        setTheme(previous_theme)
        APP.setStyleSheet(previous_style)
