from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QBoxLayout
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import CardWidget
from qfluentwidgets import MessageBoxBase
from qfluentwidgets import PlainTextEdit
from qfluentwidgets import StrongBodyLabel

from module.Localizer.Localizer import Localizer

class TextEditDialog(MessageBoxBase):
    """多行文本编辑对话框"""

    def __init__(self, src_text: str, dst_text: str, parent: QWidget) -> None:
        super().__init__(parent)

        self.src_text = src_text
        self.dst_text = dst_text
        self._init_ui()

    def _init_ui(self) -> None:
        self.viewLayout.setSpacing(16)
        self.editor_layout = QBoxLayout(QBoxLayout.LeftToRight)
        self.editor_layout.setSpacing(12)
        self.viewLayout.addLayout(self.editor_layout, 1)

        self.src_card = self._create_group_card(Localizer.get().proofreading_page_col_src)

        self.src_text_edit = PlainTextEdit(self.src_card)
        self.src_text_edit.setPlainText(self.src_text)
        self.src_text_edit.setReadOnly(True)
        self.src_text_edit.setMinimumHeight(80)

        self.src_card.layout().addWidget(self.src_text_edit)
        self.editor_layout.addWidget(self.src_card, 1)

        self.dst_card = self._create_group_card(Localizer.get().proofreading_page_col_dst)

        self.dst_text_edit = PlainTextEdit(self.dst_card)
        self.dst_text_edit.setPlainText(self.dst_text)
        self.dst_text_edit.setMinimumHeight(80)

        self.dst_card.layout().addWidget(self.dst_text_edit)
        self.editor_layout.addWidget(self.dst_card, 1)

        self.yesButton.setText(Localizer.get().confirm)
        self.cancelButton.setText(Localizer.get().cancel)

        self.dst_text_edit.setFocus()
        self._fit_editors()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "editor_layout"):
            self._fit_editors()

    def _fit_editors(self) -> None:
        """宽窗并排对照，窄窗上下排列，编辑窗口保持在父窗口内。"""
        self.editor_layout.setDirection(
            QBoxLayout.LeftToRight if self.width() >= 760 else QBoxLayout.TopToBottom
        )
        self.widget.setFixedSize(
            min(960, max(280, self.width() - 48)),
            min(560, max(320, self.height() - 48)),
        )

    def _create_group_card(self, title: str) -> CardWidget:
        card = CardWidget(self.widget)
        card.setBorderRadius(8)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel(title, card))

        return card

    def get_dst_text(self) -> str:
        return self.dst_text_edit.toPlainText()
