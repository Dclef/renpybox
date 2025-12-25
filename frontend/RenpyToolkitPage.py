"""
Ren'Py 工具箱页面
提供字体替换、格式化、错误检查等工具
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from qfluentwidgets import (
    FluentIcon,
    PushButton,
    PrimaryPushButton,
    LineEdit,
    TextEdit,
    SwitchButton,
    SpinBox,
    CardWidget,
    SubtitleLabel,
    BodyLabel,
    MessageBox,
    InfoBar,
    InfoBarPosition
)

from base.LogManager import LogManager
from module.Config import Config
from module.Tool.FontReplacer import FontReplacer
from module.Tool.Formatter import Formatter
from module.Tool.ErrorRepairer import ErrorRepairer


class RenpyToolkitPage(QWidget):
    """Ren'Py 工具箱页面"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.config = Config()
        self.logger = LogManager.get()
        self.font_replacer = FontReplacer()
        self.formatter = Formatter()
        self.error_repairer = ErrorRepairer()
        
        self._init_ui()
        self._load_config()
        self._connect_signals()

    def _init_ui(self):
        """初始化 UI"""
        self.setObjectName("RenpyToolkitPage")
        
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # 标题
        title_label = SubtitleLabel("Ren'Py 工具箱", self)
        main_layout.addWidget(title_label)

        # 字体替换卡片
        self.font_card = self._create_font_replacement_card()
        main_layout.addWidget(self.font_card)

        # 代码格式化卡片
        self.format_card = self._create_format_card()
        main_layout.addWidget(self.format_card)

        # 错误检查卡片
        self.error_card = self._create_error_check_card()
        main_layout.addWidget(self.error_card)

        # 日志显示
        self.log_text = TextEdit(self)
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("工具执行日志将显示在这里...")
        self.log_text.setMaximumHeight(150)
        main_layout.addWidget(self.log_text)

        main_layout.addStretch(1)

    def _create_font_replacement_card(self) -> CardWidget:
        """创建字体替换卡片"""
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(10)

        # 标题
        title = BodyLabel("🔤 字体替换工具", card)
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        card_layout.addWidget(title)

        # 目标文件夹
        folder_layout = QHBoxLayout()
        self.font_folder_edit = LineEdit(card)
        self.font_folder_edit.setPlaceholderText("选择要处理的文件夹...")
        self.font_folder_btn = PushButton(FluentIcon.FOLDER, "浏览", card)
        folder_layout.addWidget(BodyLabel("目标文件夹:", card))
        folder_layout.addWidget(self.font_folder_edit, 1)
        folder_layout.addWidget(self.font_folder_btn)
        card_layout.addLayout(folder_layout)

        # 原字体
        original_font_layout = QHBoxLayout()
        self.original_font_edit = LineEdit(card)
        self.original_font_edit.setPlaceholderText("例如: SourceHanSans.ttf")
        self.scan_fonts_btn = PushButton(FluentIcon.SEARCH, "扫描", card)
        original_font_layout.addWidget(BodyLabel("原字体名:", card))
        original_font_layout.addWidget(self.original_font_edit, 1)
        original_font_layout.addWidget(self.scan_fonts_btn)
        card_layout.addLayout(original_font_layout)

        # 目标字体
        target_font_layout = QHBoxLayout()
        self.target_font_edit = LineEdit(card)
        self.target_font_edit.setPlaceholderText("例如: NotoSansCJK.ttf")
        target_font_layout.addWidget(BodyLabel("目标字体名:", card))
        target_font_layout.addWidget(self.target_font_edit, 1)
        card_layout.addLayout(target_font_layout)

        # 按钮
        btn_layout = QHBoxLayout()
        self.replace_font_btn = PrimaryPushButton(FluentIcon.EDIT, "执行替换", card)
        btn_layout.addWidget(self.replace_font_btn)
        btn_layout.addStretch(1)
        card_layout.addLayout(btn_layout)

        return card

    def _create_format_card(self) -> CardWidget:
        """创建格式化卡片"""
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(10)

        # 标题
        title = BodyLabel("📐 代码格式化工具", card)
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        card_layout.addWidget(title)

        # 目标文件夹
        folder_layout = QHBoxLayout()
        self.format_folder_edit = LineEdit(card)
        self.format_folder_edit.setPlaceholderText("选择要格式化的文件夹...")
        self.format_folder_btn = PushButton(FluentIcon.FOLDER, "浏览", card)
        folder_layout.addWidget(BodyLabel("目标文件夹:", card))
        folder_layout.addWidget(self.format_folder_edit, 1)
        folder_layout.addWidget(self.format_folder_btn)
        card_layout.addLayout(folder_layout)

        # 缩进设置
        options_layout = QHBoxLayout()
        self.indent_spinbox = SpinBox(card)
        self.indent_spinbox.setRange(2, 8)
        self.indent_spinbox.setValue(4)
        options_layout.addWidget(BodyLabel("缩进空格数:", card))
        options_layout.addWidget(self.indent_spinbox)
        options_layout.addSpacing(20)

        # 行宽设置
        self.line_width_spinbox = SpinBox(card)
        self.line_width_spinbox.setRange(60, 120)
        self.line_width_spinbox.setValue(80)
        options_layout.addWidget(BodyLabel("最大行宽:", card))
        options_layout.addWidget(self.line_width_spinbox)
        options_layout.addSpacing(20)

        # 保留注释
        self.preserve_comments_switch = SwitchButton(card)
        self.preserve_comments_switch.setChecked(True)
        options_layout.addWidget(BodyLabel("保留注释:", card))
        options_layout.addWidget(self.preserve_comments_switch)
        options_layout.addStretch(1)
        card_layout.addLayout(options_layout)

        # 按钮
        btn_layout = QHBoxLayout()
        self.format_btn = PrimaryPushButton(FluentIcon.LAYOUT, "开始格式化", card)
        self.remove_whitespace_btn = PushButton(FluentIcon.DELETE, "移除行尾空格", card)
        btn_layout.addWidget(self.format_btn)
        btn_layout.addWidget(self.remove_whitespace_btn)
        btn_layout.addStretch(1)
        card_layout.addLayout(btn_layout)

        return card

    def _create_error_check_card(self) -> CardWidget:
        """创建错误检查卡片"""
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(10)

        # 标题
        title = BodyLabel("🔍 错误检查与修复", card)
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        card_layout.addWidget(title)

        # 目标文件夹
        folder_layout = QHBoxLayout()
        self.error_folder_edit = LineEdit(card)
        self.error_folder_edit.setPlaceholderText("选择要检查的文件夹...")
        self.error_folder_btn = PushButton(FluentIcon.FOLDER, "浏览", card)
        folder_layout.addWidget(BodyLabel("目标文件夹:", card))
        folder_layout.addWidget(self.error_folder_edit, 1)
        folder_layout.addWidget(self.error_folder_btn)
        card_layout.addLayout(folder_layout)

        # 检查选项
        options_layout = QHBoxLayout()
        self.check_syntax_switch = SwitchButton(card)
        self.check_syntax_switch.setChecked(True)
        self.check_indent_switch = SwitchButton(card)
        self.check_indent_switch.setChecked(True)
        self.check_quotes_switch = SwitchButton(card)
        self.check_quotes_switch.setChecked(True)

        options_layout.addWidget(BodyLabel("语法检查", card))
        options_layout.addWidget(self.check_syntax_switch)
        options_layout.addSpacing(20)
        options_layout.addWidget(BodyLabel("缩进检查", card))
        options_layout.addWidget(self.check_indent_switch)
        options_layout.addSpacing(20)
        options_layout.addWidget(BodyLabel("引号检查", card))
        options_layout.addWidget(self.check_quotes_switch)
        options_layout.addStretch(1)
        card_layout.addLayout(options_layout)

        # 按钮
        btn_layout = QHBoxLayout()
        self.check_errors_btn = PrimaryPushButton(FluentIcon.SEARCH, "开始检查", card)
        self.auto_fix_btn = PushButton(FluentIcon.ACCEPT, "自动修复", card)
        self.export_report_btn = PushButton(FluentIcon.DOCUMENT, "导出报告", card)
        self.export_report_btn.setEnabled(False)
        btn_layout.addWidget(self.check_errors_btn)
        btn_layout.addWidget(self.auto_fix_btn)
        btn_layout.addWidget(self.export_report_btn)
        btn_layout.addStretch(1)
        card_layout.addLayout(btn_layout)

        return card

    def _connect_signals(self):
        """连接信号槽"""
        # 字体替换
        self.font_folder_btn.clicked.connect(lambda: self._browse_folder(self.font_folder_edit))
        self.scan_fonts_btn.clicked.connect(self._on_scan_fonts)
        self.replace_font_btn.clicked.connect(self._on_replace_font)

        # 格式化
        self.format_folder_btn.clicked.connect(lambda: self._browse_folder(self.format_folder_edit))
        self.format_btn.clicked.connect(self._on_format_code)
        self.remove_whitespace_btn.clicked.connect(self._on_remove_whitespace)

        # 错误检查
        self.error_folder_btn.clicked.connect(lambda: self._browse_folder(self.error_folder_edit))
        self.check_errors_btn.clicked.connect(self._on_check_errors)
        self.auto_fix_btn.clicked.connect(self._on_auto_fix)
        self.export_report_btn.clicked.connect(self._on_export_report)

    def _load_config(self):
        """加载配置"""
        try:
            self.config.load()
            
            # 字体设置
            self.original_font_edit.setText(self.config.renpy_font_original)
            self.target_font_edit.setText(self.config.renpy_font_target)
            
            # 格式化设置
            self.indent_spinbox.setValue(self.config.renpy_format_indent)
            self.line_width_spinbox.setValue(self.config.renpy_format_line_width)
            self.preserve_comments_switch.setChecked(self.config.renpy_format_preserve_comments)
            
            # 错误检查设置
            self.check_syntax_switch.setChecked(self.config.renpy_error_check_syntax)
            self.check_indent_switch.setChecked(self.config.renpy_error_check_indent)
            self.check_quotes_switch.setChecked(self.config.renpy_error_check_quotes)
            
        except Exception as e:
            self.logger.error(f"加载配置失败: {e}")

    def _browse_folder(self, line_edit: LineEdit):
        """浏览文件夹"""
        from PyQt5.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            line_edit.setText(folder)
            self._log(f"选择文件夹: {folder}")

    def _on_scan_fonts(self):
        """扫描字体"""
        folder = self.font_folder_edit.text()
        if not folder:
            self._show_error("错误", "请先选择文件夹！")
            return

        try:
            fonts = self.font_replacer.scan_fonts(folder)
            if fonts:
                self._log(f"找到 {len(fonts)} 个字体:")
                for font in fonts:
                    self._log(f"  - {font}")
                self._show_success("扫描完成", f"找到 {len(fonts)} 个字体")
            else:
                self._log("未找到任何字体引用")
                self._show_info("提示", "未找到任何字体引用")
        except Exception as e:
            self._log(f"❌ 扫描失败: {e}")
            self._show_error("扫描失败", str(e))

    def _on_replace_font(self):
        """替换字体"""
        folder = self.font_folder_edit.text()
        original_font = self.original_font_edit.text()
        target_font = self.target_font_edit.text()

        if not all([folder, original_font, target_font]):
            self._show_error("错误", "请填写所有字段！")
            return

        try:
            success_count, total_replacements = self.font_replacer.replace_in_folder(
                folder, original_font, target_font
            )
            self._log(f"✅ 替换完成: {success_count} 个文件, {total_replacements} 处替换")
            self._show_success("替换完成", f"成功替换 {total_replacements} 处")
            
            # 保存配置
            self.config.renpy_font_original = original_font
            self.config.renpy_font_target = target_font
            self.config.save()
            
        except Exception as e:
            self._log(f"❌ 替换失败: {e}")
            self._show_error("替换失败", str(e))

    def _on_format_code(self):
        """格式化代码"""
        folder = self.format_folder_edit.text()
        if not folder:
            self._show_error("错误", "请先选择文件夹！")
            return

        try:
            formatter = Formatter(
                indent=self.indent_spinbox.value(),
                line_width=self.line_width_spinbox.value()
            )
            success_count = formatter.format_folder(
                folder,
                preserve_comments=self.preserve_comments_switch.isChecked()
            )
            self._log(f"✅ 格式化完成: {success_count} 个文件")
            self._show_success("格式化完成", f"成功格式化 {success_count} 个文件")
            
            # 保存配置
            self.config.renpy_format_indent = self.indent_spinbox.value()
            self.config.renpy_format_line_width = self.line_width_spinbox.value()
            self.config.renpy_format_preserve_comments = self.preserve_comments_switch.isChecked()
            self.config.save()
            
        except Exception as e:
            self._log(f"❌ 格式化失败: {e}")
            self._show_error("格式化失败", str(e))

    def _on_remove_whitespace(self):
        """移除行尾空格"""
        folder = self.format_folder_edit.text()
        if not folder:
            self._show_error("错误", "请先选择文件夹！")
            return

        try:
            formatter = Formatter()
            processed = formatter.remove_trailing_whitespace(folder)
            self._log(f"✅ 处理完成: {processed} 个文件")
            self._show_success("处理完成", f"已处理 {processed} 个文件")
        except Exception as e:
            self._log(f"❌ 处理失败: {e}")
            self._show_error("处理失败", str(e))

    def _on_check_errors(self):
        """检查错误"""
        folder = self.error_folder_edit.text()
        if not folder:
            self._show_error("错误", "请先选择文件夹！")
            return

        try:
            errors = self.error_repairer.check_folder(
                folder,
                check_syntax=self.check_syntax_switch.isChecked(),
                check_indent=self.check_indent_switch.isChecked(),
                check_quotes=self.check_quotes_switch.isChecked()
            )

            total_errors = sum(len(errs) for errs in errors.values())
            
            if total_errors > 0:
                self._log(f"⚠️ 发现 {total_errors} 个错误:")
                for file_path, file_errors in errors.items():
                    self._log(f"\n文件: {file_path}")
                    for error in file_errors[:5]:  # 只显示前5个
                        self._log(f"  行 {error['line']}: {error['message']}")
                    if len(file_errors) > 5:
                        self._log(f"  ... 还有 {len(file_errors) - 5} 个错误")
                
                self.export_report_btn.setEnabled(True)
                self._show_info("检查完成", f"发现 {total_errors} 个错误")
            else:
                self._log("✅ 未发现错误")
                self._show_success("检查完成", "未发现错误")

            # 保存错误信息供导出使用
            self._last_errors = errors
            
        except Exception as e:
            self._log(f"❌ 检查失败: {e}")
            self._show_error("检查失败", str(e))

    def _on_auto_fix(self):
        """自动修复"""
        folder = self.error_folder_edit.text()
        if not folder:
            self._show_error("错误", "请先选择文件夹！")
            return

        reply = MessageBox(
            "确认修复",
            "自动修复将直接修改文件，是否继续？",
            self
        ).exec()
        
        if not reply:
            return

        try:
            from pathlib import Path
            rpy_files = list(Path(folder).rglob("*.rpy"))
            
            total_fixes = 0
            for file_path in rpy_files:
                success, fix_count = self.error_repairer.auto_fix_file(
                    str(file_path),
                    fix_indent=True,
                    fix_quotes=False
                )
                if success:
                    total_fixes += fix_count

            self._log(f"✅ 修复完成: 共 {total_fixes} 处修复")
            self._show_success("修复完成", f"共修复 {total_fixes} 处问题")
            
        except Exception as e:
            self._log(f"❌ 修复失败: {e}")
            self._show_error("修复失败", str(e))

    def _on_export_report(self):
        """导出错误报告"""
        if not hasattr(self, '_last_errors'):
            self._show_error("错误", "请先执行错误检查！")
            return

        from PyQt5.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存错误报告",
            "error_report.xlsx",
            "Excel 文件 (*.xlsx)"
        )
        
        if file_path:
            try:
                self.error_repairer.export_error_report(self._last_errors, file_path)
                self._log(f"✅ 报告已导出: {file_path}")
                self._show_success("导出成功", f"报告已保存到: {file_path}")
            except Exception as e:
                self._log(f"❌ 导出失败: {e}")
                self._show_error("导出失败", str(e))

    def _log(self, message: str):
        """添加日志"""
        self.log_text.append(message)
        self.logger.info(message)

    def _show_success(self, title: str, content: str):
        """显示成功提示"""
        InfoBar.success(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self
        )

    def _show_error(self, title: str, content: str):
        """显示错误提示"""
        InfoBar.error(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self
        )

    def _show_info(self, title: str, content: str):
        """显示信息提示"""
        InfoBar.info(
            title=title,
            content=content,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self
        )
