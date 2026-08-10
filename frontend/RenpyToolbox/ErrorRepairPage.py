"""
错误修复页面 - 扫描并修复 Ren'Py 脚本错误
"""
import threading
from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog
from qfluentwidgets import (
    CardWidget,
    PushButton,
    PrimaryPushButton,
    LineEdit,
    CheckBox,
    InfoBar,
    FluentIcon,
    SingleDirectionScrollArea,
    CaptionLabel,
    TitleLabel,
    StrongBodyLabel,
)

from base.Base import Base
from base.LogManager import LogManager
from module.Tool.ErrorRepairer import ErrorRepairer
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area


class ErrorRepairPage(Base, QWidget):
    """错误修复页面"""

    operation_finished = pyqtSignal(str, object)
    operation_failed = pyqtSignal(str, str)

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)
        
        self.window = parent
        self._running_operation: Optional[str] = None
        self._last_scan_report: Optional[dict] = None
        self._init_ui()
        self.operation_finished.connect(self._on_operation_finished)
        self.operation_failed.connect(self._on_operation_failed)

    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        layout.addWidget(TitleLabel("🔧 错误修复"))

        # 创建滚动区域
        scroll_area = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        scroll_area.setWidgetResizable(True)
        scroll_area.enableTransparentBackground()
        mark_toolbox_scroll_area(scroll_area)

        scroll_widget = QWidget()
        mark_toolbox_widget(scroll_widget, "toolboxScroll")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)

        # 配置卡片
        scroll_layout.addWidget(self._create_config_card())

        # 修复选项卡片
        scroll_layout.addWidget(self._create_repair_options_card())

        # 深度 Lint 检查卡片
        scroll_layout.addWidget(self._create_deep_lint_card())

        # 操作按钮卡片
        scroll_layout.addWidget(self._create_action_card())

        scroll_layout.addStretch(1)
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

    def _create_config_card(self) -> CardWidget:
        """创建配置卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("📁 目标目录"))

        row = QHBoxLayout()
        row.addWidget(QLabel("game 目录:"))
        self.game_dir_edit = LineEdit()
        self.game_dir_edit.setPlaceholderText("选择包含 .rpy 文件的 game 目录")
        btn_browse = PushButton("浏览", icon=FluentIcon.FOLDER)
        btn_browse.clicked.connect(self._browse_game_dir)
        row.addWidget(self.game_dir_edit, 1)
        row.addWidget(btn_browse)
        layout.addLayout(row)

        return card

    def _create_repair_options_card(self) -> CardWidget:
        """创建修复选项卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("🔨 修复选项"))

        self.fix_indent_check = CheckBox("修复缩进问题（Tab 转空格）")
        self.fix_indent_check.setChecked(True)
        layout.addWidget(self.fix_indent_check)

        self.fix_indent_level_check = CheckBox("修复缩进层级问题（按父块回退）")
        self.fix_indent_level_check.setChecked(False)
        layout.addWidget(self.fix_indent_level_check)

        self.fix_quotes_check = CheckBox("规范化外层中文引号")
        self.fix_quotes_check.setChecked(False)
        layout.addWidget(self.fix_quotes_check)

        self.fix_dialogue_quotes_check = CheckBox("修复未转义引号（源码翻译）")
        self.fix_dialogue_quotes_check.setChecked(False)
        layout.addWidget(self.fix_dialogue_quotes_check)

        return card

    def _create_deep_lint_card(self) -> CardWidget:
        """创建深度 Lint 检查卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("🔍 深度 Lint 检查"))

        desc = CaptionLabel("调用 Ren'Py 内置 lint 命令进行深度语法检查", self)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 游戏可执行文件选择
        row = QHBoxLayout()
        row.addWidget(QLabel("游戏主程序:"))
        self.game_exe_edit = LineEdit()
        self.game_exe_edit.setPlaceholderText("选择游戏 .exe 文件（如 game.exe）")
        btn_browse_exe = PushButton("浏览", icon=FluentIcon.FOLDER)
        btn_browse_exe.clicked.connect(self._browse_game_exe)
        row.addWidget(self.game_exe_edit, 1)
        row.addWidget(btn_browse_exe)
        layout.addLayout(row)

        # 操作按钮
        btn_row = QHBoxLayout()
        
        self.lint_check_button = PushButton("执行 Lint 检查", icon=FluentIcon.SEARCH)
        self.lint_check_button.clicked.connect(self._run_lint_check)

        btn_row.addWidget(self.lint_check_button)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        return card

    def _create_action_card(self) -> CardWidget:
        """创建操作按钮卡片"""
        card = CardWidget(self)
        layout = QHBoxLayout(card)

        self.scan_button = PushButton("扫描错误", icon=FluentIcon.SEARCH)
        self.scan_button.clicked.connect(self._scan_errors)

        self.repair_button = PrimaryPushButton("自动修复", icon=FluentIcon.ACCEPT)
        self.repair_button.clicked.connect(self._repair_errors)

        self.export_report_button = PushButton("导出报告", icon=FluentIcon.SAVE)
        self.export_report_button.setEnabled(False)
        self.export_report_button.clicked.connect(self._export_report)

        layout.addWidget(self.scan_button)
        layout.addWidget(self.repair_button)
        layout.addWidget(self.export_report_button)
        layout.addStretch(1)

        return card

    def _browse_game_dir(self):
        """浏览目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择 game 目录", "")
        if directory:
            self.game_dir_edit.setText(directory)

    def _scan_errors(self):
        """扫描错误"""
        game_dir = self.game_dir_edit.text().strip()
        if not game_dir:
            InfoBar.warning("提示", "请选择 game 目录", parent=self)
            return
        if not Path(game_dir).is_dir():
            InfoBar.error("错误", "目录不存在", parent=self)
            return

        check_indent = self.fix_indent_check.isChecked()
        check_indent_level = self.fix_indent_level_check.isChecked()
        LogManager.get().info(f"开始扫描错误: {game_dir}")

        def task():
            repairer = ErrorRepairer()
            return repairer.check_folder(
                game_dir,
                check_indent=check_indent,
                check_indent_level=check_indent_level,
                check_quotes=True,
                check_dialogue_quotes=True,
                encoding="utf-8",
            )

        self._start_background_operation("scan", task)

    def _repair_errors(self):
        """修复错误"""
        game_dir = self.game_dir_edit.text().strip()
        if not game_dir:
            InfoBar.warning("提示", "请选择 game 目录", parent=self)
            return
        if not Path(game_dir).is_dir():
            InfoBar.error("错误", "目录不存在", parent=self)
            return

        fix_indent = self.fix_indent_check.isChecked()
        fix_indent_level = self.fix_indent_level_check.isChecked()
        fix_quotes = self.fix_quotes_check.isChecked()
        fix_dialogue_quotes = self.fix_dialogue_quotes_check.isChecked()
        LogManager.get().info(f"开始修复错误: {game_dir}")

        def task():
            repairer = ErrorRepairer()
            fixed_files = 0
            fixed_items = 0
            failed_files = 0
            for rpy_file in Path(game_dir).rglob("*.rpy"):
                success, count = repairer.auto_fix_file(
                    str(rpy_file),
                    fix_indent=fix_indent,
                    fix_indent_level=fix_indent_level,
                    fix_quotes=fix_quotes,
                    fix_dialogue_quotes=fix_dialogue_quotes,
                    encoding="utf-8"
                )
                if success and count > 0:
                    fixed_files += 1
                    fixed_items += count
                elif not success:
                    failed_files += 1
            return {
                "fixed_files": fixed_files,
                "fixed_items": fixed_items,
                "failed_files": failed_files,
            }

        self._start_background_operation("repair", task)

    def _browse_game_exe(self):
        """浏览游戏可执行文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择游戏主程序", "", "可执行文件 (*.exe);;所有文件 (*.*)"
        )
        if file_path:
            self.game_exe_edit.setText(file_path)

    def _run_lint_check(self):
        """执行深度 Lint 检查"""
        game_exe = self.game_exe_edit.text().strip()
        if not game_exe:
            InfoBar.warning("提示", "请选择游戏主程序", parent=self)
            return
        if not Path(game_exe).is_file():
            InfoBar.error("错误", "游戏主程序不存在", parent=self)
            return

        LogManager.get().info(f"开始深度 Lint 检查: {game_exe}")

        def task():
            repairer = ErrorRepairer()
            lint_output = repairer.exec_renpy_lint(game_exe)
            if lint_output is None:
                raise RuntimeError("Ren'Py Lint 执行失败，请查看日志")
            errors = repairer.parse_lint_errors(lint_output) if lint_output else []
            return {"output": lint_output, "errors": errors}

        self._start_background_operation("lint", task)

    def _start_background_operation(self, operation: str, task: Callable[[], object]) -> None:
        if self._running_operation is not None:
            InfoBar.warning("提示", "已有任务正在进行中", parent=self)
            return

        self._set_running_operation(operation)

        def run() -> None:
            try:
                self.operation_finished.emit(operation, task())
            except Exception as exc:
                LogManager.get().error(f"错误修复任务失败 ({operation}): {exc}")
                self.operation_failed.emit(operation, str(exc))

        try:
            threading.Thread(target=run, daemon=True).start()
        except Exception as exc:
            self._on_operation_failed(operation, str(exc))

    def _set_running_operation(self, operation: Optional[str]) -> None:
        self._running_operation = operation
        idle = operation is None
        self.scan_button.setEnabled(idle)
        self.repair_button.setEnabled(idle)
        self.lint_check_button.setEnabled(idle)
        self.export_report_button.setEnabled(
            idle and self._last_scan_report is not None
        )

    def _on_operation_finished(self, operation: str, payload: object) -> None:
        if operation == "scan":
            report = payload if isinstance(payload, dict) else {}
            self._last_scan_report = report
            total_issues = sum(len(issues) for issues in report.values())
            LogManager.get().info(f"扫描完成，发现 {total_issues} 个问题")
            self._set_running_operation(None)
            InfoBar.info(
                "扫描完成",
                f"发现 {total_issues} 个问题（可导出报告）",
                parent=self,
            )
        elif operation == "repair":
            result = payload if isinstance(payload, dict) else {}
            fixed_files = int(result.get("fixed_files", 0))
            fixed_items = int(result.get("fixed_items", 0))
            failed_files = int(result.get("failed_files", 0))
            LogManager.get().info(
                f"修复完成，共修复 {fixed_files} 个文件、{fixed_items} 处"
            )
            self._set_running_operation(None)
            if failed_files:
                InfoBar.warning(
                    "修复完成",
                    f"已修复 {fixed_files} 个文件，{failed_files} 个文件失败",
                    parent=self,
                )
            else:
                InfoBar.success(
                    "完成",
                    f"已修复 {fixed_files} 个文件、{fixed_items} 处",
                    parent=self,
                )
        elif operation == "lint":
            result = payload if isinstance(payload, dict) else {}
            lint_output = result.get("output")
            errors = result.get("errors") or []
            self._set_running_operation(None)
            if lint_output:
                LogManager.get().info(f"Lint 检查发现 {len(errors)} 个问题")
                InfoBar.warning(
                    "检查完成",
                    f"发现 {len(errors)} 个问题（详情见日志和 lint_errors.txt）",
                    parent=self,
                )
            else:
                LogManager.get().info("Lint 检查完成，未发现错误")
                InfoBar.success("检查完成", "未发现语法错误", parent=self)
        else:
            self._set_running_operation(None)

    def _on_operation_failed(self, operation: str, message: str) -> None:
        labels = {"scan": "扫描", "repair": "修复", "lint": "Lint 检查"}
        label = labels.get(operation, "任务")
        self._set_running_operation(None)
        LogManager.get().error(f"{label}失败: {message}")
        InfoBar.error("错误", f"{label}失败: {message}", parent=self)

    def _export_report(self) -> None:
        if self._last_scan_report is None:
            InfoBar.warning("提示", "请先扫描错误", parent=self)
            return

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出错误报告",
            "error_report.xlsx",
            "Excel 文件 (*.xlsx)",
        )
        if not output_path:
            return
        if Path(output_path).suffix.lower() != ".xlsx":
            output_path += ".xlsx"

        ErrorRepairer().export_error_report(self._last_scan_report, output_path)
        if Path(output_path).is_file():
            InfoBar.success("导出完成", f"报告已保存到 {output_path}", parent=self)
        else:
            InfoBar.error("导出失败", "未能生成报告文件", parent=self)

