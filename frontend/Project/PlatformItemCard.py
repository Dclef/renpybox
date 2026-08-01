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
        self._details = ""
        self._is_active = False

        self.setBorderRadius(4)
        self.setFixedWidth(240)
        self.setMinimumHeight(64)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)

        self.root = QHBoxLayout(self)
        self.root.setContentsMargins(14, 10, 10, 10)
        self.root.setSpacing(10)

        self.text_container = QWidget(self)
        self.text_container.setMinimumWidth(0)
        self.text_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.text_vbox = QVBoxLayout(self.text_container)
        self.text_vbox.setContentsMargins(0, 0, 0, 0)
        self.text_vbox.setSpacing(2)

        self.name_label = StrongBodyLabel("", self.text_container)
        self.name_label.setMinimumWidth(0)
        self.name_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.text_vbox.addWidget(self.name_label)

        self.details_label = CaptionLabel("", self.text_container)
        self.details_label.setMinimumWidth(0)
        self.details_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.details_label.setTextColor(QColor(96, 96, 96), QColor(160, 160, 160))
        self.text_vbox.addWidget(self.details_label)
        self.root.addWidget(self.text_container, 1)

        self.more_button = TransparentToolButton(FluentIcon.MORE, self)
        self.more_button.setFixedSize(32, 32)
        self.root.addWidget(self.more_button, alignment=Qt.AlignmentFlag.AlignVCenter)

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
            FluentIcon.EDIT,
            localizer.platform_page_api_edit,
            triggered=lambda _checked=False: self.edit_requested.emit(self.platform_id),
        ))
        menu.addSeparator()
        menu.addAction(Action(
            FluentIcon.DEVELOPER_TOOLS,
            localizer.platform_page_api_args,
            triggered=lambda _checked=False: self.args_requested.emit(self.platform_id),
        ))
        menu.addSeparator()
        menu.addAction(Action(
            FluentIcon.SEND,
            localizer.platform_page_api_test,
            triggered=lambda _checked=False: self.test_requested.emit(self.platform_id),
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

    def update_info(self, platform: dict) -> None:
        self.platform_id = int(platform.get("id", 0))
        self._name = str(platform.get("name", ""))
        model = str(platform.get("model", ""))
        api_format = str(platform.get("api_format", ""))
        self._details = f"{model} · {api_format}"

        self.name_label.setToolTip(self._name)
        self.details_label.setToolTip(self._details)
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
            self.details_label.setTextColor(foreground, foreground)
            self.more_button.setIcon(FluentIcon.MORE.icon(color=foreground))
            return

        self.name_label.setTextColor(QColor(0, 0, 0), QColor(255, 255, 255))
        self.details_label.setTextColor(QColor(96, 96, 96), QColor(160, 160, 160))
        self.more_button.setIcon(FluentIcon.MORE)

    def _update_elided_text(self) -> None:
        for label, text in (
            (self.name_label, self._name),
            (self.details_label, self._details),
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
        painter.drawLine(2, 6, 2, self.height() - 6)
