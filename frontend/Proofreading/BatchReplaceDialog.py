from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import CaptionLabel
from qfluentwidgets import CardWidget
from qfluentwidgets import CheckBox
from qfluentwidgets import ComboBox
from qfluentwidgets import LineEdit
from qfluentwidgets import MessageBoxBase
from qfluentwidgets import StrongBodyLabel

from module.Localizer.Localizer import Localizer
from widget.Separator import Separator


class BatchReplaceDialog(MessageBoxBase):
    """校对页批量替换对话框。"""

    SCOPE_SELECTED = "SELECTED"
    SCOPE_FILTERED = "FILTERED"

    def __init__(self, selected_count: int, filtered_count: int, parent: QWidget) -> None:
        super().__init__(parent)

        self.selected_count = selected_count
        self.filtered_count = filtered_count

        self._scope_values: list[str] = []
        self._init_ui()

    def _init_ui(self) -> None:
        self.widget.setMinimumWidth(560)
        self.viewLayout.setSpacing(16)
        self.viewLayout.setContentsMargins(24, 24, 24, 24)

        self.viewLayout.addWidget(self._build_find_replace_card())
        self.viewLayout.addWidget(self._build_option_card())

        self.yesButton.setText(Localizer.get().confirm)
        self.cancelButton.setText(Localizer.get().cancel)

        self.find_edit.setFocus()

    def _build_find_replace_card(self) -> CardWidget:
        card = CardWidget(self.widget)
        card.setBorderRadius(4)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel(Localizer.get().proofreading_page_batch_replace_action))
        layout.addWidget(Separator(card))

        find_title = CaptionLabel(Localizer.get().proofreading_page_batch_replace_find, card)
        layout.addWidget(find_title)
        self.find_edit = LineEdit(card)
        self.find_edit.setPlaceholderText(Localizer.get().placeholder)
        layout.addWidget(self.find_edit)

        replace_title = CaptionLabel(Localizer.get().proofreading_page_batch_replace_with, card)
        layout.addWidget(replace_title)
        self.replace_edit = LineEdit(card)
        layout.addWidget(self.replace_edit)

        return card

    def _build_option_card(self) -> CardWidget:
        card = CardWidget(self.widget)
        card.setBorderRadius(4)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel(Localizer.get().proofreading_page_batch_replace_options))
        layout.addWidget(Separator(card))

        option_row = QHBoxLayout()
        option_row.setContentsMargins(0, 0, 0, 0)
        option_row.setSpacing(24)

        self.regex_checkbox = CheckBox(Localizer.get().proofreading_page_batch_replace_regex, card)
        self.case_sensitive_checkbox = CheckBox(Localizer.get().proofreading_page_batch_replace_case_sensitive, card)
        option_row.addWidget(self.regex_checkbox)
        option_row.addWidget(self.case_sensitive_checkbox)
        option_row.addStretch(1)
        layout.addLayout(option_row)

        scope_title = CaptionLabel(Localizer.get().proofreading_page_batch_replace_scope, card)
        layout.addWidget(scope_title)

        self.scope_combo = ComboBox(card)
        scope_labels: list[str] = []

        if self.selected_count > 0:
            scope_labels.append(
                Localizer.get().proofreading_page_batch_replace_scope_selected.replace(
                    "{COUNT}", str(self.selected_count)
                )
            )
            self._scope_values.append(__class__.SCOPE_SELECTED)

        scope_labels.append(
            Localizer.get().proofreading_page_batch_replace_scope_filtered.replace(
                "{COUNT}", str(self.filtered_count)
            )
        )
        self._scope_values.append(__class__.SCOPE_FILTERED)

        self.scope_combo.addItems(scope_labels)
        layout.addWidget(self.scope_combo)

        return card

    def get_payload(self) -> dict[str, str | bool]:
        index = self.scope_combo.currentIndex()
        scope = self._scope_values[index] if 0 <= index < len(self._scope_values) else __class__.SCOPE_FILTERED

        return {
            "find_text": self.find_edit.text(),
            "replace_text": self.replace_edit.text(),
            "regex": self.regex_checkbox.isChecked(),
            "case_sensitive": self.case_sensitive_checkbox.isChecked(),
            "scope": scope,
        }
