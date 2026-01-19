from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import CardWidget
from qfluentwidgets import MessageBoxBase
from qfluentwidgets import PlainTextEdit
from qfluentwidgets import StrongBodyLabel

from module.Localizer.Localizer import Localizer
from widget.Separator import Separator

class TextEditDialog(MessageBoxBase):
    """多行文本编辑对话框"""

    def __init__(self, src_text: str, dst_text: str, parent: QWidget) -> None:
        super().__init__(parent)

        self.src_text = src_text
        self.dst_text = dst_text
        self._init_ui()

    def _init_ui(self) -> None:
        self.widget.setMinimumWidth(720)
        self.widget.setMinimumHeight(560)
        self.viewLayout.setSpacing(16)

        self.src_card = self._create_group_card(Localizer.get().proofreading_page_col_src)

        self.src_text_edit = PlainTextEdit(self.src_card)
        self.src_text_edit.setPlainText(self.src_text)
        self.src_text_edit.setReadOnly(True)
        self.src_text_edit.setMinimumHeight(150)

        self.src_card.layout().addWidget(self.src_text_edit)
        self.viewLayout.addWidget(self.src_card)

        self.dst_card = self._create_group_card(Localizer.get().proofreading_page_col_dst)

        self.dst_text_edit = PlainTextEdit(self.dst_card)
        self.dst_text_edit.setPlainText(self.dst_text)
        self.dst_text_edit.setMinimumHeight(200)

        self.dst_card.layout().addWidget(self.dst_text_edit)
        self.viewLayout.addWidget(self.dst_card, 1)

        self.yesButton.setText(Localizer.get().confirm)
        self.cancelButton.setText(Localizer.get().cancel)

        self.dst_text_edit.setFocus()

    def _create_group_card(self, title: str) -> CardWidget:
        card = CardWidget(self.widget)
        card.setBorderRadius(4)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel(title, card))
        layout.addWidget(Separator(card))

        return card

    def get_dst_text(self) -> str:
        return self.dst_text_edit.toPlainText()
