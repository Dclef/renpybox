import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QWidget

from base.Base import Base
from frontend.Agent.AgentPage import (
    AgentErrorWidget,
    AgentMessageWidget,
    AgentPage,
    AgentRoundHeader,
    AgentToolWidget,
    format_elapsed,
    status_color,
)
from module.Config import Config


APP = QApplication.instance() or QApplication([])


def test_agent_page_filters_unsupported_platforms_and_saves_selection(monkeypatch) -> None:
    config = Config()
    config.agent_platform = 0
    config.platforms = [
        {
            "id": 1,
            "name": "OpenAI",
            "api_format": Base.APIFormat.OPENAI,
            "model": "gpt-test",
        },
        {
            "id": 2,
            "name": "DeepL",
            "api_format": Base.APIFormat.DEEPL,
            "model": "deepl",
        },
    ]
    saved = []
    config.save = lambda: saved.append(config) or config
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)

    assert page.platform_combo.count() == 2
    assert page.platform_combo.itemData(1) == 1
    page.input_box.setPlainText("查看项目")
    assert not page.send_button.isEnabled()
    page.platform_combo.setCurrentIndex(1)
    assert config.agent_platform == 1
    assert saved
    assert page.send_button.isEnabled()

    page.deleteLater()
    window.deleteLater()


def test_agent_page_merges_tool_start_and_result(monkeypatch) -> None:
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)

    assert page.empty_state.title_label.text()
    assert page.empty_state.description_label.text()
    assert all(button.text() for button in page.empty_state.suggestion_buttons)

    page._on_worker_event("tool_start", {"name": "get_project_info"})
    assert len(page.history_widgets) == 1
    tool_widget = page.history_widgets[0]
    assert isinstance(tool_widget, AgentToolWidget)
    assert tool_widget.state == "running"

    page._on_worker_event(
        "tool_done",
        {
            "name": "get_project_info",
            "success": True,
            "message": "已识别当前项目",
        },
    )
    assert len(page.history_widgets) == 1
    assert tool_widget.state == "done"
    assert tool_widget.detail_label.text() == "已识别当前项目"
    assert tool_widget.toggle_button.isEnabled()
    tool_widget.toggle_button.click()
    assert not tool_widget.detail_label.isHidden()

    page.deleteLater()
    window.deleteLater()


def test_agent_page_uses_explicit_message_role(monkeypatch) -> None:
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)

    user_message = page._append("没有任何角色前缀", role="user")
    error_message = page._append("This text is not localized", role="error")

    assert isinstance(user_message, AgentMessageWidget)
    # 错误走独立的单行错误条，不再是普通消息气泡。
    assert isinstance(error_message, AgentErrorWidget)
    assert user_message.role == "user"
    assert error_message.role == "error"
    assert [widget.role for widget in page.history_widgets] == ["user", "error"]

    page.deleteLater()
    window.deleteLater()


def test_status_color_distinguishes_success_and_failure() -> None:
    """成功与失败必须是不同色相；用主色深浅变体会让两者无法分辨。"""
    running = status_color("running")
    done = status_color("done")
    failed = status_color("failed")

    assert done.name() != failed.name()
    assert done.name() != running.name()
    # 绿色的绿通道应压过红通道，红色相反。
    assert done.green() > done.red()
    assert failed.red() > failed.green()


def test_format_elapsed_compact_units() -> None:
    assert format_elapsed(0) == "0s"
    assert format_elapsed(9.7) == "9s"
    assert format_elapsed(65) == "1m 05s"
    assert format_elapsed(3725) == "1h 02m 05s"


def test_agent_page_round_header_freezes_after_finish(monkeypatch) -> None:
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)

    header = AgentRoundHeader(page)
    assert header._running
    header.stop()
    assert not header._running
    assert not header._timer.isActive()
    frozen = header.elapsed_label.text()
    header._tick()
    assert header.elapsed_label.text() == frozen

    page.deleteLater()
    window.deleteLater()


def test_agent_page_new_task_clears_conversation(monkeypatch) -> None:
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)

    page._append("第一条", role="user")
    page._append("回复", role="assistant")
    assert len(page.history_widgets) == 2
    assert page.conversation_stack.currentWidget() is page.history

    page.start_new_task()
    assert page.history_widgets == []
    assert page.conversation_stack.currentWidget() is page.empty_state

    page.deleteLater()
    window.deleteLater()


def test_agent_page_error_widget_offers_retry(monkeypatch) -> None:
    """错误条必须能把上一条用户消息填回输入框，不让用户重打。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)

    page._last_message = "帮我看看项目"
    error_widget = page._append("Agent 请求失败，请检查接口配置。", role="error")
    assert isinstance(error_widget, AgentErrorWidget)
    # 单行高度，不能像 TextBrowser 那样为一行字撑出大片空白。
    assert error_widget.height() <= 40
    assert error_widget.retry_button.isEnabled()

    error_widget.retry_button.click()
    assert page.input_box.toPlainText() == "帮我看看项目"

    page.deleteLater()
    window.deleteLater()


def test_agent_page_respects_manual_scroll(monkeypatch) -> None:
    """用户主动上滚后新消息不得抢回滚动位置。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)

    bar = page.history.verticalScrollBar()
    bar.setRange(0, 1000)
    bar.setValue(0)
    page._on_history_scrolled()
    assert not page._auto_follow

    page._scroll_history_to_bottom()
    assert bar.value() == 0

    bar.setValue(1000)
    page._on_history_scrolled()
    assert page._auto_follow

    page.deleteLater()
    window.deleteLater()
