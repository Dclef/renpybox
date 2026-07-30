"""工具箱入口卡片。"""

from typing import Callable

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QTextLayout
from PyQt5.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CardWidget,
    FluentIcon,
    FluentIconBase,
    IconWidget,
    SubtitleLabel,
    TransparentToolButton,
    getFont,
    qconfig,
)

from widget.Separator import Separator


class TwoLineElideLabel(QLabel):
    """最多显示两行，并在第二行末尾省略长文本。"""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = text
        self.setFont(getFont(12))
        self.setWordWrap(True)
        self.setToolTip(text)
        self.setProperty("toolCardDescription", True)
        self.setMaximumHeight(self.fontMetrics().lineSpacing() * 2 + 4)

    def _update_text(self) -> None:
        width = self.contentsRect().width()
        if width <= 0:
            return

        layout = QTextLayout(self._full_text, self.font())
        layout.beginLayout()
        first_line = layout.createLine()
        if first_line.isValid():
            first_line.setLineWidth(width)
        layout.endLayout()

        first_end = first_line.textStart() + first_line.textLength()
        if first_end >= len(self._full_text):
            display_text = self._full_text
        else:
            first = self._full_text[:first_end].rstrip()
            remainder = self._full_text[first_end:].lstrip()
            second = self.fontMetrics().elidedText(remainder, Qt.ElideRight, width)
            display_text = f"{first}\n{second}"

        if self.text() != display_text:
            super().setText(display_text)

    def resizeEvent(self, event: QEvent) -> None:
        super().resizeEvent(event)
        self._update_text()


class ItemCard(CardWidget):
    """带图标、流程序号和项目状态的工具卡片。"""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        description: str,
        init: Callable | None = None,
        clicked: Callable | None = None,
        icon: FluentIconBase | None = None,
        step: int = 0,
        project_ready: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setProperty("toolCard", True)
        self.setMinimumWidth(260)
        self.setFixedHeight(132)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setBorderRadius(8)
        self.setToolTip(description)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(16, 14, 12, 14)
        self.root.setSpacing(8)

        title_container = QWidget(self)
        title_container.setToolTip(description)
        title_layout = QHBoxLayout(title_container)
        title_layout.setSpacing(9)
        title_layout.setContentsMargins(0, 0, 0, 0)
        self.root.addWidget(title_container)

        if step > 0:
            step_label = QLabel(str(step), self)
            step_label.setFont(getFont(11))
            step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            step_label.setFixedSize(22, 22)
            step_label.setProperty("toolStep", True)
            step_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            title_layout.addWidget(step_label)

        self.icon_widget = None
        if icon is not None:
            self.icon_widget = IconWidget(icon, self)
            self.icon_widget.setFixedSize(20, 20)
            self.icon_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            title_layout.addWidget(self.icon_widget)

        self.title_label = SubtitleLabel(title, self)
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title_layout.addWidget(self.title_label)
        title_layout.addStretch(1)

        self.title_button = TransparentToolButton(FluentIcon.PAGE_RIGHT, self)
        self.title_button.setToolTip(f"打开{title}")
        title_layout.addWidget(self.title_button)

        self.root.addWidget(Separator(self))

        self.description_label = TwoLineElideLabel(description, self)
        self.description_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.root.addWidget(self.description_label, 1)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self.set_project_ready(project_ready)
        qconfig.themeChanged.connect(self._on_theme_changed)

        if callable(init):
            init(self)
        if callable(clicked):
            self.clicked.connect(lambda: clicked(self))
            self.title_button.clicked.connect(lambda: clicked(self))

    def set_project_ready(self, ready: bool) -> None:
        self.setProperty("projectReady", ready)
        self._opacity_effect.setOpacity(1.0 if ready else 0.56)
        cursor = Qt.CursorShape.PointingHandCursor if ready else Qt.CursorShape.ArrowCursor
        self.setCursor(cursor)
        self.title_button.setCursor(cursor)
        self._repolish()

    def _repolish(self) -> None:
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    def _on_theme_changed(self) -> None:
        self._repolish()
        if self.icon_widget is not None:
            self.icon_widget.update()
        self.description_label.style().unpolish(self.description_label)
        self.description_label.style().polish(self.description_label)

    def paintEvent(self, event: QEvent) -> None:
        # CardWidget 会自行绘制半透明背景，这里改由 QSS 完整接管。
        QFrame.paintEvent(self, event)
