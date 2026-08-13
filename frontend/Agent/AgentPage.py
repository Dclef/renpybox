"""Agent 助手页面。

布局取自 LinguaGacha 的 agent 页：顶部集中展示助手、接口与项目状态，
主体只保留对话区和输入区，让垂直空间尽量留给对话。
"""

from __future__ import annotations

import json
import math
import time
from typing import Any

from PyQt5.QtCore import QTimer, Qt, QSize, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QKeyEvent,
    QPainter,
    QPalette,
    QTextLength,
    QTextTable,
    QTextTableFormat,
)
from PyQt5.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    CardWidget,
    ComboBox,
    FluentIcon,
    IconWidget,
    MessageBox,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SingleDirectionScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
    TextBrowser,
    TitleLabel,
    ThemeColor,
    TransparentPushButton,
    TransparentToolButton,
    isDarkTheme,
    qconfig,
)

from base.Base import Base
from frontend.Agent.AgentWorker import AgentWorker
from module.Agent.AgentService import AgentService
from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.Renpy.ProjectPaths import RenpyProjectPaths
from widget.ThemeHelper import mark_toolbox_scroll_area, mark_toolbox_widget


# AgentRequester 目前没有导出格式白名单；能力约束暂时保留在 UI，后续任务再下移。
SUPPORTED_FORMATS = {
    str(Base.APIFormat.OPENAI),
    str(Base.APIFormat.ANTHROPIC),
    str(Base.APIFormat.GOOGLE),
}

# 对话区最大宽度。宽屏下保持可读行长，窄屏时随窗口收缩。
CONVERSATION_MAX_WIDTH = 1120

# 顶栏思考等级只作用于 Agent 请求；OFF 保持平台默认关闭行为。
THINKING_LEVELS = ("OFF", "LOW", "MEDIUM", "HIGH", "MAX")

# Markdown 正文的最小可读高度；超长内容由外层对话滚动区承载。
MESSAGE_MIN_HEIGHT = 48

# 用户主动上滚超过该距离后，新消息不再抢回滚动位置。
AUTO_FOLLOW_THRESHOLD = 80


def status_color(state: str) -> QColor:
    """工具状态色。

    成功/失败使用 Qt 的语义色（绿/红）；运行中状态使用 qfluentwidgets 主色。
    """
    if state == "done":
        # Qt 的语义色会随平台主题和高对比度设置变化，不在页面里复制一套色值。
        return QColor(Qt.green)
    if state == "failed":
        return QColor(Qt.red)
    return ThemeColor.PRIMARY.color()


def format_elapsed(seconds: float) -> str:
    """紧凑耗时格式；纯数字加单位，不需要翻译。"""
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes > 0:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


class AgentInputEdit(PlainTextEdit):
    """支持 Ctrl+Enter 提交的多行输入框。"""

    send_requested = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            event.key() in (Qt.Key_Return, Qt.Key_Enter)
            and event.modifiers() & Qt.ControlModifier
        ):
            self.send_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class AgentMarkdownView(TextBrowser):
    """让 Markdown 正文按文档尺寸参与布局，避免被 QTextBrowser 默认高度截断。"""

    def setMarkdown(self, markdown: str) -> None:
        super().setMarkdown(markdown)
        self._format_tables()

    def _format_tables(self) -> None:
        """覆盖 Qt 默认的紧缩表格样式，使表格与正文列对齐。"""
        border_color = QColor("#666666" if isDarkTheme() else "#d0d0d0")
        header_color = QColor("#444444" if isDarkTheme() else "#f3f3f3")
        for frame in self.document().rootFrame().childFrames():
            if not isinstance(frame, QTextTable):
                continue
            table_format = frame.format()
            table_format.setWidth(QTextLength(QTextLength.PercentageLength, 100))
            table_format.setBorderCollapse(True)
            table_format.setBorder(1)
            table_format.setBorderStyle(QTextTableFormat.BorderStyle_Solid)
            table_format.setBorderBrush(QBrush(border_color))
            table_format.setCellSpacing(0)
            table_format.setCellPadding(7)
            frame.setFormat(table_format)

            for column in range(frame.columns()):
                cell = frame.cellAt(0, column)
                cell_format = cell.format()
                cell_format.setBackground(QBrush(header_color))
                cell.setFormat(cell_format)

    def refresh_theme(self) -> None:
        self._format_tables()

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        document_height = self.document().size().height()
        if document_height > 0:
            hint.setHeight(max(MESSAGE_MIN_HEIGHT, math.ceil(document_height) + 8))
        return hint

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # 宽度变化会改变换行高度，交给布局重新询问 sizeHint。
        self.updateGeometry()


class AgentStatusDot(QFrame):
    """绘制随主题变化的圆形工具状态点。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = ThemeColor.PRIMARY.color()
        self.setFixedSize(8, 8)

    def set_color(self, color: QColor) -> None:
        self._color = color
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(self.rect())


class AgentAvatar(QFrame):
    """圆形头像：主色圆底 + 居中图标，用于区分用户与助手。"""

    SIZE = 28

    def __init__(self, role: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.role = role
        self.setFixedSize(self.SIZE, self.SIZE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        self._icon = IconWidget(self._icon_source(), self)
        self._icon.setFixedSize(15, 15)
        layout.addWidget(self._icon)

    def _icon_source(self):
        if self.role == "user":
            return FluentIcon.PEOPLE
        if self.role == "error":
            return FluentIcon.CANCEL
        return FluentIcon.ROBOT

    def _background(self) -> QColor:
        if self.role == "error":
            return status_color("failed")
        if self.role == "user":
            # 使用系统调色板的中性色，避免与助手的强调色抢视觉重心。
            return QApplication.palette().color(QPalette.Mid)
        return ThemeColor.PRIMARY.color()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._background())
        painter.drawEllipse(self.rect())

    def refresh_theme(self) -> None:
        self.update()


class AgentErrorWidget(CardWidget):
    """单行错误条：图标 + 摘要 + 右侧重试入口。

    错误正文用 QLabel 而不是 TextBrowser —— TextBrowser 即便设成
    AdjustToContents，也会为一行文字留出接近 100px 的视口高度。
    """

    retry_requested = pyqtSignal()

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.role = "error"
        self._full_text = str(text or "")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(38)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 10, 0)
        row.setSpacing(8)

        icon = IconWidget(FluentIcon.INFO, self)
        icon.setFixedSize(14, 14)
        row.addWidget(icon, 0, Qt.AlignVCenter)

        self.text_view = CaptionLabel(self._summary(), self)
        self.text_view.setTextFormat(Qt.PlainText)
        self.text_view.setToolTip(self._full_text)
        self.text_view.setTextColor(status_color("failed"), status_color("failed"))
        row.addWidget(self.text_view, 1, Qt.AlignVCenter)

        self.retry_button = TransparentPushButton(Localizer.get().agent_page_retry, self)
        self.retry_button.setFixedHeight(26)
        self.retry_button.clicked.connect(self.retry_requested.emit)
        row.addWidget(self.retry_button, 0, Qt.AlignVCenter)

    def _summary(self) -> str:
        """错误条只显示首行摘要，完整内容留在 tooltip。"""
        first_line = self._full_text.strip().splitlines()[0] if self._full_text.strip() else ""
        return first_line if len(first_line) <= 90 else f"{first_line[:90]} …"

    def refresh_theme(self) -> None:
        color = status_color("failed")
        self.text_view.setTextColor(color, color)


class AgentMessageWidget(QWidget):
    """一轮公开消息；中间过程折叠在同一个 Agent 身份下。"""

    def __init__(self, text: str, role: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.role = role
        self._text = str(text or "")
        self._thinking_widgets: list[AgentThinkingWidget] = []
        self._tool_widgets: list[AgentToolWidget] = []
        self._active_thinking: AgentThinkingWidget | None = None
        self.setProperty("role", role)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        localizer = Localizer.get()
        head = QWidget(self)
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(0, 0, 0, 0)
        head_layout.setSpacing(8)
        self.avatar = AgentAvatar(role, head)
        head_layout.addWidget(self.avatar, 0, Qt.AlignVCenter)
        self.role_label = StrongBodyLabel(
            localizer.agent_page_user_avatar
            if role == "user"
            else localizer.agent_page_assistant_label,
            head,
        )
        head_layout.addWidget(self.role_label, 0, Qt.AlignVCenter)
        head_layout.addStretch(1)
        root.addWidget(head)

        body = QWidget(self)
        body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        body_layout = QVBoxLayout(body)
        # 正文缩进与头像宽度对齐，让同一说话人的内容形成视觉列。
        body_layout.setContentsMargins(AgentAvatar.SIZE + 8, 0, 0, 0)
        body_layout.setSpacing(8)

        if role == "user":
            # 用户消息是纯文本，用 QLabel 就够，不必承担 TextBrowser 的视口高度。
            label = QLabel(str(text or ""), body)
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            body_layout.addWidget(label, 1)
            self.text_view = label
        else:
            text_view = AgentMarkdownView(body)
            text_view.setReadOnly(True)
            text_view.setOpenLinks(False)
            text_view.setOpenExternalLinks(False)
            text_view.setFrameShape(QFrame.NoFrame)
            text_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            # 长回复由外层对话区滚动，消息内部不再套第二个滚动条。
            text_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            text_view.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
            text_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            text_view.setTextInteractionFlags(
                Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse
            )
            text_view.document().setDocumentMargin(0)
            text_view.setAutoFillBackground(False)
            text_view.viewport().setAutoFillBackground(False)
            # 正文直接贴在对话流上；带背景框会让它看起来像可编辑输入框。
            text_view.setAttribute(Qt.WA_TranslucentBackground, True)
            text_view.viewport().setAttribute(Qt.WA_TranslucentBackground, True)
            text_view.setMinimumHeight(MESSAGE_MIN_HEIGHT)
            text_view.setMarkdown(self._text)
            text_view.setVisible(bool(self._text.strip()))
            body_layout.addWidget(text_view, 1)
            self.text_view = text_view
        root.addWidget(body)
        self.body = body
        self.body_layout = body_layout
        self.detail_container = QWidget(body)
        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_layout.setSpacing(6)
        self.detail_container.hide()
        body_layout.insertWidget(0, self.detail_container)

    @property
    def text(self) -> str:
        """返回当前消息的完整原文，流式渲染和测试共用。"""
        return self._text

    def set_text(self, text: str) -> None:
        """替换消息正文，保留同一个控件以避免滚动区跳动。"""
        self._text = str(text or "")
        if self.role == "user":
            self.text_view.setText(self._text)
        else:
            self.text_view.setMarkdown(self._text)
            self.text_view.setVisible(bool(self._text.strip()))
        self.text_view.updateGeometry()
        self.updateGeometry()

    def append_text(self, text: str) -> None:
        """追加一段模型增量。"""
        if text:
            self.set_text(self._text + str(text))

    def append_thinking_text(self, text: str) -> "AgentThinkingWidget":
        """把本轮尚未确认的模型文本放进折叠过程行。"""
        if self.role != "assistant":
            raise ValueError("只有助手消息支持思考过程")
        if self._active_thinking is None:
            self._active_thinking = AgentThinkingWidget(self.detail_container)
            self._thinking_widgets.append(self._active_thinking)
            self.detail_layout.addWidget(self._active_thinking)
            self.detail_container.show()
        self._active_thinking.append_text(text)
        self._active_thinking.set_running(True)
        self.updateGeometry()
        return self._active_thinking

    def finish_thinking(self) -> None:
        """结束当前思考行，但保持其默认折叠。"""
        if self._active_thinking is not None:
            self._active_thinking.set_running(False)
            self._active_thinking = None

    def discard_active_thinking(self) -> None:
        """最终回答到达时移除同一轮的临时文本，避免显示两遍。"""
        widget = self._active_thinking
        if widget is None:
            return
        self._active_thinking = None
        self._thinking_widgets.remove(widget)
        self.detail_layout.removeWidget(widget)
        widget.deleteLater()
        if not self._thinking_widgets and not self._tool_widgets:
            self.detail_container.hide()
        self.updateGeometry()

    def move_answer_to_thinking(self) -> None:
        """工具调用开始后，把已显示的前置说明收进折叠过程条。"""
        if self.role != "assistant" or not self._text.strip():
            return
        pending = self._text
        self.set_text("")
        self.append_thinking_text(pending)
        self.finish_thinking()

    def add_tool_widget(self, widget: "AgentToolWidget") -> None:
        """把工具条目挂到本轮 Agent 消息下。"""
        if self.role != "assistant":
            raise ValueError("只有助手消息支持工具条目")
        self.finish_thinking()
        self._tool_widgets.append(widget)
        widget.setParent(self.detail_container)
        self.detail_layout.addWidget(widget)
        self.detail_container.show()
        self.updateGeometry()

    @property
    def tool_widgets(self) -> list["AgentToolWidget"]:
        return list(self._tool_widgets)

    def refresh_theme(self) -> None:
        self.avatar.refresh_theme()
        if isinstance(self.text_view, AgentMarkdownView):
            self.text_view.refresh_theme()
        for widget in (*self._thinking_widgets, *self._tool_widgets):
            refresh = getattr(widget, "refresh_theme", None)
            if callable(refresh):
                refresh()


class AgentRoundHeader(QWidget):
    """轮次分隔：一条细线加右侧耗时，运行中每秒刷新。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._started_at = time.monotonic()
        self._running = True

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 6, 0, 0)
        row.setSpacing(10)

        line = QFrame(self)
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        line.setFixedHeight(1)
        row.addWidget(line, 1)

        self.elapsed_label = CaptionLabel(format_elapsed(0), self)
        row.addWidget(self.elapsed_label, 0)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        if not self._running:
            return
        self.elapsed_label.setText(format_elapsed(time.monotonic() - self._started_at))

    def stop(self) -> None:
        """回合结束后冻结耗时，并停掉计时器。"""
        if not self._running:
            return
        self._running = False
        self._timer.stop()
        self.elapsed_label.setText(format_elapsed(time.monotonic() - self._started_at))


class AgentToolWidget(CardWidget):
    """单行高度的工具执行条目，整行可点击展开结果。"""

    def __init__(
        self,
        tool_name: str,
        tool_label: str,
        running_text: str,
        done_text: str,
        failed_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.tool_name = tool_name
        self._running_text = running_text
        self._done_text = done_text
        self._failed_text = failed_text
        self._state = "running"
        self._started_at = time.monotonic()
        self.setProperty("state", self._state)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 0, 8, 0)
        root.setSpacing(0)

        header = QWidget(self)
        header.setFixedHeight(34)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self.status_dot = AgentStatusDot(header)
        self.status_dot.setProperty("state", self._state)
        header_layout.addWidget(self.status_dot, 0, Qt.AlignVCenter)

        self.name_label = CaptionLabel(tool_label, header)
        header_layout.addWidget(self.name_label, 0)

        self.status_label = CaptionLabel(running_text, header)
        self.status_label.setProperty("state", self._state)
        header_layout.addWidget(self.status_label, 0)
        header_layout.addStretch(1)

        # 折叠指示器保留为按钮，既是可见提示也是测试入口。
        self.toggle_button = TransparentToolButton(header)
        self.toggle_button.setIcon(FluentIcon.CHEVRON_RIGHT)
        self.toggle_button.setFixedSize(22, 22)
        self.toggle_button.setEnabled(False)
        self.toggle_button.setToolTip(Localizer.get().agent_page_tool_expand)
        self.toggle_button.clicked.connect(self._toggle_detail)
        header_layout.addWidget(self.toggle_button, 0, Qt.AlignVCenter)
        root.addWidget(header)

        self.detail_label = QLabel(self)
        self.detail_label.setWordWrap(True)
        self.detail_label.setTextFormat(Qt.PlainText)
        self.detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_label.setContentsMargins(16, 0, 0, 8)
        self.detail_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.detail_label.setMaximumHeight(360)
        self.detail_label.hide()
        root.addWidget(self.detail_label)
        self._refresh_state_colors()

    def sizeHint(self) -> QSize:
        """展开详情时把正文高度明确交给父布局，避免卡片裁切 QLabel。"""
        hint = super().sizeHint()
        if self.detail_label.isVisible():
            hint.setHeight(max(hint.height(), 34 + self.detail_label.minimumHeight()))
        return hint

    @property
    def state(self) -> str:
        return self._state

    def complete(self, success: bool, message: str) -> None:
        """更新工具结果；失败时自动展开可核对的原因。"""
        self._state = "done" if success else "failed"
        elapsed = format_elapsed(time.monotonic() - self._started_at)
        status_text = self._done_text if success else self._failed_text
        self.status_label.setText(f"{status_text} · {elapsed}")
        self.detail_label.setText(str(message or ""))
        has_detail = bool(str(message or "").strip())
        self.toggle_button.setEnabled(has_detail)
        self._set_expanded(has_detail and not success)
        self.setProperty("state", self._state)
        self.status_dot.setProperty("state", self._state)
        self.status_label.setProperty("state", self._state)
        self._refresh_state_colors()
        self.updateGeometry()

    def mouseReleaseEvent(self, event) -> None:
        """整行可点，不必精确命中折叠按钮。"""
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton and self.toggle_button.isEnabled():
            self._toggle_detail()

    def _toggle_detail(self) -> None:
        self._set_expanded(not self.detail_label.isVisible())

    def _set_expanded(self, expanded: bool) -> None:
        self.detail_label.setVisible(expanded)
        if expanded:
            # QLabel 首次显示时可能还没有按当前宽度重算换行高度，先把 sizeHint
            # 提升为布局下限，避免内容被卡片边框截断。
            self.detail_label.setMinimumHeight(
                min(360, max(0, self.detail_label.sizeHint().height()))
            )
            self.adjustSize()
            container = self.parentWidget()
            if container is not None:
                required = self.sizeHint().height()
                container.setMinimumHeight(required)
                body = container.parentWidget()
                if body is not None:
                    body.setMinimumHeight(required)
                    turn = body.parentWidget()
                    if turn is not None:
                        turn.setMinimumHeight(turn.sizeHint().height())
        else:
            self.detail_label.setMinimumHeight(0)
            container = self.parentWidget()
            if container is not None:
                container.setMinimumHeight(0)
                body = container.parentWidget()
                if body is not None:
                    body.setMinimumHeight(0)
                    turn = body.parentWidget()
                    if turn is not None:
                        turn.setMinimumHeight(0)
        self.toggle_button.setIcon(
            FluentIcon.CHEVRON_DOWN_MED if expanded else FluentIcon.CHEVRON_RIGHT
        )
        self.updateGeometry()

    def _refresh_state_colors(self) -> None:
        """直接应用语义状态色，不依赖页面级动态属性样式。"""
        color = status_color(self._state)
        self.status_dot.set_color(color)
        self.status_label.setTextColor(color, color)

    def refresh_theme(self) -> None:
        self._refresh_state_colors()


class AgentThinkingWidget(AgentToolWidget):
    """助手中间文本的折叠条，不把未确认内容当成最终回答。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        localizer = Localizer.get()
        super().__init__(
            "thinking",
            localizer.agent_page_assistant_label,
            localizer.agent_page_running,
            localizer.agent_page_done,
            localizer.agent_page_failed,
            parent,
        )
        self._text = ""
        self.name_label.setText(localizer.agent_page_thinking_process)
        self.toggle_button.setToolTip(localizer.agent_page_tool_expand)

    def append_text(self, text: str) -> None:
        if not text:
            return
        self._text += str(text)
        self.detail_label.setText(self._text)
        self.toggle_button.setEnabled(bool(self._text.strip()))
        self.updateGeometry()

    def set_running(self, running: bool) -> None:
        if running:
            self._state = "running"
            self.status_label.setText(self._running_text)
            self.setProperty("state", self._state)
            self.status_dot.setProperty("state", self._state)
            self.status_label.setProperty("state", self._state)
            self._refresh_state_colors()
            return
        self.complete(True, self._text)


class AgentActivityWidget(QWidget):
    """当前回合正在等待模型响应时的轻量状态行。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)
        self.dot = AgentStatusDot(self)
        layout.addWidget(self.dot, 0, Qt.AlignVCenter)
        self.label = CaptionLabel("", self)
        layout.addWidget(self.label)
        layout.addStretch(1)
        self.hide()

    def set_running(self, running: bool, text: str = "") -> None:
        self.label.setText(text)
        self.setVisible(running)

    def refresh_theme(self) -> None:
        self.dot.set_color(status_color("running"))


class AgentEmptyState(QWidget):
    """空会话的起始视图，提供几个可直接编辑的常用请求。"""

    suggestion_requested = pyqtSignal(str)

    def __init__(self, localizer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(0)
        outer.addStretch(1)

        intro = QWidget(self)
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(0, 0, 0, 0)
        intro_layout.setSpacing(8)
        intro_layout.setAlignment(Qt.AlignCenter)

        icon = IconWidget(FluentIcon.ROBOT, intro)
        icon.setFixedSize(28, 28)
        intro_layout.addWidget(icon, 0, Qt.AlignHCenter)

        self.title_label = SubtitleLabel(localizer.agent_page_empty_title, intro)
        intro_layout.addWidget(self.title_label, 0, Qt.AlignHCenter)

        self.description_label = CaptionLabel(localizer.agent_page_empty_description, intro)
        self.description_label.setWordWrap(True)
        self.description_label.setMaximumWidth(560)
        self.description_label.setAlignment(Qt.AlignHCenter)
        intro_layout.addWidget(self.description_label, 0, Qt.AlignHCenter)
        outer.addWidget(intro, 0, Qt.AlignHCenter)

        # 建议卡改用两列网格；三个横排按钮在窄窗口下会被压成一条。
        suggestions = QWidget(self)
        suggestions.setMaximumWidth(608)
        grid = QVBoxLayout(suggestions)
        grid.setContentsMargins(0, 20, 0, 0)
        grid.setSpacing(8)

        self.suggestion_buttons: list[PushButton] = []
        entries = (
            (localizer.agent_page_suggestion_project, FluentIcon.INFO),
            (localizer.agent_page_suggestion_rpa, FluentIcon.ZIP_FOLDER),
            (localizer.agent_page_suggestion_errors, FluentIcon.SEARCH),
        )
        for index in range(0, len(entries), 2):
            row_widget = QWidget(suggestions)
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            for text, icon_value in entries[index:index + 2]:
                button = PushButton(text, icon=icon_value, parent=row_widget)
                button.setMinimumHeight(44)
                button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                button.clicked.connect(
                    lambda _checked=False, value=text: self.suggestion_requested.emit(value)
                )
                row.addWidget(button, 1)
                self.suggestion_buttons.append(button)
            if len(entries[index:index + 2]) == 1:
                row.addStretch(1)
            grid.addWidget(row_widget)
        outer.addWidget(suggestions, 0, Qt.AlignHCenter)
        outer.addStretch(2)


class AgentPage(Base, QWidget):
    """提供对话输入、工具执行反馈与 Agent 接口选择。"""

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)

        self._window = parent
        self._service = AgentService()
        self._worker: AgentWorker | None = None
        self._platform_ids: list[int] = []
        self._running_tool_widgets: list[AgentToolWidget] = []
        self._round_header: AgentRoundHeader | None = None
        self._stream_message: AgentMessageWidget | None = None
        self._assistant_turn: AgentMessageWidget | None = None
        self._reply_rendered = False
        self._auto_follow = True
        self._reset_after_worker = False
        self._confirmation_dialog: MessageBox | None = None

        self._last_message = ""

        self.root = QVBoxLayout(self)
        # 收窄页面边距，把主要空间留给对话。
        self.root.setContentsMargins(16, 12, 16, 12)
        self.root.setSpacing(8)
        self._build_topbar()
        self._build_conversation()
        self._build_composer()

        qconfig.themeChanged.connect(self._on_theme_changed)
        self.refresh_platforms()

    def _build_topbar(self) -> None:
        """顶栏集中展示助手身份、模型选择与项目上下文。"""
        localizer = Localizer.get()
        bar = CardWidget(self)
        self.topbar = bar
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.brand_avatar = AgentAvatar("assistant", bar)
        layout.addWidget(self.brand_avatar, 0, Qt.AlignVCenter)

        self.title_label = TitleLabel(localizer.agent_page_title, bar)
        layout.addWidget(self.title_label, 0, Qt.AlignVCenter)

        self.platform_combo = ComboBox(bar)
        self.platform_combo.setMinimumWidth(200)
        self.platform_combo.setMaximumWidth(300)
        self.platform_combo.setFixedHeight(30)
        self.platform_combo.currentIndexChanged.connect(self._platform_changed)
        layout.addWidget(self.platform_combo, 0)

        self.refresh_button = TransparentToolButton(bar)
        self.refresh_button.setIcon(FluentIcon.SYNC)
        self.refresh_button.setFixedSize(28, 28)
        self.refresh_button.setToolTip(localizer.agent_page_refresh)
        self.refresh_button.clicked.connect(self.refresh_platforms)
        layout.addWidget(self.refresh_button, 0)

        self.thinking_label = CaptionLabel(
            localizer.platform_edit_page_thinking_title,
            bar,
        )
        layout.addWidget(self.thinking_label, 0, Qt.AlignVCenter)

        self.thinking_combo = ComboBox(bar)
        self.thinking_combo.setFixedWidth(96)
        self.thinking_combo.setFixedHeight(30)
        self.thinking_combo.setToolTip(localizer.platform_edit_page_thinking_content)
        for level, label in zip(
            THINKING_LEVELS,
            (
                localizer.platform_edit_page_thinking_off,
                localizer.platform_edit_page_thinking_low,
                localizer.platform_edit_page_thinking_medium,
                localizer.platform_edit_page_thinking_high,
                localizer.platform_edit_page_thinking_max,
            ),
        ):
            self.thinking_combo.addItem(label, userData=level)
        self.thinking_combo.currentIndexChanged.connect(self._thinking_changed)
        layout.addWidget(self.thinking_combo, 0)

        self.project_label = CaptionLabel("", bar)
        layout.addWidget(self.project_label, 0)
        layout.addStretch(1)

        self.new_task_button = TransparentPushButton(
            localizer.agent_page_new_task,
            bar,
            FluentIcon.ADD,
        )
        self.new_task_button.setFixedHeight(28)
        self.new_task_button.clicked.connect(self.start_new_task)
        layout.addWidget(self.new_task_button, 0)
        self.root.addWidget(bar)

        # 兼容旧引用：description_label 曾是页头描述，现由项目标签承担。
        self.description_label = self.project_label

    def _build_conversation(self) -> None:
        localizer = Localizer.get()
        self.conversation_card = CardWidget(self)
        conversation_layout = QVBoxLayout(self.conversation_card)
        conversation_layout.setContentsMargins(0, 0, 0, 0)
        conversation_layout.setSpacing(0)

        self.conversation_stack = QStackedWidget(self.conversation_card)
        self.empty_state = AgentEmptyState(localizer, self.conversation_stack)
        self.empty_state.suggestion_requested.connect(self._fill_suggestion)
        self.conversation_stack.addWidget(self.empty_state)

        self.history = SingleDirectionScrollArea(
            orient=Qt.Orientation.Vertical,
            parent=self.conversation_stack,
        )
        self.history.setWidgetResizable(True)
        self.history.setFrameShape(QFrame.NoFrame)
        self.history.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        mark_toolbox_scroll_area(self.history)

        # 让滚动区直接管理唯一的 expanding 内容列，避免左右 stretch 把正文压窄。
        self.history.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.history_content = QWidget(self.history)
        self.history_content.setMaximumWidth(CONVERSATION_MAX_WIDTH)
        self.history_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        mark_toolbox_widget(self.history_content, "toolboxScroll")
        self.history_layout = QVBoxLayout(self.history_content)
        self.history_layout.setContentsMargins(20, 18, 20, 24)
        self.history_layout.setSpacing(14)
        self.history_layout.addStretch(1)
        self.history.setWidget(self.history_content)
        self.history.enableTransparentBackground()
        self.conversation_stack.addWidget(self.history)
        self.conversation_stack.setCurrentWidget(self.empty_state)
        conversation_layout.addWidget(self.conversation_stack)
        self.root.addWidget(self.conversation_card, 1)

        # 用户主动上滚后不再自动跟随，避免流式增量抢回滚动位置。
        self.history.verticalScrollBar().valueChanged.connect(self._on_history_scrolled)
        self._history_scroll_timer = QTimer(self)
        self._history_scroll_timer.setSingleShot(True)
        self._history_scroll_timer.timeout.connect(self._scroll_history_to_bottom)

    def _build_composer(self) -> None:
        localizer = Localizer.get()
        composer = CardWidget(self)
        self.composer = composer
        composer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(14, 8, 12, 8)
        composer_layout.setSpacing(6)

        self.input_box = AgentInputEdit(composer)
        self.input_box.setPlaceholderText(localizer.agent_page_input_placeholder)
        self.input_box.setFrameShape(QFrame.NoFrame)
        # 输入区默认三行高；粘长文时自行增高到上限。
        self.input_box.setFixedHeight(78)
        self.input_box.setLineWrapMode(PlainTextEdit.WidgetWidth)
        self.input_box.textChanged.connect(self._autosize_input)
        self.input_box.textChanged.connect(self._update_send_button)
        self.input_box.send_requested.connect(self.send_message)
        composer_layout.addWidget(self.input_box)

        # 底栏只留状态与操作；模型选择已上移到顶栏。
        footer = QWidget(composer)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(6)

        self.hint_label = CaptionLabel(localizer.agent_page_send_hint, footer)
        footer_layout.addWidget(self.hint_label, 0)
        footer_layout.addStretch(1)

        self.status_label = CaptionLabel("", footer)
        footer_layout.addWidget(self.status_label, 0)

        self.stop_button = PushButton(localizer.agent_page_stop, parent=footer)
        self.stop_button.setFixedHeight(28)
        self.stop_button.clicked.connect(self.stop_request)
        self.stop_button.setEnabled(False)
        footer_layout.addWidget(self.stop_button, 0)

        self.send_button = PrimaryPushButton(
            localizer.agent_page_send,
            icon=FluentIcon.SEND,
            parent=footer,
        )
        self.send_button.setFixedHeight(28)
        self.send_button.clicked.connect(self.send_message)
        footer_layout.addWidget(self.send_button, 0)
        composer_layout.addWidget(footer)
        self.root.addWidget(composer, 0)

        # 活动指示器排在对话流末尾，跟随消息一起滚动。
        self.activity_widget = AgentActivityWidget(self.history_content)
        self.history_layout.insertWidget(
            self.history_layout.count() - 1,
            self.activity_widget,
        )

    def _autosize_input(self) -> None:
        """输入框随内容增高，上限 180px 后转为内部滚动。"""
        document_height = math.ceil(self.input_box.document().size().height())
        target = min(180, max(78, document_height + 20))
        if self.input_box.height() != target:
            self.input_box.setFixedHeight(target)

    def _on_theme_changed(self, _theme=None) -> None:
        """主题变化时刷新自绘的语义状态色，其余交给 qfluentwidgets。"""
        self.brand_avatar.refresh_theme()
        self.activity_widget.refresh_theme()
        for widget in self.history_widgets:
            refresh = getattr(widget, "refresh_theme", None)
            if callable(refresh):
                refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh_platforms()

    def refresh_platforms(self) -> None:
        config = Config().load()
        self._refresh_project_context(config)
        current = int(getattr(config, "agent_platform", -1))
        thinking_level = str(
            getattr(config, "agent_thinking_level", "OFF") or "OFF"
        ).upper()
        if thinking_level not in THINKING_LEVELS:
            thinking_level = "OFF"

        self.thinking_combo.blockSignals(True)
        self.thinking_combo.setCurrentIndex(
            self.thinking_combo.findData(thinking_level)
        )
        self.thinking_combo.blockSignals(False)

        self.platform_combo.blockSignals(True)
        self.platform_combo.clear()
        self._platform_ids = []
        localizer = Localizer.get()
        self.platform_combo.addItem(localizer.agent_page_platform_unset, userData=-1)
        for platform in config.platforms or []:
            api_format = str(platform.get("api_format", ""))
            if api_format not in SUPPORTED_FORMATS:
                continue
            platform_id = int(platform.get("id", 0))
            name = str(platform.get("name") or platform.get("model") or api_format)
            self.platform_combo.addItem(f"{name} [{api_format}]", userData=platform_id)
            self._platform_ids.append(platform_id)
        index = self.platform_combo.findData(current)
        self.platform_combo.setCurrentIndex(index if index >= 0 else 0)
        self.platform_combo.blockSignals(False)
        self._update_send_button()

    def _platform_changed(self, index: int) -> None:
        data = self.platform_combo.itemData(index)
        platform_id = int(data if data is not None else -1)
        config = Config().load()
        config.agent_platform = platform_id
        config.save()
        self.status_label.setText(
            Localizer.get().agent_page_platform_unset
            if platform_id < 0
            else Localizer.get().agent_page_platform_saved
        )
        self._update_send_button()

    def _thinking_changed(self, index: int) -> None:
        level = str(self.thinking_combo.itemData(index) or "OFF")
        config = Config().load()
        config.agent_thinking_level = level
        config.save()

    def _refresh_project_context(self, config: Config | None = None) -> None:
        current = config or Config().load()
        paths = RenpyProjectPaths.from_config(current)
        if paths is None or not paths.game_dir.is_dir():
            self.project_label.setText(Localizer.get().agent_page_project_unset)
            self.project_label.setToolTip("")
            return
        self.project_label.setText(
            Localizer.get().agent_page_project_context.format(
                name=paths.project_root.name,
                language=paths.language,
            )
        )
        self.project_label.setToolTip(str(paths.project_root))

    def _fill_suggestion(self, text: str) -> None:
        self.input_box.setPlainText(text)
        self.input_box.setFocus()
        self.input_box.selectAll()

    @property
    def history_widgets(self) -> list[QWidget]:
        """返回会话中的消息与工具控件，不含轮次头和活动指示器。"""
        widgets: list[QWidget] = []
        for index in range(self.history_layout.count()):
            widget = self.history_layout.itemAt(index).widget()
            if (
                widget is not None
                and widget is not self.activity_widget
                and not isinstance(widget, AgentRoundHeader)
            ):
                widgets.append(widget)
        return widgets

    def _on_history_scrolled(self, _value: int = 0) -> None:
        bar = self.history.verticalScrollBar()
        self._auto_follow = bar.maximum() - bar.value() <= AUTO_FOLLOW_THRESHOLD

    def _scroll_history_to_bottom(self) -> None:
        if not self._auto_follow:
            return
        bar = self.history.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _add_history_widget(self, widget: QWidget) -> None:
        if self.conversation_stack.currentWidget() is self.empty_state:
            self.conversation_stack.setCurrentWidget(self.history)
        # 活动指示器与 stretch 始终留在末尾，新内容插在它们前面。
        insert_at = self.history_layout.indexOf(self.activity_widget)
        if insert_at < 0:
            insert_at = self.history_layout.count() - 1
        self.history_layout.insertWidget(insert_at, widget)
        self._history_scroll_timer.start(0)

    def _append(self, text: str, *, role: str) -> QWidget:
        """按调用方提供的角色添加消息，不从翻译后的文案反推角色。"""
        if role == "error":
            widget: QWidget = AgentErrorWidget(str(text or ""), self.history_content)
            widget.retry_requested.connect(self.retry_last_message)
        else:
            widget = AgentMessageWidget(str(text or ""), role, self.history_content)
        self._add_history_widget(widget)
        return widget

    def _ensure_assistant_turn(self) -> AgentMessageWidget:
        """确保当前回合只有一个助手消息头，过程条目都挂在它下面。"""
        if self._assistant_turn is None:
            self._assistant_turn = AgentMessageWidget(
                "",
                "assistant",
                self.history_content,
            )
            self._stream_message = self._assistant_turn
            self._add_history_widget(self._assistant_turn)
        return self._assistant_turn

    def _append_reply_delta(self, text: str) -> None:
        """实时显示模型增量；若后续调用工具，再由事件处理器折叠。"""
        delta = str(text or "")
        if not delta:
            return
        turn = self._ensure_assistant_turn()
        turn.finish_thinking()
        turn.append_text(delta)
        self.activity_widget.label.setText(Localizer.get().agent_page_running)
        self._history_scroll_timer.start(0)

    def _append_thinking_delta(self, text: str) -> None:
        """把后端明确标记的思考增量放进折叠过程条。"""
        delta = str(text or "")
        if not delta:
            return
        turn = self._ensure_assistant_turn()
        turn.append_thinking_text(delta)
        self.activity_widget.label.setText(Localizer.get().agent_page_running)
        self._history_scroll_timer.start(0)

    def _complete_reply(self, text: str) -> None:
        """用最终响应校正流式消息；无增量时退回一次性追加。"""
        final_text = str(text or "")
        turn = self._assistant_turn
        if turn is None:
            self._append(final_text, role="assistant")
        else:
            turn.finish_thinking()
            turn.set_text(final_text)
        self._stream_message = None
        self._reply_rendered = True

    def start_new_task(self) -> None:
        """清空当前会话，回到空态。运行中的回合先请求停止。"""
        if self._worker is not None and self._worker.isRunning():
            self._reset_after_worker = True
            self._worker.cancel()
            return
        self._clear_session()

    def _clear_session(self) -> None:
        """在 Worker 结束后同时清空服务上下文和界面。"""
        if self._confirmation_dialog is not None:
            dialog = self._confirmation_dialog
            dialog.reject()
            self._confirmation_dialog = None
        self._service.reset()
        self._reset_after_worker = False
        if self._round_header is not None:
            self._round_header.stop()
            self._round_header = None
        self._running_tool_widgets.clear()
        self._stream_message = None
        self._assistant_turn = None
        self._reply_rendered = False
        # history_widgets 有意不暴露轮次头，清空时直接遍历布局以免留下旧分隔项。
        for index in range(self.history_layout.count() - 1, -1, -1):
            widget = self.history_layout.itemAt(index).widget()
            if widget is None or widget is self.activity_widget:
                continue
            self.history_layout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        self.activity_widget.set_running(False)
        self.status_label.setText("")
        self._last_message = ""
        self._auto_follow = True
        self.conversation_stack.setCurrentWidget(self.empty_state)
        self._update_send_button()

    def retry_last_message(self) -> None:
        """重发上一条用户消息；失败条自身保留在时间线里。"""
        if not self._last_message:
            return
        if self._worker is not None and self._worker.isRunning():
            return
        self.input_box.setPlainText(self._last_message)
        self.send_message()

    def _append_tool_start(self, name: str) -> AgentToolWidget:
        localizer = Localizer.get()
        label = getattr(localizer, f"agent_page_tool_{name}", name)
        widget = AgentToolWidget(
            name,
            label,
            localizer.agent_page_tool_running,
            localizer.agent_page_tool_done,
            localizer.agent_page_tool_failed,
            self.history_content,
        )
        if self._assistant_turn is not None:
            self._assistant_turn.add_tool_widget(widget)
        else:
            # 保留无网络测试和旧调用方直接注入工具事件时的平铺行为。
            self._add_history_widget(widget)
        self._running_tool_widgets.append(widget)
        self.activity_widget.label.setText(f"{localizer.agent_page_tool_calling}：{label}")
        return widget

    def _finish_tool(
        self,
        name: str,
        success: bool,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        widget = next(
            (
                candidate
                for candidate in reversed(self._running_tool_widgets)
                if candidate.tool_name == name
            ),
            None,
        )
        if widget is None:
            widget = self._append_tool_start(name)
        detail = str(message or "")
        if data:
            detail = f"{detail}\n{json.dumps(data, ensure_ascii=False, indent=2, default=str)}"
        widget.complete(success, detail)
        self._running_tool_widgets = [
            candidate
            for candidate in self._running_tool_widgets
            if candidate is not widget
        ]
        self._history_scroll_timer.start(0)

    def send_message(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        message = self.input_box.toPlainText().strip()
        if not message:
            return
        # 接口未选定时不清空输入框，否则用户刚打的内容会凭空消失。
        if int(self.platform_combo.currentData() if self.platform_combo.currentData() is not None else -1) < 0:
            self.status_label.setText(Localizer.get().agent_page_platform_unset)
            return
        self.input_box.clear()
        localizer = Localizer.get()
        # 记住原文，失败后「点击重试」直接复用，不必让用户重新输入。
        self._last_message = message
        self._stream_message = None
        self._assistant_turn = None
        self._reply_rendered = False
        # 新回合从底部开始，无论用户此前滚到哪里。
        self._auto_follow = True
        if self._round_header is not None:
            self._round_header.stop()
        self._round_header = AgentRoundHeader(self.history_content)
        self._add_history_widget(self._round_header)
        self._append(message, role="user")
        self.status_label.setText(localizer.agent_page_running)
        self.activity_widget.set_running(True, localizer.agent_page_running)
        self.send_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self._worker = AgentWorker(
            self._service,
            message,
            str(self.thinking_combo.currentData() or "OFF"),
        )
        self._worker.event.connect(self._on_worker_event)
        self._worker.confirmation_requested.connect(self._on_confirmation_requested)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def stop_request(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self.status_label.setText(Localizer.get().agent_page_cancelled)

    def _on_confirmation_requested(self, name: str, payload: dict[str, Any]) -> None:
        worker = self._worker
        if worker is None:
            return
        localizer = Localizer.get()
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        if name == "unpack_rpa_files":
            message = localizer.agent_page_unpack_confirmation.format(
                game_dir=data.get("game_dir", ""),
                count=data.get("count", 0),
            )
        else:
            message = localizer.agent_page_confirmation_generic.format(tool=name)
        dialog = MessageBox(localizer.agent_page_confirmation_title, message, self)
        dialog.yesButton.setText(localizer.confirm)
        dialog.cancelButton.setText(localizer.cancel)
        self._confirmation_dialog = dialog

        def resolve(approved: bool) -> None:
            if self._confirmation_dialog is not dialog:
                return
            self._confirmation_dialog = None
            worker.resolve_confirmation(approved)

        dialog.accepted.connect(lambda: resolve(True))
        dialog.rejected.connect(lambda: resolve(False))
        QTimer.singleShot(
            int(self._service.confirmation_timeout * 1000),
            lambda: dialog.reject() if self._confirmation_dialog is dialog else None,
        )
        self.status_label.setText(localizer.agent_page_waiting_confirmation)
        self.activity_widget.set_running(False)
        dialog.open()

    def _on_worker_event(self, event_name: str, payload: dict[str, Any]) -> None:
        localizer = Localizer.get()
        if event_name == "request":
            # 新一轮请求代表上一段中间说明已经结束，下一段会创建新的折叠行。
            if self._assistant_turn is not None:
                self._assistant_turn.finish_thinking()
            self._stream_message = self._assistant_turn
            self.activity_widget.label.setText(localizer.agent_page_running)
        elif event_name == "reply_delta":
            if payload.get("thinking") or payload.get("kind") in {"thinking", "reasoning"}:
                self._append_thinking_delta(str(payload.get("text", "")))
            else:
                self._append_reply_delta(str(payload.get("text", "")))
        elif event_name in {"thinking_delta", "reasoning_delta"}:
            self._append_thinking_delta(str(payload.get("text", "")))
        elif event_name == "reply":
            self._complete_reply(str(payload.get("message", "")))
        elif event_name == "tool_start":
            if self._assistant_turn is not None:
                self._assistant_turn.move_answer_to_thinking()
                self._assistant_turn.finish_thinking()
            self._append_tool_start(str(payload.get("name", "")))
        elif event_name == "tool_done":
            if str(payload.get("name", "")) == "set_project" and bool(payload.get("success", False)):
                self._refresh_project_context()
            self._finish_tool(
                str(payload.get("name", "")),
                bool(payload.get("success", False)),
                str(payload.get("message", "")),
                payload.get("data") if isinstance(payload.get("data"), dict) else None,
            )
        elif event_name == "error":
            self.status_label.setText(localizer.agent_page_failed)

    def _on_worker_finished(self, result: Any) -> None:
        localizer = Localizer.get()
        if self._confirmation_dialog is not None:
            dialog = self._confirmation_dialog
            self._confirmation_dialog = None
            dialog.reject()
        reset_after_worker = self._reset_after_worker
        self._worker = None
        if reset_after_worker:
            self._clear_session()
            return
        self.activity_widget.set_running(False)
        self.send_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        for widget in self._running_tool_widgets:
            widget.complete(False, str(getattr(result, "message", "")))
        self._running_tool_widgets.clear()
        if self._round_header is not None:
            self._round_header.stop()
        if getattr(result, "success", False):
            if not self._reply_rendered:
                self._complete_reply(str(result.message))
            self.status_label.setText(localizer.agent_page_done)
        else:
            self._stream_message = None
            self._append(str(result.message), role="error")
            self.status_label.setText(localizer.agent_page_failed)
        self._update_send_button()

    def _update_send_button(self) -> None:
        running = self._worker is not None and self._worker.isRunning()
        current_platform = self.platform_combo.currentData()
        platform_ready = current_platform is not None and int(current_platform) >= 0
        self.send_button.setEnabled(
            bool(self.input_box.toPlainText().strip())
            and platform_ready
            and not running
        )
