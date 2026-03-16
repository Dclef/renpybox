"""
错误修复页面 - 扫描并修复 Ren'Py 脚本错误
"""
from pathlib import Path

from PyQt5.QtCore import Qt
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

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)
        
        self.window = parent
        self._init_ui()

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

        self.fix_quotes_check = CheckBox("修复引号问题")
        self.fix_quotes_check.setChecked(True)
        layout.addWidget(self.fix_quotes_check)

        self.fix_dialogue_quotes_check = CheckBox("修复未转义引号（源码翻译）")
        self.fix_dialogue_quotes_check.setChecked(True)
        layout.addWidget(self.fix_dialogue_quotes_check)

        self.fix_encoding_check = CheckBox("修复编码问题")
        self.fix_encoding_check.setChecked(False)
        layout.addWidget(self.fix_encoding_check)

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

        layout.addWidget(self.scan_button)
        layout.addWidget(self.repair_button)
        layout.addStretch(1)

        return card

    def _browse_game_dir(self):
        """浏览目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择 game 目录", "")
        if directory:
            self.game_dir_edit.setText(directory)

    def _scan_errors(self):
        """扫描错误"""
        try:
            game_dir = self.game_dir_edit.text().strip()
            if not game_dir:
                InfoBar.warning("提示", "请选择 game 目录", parent=self)
                return

            if not Path(game_dir).exists():
                InfoBar.error("错误", "目录不存在", parent=self)
                return

            LogManager.get().info(f"开始扫描错误: {game_dir}")
             
            repairer = ErrorRepairer()
            report = repairer.check_folder(
                game_dir,
                check_indent=self.fix_indent_check.isChecked(),
                check_indent_level=self.fix_indent_level_check.isChecked(),
                check_quotes=self.fix_quotes_check.isChecked(),
                check_dialogue_quotes=self.fix_dialogue_quotes_check.isChecked(),
                encoding="utf-8",
            )
            
            total_issues = sum(len(issues) for issues in report.values())
            LogManager.get().info(f"扫描完成，发现 {total_issues} 个问题")
            
            InfoBar.info("扫描完成", f"发现 {total_issues} 个问题（详情见日志）", parent=self)
            
        except Exception as e:
            LogManager.get().error(f"扫描失败: {e}")
            InfoBar.error("错误", f"扫描失败: {e}", parent=self)

    def _repair_errors(self):
        """修复错误"""
        try:
            game_dir = self.game_dir_edit.text().strip()
            if not game_dir:
                InfoBar.warning("提示", "请选择 game 目录", parent=self)
                return

            if not Path(game_dir).exists():
                InfoBar.error("错误", "目录不存在", parent=self)
                return

            LogManager.get().info(f"开始修复错误: {game_dir}")
            
            repairer = ErrorRepairer()
            fixed_count = 0
            
            for rpy_file in Path(game_dir).rglob("*.rpy"):
                success, count = repairer.auto_fix_file(
                    str(rpy_file),
                    fix_indent=self.fix_indent_check.isChecked(),
                    fix_indent_level=self.fix_indent_level_check.isChecked(),
                    fix_quotes=self.fix_quotes_check.isChecked(),
                    fix_dialogue_quotes=self.fix_dialogue_quotes_check.isChecked(),
                    encoding="utf-8"
                )
                if success and count > 0:
                    fixed_count += 1
            
            LogManager.get().info(f"修复完成，共修复 {fixed_count} 个文件")
            InfoBar.success("完成", f"已修复 {fixed_count} 个文件", parent=self)
            
        except Exception as e:
            LogManager.get().error(f"修复失败: {e}")
            InfoBar.error("错误", f"修复失败: {e}", parent=self)

    def _browse_game_exe(self):
        """浏览游戏可执行文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择游戏主程序", "", "可执行文件 (*.exe);;所有文件 (*.*)"
        )
        if file_path:
            self.game_exe_edit.setText(file_path)

    def _run_lint_check(self):
        """执行深度 Lint 检查"""
        try:
            game_exe = self.game_exe_edit.text().strip()
            if not game_exe:
                InfoBar.warning("提示", "请选择游戏主程序", parent=self)
                return

            if not Path(game_exe).exists():
                InfoBar.error("错误", "游戏主程序不存在", parent=self)
                return

            LogManager.get().info(f"开始深度 Lint 检查: {game_exe}")
            
            repairer = ErrorRepairer()
            lint_output = repairer.exec_renpy_lint(game_exe)
            
            if lint_output:
                errors = repairer.parse_lint_errors(lint_output)
                LogManager.get().info(f"Lint 检查发现 {len(errors)} 个问题")
                InfoBar.warning("检查完成", f"发现 {len(errors)} 个问题（详情见日志和 lint_errors.txt）", parent=self)
            else:
                LogManager.get().info("Lint 检查完成，未发现错误")
                InfoBar.success("检查完成", "未发现语法错误", parent=self)
                
        except Exception as e:
            LogManager.get().error(f"Lint 检查失败: {e}")
            InfoBar.error("错误", f"Lint 检查失败: {e}", parent=self)

