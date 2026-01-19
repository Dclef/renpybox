from PyQt5.QtCore import Qt
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QAbstractItemView
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QHeaderView
from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import Action
from qfluentwidgets import FluentIcon
from qfluentwidgets import IconWidget
from qfluentwidgets import PillToolButton
from qfluentwidgets import RoundMenu
from qfluentwidgets import TableWidget
from qfluentwidgets import ToolTipFilter
from qfluentwidgets import ToolTipPosition

from base.Base import Base
from frontend.Proofreading.TextEditDialog import TextEditDialog
from module.Cache.CacheItem import CacheItem
from module.Localizer.Localizer import Localizer
from module.ResultChecker import WarningType

class ProofreadingTableWidget(TableWidget):
    """校对任务专用表格组件"""

    cell_edited = pyqtSignal(object, str)
    retranslate_clicked = pyqtSignal(object)
    copy_src_clicked = pyqtSignal(object)
    copy_dst_clicked = pyqtSignal(object)

    COL_SRC = 0
    COL_DST = 1
    COL_STATUS = 2
    COL_ACTION = 3

    COL_WIDTH_STATUS = 60
    COL_WIDTH_ACTION = 60
    SYMBOL_NEWLINE = " ↵ "

    ITEM_ROLE = Qt.UserRole + 1

    STATUS_ICONS = {
        Base.TranslationStatus.TRANSLATED: FluentIcon.COMPLETED,
        Base.TranslationStatus.TRANSLATED_IN_PAST: FluentIcon.HISTORY,
    }

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)

        self.setColumnCount(4)
        self.setHorizontalHeaderLabels([
            Localizer.get().proofreading_page_col_src,
            Localizer.get().proofreading_page_col_dst,
            Localizer.get().proofreading_page_col_status,
            "",
        ])

        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.verticalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.setBorderVisible(False)

        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideRight)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.verticalHeader().setDefaultSectionSize(40)

        header = self.horizontalHeader()
        header.setSectionResizeMode(self.COL_SRC, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_DST, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_STATUS, QHeaderView.Fixed)
        header.setSectionResizeMode(self.COL_ACTION, QHeaderView.Fixed)
        self.setColumnWidth(self.COL_STATUS, self.COL_WIDTH_STATUS)
        self.setColumnWidth(self.COL_ACTION, self.COL_WIDTH_ACTION)

        self._readonly = False
        self._loading_rows: set[int] = set()

        self.cellDoubleClicked.connect(self._on_cell_double_clicked)

    def set_items(self, items: list[CacheItem], warning_map: dict[int, list[WarningType]]) -> None:
        self.blockSignals(True)
        self.setUpdatesEnabled(False)

        self._clear_cell_widgets()

        self.clearContents()
        if not items:
            self.setRowCount(30)
            for row in range(30):
                for col in range(self.columnCount()):
                    item = QTableWidgetItem("")
                    item.setFlags(Qt.ItemIsEnabled)
                    self.setItem(row, col, item)
        else:
            self.setRowCount(len(items))
            for row, item in enumerate(items):
                self._set_row_data(row, item, warning_map.get(id(item), []))

        self.setUpdatesEnabled(True)
        self.blockSignals(False)

    def _clear_cell_widgets(self) -> None:
        for row in range(self.rowCount()):
            for col in (self.COL_STATUS, self.COL_ACTION):
                widget = self.cellWidget(row, col)
                if widget:
                    self.removeCellWidget(row, col)
                    widget.deleteLater()

    def _set_row_data(self, row: int, item: CacheItem, warnings: list[WarningType]) -> None:
        src_text = item.get_src()
        dst_text = item.get_dst()

        src_display = src_text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", self.SYMBOL_NEWLINE)
        src_item = QTableWidgetItem(src_display)
        src_item.setFlags(src_item.flags() & ~Qt.ItemIsEditable)
        src_item.setData(self.ITEM_ROLE, item)
        src_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        src_item.setToolTip(src_text)
        self.setItem(row, self.COL_SRC, src_item)

        dst_display = dst_text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", self.SYMBOL_NEWLINE)
        dst_item = QTableWidgetItem(dst_display)
        dst_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        dst_item.setToolTip(dst_text)
        if self._readonly:
            dst_item.setFlags(dst_item.flags() & ~Qt.ItemIsEditable)
        self.setItem(row, self.COL_DST, dst_item)

        self._create_status_widget(row, item, warnings)
        self._create_action_widget(row, item)

    def _create_status_widget(self, row: int, item: CacheItem, warnings: list[WarningType]) -> None:
        widget = QWidget()
        widget.setFixedHeight(40)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        status = item.get_status()

        if status in self.STATUS_ICONS:
            status_icon = IconWidget(self.STATUS_ICONS[status])
            status_icon.setFixedSize(16, 16)
            status_icon.installEventFilter(ToolTipFilter(status_icon, 300, ToolTipPosition.TOP))
            status_tooltip = (
                f"{Localizer.get().proofreading_page_filter_status}\n"
                f"{Localizer.get().current_status}{self._get_status_text(status)}"
            )
            status_icon.setToolTip(status_tooltip)
            layout.addWidget(status_icon)

        if warnings:
            warning_icon = IconWidget(FluentIcon.VPN)
            warning_icon.setFixedSize(16, 16)
            warning_texts = [self._get_warning_text(e) for e in warnings]
            warning_icon.installEventFilter(ToolTipFilter(warning_icon, 300, ToolTipPosition.TOP))
            warning_tooltip = (
                f"{Localizer.get().proofreading_page_warning_tooltip_title}\n"
                f"{Localizer.get().current_status}{' | '.join(warning_texts)}"
            )
            warning_icon.setToolTip(warning_tooltip)
            layout.addWidget(warning_icon)

        self.setCellWidget(row, self.COL_STATUS, widget)

    def _get_status_text(self, status: Base.TranslationStatus) -> str:
        status_texts = {
            Base.TranslationStatus.UNTRANSLATED: Localizer.get().proofreading_page_status_none,
            Base.TranslationStatus.TRANSLATED: Localizer.get().proofreading_page_status_processed,
            Base.TranslationStatus.TRANSLATED_IN_PAST: Localizer.get().proofreading_page_status_processed_in_past,
        }
        return status_texts.get(status, str(status))

    def _get_warning_text(self, error: WarningType) -> str:
        warning_texts = {
            WarningType.KANA: Localizer.get().proofreading_page_warning_kana,
            WarningType.HANGEUL: Localizer.get().proofreading_page_warning_hangeul,
            WarningType.TEXT_PRESERVE: Localizer.get().proofreading_page_warning_text_preserve,
            WarningType.SIMILARITY: Localizer.get().proofreading_page_warning_similarity,
            WarningType.GLOSSARY: Localizer.get().proofreading_page_warning_glossary,
            WarningType.RETRY_THRESHOLD: Localizer.get().proofreading_page_warning_retry,
        }
        return warning_texts.get(error, str(error))

    def _create_action_widget(self, row: int, item: CacheItem) -> None:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 4, 16, 4)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)

        btn_action = PillToolButton(FluentIcon.MORE, widget)
        btn_action.setCheckable(False)
        btn_action.setEnabled(not self._readonly and row not in self._loading_rows)

        def show_menu() -> None:
            menu = RoundMenu(parent = btn_action)

            menu.addAction(Action(
                FluentIcon.SYNC,
                Localizer.get().proofreading_page_retranslate,
                triggered = lambda checked: self.retranslate_clicked.emit(item)
            ))

            menu.addAction(Action(
                FluentIcon.PASTE,
                Localizer.get().proofreading_page_copy_src,
                triggered = lambda checked: self.copy_src_clicked.emit(item)
            ))

            menu.addAction(Action(
                FluentIcon.COPY,
                Localizer.get().proofreading_page_copy_dst,
                triggered = lambda checked: self.copy_dst_clicked.emit(item)
            ))

            menu.exec(btn_action.mapToGlobal(btn_action.rect().bottomLeft()))

        btn_action.clicked.connect(show_menu)
        layout.addWidget(btn_action)

        self.setCellWidget(row, self.COL_ACTION, widget)

    def get_item_at_row(self, row: int) -> CacheItem | None:
        src_cell = self.item(row, self.COL_SRC)
        if src_cell:
            return src_cell.data(self.ITEM_ROLE)
        return None

    def update_row_status(self, row: int, warnings: list[WarningType]) -> None:
        item = self.get_item_at_row(row)
        if item:
            self._create_status_widget(row, item, warnings)

    def set_row_loading(self, row: int, loading: bool) -> None:
        if loading:
            self._loading_rows.add(row)
        else:
            self._loading_rows.discard(row)

        widget = self.cellWidget(row, self.COL_ACTION)
        if widget:
            for btn in widget.findChildren(PillToolButton):
                btn.setEnabled(not loading and not self._readonly)

    def set_readonly(self, readonly: bool) -> None:
        self._readonly = readonly

        for row in range(self.rowCount()):
            dst_cell = self.item(row, self.COL_DST)
            if dst_cell:
                flags = dst_cell.flags()
                if readonly:
                    flags = flags & ~Qt.ItemIsEditable
                else:
                    flags = flags | Qt.ItemIsEditable
                dst_cell.setFlags(flags)

            widget = self.cellWidget(row, self.COL_ACTION)
            if widget:
                for btn in widget.findChildren(PillToolButton):
                    btn.setEnabled(not readonly and row not in self._loading_rows)

    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        if column not in (self.COL_SRC, self.COL_DST):
            return

        if self._readonly:
            return

        item = self.get_item_at_row(row)
        if not item:
            return

        dialog = TextEditDialog(item.get_src(), item.get_dst(), self.window())
        if dialog.exec():
            new_dst = dialog.get_dst_text()
            if new_dst != item.get_dst():
                self.update_row_dst(row, new_dst)
                self.cell_edited.emit(item, new_dst)

    def find_row_by_item(self, item: CacheItem) -> int:
        for row in range(self.rowCount()):
            if self.get_item_at_row(row) is item:
                return row
        return -1

    def update_row_dst(self, row: int, new_dst: str) -> None:
        self.blockSignals(True)
        dst_cell = self.item(row, self.COL_DST)
        if dst_cell:
            dst_display = new_dst.replace("\r\n", "\n").replace("\r", "\n").replace("\n", self.SYMBOL_NEWLINE)
            dst_cell.setText(dst_display)
            dst_cell.setToolTip(new_dst)
        self.blockSignals(False)

    def select_row(self, row: int) -> None:
        if row < 0 or row >= self.rowCount():
            return
        self.selectRow(row)
        QTimer.singleShot(0, lambda: self.scrollToItem(self.item(row, self.COL_SRC), QAbstractItemView.PositionAtCenter))
