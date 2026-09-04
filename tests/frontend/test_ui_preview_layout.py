import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from frontend.Agent.AgentPage import AgentEmptyState
from frontend.RenpyToolbox.OneKeyTranslatePage import YiJianFanyiPage
from module.Config import Config
from module.Localizer.Localizer import Localizer


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
