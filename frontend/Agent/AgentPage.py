"""Agent 助手页面。

布局取自 LinguaGacha 的 Agent 页：顶部集中展示助手、接口与项目状态，
主体只保留对话区和输入区，让垂直空间尽量留给对话。
"""

from __future__ import annotations

import json
import math
import time
from typing import Any

from PyQt5.QtCore import QPoint, QTimer, Qt, QSize, pyqtSignal
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
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    FlowLayout,
    FluentIcon,
    IconWidget,
    InfoBar,
    MessageBox,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    SingleDirectionScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
    TextBrowser,
    ThemeColor,
    TransparentPushButton,
    TransparentToolButton,
    isDarkTheme,
    qconfig,
)

from base.Base import Base
from frontend.Agent.AgentWorker import AgentToolWorker, AgentWorker
from module.Agent.AgentService import AgentService
from module.Agent.tools.inspection_tools import inspect_translation_project
from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.Renpy.ProjectPaths import RenpyProjectPaths, source_script_counts
from widget.ThemeHelper import (
    get_theme_accent_color,
    mark_toolbox_scroll_area,
    mark_toolbox_widget,
)


# AgentRequester 目前没有导出格式白名单；能力约束暂时保留在 UI，后续任务再下移。
SUPPORTED_FORMATS = {
    str(Base.APIFormat.OPENAI),
    str(Base.APIFormat.ANTHROPIC),
    str(Base.APIFormat.GOOGLE),
}

# 对话区最大宽度。宽屏下保持可读行长，窄屏时随窗口收缩。
CONVERSATION_MAX_WIDTH = 960

# 顶栏思考等级只作用于 Agent 请求；OFF 保持平台默认关闭行为。
THINKING_LEVELS = ("OFF", "LOW", "MEDIUM", "HIGH", "MAX")

# Markdown 正文的最小可读高度；超长内容由外层对话滚动区承载。
MESSAGE_MIN_HEIGHT = 48

# 用户主动上滚超过该距离后，新消息不再抢回滚动位置。
AUTO_FOLLOW_THRESHOLD = 80

# 回复越长，Markdown 全量重排越昂贵；逐步放宽刷新间隔以控制主线程开销。
STREAM_RENDER_MEDIUM_CHARS = 5_000
STREAM_RENDER_SLOW_CHARS = 20_000

# 项目体检快捷操作使用稳定代码，不从模型回复文案反推意图。
ACTION_OPEN_TRANSLATION = "open_translation"
ACTION_ONE_KEY_TRANSLATE = "one_key_translate"
ACTION_OPEN_WORKBENCH = "open_workbench"
ACTION_OPEN_TOOLBOX = "open_toolbox"
ACTION_LIST_RPA = "list_rpa"
ACTION_UNPACK_RPA = "unpack_rpa"
ACTION_SCAN_ERRORS = "scan_errors"

# 彩色 Emoji 无法跟随 Fluent 主题，模型回复只保留文字语义。
DECORATIVE_STATUS_SYMBOLS = (
    "✅",
    "☑️",
    "☑",
    "✔️",
    "✔",
    "❌",
    "⚠️",
    "⚠",
    "📊",
    "🔮",
    "💡",
    "📦",
    "➡️",
    "➡",
    "🟢",
    "🟡",
    "🔴",
)


def clean_agent_display_text(text: str) -> str:
    """移除模型用于装饰的彩色状态符号，保留原有正文和 Markdown。"""
    cleaned = str(text or "")
    for symbol in DECORATIVE_STATUS_SYMBOLS:
        cleaned = cleaned.replace(symbol, "")
    return cleaned


def status_color(state: str) -> QColor:
    """工具状态色。

    运行与完成使用主题色系，失败保留红色语义色。
    """
    if state == "done":
        return ThemeColor.DARK_1.color()
    if state == "failed":
        return QColor("#D96868" if isDarkTheme() else "#C0392B")
    return get_theme_accent_color()


def _qss_rgba(color: QColor, alpha: int) -> str:
    """把当前主题色转换成 Qt 样式表可用的透明色。"""
    return f"rgba({color.red()},{color.green()},{color.blue()},{alpha})"


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


def _coerce_int(value: Any, default: int = 0) -> int:
    """把配置或工具结果中的数字安全转换为整数。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._apply_document_style()

    def _apply_document_style(self) -> None:
        """给文档套主题感知的默认样式：正文加大、标题分级、代码块/引用块有型。

        颜色必须显式给出：应用不随主题切换系统调色板，暗色下 QPalette.Text
        仍是黑色，直接取调色板会让正文变成黑字黑底。
        """
        accent = get_theme_accent_color().name()
        if isDarkTheme():
            text = "#e6e6e6"
            muted = "#9a9a9a"
            code_bg = "rgb(26, 26, 26)"
            code_border = "rgb(58, 58, 58)"
        else:
            text = "#1a1a1a"
            muted = "#6f6f6f"
            code_bg = "rgb(246, 246, 246)"
            code_border = "rgb(226, 226, 226)"
        self.document().setDefaultStyleSheet(
            "body { font-size: 11pt; color: %s; }"
            "h1 { font-size: 16pt; font-weight: bold; margin-top: 14px; margin-bottom: 6px; }"
            "h2 { font-size: 14pt; font-weight: bold; margin-top: 12px; margin-bottom: 6px; }"
            "h3 { font-size: 12.5pt; font-weight: bold; margin-top: 10px; margin-bottom: 4px; }"
            "h4 { font-size: 11.5pt; font-weight: bold; margin-top: 8px; margin-bottom: 4px; }"
            "p { margin: 6px 0; }"
            "pre { font-family: Consolas, 'Courier New', monospace; font-size: 10pt; "
            "background-color: %s; border: 1px solid %s; border-radius: 6px; "
            "padding: 10px; margin: 8px 0; }"
            "code { font-family: Consolas, 'Courier New', monospace; background-color: %s; }"
            "blockquote { border-left: 3px solid %s; margin-left: 4px; padding-left: 10px; "
            "color: %s; }"
            "a { color: %s; }"
            "li { margin: 2px 0; }"
            "hr { border: 0; border-top: 1px solid %s; margin: 10px 0; }"
            % (text, code_bg, code_border, code_bg, accent, muted, accent, code_border)
        )

    def setMarkdown(self, markdown: str) -> None:
        super().setMarkdown(markdown)
        self._format_tables()

    def _format_tables(self) -> None:
        """覆盖 Qt 默认的紧缩表格样式，使表格与正文列对齐。"""
        if isDarkTheme():
            border_color = QColor("#666666")
            header_color = QColor("#444444")
        else:
            border_color = QColor(get_theme_accent_color())
            border_color.setAlpha(64)
            header_color = QColor(get_theme_accent_color())
            header_color.setAlpha(24)
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
        self._apply_document_style()
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
        self._color = get_theme_accent_color()
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
    """圆形头像：明暗反相圆底 + 居中图标，用于区分用户与助手。"""

    SIZE = 28

    def __init__(
        self,
        role: str,
        parent: QWidget | None = None,
        size: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.role = role
        size = int(size or self.SIZE)
        self.setFixedSize(size, size)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)
        self._icon = IconWidget(
            self._icon_source().icon(color=self._icon_color()),
            self,
        )
        self._icon.setFixedSize(max(14, round(size * 0.54)), max(14, round(size * 0.54)))
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
            # 中性灰，避免与助手的强调色抢视觉重心；不依赖调色板。
            return QColor("#6f6f6f" if isDarkTheme() else "#8a8a8a")
        return QColor("#ffffff" if isDarkTheme() else "#000000")

    def _icon_color(self) -> QColor:
        """助手图标与圆底反相，不跟随绿色等强调色。"""
        if self.role == "assistant":
            return QColor("#000000" if isDarkTheme() else "#ffffff")
        return QColor("#ffffff" if isDarkTheme() else "#000000")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._background())
        painter.drawEllipse(self.rect())

    def refresh_theme(self) -> None:
        self._icon.setIcon(self._icon_source().icon(color=self._icon_color()))
        self._icon.update()
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


class AgentBubble(QFrame):
    """用户消息的圆角气泡：主色系半透明底，随明暗主题变化。"""

    RADIUS = 12

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        primary = get_theme_accent_color()
        if isDarkTheme():
            background = QColor(primary)
            background.setAlpha(46)
        else:
            # 亮色主题下把主色大幅兑白，保持文字可读。
            background = QColor(
                round(primary.red() + (255 - primary.red()) * 0.88),
                round(primary.green() + (255 - primary.green()) * 0.88),
                round(primary.blue() + (255 - primary.blue()) * 0.88),
            )
        painter.setPen(Qt.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(self.rect(), self.RADIUS, self.RADIUS)

    def refresh_theme(self) -> None:
        self.update()


class AgentMessageWidget(QWidget):
    """一轮公开消息；用户为右侧气泡，助手为左侧头像 + 文档式正文。"""

    action_requested = pyqtSignal(str)

    def __init__(self, text: str, role: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.role = role
        raw_text = str(text or "")
        self._text = clean_agent_display_text(raw_text) if role == "assistant" else raw_text
        self._thinking_widgets: list[AgentThinkingWidget] = []
        self._tool_widgets: list[AgentToolWidget] = []
        self._active_thinking: AgentThinkingWidget | None = None
        self.action_container: QWidget | None = None
        self.action_buttons: dict[str, PushButton] = {}
        self.setProperty("role", role)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        localizer = Localizer.get()

        if role == "user":
            # 用户：右侧气泡 + 左侧复制按钮，不再重复头像与名字。
            self.avatar = None
            root.addStretch(1)
            self.copy_button = TransparentToolButton(self)
            self.copy_button.setIcon(FluentIcon.COPY)
            self.copy_button.setFixedSize(20, 20)
            self.copy_button.setToolTip(localizer.agent_page_copy)
            self.copy_button.clicked.connect(self._copy_text)
            root.addWidget(self.copy_button, 0, Qt.AlignVCenter)

            self.bubble = AgentBubble(self)
            self.bubble.setMaximumWidth(int(CONVERSATION_MAX_WIDTH * 0.72))
            bubble_layout = QVBoxLayout(self.bubble)
            bubble_layout.setContentsMargins(14, 10, 14, 10)
            bubble_layout.setSpacing(0)

            label = QLabel(self._text, self.bubble)
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setAttribute(Qt.WA_TranslucentBackground, True)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            bubble_layout.addWidget(label)
            self.text_view = label

            root.addWidget(self.bubble, 0, Qt.AlignVCenter)
            self.body = self.bubble
            self.body_layout = bubble_layout
            self.detail_container = QWidget(self.bubble)
            self.detail_layout = QVBoxLayout(self.detail_container)
            self.detail_layout.setContentsMargins(0, 0, 0, 0)
            self.detail_layout.setSpacing(6)
            self.detail_container.hide()
            bubble_layout.addWidget(self.detail_container)
            return

        # 助手：左侧头像 + 正文；复制按钮放在正文右上角，弱化存在感。
        self.avatar = AgentAvatar(role, self)
        root.addWidget(self.avatar, 0, Qt.AlignTop)

        column = QWidget(self)
        column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(8)

        self.detail_container = QWidget(column)
        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_layout.setSpacing(6)
        self.detail_container.hide()
        column_layout.addWidget(self.detail_container)

        text_row = QWidget(column)
        text_row_layout = QHBoxLayout(text_row)
        text_row_layout.setContentsMargins(0, 0, 0, 0)
        text_row_layout.setSpacing(6)

        text_view = AgentMarkdownView(text_row)
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
        text_row_layout.addWidget(text_view, 1)
        self.text_view = text_view

        self.copy_button = TransparentToolButton(text_row)
        self.copy_button.setIcon(FluentIcon.COPY)
        self.copy_button.setFixedSize(20, 20)
        self.copy_button.setToolTip(localizer.agent_page_copy)
        self.copy_button.clicked.connect(self._copy_text)
        text_row_layout.addWidget(self.copy_button, 0, Qt.AlignTop)

        column_layout.addWidget(text_row)
        root.addWidget(column, 1)
        self.body = column
        self.body_layout = column_layout

    @property
    def text(self) -> str:
        """返回当前消息的完整原文，流式渲染和测试共用。"""
        return self._text

    def _copy_text(self) -> None:
        """复制消息全文到剪贴板。"""
        QApplication.clipboard().setText(self.text)
        InfoBar.success(
            Localizer.get().agent_page_copy,
            Localizer.get().agent_page_copied,
            parent=self,
        )

    def set_text(self, text: str) -> None:
        """替换消息正文，保留同一个控件以避免滚动区跳动。"""
        raw_text = str(text or "")
        self._text = (
            clean_agent_display_text(raw_text)
            if self.role == "assistant"
            else raw_text
        )
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

    def set_actions(self, actions: list[tuple[str, str, Any]]) -> None:
        """在助手正文下方显示结构化快捷操作。"""
        if self.role != "assistant":
            return
        if self.action_container is not None:
            self.body_layout.removeWidget(self.action_container)
            self.action_container.setParent(None)
            self.action_container.deleteLater()
            self.action_container = None
        self.action_buttons.clear()
        if not actions:
            return

        container = QWidget(self.body)
        layout = FlowLayout(container, needAni=False, isTight=False)
        layout.setContentsMargins(0, 2, 26, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)
        for index, (code, label, icon) in enumerate(actions):
            button_class = PrimaryPushButton if index == 0 else PushButton
            button = button_class(label, icon=icon, parent=container)
            button.setFixedHeight(32)
            button.clicked.connect(
                lambda _checked=False, value=code: self.action_requested.emit(value)
            )
            self.action_buttons[code] = button
            layout.addWidget(button)
        self.action_container = container
        self.body_layout.addWidget(container)
        self.updateGeometry()

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
        if self.avatar is not None:
            self.avatar.refresh_theme()
        bubble = getattr(self, "bubble", None)
        if bubble is not None:
            bubble.refresh_theme()
        if isinstance(self.text_view, AgentMarkdownView):
            self.text_view.refresh_theme()
        for widget in (*self._thinking_widgets, *self._tool_widgets):
            refresh = getattr(widget, "refresh_theme", None)
            if callable(refresh):
                refresh()


class AgentRoundHeader(QWidget):
    """轮次分隔：居中的轮次与耗时胶囊，运行中每秒刷新。"""

    def __init__(self, parent: QWidget | None = None, round_number: int = 0) -> None:
        super().__init__(parent)
        self._started_at = time.monotonic()
        self._running = True
        self._round_number = int(round_number or 0)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 10, 0, 2)
        row.setSpacing(10)

        # 两侧发丝线托住居中胶囊，替代单调的整条横线。
        self.line_left = QFrame(self)
        self.line_left.setFixedHeight(1)
        row.addWidget(self.line_left, 1)

        self.pill = QFrame(self)
        self.pill.setObjectName("agentRoundPill")
        pill_layout = QHBoxLayout(self.pill)
        pill_layout.setContentsMargins(14, 4, 14, 4)
        pill_layout.setSpacing(8)

        self.round_label = CaptionLabel(
            (
                Localizer.get().agent_page_round.format(round=self._round_number)
                if self._round_number > 0
                else ""
            ),
            self.pill,
        )
        pill_layout.addWidget(self.round_label, 0)

        self.pill_separator = QFrame(self.pill)
        self.pill_separator.setFixedSize(1, 12)
        pill_layout.addWidget(self.pill_separator, 0, Qt.AlignVCenter)

        self.elapsed_label = CaptionLabel(format_elapsed(0), self.pill)
        pill_layout.addWidget(self.elapsed_label, 0)

        row.addWidget(self.pill, 0)

        self.line_right = QFrame(self)
        self.line_right.setFixedHeight(1)
        row.addWidget(self.line_right, 1)

        self._apply_theme()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _apply_theme(self) -> None:
        accent = get_theme_accent_color()
        if isDarkTheme():
            self.pill.setStyleSheet(
                "QFrame#agentRoundPill {"
                f" background-color: {_qss_rgba(accent, 13)};"
                f" border: 1px solid {_qss_rgba(accent, 25)};"
                " border-radius: 12px; }"
            )
            line_style = (
                f"background-color: {_qss_rgba(accent, 38)}; border: none;"
            )
        else:
            self.pill.setStyleSheet(
                "QFrame#agentRoundPill {"
                f" background-color: {_qss_rgba(accent, 18)};"
                f" border: 1px solid {_qss_rgba(accent, 42)};"
                " border-radius: 12px; }"
            )
            line_style = (
                f"background-color: {_qss_rgba(accent, 54)}; border: none;"
            )
        self.line_left.setStyleSheet(line_style)
        self.line_right.setStyleSheet(line_style)
        self.pill_separator.setStyleSheet(line_style)

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

    def refresh_theme(self) -> None:
        self._apply_theme()


class AgentInsetCard(CardWidget):
    """轻量内嵌面板：暗色保持中性，亮色使用低透明主题色。"""

    def _normalBackgroundColor(self) -> QColor:
        if isDarkTheme():
            return QColor(0, 0, 0, 30)
        color = QColor(get_theme_accent_color())
        color.setAlpha(20)
        return color

    def _hoverBackgroundColor(self) -> QColor:
        if isDarkTheme():
            return QColor(0, 0, 0, 42)
        color = QColor(get_theme_accent_color())
        color.setAlpha(32)
        return color

    def _pressedBackgroundColor(self) -> QColor:
        if isDarkTheme():
            return self._normalBackgroundColor()
        color = QColor(get_theme_accent_color())
        color.setAlpha(26)
        return color

    def refresh_theme(self) -> None:
        self._updateBackgroundColor()


class AgentToolWidget(AgentInsetCard):
    """单行高度的工具执行条目，整行可点击展开结果。"""

    MAX_DETAIL_CHARS = 2000
    MAX_TOOLTIP_CHARS = 20000

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
        root.setContentsMargins(10, 0, 8, 0)
        root.setSpacing(0)

        header = QWidget(self)
        header.setFixedHeight(34)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self.status_dot = AgentStatusDot(header)
        self.status_dot.setProperty("state", self._state)
        header_layout.addWidget(self.status_dot, 0, Qt.AlignVCenter)

        # 工具图标放进小圆角底片，形成稳定的视觉锚点。
        self.icon_chip = QFrame(header)
        self.icon_chip.setObjectName("agentToolIconChip")
        self.icon_chip.setFixedSize(22, 22)
        chip_layout = QHBoxLayout(self.icon_chip)
        chip_layout.setContentsMargins(0, 0, 0, 0)
        chip_layout.setAlignment(Qt.AlignCenter)
        self.icon_widget = IconWidget(self._tool_icon(), self.icon_chip)
        self.icon_widget.setFixedSize(14, 14)
        chip_layout.addWidget(self.icon_widget)
        header_layout.addWidget(self.icon_chip, 0, Qt.AlignVCenter)

        self.name_label = CaptionLabel(tool_label, header)
        header_layout.addWidget(self.name_label, 0, Qt.AlignVCenter)

        self.status_label = CaptionLabel(running_text, header)
        self.status_label.setProperty("state", self._state)
        header_layout.addWidget(self.status_label, 0, Qt.AlignVCenter)
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

        self.detail_label = QTextBrowser(self)
        self.detail_label.setReadOnly(True)
        self.detail_label.setOpenLinks(False)
        self.detail_label.setOpenExternalLinks(False)
        self.detail_label.setFrameShape(QFrame.NoFrame)
        self.detail_label.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.detail_label.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_label.document().setDocumentMargin(8)
        self.detail_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.detail_label.setMaximumHeight(360)
        self.detail_label.hide()
        root.addWidget(self.detail_label)
        self._apply_detail_style()
        self._refresh_state_colors()

    def _tool_icon(self):
        """按工具名映射图标；未知工具退回信息图标。"""
        icons = {
            "unpack_rpa_files": FluentIcon.ZIP_FOLDER,
            "list_rpa_files": FluentIcon.ZIP_FOLDER,
            "scan_script_errors": FluentIcon.SEARCH,
            "get_project_info": FluentIcon.INFO,
            "inspect_translation_project": FluentIcon.SEARCH,
            "set_project": FluentIcon.FOLDER,
            "optimize_old_new_translations": FluentIcon.CODE,
        }
        return icons.get(self.tool_name, FluentIcon.INFO)

    def _apply_detail_style(self) -> None:
        """详情区做等宽字体的内嵌面板，图标底片随主题刷新。"""
        if isDarkTheme():
            self.icon_chip.setStyleSheet(
                "QFrame#agentToolIconChip { background-color: rgba(255,255,255,0.07);"
                " border-radius: 6px; }"
            )
            self.detail_label.setStyleSheet(
                "color: #e6e6e6; background-color: rgba(0,0,0,0.28);"
                "border: 1px solid rgba(255,255,255,0.06); border-radius: 6px;"
                "font-family: Consolas, 'Courier New', monospace;"
            )
        else:
            accent = get_theme_accent_color()
            self.icon_chip.setStyleSheet(
                "QFrame#agentToolIconChip {"
                f" background-color: {_qss_rgba(accent, 28)};"
                " border-radius: 6px; }"
            )
            self.detail_label.setStyleSheet(
                "color: #1a1a1a; background-color: rgba(255,255,255,0.82);"
                f"border: 1px solid {_qss_rgba(accent, 46)}; border-radius: 6px;"
                "font-family: Consolas, 'Courier New', monospace;"
            )

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
        self.status_label.setText(f"{status_text}  {elapsed}")
        full_detail = str(message or "")
        if len(full_detail) > self.MAX_DETAIL_CHARS:
            self.detail_label.setPlainText(
                f"{full_detail[:self.MAX_DETAIL_CHARS]}\n…\n"
                + Localizer.get().agent_page_tool_detail_truncated.format(
                    shown=self.MAX_DETAIL_CHARS,
                    total=len(full_detail),
                )
            )
            self.detail_label.setToolTip(full_detail[:self.MAX_TOOLTIP_CHARS])
        else:
            self.detail_label.setPlainText(full_detail)
            self.detail_label.setToolTip("")
        has_detail = bool(full_detail.strip())
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
            # 按卡片当前宽度计算换行高度，避免使用隐藏状态下的窄宽度锁出大片空白。
            margins = self.layout().contentsMargins()
            available_width = max(
                1,
                self.width() - margins.left() - margins.right(),
            )
            document = self.detail_label.document().clone()
            document.setTextWidth(max(1, available_width - 16))
            detail_height = math.ceil(document.size().height()) + 2
            self.detail_label.setMinimumHeight(
                min(360, max(0, detail_height))
            )
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
        super().refresh_theme()
        self._apply_detail_style()
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
        self.status_dot.hide()
        self.name_label.setText(localizer.agent_page_thinking_process)
        self.toggle_button.setToolTip(localizer.agent_page_tool_expand)
        # 思考过程与工具调用视觉区分：思考图标 + 弱化的名称色。
        self.icon_widget.setIcon(FluentIcon.HELP)
        self._apply_thinking_muted()

    def _apply_thinking_muted(self) -> None:
        """思考条用中性灰，不与工具的成功/失败语义色混淆。"""
        muted = QColor("#8f8f8f" if isDarkTheme() else "#6f6f6f")
        self.name_label.setTextColor(muted, muted)

    def _refresh_state_colors(self) -> None:
        if self._state == "done":
            muted = QColor("#8f8f8f" if isDarkTheme() else "#6f6f6f")
            self.status_dot.set_color(muted)
            self.status_label.setTextColor(muted, muted)
            return
        super()._refresh_state_colors()

    def refresh_theme(self) -> None:
        self._apply_thinking_muted()
        super().refresh_theme()

    def append_text(self, text: str) -> None:
        if not text:
            return
        self._text += str(text)
        self.detail_label.setPlainText(self._text)
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
    """当前回合等待模型响应时的轻量状态胶囊。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 8)
        layout.setSpacing(0)

        self.pill = QFrame(self)
        self.pill.setObjectName("agentActivityPill")
        pill_layout = QHBoxLayout(self.pill)
        pill_layout.setContentsMargins(12, 5, 12, 5)
        pill_layout.setSpacing(8)
        self.dot = AgentStatusDot(self.pill)
        pill_layout.addWidget(self.dot, 0, Qt.AlignVCenter)
        self.label = CaptionLabel("", self.pill)
        pill_layout.addWidget(self.label)

        layout.addWidget(self.pill, 0)
        layout.addStretch(1)
        self._apply_theme()
        self.hide()

    def _apply_theme(self) -> None:
        if isDarkTheme():
            self.pill.setStyleSheet(
                "QFrame#agentActivityPill { background-color: rgba(255,255,255,0.05);"
                " border: 1px solid rgba(255,255,255,0.08); border-radius: 14px; }"
            )
        else:
            self.pill.setStyleSheet(
                "QFrame#agentActivityPill { background-color: rgba(0,0,0,0.04);"
                " border: 1px solid rgba(0,0,0,0.08); border-radius: 14px; }"
            )

    def set_running(self, running: bool, text: str = "") -> None:
        self.label.setText(text)
        self.setVisible(running)

    def refresh_theme(self) -> None:
        self._apply_theme()
        self.dot.set_color(status_color("running"))


class AgentSuggestionCard(CardWidget):
    """空态的块状建议卡：图标 + 标题 + 描述，整卡可点击。"""

    clicked = pyqtSignal()

    def __init__(
        self,
        title: str,
        description: str,
        icon_value,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = str(title or "")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(72)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 12, 10)
        row.setSpacing(12)

        icon = IconWidget(icon_value, self)
        icon.setFixedSize(18, 18)
        row.addWidget(icon, 0, Qt.AlignVCenter)

        text_column = QWidget(self)
        text_column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        text_layout = QVBoxLayout(text_column)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        self.title_label = StrongBodyLabel(self._title, text_column)
        self.title_label.setMinimumHeight(20)
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.description_label = CaptionLabel(str(description or ""), text_column)
        self.description_label.setMinimumHeight(18)
        self.description_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.description_label.setWordWrap(True)
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.description_label)
        row.addWidget(text_column, 1, Qt.AlignVCenter)

        chevron = IconWidget(FluentIcon.CHEVRON_RIGHT, self)
        chevron.setFixedSize(14, 14)
        row.addWidget(chevron, 0, Qt.AlignVCenter)

    def text(self) -> str:
        """兼容旧测试对按钮文案的读取。"""
        return self._title

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class AgentEmptyState(QWidget):
    """空会话的起始视图：圆底徽章 + 工程诊断 + 块状建议卡。"""

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

        self.brand_badge = AgentAvatar("assistant", intro, size=48)
        intro_layout.addWidget(self.brand_badge, 0, Qt.AlignHCenter)

        self.title_label = SubtitleLabel(localizer.agent_page_empty_title, intro)
        intro_layout.addWidget(self.title_label, 0, Qt.AlignHCenter)

        self.description_label = CaptionLabel(localizer.agent_page_empty_description, intro)
        self.description_label.setWordWrap(True)
        self.description_label.setMaximumWidth(560)
        self.description_label.setMinimumHeight(20)
        self.description_label.setAlignment(Qt.AlignCenter)
        intro_layout.addWidget(self.description_label, 0, Qt.AlignHCenter)
        outer.addWidget(intro, 0, Qt.AlignHCenter)

        # 工程就绪诊断卡保持轻量，只展示体检工具返回的关键状态。
        self.preflight_card = CardWidget(self)
        self.preflight_card.setBorderRadius(8)
        self.preflight_card.setFixedWidth(560)
        preflight_layout = QVBoxLayout(self.preflight_card)
        preflight_layout.setContentsMargins(14, 12, 14, 12)
        preflight_layout.setSpacing(8)

        preflight_header = QHBoxLayout()
        preflight_header.setContentsMargins(0, 0, 0, 0)
        preflight_header.setSpacing(8)
        self.preflight_title_label = StrongBodyLabel(
            localizer.agent_page_tool_inspect_translation_project,
            self.preflight_card,
        )
        preflight_header.addWidget(self.preflight_title_label)
        preflight_header.addStretch(1)
        self.preflight_project_label = QLabel("", self.preflight_card)
        self.preflight_project_label.setAlignment(Qt.AlignCenter)
        self.preflight_project_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        preflight_header.addWidget(self.preflight_project_label)
        preflight_layout.addLayout(preflight_header)

        path_row = QHBoxLayout()
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.setSpacing(8)
        path_caption = CaptionLabel(localizer.workbench_project_folder, self.preflight_card)
        path_row.addWidget(path_caption, 0)
        self.preflight_path_label = QLabel("", self.preflight_card)
        self.preflight_path_label.setWordWrap(True)
        self.preflight_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_row.addWidget(self.preflight_path_label, 1)
        preflight_layout.addLayout(path_row)

        metrics = QGridLayout()
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setHorizontalSpacing(16)
        metrics.setVerticalSpacing(8)
        self.preflight_value_labels: dict[str, QLabel] = {}
        for index, (key, caption) in enumerate(
            (
                ("rpa", localizer.agent_page_tool_list_rpa_files),
                ("scripts", localizer.agent_page_tool_scan_script_errors),
                ("tl", localizer.workbench_tl_folder),
                ("worldbook", localizer.workbench_worldbuilding),
            )
        ):
            field = QWidget(self.preflight_card)
            field_layout = QVBoxLayout(field)
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.setSpacing(2)
            field_layout.addWidget(CaptionLabel(caption, field))
            value_label = QLabel("", field)
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.preflight_value_labels[key] = value_label
            field_layout.addWidget(value_label)
            metrics.addWidget(field, index // 2, index % 2)
        preflight_layout.addLayout(metrics)
        outer.addWidget(self.preflight_card, 0, Qt.AlignHCenter)

        suggestions = QWidget(self)
        suggestions.setFixedWidth(560)
        self.suggestions = suggestions
        grid = QVBoxLayout(suggestions)
        grid.setContentsMargins(0, 20, 0, 0)
        grid.setSpacing(8)

        self.suggestion_buttons: list[AgentSuggestionCard] = []
        entries = (
            (
                localizer.agent_page_suggestion_project,
                localizer.agent_page_suggestion_project_desc,
                FluentIcon.SEARCH,
            ),
            (
                localizer.agent_page_suggestion_rpa,
                localizer.agent_page_suggestion_rpa_desc,
                FluentIcon.ZIP_FOLDER,
            ),
            (
                localizer.agent_page_suggestion_errors,
                localizer.agent_page_suggestion_errors_desc,
                FluentIcon.SEARCH,
            ),
            (
                localizer.agent_page_suggestion_old_new,
                localizer.agent_page_suggestion_old_new_desc,
                FluentIcon.CODE,
            ),
        )
        for text, description, icon_value in entries:
            card = AgentSuggestionCard(text, description, icon_value, suggestions)
            card.clicked.connect(
                lambda value=text: self.suggestion_requested.emit(value)
            )
            self.suggestion_buttons.append(card)
            grid.addWidget(card)
        outer.addWidget(suggestions, 0, Qt.AlignHCenter)
        outer.addStretch(2)

        self._preflight_project_key = None
        self._refresh_preflight()

    def _fallback_preflight_data(self, paths: RenpyProjectPaths) -> dict[str, Any]:
        """体检工具异常时仅用文件系统信息维持卡片可读性。"""
        tl_language_dir = getattr(paths, "tl_language_dir", paths.game_dir / "tl")
        output_dir = getattr(
            paths,
            "translation_output_dir",
            paths.project_root / "RenpyBox_Translation",
        )
        try:
            rpa_paths = sorted(
                paths.game_dir.glob("*.rpa"),
                key=lambda item: item.name.casefold(),
            )
            rpy_count, rpyc_count = source_script_counts(paths)
            tl_file_count = (
                sum(1 for _ in tl_language_dir.rglob("*.rpy"))
                if tl_language_dir.is_dir()
                else 0
            )
            cache_dir = output_dir / "cache"
            cache_exists = any(
                (cache_dir / name).is_file()
                for name in ("cache.db", "project.json", "items.json")
            )
        except (AttributeError, OSError, RuntimeError):
            rpa_paths = []
            rpy_count = rpyc_count = tl_file_count = 0
            cache_exists = False
        return {
            "files": {
                "rpa_count": len(rpa_paths),
                "rpy_count": rpy_count,
                "rpyc_count": rpyc_count,
                "tl_file_count": tl_file_count,
                "unpack_required": bool(rpa_paths) and not (rpy_count or rpyc_count),
                "rpa_names": [item.name for item in rpa_paths],
            },
            "cache": {"exists": cache_exists, "item_count": 0},
            "assets": {},
        }

    def _refresh_preflight(self, config: Config | None = None) -> None:
        """刷新当前工程的诊断指标，不触碰建议卡结构。"""
        localizer = Localizer.get()
        current = config or Config().load()
        paths = RenpyProjectPaths.from_config(current)
        if paths is None or not paths.game_dir.is_dir():
            if self._preflight_project_key == "":
                return
            self._preflight_project_key = ""
            self.preflight_project_label.setText(localizer.agent_page_project_unset)
            self.preflight_path_label.setText(localizer.agent_project_not_set)
            for value_label in self.preflight_value_labels.values():
                value_label.setText(localizer.workbench_not_set)
                value_label.setStyleSheet(
                    "background: rgba(148, 163, 184, 0.12); color: #64748B; "
                    "border-radius: 4px; padding: 2px 6px;"
                )
            return

        project_key = getattr(paths, "project_key", str(paths.project_root))
        if self._preflight_project_key == project_key:
            return
        self._preflight_project_key = project_key

        try:
            result = inspect_translation_project(config=current)
            data = getattr(result, "data", {})
            if not isinstance(data, dict) or not data:
                data = self._fallback_preflight_data(paths)
        except Exception:
            data = self._fallback_preflight_data(paths)

        files = data.get("files", {})
        assets = data.get("assets", {})
        rpa_count = int(files.get("rpa_count", 0) or 0)
        rpa_names = files.get("rpa_names") or []
        if not rpa_names:
            try:
                rpa_names = sorted(
                    item.name for item in paths.game_dir.glob("*.rpa")
                )
            except (AttributeError, OSError, RuntimeError):
                rpa_names = []
        rpa_files = localizer.list_separator.join(rpa_names)
        if not rpa_files:
            rpa_files = localizer.workbench_none
        rpa_text = (
            (
                f"{localizer.agent_page_tool_unpack_rpa_files}\n"
                f"{localizer.agent_rpa_found.format(count=rpa_count, files=rpa_files)}"
            )
            if rpa_count
            else localizer.agent_rpa_not_found
        )
        rpy_count = int(files.get("rpy_count", 0) or 0)
        rpyc_count = int(files.get("rpyc_count", 0) or 0)
        scripts_text = (
            localizer.onekey_found_rpy_files_rpyc_files.format(
                rpy_count=rpy_count,
                rpyc_count=rpyc_count,
            )
            if rpy_count or rpyc_count
            else localizer.agent_inspection_action_check_project_files
        )
        tl_file_count = int(files.get("tl_file_count", 0) or 0)
        tl_status = (
            localizer.onekey_existing_translation_detected_files.format(
                rpy_count=tl_file_count
            )
            if tl_file_count
            else localizer.workbench_not_set
        )
        worldbook_status = (
            localizer.workbench_enabled
            if assets.get("has_effective_assets") or assets.get("worldbook_draft")
            else localizer.workbench_not_enabled
        )
        worldbook_text = localizer.workbench_draft_summary.format(
            worldbook_status=worldbook_status,
            draft_count=int(assets.get("character_draft_count", 0) or 0),
            scope=localizer.current_scope,
        )

        self.preflight_project_label.setText(
            localizer.agent_page_project_context.format(
                name=paths.project_root.name,
                language=paths.language,
            )
        )
        self.preflight_path_label.setText(str(paths.project_root))
        self.preflight_path_label.setToolTip(str(paths.project_root))
        tl_language_dir = getattr(paths, "tl_language_dir", paths.game_dir / "tl")
        unpack_required = bool(files.get("unpack_required"))
        rpa_tone = "warning" if unpack_required else "success" if rpa_count else "neutral"
        scripts_tone = "success" if rpy_count else "warning" if rpyc_count else "neutral"
        tl_tone = "success" if tl_file_count else "neutral"
        worldbook_tone = (
            "success"
            if assets.get("has_effective_assets") or assets.get("worldbook_draft")
            else "neutral"
        )
        values = {
            "rpa": (rpa_text, rpa_tone),
            "scripts": (scripts_text, scripts_tone),
            "tl": (f"{tl_language_dir}\n{tl_status}", tl_tone),
            "worldbook": (worldbook_text, worldbook_tone),
        }
        for key, (text, tone) in values.items():
            value_label = self.preflight_value_labels[key]
            value_label.setText(text)
            if tone == "warning":
                style = (
                    "background: rgba(245, 158, 11, 0.12); color: #B45309; "
                    "border-radius: 4px; padding: 2px 6px;"
                )
            elif tone == "success":
                style = (
                    "background: rgba(16, 185, 129, 0.12); color: #047857; "
                    "border-radius: 4px; padding: 2px 6px;"
                )
            else:
                style = (
                    "background: rgba(148, 163, 184, 0.12); color: #64748B; "
                    "border-radius: 4px; padding: 2px 6px;"
                )
            value_label.setStyleSheet(style)

    def refresh_theme(self) -> None:
        self.brand_badge.refresh_theme()


class AgentPage(Base, QWidget):
    """提供对话输入、工具执行反馈与 Agent 接口选择。"""

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)

        self._window = parent
        self._service = AgentService()
        self._worker: AgentWorker | AgentToolWorker | None = None
        self._platform_ids: list[int] = []
        self._running_tool_widgets: list[AgentToolWidget] = []
        self._round_header: AgentRoundHeader | None = None
        self._stream_message: AgentMessageWidget | None = None
        self._assistant_turn: AgentMessageWidget | None = None
        self._reply_rendered = False
        self._pending_reply_actions: list[tuple[str, str, Any]] = []
        self._project_actions: list[tuple[str, str, Any]] = []
        self._project_actions_key = ""
        self._auto_follow = True
        self._reset_after_worker = False
        self._confirmation_dialog: MessageBox | None = None

        self._last_message = ""
        self._round_count = 0

        # 流式增量渲染节流：合并高频 delta，限制 Markdown 全量重排次数。
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(50)
        self._render_timer.timeout.connect(self._flush_pending_deltas)
        self._pending_reply_text = ""
        self._pending_thinking_text = ""

        self.root = QVBoxLayout(self)
        # 收窄页面边距，把主要空间留给对话。
        self.root.setContentsMargins(16, 12, 16, 12)
        self.root.setSpacing(8)
        self._build_topbar()
        self._build_conversation()
        self._build_composer()

        qconfig.themeChanged.connect(self._on_theme_changed)
        qconfig.themeColorChanged.connect(self._on_theme_changed)
        self.refresh_platforms()

    def _build_topbar(self) -> None:
        """顶栏：身份组 | 接口选择 | 项目胶囊 | 设置弹层 | 新任务。"""
        localizer = Localizer.get()
        bar = CardWidget(self)
        self.topbar = bar
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 7, 10, 7)
        layout.setSpacing(8)

        self.brand_avatar = AgentAvatar("assistant", bar)
        layout.addWidget(self.brand_avatar, 0, Qt.AlignVCenter)

        self.title_label = SubtitleLabel(localizer.agent_page_title, bar)
        layout.addWidget(self.title_label, 0, Qt.AlignVCenter)

        self.topbar_divider = QFrame(bar)
        self.topbar_divider.setFixedSize(1, 22)
        layout.addWidget(self.topbar_divider, 0, Qt.AlignVCenter)

        self.platform_combo = ComboBox(bar)
        self.platform_combo.setMinimumWidth(140)
        self.platform_combo.setMaximumWidth(240)
        self.platform_combo.setFixedHeight(30)
        self.platform_combo.currentIndexChanged.connect(self._platform_changed)
        layout.addWidget(self.platform_combo, 0)

        layout.addStretch(1)

        self.project_label = QLabel("", bar)
        self.project_label.setMaximumWidth(220)
        self.project_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.project_label, 0, Qt.AlignVCenter)

        self.settings_button = TransparentToolButton(bar)
        self.settings_button.setIcon(FluentIcon.SETTING)
        self.settings_button.setFixedSize(30, 30)
        self.settings_button.setToolTip(localizer.agent_page_settings_title)
        self.settings_button.clicked.connect(self._open_settings_menu)
        layout.addWidget(self.settings_button, 0)

        self.new_task_button = TransparentPushButton(
            localizer.agent_page_new_task,
            bar,
            FluentIcon.ADD,
        )
        self.new_task_button.setFixedHeight(30)
        self.new_task_button.clicked.connect(self.start_new_task)
        layout.addWidget(self.new_task_button, 0)
        self.root.addWidget(bar)

        self._build_settings_menu()
        self._apply_project_pill_style()

        # 兼容旧引用：description_label 曾是页头描述，现由项目标签承担。
        self.description_label = self.project_label

    def _build_settings_menu(self) -> None:
        """次要设置收进弹层：思考等级与接口刷新。"""
        localizer = Localizer.get()
        self.settings_menu = RoundMenu(parent=self)

        panel = QWidget()
        # 固定表单宽度，长文案与下拉框纵向排列，避免中英文互相挤压。
        panel.setFixedWidth(280)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        panel_layout.setSpacing(10)

        title_caption = StrongBodyLabel(localizer.agent_page_settings_title, panel)
        panel_layout.addWidget(title_caption)

        thinking_caption = CaptionLabel(
            localizer.platform_edit_page_thinking_title,
            panel,
        )
        panel_layout.addWidget(thinking_caption)

        self.thinking_combo = ComboBox(panel)
        self.thinking_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
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
        panel_layout.addWidget(self.thinking_combo)

        self.refresh_button = PushButton(
            localizer.agent_page_settings_refresh,
            panel,
            FluentIcon.SYNC,
        )
        self.refresh_button.clicked.connect(self.refresh_platforms)
        panel_layout.addWidget(self.refresh_button)

        # 解包确认开关：勾选「不再询问」后在这里重新打开确认。
        self.unpack_confirm_check = CheckBox(
            localizer.agent_page_settings_unpack_confirm,
            panel,
        )
        self.unpack_confirm_check.setChecked(
            not bool(getattr(Config().load(), "agent_unpack_auto_confirm", False))
        )
        self.unpack_confirm_check.stateChanged.connect(self._unpack_confirm_changed)
        panel_layout.addWidget(self.unpack_confirm_check)

        panel.adjustSize()
        self.settings_panel = panel
        self.settings_menu.addWidget(panel, selectable=False)
        # 菜单内边距 + 面板固定宽度，避免内容被裁。
        self.settings_menu.setMinimumWidth(panel.width() + 16)

    def _unpack_confirm_changed(self, state: int) -> None:
        """解包前确认开关：写入 agent_unpack_auto_confirm（取反）。"""
        config = Config().load()
        config.agent_unpack_auto_confirm = not bool(state)
        config.save()

    def _open_settings_menu(self) -> None:
        """在设置按钮下方弹出设置菜单。"""
        if self.settings_menu is None:
            return
        position = self.settings_button.mapToGlobal(
            QPoint(0, self.settings_button.height() + 6)
        )
        self.settings_menu.exec(position)

    def _apply_project_pill_style(self) -> None:
        """项目上下文胶囊：显式主题色，不依赖系统调色板（高分屏/暗色下会返回黑色）。"""
        if isDarkTheme():
            self.topbar_divider.setStyleSheet(
                "background-color: rgba(255,255,255,0.14); border: none;"
            )
            self.project_label.setStyleSheet(
                "background-color: rgba(255,255,255,0.08);"
                "border: 1px solid rgba(255,255,255,0.14);"
                "border-radius: 11px; padding: 2px 10px;"
                "color: #b6b6b6;"
            )
        else:
            self.topbar_divider.setStyleSheet(
                "background-color: rgba(0,0,0,0.12); border: none;"
            )
            self.project_label.setStyleSheet(
                "background-color: rgba(0,0,0,0.05);"
                "border: 1px solid rgba(0,0,0,0.10);"
                "border-radius: 11px; padding: 2px 10px;"
                "color: #555555;"
            )

    def _build_conversation(self) -> None:
        localizer = Localizer.get()
        self.conversation_card = CardWidget(self)
        conversation_layout = QGridLayout(self.conversation_card)
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
        self.history_layout.setContentsMargins(18, 18, 18, 22)
        self.history_layout.setSpacing(14)
        self.history_layout.addStretch(1)
        self.history.setWidget(self.history_content)
        self.history.enableTransparentBackground()
        self.conversation_stack.addWidget(self.history)
        self.conversation_stack.setCurrentWidget(self.empty_state)
        conversation_layout.addWidget(self.conversation_stack, 0, 0)

        # 用户上滚时提供一个固定的回到底部入口，不打断当前阅读位置。
        self.scroll_latest_button = TransparentToolButton(self.conversation_card)
        self.scroll_latest_button.setIcon(FluentIcon.CHEVRON_DOWN_MED)
        self.scroll_latest_button.setFixedSize(32, 32)
        self.scroll_latest_button.setToolTip(localizer.agent_page_scroll_latest)
        self.scroll_latest_button.setAccessibleName(localizer.agent_page_scroll_latest)
        self.scroll_latest_button.clicked.connect(self._scroll_to_latest)
        self.scroll_latest_button.hide()
        conversation_layout.addWidget(
            self.scroll_latest_button,
            0,
            0,
            Qt.AlignRight | Qt.AlignBottom,
        )
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
        self.input_box.setObjectName("agentInput")
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
        footer_layout.setSpacing(8)

        self.hint_label = CaptionLabel(localizer.agent_page_send_hint, footer)
        footer_layout.addWidget(self.hint_label, 0)
        footer_layout.addStretch(1)

        self.status_label = CaptionLabel("", footer)
        footer_layout.addWidget(self.status_label, 0)

        self.stop_button = PushButton(
            localizer.agent_page_stop,
            icon=FluentIcon.CANCEL,
            parent=footer,
        )
        self.stop_button.setFixedHeight(32)
        self.stop_button.clicked.connect(self.stop_request)
        self.stop_button.setEnabled(False)
        self.stop_button.hide()
        footer_layout.addWidget(self.stop_button, 0)

        self.send_button = PrimaryPushButton(
            localizer.agent_page_send,
            icon=FluentIcon.SEND,
            parent=footer,
        )
        self.send_button.setFixedHeight(32)
        self.send_button.clicked.connect(self.send_message)
        footer_layout.addWidget(self.send_button, 0)
        composer_layout.addWidget(footer)
        self.root.addWidget(composer, 0)

        self._apply_composer_style()

        # 活动指示器排在对话流末尾，跟随消息一起滚动。
        self.activity_widget = AgentActivityWidget(self.history_content)
        self.history_layout.insertWidget(
            self.history_layout.count() - 1,
            self.activity_widget,
        )

    def _apply_composer_style(self) -> None:
        """输入框融入输入面板，聚焦时再用主色描边。"""
        accent = get_theme_accent_color().name()
        palette = self.input_box.palette()
        if isDarkTheme():
            palette.setColor(QPalette.Text, QColor("#f2f2f2"))
            palette.setColor(QPalette.PlaceholderText, QColor("#9a9a9a"))
            self.input_box.setStyleSheet(
                "QPlainTextEdit#agentInput {"
                " background: transparent;"
                " border: 1px solid transparent;"
                " border-radius: 10px; padding: 8px 10px;"
                f"}} QPlainTextEdit#agentInput:focus {{ border: 1px solid {accent}; }}"
            )
            self.hint_label.setStyleSheet("color: #8f8f8f;")
            self.status_label.setStyleSheet("color: #b8b8b8;")
        else:
            palette.setColor(QPalette.Text, QColor("#1a1a1a"))
            palette.setColor(QPalette.PlaceholderText, QColor("#737373"))
            self.input_box.setStyleSheet(
                "QPlainTextEdit#agentInput {"
                " background: transparent;"
                " border: 1px solid transparent;"
                " border-radius: 10px; padding: 8px 10px;"
                f"}} QPlainTextEdit#agentInput:focus {{ border: 1px solid {accent}; }}"
            )
            self.hint_label.setStyleSheet("color: #6f6f6f;")
            self.status_label.setStyleSheet("color: #555555;")
        self.input_box.setPalette(palette)

    def _autosize_input(self) -> None:
        """输入框随内容增高，上限 180px 后转为内部滚动。"""
        document_height = math.ceil(self.input_box.document().size().height())
        target = min(180, max(78, document_height + 20))
        if self.input_box.height() != target:
            self.input_box.setFixedHeight(target)

    def _on_theme_changed(self, _theme=None) -> None:
        """主题变化时刷新自绘元素与主题相关样式，其余交给 qfluentwidgets。"""
        self.brand_avatar.refresh_theme()
        self.activity_widget.refresh_theme()
        self.empty_state.refresh_theme()
        self._apply_project_pill_style()
        self._apply_composer_style()
        for index in range(self.history_layout.count()):
            widget = self.history_layout.itemAt(index).widget()
            refresh = getattr(widget, "refresh_theme", None)
            if callable(refresh):
                refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh_platforms()

    def refresh_platforms(self) -> None:
        config = Config().load()
        self._refresh_project_context(config)
        current = _coerce_int(getattr(config, "agent_platform", -1), -1)
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

        confirm_check = getattr(self, "unpack_confirm_check", None)
        if confirm_check is not None:
            confirm_check.blockSignals(True)
            confirm_check.setChecked(
                not bool(getattr(config, "agent_unpack_auto_confirm", False))
            )
            confirm_check.blockSignals(False)

        self.platform_combo.blockSignals(True)
        self.platform_combo.clear()
        self._platform_ids = []
        localizer = Localizer.get()
        self.platform_combo.addItem(localizer.agent_page_platform_unset, userData=-1)
        for platform in config.platforms or []:
            api_format = str(platform.get("api_format", ""))
            if api_format not in SUPPORTED_FORMATS:
                continue
            platform_id = _coerce_int(platform.get("id", -1), -1)
            if platform_id < 0:
                continue
            name = str(platform.get("name") or platform.get("model") or api_format)
            self.platform_combo.addItem(f"{name} [{api_format}]", userData=platform_id)
            self._platform_ids.append(platform_id)
        index = self.platform_combo.findData(current)
        self.platform_combo.setCurrentIndex(index if index >= 0 else 0)
        self.platform_combo.blockSignals(False)
        self._update_send_button()

    def _platform_changed(self, index: int) -> None:
        data = self.platform_combo.itemData(index)
        platform_id = _coerce_int(data if data is not None else -1, -1)
        config = Config().load()
        config.agent_platform = platform_id
        config.save()
        self.status_label.setText(
            Localizer.get().agent_page_platform_unset
            if platform_id < 0
            else Localizer.get().agent_page_platform_saved
        )
        if self.history_widgets:
            InfoBar.info(
                Localizer.get().agent_page_platform,
                Localizer.get().agent_page_platform_changed_hint,
                parent=self,
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
            self._project_actions = []
            self._project_actions_key = ""
            self.project_label.setText(Localizer.get().agent_page_project_unset)
            self.project_label.setToolTip("")
            empty_state = getattr(self, "empty_state", None)
            if empty_state is not None:
                empty_state._refresh_preflight(current)
            return
        if self._project_actions_key and self._project_actions_key != paths.project_key:
            self._project_actions = []
            self._project_actions_key = ""
        self.project_label.setText(
            Localizer.get().agent_page_project_context.format(
                name=paths.project_root.name,
                language=paths.language,
            )
        )
        self.project_label.setToolTip(str(paths.project_root))
        empty_state = getattr(self, "empty_state", None)
        if empty_state is not None:
            empty_state._refresh_preflight(current)

    def _fill_suggestion(self, text: str) -> None:
        self.input_box.setPlainText(text)
        self.input_box.setFocus()
        self.input_box.selectAll()

    @property
    def history_widgets(self) -> list[QWidget]:
        """返回会话中的消息与工具控件，不含轮次头和活动指示器。"""
        activity_widget = getattr(self, "activity_widget", None)
        widgets: list[QWidget] = []
        for index in range(self.history_layout.count()):
            widget = self.history_layout.itemAt(index).widget()
            if (
                widget is not None
                and widget is not activity_widget
                and not isinstance(widget, AgentRoundHeader)
            ):
                widgets.append(widget)
        return widgets

    def _on_history_scrolled(self, _value: int = 0) -> None:
        bar = self.history.verticalScrollBar()
        self._auto_follow = bar.maximum() - bar.value() <= AUTO_FOLLOW_THRESHOLD
        self._update_scroll_latest_button()

    def _update_scroll_latest_button(self) -> None:
        button = getattr(self, "scroll_latest_button", None)
        if button is None:
            return
        button.setVisible(bool(self.history_widgets) and not self._auto_follow)

    def _scroll_to_latest(self) -> None:
        """恢复自动跟随并滚到最新消息。"""
        self._auto_follow = True
        self._update_scroll_latest_button()
        self._history_scroll_timer.start(0)

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
        self._update_scroll_latest_button()
        self._history_scroll_timer.start(0)

    def _append(self, text: str, *, role: str) -> QWidget:
        """按调用方提供的角色添加消息，不从翻译后的文案反推角色。"""
        if role == "error":
            widget: QWidget = AgentErrorWidget(str(text or ""), self.history_content)
            widget.retry_requested.connect(self.retry_last_message)
        else:
            widget = AgentMessageWidget(str(text or ""), role, self.history_content)
            if role == "assistant":
                widget.action_requested.connect(self._handle_reply_action)
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
            self._assistant_turn.action_requested.connect(self._handle_reply_action)
            self._stream_message = self._assistant_turn
            self._add_history_widget(self._assistant_turn)
        return self._assistant_turn

    def _append_reply_delta(self, text: str) -> None:
        """累积模型增量，由节流定时器合并渲染，避免逐 delta 重排全文。"""
        delta = str(text or "")
        if not delta:
            return
        self._ensure_assistant_turn()
        self._pending_reply_text += delta
        self.activity_widget.label.setText(Localizer.get().agent_page_running)
        self._schedule_render()

    def _append_thinking_delta(self, text: str) -> None:
        """累积思考增量，与正文共用节流定时器。"""
        delta = str(text or "")
        if not delta:
            return
        self._ensure_assistant_turn()
        self._pending_thinking_text += delta
        self.activity_widget.label.setText(Localizer.get().agent_page_running)
        self._schedule_render()

    def _schedule_render(self) -> None:
        """按当前消息长度选择节流间隔，短回复仍保持即时打字感。"""
        rendered_chars = len(self._pending_reply_text) + len(self._pending_thinking_text)
        if self._assistant_turn is not None:
            rendered_chars += len(self._assistant_turn.text)
        interval = (
            50
            if rendered_chars < STREAM_RENDER_MEDIUM_CHARS
            else 80
            if rendered_chars < STREAM_RENDER_SLOW_CHARS
            else 120
        )
        self._render_timer.start(interval)

    def _flush_pending_deltas(self) -> None:
        """把累积的增量一次性渲染；正文与思考各只触发一次重排。"""
        flushed = False
        if self._pending_reply_text:
            reply_text = self._pending_reply_text
            self._pending_reply_text = ""
            turn = self._ensure_assistant_turn()
            turn.finish_thinking()
            turn.append_text(reply_text)
            flushed = True
        if self._pending_thinking_text:
            thinking_text = self._pending_thinking_text
            self._pending_thinking_text = ""
            turn = self._ensure_assistant_turn()
            turn.append_thinking_text(thinking_text)
            flushed = True
        if flushed:
            self._update_scroll_latest_button()
            self._history_scroll_timer.start(0)

    def _complete_reply(self, text: str) -> None:
        """用最终响应校正流式消息；无增量时退回一次性追加。"""
        final_text = str(text or "")
        turn = self._assistant_turn
        if turn is None:
            turn = self._append(final_text, role="assistant")
            if isinstance(turn, AgentMessageWidget):
                self._assistant_turn = turn
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
        self._render_timer.stop()
        self._pending_reply_text = ""
        self._pending_thinking_text = ""
        self._pending_reply_actions = []
        self._project_actions = []
        self._project_actions_key = ""
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
        self._update_scroll_latest_button()
        self.status_label.setText("")
        self.stop_button.setEnabled(False)
        self.stop_button.hide()
        self._last_message = ""
        self._round_count = 0
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
        # 工具完成后仍可能马上进入下一轮模型请求，活动指示不能停在旧工具名称。
        self.activity_widget.label.setText(Localizer.get().agent_page_running)
        self._history_scroll_timer.start(0)

    def send_message(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        message = self.input_box.toPlainText().strip()
        if not message:
            return
        # 接口未选定时不清空输入框，否则用户刚打的内容会凭空消失。
        if _coerce_int(
            self.platform_combo.currentData()
            if self.platform_combo.currentData() is not None
            else -1,
            -1,
        ) < 0:
            self.status_label.setText(Localizer.get().agent_page_platform_unset)
            return
        self.input_box.clear()
        localizer = Localizer.get()
        # 记住原文，失败后「点击重试」直接复用，不必让用户重新输入。
        self._last_message = message
        self._stream_message = None
        self._assistant_turn = None
        self._reply_rendered = False
        self._pending_reply_actions = []
        # 新回合从底部开始，无论用户此前滚到哪里。
        self._auto_follow = True
        self._round_count += 1
        if self._round_header is not None:
            self._round_header.stop()
        self._round_header = AgentRoundHeader(self.history_content, self._round_count)
        self._add_history_widget(self._round_header)
        self._append(message, role="user")
        self.status_label.setText(localizer.agent_page_running)
        self.activity_widget.set_running(True, localizer.agent_page_running)
        self.send_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.stop_button.show()
        self._worker = AgentWorker(
            self._service,
            message,
            str(self.thinking_combo.currentData() or "OFF"),
            auto_confirm_unpack=bool(
                getattr(Config().load(), "agent_unpack_auto_confirm", False)
            ),
        )
        self._worker.agent_event.connect(self._on_worker_event)
        self._worker.confirmation_requested.connect(self._on_confirmation_requested)
        self._worker.completed.connect(self._on_worker_finished)
        # 销毁挂在 QThread 原生 finished 上：它在线程真正退出后才发出，
        # 保证 deleteLater 不会销毁一个仍在运行的线程。
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def stop_request(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._flush_pending_deltas()
            turn = self._assistant_turn
            if turn is not None and turn.text.strip():
                turn.append_text(f"\n\n*{Localizer.get().agent_page_stopped_hint}*")
            self._worker.cancel()
            self.status_label.setText(Localizer.get().agent_page_cancelled)

    def _on_confirmation_requested(self, name: str, payload: dict[str, Any]) -> None:
        worker = self._worker
        if worker is None:
            return
        localizer = Localizer.get()
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        if name == "unpack_rpa_files":
            title = localizer.agent_page_confirmation_title
            message = localizer.agent_page_unpack_confirmation.format(
                game_dir=data.get("game_dir", ""),
                count=data.get("count", 0),
            )
        elif name == "optimize_old_new_translations":
            title = localizer.agent_page_old_new_confirmation_title
            message = localizer.agent_page_old_new_confirmation.format(
                old_new_count=data.get("old_new_count", 0),
                supplement_count=data.get("supplement_count", 0),
                total_count=data.get("total_count", 0),
                conflict_count=data.get("conflict_count", 0),
                tl_dir=data.get("tl_dir", ""),
                output_path=data.get("output_path", ""),
            )
        else:
            title = localizer.agent_page_confirmation_title
            message = localizer.agent_page_confirmation_generic.format(tool=name)
        dialog = MessageBox(title, message, self)
        dialog.yesButton.setText(localizer.confirm)
        dialog.cancelButton.setText(localizer.cancel)
        self._confirmation_dialog = dialog

        # 解包确认支持「不再询问」：勾选后下一次同类操作直接放行，
        # 可在顶栏设置弹层里重新打开确认。
        dont_ask = None
        if name == "unpack_rpa_files":
            dont_ask = CheckBox(localizer.agent_page_unpack_dont_ask, dialog.widget)
            dialog.textLayout.addWidget(dont_ask)

        def resolve(approved: bool) -> None:
            if self._confirmation_dialog is not dialog:
                return
            self._confirmation_dialog = None
            if approved and dont_ask is not None and dont_ask.isChecked():
                config = Config().load()
                config.agent_unpack_auto_confirm = True
                config.save()
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
            self.activity_widget.set_running(True, localizer.agent_page_running)
        elif event_name == "reply_delta":
            if payload.get("thinking") or payload.get("kind") in {"thinking", "reasoning"}:
                self._append_thinking_delta(str(payload.get("text", "")))
            else:
                self._append_reply_delta(str(payload.get("text", "")))
        elif event_name in {"thinking_delta", "reasoning_delta"}:
            self._append_thinking_delta(str(payload.get("text", "")))
        elif event_name == "reply":
            # 最终文本覆盖流式正文，未渲染的正文增量直接丢弃；思考增量先落进折叠条。
            self._pending_reply_text = ""
            self._flush_pending_deltas()
            self._complete_reply(str(payload.get("message", "")))
        elif event_name == "tool_start":
            self._flush_pending_deltas()
            if self._assistant_turn is not None:
                self._assistant_turn.move_answer_to_thinking()
                self._assistant_turn.finish_thinking()
            self._append_tool_start(str(payload.get("name", "")))
        elif event_name == "tool_done":
            tool_name = str(payload.get("name", ""))
            tool_success = bool(payload.get("success", False))
            tool_data = (
                payload.get("data")
                if isinstance(payload.get("data"), dict)
                else None
            )
            if tool_name == "set_project" and tool_success:
                self._project_actions = []
                self._project_actions_key = ""
                self._refresh_project_context()
            if tool_name == "inspect_translation_project" and tool_success and tool_data:
                self._project_actions = self._inspection_actions(tool_data)
                paths = RenpyProjectPaths.from_config(Config().load())
                self._project_actions_key = paths.project_key if paths is not None else ""
                self._pending_reply_actions = list(self._project_actions)
            elif tool_success:
                self._pending_reply_actions = self._followup_actions(
                    tool_name,
                    tool_data or {},
                )
            self._finish_tool(
                tool_name,
                tool_success,
                str(payload.get("message", "")),
                tool_data,
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
        self._flush_pending_deltas()
        self.activity_widget.set_running(False)
        self.send_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.stop_button.hide()
        for widget in self._running_tool_widgets:
            widget.complete(False, str(getattr(result, "message", "")))
        self._running_tool_widgets.clear()
        if self._round_header is not None:
            self._round_header.stop()
        result_code = str(getattr(result, "code", "") or "")
        if getattr(result, "success", False):
            if not self._reply_rendered:
                self._complete_reply(str(result.message))
            if self._assistant_turn is not None and self._pending_reply_actions:
                self._assistant_turn.set_actions(self._pending_reply_actions)
                self._pending_reply_actions = []
                self._history_scroll_timer.start(0)
            self.status_label.setText(localizer.agent_page_done)
        elif result_code in {"CANCELLED", "USER_CANCELLED"}:
            # 主动停止或拒绝确认属于正常结束，不再追加一条可重试的错误。
            self._pending_reply_actions = []
            self._stream_message = None
            self.status_label.setText(localizer.agent_page_cancelled)
        else:
            self._pending_reply_actions = []
            self._stream_message = None
            self._append(str(result.message), role="error")
            self.status_label.setText(localizer.agent_page_failed)
        self._update_send_button()

    def _inspection_actions(
        self,
        data: dict[str, Any],
    ) -> list[tuple[str, str, Any]]:
        """把体检代码映射为受控界面动作，并补充当前项目可用的常用工具。"""
        localizer = Localizer.get()
        action_code = str(data.get("next_action_code", "")).upper()
        primary = {
            "START_TRANSLATION": (
                ACTION_ONE_KEY_TRANSLATE,
                localizer.agent_page_action_one_key_translate,
                FluentIcon.PLAY,
            ),
            "CONTINUE_TRANSLATION": (
                ACTION_OPEN_TRANSLATION,
                localizer.agent_page_action_continue_translation,
                FluentIcon.PLAY,
            ),
            "REVIEW_TRANSLATION": (
                ACTION_OPEN_TRANSLATION,
                localizer.agent_page_action_open_translation,
                FluentIcon.PLAY,
            ),
            "REVIEW_QUALITY": (
                ACTION_OPEN_TRANSLATION,
                localizer.agent_page_action_open_translation,
                FluentIcon.PLAY,
            ),
            "REVIEW_WORKBENCH": (
                ACTION_OPEN_WORKBENCH,
                localizer.agent_page_action_open_workbench,
                FluentIcon.PEOPLE,
            ),
            "UNPACK_RPA": (
                ACTION_UNPACK_RPA,
                localizer.agent_page_tool_unpack_rpa_files,
                FluentIcon.FOLDER_ADD,
            ),
            "DECOMPILE_SCRIPTS": (
                ACTION_OPEN_TOOLBOX,
                localizer.agent_page_action_open_toolbox,
                FluentIcon.GAME,
            ),
            "REPAIR_CACHE": (
                ACTION_OPEN_TRANSLATION,
                localizer.agent_page_action_open_translation,
                FluentIcon.PLAY,
            ),
            "CHECK_PROJECT_FILES": (
                ACTION_SCAN_ERRORS,
                localizer.agent_page_tool_scan_script_errors,
                FluentIcon.SEARCH,
            ),
        }.get(action_code)

        actions: list[tuple[str, str, Any]] = []
        used: set[str] = set()

        def add(action: tuple[str, str, Any] | None) -> None:
            if action is not None and action[0] not in used:
                actions.append(action)
                used.add(action[0])

        add(primary)
        files = data.get("files") if isinstance(data.get("files"), dict) else {}
        unpack_required = bool(
            files.get("unpack_required", action_code == "UNPACK_RPA")
        )
        if _coerce_int(files.get("rpa_count", 0), 0) > 0:
            add(
                (
                    ACTION_LIST_RPA,
                    localizer.agent_page_tool_list_rpa_files,
                    FluentIcon.ZIP_FOLDER,
                )
            )
            if unpack_required:
                add(
                    (
                        ACTION_UNPACK_RPA,
                        localizer.agent_page_tool_unpack_rpa_files,
                        FluentIcon.FOLDER_ADD,
                    )
                )
        if _coerce_int(files.get("rpy_count", 0), 0) > 0 or _coerce_int(
            files.get("rpyc_count", 0),
            0,
        ) > 0:
            add(
                (
                    ACTION_SCAN_ERRORS,
                    localizer.agent_page_tool_scan_script_errors,
                    FluentIcon.SEARCH,
                )
            )
        return actions

    def _followup_actions(
        self,
        tool_name: str,
        data: dict[str, Any],
    ) -> list[tuple[str, str, Any]]:
        """让只读工具回复延续可执行按钮，避免点一次后操作入口消失。"""
        consumed = {
            "list_rpa_files": {ACTION_LIST_RPA},
            "scan_script_errors": {ACTION_SCAN_ERRORS},
            "unpack_rpa_files": {ACTION_LIST_RPA, ACTION_UNPACK_RPA},
        }.get(tool_name, set())
        actions = [
            action
            for action in self._project_actions
            if action[0] not in consumed
        ]
        if actions:
            return actions

        localizer = Localizer.get()
        if tool_name == "list_rpa_files":
            if data.get("unpack_required") is True:
                actions.append(
                    (
                        ACTION_UNPACK_RPA,
                        localizer.agent_page_tool_unpack_rpa_files,
                        FluentIcon.FOLDER_ADD,
                    )
                )
            if (
                _coerce_int(data.get("rpy_count", 0), 0) > 0
                or _coerce_int(data.get("rpyc_count", 0), 0) > 0
                or "unpack_required" not in data
            ):
                actions.append(
                    (
                        ACTION_SCAN_ERRORS,
                        localizer.agent_page_tool_scan_script_errors,
                        FluentIcon.SEARCH,
                    )
                )
        elif tool_name == "scan_script_errors":
            actions.append(
                (
                    ACTION_LIST_RPA,
                    localizer.agent_page_tool_list_rpa_files,
                    FluentIcon.ZIP_FOLDER,
                )
            )
        elif tool_name == "unpack_rpa_files":
            actions.extend(
                (
                    (
                        ACTION_ONE_KEY_TRANSLATE,
                        localizer.agent_page_action_one_key_translate,
                        FluentIcon.PLAY,
                    ),
                    (
                        ACTION_SCAN_ERRORS,
                        localizer.agent_page_tool_scan_script_errors,
                        FluentIcon.SEARCH,
                    ),
                )
            )
        return actions

    def _start_confirmed_tool(
        self,
        tool_name: str,
        trusted_context: dict[str, Any],
    ) -> None:
        """启动一次已确认工具；直接走服务端，不再让模型决定是否调用。"""
        if self._worker is not None and self._worker.isRunning():
            return
        localizer = Localizer.get()
        label = getattr(localizer, f"agent_page_tool_{tool_name}", tool_name)
        self._last_message = ""
        self._stream_message = None
        self._assistant_turn = None
        self._reply_rendered = False
        self._pending_reply_actions = []
        self._auto_follow = True
        self._round_count += 1
        if self._round_header is not None:
            self._round_header.stop()
        self._round_header = AgentRoundHeader(self.history_content, self._round_count)
        self._add_history_widget(self._round_header)
        self._append(label, role="user")
        self._ensure_assistant_turn()
        self.status_label.setText(localizer.agent_page_running)
        self.activity_widget.set_running(True, localizer.agent_page_running)
        self.send_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.stop_button.show()

        self._worker = AgentToolWorker(
            self._service,
            tool_name,
            trusted_context,
        )
        self._worker.agent_event.connect(self._on_worker_event)
        self._worker.completed.connect(self._on_worker_finished)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _confirm_unpack_action(self) -> None:
        """点击解包操作后立即展示真实确认按钮，不让模型用文字代替确认。"""
        if self._worker is not None and self._worker.isRunning():
            return
        if self._confirmation_dialog is not None:
            return

        localizer = Localizer.get()
        data = self._service.confirmation_context("unpack_rpa_files")
        message = localizer.agent_page_unpack_confirmation.format(
            game_dir=data.get("game_dir", ""),
            count=data.get("count", 0),
        )
        dialog = MessageBox(localizer.agent_page_confirmation_title, message, self)
        dialog.yesButton.setText(localizer.confirm)
        dialog.cancelButton.setText(localizer.cancel)
        self._confirmation_dialog = dialog

        def resolve(approved: bool) -> None:
            if self._confirmation_dialog is not dialog:
                return
            self._confirmation_dialog = None
            if not approved:
                self.status_label.setText("")
                return
            self._start_confirmed_tool("unpack_rpa_files", data)

        dialog.accepted.connect(lambda: resolve(True))
        dialog.rejected.connect(lambda: resolve(False))
        self.status_label.setText(localizer.agent_page_waiting_confirmation)
        dialog.open()

    def _start_one_key_translation(self) -> None:
        """复用一键向导启动当前项目，免去重复选择项目和手动点下一步。"""
        localizer = Localizer.get()
        paths = RenpyProjectPaths.from_config(Config().load())
        toolbox = getattr(self._window, "renpy_toolbox_page", None)
        get_tool_page = getattr(toolbox, "get_tool_page", None)
        navigate = getattr(self._window, "navigate_to_page", None)
        if paths is None or not callable(get_tool_page) or not callable(navigate):
            InfoBar.warning(
                localizer.notice,
                localizer.agent_page_one_key_unavailable,
                parent=self,
            )
            return

        try:
            page = get_tool_page("one_key_translate")
            start = getattr(page, "start_current_project", None)
            if not callable(start):
                raise AttributeError("一键翻译页面未提供 Agent 启动入口")
            navigate(page)
            started = bool(start(str(paths.project_root), paths.language))
        except Exception:
            started = False
        if not started:
            InfoBar.warning(
                localizer.notice,
                localizer.agent_page_one_key_unavailable,
                parent=self,
            )

    def _handle_reply_action(self, action: str) -> None:
        """执行回复快捷操作；跳页不请求模型，工具操作复用现有对话链路。"""
        page_attributes = {
            ACTION_OPEN_TRANSLATION: "translation_page",
            ACTION_OPEN_WORKBENCH: "renpy_workbench_page",
            ACTION_OPEN_TOOLBOX: "renpy_toolbox_page",
        }
        page_attribute = page_attributes.get(action)
        if page_attribute is not None:
            window = self._window
            page = getattr(window, page_attribute, None)
            navigate = getattr(window, "navigate_to_page", None)
            if page is not None and callable(navigate):
                navigate(page)
            return

        if action == ACTION_UNPACK_RPA:
            self._confirm_unpack_action()
            return

        if action == ACTION_ONE_KEY_TRANSLATE:
            self._start_one_key_translation()
            return

        prompts = {
            ACTION_LIST_RPA: Localizer.get().agent_page_suggestion_rpa,
            ACTION_SCAN_ERRORS: Localizer.get().agent_page_suggestion_errors,
        }
        prompt = prompts.get(action)
        if prompt is None or (self._worker is not None and self._worker.isRunning()):
            return
        self.input_box.setPlainText(prompt)
        self.send_message()

    def _update_send_button(self) -> None:
        running = self._worker is not None and self._worker.isRunning()
        current_platform = self.platform_combo.currentData()
        platform_ready = _coerce_int(current_platform, -1) >= 0
        self.send_button.setEnabled(
            bool(self.input_box.toPlainText().strip())
            and platform_ready
            and not running
        )
