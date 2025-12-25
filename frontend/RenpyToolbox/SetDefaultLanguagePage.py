"""
设置默认语言页面 - 设置游戏启动时的默认语言
"""
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog
from qfluentwidgets import (
    CardWidget,
    PushButton,
    PrimaryPushButton,
    LineEdit,
    ComboBox,
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


class SetDefaultLanguagePage(Base, QWidget):
    """设置默认语言页面"""

    def __init__(self, object_name: str, parent=None, project_dir: str = None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)
        
        self.window = parent
        self.initial_project_dir = project_dir  # 传入的初始项目目录
        self._init_ui()

    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        layout.addWidget(TitleLabel("🌍 设置默认语言"))

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

        # 语言设置卡片
        scroll_layout.addWidget(self._create_language_card())

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

        # 项目目录（包含 game 目录的上级）
        row = QHBoxLayout()
        row.addWidget(QLabel("项目目录:"))
        self.project_dir_edit = LineEdit()
        self.project_dir_edit.setPlaceholderText("选择项目根目录（包含 game/ 的上级目录）")
        btn_browse = PushButton("浏览", icon=FluentIcon.FOLDER)
        btn_browse.clicked.connect(self._browse_project_dir)
        row.addWidget(self.project_dir_edit, 1)
        row.addWidget(btn_browse)
        layout.addLayout(row)
        
        # 如果有传入的初始目录，自动填充
        if self.initial_project_dir:
            self.project_dir_edit.setText(self.initial_project_dir)

        return card

    def _create_language_card(self) -> CardWidget:
        """创建语言设置卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("🗣️ 默认语言"))

        # 语言选择
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("默认语言:"))
        self.language_combo = ComboBox()
        self.language_combo.addItems([
            "chinese",
            "schinese", 
            "tchinese",
            "japanese",
            "korean",
            "english",
        ])
        self.language_combo.setCurrentText("chinese")
        row1.addWidget(self.language_combo, 1)
        layout.addLayout(row1)

        # 或自定义
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("自定义名称:"))
        self.custom_lang_edit = LineEdit()
        self.custom_lang_edit.setPlaceholderText("留空则使用上方选择的语言")
        row2.addWidget(self.custom_lang_edit, 1)
        layout.addLayout(row2)

        return card

    def _create_info_card(self) -> CardWidget:
        """创建说明卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("ℹ️ 功能说明"))

        info_text = CaptionLabel(
            "此功能将设置游戏启动时使用的默认语言。\n\n"
            "操作步骤：\n"
            "1. 选择项目根目录\n"
            "2. 选择或输入默认语言名称（必须与 tl 目录下的语言目录名一致）\n"
            "3. 点击'设置默认语言'按钮\n\n"
            "注意：语言名称必须与 game/tl/ 下的目录名完全一致",
            self
        )
        info_text.setWordWrap(True)
        layout.addWidget(info_text)

        return card

    def _create_action_card(self) -> CardWidget:
        """创建操作按钮卡片"""
        card = CardWidget(self)
        layout = QHBoxLayout(card)

        self.set_button = PrimaryPushButton("设置默认语言", icon=FluentIcon.ACCEPT)
        self.set_button.setFixedHeight(48)
        self.set_button.clicked.connect(self._set_default_language)

        layout.addStretch(1)
        layout.addWidget(self.set_button)
        layout.addStretch(1)

        return card

    def _browse_project_dir(self):
        """浏览目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择项目根目录", "")
        if directory:
            self.project_dir_edit.setText(directory)

    def _set_default_language(self):
        """设置默认语言"""
        try:
            project_dir = self.project_dir_edit.text().strip()
            if not project_dir:
                InfoBar.warning("提示", "请选择项目目录", parent=self)
                return

            if not Path(project_dir).exists():
                InfoBar.error("错误", "目录不存在", parent=self)
                return

            # 获取语言名称
            custom_lang = self.custom_lang_edit.text().strip()
            language = custom_lang if custom_lang else self.language_combo.currentText()

            if not language:
                InfoBar.warning("提示", "请选择或输入语言名称", parent=self)
                return

            # 检查 tl 目录是否存在
            game_dir = Path(project_dir) / "game"
            tl_dir = game_dir / "tl" / language
            if not tl_dir.exists():
                InfoBar.warning("警告", f"未找到语言目录: {tl_dir}\n请确保已创建该语言的翻译", parent=self)
                return

            LogManager.get().info(f"设置默认语言: {language}")

            template = Path(get_resource_path("resource", "templates", "default_langauge_template.txt"))
            if not template.exists():
                raise FileNotFoundError(f"缺少模板: {template}")

            target = game_dir / "set_default_language_at_startup.rpy"
            data = template.read_text(encoding="utf-8").replace('{tl_name}', language)
            target.write_text(data, encoding="utf-8")

            LogManager.get().info(f"默认语言已设置为: {language}")
            InfoBar.success("完成", f"默认语言脚本已生成: {target.name}", parent=self)
            
        except Exception as e:
            LogManager.get().error(f"设置默认语言失败: {e}")
            InfoBar.error("错误", f"设置默认语言失败: {e}", parent=self)
