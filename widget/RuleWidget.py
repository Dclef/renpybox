from typing import Callable

from PyQt5.QtCore import QSize
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import FluentIcon
from qfluentwidgets import PillToolButton
from qfluentwidgets import ToolTipFilter
from qfluentwidgets import ToolTipPosition

from module.Localizer.Localizer import Localizer

class RuleWidget(QWidget):
    """规则切换按钮组件，包含正则和大小写敏感两个切换按钮"""

    def __init__(
        self,
        parent: QWidget = None,
        show_regex: bool = True,
        show_case_sensitive: bool = True,
        regex_enabled: bool = False,
        case_sensitive_enabled: bool = False,
        on_changed: Callable[[bool, bool], None] = None,
    ) -> None:
        super().__init__(parent)

        self.on_changed_callback = on_changed

        # 设置布局
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(4)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.regex_button: PillToolButton | None = None
        self.case_button: PillToolButton | None = None

        if show_regex:
            self.regex_button = PillToolButton(FluentIcon.IOT, self)
            self.regex_button.setIconSize(QSize(14, 14))
            self.regex_button.setFixedSize(28, 28)
            self.regex_button.setChecked(regex_enabled)
            self.regex_button.toggled.connect(self._on_regex_toggled)
            self.layout.addWidget(self.regex_button)
            self.regex_button.installEventFilter(ToolTipFilter(self.regex_button, 300, ToolTipPosition.TOP))
            self._update_regex_tooltip()

        if show_case_sensitive:
            self.case_button = PillToolButton(FluentIcon.FONT, self)
            self.case_button.setIconSize(QSize(16, 16))
            self.case_button.setFixedSize(28, 28)
            self.case_button.setChecked(case_sensitive_enabled)
            self.case_button.toggled.connect(self._on_case_toggled)
            self.layout.addWidget(self.case_button)
            self.case_button.installEventFilter(ToolTipFilter(self.case_button, 300, ToolTipPosition.TOP))
            self._update_case_tooltip()

    def _on_regex_toggled(self, checked: bool) -> None:
        self._update_regex_tooltip()
        self._trigger_callback()

    def _on_case_toggled(self, checked: bool) -> None:
        self._update_case_tooltip()
        self._trigger_callback()

    def _update_regex_tooltip(self) -> None:
        if self.regex_button is None:
            return
        tooltip_text = (
            f"{Localizer.get().rule_regex}\n{Localizer.get().rule_regex_on}"
            if self.regex_button.isChecked()
            else f"{Localizer.get().rule_regex}\n{Localizer.get().rule_regex_off}"
        )
        self.regex_button.setToolTip(tooltip_text)

    def _update_case_tooltip(self) -> None:
        if self.case_button is None:
            return
        tooltip_text = (
            f"{Localizer.get().rule_case_sensitive}\n{Localizer.get().rule_case_sensitive_on}"
            if self.case_button.isChecked()
            else f"{Localizer.get().rule_case_sensitive}\n{Localizer.get().rule_case_sensitive_off}"
        )
        self.case_button.setToolTip(tooltip_text)

    def _trigger_callback(self) -> None:
        if callable(self.on_changed_callback):
            self.on_changed_callback(self.get_regex_enabled(), self.get_case_sensitive_enabled())

    def get_regex_enabled(self) -> bool:
        if self.regex_button is None:
            return False
        return self.regex_button.isChecked()

    def get_case_sensitive_enabled(self) -> bool:
        if self.case_button is None:
            return False
        return self.case_button.isChecked()

    def set_regex_enabled(self, enabled: bool) -> None:
        if self.regex_button is not None:
            self.regex_button.setChecked(enabled)

    def set_case_sensitive_enabled(self, enabled: bool) -> None:
        if self.case_button is not None:
            self.case_button.setChecked(enabled)
