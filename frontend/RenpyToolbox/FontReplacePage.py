"""
字体注入页面 - 小白模式
一键注入预置字体包（tl/<lang>/base_box + tl/<lang>/fonts）

说明：
- 默认是“非破坏性”注入：不会去改动 game/ 下的原始脚本字体引用
- 如需生成 GUI Hook（旧逻辑），可在高级选项勾选
- 如需直接替换所有字体引用（破坏性），可在高级选项执行
"""
import threading
from pathlib import Path
from typing import List, Optional

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
    ComboBox,
)

from base.Base import Base
from base.LogManager import LogManager
from module.Localizer.Localizer import Localizer
from module.Tool.FontReplacer import FontReplacer
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area


class FontReplacePage(Base, QWidget):
    """字体注入页面 - 小白模式"""

    font_replace_done = pyqtSignal(bool, str, object)

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)
        
        self.window = parent
        self.replacer = FontReplacer()
        self.new_font_source_path: Optional[str] = None
        self.detected_fonts: List[str] = []
        self.discovered_font_files: List[str] = []
        self.detected_languages: List[str] = []

        self._init_ui()
        self.font_replace_done.connect(self._on_font_replace_done)

    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        layout.addWidget(
            TitleLabel(Localizer.get().font_replace_font_injection)
        )

        # 创建滚动区域
        scroll_area = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        scroll_area.setWidgetResizable(True)
        scroll_area.enableTransparentBackground()
        mark_toolbox_scroll_area(scroll_area)

        scroll_widget = QWidget()
        mark_toolbox_widget(scroll_widget, "toolboxScroll")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(16)

        # 使用说明卡片
        scroll_layout.addWidget(self._create_intro_card())

        # 主操作卡片
        scroll_layout.addWidget(self._create_main_card())

        # 高级选项卡片
        scroll_layout.addWidget(self._create_advanced_card())

        scroll_layout.addStretch(1)
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

    def _create_intro_card(self) -> CardWidget:
        """创建使用说明卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        intro = CaptionLabel(
            Localizer.get().font_replace_if_game_cannot_display_translated_text_font,
            self
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        return card

    def _create_main_card(self) -> CardWidget:
        """创建主操作卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(16)

        layout.addWidget(
            StrongBodyLabel(
                Localizer.get().font_replace_select_game_folder_2
            )
        )

        # 目录选择
        dir_row = QHBoxLayout()
        self.game_dir_edit = LineEdit()
        self.game_dir_edit.setPlaceholderText(
            Localizer.get().font_replace_select_project_root_game_folder
        )
        self.game_dir_edit.editingFinished.connect(self._on_game_dir_edit_finished)
        btn_browse = PushButton(
            Localizer.get().browse, icon=FluentIcon.FOLDER
        )
        btn_browse.clicked.connect(self._browse_game_dir)
        dir_row.addWidget(self.game_dir_edit, 1)
        dir_row.addWidget(btn_browse)
        layout.addLayout(dir_row)

        # 扫描状态
        self.status_label = CaptionLabel(
            Localizer.get().font_replace_select_game_folder_first,
            self,
        )
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # 目标语言选择
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(Localizer.get().direct_rpy_target_language))
        self.target_lang_combo = ComboBox(self)
        self.target_lang_combo.addItem(
            Localizer.get().font_replace_auto_detect, None
        )
        self.target_lang_combo.setMinimumWidth(200)
        lang_row.addWidget(self.target_lang_combo, 1)
        layout.addLayout(lang_row)

        lang_hint = CaptionLabel(
            Localizer.get().font_replace_select_translation_language_receive_font_pack_chinese,
            self,
        )
        lang_hint.setWordWrap(True)
        layout.addWidget(lang_hint)

        # 一键注入按钮
        self.action_button = PrimaryPushButton(
            Localizer.get().font_replace_inject_fonts,
            icon=FluentIcon.FONT,
        )
        self.action_button.setFixedHeight(56)
        self.action_button.clicked.connect(self._one_click_inject)
        layout.addWidget(self.action_button)

        return card

    def _create_advanced_card(self) -> CardWidget:
        """创建高级选项卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        # 折叠标题
        header_row = QHBoxLayout()
        header_row.addWidget(
            StrongBodyLabel(
                Localizer.get().font_replace_advanced_options
            )
        )
        self.toggle_advanced_btn = PushButton(
            Localizer.get().font_replace_expand,
            icon=FluentIcon.CHEVRON_DOWN_MED,
        )
        self.toggle_advanced_btn.setFixedWidth(80)
        self.toggle_advanced_btn.clicked.connect(self._toggle_advanced)
        header_row.addStretch(1)
        header_row.addWidget(self.toggle_advanced_btn)
        layout.addLayout(header_row)

        # 高级选项容器
        self.advanced_widget = QWidget()
        advanced_layout = QVBoxLayout(self.advanced_widget)
        advanced_layout.setContentsMargins(0, 12, 0, 0)
        advanced_layout.setSpacing(12)

        # 自定义字体
        font_row = QHBoxLayout()
        font_row.addWidget(QLabel(Localizer.get().font_replace_custom_font))
        self.custom_font_edit = LineEdit()
        self.custom_font_edit.setPlaceholderText(
            Localizer.get().font_replace_leave_blank_use_bundled_font
        )
        btn_browse_font = PushButton(
            Localizer.get().browse, icon=FluentIcon.FOLDER
        )
        btn_browse_font.clicked.connect(self._browse_custom_font)
        font_row.addWidget(self.custom_font_edit, 1)
        font_row.addWidget(btn_browse_font)
        advanced_layout.addLayout(font_row)

        # 检测到的字体引用列表
        detected_row = QHBoxLayout()
        detected_row.addWidget(
            QLabel(
                Localizer.get().font_replace_detected_font_references
            )
        )
        self.detected_font_combo = ComboBox(self)
        self.detected_font_combo.addItem(
            Localizer.get().font_replace_not_scanned
        )
        self.detected_font_combo.setEnabled(False)
        detected_row.addWidget(self.detected_font_combo, 1)
        advanced_layout.addLayout(detected_row)

        self.font_scan_summary_label = CaptionLabel(
            Localizer.get().font_replace_only_fonts_referenced_scripts_listed_here_unreferenced,
            self,
        )
        self.font_scan_summary_label.setWordWrap(True)
        advanced_layout.addWidget(self.font_scan_summary_label)

        # 替换模式
        self.replace_all_check = CheckBox(
            Localizer.get().font_replace_replace_all_detected_fonts
        )
        self.replace_all_check.setChecked(False)
        advanced_layout.addWidget(self.replace_all_check)

        # 手动指定原字体
        old_font_row = QHBoxLayout()
        old_font_row.addWidget(
            QLabel(Localizer.get().font_replace_original_font)
        )
        self.old_font_edit = LineEdit()
        self.old_font_edit.setPlaceholderText(
            Localizer.get().font_replace_leave_blank_replace_all_detected_fonts
        )
        self.old_font_edit.setEnabled(True)
        old_font_row.addWidget(self.old_font_edit, 1)
        advanced_layout.addLayout(old_font_row)

        self.replace_all_check.stateChanged.connect(
            lambda checked: self.old_font_edit.setEnabled(not checked)
        )

        # 生成 GUI Hook（旧逻辑）
        self.generate_gui_check = CheckBox(
            Localizer.get().font_replace_also_generate_gui_font_hook_optional
        )
        self.generate_gui_check.setToolTip(
            Localizer.get().font_replace_creates_font_hook_tl_lang_gui_rpy
        )
        advanced_layout.addWidget(self.generate_gui_check)

        # 备份选项
        self.auto_backup_check = CheckBox(
            Localizer.get().font_replace_automatically_back_up_before_replacing_recommended
        )
        self.auto_backup_check.setChecked(True)
        advanced_layout.addWidget(self.auto_backup_check)
        
        # 操作按钮
        backup_row = QHBoxLayout()
        self.rescan_btn = PushButton(
            Localizer.get().font_replace_scan_all_fonts,
            icon=FluentIcon.SEARCH,
        )
        self.rescan_btn.clicked.connect(self._manual_rescan)
        backup_row.addWidget(self.rescan_btn)

        self.replace_all_fonts_btn = PushButton(
            Localizer.get().font_replace_replace_all_fonts,
            icon=FluentIcon.EDIT,
        )
        self.replace_all_fonts_btn.clicked.connect(self._replace_all_fonts)
        backup_row.addWidget(self.replace_all_fonts_btn)

        backup_row.addStretch(1)
        advanced_layout.addLayout(backup_row)

        layout.addWidget(self.advanced_widget)
        self.advanced_widget.setVisible(False)

        return card

    def _toggle_advanced(self):
        """切换高级选项显示"""
        visible = not self.advanced_widget.isVisible()
        self.advanced_widget.setVisible(visible)
        if visible:
            self.toggle_advanced_btn.setText(
                Localizer.get().font_replace_collapse
            )
            self.toggle_advanced_btn.setIcon(FluentIcon.UP)
        else:
            self.toggle_advanced_btn.setText(Localizer.get().font_replace_expand)
            self.toggle_advanced_btn.setIcon(FluentIcon.CHEVRON_DOWN_MED)

    def _browse_game_dir(self):
        """浏览游戏目录"""
        directory = QFileDialog.getExistingDirectory(
            self,
            Localizer.get().font_replace_select_game_folder,
            "",
        )
        if directory:
            self.game_dir_edit.setText(directory)
            self._scan_game_dir(directory)

    def _on_game_dir_edit_finished(self):
        """用户手动输入路径后自动扫描"""
        directory = self.game_dir_edit.text().strip()
        if directory:
            self._scan_game_dir(directory)

    def _browse_custom_font(self):
        """浏览自定义字体"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            Localizer.get().font_replace_select_font_file,
            "",
            Localizer.get().font_replace_font_files_ttf_otf_all_files,
        )
        if file_path:
            self.custom_font_edit.setText(file_path)
            self.new_font_source_path = file_path

    def _scan_game_dir(self, game_dir: str):
        """扫描游戏目录"""
        try:
            game_path = Path(game_dir)
            if not game_path.exists():
                self.status_label.setText(
                    Localizer.get().font_replace_folder_does_not_exist
                )
                return

            # 扫描脚本里的字体引用
            detected_fonts = self.replacer.scan_fonts(game_dir)
            self.detected_fonts = detected_fonts

            # 扫描游戏目录中的实际字体文件
            discovered_font_files = [
                rel_path for rel_path, _ in self.replacer.discover_font_files(game_dir)
            ]
            self.discovered_font_files = discovered_font_files

            # 扫描翻译语言
            detected_languages = self.replacer.get_translation_languages(game_dir)
            # 确保 chinese 总是存在 (方便用户新建汉化)
            if "chinese" not in detected_languages:
                detected_languages.append("chinese")
            self.detected_languages = detected_languages

            # 更新字体下拉框
            self.detected_font_combo.blockSignals(True)
            self.detected_font_combo.clear()
            if detected_fonts:
                self.detected_font_combo.addItems(detected_fonts)
                self.detected_font_combo.setEnabled(True)
            else:
                if discovered_font_files:
                    self.detected_font_combo.addItem(
                        Localizer.get().font_replace_no_font_references_detected_font_file_s.format(discovered_font_files_count=len(discovered_font_files))
                    )
                else:
                    self.detected_font_combo.addItem(
                        Localizer.get().font_replace_no_font_references_detected
                    )
                self.detected_font_combo.setEnabled(False)
            self.detected_font_combo.blockSignals(False)

            # 更新语言下拉框
            self.target_lang_combo.blockSignals(True)
            self.target_lang_combo.clear()
            self.target_lang_combo.addItem(
                Localizer.get().font_replace_default_language_global_replacement,
                None,
            )
            for lang in detected_languages:
                self.target_lang_combo.addItem(lang, lang)
            # 如果有 chinese，默认选中
            for i in range(self.target_lang_combo.count()):
                if self.target_lang_combo.itemData(i) == "chinese":
                    self.target_lang_combo.setCurrentIndex(i)
                    break
            self.target_lang_combo.blockSignals(False)

            # 更新状态
            font_count = len(detected_fonts)
            font_file_count = len(discovered_font_files)
            lang_count = len(detected_languages)
            self.status_label.setText(
                Localizer.get().font_replace_scan_complete_font_reference_s_font_file.format(font_count=font_count, font_file_count=font_file_count, lang_count=lang_count)
            )

            self.font_scan_summary_label.setText(
                Localizer.get().font_replace_scripts_reference_font_s_font_file_s.format(font_count=font_count, font_file_count=font_file_count)
            )

            LogManager.get().info(
                f"游戏目录扫描完成: 字体引用 {font_count} 个, 字体文件 {font_file_count} 个, 语言 {lang_count} 个"
            )

        except Exception as e:
            LogManager.get().error(f"扫描游戏目录失败: {e}")
            self.status_label.setText(
                Localizer.get().font_replace_scan_failed.format(e=e)
            )

    def _one_click_inject(self):
        """一键注入预置字体包（默认非破坏性）"""
        try:
            game_dir = self.game_dir_edit.text().strip()
            if not game_dir:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().font_replace_select_game_folder_first,
                    parent=self,
                )
                return

            if not Path(game_dir).exists():
                InfoBar.error(
                    Localizer.get().error,
                    Localizer.get().font_replace_folder_does_not_exist_2,
                    parent=self,
                )
                return

            # 获取目标语言
            target_lang = self.target_lang_combo.currentData()
            
            # 尝试从文本获取（当 data 为空但选择了有效语言时）
            if not target_lang:
                current_text = self.target_lang_combo.currentText()
                if current_text in self.detected_languages:
                    target_lang = current_text

            # 默认若未选择，使用 chinese（方便新建汉化）
            if not target_lang:
                target_lang = "chinese"

            # 1) 注入预置字体包（tl/<lang>/base_box + tl/<lang>/fonts）
            ok, message = self.replacer.deploy_builtin_font_pack(game_dir, target_lang)
            if not ok:
                InfoBar.error(
                    Localizer.get().error,
                    Localizer.get().font_replace_font_injection_failed.format(message=message),
                    parent=self,
                )
                return

            # 2) 可选：生成 GUI Hook（旧逻辑，放在高级选项）
            if self.generate_gui_check.isChecked():
                custom_font = self.custom_font_edit.text().strip()
                if custom_font:
                    if not Path(custom_font).exists():
                        InfoBar.error(
                            Localizer.get().error,
                            Localizer.get().font_replace_custom_font_file_does_not_exist,
                            parent=self,
                        )
                        return
                    font_source_path = custom_font
                else:
                    font_source_path = self.replacer.get_builtin_font_path()
                    if not font_source_path:
                        InfoBar.error(
                            Localizer.get().error,
                            Localizer.get().font_replace_bundled_font_not_found,
                            parent=self,
                        )
                        return

                success = self.replacer.gen_gui_fonts(
                    game_dir, target_lang, font_source_path, is_rtl=False
                )
                if not success:
                    InfoBar.warning(
                        Localizer.get().notice,
                        Localizer.get().font_replace_font_pack_injected_but_gui_hook_could,
                        parent=self,
                    )

            InfoBar.success(
                Localizer.get().android_build_done,
                Localizer.get().font_replace_font_pack_injected_into_tl.format(
                    target_lang=target_lang
                ),
                parent=self,
            )
            return

            # 确定要替换的字体
            original_fonts = None
            # 如果选择了替换所有字体
            if self.replace_all_check.isChecked():
                if not self.detected_fonts:
                    self._scan_game_dir(game_dir)
                original_fonts = self.detected_fonts
            
            # 尝试获取手动指定的原字体 (无论是否勾选替换所有，用户可能只想填这个)
            old_font_manual = self.old_font_edit.text().strip()
            if old_font_manual:
                if original_fonts is None:
                    original_fonts = []
                # 避免重复
                if old_font_manual not in original_fonts:
                    original_fonts.append(old_font_manual)
            
        except Exception as e:
            LogManager.get().error(f"一键注入失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().font_replace_font_injection_failed_2.format(e=e),
                parent=self,
            )

    def _replace_all_fonts(self):
        """替换所有检测到的字体引用（破坏性操作）"""
        try:
            game_dir = self.game_dir_edit.text().strip()
            if not game_dir:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().font_replace_select_game_folder_first,
                    parent=self,
                )
                return
            if not Path(game_dir).exists():
                InfoBar.error(
                    Localizer.get().error,
                    Localizer.get().font_replace_folder_does_not_exist_2,
                    parent=self,
                )
                return

            # 确定新字体
            custom_font = self.custom_font_edit.text().strip()
            if custom_font:
                if not Path(custom_font).exists():
                    InfoBar.error(
                        Localizer.get().error,
                        Localizer.get().font_replace_custom_font_file_does_not_exist,
                        parent=self,
                    )
                    return
                font_source_path = custom_font
            else:
                font_source_path = self.replacer.get_builtin_font_path()
                if not font_source_path:
                    InfoBar.error(
                        Localizer.get().error,
                        Localizer.get().font_replace_bundled_font_not_found,
                        parent=self,
                    )
                    return

            # 确定要替换的字体集合
            if not self.detected_fonts:
                self._scan_game_dir(game_dir)

            original_fonts: Optional[List[str]] = None
            if self.replace_all_check.isChecked():
                original_fonts = list(self.detected_fonts)
            else:
                old_font = self.old_font_edit.text().strip()
                if old_font:
                    original_fonts = [old_font]

            if not original_fonts:
                if self.detected_fonts:
                    InfoBar.warning(
                        Localizer.get().notice,
                        Localizer.get().font_replace_select_replace_all_detected_fonts_enter_original,
                        parent=self,
                    )
                else:
                    InfoBar.warning(
                        Localizer.get().notice,
                        Localizer.get().font_replace_no_font_references_detected_2,
                        parent=self,
                    )
                return

            create_backup = self.auto_backup_check.isChecked()
            self._set_replace_running(True)

            def task() -> None:
                try:
                    result = self.replacer.safe_replace_font(
                        game_dir=game_dir,
                        source_font_path=font_source_path,
                        original_fonts=original_fonts,
                        create_backup=create_backup,
                    )
                except Exception as e:
                    LogManager.get().error("替换所有字体失败", e)
                    result = (False, str(e), {})
                self.font_replace_done.emit(*result)

            threading.Thread(target=task, daemon=True).start()
        except Exception as e:
            self._set_replace_running(False)
            LogManager.get().error(f"替换所有字体失败: {e}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().font_replace_font_replacement_failed_3.format(e=e),
                parent=self,
            )

    def _set_replace_running(self, running: bool) -> None:
        """更新字体替换期间的页面状态。"""
        self.replace_all_fonts_btn.setEnabled(not running)
        self.rescan_btn.setEnabled(not running)
        self.action_button.setEnabled(not running)
        if running:
            self.status_label.setText(
                Localizer.get().font_replace_replacing_fonts_please_wait
            )

    def _on_font_replace_done(self, success: bool, message: str, details: dict) -> None:
        """在 UI 线程显示字体替换结果。"""
        self._set_replace_running(False)
        if success:
            replaced_files = details.get("replaced_files", 0)
            replaced_count = details.get("replaced_count", 0)
            self.status_label.setText(
                Localizer.get().font_replace_font_replacement_complete_file_s_replacement_s.format(replaced_files=replaced_files, replaced_count=replaced_count)
            )
            backup_info = ""
            if details.get("backup_name"):
                backup_info = Localizer.get().font_replace_backup_fonts_backup.format(details_backup_name=details['backup_name'])
            InfoBar.success(
                Localizer.get().android_build_done,
                Localizer.get().font_replace_modified_files_with_replacements.format(
                    replaced_files=replaced_files,
                    replaced_count=replaced_count,
                    backup_info=backup_info,
                ),
                parent=self,
            )
        else:
            self.status_label.setText(
                Localizer.get().font_replace_font_replacement_failed.format(message=message)
            )
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().font_replace_font_replacement_failed_2.format(message=message),
                parent=self,
            )

    def _manual_rescan(self):
        """手动重新扫描游戏目录"""
        game_dir = self.game_dir_edit.text().strip()
        if not game_dir:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().font_replace_select_game_folder_first,
                parent=self,
            )
            return
        self._scan_game_dir(game_dir)
        InfoBar.success(
            Localizer.get().android_build_done,
            Localizer.get().font_replace_game_folder_rescanned,
            parent=self,
        )
