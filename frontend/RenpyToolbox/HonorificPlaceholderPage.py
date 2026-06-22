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

    HEADERS = ("称呼词", "备注")

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
        title = TitleLabel("称呼变量智能桥接")
        layout.addWidget(title)

        # 描述
        desc = CaptionLabel(
            "管理用于识别「称呼 + 变量」结构的称呼词列表。"
            + "翻译时将 Mr.[xx] 等模式临时替换为结构化占位符，译后自动还原并修正中文语序（如 [xx]先生）。"
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

        label = StrongBodyLabel("启用称呼变量智能桥接")
        h_layout.addWidget(label)

        desc_label = CaptionLabel(
            "开启后，翻译流程会自动检测并处理 称呼+变量 结构"
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

        save_btn = PrimaryPushButton("保存到配置", icon=FluentIcon.SAVE)
        save_btn.clicked.connect(self._save_to_config)
        row1.addWidget(save_btn)

        load_btn = PushButton("从配置加载", icon=FluentIcon.HISTORY)
        load_btn.clicked.connect(self._load_from_config)
        row1.addWidget(load_btn)

        row1.addStretch(1)
        v_layout.addLayout(row1)

        # 第二排：新增 / 删除选中 / 去重 / 清空 / 恢复默认
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        add_btn = PushButton("新增条目", icon=FluentIcon.ADD)
        add_btn.clicked.connect(self._add_row)
        row2.addWidget(add_btn)

        delete_btn = PushButton("删除选中", icon=FluentIcon.DELETE)
        delete_btn.clicked.connect(self._remove_selected_rows)
        row2.addWidget(delete_btn)

        dedup_btn = PushButton("去重", icon=FluentIcon.FILTER)
        dedup_btn.setToolTip("按称呼词去重，合并备注")
        dedup_btn.clicked.connect(self._deduplicate_rows)
        row2.addWidget(dedup_btn)

        clear_btn = PushButton("清空全部", icon=FluentIcon.CLOSE)
        clear_btn.setToolTip("清空所有称呼词")
        clear_btn.clicked.connect(self._clear_all)
        row2.addWidget(clear_btn)

        restore_btn = PushButton("恢复默认", icon=FluentIcon.SYNC)
        restore_btn.setToolTip("恢复为内置默认称呼词列表")
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

        table_label = StrongBodyLabel("称呼词列表（可直接编辑单元格）")
        v_layout.addWidget(table_label)

        self.table = QTableWidget(0, len(self.HEADERS), self)
        self.table.setHorizontalHeaderLabels(self.HEADERS)
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
        for col in range(len(self.HEADERS)):
            self.table.setItem(row, col, QTableWidgetItem(""))
        self.table.setCurrentCell(row, 0)

    def _remove_selected_rows(self):
        row = self.table.currentRow()
        if row < 0:
            InfoBar.warning("提示", "请选择需要删除的条目", parent=self)
            return
        self.table.removeRow(row)

    def _deduplicate_rows(self):
        """按称呼词去重，优先保留有备注的条目"""
        entries = self._collect_table_data()
        if not entries:
            InfoBar.info("提示", "表格为空，暂无可去重的数据", parent=self)
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
            InfoBar.success("完成", f"已去除重复 {removed} 条，保留 {len(deduped)} 条", parent=self)
        else:
            InfoBar.info("提示", "未发现重复条目", parent=self)

    def _clear_all(self):
        """清空表格"""
        self.table.setRowCount(0)
        InfoBar.success("已清空", "已清空所有称呼词", parent=self)

    def _restore_defaults(self):
        """恢复为内置默认称呼词"""
        items = [{"src": t, "comment": ""} for t in TextProcessor.DEFAULT_HONORIFIC_TITLES]
        self._set_table_data(items)
        InfoBar.success("已恢复", f"已恢复为内置默认 {len(TextProcessor.DEFAULT_HONORIFIC_TITLES)} 个称呼词", parent=self)

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
        InfoBar.success("完成", f"已从配置加载 {len(items)} 个称呼词", parent=self)

    def _save_to_config(self):
        entries = self._collect_table_data()
        self.config = Config().load()
        self.config.honorific_placeholder_titles = [e["src"] for e in entries]
        self.config.honorific_placeholder_bridge_enable = self.switch_btn.isChecked()
        self.config.save()
        InfoBar.success("保存成功", f"已写入 {len(entries)} 个称呼词到配置", parent=self)

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
