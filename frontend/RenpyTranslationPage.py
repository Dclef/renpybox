"""
翻译抽取到 TL 页面
简化版：一个主功能 + 可折叠的高级选项
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog
from qfluentwidgets import (
    FluentIcon,
    PushButton,
    PrimaryPushButton,
    LineEdit,
    CheckBox,
    CardWidget,
    SubtitleLabel,
    BodyLabel,
    CaptionLabel,
    ProgressBar,
    InfoBar,
    SingleDirectionScrollArea,
)

from base.LogManager import LogManager
from module.Config import Config
from module.Extract.UnifiedExtractor import UnifiedExtractor
from module.Localizer.Localizer import Localizer
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area




class RenpyTranslationPage(QWidget):
    """翻译抽取到 TL - 简化版"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent=parent)
        self.logger = LogManager.get()
        self.config = Config().load()
        # 保底：至少开启补充抽取，避免全关导致不会跑
        if not self.config.extract_use_official and not self.config.extract_use_custom:
            self.config.extract_use_custom = True
        self.unified_extractor = UnifiedExtractor()
        self._init_ui()

    def _init_ui(self) -> None:
        self.setObjectName("RenpyTranslationPage")
        mark_toolbox_widget(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        title = SubtitleLabel(Localizer.get().extract_tl_translation_extraction)
        layout.addWidget(title)

        # 简单说明
        intro = CaptionLabel(Localizer.get().extract_tl_extract_translatable_text_ren_py_game_tl)
        intro.setStyleSheet("color: gray;")
        layout.addWidget(intro)

        scroll_area = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        scroll_area.setWidgetResizable(True)
        mark_toolbox_scroll_area(scroll_area)
        scroll_widget = QWidget()
        mark_toolbox_widget(scroll_widget, "toolboxScroll")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)

        # 主功能区
        scroll_layout.addWidget(self._create_main_card())
        
        # 高级功能（折叠）
        scroll_layout.addWidget(self._create_advanced_card())
        
        scroll_layout.addStretch(1)

        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        self.progress_bar = ProgressBar(self)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

    def _create_main_card(self) -> CardWidget:
        """主功能卡片 - 极简"""
        card = CardWidget(self)
        mark_toolbox_widget(card)
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        # 游戏目录（最重要的输入）
        row1 = QHBoxLayout()
        row1.addWidget(BodyLabel(Localizer.get().extract_tl_game_folder))
        self.game_dir_edit = LineEdit()
        self.game_dir_edit.setPlaceholderText(Localizer.get().extract_tl_select_game_project_folder_contains_game_directory)
        if self.config.renpy_game_folder:
            self.game_dir_edit.setText(self.config.renpy_game_folder)
        btn_browse = PushButton(FluentIcon.FOLDER, Localizer.get().browse)
        btn_browse.clicked.connect(self._browse_game_dir)
        row1.addWidget(self.game_dir_edit, 1)
        row1.addWidget(btn_browse)
        layout.addLayout(row1)

        # 语言名称（简化）
        row2 = QHBoxLayout()
        row2.addWidget(BodyLabel(Localizer.get().extract_tl_language_name))
        self.tl_name_edit = LineEdit()
        self.tl_name_edit.setText("chinese")
        self.tl_name_edit.setFixedWidth(120)
        self.tl_name_edit.setToolTip(Localizer.get().extract_tl_translation_folder_name_such_chinese_schinese)
        row2.addWidget(self.tl_name_edit)
        row2.addStretch(1)
        
        # 主按钮
        self.extract_btn = PrimaryPushButton(FluentIcon.PLAY, Localizer.get().extract_tl_start_extraction)
        self.extract_btn.clicked.connect(self._do_extract)
        row2.addWidget(self.extract_btn)
        layout.addLayout(row2)

        # 快速提示
        tip = CaptionLabel(Localizer.get().extract_tl_existing_translations_preserved_default_supplemental_extraction_works)
        tip.setStyleSheet("color: #888;")
        layout.addWidget(tip)

        return card

    def _create_advanced_card(self) -> CardWidget:
        """高级选项卡片 - 默认折叠"""
        card = CardWidget(self)
        mark_toolbox_widget(card)
        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        # 标题行（可点击展开）
        header = QHBoxLayout()
        self.advanced_toggle = PushButton(Localizer.get().extract_tl_advanced_options)
        self.advanced_toggle.setFlat(True)
        self.advanced_toggle.clicked.connect(self._toggle_advanced)
        header.addWidget(self.advanced_toggle)
        header.addStretch(1)
        layout.addLayout(header)

        # 高级选项内容（默认隐藏）
        self.advanced_widget = QWidget()
        adv_layout = QVBoxLayout(self.advanced_widget)
        adv_layout.setContentsMargins(0, 8, 0, 0)
        adv_layout.setSpacing(8)

        # === 抽取方式选择 ===
        extract_row = QHBoxLayout()
        extract_row.addWidget(CaptionLabel(Localizer.get().extract_tl_extraction_method))
        
        self.chk_official = CheckBox(Localizer.get().extract_tl_official_extraction)
        self.chk_official.setChecked(self.config.extract_use_official)
        self.chk_official.setToolTip(Localizer.get().extract_tl_use_game_engine_s_official_translation_extraction)
        self.chk_official.stateChanged.connect(self._refresh_option_state)
        extract_row.addWidget(self.chk_official)
        
        self.chk_custom = CheckBox(Localizer.get().extract_tl_supplemental_extraction)
        self.chk_custom.setChecked(self.config.extract_use_custom)
        self.chk_custom.setToolTip(Localizer.get().extract_tl_use_custom_ast_parsing_extract_text_missed)
        self.chk_custom.stateChanged.connect(self._refresh_option_state)
        extract_row.addWidget(self.chk_custom)
        
        extract_row.addStretch(1)
        adv_layout.addLayout(extract_row)

        # === 可选 exe ===
        exe_row = QHBoxLayout()
        exe_row.addWidget(CaptionLabel(Localizer.get().extract_tl_game_exe_optional))
        self.exe_edit = LineEdit()
        self.exe_edit.setPlaceholderText(Localizer.get().extract_tl_only_required_official_extraction_leave_blank_find)
        btn_exe = PushButton(FluentIcon.FOLDER, Localizer.get().select)
        btn_exe.clicked.connect(lambda: self._browse_exe(self.exe_edit))
        exe_row.addWidget(self.exe_edit, 1)
        exe_row.addWidget(btn_exe)
        adv_layout.addLayout(exe_row)

        # === 其他选项 ===
        opt_row = QHBoxLayout()
        self.chk_skip_hooks = CheckBox(Localizer.get().extract_tl_skip_hook_files)
        self.chk_skip_hooks.setChecked(self.config.extract_skip_hook_files)
        opt_row.addWidget(self.chk_skip_hooks)
        self.chk_filter_bool_expr = CheckBox(Localizer.get().extract_tl_filter_suspected_code_entries)
        self.chk_filter_bool_expr.setChecked(
            getattr(self.config, "renpy_filter_suspicious_bool_expr", True)
        )
        self.chk_filter_bool_expr.setToolTip(Localizer.get().extract_tl_back_up_filtered_entries_filtered_suspicious_so)
        opt_row.addWidget(self.chk_filter_bool_expr)
        opt_row.addStretch(1)
        adv_layout.addLayout(opt_row)

        # === 增量合并 ===
        merge_row = QHBoxLayout()
        self.chk_auto_merge_cleanup = CheckBox(Localizer.get().extract_tl_merge_incremental_results_remove_duplicates_automatically)
        self.chk_auto_merge_cleanup.setChecked(
            getattr(self.config, "renpy_incremental_auto_merge_cleanup", True)
        )
        merge_row.addWidget(self.chk_auto_merge_cleanup)

        self.merge_cleanup_btn = PushButton(FluentIcon.SYNC, Localizer.get().extract_tl_merge_remove_duplicates)
        self.merge_cleanup_btn.clicked.connect(self._merge_incremental_now)
        merge_row.addWidget(self.merge_cleanup_btn)
        merge_row.addStretch(1)
        adv_layout.addLayout(merge_row)

        # === 误提取恢复 ===
        restore_row = QHBoxLayout()
        self.open_filtered_backup_btn = PushButton(FluentIcon.FOLDER, Localizer.get().extract_tl_open_filtered_backup)
        self.open_filtered_backup_btn.clicked.connect(self._open_filtered_backup_dir)
        restore_row.addWidget(self.open_filtered_backup_btn)

        self.restore_filtered_btn = PushButton(FluentIcon.SYNC, Localizer.get().extract_tl_restore_selected_entries)
        self.restore_filtered_btn.clicked.connect(self._restore_filtered_entries)
        restore_row.addWidget(self.restore_filtered_btn)
        restore_row.addStretch(1)
        adv_layout.addLayout(restore_row)

        restore_tip = CaptionLabel(Localizer.get().extract_tl_suspected_code_lines_moved_tl_lang_filtered)
        restore_tip.setStyleSheet("color: #666; font-size: 11px;")
        restore_tip.setWordWrap(True)
        adv_layout.addWidget(restore_tip)

        layout.addWidget(self.advanced_widget)
        self.advanced_widget.setVisible(False)  # 默认折叠
        self._refresh_option_state()

        return card

    def _toggle_advanced(self):
        """切换高级选项显示"""
        try:
            visible = not self.advanced_widget.isVisible()
            self.advanced_widget.setVisible(visible)
            # 更新按钮文字来表示展开/折叠状态
            text = (
                Localizer.get().extract_tl_advanced_options_2
                if visible
                else Localizer.get().extract_tl_advanced_options
            )
            self.advanced_toggle.setText(text)
        except Exception as e:
            self.logger.error(f"切换高级选项失败: {e}")

    # ==================== 核心逻辑 ====================

    def _do_extract(self):
        """执行抽取（主按钮）"""
        try:
            game_dir = self.game_dir_edit.text().strip()
            if not game_dir:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.get().onekey_select_game_folder_first,
                    parent=self,
                )
                return

            root_path = Path(game_dir)
            if not root_path.exists():
                InfoBar.error(
                    Localizer.get().error,
                    Localizer.get().extract_tl_folder_does_not_exist.format(game_dir=game_dir),
                    parent=self,
                )
                return

            # 处理路径
            exe_path: Optional[Path] = None
            if root_path.is_file():
                exe_path = root_path
                root_path = root_path.parent

            if root_path.name.lower() == "game":
                project_root = root_path.parent
            else:
                project_root = root_path

            game_folder = project_root / "game"
            if not game_folder.exists():
                InfoBar.error(
                    Localizer.get().error,
                    Localizer.get().extract_tl_game_directory_not_found,
                    parent=self,
                )
                return

            tl_name = self.tl_name_edit.text().strip() or "chinese"
            tl_dir = project_root / "game" / "tl" / tl_name
            if not tl_dir.exists():
                InfoBar.error(
                    Localizer.get().error,
                    Localizer.get().extract_tl_tl_subfolder_not_found.format(tl_dir=tl_dir),
                    parent=self,
                )
                return

            def _is_effective_tl_rpy(path: Path) -> bool:
                name = path.name.lower()
                if name.startswith("miss_ready_replace"):
                    return False
                if name.startswith("hook_"):
                    return False
                if name in {"replace_text_auto.rpy", "set_default_language_at_startup.rpy"}:
                    return False
                return True

            has_existing_tl = any(_is_effective_tl_rpy(p) for p in tl_dir.rglob("*.rpy"))

            # 编码预检：关闭自动检测时尝试读取一个文件
            if not self.config.renpy_auto_detect_encoding:
                sample_file = next(tl_dir.rglob("*.rpy"), None)
                if sample_file:
                    try:
                        sample_file.read_text(encoding=self.config.renpy_default_encoding)
                    except Exception as e:
                        InfoBar.error(
                            Localizer.get().error,
                            Localizer.get().extract_tl_failed_read_default_encoding.format(renpy_default_encoding=self.config.renpy_default_encoding, e=e),
                            parent=self,
                        )
                        return

            # 获取选项
            use_official = self.chk_official.isChecked() if hasattr(self, 'chk_official') else self.config.extract_use_official
            use_custom = self.chk_custom.isChecked() if hasattr(self, 'chk_custom') else self.config.extract_use_custom

            if not use_official and not use_custom:
                use_custom = True  # 至少启用补充抽取

            # 自动查找 exe
            if use_official and not exe_path:
                exe_edit_text = self.exe_edit.text().strip() if hasattr(self, 'exe_edit') else ""
                if exe_edit_text:
                    exe_path = Path(exe_edit_text)
                else:
                    exe_path = self._auto_find_exe(project_root)

            if use_official and not exe_path:
                use_official = False
                # 未找到 exe 时自动回退到补充抽取，避免“官方开但补充关”时无法抽取
                if not use_custom:
                    use_custom = True
                    if hasattr(self, "chk_custom"):
                        try:
                            self.chk_custom.setChecked(True)
                        except Exception:
                            pass
                self.logger.info("未找到 exe，跳过官方抽取")
                InfoBar.info(
                    Localizer.get().notice,
                    Localizer.get().extract_tl_no_exe_found_official_extraction_disabled_supplemental,
                    parent=self,
                )

            # 保存配置
            self.config.renpy_game_folder = game_dir
            self.config.extract_use_official = use_official
            self.config.extract_use_custom = use_custom
            if hasattr(self, 'chk_skip_hooks'):
                self.config.extract_skip_hook_files = self.chk_skip_hooks.isChecked()
            if hasattr(self, 'chk_filter_bool_expr'):
                self.config.renpy_filter_suspicious_bool_expr = self.chk_filter_bool_expr.isChecked()
            if hasattr(self, "chk_auto_merge_cleanup"):
                self.config.renpy_incremental_auto_merge_cleanup = self.chk_auto_merge_cleanup.isChecked()
            self.config.save()

            # 执行抽取
            self._begin(Localizer.get().extract_tl_extracting_translatable_text)

            if has_existing_tl:
                self.logger.info("检测到已有翻译，启用增量抽取以保留译文")
                InfoBar.info(
                    Localizer.get().extract_tl_incremental_mode,
                    Localizer.get().extract_tl_existing_tl_files_found_incremental_extraction_preserve,
                    parent=self,
                )
                result = self.unified_extractor.extract_incremental(
                    project_root,
                    tl_name,
                    exe_path,
                    use_official=use_official
                )
                if (
                    result.success
                    and getattr(self.config, "renpy_incremental_auto_merge_cleanup", True)
                    and result.incremental_dir
                ):
                    merge_result = self.unified_extractor.merge_incremental_folder(
                        project_root,
                        tl_name,
                        result.incremental_dir,
                        clean_duplicates=True,
                    )
                    if merge_result.success:
                        InfoBar.success(
                            Localizer.get().extract_tl_automatic_merge_complete,
                            Localizer.get().extract_tl_incremental_results_merged,
                            parent=self,
                        )
                    else:
                        InfoBar.warning(
                            Localizer.get().extract_tl_automatic_merge_failed,
                            Localizer.get().extract_tl_incremental_results_merge_failed,
                            parent=self,
                        )
            else:
                result = self.unified_extractor.extract_regular(
                    project_root,
                    tl_name,
                    exe_path,
                    use_official=use_official
                )

            self._end(result.success)
            
            if result.success:
                InfoBar.success(
                    Localizer.get().extract_tl_extraction_complete,
                    Localizer.get().extract_tl_translation_extraction_completed,
                    parent=self,
                )
            else:
                InfoBar.error(
                    Localizer.get().extract_tl_extraction_failed,
                    Localizer.get().extract_tl_translation_extraction_failed,
                    parent=self,
                )

        except Exception as e:
            self.logger.error(f"抽取失败: {e}")
            InfoBar.error(Localizer.get().error, str(e), parent=self)
            self._end(False)

    def _merge_incremental_now(self):
        """合并增量目录并清理重复"""
        try:
            _, tl, project_root = self._resolve_paths()
            incremental_dir = project_root / "game" / "tl" / f"{tl}_new"
            self._begin(Localizer.get().extract_tl_merging_incremental_translations)
            result = self.unified_extractor.merge_incremental_folder(
                project_root,
                tl,
                incremental_dir,
                clean_duplicates=True,
            )
            self._end(result.success)
            if result.success:
                InfoBar.success(
                    Localizer.get().extract_tl_merge_complete,
                    Localizer.get().extract_tl_incremental_results_merged,
                    parent=self,
                )
            else:
                InfoBar.warning(
                    Localizer.get().onekey_merge_failed,
                    Localizer.get().extract_tl_incremental_results_merge_failed,
                    parent=self,
                )
        except Exception as e:
            self.logger.error(f"合并失败: {e}")
            InfoBar.error(Localizer.get().error, str(e), parent=self)
            self._end(False)

    def _get_filtered_backup_root(self) -> Path:
        _, tl, project_root = self._resolve_paths()
        return project_root / "game" / "tl" / tl / "_filtered_suspicious"

    def _find_latest_filtered_manifest(self) -> Optional[Path]:
        backup_root = self._get_filtered_backup_root()
        if not backup_root.exists():
            return None

        manifests = sorted(
            backup_root.glob("*/restore_manifest.csv"),
            key=lambda path: path.stat().st_mtime if path.exists() else 0.0,
            reverse=True,
        )
        if manifests:
            return manifests[0]

        fallback = backup_root / "restore_manifest.csv"
        return fallback if fallback.exists() else None

    def _open_path_in_shell(self, path: Path) -> None:
        target = str(path)
        if sys.platform.startswith("win"):
            os.startfile(target)
            return
        if sys.platform == "darwin":
            subprocess.run(["open", target], check=False)
            return
        subprocess.run(["xdg-open", target], check=False)

    def _open_filtered_backup_dir(self):
        try:
            manifest = self._find_latest_filtered_manifest()
            if manifest and manifest.exists():
                self._open_path_in_shell(manifest)
                return

            backup_root = self._get_filtered_backup_root()
            if backup_root.exists():
                self._open_path_in_shell(backup_root)
                return

            InfoBar.warning(
                Localizer.get().notice,
                Localizer.get().extract_tl_no_filtered_backup_available_yet,
                parent=self,
            )
        except Exception as e:
            self.logger.error(f"打开误提取备份失败: {e}")
            InfoBar.error(Localizer.get().error, str(e), parent=self)

    def _restore_filtered_entries(self):
        try:
            _, tl, project_root = self._resolve_paths()
            self._begin(Localizer.get().extract_tl_restoring_filtered_entries)
            result = self.unified_extractor.restore_flagged_suspicious_entries(project_root, tl)
            self._end(result.success)
            if result.success:
                InfoBar.success(
                    Localizer.get().extract_tl_restore_complete,
                    Localizer.get().extract_tl_entries_restored,
                    parent=self,
                )
            else:
                InfoBar.warning(
                    Localizer.get().extract_tl_nothing_restored,
                    Localizer.get().extract_tl_no_entries_restored,
                    parent=self,
                )
        except Exception as e:
            self.logger.error(f"恢复误提取条目失败: {e}")
            InfoBar.error(Localizer.get().error, str(e), parent=self)
            self._end(False)

    # ==================== 工具方法 ====================

    def _resolve_paths(self) -> tuple[str, str, Path]:
        """解析路径"""
        game_dir = self.game_dir_edit.text().strip()
        if not game_dir:
            raise RuntimeError(Localizer.get().onekey_select_game_folder_first)

        path = Path(game_dir).resolve()
        if path.is_file():
            project_root = path.parent
        elif path.name.lower() == "game":
            project_root = path.parent
        else:
            project_root = path

        tl = self.tl_name_edit.text().strip() or "chinese"
        target = self.exe_edit.text().strip() if hasattr(self, 'exe_edit') and self.exe_edit.text().strip() else str(project_root)

        return target, tl, project_root

    def _auto_find_exe(self, root_dir: Path) -> Optional[Path]:
        """自动查找 exe"""
        for pattern in ("*.exe", "*.py"):
            for f in root_dir.glob(pattern):
                if f.is_file() and f.stat().st_size > 1024:
                    return f
        return None

    def _browse_game_dir(self):
        path = QFileDialog.getExistingDirectory(self, Localizer.get().onekey_select_game_folder)
        if path:
            self.game_dir_edit.setText(path)
            self.config.renpy_game_folder = path
            self.config.save()

    def _browse_exe(self, edit: LineEdit):
        path, _ = QFileDialog.getOpenFileName(
            self,
            Localizer.get().extract_tl_select_game_executable,
            "",
            Localizer.get().extract_tl_executable_files_exe_py,
        )
        if path:
            edit.setText(path)

    def _begin(self, msg: str):
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.extract_btn.setEnabled(False)

    def _end(self, ok: bool):
        self.progress_bar.setVisible(False)
        self.extract_btn.setEnabled(True)
        # 根据选项状态更新可用性
        self._refresh_option_state()

    def _refresh_option_state(self):
        """根据勾选状态刷新控件可用性"""
        try:
            use_official = self.chk_official.isChecked() if hasattr(self, 'chk_official') else False
            use_custom = self.chk_custom.isChecked() if hasattr(self, 'chk_custom') else True

            if hasattr(self, 'exe_edit'):
                self.exe_edit.setEnabled(use_official)
                if not use_official:
                    self.exe_edit.setPlaceholderText(Localizer.get().extract_tl_only_required_official_extraction_leave_blank_find)
                else:
                    self.exe_edit.setPlaceholderText(Localizer.get().extract_tl_leave_blank_find_exe_automatically)

            # 至少保证有一种抽取方式
            if not use_official and not use_custom:
                self.chk_custom.setChecked(True)
        except Exception as e:
            self.logger.warning(f"刷新选项状态失败: {e}")
