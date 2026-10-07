"""QTableWidget 绑定层（M1 从 module/TableManager.py 拆出）。

只负责把 TableManager 里的数据刷进 Qt 表格、以及把表格交互写回数据。
Electron 侧不需要这一层——它由 React 虚拟表格直接消费 TableManager 的数据。
"""
from functools import partial

from PyQt5.QtCore import Qt
from PyQt5.QtCore import QModelIndex
from PyQt5.QtWidgets import QTableWidgetItem
from qfluentwidgets import TableWidget

from module.TableManager import TableManager
from widget.RuleWidget import RuleWidget


class LegacyTableBinding(TableManager):
    """把 TableManager 的数据渲染成QTableWidget，并处理行内编辑。"""

    def __init__(self, type: str, data: list[dict[str, str]], table: TableWidget) -> None:
        super().__init__(type, data)

        self.table = table

    def reset(self) -> None:
        super().reset()
        self.table.clearContents()
        self.table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)

    def sync(self) -> None:
        self.set_updating(True)

        super().sync()

        self.table.setRowCount(max(20, len(self.data) + 8))
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item is not None:
                    item.setText("")
                else:
                    self.table.setItem(row, col, self.generate_item(col))

        if self.type == __class__.Type.GLOSSARY:
            for row, v in enumerate(self.data):
                for col in range(self.table.columnCount()):
                    if col == 0:
                        self.table.item(row, col).setText(v.get("src", ""))
                    elif col == 1:
                        self.table.item(row, col).setText(v.get("dst", ""))
                    elif col == 2:
                        self.table.item(row, col).setText(v.get("info", ""))
                    elif col == 3:
                        rule_widget = RuleWidget(
                            show_regex = False,
                            show_case_sensitive = True,
                            case_sensitive_enabled = v.get("case_sensitive", False),
                            on_changed = partial(self._on_rule_changed, row, v),
                        )
                        self.table.setCellWidget(row, col, rule_widget)
        elif self.type == __class__.Type.REPLACEMENT:
            for row, v in enumerate(self.data):
                for col in range(self.table.columnCount()):
                    if col == 0:
                        self.table.item(row, col).setText(v.get("src", ""))
                    elif col == 1:
                        self.table.item(row, col).setText(v.get("dst", ""))
                    elif col == 2:
                        rule_widget = RuleWidget(
                            show_regex = True,
                            show_case_sensitive = True,
                            regex_enabled = v.get("regex", False),
                            case_sensitive_enabled = v.get("case_sensitive", False),
                            on_changed = partial(self._on_rule_changed, row, v),
                        )
                        self.table.setCellWidget(row, col, rule_widget)
        elif self.type == __class__.Type.TEXT_PRESERVE:
            for row, v in enumerate(self.data):
                for col in range(self.table.columnCount()):
                    if col == 0:
                        self.table.item(row, col).setText(v.get("src", ""))
                    elif col == 1:
                        self.table.item(row, col).setText(v.get("info", ""))

        self.set_updating(False)

    def generate_item(self, col: int) -> QTableWidgetItem:
        item = QTableWidgetItem("")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        if self.type == __class__.Type.GLOSSARY:
            if col == 3:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        elif self.type == __class__.Type.REPLACEMENT:
            if col == 2:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        elif self.type == __class__.Type.TEXT_PRESERVE:
            pass

        return item

    def delete_row(self) -> None:
        selected_index = self.table.selectedIndexes()

        if selected_index == None or len(selected_index) == 0:
            return

        for row in sorted({item.row() for item in selected_index}, reverse = True):
            self.table.removeRow(row)

        self.table.itemChanged.emit(QTableWidgetItem())

    def switch_regex(self) -> None:
        selected_index: list[QModelIndex] = self.table.selectedIndexes()

        if selected_index == None or len(selected_index) == 0:
            return

        for index in selected_index:
            row = index.row()
            item = self.table.item(row, 2)
            if item is not None:
                item.setText("False")
                self.table.setItem(row, 2, item)

    def get_entry_by_row(self, row: int) -> dict[str, str | bool]:
        result: dict[str, str | bool] = {
            "src": "",
            "dst": "",
            "info": "",
            "regex": False,
            "case_sensitive": False,
        }

        for col in range(self.table.columnCount()):
            items: list[QTableWidgetItem] = [
                self.table.item(row, col)
            ]
            if self.type == __class__.Type.GLOSSARY:
                if col == 0:
                    result["src"] = items[0].text().strip() if isinstance(items[0], QTableWidgetItem) else ""
                elif col == 1:
                    result["dst"] = items[0].text().strip() if isinstance(items[0], QTableWidgetItem) else ""
                elif col == 2:
                    result["info"] = items[0].text().strip() if isinstance(items[0], QTableWidgetItem) else ""
                elif col == 3:
                    rule_widget = self.table.cellWidget(row, 3)
                    result["case_sensitive"] = getattr(rule_widget, "case_sensitive", False)
            elif self.type == __class__.Type.REPLACEMENT:
                if col == 0:
                    result["src"] = items[0].text().strip() if isinstance(items[0], QTableWidgetItem) else ""
                elif col == 1:
                    result["dst"] = items[0].text().strip() if isinstance(items[0], QTableWidgetItem) else ""
                elif col == 2:
                    rule_widget = self.table.cellWidget(row, 2)
                    result["regex"] = getattr(rule_widget, "regex", False)
                    result["case_sensitive"] = getattr(rule_widget, "case_sensitive", False)
            elif self.type == __class__.Type.TEXT_PRESERVE:
                if col == 0:
                    result["src"] = items[0].text().strip() if isinstance(items[0], QTableWidgetItem) else ""
                elif col == 1:
                    result["info"] = items[0].text().strip() if isinstance(items[0], QTableWidgetItem) else ""

        return result

    def append_data_from_table(self) -> None:
        for row in range(self.table.rowCount()):
            entry: dict[str, str | bool] = self.get_entry_by_row(row)
            if entry.get("src") != "":
                self.data.append(entry)

    def _on_rule_changed(self, row: int, data_ref: dict[str, str | bool], regex: bool, case_sensitive: bool) -> None:
        if self.type == __class__.Type.REPLACEMENT:
            data_ref["regex"] = regex

        data_ref["case_sensitive"] = case_sensitive

        self.table.itemChanged.emit(self.table.item(row, 0))