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



def test_new_character_is_visible_and_keeps_pending_edits(monkeypatch):
    """搜索旧角色后新增，必须保留旧角色编辑并直接显示新角色。"""
    config = Config()
    config.platforms = []
    card = create_default_character_card("Alice")
    config.renpy_workbench_character_cards = [card]
    monkeypatch.setattr(Config, "load", lambda *args, **kwargs: config)
    monkeypatch.setattr(RenpyWorkbenchPage, "_load_config", lambda self: config)
    monkeypatch.setattr(RenpyWorkbenchPage, "_save_config", lambda *args: None)
    page = RenpyWorkbenchPage("workbench")
    try:
        page.character_search_edit.setText("Alice")
        page.character_widgets["identity"].setPlainText("尚未触发自动保存的身份")
        page._add_character_card()
        assert config.renpy_workbench_character_cards[0]["identity"] == "尚未触发自动保存的身份"
        assert page.character_search_edit.text() == ""
        assert page._selected_character_id == config.renpy_workbench_character_cards[-1]["id"]
        assert not page.character_list.currentItem().isHidden()
    finally:
        page.close()
        page.deleteLater()


def test_inline_search_advances_literal_matches_and_clears_state(monkeypatch):
    """常驻搜索忽略高级搜索的正则开关，回车继续定位下一处，清空后不残留旧词。"""
    monkeypatch.setattr(Config, "load", lambda *args, **kwargs: Config())
    window = QWidget()
    page = ProofreadingPage("proofreading", window)
    page.items = page.filtered_items = [CacheItem(src=s) for s in ("Hello [name]", "No variable", "Goodbye [name]")]
    page.table_widget.set_items(page.items, {})
    page.search_card.regex_btn.setChecked(True)
    page.search_card._on_regex_toggle()
    try:
        page.inline_search_edit.setText("[name]")
        page._on_inline_search_submitted()
        assert page.search_match_indices == [0, 2]
        assert page.search_current_match == 0
        page._on_inline_search_submitted()
        assert page.search_current_match == 1
        assert page.table_widget.get_selected_items() == [page.items[2]]
        assert page.search_card.isHidden()
        page._on_inline_search_submitted()
        assert page.search_current_match == 0
        page.inline_search_edit.clear()
        page._on_inline_search_submitted()
        assert page.search_keyword == ""
        assert page.search_match_indices == []
    finally:
        window.close()
        window.deleteLater()


def test_corrected_translation_leaves_issue_filter(monkeypatch):
    """修正占位符后自动更新问题列表，译文仍保留在完整缓存中。"""
    config = Config()
    monkeypatch.setattr(Config, "load", lambda *args, **kwargs: config)
    window = QWidget()
    page = ProofreadingPage("proofreading", window)
    page.config = config
    item = CacheItem(src="Hello [name]", dst="你好", status=Base.TranslationStatus.TRANSLATED)
    page.items = [item]
    page.warning_map = {id(item): [WarningType.TEXT_PRESERVE]}
    import importlib
    module = importlib.import_module("frontend.Proofreading.ProofreadingPage")
    monkeypatch.setattr(module.ResultChecker, "check_single_item", lambda self, current: [])
    try:
        page.only_issues_check.setChecked(True)
        assert page.filtered_items == [item]
        page._on_cell_edited(item, "你好 [name]")
        QTest.qWait(20)
        assert page.filtered_items == []
        assert page.items == [item]
        assert item.get_dst() == "你好 [name]"
        page.only_issues_check.setChecked(False)
        assert page.filtered_items == [item]
    finally:
        window.close()
        window.deleteLater()


@pytest.mark.parametrize("save_fails", [True, False])
def test_proofreading_export_requires_persisted_edits(monkeypatch, tmp_path, save_fails):
    """缓存实际写入失败必须提示失败并阻止导出，成功时可重新读出修改。"""
    from module.Cache.CacheManager import CacheManager
    config = Config(cache_use_sqlite=False, output_folder=str(tmp_path))
    monkeypatch.setattr(Config, "load", lambda *args, **kwargs: config)
    manager = CacheManager(service=False)
    old = CacheItem(src="Hello", dst="旧译文", status=Base.TranslationStatus.TRANSLATED)
    manager.save_to_file(manager.get_project(), [old], str(tmp_path), strict=True)
    import importlib
    module = importlib.import_module("frontend.Proofreading.ProofreadingPage")
    monkeypatch.setattr(module.threading, "Thread", lambda *, target, daemon: SimpleNamespace(start=target))
    if save_fails:
        def fail_write(*args, **kwargs):
            raise OSError("模拟磁盘写入失败")
        monkeypatch.setattr(CacheManager, "_save_translation_run_to_json", fail_write)
    window = QWidget()
    page = ProofreadingPage("proofreading", window)
    page.config = config
    page.items = [CacheItem(src="Hello", dst="新译文", status=Base.TranslationStatus.TRANSLATED)]
    exports, results = [], []
    monkeypatch.setattr(page, "export_data", lambda: exports.append(True))
    monkeypatch.setattr(page, "indeterminate_show", lambda *args: None)
    monkeypatch.setattr(page, "indeterminate_hide", lambda: None)
    page.save_done.connect(results.append)
    page._pending_export = True
    try:
        page.save_data()
        assert results == [not save_fails]
        assert exports == ([] if save_fails else [True])
        reloaded = CacheManager(service=False)
        reloaded.load_from_file(str(tmp_path), strict=True)
        assert reloaded.get_items()[0].get_dst() == ("旧译文" if save_fails else "新译文")
    finally:
        window.close()
        window.deleteLater()
