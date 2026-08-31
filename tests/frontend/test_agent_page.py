import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette, QTextLength, QTextTable
from PyQt5.QtWidgets import QApplication, QSizePolicy, QWidget

from base.Base import Base
from frontend.Agent.AgentPage import (
    ACTION_LIST_RPA,
    ACTION_ONE_KEY_TRANSLATE,
    ACTION_OPEN_TRANSLATION,
    ACTION_SCAN_ERRORS,
    ACTION_UNPACK_RPA,
    CONVERSATION_MAX_WIDTH,
    AgentAvatar,
    AgentEmptyState,
    AgentErrorWidget,
    AgentMessageWidget,
    AgentPage,
    AgentRoundHeader,
    AgentThinkingWidget,
    AgentToolWidget,
    clean_agent_display_text,
    format_elapsed,
    status_color,
)
from qfluentwidgets import (
    FluentIcon,
    PrimaryPushButton,
    Theme,
    ThemeColor,
    qconfig,
    setTheme,
    setThemeColor,
)
from frontend.Agent.AgentWorker import AgentWorker
from module.Agent.AgentService import AgentService
from module.Config import Config
from module.Localizer.Localizer import Localizer
from base.BaseLanguage import BaseLanguage
from module.Renpy.ProjectPaths import RenpyProjectPaths


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


def test_agent_page_treats_malformed_platform_ids_as_unset(monkeypatch) -> None:
    """配置被手工改坏时，页面仍能打开并忽略非法接口编号。"""
    config = Config(agent_platform="invalid")
    config.platforms = [
        {"id": "broken", "name": "坏配置", "api_format": Base.APIFormat.OPENAI},
        {"id": 3, "name": "OpenAI", "api_format": Base.APIFormat.OPENAI},
    ]
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)

    assert page.platform_combo.itemData(0) == -1
    assert page.platform_combo.count() == 2
    assert page.platform_combo.itemData(1) == 3

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
    assert tool_widget.detail_label.toPlainText() == "已识别当前项目"
    assert tool_widget.toggle_button.isEnabled()
    assert page.activity_widget.label.text() == Localizer.get().agent_page_running
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

    detail = page.history_widgets[0].detail_label.toPlainText()
    assert "script.rpy" in detail
    assert '"line": 3' in detail
    page.deleteLater()
    window.deleteLater()


def test_agent_worker_does_not_shadow_qthread_internal_signals() -> None:
    """worker 曾用 event/finished 覆盖 QThread 内建信号，线程对象销毁时崩溃。"""
    assert "event" not in AgentWorker.__dict__
    assert "finished" not in AgentWorker.__dict__
    worker = AgentWorker(AgentService(confirmation_timeout=1), "检查项目")
    # 结果信号走 completed，原生 finished 仍可用于安全的 deleteLater。
    assert worker.agent_event is not None
    assert worker.completed is not None
    assert not worker.isFinished()


def test_agent_worker_auto_confirms_unpack_without_dialog() -> None:
    """自动确认只放行一次解包，不能授权同一 Worker 重复执行。"""
    emitted = []
    worker = AgentWorker(
        AgentService(confirmation_timeout=1),
        "解包",
        auto_confirm_unpack=True,
    )
    worker.confirmation_requested.connect(lambda n, p: emitted.append(n))

    assert worker._request_confirmation("unpack_rpa_files", {}) is True
    assert emitted == []
    assert worker._auto_confirm_unpack is False

    # 未开启时仍走确认流程。
    manual = AgentWorker(AgentService(confirmation_timeout=1), "解包")
    manual.confirmation_requested.connect(
        lambda n, p: emitted.append(n) or manual.resolve_confirmation(False)
    )
    assert manual._request_confirmation("unpack_rpa_files", {}) is False
    assert emitted == ["unpack_rpa_files"]


def test_agent_page_unpack_dont_ask_checkbox_saves_config(monkeypatch) -> None:
    """确认框勾选「不再询问」并确认后，配置写入自动放行开关。"""
    from qfluentwidgets import CheckBox as QCheckBox

    config = Config()
    config.agent_platform = 0
    config.platforms = []
    saved = []
    config.save = lambda: saved.append(True) or config
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    class FakeWorker:
        def resolve_confirmation(self, approved):
            self.approved = approved

    window = QWidget()
    page = AgentPage("agent_page", window)
    worker = FakeWorker()
    page._worker = worker
    page._on_confirmation_requested(
        "unpack_rpa_files",
        {"data": {"game_dir": "E:/Game/game", "count": 2}},
    )
    dialog = page._confirmation_dialog
    assert dialog is not None
    checkboxes = dialog.findChildren(QCheckBox)
    assert checkboxes
    checkboxes[0].setChecked(True)
    dialog.accept()
    # 对话框带 100ms 淡出动画，accepted 信号在动画结束后才发出。
    import time as _time
    for _ in range(20):
        APP.processEvents()
        if page._confirmation_dialog is None:
            break
        _time.sleep(0.02)

    assert config.agent_unpack_auto_confirm is True
    assert saved
    assert worker.approved is True

    page._worker = None
    page.deleteLater()
    window.deleteLater()


def test_agent_page_settings_unpack_confirm_switch_controls_flag(monkeypatch) -> None:
    """设置弹层里的「解包前确认」开关应反向写入自动放行配置。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    saved = []
    config.save = lambda: saved.append(True) or config
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)

    assert page.unpack_confirm_check.isChecked() is True
    page.unpack_confirm_check.setChecked(False)
    assert config.agent_unpack_auto_confirm is True
    assert saved

    page.unpack_confirm_check.setChecked(True)
    assert config.agent_unpack_auto_confirm is False

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


def test_agent_old_new_confirmation_is_bilingual() -> None:
    original = Localizer.get_app_language()
    try:
        Localizer.set_app_language(BaseLanguage.Enum.ZH)
        zh = Localizer.get().agent_page_old_new_confirmation.format(
            old_new_count=12,
            supplement_count=2,
            total_count=14,
            conflict_count=1,
            tl_dir="E:/Game/game/tl/chinese",
            output_path="E:/Game/game/tl/chinese/replace_text_auto.rpy",
        )
        Localizer.set_app_language(BaseLanguage.Enum.EN)
        en = Localizer.get().agent_page_old_new_confirmation.format(
            old_new_count=12,
            supplement_count=2,
            total_count=14,
            conflict_count=1,
            tl_dir="E:/Game/game/tl/chinese",
            output_path="E:/Game/game/tl/chinese/replace_text_auto.rpy",
        )
    finally:
        Localizer.set_app_language(original)

    assert "从长到短" in zh
    assert "longest" in en
    assert "14" in zh and "14" in en
    assert "冲突" in zh and "Conflicting" in en
    assert "replace_text_auto.rpy" in zh and "replace_text_auto.rpy" in en


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


def test_status_color_follows_current_theme_color() -> None:
    """运行与完成状态跟随主题色，只有失败保留红色语义色。"""
    original_theme = qconfig.theme
    original_color = QColor(qconfig.get(qconfig.themeColor))
    try:
        setTheme(Theme.LIGHT)
        setThemeColor("#336699")

        running = status_color("running")
        done = status_color("done")
        failed = status_color("failed")

        assert running.name() == ThemeColor.PRIMARY.color().name()
        assert done.name() == ThemeColor.DARK_1.color().name()
        assert done.name() != running.name()
        assert done.name() != failed.name()
        assert failed.red() > failed.green()
    finally:
        setTheme(original_theme)
        setThemeColor(original_color)


def test_agent_avatar_uses_inverse_black_and_white_badge() -> None:
    """机器人头像使用黑白反相圆底，不得被绿色等强调色染色。"""
    original_theme = qconfig.theme
    original_color = QColor(qconfig.get(qconfig.themeColor))
    avatar = None
    try:
        setThemeColor("#00aa55")
        setTheme(Theme.LIGHT)
        avatar = AgentAvatar("assistant")
        avatar.refresh_theme()
        assert avatar._background().name() == "#000000"
        assert avatar._icon_color().name() == "#ffffff"
        assert avatar._background().name() != ThemeColor.PRIMARY.color().name()

        setTheme(Theme.DARK)
        avatar.refresh_theme()
        assert avatar._background().name() == "#ffffff"
        assert avatar._icon_color().name() == "#000000"
        assert avatar._background().name() != ThemeColor.PRIMARY.color().name()
    finally:
        if avatar is not None:
            avatar.deleteLater()
        setTheme(original_theme)
        setThemeColor(original_color)


def test_agent_page_refreshes_tool_cards_after_theme_color_change(monkeypatch) -> None:
    """切换主题色后，已经显示的过程卡和完成状态也要立即刷新。"""
    original_theme = qconfig.theme
    original_color = QColor(qconfig.get(qconfig.themeColor))
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    page = None
    window = None
    try:
        setTheme(Theme.LIGHT)
        setThemeColor("#336699")
        window = QWidget()
        page = AgentPage("agent_page", window)
        page._ensure_assistant_turn()
        tool = page._append_tool_start("get_project_info")
        tool.complete(True, "项目读取完成")

        initial_done = tool.status_dot._color.name()
        initial_surface = tool._normalBackgroundColor()
        assert initial_surface.getRgb() == (51, 102, 153, 20)

        setThemeColor("#AA5500")
        APP.processEvents()

        refreshed_surface = tool._normalBackgroundColor()
        assert tool.status_dot._color.name() == ThemeColor.DARK_1.color().name()
        assert tool.status_dot._color.name() != initial_done
        assert refreshed_surface.getRgb() == (170, 85, 0, 20)
        assert "rgba(170,85,0,46)" in tool.detail_label.styleSheet()
        assert "color: #1a1a1a" in tool.detail_label.styleSheet()

        setTheme(Theme.DARK)
        APP.processEvents()

        assert tool._normalBackgroundColor().getRgb() == (0, 0, 0, 30)
        assert tool.status_dot._color.name() == ThemeColor.DARK_1.color().name()
        assert "background-color: rgba(0,0,0,0.28)" in tool.detail_label.styleSheet()
        assert "color: #e6e6e6" in tool.detail_label.styleSheet()
    finally:
        setTheme(original_theme)
        setThemeColor(original_color)
        if page is not None:
            page.deleteLater()
        if window is not None:
            window.deleteLater()


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


def test_agent_page_offers_return_to_latest_after_manual_scroll(monkeypatch) -> None:
    """用户上滚查看旧消息时，应能一键恢复自动跟随。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)
    page._append("历史消息", role="assistant")

    bar = page.history.verticalScrollBar()
    bar.setRange(0, 1000)
    bar.setValue(0)
    page._on_history_scrolled()

    assert not page._auto_follow
    assert not page.scroll_latest_button.isHidden()

    page._scroll_to_latest()

    assert page._auto_follow
    assert page.scroll_latest_button.isHidden()

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
    assert any("The model" in item.detail_label.toPlainText() for item in thinking)
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
    assert thinking[0].detail_label.toPlainText() == "先分析项目结构。"
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

    assert page.history_content.width() == CONVERSATION_MAX_WIDTH
    assert message.text_view.maximumHeight() > 1000
    assert message.text_view.height() >= 600

    page.deleteLater()
    window.deleteLater()


def test_agent_page_batches_streaming_deltas_until_flush(monkeypatch) -> None:
    """流式增量应合并渲染：未 flush 前不触发 setMarkdown 重排。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)

    page._on_worker_event("request", {"iteration": 1})
    page._append_reply_delta("第一")
    page._append_reply_delta("段")
    turn = page._assistant_turn
    assert turn is not None
    assert turn.text == ""

    page._flush_pending_deltas()
    assert turn.text == "第一段"
    assert turn.text_view.toPlainText() == "第一段"
    assert page._pending_reply_text == ""

    page.deleteLater()
    window.deleteLater()


def test_agent_page_adapts_stream_render_interval_to_reply_size(monkeypatch) -> None:
    """长回复降低重排频率，短回复保持 50ms 的即时反馈。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)

    page._append_reply_delta("x" * 5_000)
    assert page._render_timer.interval() == 80
    page._render_timer.stop()
    page._pending_reply_text = "x" * 20_000
    page._schedule_render()
    assert page._render_timer.interval() == 120

    page.deleteLater()
    window.deleteLater()


def test_agent_page_flushes_thinking_before_final_reply(monkeypatch) -> None:
    """最终回答覆盖前，思考增量必须同步落入折叠条。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)

    page._on_worker_event("request", {"iteration": 1})
    page._append_thinking_delta("先想一下。")
    page._append_reply_delta("未完成的正文增量")
    page._on_worker_event("reply", {"message": "最终回答。"})

    turn = page._assistant_turn
    assert turn.text_view.toPlainText() == "最终回答。"
    thinking = turn.findChildren(AgentThinkingWidget)
    assert len(thinking) == 1
    assert thinking[0].detail_label.toPlainText() == "先想一下。"

    page.deleteLater()
    window.deleteLater()


def test_agent_page_tool_detail_truncates_long_results() -> None:
    """超长工具结果应截断显示，完整内容放 tooltip，避免卡界面。"""
    widget = AgentToolWidget(
        "scan_script_errors",
        "扫描脚本错误",
        "执行中",
        "已完成",
        "失败",
    )
    long_text = "错误行" * 1500
    widget.complete(True, long_text)

    assert len(widget.detail_label.toPlainText()) < len(long_text)
    assert widget.detail_label.toolTip().startswith("错误行")
    assert widget.toggle_button.isEnabled()
    assert widget.state == "done"

    widget.deleteLater()


def test_agent_message_copy_button_writes_full_text(monkeypatch) -> None:
    """复制按钮应把消息全文写入剪贴板。"""
    message = AgentMessageWidget("要复制的内容", "assistant")
    message.append_text("，以及增量")
    assert message.copy_button is not None
    message._copy_text()

    assert QApplication.clipboard().text() == "要复制的内容，以及增量"
    message.deleteLater()


def test_agent_page_stop_request_appends_stopped_mark(monkeypatch) -> None:
    """停止后已流出正文尾部应有停止标记。"""
    class _StubWorker:
        def isRunning(self) -> bool:
            return True

        def cancel(self) -> None:
            self.cancelled = True

    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)
    page._ensure_assistant_turn()
    page._append_reply_delta("已经输出的部分")
    page._flush_pending_deltas()
    stub = _StubWorker()
    page._worker = stub

    page.stop_request()

    turn = page._assistant_turn
    assert "已停止生成" in turn.text
    assert stub.cancelled
    assert page.status_label.text()

    page._worker = None
    page.deleteLater()
    window.deleteLater()


def test_agent_page_request_event_restores_activity_after_confirmation(monkeypatch) -> None:
    config = Config(agent_platform=0)
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)
    page.activity_widget.set_running(False)

    page._on_worker_event("request", {"iteration": 2})

    assert not page.activity_widget.isHidden()
    assert page.activity_widget.label.text() == Localizer.get().agent_page_running

    page.deleteLater()
    window.deleteLater()


def test_agent_page_cancelled_worker_does_not_append_retry_error(monkeypatch) -> None:
    """主动停止是正常结束，不应再追加一条红色失败记录。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)
    page._append("检查项目", role="user")

    result = type(
        "Result",
        (),
        {"success": False, "message": "Agent 请求已取消。", "code": "CANCELLED"},
    )()
    page._on_worker_finished(result)

    assert all(
        not isinstance(widget, AgentErrorWidget)
        for widget in page.history_widgets
    )
    assert page.status_label.text() == Localizer.get().agent_page_cancelled

    page.deleteLater()
    window.deleteLater()


def test_user_message_renders_as_bubble_without_avatar() -> None:
    """用户消息应是右侧气泡，不带头像；助手消息保持头像 + 文档式正文。"""
    user = AgentMessageWidget("用户消息", "user")
    assistant = AgentMessageWidget("助手消息", "assistant")

    assert user.avatar is None
    assert user.bubble is not None
    assert assistant.avatar is not None
    assert not hasattr(assistant, "bubble") or assistant.bubble is None
    assert user.copy_button is not None
    assert assistant.copy_button is not None

    user.deleteLater()
    assistant.deleteLater()


def test_round_header_shows_round_number_pill() -> None:
    """轮次头应显示居中胶囊中的第几轮。"""
    header = AgentRoundHeader(None, 2)
    assert header.round_label.text() == "第 2 轮"
    assert header.elapsed_label.text() == "0s"
    assert header.pill_separator.width() == 1
    assert "background-color" in header.pill_separator.styleSheet()
    header.stop()
    header.deleteLater()


def test_empty_state_suggestion_cards_expose_text() -> None:
    """空态建议卡保留 text() 兼容，卡片带图标描述。"""
    from module.Localizer.Localizer import Localizer

    state = AgentEmptyState(Localizer.get())
    assert len(state.suggestion_buttons) == 4
    assert all(button.text() for button in state.suggestion_buttons)
    assert state.brand_badge is not None
    state.deleteLater()


def test_assistant_markdown_applies_document_stylesheet() -> None:
    """助手 Markdown 文档应有默认样式表（正文加大、代码块/引用块有型）。"""
    message = AgentMessageWidget("# 标题\n\n普通段落\n\n    code block\n\n> 引用", "assistant")
    stylesheet = message.text_view.document().defaultStyleSheet()
    assert "pre" in stylesheet
    assert "Consolas" in stylesheet
    assert "blockquote" in stylesheet
    message.deleteLater()


def test_agent_page_dark_styles_avoid_black_on_black(monkeypatch) -> None:
    """暗色主题下项目胶囊文字与输入框不得是黑色（曾取调色板导致黑字黑底）。"""
    from qfluentwidgets import Theme, setTheme

    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    setTheme(Theme.DARK)
    window = QWidget()
    page = AgentPage("agent_page", window)
    page._apply_project_pill_style()
    page._apply_composer_style()

    assert "#b6b6b6" in page.project_label.styleSheet()
    assert "background: transparent" in page.input_box.styleSheet()
    assert "border: 1px solid transparent" in page.input_box.styleSheet()
    assert "rgba(0,0,0,0.30)" not in page.input_box.styleSheet()
    assert page.input_box.palette().color(QPalette.Text).name() == "#f2f2f2"
    assert page.input_box.palette().color(QPalette.PlaceholderText).name() == "#9a9a9a"
    assert page.settings_menu.minimumWidth() >= 200

    # Markdown 正文字色必须显式浅色（暗色下系统调色板是黑色）。
    message = AgentMessageWidget("# 标题\n\n正文内容", "assistant")
    assert "color: #e6e6e6" in message.text_view.document().defaultStyleSheet()
    assert "#000000" not in message.text_view.document().defaultStyleSheet()
    message.deleteLater()

    page.deleteLater()
    window.deleteLater()


def test_agent_settings_menu_embeds_the_full_panel(monkeypatch) -> None:
    """设置面板必须作为 RoundMenu 自定义控件完整嵌入，不能压成普通菜单项。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)
    item = page.settings_menu.view.item(0)

    assert page.settings_menu.view.itemWidget(item) is page.settings_panel
    assert item.sizeHint().height() >= page.settings_panel.height()
    assert page.settings_menu.height() > page.settings_panel.height()

    page.deleteLater()
    window.deleteLater()


def test_agent_empty_state_keeps_suggestion_text_aligned() -> None:
    """建议区保持稳定宽度，标题和说明为中文字体预留足够行高。"""
    state = AgentEmptyState(Localizer.get())

    assert state.suggestions.width() == 560
    for card in state.suggestion_buttons:
        assert card.minimumHeight() >= 72
        assert card.sizePolicy().verticalPolicy() == QSizePolicy.Minimum
        assert card.title_label.minimumHeight() >= 20
        assert card.description_label.minimumHeight() >= 18
        assert card.title_label.alignment() & Qt.AlignVCenter
        assert card.description_label.alignment() & Qt.AlignVCenter

    assert state.description_label.minimumHeight() >= 20
    assert state.description_label.alignment() == Qt.AlignCenter
    state.deleteLater()


def test_agent_thinking_detail_scrolls_instead_of_clipping() -> None:
    """长思考详情限制高度并提供滚动，不能把后半段直接裁掉。"""
    widget = AgentThinkingWidget()
    widget.resize(800, widget.sizeHint().height())
    widget.append_text(("查看当前项目信息。" * 20 + "\n") * 30)
    widget._set_expanded(True)
    widget.show()
    APP.processEvents()

    header_layout = widget.layout().itemAt(0).widget().layout()
    assert header_layout.itemAt(2).alignment() & Qt.AlignVCenter
    assert header_layout.itemAt(3).alignment() & Qt.AlignVCenter
    assert widget.detail_label.maximumHeight() == 360
    assert widget.detail_label.height() == 360
    assert widget.detail_label.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert widget.detail_label.verticalScrollBar().maximum() > 0
    assert widget.detail_label.toPlainText().endswith("\n")
    widget.deleteLater()


def test_agent_page_uses_compact_visual_hierarchy(monkeypatch) -> None:
    """工作台标题、空态与设置表单保持紧凑，不再挤占对话空间。"""
    from qfluentwidgets import SubtitleLabel

    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)

    assert isinstance(page.title_label, SubtitleLabel)
    assert isinstance(page.empty_state.title_label, SubtitleLabel)
    assert page.empty_state.brand_badge.width() == 48
    assert page.new_task_button.height() == 30
    assert CONVERSATION_MAX_WIDTH == 960
    assert page.history_content.maximumWidth() == CONVERSATION_MAX_WIDTH
    assert page.topbar_divider.width() == 1
    assert "background-color" in page.topbar_divider.styleSheet()
    assert page.settings_panel.width() == 280
    assert (
        page.thinking_combo.sizePolicy().horizontalPolicy()
        == QSizePolicy.Expanding
    )

    page.deleteLater()
    window.deleteLater()


def test_agent_page_only_shows_stop_button_while_running(monkeypatch) -> None:
    """停止按钮只在任务运行时占位，空闲输入区只保留主操作。"""
    config = Config()
    config.agent_platform = 1
    config.platforms = [
        {
            "id": 1,
            "name": "OpenAI",
            "api_format": Base.APIFormat.OPENAI,
            "model": "gpt-test",
        }
    ]
    config.save = lambda: config
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(AgentWorker, "start", lambda self: None)

    window = QWidget()
    page = AgentPage("agent_page", window)
    assert page.stop_button.isHidden()

    page.input_box.setPlainText("检查项目")
    page.send_message()
    assert not page.stop_button.isHidden()
    assert page.stop_button.isEnabled()

    result = type("Result", (), {"success": True, "message": "完成"})()
    page._on_worker_finished(result)
    assert page.stop_button.isHidden()
    assert not page.stop_button.isEnabled()

    page.deleteLater()
    window.deleteLater()


def test_agent_message_renders_structured_action_buttons() -> None:
    """助手消息把第一个建议显示为主按钮，并通过稳定代码上报点击。"""
    message = AgentMessageWidget("检查完成", "assistant")
    emitted = []
    message.action_requested.connect(emitted.append)
    message.set_actions(
        [
            (ACTION_OPEN_TRANSLATION, "进入翻译页面", FluentIcon.PLAY),
            (ACTION_SCAN_ERRORS, "扫描脚本错误", FluentIcon.SEARCH),
        ]
    )

    assert message.action_container is not None
    assert list(message.action_buttons) == [
        ACTION_OPEN_TRANSLATION,
        ACTION_SCAN_ERRORS,
    ]
    assert isinstance(
        message.action_buttons[ACTION_OPEN_TRANSLATION],
        PrimaryPushButton,
    )
    assert all(button.height() == 32 for button in message.action_buttons.values())
    message.show()
    APP.processEvents()
    primary = message.action_buttons[ACTION_OPEN_TRANSLATION]
    assert message.action_container.height() >= primary.height()
    assert message.action_container.rect().contains(primary.geometry())

    message.action_buttons[ACTION_SCAN_ERRORS].click()
    assert emitted == [ACTION_SCAN_ERRORS]
    message.deleteLater()


def test_agent_message_removes_colored_status_emoji() -> None:
    """模型的彩色状态符号不进入正文，状态统一由 Fluent 控件表达。"""
    text = "✅ 下一步建议\n⚠️ 覆盖风险\n📊 翻译状态\n🔮 继续操作"
    message = AgentMessageWidget(text, "assistant")

    assert message.text == clean_agent_display_text(text)
    assert all(symbol not in message.text for symbol in ("✅", "⚠️", "📊", "🔮"))
    assert "下一步建议" in message.text
    message.deleteLater()


def test_agent_thinking_row_hides_status_dot() -> None:
    """思考行不显示绿色状态圆点，普通工具仍保留主题化状态点。"""
    thinking = AgentThinkingWidget()
    tool = AgentToolWidget("get_project_info", "读取项目", "执行中", "完成", "失败")

    assert thinking.status_dot.isHidden()
    assert not tool.status_dot.isHidden()
    thinking.deleteLater()
    tool.deleteLater()


def test_agent_inspection_builds_buttons_for_translation_ready_project(monkeypatch) -> None:
    """已有脚本时保留 RPA 查看入口，但不再建议重复解包。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)
    actions = page._inspection_actions(
        {
            "next_action_code": "START_TRANSLATION",
            "files": {
                "rpy_count": 192,
                "rpyc_count": 192,
                "rpa_count": 4,
                "unpack_required": False,
            },
        }
    )

    assert [action[0] for action in actions] == [
        ACTION_ONE_KEY_TRANSLATE,
        ACTION_LIST_RPA,
        ACTION_SCAN_ERRORS,
    ]
    page.deleteLater()
    window.deleteLater()


def test_agent_inspection_buttons_attach_after_reply(monkeypatch) -> None:
    """体检按钮在 Worker 完成后挂到最终回复，并触发底部跟随。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    class FakeWindow(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.translation_page = QWidget(self)
            self.navigated = []

        def navigate_to_page(self, page) -> None:
            self.navigated.append(page)

    window = FakeWindow()
    page = AgentPage("agent_page", window)
    page._on_worker_event(
        "tool_done",
        {
            "name": "inspect_translation_project",
            "success": True,
            "message": "项目体检完成",
            "data": {
                "next_action_code": "START_TRANSLATION",
                "files": {
                    "rpy_count": 3,
                    "rpyc_count": 0,
                    "rpa_count": 1,
                    "unpack_required": False,
                },
            },
        },
    )
    page._on_worker_event("reply", {"message": "建议进入翻译页面。"})

    # 回复事件先完成正文，线程结束后才开放操作，避免按钮点击与 Worker 竞争。
    assert page._assistant_turn.action_buttons == {}
    page._history_scroll_timer.stop()
    result = type("Result", (), {"success": True, "message": "完成"})()
    page._on_worker_finished(result)

    turn = page._assistant_turn
    assert page._history_scroll_timer.isActive()
    assert list(turn.action_buttons) == [
        ACTION_ONE_KEY_TRANSLATE,
        ACTION_LIST_RPA,
        ACTION_SCAN_ERRORS,
    ]

    page.deleteLater()
    window.deleteLater()


def test_agent_one_key_action_prefills_project_and_starts(monkeypatch, tmp_path) -> None:
    """一键翻译按钮直接带入当前项目并启动，不要求用户重新选择目录。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    starts = []

    class FakeOneKeyPage(QWidget):
        def start_current_project(self, project_root, language) -> bool:
            starts.append((project_root, language))
            return True

    one_key_page = FakeOneKeyPage()

    class FakeToolbox:
        def get_tool_page(self, key):
            assert key == "one_key_translate"
            return one_key_page

    class FakeWindow(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.renpy_toolbox_page = FakeToolbox()
            self.navigated = []

        def navigate_to_page(self, page) -> None:
            self.navigated.append(page)

    window = FakeWindow()
    page = AgentPage("agent_page", window)
    paths = type(
        "Paths",
        (),
        {"project_root": tmp_path, "language": "chinese"},
    )()
    monkeypatch.setattr(RenpyProjectPaths, "from_config", lambda _config: paths)
    page._handle_reply_action(ACTION_ONE_KEY_TRANSLATE)

    assert window.navigated == [one_key_page]
    assert starts == [(str(tmp_path), "chinese")]
    page.deleteLater()
    one_key_page.deleteLater()
    window.deleteLater()


def test_agent_list_rpa_reply_keeps_followup_buttons(monkeypatch) -> None:
    """点击查找 RPA 后，新回复继续显示剩余操作，不能只在首次体检出现。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)
    page._on_worker_event(
        "tool_done",
        {
            "name": "inspect_translation_project",
            "success": True,
            "message": "项目体检完成",
            "data": {
                "next_action_code": "START_TRANSLATION",
                "files": {
                    "rpy_count": 192,
                    "rpyc_count": 192,
                    "rpa_count": 4,
                    "unpack_required": False,
                },
            },
        },
    )
    page._pending_reply_actions = []
    page._assistant_turn = None
    page._reply_rendered = False
    page._on_worker_event(
        "tool_done",
        {
            "name": "list_rpa_files",
            "success": True,
            "message": "找到 4 个 RPA 文件",
            "data": {"count": 4, "files": ["script.rpa"]},
        },
    )
    page._on_worker_event("reply", {"message": "RPA 文件已列出。"})
    result = type("Result", (), {"success": True, "message": "完成"})()
    page._on_worker_finished(result)

    assert list(page._assistant_turn.action_buttons) == [
        ACTION_ONE_KEY_TRANSLATE,
        ACTION_SCAN_ERRORS,
    ]
    page.deleteLater()
    window.deleteLater()


def test_agent_list_rpa_without_inspection_uses_script_availability(monkeypatch) -> None:
    """直接查 RPA 时也必须按脚本状态判断，不能只看归档数量。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)
    actions = page._followup_actions(
        "list_rpa_files",
        {
            "count": 4,
            "rpy_count": 0,
            "rpyc_count": 0,
            "unpack_required": True,
        },
    )

    assert [action[0] for action in actions] == [ACTION_UNPACK_RPA]

    actions = page._followup_actions(
        "list_rpa_files",
        {
            "count": 4,
            "rpy_count": 192,
            "rpyc_count": 192,
            "unpack_required": False,
        },
    )
    assert [action[0] for action in actions] == [ACTION_SCAN_ERRORS]
    page.deleteLater()
    window.deleteLater()


def test_agent_inspection_keeps_unpack_button_for_archive_only_project(
    monkeypatch,
) -> None:
    """只有 RPA 且没有脚本时，体检仍提供解包与归档查看入口。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)
    actions = page._inspection_actions(
        {
            "next_action_code": "UNPACK_RPA",
            "files": {
                "rpy_count": 0,
                "rpyc_count": 0,
                "rpa_count": 4,
                "unpack_required": True,
            },
        }
    )

    assert [action[0] for action in actions] == [
        ACTION_UNPACK_RPA,
        ACTION_LIST_RPA,
    ]
    page.deleteLater()
    window.deleteLater()


def test_agent_project_actions_clear_after_external_project_change(
    monkeypatch,
    tmp_path,
) -> None:
    """其他页面切换游戏后，不能继续显示上一项目的操作按钮。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)
    page._project_actions = [
        (ACTION_UNPACK_RPA, "解包 RPA 文件", FluentIcon.FOLDER_ADD)
    ]
    page._project_actions_key = "old-project"
    paths = type(
        "Paths",
        (),
        {
            "game_dir": tmp_path,
            "project_root": tmp_path,
            "language": "chinese",
            "project_key": "new-project",
        },
    )()
    monkeypatch.setattr(RenpyProjectPaths, "from_config", lambda _config: paths)

    page._refresh_project_context(config)

    assert page._project_actions == []
    assert page._project_actions_key == ""
    page.deleteLater()
    window.deleteLater()


def test_agent_unpack_action_opens_confirmation_then_starts_direct_tool(monkeypatch) -> None:
    """点击解包先确认，确认后用原项目快照直接执行一次工具。"""
    config = Config()
    config.agent_platform = 0
    config.platforms = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)

    window = QWidget()
    page = AgentPage("agent_page", window)
    monkeypatch.setattr(
        page._service,
        "confirmation_context",
        lambda _name: {"game_dir": "E:/Game/game", "count": 4},
    )
    started = []
    monkeypatch.setattr(
        page,
        "_start_confirmed_tool",
        lambda name, context: started.append((name, context)),
    )

    page._handle_reply_action(ACTION_UNPACK_RPA)

    dialog = page._confirmation_dialog
    assert dialog is not None
    assert dialog.yesButton.text() == Localizer.get().confirm
    assert dialog.cancelButton.text() == Localizer.get().cancel
    assert started == []

    dialog.accept()
    # qfluentwidgets 在淡出动画完成后才发出 accepted。
    import time as _time
    for _ in range(20):
        APP.processEvents()
        if started:
            break
        _time.sleep(0.02)

    assert started == [
        ("unpack_rpa_files", {"game_dir": "E:/Game/game", "count": 4})
    ]
    assert page._confirmation_dialog is None
    page.deleteLater()
    window.deleteLater()
