import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtGui import QTextLength, QTextTable
from PyQt5.QtWidgets import QApplication, QWidget

from base.Base import Base
from frontend.Agent.AgentPage import (
    AgentErrorWidget,
    AgentMessageWidget,
    AgentPage,
    AgentRoundHeader,
    AgentThinkingWidget,
    AgentToolWidget,
    format_elapsed,
    status_color,
)
from frontend.Agent.AgentWorker import AgentWorker
from module.Agent.AgentService import AgentService
from module.Config import Config
from module.Localizer.Localizer import Localizer
from base.BaseLanguage import BaseLanguage


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


def test_agent_page_restores_saves_and_sends_thinking_level(monkeypatch) -> None:
    config = Config()
    config.agent_platform = 1
    config.agent_thinking_level = "HIGH"
    config.platforms = [
        {
            "id": 1,
            "name": "OpenAI",
            "api_format": Base.APIFormat.OPENAI,
            "model": "gpt-5",
        },
    ]
    saved = []
    config.save = lambda: saved.append(config.agent_thinking_level) or config
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(AgentWorker, "start", lambda self: None)

    window = QWidget()
    page = AgentPage("agent_page", window)

    assert page.thinking_combo.currentData() == "HIGH"
    page.thinking_combo.setCurrentIndex(page.thinking_combo.findData("LOW"))
    assert config.agent_thinking_level == "LOW"
    assert saved == ["LOW"]

    page.input_box.setPlainText("检查项目")
    page.send_message()
    assert page._worker is not None
    assert page._worker.thinking_level == "LOW"

    page._worker.deleteLater()
    page._worker = None
    page.deleteLater()
    window.deleteLater()


def test_agent_page_can_select_real_platform_zero(monkeypatch) -> None:
    config = Config(agent_platform=-1)
    config.platforms = [{
        "id": 0,
        "name": "OpenAI",
        "api_format": Base.APIFormat.OPENAI,
        "model": "gpt-test",
    }]
    config.save = lambda: config
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)

    assert page.platform_combo.itemData(0) == -1
    assert page.platform_combo.itemData(1) == 0
    page.platform_combo.setCurrentIndex(1)
    page.input_box.setPlainText("检查项目")
    assert config.agent_platform == 0
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


def test_agent_page_keeps_structured_tool_details(monkeypatch) -> None:
    config = Config(agent_platform=-1)
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    window = QWidget()
    page = AgentPage("agent_page", window)

    page._on_worker_event("tool_start", {"name": "scan_script_errors"})
    page._on_worker_event(
        "tool_done",
        {
            "name": "scan_script_errors",
            "success": True,
            "message": "发现 1 个错误",
            "data": {"errors": {"script.rpy": [{"line": 3}]}},
        },
    )

    detail = page.history_widgets[0].detail_label.text()
    assert "script.rpy" in detail
    assert '"line": 3' in detail
    page.deleteLater()
    window.deleteLater()


def test_agent_worker_cancel_resolves_pending_confirmation() -> None:
    service = AgentService(confirmation_timeout=1)
    worker = AgentWorker(service, "解包")
    worker.confirmation_requested.connect(lambda _name, _payload: worker.cancel())

    approved = worker._request_confirmation("unpack_rpa_files", {})

    assert approved is False


def test_agent_worker_cancel_before_confirmation_returns_immediately() -> None:
    service = AgentService(confirmation_timeout=1)
    worker = AgentWorker(service, "解包")
    worker.cancel()

    assert worker._request_confirmation("unpack_rpa_files", {}) is False


def test_agent_worker_confirmation_timeout_returns_none() -> None:
    service = AgentService(confirmation_timeout=0.01)
    worker = AgentWorker(service, "解包")

    assert worker._request_confirmation("unpack_rpa_files", {}) is None


def test_agent_unpack_confirmation_is_bilingual() -> None:
    original = Localizer.get_app_language()
    try:
        Localizer.set_app_language(BaseLanguage.Enum.ZH)
        zh = Localizer.get().agent_page_unpack_confirmation.format(game_dir="E:/Game/game", count=2)
        Localizer.set_app_language(BaseLanguage.Enum.EN)
        en = Localizer.get().agent_page_unpack_confirmation.format(game_dir="E:/Game/game", count=2)
    finally:
        Localizer.set_app_language(original)

    assert "覆盖" in zh
    assert "overwrite" in en
    assert "E:/Game/game" in zh and "E:/Game/game" in en


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
    page._service.messages = [{"role": "user", "content": "旧任务"}]
    assert len(page.history_widgets) == 2
    assert page.conversation_stack.currentWidget() is page.history

    page.start_new_task()
    assert page.history_widgets == []
    assert page._service.messages == []
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


def test_agent_page_folds_intermediate_text_under_one_assistant_turn(monkeypatch) -> None:
    """工具前的普通说明只进折叠过程，不应和最终答案重复显示。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)

    page._on_worker_event("request", {"iteration": 1})
    page._on_worker_event(
        "reply_delta",
        {"text": "The model is preparing a tool call.我来读取当前项目。"},
    )
    page._on_worker_event("tool_start", {"name": "get_project_info"})
    page._on_worker_event(
        "tool_done",
        {"name": "get_project_info", "success": True, "message": "项目已读取"},
    )
    page._on_worker_event("request", {"iteration": 2})
    page._on_worker_event("reply_delta", {"text": "正在整理结果。"})
    page._on_worker_event("reply", {"message": "项目检查完成。"})

    assert len(page.history_widgets) == 1
    turn = page.history_widgets[0]
    assert isinstance(turn, AgentMessageWidget)
    assert turn.text_view.toPlainText() == "项目检查完成。"
    thinking = turn.findChildren(AgentThinkingWidget)
    assert len(thinking) == 1
    assert all(not item.detail_label.isVisible() for item in thinking)
    assert any("The model" in item.detail_label.text() for item in thinking)
    assert any(
        item.tool_name == "get_project_info"
        for item in turn.findChildren(AgentToolWidget)
    )

    page.deleteLater()
    window.deleteLater()


def test_agent_page_keeps_reasoning_delta_in_thinking_process(monkeypatch) -> None:
    """模型明确返回的思考增量应折叠保留，不得混入最终回答。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)

    page._on_worker_event("reasoning_delta", {"text": "先分析项目结构。"})
    turn = page.history_widgets[0]
    assert isinstance(turn, AgentMessageWidget)
    assert turn.text == ""

    page._on_worker_event("reply_delta", {"text": "正在生成结论。"})
    page._on_worker_event("reply", {"message": "检查完成。"})

    assert turn.text_view.toPlainText() == "检查完成。"
    thinking = turn.findChildren(AgentThinkingWidget)
    assert len(thinking) == 1
    assert thinking[0].detail_label.text() == "先分析项目结构。"
    assert not thinking[0].detail_label.isVisible()

    page.deleteLater()
    window.deleteLater()


def test_agent_markdown_table_uses_readable_full_width_layout() -> None:
    message = AgentMessageWidget(
        "| 文件 |\n| --- |\n| `audio.rpa` |\n| `script.rpa` |",
        "assistant",
    )

    tables = [
        frame
        for frame in message.text_view.document().rootFrame().childFrames()
        if isinstance(frame, QTextTable)
    ]
    assert len(tables) == 1
    table_format = tables[0].format()
    assert table_format.width().type() == QTextLength.PercentageLength
    assert table_format.width().rawValue() == 100
    assert table_format.borderCollapse()
    assert table_format.cellSpacing() == 0
    assert table_format.cellPadding() == 7

    message.deleteLater()


def test_agent_page_content_width_and_markdown_height_follow_layout(monkeypatch) -> None:
    """宽屏正文使用主要列宽，长 Markdown 由外层滚动区承载。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    window.resize(1600, 900)
    page = AgentPage("agent_page", window)
    page.resize(1550, 820)
    message = page._append("\n\n".join(f"第 {i} 行" for i in range(1, 61)), role="assistant")
    window.show()
    APP.processEvents()

    assert page.history_content.width() >= 1000
    assert message.text_view.maximumHeight() > 1000
    assert message.text_view.height() >= 600

    page.deleteLater()
    window.deleteLater()
