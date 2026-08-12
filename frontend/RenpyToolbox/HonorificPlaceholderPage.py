"""
称呼变量智能桥接管理页面
管理用于识别"称呼 + 变量"结构的称呼词列表，支持自定义增删改。
翻译时将 Mr.[xx] 等模式临时替换为结构化占位符，译后自动还原并修正中文语序。
"""

from typing import List

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)
from qfluentwidgets import (
    CardWidget,
    PrimaryPushButton,
    PushButton,
    InfoBar,
    FluentIcon,
    TitleLabel,
    CaptionLabel,
    StrongBodyLabel,
    SwitchButton,
    isDarkTheme,
    qconfig,
)

from base.Base import Base
from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.TextProcessor import TextProcessor


class HonorificPlaceholderPage(Base, QWidget):
    """称呼变量智能桥接管理页面"""

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        self.setProperty("toolboxPage", True)

        self.config = Config().load()

        self._init_ui()
        self._load_from_config()

        # 监听主题变化以更新表格配色
        qconfig.themeChanged.connect(self._on_theme_changed)

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        title = TitleLabel(Localizer.localize("称呼变量智能桥接", "Honorific Variable Bridge"))
        layout.addWidget(title)

        # 描述
        desc = CaptionLabel(
            Localizer.localize(
                "管理用于识别「称呼 + 变量」结构的称呼词列表。"
                "翻译时将 Mr.[xx] 等模式临时替换为结构化占位符，译后自动还原并修正中文语序（如 [xx]先生）。",
                "Manage honorific terms used to recognize honorific-plus-variable patterns. During translation, patterns such as Mr.[xx] become structured placeholders and are restored afterward with the correct word order.",
            )
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 启用开关卡片
        layout.addWidget(self._build_switch_card())

        # 工具栏
        layout.addWidget(self._build_toolbar_card())

        # 表格
        layout.addWidget(self._build_table_card())

        layout.addStretch(1)

    # ---------- 启用开关
    def _build_switch_card(self) -> CardWidget:
        card = CardWidget(self)
        h_layout = QHBoxLayout(card)
        h_layout.setContentsMargins(16, 12, 16, 12)
        h_layout.setSpacing(12)

        label = StrongBodyLabel(Localizer.localize("启用称呼变量智能桥接", "Enable Honorific Variable Bridge"))
        h_layout.addWidget(label)

        desc_label = CaptionLabel(
            Localizer.localize("开启后，翻译流程会自动检测并处理 称呼+变量 结构", "Automatically detect and process honorific-plus-variable patterns during translation.")
        )
        desc_label.setWordWrap(True)
        h_layout.addWidget(desc_label, 1)

        self.switch_btn = SwitchButton()
        self.switch_btn.setChecked(
            getattr(self.config, "honorific_placeholder_bridge_enable", True)
        )
        self.switch_btn.checkedChanged.connect(self._on_switch_changed)
        h_layout.addWidget(self.switch_btn)

        return card

    def _on_switch_changed(self, checked: bool):
        config = Config().load()
        config.honorific_placeholder_bridge_enable = checked
        config.save()

    # ---------- 工具栏
    def _build_toolbar_card(self) -> CardWidget:
        card = CardWidget(self)
        v_layout = QVBoxLayout(card)
        v_layout.setContentsMargins(16, 12, 16, 12)
        v_layout.setSpacing(6)

        # 第一排：保存 / 从配置加载
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        save_btn = PrimaryPushButton(Localizer.localize("保存到配置", "Save to Settings"), icon=FluentIcon.SAVE)
        save_btn.clicked.connect(self._save_to_config)
        row1.addWidget(save_btn)

        load_btn = PushButton(Localizer.localize("从配置加载", "Load from Settings"), icon=FluentIcon.HISTORY)
        load_btn.clicked.connect(self._load_from_config)
        row1.addWidget(load_btn)

        row1.addStretch(1)
        v_layout.addLayout(row1)

        # 第二排：新增 / 删除选中 / 去重 / 清空 / 恢复默认
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        add_btn = PushButton(Localizer.localize("新增条目", "Add Entry"), icon=FluentIcon.ADD)
        add_btn.clicked.connect(self._add_row)
        row2.addWidget(add_btn)

        delete_btn = PushButton(Localizer.localize("删除选中", "Delete Selected"), icon=FluentIcon.DELETE)
        delete_btn.clicked.connect(self._remove_selected_rows)
        row2.addWidget(delete_btn)

        dedup_btn = PushButton(Localizer.localize("去重", "Remove Duplicates"), icon=FluentIcon.FILTER)
        dedup_btn.setToolTip(Localizer.localize("按称呼词去重，合并备注", "Remove duplicate honorifics and merge notes"))
        dedup_btn.clicked.connect(self._deduplicate_rows)
        row2.addWidget(dedup_btn)

        clear_btn = PushButton(Localizer.localize("清空全部", "Clear All"), icon=FluentIcon.CLOSE)
        clear_btn.setToolTip(Localizer.localize("清空所有称呼词", "Remove all honorific terms"))
        clear_btn.clicked.connect(self._clear_all)
        row2.addWidget(clear_btn)

        restore_btn = PushButton(Localizer.localize("恢复默认", "Restore Defaults"), icon=FluentIcon.SYNC)
        restore_btn.setToolTip(Localizer.localize("恢复为内置默认称呼词列表", "Restore the built-in honorific list"))
        restore_btn.clicked.connect(self._restore_defaults)
        row2.addWidget(restore_btn)

        row2.addStretch(1)
        v_layout.addLayout(row2)

        return card

    # ---------- 表格
    def _build_table_card(self) -> CardWidget:
        card = CardWidget(self)
        v_layout = QVBoxLayout(card)
        v_layout.setContentsMargins(16, 12, 16, 16)
        v_layout.setSpacing(12)

        table_label = StrongBodyLabel(Localizer.localize("称呼词列表（可直接编辑单元格）", "Honorific Terms (cells are editable)"))
        v_layout.addWidget(table_label)

        headers = (
            Localizer.localize("称呼词", "Honorific"),
            Localizer.localize("备注", "Notes"),
        )
        self.table = QTableWidget(0, len(headers), self)
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
        )
        self.table.verticalHeader().setVisible(False)
        self._apply_table_theme()
        v_layout.addWidget(self.table)

        return card

    # ------------------------------------------------------------------ 主题
    def _apply_table_theme(self) -> None:
        """根据当前主题更新表格样式"""
        if isDarkTheme():
            stylesheet = """
                QTableWidget {
                    background-color: rgb(39, 39, 39);
                    alternate-background-color: rgb(45, 45, 45);
                    color: rgb(200, 200, 200);
                    border: 1px solid rgb(55, 55, 55);
                    border-radius: 4px;
                    gridline-color: rgb(55, 55, 55);
                }
                QTableWidget::item {
                    padding: 6px;
                }
                QTableWidget::item:selected {
                    background-color: rgb(70, 70, 70);
                    color: rgb(255, 255, 255);
                }
                QHeaderView::section {
                    background-color: rgb(50, 50, 50);
                    color: rgb(200, 200, 200);
                    padding: 8px;
                    border: none;
                    border-bottom: 1px solid rgb(65, 65, 65);
                    font-weight: bold;
                }
            """
        else:
            stylesheet = """
                QTableWidget {
                    background-color: rgb(255, 255, 255);
                    alternate-background-color: rgb(248, 248, 248);
                    color: rgb(32, 32, 32);
                    border: 1px solid rgb(220, 220, 220);
                    border-radius: 4px;
                    gridline-color: rgb(230, 230, 230);
                }
                QTableWidget::item {
                    padding: 6px;
                }
                QTableWidget::item:selected {
                    background-color: rgb(210, 210, 210);
                    color: rgb(0, 0, 0);
                }
                QHeaderView::section {
                    background-color: rgb(245, 245, 245);
                    color: rgb(32, 32, 32);
                    padding: 8px;
                    border: none;
                    border-bottom: 1px solid rgb(220, 220, 220);
                    font-weight: bold;
                }
            """
        self.table.setStyleSheet(stylesheet)

    def _on_theme_changed(self) -> None:
        self._apply_table_theme()

    # ------------------------------------------------------------------ 数据操作
    def _add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col in range(self.table.columnCount()):
            self.table.setItem(row, col, QTableWidgetItem(""))
        self.table.setCurrentCell(row, 0)

    def _remove_selected_rows(self):
        row = self.table.currentRow()
        if row < 0:
            InfoBar.warning(Localizer.get().notice, Localizer.localize("请选择需要删除的条目", "Select an entry to delete."), parent=self)
            return
        self.table.removeRow(row)

    def _deduplicate_rows(self):
        """按称呼词去重，优先保留有备注的条目"""
        entries = self._collect_table_data()
        if not entries:
            InfoBar.info(Localizer.get().notice, Localizer.localize("表格为空，暂无可去重的数据", "The table is empty."), parent=self)
            return

        seen: dict[str, int] = {}
        deduped: list[dict[str, str]] = []
        for item in entries:
            key = item.get("src", "").strip().lower()
            if not key:
                continue
            if key not in seen:
                deduped.append(item)
                seen[key] = len(deduped) - 1
            else:
                # 合并备注
                existing = deduped[seen[key]]
                incoming_comment = item.get("comment", "").strip()
                if incoming_comment and not existing.get("comment", "").strip():
                    existing["comment"] = incoming_comment

        removed = len(entries) - len(deduped)
        if removed > 0:
            self._set_table_data(deduped)
            InfoBar.success(Localizer.get().complete, Localizer.localize("已去除重复 {removed} 条，保留 {kept} 条", "Removed {removed} duplicate(s); kept {kept}.").format(removed=removed, kept=len(deduped)), parent=self)
        else:
            InfoBar.info(Localizer.get().notice, Localizer.localize("未发现重复条目", "No duplicate entries were found."), parent=self)

    def _clear_all(self):
        """清空表格"""
        self.table.setRowCount(0)
        InfoBar.success(Localizer.localize("已清空", "Cleared"), Localizer.localize("已清空所有称呼词", "All honorific terms were removed."), parent=self)

    def _restore_defaults(self):
        """恢复为内置默认称呼词"""
        items = [{"src": t, "comment": ""} for t in TextProcessor.DEFAULT_HONORIFIC_TITLES]
        self._set_table_data(items)
        InfoBar.success(Localizer.localize("已恢复", "Restored"), Localizer.localize("已恢复为内置默认 {count} 个称呼词", "Restored {count} built-in honorific terms.").format(count=len(TextProcessor.DEFAULT_HONORIFIC_TITLES)), parent=self)

    def _load_from_config(self):
        self.config = Config().load()
        titles = getattr(self.config, "honorific_placeholder_titles", []) or []
        items: list[dict[str, str]] = []
        for t in titles:
            if isinstance(t, dict):
                items.append({
                    "src": t.get("src", ""),
                    "comment": t.get("comment", ""),
                })
            elif isinstance(t, str) and t.strip():
                items.append({"src": t.strip(), "comment": ""})
        self._set_table_data(items)
        InfoBar.success(Localizer.get().complete, Localizer.localize("已从配置加载 {count} 个称呼词", "Loaded {count} honorific terms from settings.").format(count=len(items)), parent=self)

    def _save_to_config(self):
        entries = self._collect_table_data()
        self.config = Config().load()
        self.config.honorific_placeholder_titles = [e["src"] for e in entries]
        self.config.honorific_placeholder_bridge_enable = self.switch_btn.isChecked()
        self.config.save()
        InfoBar.success(Localizer.localize("保存成功", "Saved"), Localizer.localize("已写入 {count} 个称呼词到配置", "Saved {count} honorific terms to settings.").format(count=len(entries)), parent=self)

    # ------------------------------------------------------------------ 工具方法
    def _set_table_data(self, items: List[dict]):
        self.table.setRowCount(0)
        for item in items:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(item.get("src", "")))
            self.table.setItem(row, 1, QTableWidgetItem(item.get("comment", "")))

    def _collect_table_data(self) -> List[dict]:
        results: list[dict[str, str]] = []
        for row in range(self.table.rowCount()):
            src_item = self.table.item(row, 0)
            comment_item = self.table.item(row, 1)
            src = (src_item.text() if src_item else "").strip().lower()
            comment = (comment_item.text() if comment_item else "").strip()
            if not src:
                continue
            results.append({"src": src, "comment": comment})
        return results
