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
from module.Localizer.Localizer import Localizer
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
        layout.addWidget(TitleLabel(Localizer.localize("🔧 错误修复", "🔧 Error Repair")))

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

        layout.addWidget(StrongBodyLabel(Localizer.localize("📁 目标目录", "📁 Target Folder")))

        row = QHBoxLayout()
        row.addWidget(QLabel(Localizer.localize("game 目录:", "Game Folder:")))
        self.game_dir_edit = LineEdit()
        self.game_dir_edit.setPlaceholderText(Localizer.localize("选择包含 .rpy 文件的 game 目录", "Select the game folder containing .rpy files"))
        btn_browse = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
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

        layout.addWidget(StrongBodyLabel(Localizer.localize("🔨 修复选项", "🔨 Repair Options")))

        self.fix_indent_check = CheckBox(Localizer.localize("修复缩进问题（Tab 转空格）", "Fix Indentation (Convert Tabs to Spaces)"))
        self.fix_indent_check.setChecked(True)
        layout.addWidget(self.fix_indent_check)

        self.fix_indent_level_check = CheckBox(Localizer.localize("修复缩进层级问题（按父块回退）", "Fix Indentation Levels (Follow Parent Blocks)"))
        self.fix_indent_level_check.setChecked(False)
        layout.addWidget(self.fix_indent_level_check)

        self.fix_quotes_check = CheckBox(Localizer.localize("规范化外层中文引号", "Normalize Outer Chinese Quotation Marks"))
        self.fix_quotes_check.setChecked(False)
        layout.addWidget(self.fix_quotes_check)

        self.fix_dialogue_quotes_check = CheckBox(Localizer.localize("修复未转义引号（源码翻译）", "Fix Unescaped Quotes (Source Translation)"))
        self.fix_dialogue_quotes_check.setChecked(False)
        layout.addWidget(self.fix_dialogue_quotes_check)

        return card

    def _create_deep_lint_card(self) -> CardWidget:
        """创建深度 Lint 检查卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel(Localizer.localize("🔍 深度 Lint 检查", "🔍 Deep Lint Check")))

        desc = CaptionLabel(Localizer.localize("调用 Ren'Py 内置 lint 命令进行深度语法检查", "Run Ren'Py's built-in lint command for a deeper syntax check"), self)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 游戏可执行文件选择
        row = QHBoxLayout()
        row.addWidget(QLabel(Localizer.localize("游戏主程序:", "Game Executable:")))
        self.game_exe_edit = LineEdit()
        self.game_exe_edit.setPlaceholderText(Localizer.localize("选择游戏 .exe 文件（如 game.exe）", "Select the game .exe file, such as game.exe"))
        btn_browse_exe = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
        btn_browse_exe.clicked.connect(self._browse_game_exe)
        row.addWidget(self.game_exe_edit, 1)
        row.addWidget(btn_browse_exe)
        layout.addLayout(row)

        # 操作按钮
        btn_row = QHBoxLayout()
        
        self.lint_check_button = PushButton(Localizer.localize("执行 Lint 检查", "Run Lint Check"), icon=FluentIcon.SEARCH)
        self.lint_check_button.clicked.connect(self._run_lint_check)

        btn_row.addWidget(self.lint_check_button)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        return card

    def _create_action_card(self) -> CardWidget:
        """创建操作按钮卡片"""
        card = CardWidget(self)
        layout = QHBoxLayout(card)

        self.scan_button = PushButton(Localizer.localize("扫描错误", "Scan for Errors"), icon=FluentIcon.SEARCH)
        self.scan_button.clicked.connect(self._scan_errors)

        self.repair_button = PrimaryPushButton(Localizer.localize("自动修复", "Repair Automatically"), icon=FluentIcon.ACCEPT)
        self.repair_button.clicked.connect(self._repair_errors)

        self.export_report_button = PushButton(Localizer.localize("导出报告", "Export Report"), icon=FluentIcon.SAVE)
        self.export_report_button.setEnabled(False)
        self.export_report_button.clicked.connect(self._export_report)

        layout.addWidget(self.scan_button)
        layout.addWidget(self.repair_button)
        layout.addWidget(self.export_report_button)
        layout.addStretch(1)

        return card

    def _browse_game_dir(self):
        """浏览目录"""
        directory = QFileDialog.getExistingDirectory(self, Localizer.localize("选择 game 目录", "Select Game Folder"), "")
        if directory:
            self.game_dir_edit.setText(directory)

    def _scan_errors(self):
        """扫描错误"""
        game_dir = self.game_dir_edit.text().strip()
        if not game_dir:
            InfoBar.warning(Localizer.get().notice, Localizer.localize("请选择 game 目录", "Select a game folder."), parent=self)
            return
        if not Path(game_dir).is_dir():
            InfoBar.error(Localizer.get().error, Localizer.localize("目录不存在", "The folder does not exist."), parent=self)
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
            InfoBar.warning(Localizer.get().notice, Localizer.localize("请选择 game 目录", "Select a game folder."), parent=self)
            return
        if not Path(game_dir).is_dir():
            InfoBar.error(Localizer.get().error, Localizer.localize("目录不存在", "The folder does not exist."), parent=self)
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
            self, Localizer.localize("选择游戏主程序", "Select Game Executable"), "", Localizer.localize("可执行文件 (*.exe);;所有文件 (*.*)", "Executable Files (*.exe);;All Files (*.*)")
        )
        if file_path:
            self.game_exe_edit.setText(file_path)

    def _run_lint_check(self):
        """执行深度 Lint 检查"""
        game_exe = self.game_exe_edit.text().strip()
        if not game_exe:
            InfoBar.warning(Localizer.get().notice, Localizer.localize("请选择游戏主程序", "Select the game executable."), parent=self)
            return
        if not Path(game_exe).is_file():
            InfoBar.error(Localizer.get().error, Localizer.localize("游戏主程序不存在", "The game executable does not exist."), parent=self)
            return

        LogManager.get().info(f"开始深度 Lint 检查: {game_exe}")

        def task():
            repairer = ErrorRepairer()
            lint_output = repairer.exec_renpy_lint(game_exe)
            if lint_output is None:
                raise RuntimeError(Localizer.localize("Ren'Py Lint 执行失败，请查看日志", "Ren'Py Lint failed. Check the logs."))
            errors = repairer.parse_lint_errors(lint_output) if lint_output else []
            return {"output": lint_output, "errors": errors}

        self._start_background_operation("lint", task)

    def _start_background_operation(self, operation: str, task: Callable[[], object]) -> None:
        if self._running_operation is not None:
            InfoBar.warning(Localizer.get().notice, Localizer.localize("已有任务正在进行中", "Another task is already running."), parent=self)
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
                Localizer.localize("扫描完成", "Scan Complete"),
                Localizer.localize("发现 {count} 个问题（可导出报告）", "Found {count} issue(s). You can export the report.").format(count=total_issues),
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
                    Localizer.localize("修复完成", "Repair Complete"),
                    Localizer.localize("已修复 {fixed} 个文件，{failed} 个文件失败", "Repaired {fixed} file(s); {failed} file(s) failed.").format(fixed=fixed_files, failed=failed_files),
                    parent=self,
                )
            else:
                InfoBar.success(
                    Localizer.get().complete,
                    Localizer.localize("已修复 {files} 个文件、{items} 处", "Repaired {items} issue(s) in {files} file(s).").format(files=fixed_files, items=fixed_items),
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
                    Localizer.localize("检查完成", "Check Complete"),
                    Localizer.localize("发现 {count} 个问题（详情见日志和 lint_errors.txt）", "Found {count} issue(s). See the logs and lint_errors.txt for details.").format(count=len(errors)),
                    parent=self,
                )
            else:
                LogManager.get().info("Lint 检查完成，未发现错误")
                InfoBar.success(Localizer.localize("检查完成", "Check Complete"), Localizer.localize("未发现语法错误", "No syntax errors were found."), parent=self)
        else:
            self._set_running_operation(None)

    def _on_operation_failed(self, operation: str, message: str) -> None:
        labels = {
            "scan": Localizer.localize("扫描", "Scan"),
            "repair": Localizer.localize("修复", "Repair"),
            "lint": Localizer.localize("Lint 检查", "Lint check"),
        }
        label = labels.get(operation, Localizer.localize("任务", "Task"))
        self._set_running_operation(None)
        LogManager.get().error(f"{label}失败: {message}")
        InfoBar.error(
            Localizer.get().error,
            Localizer.localize(
                "{label}失败: {message}",
                "{label} failed. Check the logs for details.",
            ).format(label=label, message=message),
            parent=self,
        )

    def _export_report(self) -> None:
        if self._last_scan_report is None:
            InfoBar.warning(Localizer.get().notice, Localizer.localize("请先扫描错误", "Scan for errors first."), parent=self)
            return

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            Localizer.localize("导出错误报告", "Export Error Report"),
            "error_report.xlsx",
            Localizer.localize("Excel 文件 (*.xlsx)", "Excel Files (*.xlsx)"),
        )
        if not output_path:
            return
        if Path(output_path).suffix.lower() != ".xlsx":
            output_path += ".xlsx"

        ErrorRepairer().export_error_report(self._last_scan_report, output_path)
        if Path(output_path).is_file():
            InfoBar.success(Localizer.localize("导出完成", "Export Complete"), Localizer.localize("报告已保存到 {path}", "The report was saved to {path}").format(path=output_path), parent=self)
        else:
            InfoBar.error(Localizer.localize("导出失败", "Export Failed"), Localizer.localize("未能生成报告文件", "The report file could not be generated."), parent=self)

