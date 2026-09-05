import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QWidget

from frontend.Agent.AgentPage import AgentEmptyState
from frontend.Proofreading.ProofreadingPage import ProofreadingPage
from frontend.RenpyToolbox.OneKeyTranslatePage import YiJianFanyiPage
from frontend.TranslationPage import TranslationPage
from frontend.Workbench.RenpyWorkbenchPage import RenpyWorkbenchPage
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Localizer.Localizer import Localizer
from widget import ThemeHelper


APP = QApplication.instance() or QApplication([])


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

    assert state.suggestions.width() == 560
    assert len(state.suggestion_buttons) == 4
    wide_x = [card.geometry().x() for card in state.suggestion_buttons]
    assert wide_x[0] != wide_x[1]

    state.resize(500, 640)
    APP.processEvents()
    narrow_x = [card.geometry().x() for card in state.suggestion_buttons]
    assert len(set(narrow_x)) == 1
    state.deleteLater()


def test_translation_dashboard_uses_html_grid_hierarchy(monkeypatch) -> None:
    """监控页保持 Hero、吞吐、两张指标卡和流水卡的原型层级。"""
    config = Config()
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(Config, "save", lambda self: self)

    window = QWidget()
    window.resize(1024, 740)
    page = TranslationPage("translation_page", window)
    page.setGeometry(window.rect())
    window.show()
    APP.processEvents()

    hero = page.findChild(QWidget, "translationProgressCard")
    throughput = page.findChild(QWidget, "translationThroughputCard")
    feed = page.findChild(QWidget, "translationStreamFeedCard")
    footer = page.findChild(QWidget, "translationFooterBar")
    assert hero is not None and throughput is not None and feed is not None and footer is not None
    assert hero.width() < throughput.width()
    assert feed.height() <= 190
    assert footer.geometry().bottom() <= page.height()

    page.deleteLater()
    window.close()


def test_proofreading_inline_search_keeps_command_bar_visible() -> None:
    """常驻搜索应直接定位条目，不再切换到第二套搜索工具栏。"""
    window = QWidget()
    window.resize(1024, 740)
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
    assert len({widget.y() for widget in previews}) == 1
    assert previews[0].x() < previews[1].x() < previews[2].x()
    page.deleteLater()
    window.close()


def test_platform_active_surface_uses_subtle_accent(monkeypatch) -> None:
    """接口激活态应为弱主题色表面，而不是整张实心主按钮色。"""
    monkeypatch.setattr(ThemeHelper, "isDarkTheme", lambda: True)
    dark_background = ThemeHelper.get_theme_active_card_background_color()
    dark_foreground = ThemeHelper.get_theme_active_card_foreground_color()
    assert 0 < dark_background.alpha() < 64
    assert dark_foreground.name().upper() == "#F8FAFC"

    monkeypatch.setattr(ThemeHelper, "isDarkTheme", lambda: False)
    light_background = ThemeHelper.get_theme_active_card_background_color()
    light_foreground = ThemeHelper.get_theme_active_card_foreground_color()
    assert 0 < light_background.alpha() < 64
    assert light_foreground.name().upper() == "#0F172A"
