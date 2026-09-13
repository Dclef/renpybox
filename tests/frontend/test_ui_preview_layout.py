import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QBoxLayout
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QColor, QFontDatabase
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from qfluentwidgets import SingleDirectionScrollArea, Theme, ThemeColor, qconfig, setTheme

from base.BaseLanguage import BaseLanguage
from frontend.Agent.AgentPage import AgentEmptyState, AgentMessageWidget, AgentPage
from frontend.AppSettingsPage import AppSettingsPage
from frontend.Proofreading.ProofreadingPage import ProofreadingPage
from frontend.Project.ProjectPage import ProjectPage
from frontend.RenpyToolbox.OneKeyTranslatePage import YiJianFanyiPage
from frontend.RenpyToolbox.RenpyToolboxPage import RenpyToolboxPage
from frontend.Setting.BasicSettingsPage import BasicSettingsPage
from frontend.TranslationPage import TranslationPage
from frontend.Workbench.RenpyWorkbenchPage import RenpyWorkbenchPage
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.Engine import Engine
from module.Localizer.Localizer import Localizer
from module.Workbench.WorkbenchData import create_default_character_card
from widget import ThemeHelper
from widget.ThemeTokens import DARK, LIGHT


APP = QApplication.instance() or QApplication([])


@pytest.fixture(scope="module", autouse=True)
def layout_fonts():
    font_ids = []
    if not QFontDatabase().families():
        font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for filename in ("segoeui.ttf", "msyh.ttc"):
            font_id = QFontDatabase.addApplicationFont(str(font_dir / filename))
            if font_id >= 0:
                font_ids.append(font_id)
    try:
        if not QFontDatabase().families():
            pytest.skip("离屏平台未提供真实字体，无法验证文字布局")
        yield
    finally:
        for font_id in font_ids:
            QFontDatabase.removeApplicationFont(font_id)


@pytest.mark.parametrize("language", [BaseLanguage.Enum.ZH, BaseLanguage.Enum.EN])
def test_onekey_preparation_reflows_and_preserves_controls(monkeypatch, language) -> None:
    monkeypatch.setattr(Config, "load", lambda self, path=None: self)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", language)
    page = YiJianFanyiPage()
    page.resize(1600, 800)
    page.show()
    APP.processEvents()

    assert page.workspace.width() == 1400
    assert page.workspace.x() == (page.width() - page.workspace.width()) // 2
    assert page.step1_columns.direction() == QBoxLayout.LeftToRight
    assert page.project_card.y() == page.language_card.y()
    assert page.project_card.geometry().right() < page.language_card.x()
    assert page.project_card.isAncestorOf(page.game_path_edit)
    assert page.language_card.isAncestorOf(page.src_lang_combo)
    assert page.language_card.isAncestorOf(page.tgt_lang_combo)
    assert page.language_card.isAncestorOf(page.tl_folder_edit)

    page.resize(680, 740)
    APP.processEvents()
    assert page.workspace.width() == page.width()
    assert page.step1_columns.direction() == QBoxLayout.TopToBottom
    assert page.project_card.geometry().bottom() < page.language_card.y()
    assert page.step1_page.content_scroll.horizontalScrollBar().maximum() == 0
    assert not page.step1_page.content_scroll.isAncestorOf(page.step1_next_btn)
    assert not page.step1_next_btn.visibleRegion().isEmpty()
    assert not page.step1_next_btn.isEnabled()
    assert page.tl_folder_edit.text() == "chinese"
    page.close()
    page.deleteLater()


@pytest.mark.parametrize("language", [BaseLanguage.Enum.ZH, BaseLanguage.Enum.EN])
@pytest.mark.parametrize("width", [1024, 680])
def test_onekey_steps_share_surface_and_keep_progress_contract(monkeypatch, language, width) -> None:
    monkeypatch.setattr(Config, "load", lambda self, path=None: self)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", language)
    page = YiJianFanyiPage()
    page.resize(width, 740)
    page.show()

    for index in range(5):
        page.stacked.setCurrentIndex(index)
        APP.processEvents()
        step = page.stacked.currentWidget()
        surface = step.findChild(QWidget, "onekeySurface")
        step_bar = step.findChild(QWidget, "onekeyStepBar")
        assert surface.isAncestorOf(step_bar)
        assert surface.isAncestorOf(step.content_scroll)
        assert surface.isAncestorOf(step.progress_ring)
        assert surface.isAncestorOf(step.status_label)
        assert surface.isAncestorOf(step.progress_bar)
        assert step_bar.geometry().bottom() < step.content_scroll.y()
        assert not step.progress_bar.visibleRegion().isEmpty()
        assert step.content_scroll.horizontalScrollBar().maximum() == 0

    page.close()
    page.deleteLater()


@pytest.mark.parametrize("language", [BaseLanguage.Enum.ZH, BaseLanguage.Enum.EN])
def test_toolbox_workspace_and_search_reflow(monkeypatch, language) -> None:
    monkeypatch.setattr(Config, "load", lambda self, path=None: self)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", language)
    page = RenpyToolboxPage("renpy_toolbox_page")
    page.resize(1600, 800)
    page.show()
    APP.processEvents()
    page._update_card_widths()

    assert page.workspace.width() == 1400
    assert page.workspace.x() == (page.width() - page.workspace.width()) // 2
    assert page.header_layout.direction() == QBoxLayout.LeftToRight

    page.resize(680, 740)
    APP.processEvents()
    page._update_card_widths()
    APP.processEvents()
    assert page.workspace.width() == 680
    assert page.header_layout.direction() == QBoxLayout.TopToBottom
    header_text = page.header_layout.itemAt(0).widget()
    assert header_text.geometry().bottom() < page.search_edit.y()
    assert page.scroll_area.horizontalScrollBar().maximum() == 0
    page.search_edit.setText("archive")
    APP.processEvents()
    assert [key for key, card in page._cards.items() if card.isVisible()] == ["pack_unpack"]

    page.resize(1600, 800)
    APP.processEvents()
    assert page.header_layout.direction() == QBoxLayout.LeftToRight
    assert page.search_edit.maximumWidth() == 320
    page.close()
    page.deleteLater()


@pytest.mark.parametrize("language", [BaseLanguage.Enum.ZH, BaseLanguage.Enum.EN])
def test_agent_compact_topbar_and_scrolling_empty_state(monkeypatch, language) -> None:
    config = Config()
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Config, "save", lambda self: self)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", language)
    window = QWidget()
    page = AgentPage("agent", window)
    try:
        for width in (1024, 680, 1024):
            window.resize(width, 740)
            page.setGeometry(window.rect())
            window.show()
            APP.processEvents()
            assert page.minimumSizeHint().width() <= width
            widgets = [widget for widget in page._topbar_widgets if widget.isVisible()]
            for index, widget in enumerate(widgets):
                assert page.topbar.rect().contains(widget.geometry())
                assert all(not widget.geometry().intersects(other.geometry()) for other in widgets[index + 1:])
            assert page._topbar_compact == (width < 940)
            assert page.new_task_button.width() >= page.new_task_button.sizeHint().width()

        window.resize(680, 500)
        page.setGeometry(window.rect())
        text = "A long follow-up request\n" * 40
        page.input_box.setPlainText(text)
        QTest.qWait(100)
        assert page.input_box.height() == 160
        assert page.input_box.toPlainText() == text
        assert page.empty_state.suggestions.width() <= 720
        assert len(page.empty_state.suggestion_buttons) == 4
        scroll = page.empty_state.content_scroll
        assert scroll.verticalScrollBar().maximum() > 0
        last_card = page.empty_state.suggestion_buttons[-1]
        scroll.ensureWidgetVisible(last_card)
        QTest.qWait(100)
        assert not last_card.visibleRegion().isEmpty()
        assert not page.send_button.visibleRegion().isEmpty()
        page.input_box.clear()
        assert page.input_box.height() == 64
    finally:
        window.close()
        window.deleteLater()


def test_agent_long_conversation_tools_errors_and_scroll_position(monkeypatch) -> None:
    config = Config()
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    window = QWidget()
    window.resize(680, 740)
    page = AgentPage("agent", window)
    page.setGeometry(window.rect())
    window.show()
    try:
        page._append("Inspect the project", role="user")
        page._append_reply_delta("## Inspection\n\n" + "Long project context.\n\n" * 80)
        page._flush_pending_deltas()
        tool = page._append_tool_start("inspect_translation_project")
        page._finish_tool("inspect_translation_project", True, "Successful detail\n" * 20)
        APP.processEvents()
        assert tool.state == "done"
        assert tool.detail_label.isHidden()
        tool.toggle_button.click()
        assert not tool.detail_label.isHidden()
        failed = page._append_tool_start("scan_script_errors")
        detail = "Long diagnostic content\n" * 150
        page._finish_tool("scan_script_errors", False, detail)
        error = page._append("Long retryable error " * 80, role="error")
        for _ in range(4):
            APP.processEvents()
        assert failed.state == "failed"
        assert failed.detail_label.isVisible()
        assert failed.detail_label.height() <= 360
        assert failed.detail_label.verticalScrollBar().maximum() > 0
        assert failed.detail_label.toolTip() == detail
        assert error.retry_button.isEnabled()
        assert error.geometry().right() <= page.history_content.width()
        assert page.history.horizontalScrollBar().maximum() == 0
        scroll = page.history.verticalScrollBar()
        assert scroll.maximum() > 0
        scroll.setValue(0)
        assert not page._auto_follow
        page._append_reply_delta("More streamed content.\n" * 10)
        page._flush_pending_deltas()
        for _ in range(4):
            APP.processEvents()
        assert scroll.value() == 0
        assert page.scroll_latest_button.isVisible()
        page._scroll_to_latest()
        APP.processEvents()
        assert scroll.value() == scroll.maximum()
    finally:
        window.close()
        window.deleteLater()


@pytest.mark.parametrize("language", [BaseLanguage.Enum.ZH, BaseLanguage.Enum.EN])
def test_workbench_panels_reflow_without_losing_long_content(monkeypatch, language) -> None:
    config = Config()
    character = create_default_character_card("Alice")
    config.renpy_workbench_character_cards = [character]
    config.renpy_workbench_generated_character_drafts = [dict(character, identity="Historian")]
    config.renpy_workbench_worldbook_data = {"setting_summary": "Worldbuilding text\n" * 80}
    monkeypatch.setattr(RenpyWorkbenchPage, "_load_config", lambda self: config)
    monkeypatch.setattr(RenpyWorkbenchPage, "_save_config", lambda self, current: None)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", language)
    window = QWidget()
    page = RenpyWorkbenchPage("workbench", window)
    try:
        for width in (1024, 680, 1024):
            window.resize(width, 740)
            page.setGeometry(window.rect())
            window.show()
            for panel, _title in page.panel_order:
                page.switch_panel(panel)
                APP.processEvents()
                scroll = page.stack.currentWidget().findChild(SingleDirectionScrollArea)
                assert scroll.horizontalScrollBar().maximum() == 0, (width, panel)
            expected_orientation = Qt.Vertical if width < 900 else Qt.Horizontal
            assert page.worldbook_splitter.orientation() == expected_orientation
            assert page.character_splitter.orientation() == expected_orientation
            previews = (page.preview_world_context, page.preview_character_context, page.preview_final_context)
            assert len({view.y() for view in previews}) == (3 if width < 900 else 1)
            assert page.worldbook_widgets["setting_summary"].toPlainText() == ("Worldbuilding text\n" * 80).strip()
            assert all(button.width() >= button.sizeHint().width() for button in page.character_filter_buttons.values())
    finally:
        window.close()
        window.deleteLater()


@pytest.mark.parametrize("theme", [Theme.DARK, Theme.LIGHT])
def test_agent_empty_scroll_surface_matches_theme(monkeypatch, theme) -> None:
    previous_theme = qconfig.theme
    previous_stylesheet = APP.styleSheet()
    monkeypatch.setattr(Config, "load", lambda self, path=None: self)
    state = None
    try:
        setTheme(theme)
        APP.setStyleSheet(ThemeHelper.get_current_stylesheet())
        state = AgentEmptyState(Localizer.get())
        state.resize(680, 500)
        state.show()
        APP.processEvents()
        surface = state.content_scroll.viewport().grab().toImage()
        palette = DARK if theme == Theme.DARK else LIGHT
        assert surface.pixelColor(2, 2).name() == QColor(palette.background).name()
    finally:
        if state is not None:
            state.close()
            state.deleteLater()
        setTheme(previous_theme)
        APP.setStyleSheet(previous_stylesheet)


def test_onekey_step_header_states_and_completed_review(monkeypatch) -> None:
    """步骤头应显示 HTML 状态，并且只允许回看已到达步骤。"""
    monkeypatch.setattr(Config, "load", lambda self, path=None: self)
    page = YiJianFanyiPage()
    page.current_step = 3
    page._max_reached_step = 4
    page._refresh_step_indicators()

    indicators = page._step_indicator_buttons[:5]
    assert [button.property("stepState") for button, _ in indicators] == [
        "done",
        "done",
        "active",
        "done",
        "pending",
    ]
    assert [button.isEnabled() for button, _ in indicators] == [
        True,
        True,
        True,
        True,
        False,
    ]
    page.resize(1024, 740)
    page.show()
    APP.processEvents()
    assert max(button.width() for button, _ in indicators) - min(
        button.width() for button, _ in indicators
    ) <= 1
    assert all(not button.icon().isNull() for button, _ in indicators)
    assert indicators[0][0].text() == Localizer.get().onekey_select_game
    assert indicators[2][0].toolTip().startswith("3.")

    page._on_step_indicator_clicked(2)
    assert page.current_step == 2
    assert page.stacked.currentIndex() == 1
    page.deleteLater()


def test_agent_suggestions_reflow_without_breaking_fixed_width() -> None:
    """建议卡宽屏两列、窄屏单列，容器宽度和四卡片结构保持不变。"""
    state = AgentEmptyState(Localizer.get())
    state.resize(800, 640)
    state.show()
    APP.processEvents()

    assert state.suggestions.width() == 720
    assert len(state.suggestion_buttons) == 4
    wide_x = [card.geometry().x() for card in state.suggestion_buttons]
    assert wide_x[0] != wide_x[1]

    state.resize(500, 640)
    APP.processEvents()
    narrow_x = [card.geometry().x() for card in state.suggestion_buttons]
    assert len(set(narrow_x)) == 1
    state.deleteLater()


def test_agent_workspace_is_centered_without_shrinking_message_contract(monkeypatch) -> None:
    """宽屏 Agent 工作区应居中，同时保留 960px 消息正文宽度。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    window.resize(1600, 900)
    page = AgentPage("agent_page", window)
    page.setGeometry(window.rect())
    window.show()
    APP.processEvents()

    assert page.workspace.width() == 1400
    assert page.workspace.x() == (page.width() - page.workspace.width()) // 2
    assert page.conversation_card.width() == page.workspace.width() - 32
    page.deleteLater()
    window.close()


def test_agent_streaming_appends_without_reparsing_markdown() -> None:
    """流式增量只更新纯文本，完成时才重新解析 Markdown。"""
    widget = AgentMessageWidget("", "assistant")
    markdown_calls = []
    original_set_markdown = widget.text_view.setMarkdown
    widget.text_view.setMarkdown = markdown_calls.append

    widget.set_streaming(True)
    widget.append_stream_text("第一段")
    widget.append_stream_text("第二段")

    assert widget.text == "第一段第二段"
    assert widget.text_view.toPlainText() == "第一段第二段"
    assert markdown_calls == []

    widget.set_text("**完成**")
    assert markdown_calls == ["**完成**"]
    widget.text_view.setMarkdown = original_set_markdown
    widget.deleteLater()


def test_translation_dashboard_uses_html_grid_hierarchy(monkeypatch) -> None:
    """监控页保持 Hero、吞吐、两张指标卡和流水卡的原型层级。"""
    config = Config()
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Config, "save", lambda self: self)

    window = QWidget()
    window.resize(1400, 740)
    page = TranslationPage("translation_page", window)
    page.setGeometry(window.rect())
    window.show()
    APP.processEvents()

    hero = page.findChild(QWidget, "translationProgressCard")
    throughput = page.findChild(QWidget, "translationThroughputCard")
    feed = page.findChild(QWidget, "translationStreamFeedCard")
    footer = page.findChild(QWidget, "translationFooterBar")
    assert hero is not None and throughput is not None and feed is not None and footer is not None
    assert page.workspace.width() == 1400
    assert page.workspace.x() == (page.width() - page.workspace.width()) // 2
    assert hero.width() < throughput.width()
    assert feed.height() >= 168
    assert footer.geometry().bottom() <= page.height()
    assert page.progress_kpi_card.isHidden()
    assert page.speed_kpi_card.isHidden()
    assert page.output_token is page.token
    assert page.output_token.title_label.text() == "输出令牌"
    assert page.input_token.title_label.text() == "输入令牌"
    assert page.feed_items_container.sizePolicy().horizontalPolicy() == page.feed_items_container.sizePolicy().Expanding

    page.deleteLater()
    window.close()


def test_translation_dashboard_renders_runtime_metrics_and_feed(monkeypatch) -> None:
    """监控页展示进度事件中的指标和最近处理条目。"""
    config = Config()
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Config, "save", lambda self: self)

    window = QWidget()
    page = TranslationPage("translation_page", window)
    page.data = {
        "start_time": 0,
        "time": 2,
        "line": 12,
        "total_line": 20,
        "total_output_tokens": 120,
        "total_input_tokens": 80,
        "processed_batches": 3,
        "cache_hit_rate": 0.25,
        "latency_ms": 140.5,
        "recent_items": [{
            "id": "#12",
            "speaker": "Alice",
            "file": "script.rpy:12",
            "source": "Hello",
            "target": "你好",
            "latency_ms": 140.5,
            "status": "TRANSLATED",
        }],
    }
    page._update_dashboard_details()

    assert [label.text() for label in page.throughput_stat_values] == [
        "60.00 T/s",
        "3",
        "25.0%",
        "140.5 ms",
    ]
    assert page.hero_cache_pill.text() == "已有 25.0%"
    assert page.hero_cache_pill.toolTip() == Localizer.get().translation_page_cache_help
    assert not page.feed_empty_label.isVisible()
    assert page.feed_items_layout.count() == 2
    assert page.output_token.detail_label.text() == "累计输出 120"
    assert page.input_token.detail_label.text() == "累计输入 80"

    page.deleteLater()
    window.close()


@pytest.mark.parametrize("language", [BaseLanguage.Enum.ZH, BaseLanguage.Enum.EN])
def test_translation_feed_fills_card_and_wraps_long_text(monkeypatch, language) -> None:
    """有流水时，宽窄切换仍应填满卡片、对齐列并显示完整的换行内容。"""
    config = Config()
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Config, "save", lambda self: self)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", language)
    window = QWidget()
    page = TranslationPage("translation_page", window)
    source = "A long source sentence that must fit its column. " * 8
    target = "这是一段需要随窗口宽度换行的译文，不能覆盖原文列或被截断。" * 5
    page.data = {"recent_items": [
        {"timestamp": "04:03:28", "source": source, "target": target, "status": "TRANSLATED"},
        {"timestamp": "04:03:29", "source": "Take care of yourself, human.", "target": "你自己保重吧，人类。"},
    ]}
    page._refresh_stream_feed()
    try:
        for width in (1400, 680, 1024, 1400):
            window.resize(width, 740)
            page.setGeometry(window.rect())
            window.show()
            QTest.qWait(50)
            assert page.feed_columns_header.width() == page.feed_items_container.width()
            assert page.content_scroll.horizontalScrollBar().maximum() == 0
            for index in range(2):
                row = page.feed_items_layout.itemAt(index).widget()
                assert row.width() == page.feed_items_container.width()
                for column in (1, 2):
                    label = row.layout().itemAt(column).widget()
                    header = page.feed_columns_header.layout().itemAt(column).widget()
                    assert abs(label.x() - header.x()) <= 1
                    assert abs(label.width() - header.width()) <= 1
                    assert label.wordWrap()
                    assert row.height() >= label.heightForWidth(label.width()) + 8
            long_row = page.feed_items_layout.itemAt(1).widget()
            assert long_row.layout().itemAt(1).widget().toolTip() == source
            assert target in long_row.layout().itemAt(2).widget().toolTip()
    finally:
        page.ui_update_timer.stop()
        window.close()
        window.deleteLater()


@pytest.mark.parametrize("language", [BaseLanguage.Enum.ZH, BaseLanguage.Enum.EN])
def test_translation_dashboard_scrolls_and_reflows_in_short_window(monkeypatch, language) -> None:
    """短窗口的监控正文可滚动，速览卡改为两列且不会遮挡流水卡。"""
    config = Config()
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Config, "save", lambda self: self)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", language)
    window = QWidget()
    window.resize(900, 640)
    page = TranslationPage("translation_page", window)
    page.setGeometry(window.rect())
    window.show()
    APP.processEvents()

    hero = page.findChild(QWidget, "translationProgressCard")
    feed = page.findChild(QWidget, "translationStreamFeedCard")
    assert hero is not None and feed is not None
    assert not hero.geometry().intersects(feed.geometry())
    assert page.kpi_layout.rowCount() == 2
    assert page.content_scroll.horizontalScrollBar().maximum() == 0
    assert page.content_scroll.verticalScrollBar().maximum() > 0
    assert page.footer_backup_label.isHidden()
    for width in (1231, 851, 680, 1231):
        window.resize(width, 601)
        page.setGeometry(window.rect())
        QTest.qWait(50)
        bar = page.command_bar_card.command_bar
        for button in (page.action_start, page.action_stop, page.action_continue):
            assert button.isVisible()
            assert button.width() >= button.sizeHint().width()
            assert not button.visibleRegion().isEmpty()
        assert not bar.geometry().intersects(page.footer_backup_label.geometry()) or page.footer_backup_label.isHidden()
    page.deleteLater()
    window.close()


def test_workbench_summary_values_keep_visible_width(monkeypatch) -> None:
    """概览摘要的值可省略长路径，但不能被布局压缩成零宽度。"""
    config = Config()
    config.platforms = []
    monkeypatch.setattr(RenpyWorkbenchPage, "_load_config", lambda self: config)
    monkeypatch.setattr(RenpyWorkbenchPage, "_save_config", lambda self, current: None)
    window = QWidget()
    window.resize(1024, 740)
    page = RenpyWorkbenchPage("workbench", window)
    page.setGeometry(window.rect())
    window.show()
    APP.processEvents()

    assert all(label.text() for label in page.summary_labels.values())
    assert all(label.width() > 0 for label in page.summary_labels.values())
    page.deleteLater()
    window.close()


@pytest.mark.parametrize("page_type", [BasicSettingsPage, AppSettingsPage])
def test_settings_cards_wrap_without_horizontal_scrolling(monkeypatch, page_type) -> None:
    """英文长说明在卡片内换行，不把表单控件推离初始视口。"""
    config = Config()
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Config, "save", lambda self: self)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)
    window = QWidget()
    window.resize(744, 602)
    page = page_type("settings", window)
    page.setGeometry(window.rect())
    window.show()
    APP.processEvents()

    scroll = page.findChild(SingleDirectionScrollArea)
    assert scroll is not None
    assert scroll.horizontalScrollBar().maximum() == 0
    page.deleteLater()
    window.close()


@pytest.mark.parametrize("language", [BaseLanguage.Enum.ZH, BaseLanguage.Enum.EN])
def test_project_path_description_wraps_and_keeps_full_path(monkeypatch, language) -> None:
    """长目录可换行显示，悬停仍可获得未截断的完整路径。"""
    config = Config()
    config.input_folder = "D:/Games/" + "TranslationWorkspace/" * 5 + "game/tl/chinese"
    config.output_folder = config.input_folder + "/output"
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Config, "save", lambda self: self)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", language)
    window = QWidget()
    page = ProjectPage("project", window)
    window.show()
    for width, height in ((1024, 740), (851, 601), (680, 500), (1024, 740)):
        window.resize(width, height)
        page.setGeometry(window.rect())
        QTest.qWait(50)
        assert page.content_scroll.horizontalScrollBar().maximum() == 0
        for card, path in (
            (page.input_folder_card, config.input_folder),
            (page.output_folder_card, config.output_folder),
        ):
            label = card.get_description_label()
            assert label.wordWrap()
            assert label.toolTip() == path
            assert label.height() >= label.heightForWidth(label.width())
            page.content_scroll.ensureWidgetVisible(card)
            QTest.qWait(30)
            assert not card.get_push_button().visibleRegion().isEmpty()
    page.deleteLater()
    window.close()


@pytest.mark.parametrize("page_type", [TranslationPage, ProjectPage])
@pytest.mark.parametrize("initial_theme", [Theme.DARK, Theme.LIGHT])
def test_scrolling_pages_keep_theme_background_after_switch(monkeypatch, page_type, initial_theme) -> None:
    """滚动正文在明暗主题往返切换后仍使用页面底色。"""
    config = Config()
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Config, "save", lambda self: self)
    previous_theme, previous_style = qconfig.theme, APP.styleSheet()
    window = QWidget()
    try:
        setTheme(initial_theme)
        APP.setStyleSheet(ThemeHelper.get_current_stylesheet())
        window.resize(851, 601)
        page = page_type("theme_review", window)
        page.setGeometry(window.rect())
        window.show()
        for theme in (initial_theme, Theme.LIGHT, Theme.DARK):
            setTheme(theme)
            APP.setStyleSheet(ThemeHelper.get_current_stylesheet())
            QTest.qWait(50)
            palette = DARK if theme == Theme.DARK else LIGHT
            surface = page.content_scroll.widget().grab().toImage()
            assert surface.pixelColor(1, 1).name() == QColor(palette.background).name()
    finally:
        window.close()
        window.deleteLater()
        setTheme(previous_theme)
        APP.setStyleSheet(previous_style)


def test_proofreading_cache_errors_follow_the_selected_language(monkeypatch) -> None:
    """缓存异常不泄露路径，同时使用当前界面的语言。"""
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)
    assert ProofreadingPage._cache_load_error_message(FileNotFoundError()) == (
        Localizer.get().proofreading_page_cache_access_denied
    )


@pytest.mark.parametrize("language", [BaseLanguage.Enum.ZH, BaseLanguage.Enum.EN])
def test_translation_dashboard_localizes_live_metrics(monkeypatch, language) -> None:
    config = Config()
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Config, "save", lambda self: self)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", language)
    monkeypatch.setattr(Engine.get(), "get_status", lambda: Engine.Status.IDLE)
    page = TranslationPage("translation_page", QWidget())
    try:
        strings = Localizer.get()
        assert page.progress_kpi_card.title_label.text() == strings.translation_page_kpi_progress
        assert page.speed_kpi_card.title_label.text() == strings.translation_page_kpi_throughput
        monkeypatch.setattr(Localizer, "localize", lambda *args: pytest.fail("Live metrics must use locale fields"))
        page.data = {
            "time": 20, "line": 25, "total_line": 100,
            "total_output_tokens": 400, "cached_line_count": 10,
        }
        page._peak_speed = 24.0
        page._update_dashboard_details()
        assert page.progress_kpi_card.value_label.text() == "25.0%"
        assert page.progress_kpi_card.detail_label.text() == strings.translation_page_lines_detail.format(LINE=25, TOTAL=100)
        assert page.speed_kpi_card.trend_label.text() == strings.translation_page_trend_live
        assert page.speed_kpi_card.detail_label.text() == strings.translation_page_peak_speed.format(SPEED="24.00")
        assert page.token.trend_label.text() == strings.translation_page_trend_total
        assert page.task.trend_label.text() == strings.translation_page_trend_healthy
        assert page.hero_translated_pill.text() == strings.translation_page_translated_percent.format(PERCENT=25)
        assert page.hero_pending_pill.text() == strings.translation_page_pending_percent.format(PERCENT=75)
        assert page.hero_cache_pill.text() == strings.translation_page_cache_percent.format(PERCENT=10)
        page.data = {}
        page._update_dashboard_details()
        assert page.speed_kpi_card.trend_label.text() == strings.translation_page_trend_idle
        assert page.hero_cache_pill.text() == strings.translation_page_cache_unavailable
    finally:
        page.close()
        page.deleteLater()


def test_proofreading_inline_search_keeps_command_bar_visible() -> None:
    """常驻搜索应直接定位条目，不再切换到第二套搜索工具栏。"""
    window = QWidget()
    window.resize(1400, 740)
    page = ProofreadingPage("proofreading_page", window)
    page.setGeometry(window.rect())
    page.items = [CacheItem(src="source needle", dst="译文")]
    page.filtered_items = list(page.items)
    page.table_widget.set_items(page.items, {})
    page.pagination_bar.set_total(1)
    page.inline_search_edit.setText("needle")
    window.show()
    APP.processEvents()

    page._on_inline_search_submitted()

    assert page.search_current_match == 0
    assert page.search_card.isHidden()
    assert page.command_bar_card.isVisible()
    page.deleteLater()
    window.close()


def test_workbench_prompt_preview_uses_three_columns(monkeypatch) -> None:
    """宽屏提示词预览应并列展示世界观、角色和最终上下文。"""
    config = Config()
    monkeypatch.setattr(RenpyWorkbenchPage, "_load_config", lambda self: config)
    monkeypatch.setattr(
        RenpyWorkbenchPage,
        "_save_config",
        lambda self, current: None,
    )
    window = QWidget()
    window.resize(1024, 740)
    page = RenpyWorkbenchPage("renpy_workbench_page", window)
    page.setGeometry(window.rect())
    page.switch_panel("preview")
    window.show()
    APP.processEvents()

    previews = (
        page.preview_world_context,
        page.preview_character_context,
        page.preview_final_context,
    )
    assert page.workspace.width() == 1024
    assert page.workspace.x() == (page.width() - page.workspace.width()) // 2
    assert len({widget.y() for widget in previews}) == 1
    assert previews[0].x() < previews[1].x() < previews[2].x()
    page.deleteLater()
    window.close()


@pytest.mark.parametrize(
    ("theme", "palette", "expected_alpha"),
    [
        (Theme.DARK, DARK, 28),
        (Theme.LIGHT, LIGHT, 18),
    ],
)
def test_platform_active_surface_uses_subtle_accent(theme, palette, expected_alpha) -> None:
    """接口激活态应为弱主题色表面，而不是整张实心主按钮色。"""
    previous_theme = qconfig.theme
    try:
        setTheme(theme)
        background = ThemeHelper.get_theme_active_card_background_color()
        foreground = ThemeHelper.get_theme_active_card_foreground_color()

        assert background.alpha() == expected_alpha
        assert background.name() == ThemeColor.PRIMARY.color().name()
        assert foreground.name() == QColor(palette.text_primary).name()
    finally:
        setTheme(previous_theme)
