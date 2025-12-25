"""
添加语言入口页面 - 向游戏添加语言切换功能
"""
from pathlib import Path
import shutil

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog
from qfluentwidgets import (
    CardWidget,
    PushButton,
    PrimaryPushButton,
    LineEdit,
    InfoBar,
    FluentIcon,
    SingleDirectionScrollArea,
    CaptionLabel,
    TitleLabel,
    StrongBodyLabel,
)

from base.Base import Base
from base.LogManager import LogManager
from base.PathHelper import get_resource_path
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area


class AddLanguageEntrancePage(Base, QWidget):
    """添加语言入口页面"""

    def __init__(self, object_name: str, parent=None, game_dir: str = None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)
        
        self.window = parent
        self.initial_game_dir = game_dir  # 传入的初始 game 目录
        self._init_ui()

    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        layout.addWidget(TitleLabel("🌐 添加语言入口"))

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

        # 说明卡片
        scroll_layout.addWidget(self._create_info_card())

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

        layout.addWidget(StrongBodyLabel("📁 项目配置"))

        # game 目录
        row = QHBoxLayout()
        row.addWidget(QLabel("game 目录:"))
        self.game_dir_edit = LineEdit()
        self.game_dir_edit.setPlaceholderText("选择项目的 game 目录")
        btn_browse = PushButton("浏览", icon=FluentIcon.FOLDER)
        btn_browse.clicked.connect(self._browse_game_dir)
        row.addWidget(self.game_dir_edit, 1)
        row.addWidget(btn_browse)
        layout.addLayout(row)
        
        # 如果有传入的初始目录，自动填充
        if self.initial_game_dir:
            self.game_dir_edit.setText(self.initial_game_dir)

        return card

    def _create_info_card(self) -> CardWidget:
        """创建说明卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("ℹ️ 功能说明"))

        info_text = CaptionLabel(
            "此功能将在游戏中添加语言切换菜单，允许玩家在游戏设置中切换语言。\n\n"
            "操作步骤：\n"
            "1. 选择项目的 game 目录\n"
            "2. 点击'添加语言入口'按钮\n"
            "3. 脚本将自动注入语言切换代码到游戏中\n\n"
            "注意：此操作会修改游戏脚本，建议先备份",
            self
        )
        info_text.setWordWrap(True)
        layout.addWidget(info_text)

        return card

    def _create_action_card(self) -> CardWidget:
        """创建操作按钮卡片"""
        card = CardWidget(self)
        layout = QHBoxLayout(card)

        self.add_button = PrimaryPushButton("添加语言入口", icon=FluentIcon.GLOBE)
        self.add_button.setFixedHeight(48)
        self.add_button.clicked.connect(self._add_language_entrance)

        layout.addStretch(1)
        layout.addWidget(self.add_button)
        layout.addStretch(1)

        return card

    def _browse_game_dir(self):
        """浏览目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择 game 目录", "")
        if directory:
            self.game_dir_edit.setText(directory)

    def _add_language_entrance(self):
        """添加语言入口"""
        try:
            game_dir = self.game_dir_edit.text().strip()
            if not game_dir:
                InfoBar.warning("提示", "请选择 game 目录", parent=self)
                return

            if not Path(game_dir).exists():
                InfoBar.error("错误", "目录不存在", parent=self)
                return

            LogManager.get().info(f"添加语言入口: {game_dir}")

            hook_source = Path(get_resource_path("resource", "hooks", "hook_add_change_language_entrance.rpy"))
            if not hook_source.exists():
                raise FileNotFoundError(f"缺少 hook 文件: {hook_source}")

            target = Path(game_dir) / "hook_add_change_language_entrance.rpy"
            shutil.copy2(hook_source, target)
            LogManager.get().info(f"语言入口 Hook 写入: {target}")

            InfoBar.success("完成", "已添加语言入口脚本 (hook_add_change_language_entrance.rpy)", parent=self)

        except Exception as e:
            LogManager.get().error(f"添加语言入口失败: {e}")
            InfoBar.error("错误", f"添加语言入口失败: {e}", parent=self)
