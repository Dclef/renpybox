# -*- coding: utf-8 -*-
"""前端页面 - 终极结构导出（哈基米修正版）。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
)
from qfluentwidgets import (
    CardWidget,
    SubtitleLabel,
    BodyLabel,
    CaptionLabel,
    LineEdit,
    ComboBox,
    PushButton,
    PrimaryPushButton,
    CheckBox,
    InfoBar,
    FluentIcon,
)

from base.Base import Base
from base.LogManager import LogManager
from module.Config import Config
from module.Extract.HakimiSuiteRunner import HakimiSuiteRunner
from module.Localizer.Localizer import Localizer
from module.Extract.EmojiReplacer import (
    load_default_mapping,
    apply_replacements_dir,
    backup_folder,
)
from widget.ThemeHelper import mark_toolbox_widget


class MaSuitePage(Base, QWidget):
    """调用 MaSuiteRunner，生成 Excel 与终极结构文件。"""

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)

        self.logger = LogManager.get()
        self.config = Config().load()
        self.hakimi_runner = HakimiSuiteRunner(self.logger)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = SubtitleLabel(Localizer.get().ma_suite_title)
        layout.addWidget(title)

        desc = CaptionLabel(Localizer.get().ma_suite_description)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666;")
        layout.addWidget(desc)

        layout.addWidget(self._create_form_card())
        layout.addWidget(self._create_emoji_card())
        layout.addStretch(1)

    def _create_form_card(self) -> CardWidget:
        card = CardWidget(self)
        mark_toolbox_widget(card)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(10)

        # 游戏路径
        path_row = QHBoxLayout()
        path_row.addWidget(BodyLabel(Localizer.get().ma_suite_game_path))
        self.path_edit = LineEdit()
        self.path_edit.setPlaceholderText(Localizer.get().ma_suite_game_path_placeholder)
        if self.config.renpy_game_folder:
            self.path_edit.setText(self.config.renpy_game_folder)
        btn_browse_dir = PushButton(FluentIcon.FOLDER, Localizer.get().ma_suite_select_folder)
        btn_browse_dir.clicked.connect(self._browse_dir)
        btn_browse_exe = PushButton(Localizer.get().ma_suite_select_exe)
        btn_browse_exe.clicked.connect(self._browse_exe_into_path)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(btn_browse_dir)
        path_row.addWidget(btn_browse_exe)
        card_layout.addLayout(path_row)

        # 语言与官方提取
        tl_row = QHBoxLayout()
        tl_row.addWidget(BodyLabel(Localizer.get().ma_suite_language_name))
        self.tl_edit = LineEdit()
        self.tl_edit.setText("chinese")
        self.tl_edit.setFixedWidth(150)
        self.tl_edit.setToolTip(Localizer.get().ma_suite_language_name_tooltip)
        tl_row.addWidget(self.tl_edit)

        self.chk_official = CheckBox(Localizer.get().ma_suite_run_official_extraction_first)
        self.chk_official.setChecked(False)
        self.chk_official.stateChanged.connect(self._toggle_official_state)
        tl_row.addWidget(self.chk_official)
        tl_row.addStretch(1)
        card_layout.addLayout(tl_row)

        # 模式（老猫套件 v7.5 多模式版）
        mode_row = QHBoxLayout()
        mode_row.addWidget(BodyLabel(Localizer.get().ma_suite_extraction_mode))
        self.mode_combo = ComboBox()
        self.mode_combo.addItems([
            Localizer.get().ma_suite_mode_standard,
            Localizer.get().ma_suite_mode_external,
            Localizer.get().ma_suite_mode_aggressive,
        ])
        self.mode_combo.setCurrentIndex(0)
        self.mode_combo.setToolTip(Localizer.get().ma_suite_mode_tooltip)
        mode_row.addWidget(self.mode_combo, 1)
        mode_row.addStretch(1)
        card_layout.addLayout(mode_row)

        opt_row = QHBoxLayout()
        self.chk_emoji = CheckBox(Localizer.get().ma_suite_generate_emoji_mapping)
        self.chk_emoji.setChecked(False)
        self.chk_emoji.setToolTip(Localizer.get().ma_suite_generate_emoji_mapping_tooltip)
        opt_row.addWidget(self.chk_emoji)
        opt_row.addStretch(1)
        card_layout.addLayout(opt_row)

        # 可选 exe
        exe_row = QHBoxLayout()
        exe_row.addWidget(BodyLabel(Localizer.get().ma_suite_official_exe_optional))
        self.exe_edit = LineEdit()
        self.exe_edit.setPlaceholderText(Localizer.get().ma_suite_official_exe_placeholder)
        self.exe_edit.setEnabled(False)
        btn_exe = PushButton(FluentIcon.FOLDER, Localizer.get().select)
        btn_exe.clicked.connect(self._browse_exe)
        exe_row.addWidget(self.exe_edit, 1)
        exe_row.addWidget(btn_exe)
        card_layout.addLayout(exe_row)

        # 状态 + 按钮
        status_row = QHBoxLayout()
        self.status_label = CaptionLabel(Localizer.get().ready)
        self.status_label.setStyleSheet("color: #666;")
        status_row.addWidget(self.status_label)
        status_row.addStretch(1)
        card_layout.addLayout(status_row)

        action_row = QHBoxLayout()
        self.run_btn = PrimaryPushButton(FluentIcon.PLAY, Localizer.get().ma_suite_generate_structure)
        self.run_btn.clicked.connect(self._run_suite)
        action_row.addStretch(1)
        action_row.addWidget(self.run_btn)
        card_layout.addLayout(action_row)

        return card

    def _create_emoji_card(self) -> CardWidget:
        card = CardWidget(self)
        mark_toolbox_widget(card)
        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        layout.addWidget(BodyLabel(Localizer.get().ma_suite_emoji_helper))
        tip = CaptionLabel(Localizer.get().ma_suite_emoji_helper_description)
        tip.setStyleSheet("color: #666;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        path_row = QHBoxLayout()
        path_row.addWidget(BodyLabel(Localizer.get().ma_suite_target_folder))
        self.emoji_dir_edit = LineEdit()
        self.emoji_dir_edit.setPlaceholderText(Localizer.get().ma_suite_target_folder_placeholder)
        btn_browse = PushButton(FluentIcon.FOLDER, Localizer.get().select)
        btn_browse.clicked.connect(self._browse_emoji_dir)
        path_row.addWidget(self.emoji_dir_edit, 1)
        path_row.addWidget(btn_browse)
        layout.addLayout(path_row)

        btn_row = QHBoxLayout()
        self.btn_emoji_prepare = PushButton(Localizer.get().ma_suite_prepare_folder)
        self.btn_emoji_prepare.clicked.connect(lambda: self._run_emoji_dir("prepare"))
        self.btn_emoji_restore = PushButton(Localizer.get().ma_suite_restore_folder)
        self.btn_emoji_restore.clicked.connect(lambda: self._run_emoji_dir("restore"))
        btn_row.addWidget(self.btn_emoji_prepare)
        btn_row.addWidget(self.btn_emoji_restore)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        return card

    # -------------------- UI handlers -------------------- #
    def _toggle_official_state(self):
        enabled = self.chk_official.isChecked()
        self.exe_edit.setEnabled(enabled)
        if not enabled:
            self.exe_edit.clear()

    def _browse_emoji_dir(self):
        path = QFileDialog.getExistingDirectory(self, Localizer.get().ma_suite_select_rpy_folder)
        if path:
            self.emoji_dir_edit.setText(path)

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, Localizer.get().ma_suite_select_game_folder)
        if path:
            self.path_edit.setText(path)

    def _browse_exe_into_path(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            Localizer.get().ma_suite_select_game_executable,
            "",
            Localizer.get().ma_suite_executable_filter,
        )
        if path:
            self.path_edit.setText(path)

    def _browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            Localizer.get().ma_suite_select_official_exe,
            "",
            Localizer.get().ma_suite_executable_filter,
        )
        if path:
            self.exe_edit.setText(path)
            if not self.chk_official.isChecked():
                self.chk_official.setChecked(True)

    def _set_running(self, running: bool, message: Optional[str] = None):
        self.run_btn.setEnabled(not running)
        if message is not None:
            self.status_label.setText(message)
            self.status_label.setStyleSheet("color: #0078d4;" if running else "color: #666;")

    def _run_suite(self):
        game_path = self.path_edit.text().strip()
        if not game_path:
            InfoBar.warning(Localizer.get().notice, Localizer.get().ma_suite_select_game_path_first, parent=self)
            return

        tl_name = self.tl_edit.text().strip() or "chinese"
        use_official = self.chk_official.isChecked()
        gen_emoji = self.chk_emoji.isChecked()
        exe_path = self.exe_edit.text().strip() if use_official and self.exe_edit.text().strip() else None
        mode = str(self.mode_combo.currentIndex() + 1) if hasattr(self, "mode_combo") else "1"

        self._set_running(True, Localizer.get().ma_suite_generating_structure)
        try:
            result = self.hakimi_runner.run(
                game_path,
                tl_name,
                use_official=use_official,
                exe_path=exe_path,
                gen_emoji=gen_emoji,
                mode=mode,
            )
            if result is None:
                InfoBar.info(Localizer.get().complete, Localizer.get().ma_suite_no_result_check_paths, parent=self)
                self.status_label.setText(Localizer.get().ma_suite_no_result)
                self.status_label.setStyleSheet("color: #e67e22;")
                return

            result_path = ""
            if hasattr(result, "result_dir") and isinstance(result.result_dir, Path):
                result_path = str(result.result_dir)
            elif hasattr(result, "base_dir") and getattr(result, "base_dir", None):
                result_path = str(result.base_dir)

            extra = ""
            emoji_count = getattr(result, "emoji_replacements", 0)
            emoji_dir = getattr(result, "emoji_output_dir", None) or getattr(result, "emoji_dir", None)
            if gen_emoji and emoji_count:
                extra = Localizer.get().ma_suite_emoji_mapping_summary.format(
                    emoji_count=emoji_count,
                    emoji_dir=emoji_dir,
                )

            summary = Localizer.get().ma_suite_result_summary.format(
                names_count=result.names_count,
                others_count=result.others_count,
                replace_count=result.replace_count,
            )
            if hasattr(result, "deleted_count"):
                summary += Localizer.get().ma_suite_deleted_summary.format(
                    deleted_count=result.deleted_count
                )

            default_out = "translate_output"
            detail = Localizer.get().ma_suite_output_summary.format(
                summary=summary,
                output=result_path or default_out,
                extra=extra,
            )
            InfoBar.success(Localizer.get().complete, detail, parent=self)
            self.status_label.setText(Localizer.get().ma_suite_complete_status.format(
                output=result_path or Localizer.get().ma_suite_output_written
            ))
            self.status_label.setStyleSheet("color: #107c10;")

            # 记住路径
            self.config.renpy_game_folder = game_path
            self.config.save()
        except Exception as e:
            self.logger.error(f"翻译套件执行失败: {e}")
            InfoBar.error(Localizer.get().error, str(e), parent=self)
            self.status_label.setText(Localizer.get().ma_suite_execution_failed)
            self.status_label.setStyleSheet("color: #c50f1f;")
        finally:
            self._set_running(False)

    def _run_emoji_dir(self, mode: str):
        folder_path = self.emoji_dir_edit.text().strip()
        if not folder_path:
            InfoBar.warning(Localizer.get().notice, Localizer.get().ma_suite_select_target_folder, parent=self)
            return
        target = Path(folder_path)
        if not target.exists():
            InfoBar.error(
                Localizer.get().error,
                Localizer.get().ma_suite_folder_does_not_exist.format(target=target),
                parent=self,
            )
            return

        try:
            project_root = self._resolve_project_root()
            mapping = load_default_mapping(project_root, mode)

            # 备份
            backup_path = backup_folder(target)
            self.logger.info(f"已备份到: {backup_path}")

            success, failed = apply_replacements_dir(target, mapping, is_restore=(mode == "restore"))

            InfoBar.success(
                Localizer.get().complete,
                Localizer.get().ma_suite_folder_processed.format(
                    target=target,
                    success=success,
                    failed=failed,
                    backup_path=backup_path,
                ),
                parent=self,
            )
        except Exception as e:
            self.logger.error(f"Emoji 替换失败: {e}")
            InfoBar.error(Localizer.get().error, str(e), parent=self)

    def _resolve_project_root(self) -> Path:
        base_path = self.path_edit.text().strip() or self.config.renpy_game_folder
        if not base_path:
            raise RuntimeError(Localizer.get().ma_suite_select_game_path_above)
        path = Path(base_path).expanduser().resolve()
        project_root = path.parent if path.is_file() else path
        if project_root.name.lower() == "game":
            project_root = project_root.parent
        if not (project_root / "game").exists():
            raise FileNotFoundError(Localizer.get().ma_suite_game_folder_not_found.format(
                game_folder=project_root / "game"
            ))
        return project_root


__all__ = ["MaSuitePage"]
