from PyQt5.QtCore import QEvent, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action,
    CardWidget,
    CaptionLabel,
    FluentIcon,
    RoundMenu,
    StrongBodyLabel,
    TransparentToolButton,
    isDarkTheme,
    qconfig,
)

from module.Localizer.Localizer import Localizer
from widget.ThemeHelper import get_theme_active_card_background_color
from widget.ThemeHelper import get_theme_active_card_border_color
from widget.ThemeHelper import get_theme_active_card_foreground_color
from widget.ThemeHelper import get_theme_active_card_indicator_color


class PlatformItemCard(CardWidget):
    """显示接口摘要并转发接口操作的条目卡。"""

    activate_requested = pyqtSignal(int)
    edit_requested = pyqtSignal(int)
    args_requested = pyqtSignal(int)
    test_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)

    def __init__(
        self,
        platform: dict,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.platform_id = 0
        self._name = ""
        self._model = ""
        self._api_format = ""
        self._is_active = False

        self.setBorderRadius(8)
        self.setFixedWidth(280)
        self.setFixedHeight(72)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(14, 10, 10, 10)
        self.root.setSpacing(4)

        # 顶部行：名称 + 测试/编辑/更多
        self.top_row = QHBoxLayout()
        self.top_row.setContentsMargins(0, 0, 0, 0)
        self.top_row.setSpacing(4)

        self.name_label = StrongBodyLabel("", self)
        self.name_label.setMinimumWidth(0)
        self.name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.top_row.addWidget(self.name_label, 1)

        self.test_button = TransparentToolButton(FluentIcon.SEND, self)
        self.test_button.setFixedSize(30, 30)
        self.test_button.setToolTip(Localizer.get().platform_page_api_test)
        self.test_button.clicked.connect(
            lambda: self.test_requested.emit(self.platform_id)
        )
        self.top_row.addWidget(self.test_button)

        self.edit_button = TransparentToolButton(FluentIcon.EDIT, self)
        self.edit_button.setFixedSize(30, 30)
        self.edit_button.setToolTip(Localizer.get().platform_page_api_edit)
        self.edit_button.clicked.connect(
            lambda: self.edit_requested.emit(self.platform_id)
        )
        self.top_row.addWidget(self.edit_button)

        self.more_button = TransparentToolButton(FluentIcon.MORE, self)
        self.more_button.setFixedSize(30, 30)
        self.top_row.addWidget(self.more_button)
        self.root.addLayout(self.top_row)

        # 底部行：格式徽标 + 模型名 + 激活指示点
        self.bottom_row = QHBoxLayout()
        self.bottom_row.setContentsMargins(0, 0, 0, 0)
        self.bottom_row.setSpacing(8)

        self.format_badge = CaptionLabel("", self)
        self.format_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.bottom_row.addWidget(self.format_badge)

        self.model_label = CaptionLabel("", self)
        self.model_label.setMinimumWidth(0)
        self.model_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.model_label.setTextColor(QColor(96, 96, 96), QColor(160, 160, 160))
        self.bottom_row.addWidget(self.model_label, 1)

        self.status_label = CaptionLabel("", self)
        self.status_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.bottom_row.addWidget(self.status_label)
        self.root.addLayout(self.bottom_row)

        self.menu = self._build_menu()
        self.more_button.clicked.connect(self._show_menu)
        qconfig.themeChanged.connect(self._on_theme_changed)

        self.update_info(platform)
        self.set_active(False)

    def _build_menu(self) -> RoundMenu:
        localizer = Localizer.get()
        menu = RoundMenu("", self.more_button)

        self.activate_action = Action(
            FluentIcon.EXPRESSIVE_INPUT_ENTRY,
            localizer.platform_page_api_activate,
            triggered=lambda _checked=False: self.activate_requested.emit(self.platform_id),
        )
        menu.addAction(self.activate_action)
        menu.addSeparator()
        menu.addAction(Action(
            FluentIcon.DEVELOPER_TOOLS,
            localizer.platform_page_api_args,
            triggered=lambda _checked=False: self.args_requested.emit(self.platform_id),
        ))
        menu.addSeparator()
        menu.addAction(Action(
            FluentIcon.DELETE,
            localizer.platform_page_api_delete,
            triggered=lambda _checked=False: self.delete_requested.emit(self.platform_id),
        ))
        return menu

    def _show_menu(self) -> None:
        self.menu.exec(self.more_button.mapToGlobal(self.more_button.rect().bottomLeft()))

    def mouseDoubleClickEvent(self, event) -> None:
        # 双击卡片快速进入编辑
        if event.button() == Qt.LeftButton:
            self.edit_requested.emit(self.platform_id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def update_info(self, platform: dict) -> None:
        self.platform_id = int(platform.get("id", 0))
        self._name = str(platform.get("name", ""))
        self._model = str(platform.get("model", ""))
        self._api_format = str(platform.get("api_format", ""))

        self.name_label.setToolTip(self._name)
        self.model_label.setToolTip(self._model)
        self.format_badge.setText(self._api_format)
        self._update_format_badge_color()
        self._update_elided_text()

    def set_active(self, active: bool) -> None:
        self._is_active = active
        self.activate_action.setEnabled(not active)
        self._update_active_colors()
        self._update_elided_text()
        self.update()

    def _update_active_colors(self) -> None:
        if self._is_active:
            foreground = get_theme_active_card_foreground_color()
            self.name_label.setTextColor(foreground, foreground)
            self.model_label.setTextColor(
                QColor("#64748B"),
                QColor("#94A3B8"),
            )
            self.status_label.setText("●")
            self.status_label.setTextColor(
                get_theme_active_card_indicator_color(),
                get_theme_active_card_indicator_color(),
            )
            self.status_label.setToolTip(Localizer.get().platform_page_api_activate)
        else:
            self.name_label.setTextColor(QColor(0, 0, 0), QColor(255, 255, 255))
            self.model_label.setTextColor(QColor(96, 96, 96), QColor(160, 160, 160))
            self.status_label.setText("")
            self.status_label.setToolTip("")
        self._update_format_badge_color()

    def _update_format_badge_color(self) -> None:
        if self._is_active:
            fg = get_theme_active_card_indicator_color()
            self.format_badge.setTextColor(fg, fg)
        elif isDarkTheme():
            self.format_badge.setTextColor(QColor(180, 180, 180), QColor(180, 180, 180))
        else:
            self.format_badge.setTextColor(QColor(110, 110, 110), QColor(110, 110, 110))

    def _update_elided_text(self) -> None:
        for label, text in (
            (self.name_label, self._name),
            (self.model_label, self._model),
        ):
            width = label.contentsRect().width()
            elided = label.fontMetrics().elidedText(text, Qt.ElideRight, width)
            label.setText(elided if width > 0 else text)

    def _on_theme_changed(self, _theme=None) -> None:
        self._update_active_colors()
        self.update()

    def resizeEvent(self, event: QEvent) -> None:
        super().resizeEvent(event)
        self._update_elided_text()

    def paintEvent(self, event: QEvent) -> None:
        super().paintEvent(event)
        if not self._is_active:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        radius = self.getBorderRadius()
        painter.setPen(QPen(get_theme_active_card_border_color(), 1))
        painter.setBrush(get_theme_active_card_background_color())
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), radius, radius)

        pen = QPen(get_theme_active_card_indicator_color(), 3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(2, 8, 2, self.height() - 8)
