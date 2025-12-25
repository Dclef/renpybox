"""
代码格式化页面 - 格式化 Ren'Py 脚本文件
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
    TitleLabel,
    StrongBodyLabel,
)

from base.Base import Base
from base.LogManager import LogManager
from module.Tool.Formatter import Formatter
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area


class FormatterPage(Base, QWidget):
    """代码格式化页面"""

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
        layout.addWidget(TitleLabel("🎨 代码格式化"))

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

        # 选项卡片
        scroll_layout.addWidget(self._create_options_card())

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

    def _create_options_card(self) -> CardWidget:
        """创建选项卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("⚙️ 格式化选项"))

        self.preserve_comments_check = CheckBox("保留注释")
        self.preserve_comments_check.setChecked(True)
        layout.addWidget(self.preserve_comments_check)

        self.fix_indentation_check = CheckBox("修复缩进（Tab 转空格）")
        self.fix_indentation_check.setChecked(True)
        layout.addWidget(self.fix_indentation_check)

        self.remove_trailing_spaces_check = CheckBox("移除行尾空格")
        self.remove_trailing_spaces_check.setChecked(True)
        layout.addWidget(self.remove_trailing_spaces_check)

        return card

    def _create_action_card(self) -> CardWidget:
        """创建操作按钮卡片"""
        card = CardWidget(self)
        layout = QHBoxLayout(card)

        self.format_button = PrimaryPushButton("开始格式化", icon=FluentIcon.BRUSH)
        self.format_button.setFixedHeight(48)
        self.format_button.clicked.connect(self._format_files)

        layout.addStretch(1)
        layout.addWidget(self.format_button)
        layout.addStretch(1)

        return card

    def _browse_game_dir(self):
        """浏览目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择 game 目录", "")
        if directory:
            self.game_dir_edit.setText(directory)

    def _format_files(self):
        """格式化文件"""
        try:
            game_dir = self.game_dir_edit.text().strip()
            if not game_dir:
                InfoBar.warning("提示", "请选择 game 目录", parent=self)
                return

            if not Path(game_dir).exists():
                InfoBar.error("错误", "目录不存在", parent=self)
                return

            LogManager.get().info(f"开始格式化: {game_dir}")
            
            formatter = Formatter()
            count = formatter.format_folder(
                game_dir,
                preserve_comments=self.preserve_comments_check.isChecked(),
                fix_indent=self.fix_indentation_check.isChecked(),
                remove_trailing=self.remove_trailing_spaces_check.isChecked(),
                encoding="utf-8"
            )
            
            LogManager.get().info(f"格式化完成，共处理 {count} 个文件")
            InfoBar.success("完成", f"已格式化 {count} 个 .rpy 文件", parent=self)
            
        except Exception as e:
            LogManager.get().error(f"格式化失败: {e}")
            InfoBar.error("错误", f"格式化失败: {e}", parent=self)
