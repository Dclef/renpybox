from PyQt5.QtCore import QSize
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QAbstractItemView
from PyQt5.QtWidgets import QGridLayout
from PyQt5.QtWidgets import QListWidgetItem
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import BodyLabel
from qfluentwidgets import CardWidget
from qfluentwidgets import CheckBox
from qfluentwidgets import ListWidget
from qfluentwidgets import MessageBoxBase
from qfluentwidgets import StrongBodyLabel

from module.Engine.Quality.TranslationQualityReport import TranslationQualityReport
from module.Localizer.Localizer import Localizer
from widget.Separator import Separator


class QualityReportDialog(MessageBoxBase):
    """展示初译质量报告，并返回用户选择的待校对条目。"""

    def __init__(self, report: TranslationQualityReport, parent: QWidget) -> None:
        super().__init__(parent)
        self.report = report
        self.item_checkboxes: dict[int, CheckBox] = {}
        self._init_ui()

    def _init_ui(self) -> None:
        self.widget.setMinimumWidth(720)
        self.viewLayout.setSpacing(16)
        self.viewLayout.setContentsMargins(24, 24, 24, 24)

        self.viewLayout.addWidget(self._build_summary_card())
        self.viewLayout.addWidget(self._build_item_card())

        self.yesButton.setText(Localizer.get().proofreading_page_quality_report_proofread)
        self.cancelButton.setText(Localizer.get().cancel)
        self.yesButton.setEnabled(bool(self.item_checkboxes))

    def _build_summary_card(self) -> CardWidget:
        card = CardWidget(self.widget)
        card.setBorderRadius(4)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(StrongBodyLabel(Localizer.get().proofreading_page_quality_report_title, card))
        layout.addWidget(Separator(card))

        summary = QGridLayout()
        summary.setHorizontalSpacing(24)
        summary.setVerticalSpacing(8)
        values = (
            (
                Localizer.get().proofreading_page_quality_report_failed,
                self.report.failed_count,
            ),
            (
                Localizer.get().proofreading_page_quality_report_fallback,
                self.report.fallback_count,
            ),
            (
                Localizer.get().proofreading_page_quality_report_alignment,
                self.report.line_mismatch_count,
            ),
        )
        for column, (label, value) in enumerate(values):
            summary.addWidget(BodyLabel(label, card), 0, column)
            summary.addWidget(StrongBodyLabel(str(value), card), 1, column)
        layout.addLayout(summary)

        error_text = self._format_error_counts(self.report.error_type_counts)
        layout.addWidget(BodyLabel(
            Localizer.get().proofreading_page_quality_report_error_types.replace(
                "{ERRORS}", error_text
            ),
            card,
        ))
        return card

    def _build_item_card(self) -> CardWidget:
        card = CardWidget(self.widget)
        card.setBorderRadius(4)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(StrongBodyLabel(
            Localizer.get().proofreading_page_quality_report_items,
            card,
        ))
        layout.addWidget(Separator(card))

        item_list = ListWidget(card)
        item_list.setFixedHeight(300)
        item_list.setSelectionMode(QAbstractItemView.NoSelection)
        item_list.setFocusPolicy(Qt.NoFocus)
        item_list.itemClicked.connect(self._on_item_clicked)

        if not self.report.item_references:
            item_list.addItem(Localizer.get().proofreading_page_quality_report_empty)
        else:
            for reference in self.report.item_references:
                list_item = QListWidgetItem()
                list_item.setSizeHint(QSize(0, 48))
                list_item.setData(Qt.UserRole, reference.item_index)
                item_list.addItem(list_item)

                error_types = ", ".join(reference.error_types) or "-"
                label = CheckBox(
                    f"{reference.reference}  [{error_types}]  {reference.source_preview}",
                    item_list,
                )
                label.setChecked(True)
                label.setToolTip(reference.source_preview)
                label.setAttribute(Qt.WA_TransparentForMouseEvents)
                item_list.setItemWidget(list_item, label)
                self.item_checkboxes[reference.item_index] = label

        self.item_list = item_list
        layout.addWidget(item_list)
        return card

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        item_index = item.data(Qt.UserRole)
        checkbox = self.item_checkboxes.get(item_index)
        if checkbox is not None:
            checkbox.setChecked(not checkbox.isChecked())
        self.yesButton.setEnabled(bool(self.get_selected_item_indices()))

    @staticmethod
    def _format_error_counts(error_type_counts: dict[str, int]) -> str:
        if not error_type_counts:
            return "-"
        return ", ".join(
            f"{error_type}: {count}"
            for error_type, count in sorted(error_type_counts.items())
        )

    def get_selected_item_indices(self) -> tuple[int, ...]:
        return tuple(sorted(
            item_index
            for item_index, checkbox in self.item_checkboxes.items()
            if checkbox.isChecked()
        ))
