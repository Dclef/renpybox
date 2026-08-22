"""
Ren'Py 项目配置页面
管理项目路径、语言设置等
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from qfluentwidgets import (
    FluentIcon,
    PushButton,
    PrimaryPushButton,
    LineEdit,
    ComboBox,
    SwitchButton,
    CardWidget,
    SubtitleLabel,
    BodyLabel,
    MessageBox,
    InfoBar,
    InfoBarPosition
)

from base.LogManager import LogManager
from module.Config import Config
from module.Project.ProjectStore import ProjectStore


class RenpyProjectPage(QWidget):
    """Ren'Py 项目配置页面"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.config = Config()
        self.logger = LogManager.get()
        
        self._init_ui()
        self._load_config()
        self._connect_signals()

    def _init_ui(self):
        """初始化 UI"""
        self.setObjectName("RenpyProjectPage")
        
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # 标题
        title_label = SubtitleLabel("Ren'Py 项目设置", self)
        main_layout.addWidget(title_label)

        # 项目路径卡片
        self.path_card = self._create_path_card()
        main_layout.addWidget(self.path_card)

        # 语言设置卡片
        self.language_card = self._create_language_card()
        main_layout.addWidget(self.language_card)

        # 提取选项卡片
        self.extract_options_card = self._create_extract_options_card()
        main_layout.addWidget(self.extract_options_card)

        # 保存按钮
        btn_layout = QHBoxLayout()
        self.save_btn = PrimaryPushButton(FluentIcon.SAVE, "保存配置", self)
        self.reset_btn = PushButton(FluentIcon.CANCEL, "重置", self)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.reset_btn)
        btn_layout.addStretch(1)
        main_layout.addLayout(btn_layout)

        main_layout.addStretch(1)

    def _create_path_card(self) -> CardWidget:
        """创建路径配置卡片"""
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(10)

        # 标题
        title = BodyLabel("📁 项目路径", card)
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        card_layout.addWidget(title)

        # 项目路径
        project_layout = QHBoxLayout()
        self.project_path_edit = LineEdit(card)
        self.project_path_edit.setPlaceholderText("选择 Ren'Py 项目根目录...")
        self.project_path_btn = PushButton(FluentIcon.FOLDER, "浏览", card)
        project_layout.addWidget(BodyLabel("项目路径:", card), 0)
        project_layout.addWidget(self.project_path_edit, 1)
        project_layout.addWidget(self.project_path_btn)
        card_layout.addLayout(project_layout)

        # game 文件夹
        game_layout = QHBoxLayout()
        self.game_folder_edit = LineEdit(card)
        self.game_folder_edit.setPlaceholderText("game 文件夹路径 (通常为 game/)")
        self.game_folder_btn = PushButton(FluentIcon.FOLDER, "浏览", card)
        game_layout.addWidget(BodyLabel("game 文件夹:", card), 0)
        game_layout.addWidget(self.game_folder_edit, 1)
        game_layout.addWidget(self.game_folder_btn)
        card_layout.addLayout(game_layout)

        # tl 文件夹
        tl_layout = QHBoxLayout()
        self.tl_folder_edit = LineEdit(card)
        self.tl_folder_edit.setPlaceholderText("翻译文件夹路径 (通常为 game/tl/)")
        self.tl_folder_btn = PushButton(FluentIcon.FOLDER, "浏览", card)
        tl_layout.addWidget(BodyLabel("tl 文件夹:", card), 0)
        tl_layout.addWidget(self.tl_folder_edit, 1)
        tl_layout.addWidget(self.tl_folder_btn)
        card_layout.addLayout(tl_layout)

        # 自动检测按钮
        detect_layout = QHBoxLayout()
        self.auto_detect_btn = PushButton(FluentIcon.SEARCH, "自动检测路径", card)
        detect_layout.addWidget(self.auto_detect_btn)
        detect_layout.addStretch(1)
        card_layout.addLayout(detect_layout)

        return card

    def _create_language_card(self) -> CardWidget:
        """创建语言设置卡片"""
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(10)

        # 标题
        title = BodyLabel("🌍 语言设置", card)
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        card_layout.addWidget(title)

        # 源语言
        source_layout = QHBoxLayout()
        self.source_language_combo = ComboBox(card)
        self.source_language_combo.addItems([
            "日语 (JA)",
            "英语 (EN)",
            "韩语 (KO)",
            "简体中文 (ZH)",
            "繁体中文 (ZH-TW)"
        ])
        source_layout.addWidget(BodyLabel("源语言:", card), 0)
        source_layout.addWidget(self.source_language_combo, 1)
        source_layout.addStretch(2)
        card_layout.addLayout(source_layout)

        # 目标语言
        target_layout = QHBoxLayout()
        self.target_language_combo = ComboBox(card)
        self.target_language_combo.addItems([
            "简体中文 (ZH)",
            "繁体中文 (ZH-TW)",
            "英语 (EN)",
            "日语 (JA)",
            "韩语 (KO)"
        ])
        target_layout.addWidget(BodyLabel("目标语言:", card), 0)
        target_layout.addWidget(self.target_language_combo, 1)
        target_layout.addStretch(2)
        card_layout.addLayout(target_layout)

        # 繁体中文转换
        traditional_layout = QHBoxLayout()
        self.traditional_chinese_switch = SwitchButton(card)
        traditional_layout.addWidget(BodyLabel("启用繁体中文转换 (简→繁):", card))
        traditional_layout.addWidget(self.traditional_chinese_switch)
        traditional_layout.addStretch(1)
        card_layout.addLayout(traditional_layout)

        return card

    def _create_extract_options_card(self) -> CardWidget:
        """创建提取选项卡片"""
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(10)

        # 标题
        title = BodyLabel("⚙️ 提取选项", card)
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        card_layout.addWidget(title)

        # 提取对话
        dialogs_layout = QHBoxLayout()
        self.extract_dialogs_switch = SwitchButton(card)
        self.extract_dialogs_switch.setChecked(True)
        dialogs_layout.addWidget(BodyLabel("提取对话文本:", card))
        dialogs_layout.addWidget(self.extract_dialogs_switch)
        dialogs_layout.addStretch(1)
        card_layout.addLayout(dialogs_layout)

        # 提取字符串
        strings_layout = QHBoxLayout()
        self.extract_strings_switch = SwitchButton(card)
        self.extract_strings_switch.setChecked(True)
        strings_layout.addWidget(BodyLabel("提取字符串:", card))
        strings_layout.addWidget(self.extract_strings_switch)
        strings_layout.addStretch(1)
        card_layout.addLayout(strings_layout)

        # 提取界面
        screens_layout = QHBoxLayout()
        self.extract_screens_switch = SwitchButton(card)
        screens_layout.addWidget(BodyLabel("提取界面文本:", card))
        screens_layout.addWidget(self.extract_screens_switch)
        screens_layout.addStretch(1)
        card_layout.addLayout(screens_layout)

        # 备份原文件
        backup_layout = QHBoxLayout()
        self.backup_original_switch = SwitchButton(card)
        self.backup_original_switch.setChecked(True)
        backup_layout.addWidget(BodyLabel("自动备份原文件:", card))
        backup_layout.addWidget(self.backup_original_switch)
        backup_layout.addStretch(1)
        card_layout.addLayout(backup_layout)

        # 自动检测编码
        encoding_layout = QHBoxLayout()
        self.auto_detect_encoding_switch = SwitchButton(card)
        self.auto_detect_encoding_switch.setChecked(True)
        encoding_layout.addWidget(BodyLabel("自动检测文件编码:", card))
        encoding_layout.addWidget(self.auto_detect_encoding_switch)
        encoding_layout.addStretch(1)
        card_layout.addLayout(encoding_layout)

        # 默认编码
        default_encoding_layout = QHBoxLayout()
        self.default_encoding_combo = ComboBox(card)
        self.default_encoding_combo.addItems(["utf-8", "gbk", "shift-jis", "cp1252"])
        self.default_encoding_combo.setCurrentText("utf-8")
        default_encoding_layout.addWidget(BodyLabel("默认编码:", card), 0)
        default_encoding_layout.addWidget(self.default_encoding_combo, 1)
        default_encoding_layout.addStretch(2)
        card_layout.addLayout(default_encoding_layout)

        return card

    def _connect_signals(self):
        """连接信号槽"""
        self.project_path_btn.clicked.connect(self._on_browse_project_path)
        self.game_folder_btn.clicked.connect(self._on_browse_game_folder)
        self.tl_folder_btn.clicked.connect(self._on_browse_tl_folder)
        self.auto_detect_btn.clicked.connect(self._on_auto_detect_paths)
        
        self.save_btn.clicked.connect(self._on_save_config)
        self.reset_btn.clicked.connect(self._on_reset_config)

    def _load_config(self):
        """加载配置"""
        try:
            self.config.load()
            
            # 路径
            self.project_path_edit.setText(self.config.renpy_project_path)
            self.game_folder_edit.setText(self.config.renpy_game_folder)
            self.tl_folder_edit.setText(self.config.renpy_tl_folder)
            
            # 语言
            self.traditional_chinese_switch.setChecked(self.config.traditional_chinese_enable)
            
            # 提取选项
            self.extract_dialogs_switch.setChecked(self.config.renpy_extract_dialogs)
            self.extract_strings_switch.setChecked(self.config.renpy_extract_strings)
            self.extract_screens_switch.setChecked(self.config.renpy_extract_screens)
            self.backup_original_switch.setChecked(self.config.renpy_backup_original)
            self.auto_detect_encoding_switch.setChecked(self.config.renpy_auto_detect_encoding)
            self.default_encoding_combo.setCurrentText(self.config.renpy_default_encoding)
            
            self.logger.info("配置加载成功")
            
        except Exception as e:
            self.logger.error(f"加载配置失败: {e}")

    def _on_browse_project_path(self):
        """浏览项目路径"""
        from PyQt5.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "选择 Ren'Py 项目根目录")
        if folder:
            self.project_path_edit.setText(folder)

    def _on_browse_game_folder(self):
        """浏览 game 文件夹"""
        from PyQt5.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "选择 game 文件夹")
        if folder:
            self.game_folder_edit.setText(folder)

    def _on_browse_tl_folder(self):
        """浏览 tl 文件夹"""
        from PyQt5.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "选择翻译文件夹")
        if folder:
            self.tl_folder_edit.setText(folder)

    def _on_auto_detect_paths(self):
        """自动检测路径"""
        import os
        project_path = self.project_path_edit.text()
        
        if not project_path:
            self._show_error("错误", "请先选择项目根目录！")
            return

        # 检测 game 文件夹
        game_folder = os.path.join(project_path, "game")
        if os.path.isdir(game_folder):
            self.game_folder_edit.setText(game_folder)
            self.logger.info(f"检测到 game 文件夹: {game_folder}")

        # 检测 tl 文件夹
        tl_folder = os.path.join(game_folder, "tl")
        if os.path.isdir(tl_folder):
            self.tl_folder_edit.setText(tl_folder)
            self.logger.info(f"检测到 tl 文件夹: {tl_folder}")

        self._show_success("检测完成", "路径自动检测完成")

    def _on_save_config(self):
        """保存配置"""
        try:
            # 路径（项目事实经 ProjectStore 写入，切换后发 PROJECT_CHANGED）
            ProjectStore.get().save_edited_paths(
                self.config,
                project_path = self.project_path_edit.text(),
                game_folder = self.game_folder_edit.text(),
                tl_folder = self.tl_folder_edit.text(),
            )
            
            # 语言
            self.config.traditional_chinese_enable = self.traditional_chinese_switch.isChecked()
            
            # 提取选项
            self.config.renpy_extract_dialogs = self.extract_dialogs_switch.isChecked()
            self.config.renpy_extract_strings = self.extract_strings_switch.isChecked()
            self.config.renpy_extract_screens = self.extract_screens_switch.isChecked()
            self.config.renpy_backup_original = self.backup_original_switch.isChecked()
            self.config.renpy_auto_detect_encoding = self.auto_detect_encoding_switch.isChecked()
            self.config.renpy_default_encoding = self.default_encoding_combo.currentText()
            
            self.config.save()
            
            self._show_success("保存成功", "配置已保存")
            self.logger.info("配置保存成功")
            
        except Exception as e:
            self._show_error("保存失败", str(e))
            self.logger.error(f"保存配置失败: {e}")

    def _on_reset_config(self):
        """重置配置"""
        reply = MessageBox(
            "重置配置",
            "确定要重置所有配置吗？",
            self
        ).exec()
        
        if reply:
            self._load_config()
            self._show_info("重置成功", "配置已重置")

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
