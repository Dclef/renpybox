import re
from typing import Callable

from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import CaptionLabel
from qfluentwidgets import CardWidget
from qfluentwidgets import FluentIcon
from qfluentwidgets import PillPushButton
from qfluentwidgets import SearchLineEdit
from qfluentwidgets import ToolTipFilter
from qfluentwidgets import ToolTipPosition
from qfluentwidgets import TransparentPushButton
from qfluentwidgets import TransparentToolButton
from qfluentwidgets import VerticalSeparator

from module.Localizer.Localizer import Localizer

class SearchCard(CardWidget):
    """搜索卡片组件，支持普通/正则搜索模式及上下跳转"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        # 搜索模式：False=普通搜索，True=正则搜索
        self._regex_mode: bool = False

        # 设置容器布局
        self.setBorderRadius(4)
        self.root = QHBoxLayout(self)
        self.root.setContentsMargins(16, 16, 16, 16)
        self.root.setSpacing(12)

        # 正则模式切换按钮
        self.regex_btn = PillPushButton(Localizer.get().search_regex_btn, self)
        self.regex_btn.setCheckable(True)
        self.regex_btn.clicked.connect(self._on_regex_toggle)
        self.regex_btn.installEventFilter(ToolTipFilter(self.regex_btn, 300, ToolTipPosition.TOP))
        self._update_regex_tooltip()
        self.root.addWidget(self.regex_btn)

        self.root.addWidget(VerticalSeparator())

        # 搜索输入框
        self.line_edit = SearchLineEdit(self)
        self.line_edit.setMinimumWidth(256)
        self.line_edit.setStyleSheet("""
            SearchLineEdit {
                border: none;
                background: transparent;
                border-radius: 4px;
                padding: 4px 8px;
            }
            SearchLineEdit:hover {
                background: rgba(0, 0, 0, 0.05);
            }
            SearchLineEdit[has-focus=true] {
                background: rgba(255, 255, 255, 0.7);
                border-bottom: 2px solid #005fb8;
            }
        """)
        self.line_edit.setPlaceholderText(Localizer.get().placeholder)
        self.line_edit.setClearButtonEnabled(True)
        self.root.addWidget(self.line_edit, 1)

        self.root.addWidget(VerticalSeparator())

        # 导航按钮
        self.prev = TransparentToolButton(self)
        self.prev.setIcon(FluentIcon.UP)
        self.prev.setToolTip(Localizer.get().search_prev_match)
        self.prev.installEventFilter(ToolTipFilter(self.prev, 300, ToolTipPosition.TOP))
        self.root.addWidget(self.prev)

        self.next = TransparentToolButton(self)
        self.next.setIcon(FluentIcon.DOWN)
        self.next.setToolTip(Localizer.get().search_next_match)
        self.next.installEventFilter(ToolTipFilter(self.next, 300, ToolTipPosition.TOP))
        self.root.addWidget(self.next)

        self.root.addWidget(VerticalSeparator())

        # 匹配数量显示
        self.match_label = CaptionLabel(Localizer.get().search_no_result, self)
        self.match_label.setMinimumWidth(64)
        self.root.addWidget(self.match_label)

        self.root.addStretch(1)

        # 返回按钮
        self.back = TransparentPushButton(self)
        self.back.setIcon(FluentIcon.EMBED)
        self.back.setText(Localizer.get().back)
        self.root.addWidget(self.back)

    def _on_regex_toggle(self) -> None:
        self._regex_mode = self.regex_btn.isChecked()
        self._update_regex_tooltip()

    def _update_regex_tooltip(self) -> None:
        tooltip = Localizer.get().search_regex_on if self._regex_mode else Localizer.get().search_regex_off
        self.regex_btn.setToolTip(tooltip)

    def is_regex_mode(self) -> bool:
        return self._regex_mode

    def get_line_edit(self) -> SearchLineEdit:
        return self.line_edit

    def get_keyword(self) -> str:
        return self.line_edit.text().strip()

    def set_match_info(self, current: int, total: int) -> None:
        if total > 0:
            self.match_label.setText(Localizer.get().search_match_info.format(current = current, total = total))
        else:
            self.match_label.setText(Localizer.get().search_no_result)

    def clear_match_info(self) -> None:
        self.match_label.setText(Localizer.get().search_no_result)

    def validate_regex(self) -> tuple[bool, str]:
        if not self._regex_mode:
            return True, ""

        pattern = self.get_keyword()
        if not pattern:
            return True, ""

        try:
            re.compile(pattern)
            return True, ""
        except re.error as e:
            return False, str(e)

    def on_prev_clicked(self, clicked: Callable) -> None:
        self.prev.clicked.connect(lambda: clicked(self))

    def on_next_clicked(self, clicked: Callable) -> None:
        self.next.clicked.connect(lambda: clicked(self))

    def on_back_clicked(self, clicked: Callable) -> None:
        self.back.clicked.connect(lambda: clicked(self))

    def on_search_triggered(self, triggered: Callable) -> None:
        self.line_edit.searchSignal.connect(lambda text: triggered(self))
        self.line_edit.returnPressed.connect(lambda: triggered(self))
