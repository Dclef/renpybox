"""源码翻译页面（精简版，统一走 Engine 流程）。"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ComboBox,
    FluentIcon,
    InfoBar,
    LineEdit,
    MessageBox,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SingleDirectionScrollArea,
    StrongBodyLabel,
    SwitchButton,
    TitleLabel,
)

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from base.LogManager import LogManager
from module.Config import Config
from module.Localizer.Localizer import Localizer
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area


class SourceTranslatePage(Base, QWidget):
    """直接翻译 game/*.rpy 源码，参数精简，只负责触发 Engine。"""

    def __init__(self, object_name: str, parent: Optional[QWidget] = None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)

        self.window = parent
        self.logger = LogManager.get()
        self._output_hint_text = ""

        self._init_ui()

        # Engine 事件
        self.subscribe(Base.Event.TRANSLATION_UPDATE, self._on_engine_update)
        self.subscribe(Base.Event.TRANSLATION_DONE, self._on_engine_done)
        self.subscribe(Base.Event.TRANSLATION_STOP, self._on_engine_stop)

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(24, 24, 24, 24)

        layout.addWidget(
            TitleLabel(Localizer.localize("🔧 源码翻译", "🔧 Source Translation"))
        )

        warn = CaptionLabel(
            Localizer.localize(
                "使用引擎翻译源码。请选择 game 目录/文件、语言、备份，然后开始。",
                "Translate source code with the engine. Select a game folder or file, languages, "
                "and backup options, then start.",
            )
        )
        warn.setStyleSheet("color: #e0a000;")
        layout.addWidget(warn)

        scroll_area = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        scroll_area.setWidgetResizable(True)
        scroll_area.enableTransparentBackground()
        mark_toolbox_scroll_area(scroll_area)

        scroll_widget = QWidget()
        mark_toolbox_widget(scroll_widget, "toolboxScroll")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)

        scroll_layout.addWidget(self._create_target_card())
        scroll_layout.addWidget(self._create_action_card())
        scroll_layout.addStretch(1)

        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

    def _create_target_card(self) -> CardWidget:
        card = CardWidget(self)
        box = QVBoxLayout(card)
        box.setSpacing(12)

        box.addWidget(
            StrongBodyLabel(Localizer.localize("📂 翻译目标", "📂 Translation Target"))
        )

        # 模式：目录 / 单文件
        mode_row = QHBoxLayout()
        self.single_file_switch = SwitchButton(
            Localizer.localize("单文件模式", "Single File Mode")
        )
        self.single_file_switch.setChecked(False)
        self.single_file_switch.checkedChanged.connect(self._on_single_file_changed)
        mode_row.addWidget(self.single_file_switch)
        mode_row.addStretch(1)
        box.addLayout(mode_row)

        # game 目录
        self.game_dir_row = QWidget()
        row1 = QHBoxLayout(self.game_dir_row)
        row1.setContentsMargins(0, 0, 0, 0)
        row1.addWidget(QLabel(Localizer.localize("game 目录:", "Game Folder:")))
        self.game_dir_edit = LineEdit()
        self.game_dir_edit.setPlaceholderText(
            Localizer.localize("选择游戏的 game 目录", "Select the game's game folder")
        )
        self.game_dir_edit.textChanged.connect(self._refresh_output_hint)
        btn_browse = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
        btn_browse.clicked.connect(self._browse_game_dir)
        row1.addWidget(self.game_dir_edit, 1)
        row1.addWidget(btn_browse)
        box.addWidget(self.game_dir_row)

        # 单个文件
        self.single_file_row = QWidget()
        file_row = QHBoxLayout(self.single_file_row)
        file_row.setContentsMargins(0, 0, 0, 0)
        file_row.addWidget(QLabel(Localizer.localize(".rpy 文件:", ".rpy File:")))
        self.single_file_edit = LineEdit()
        self.single_file_edit.setPlaceholderText(
            Localizer.localize(
                "选择要翻译的单个 .rpy 文件", "Select a single .rpy file to translate"
            )
        )
        self.single_file_edit.textChanged.connect(self._refresh_output_hint)
        btn_browse_file = PushButton(Localizer.get().browse, icon=FluentIcon.DOCUMENT)
        btn_browse_file.clicked.connect(self._browse_single_rpy_file)
        file_row.addWidget(self.single_file_edit, 1)
        file_row.addWidget(btn_browse_file)
        self.single_file_row.setVisible(False)
        box.addWidget(self.single_file_row)

        self.output_hint_label = CaptionLabel("")
        self.output_hint_label.setWordWrap(True)
        self.output_hint_label.setStyleSheet("color: #8fb3ff;")
        box.addWidget(self.output_hint_label)

        # 源语言
        src_lang_row = QHBoxLayout()
        src_lang_row.addWidget(QLabel(Localizer.localize("源语言:", "Source Language:")))
        self.source_lang_combo = ComboBox()
        self.source_lang_combo.addItem(
            Localizer.localize("简体中文", "Simplified Chinese"),
            userData=BaseLanguage.Enum.ZH,
        )
        self.source_lang_combo.addItem(
            Localizer.localize("繁体中文", "Traditional Chinese"),
            userData=BaseLanguage.Enum.ZH,
        )
        self.source_lang_combo.addItem(
            Localizer.localize("英语", "English"), userData=BaseLanguage.Enum.EN
        )
        self.source_lang_combo.addItem(
            Localizer.localize("日语", "Japanese"), userData=BaseLanguage.Enum.JA
        )
        self.source_lang_combo.addItem(
            Localizer.localize("韩语", "Korean"), userData=BaseLanguage.Enum.KO
        )
        self.source_lang_combo.setCurrentIndex(2)
        src_lang_row.addWidget(self.source_lang_combo, 1)
        box.addLayout(src_lang_row)

        # 目标语言
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(Localizer.localize("目标语言:", "Target Language:")))
        self.target_lang_combo = ComboBox()
        self.target_lang_combo.addItem(
            Localizer.localize("简体中文", "Simplified Chinese"),
            userData=BaseLanguage.Enum.ZH,
        )
        self.target_lang_combo.addItem(
            Localizer.localize("繁体中文", "Traditional Chinese"),
            userData=BaseLanguage.Enum.ZH,
        )
        self.target_lang_combo.addItem(
            Localizer.localize("英语", "English"), userData=BaseLanguage.Enum.EN
        )
        self.target_lang_combo.addItem(
            Localizer.localize("日语", "Japanese"), userData=BaseLanguage.Enum.JA
        )
        self.target_lang_combo.addItem(
            Localizer.localize("韩语", "Korean"), userData=BaseLanguage.Enum.KO
        )
        self.target_lang_combo.setCurrentIndex(0)
        lang_row.addWidget(self.target_lang_combo, 1)
        box.addLayout(lang_row)

        # 备份开关
        backup_row = QHBoxLayout()
        self.backup_switch = SwitchButton(
            Localizer.localize("自动备份 .bak", "Automatically Back Up .bak")
        )
        self.backup_switch.setChecked(False)
        backup_row.addWidget(self.backup_switch)
        self.backup_external_switch = SwitchButton(
            Localizer.localize("备份源码到外部", "Back Up Source Code Externally")
        )
        self.backup_external_switch.checkedChanged.connect(self._on_backup_external_changed)
        backup_row.addWidget(self.backup_external_switch)
        backup_row.addStretch(1)
        box.addLayout(backup_row)

        # 备份目录
        backup_row2 = QHBoxLayout()
        self.backup_external_edit = LineEdit()
        self.backup_external_edit.setPlaceholderText(
            Localizer.localize("选择备份目录", "Select a backup folder")
        )
        self.backup_external_edit.setVisible(False)
        self.btn_browse_backup = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
        self.btn_browse_backup.setVisible(False)
        self.btn_browse_backup.clicked.connect(self._browse_backup_dir)
        backup_row2.addWidget(self.backup_external_edit, 1)
        backup_row2.addWidget(self.btn_browse_backup)
        box.addLayout(backup_row2)

        return card

    def _create_action_card(self) -> CardWidget:
        card = CardWidget(self)
        box = QVBoxLayout(card)
        box.setSpacing(10)

        row = QHBoxLayout()
        self.btn_start = PrimaryPushButton(
            Localizer.localize("开始翻译", "Start Translation"), icon=FluentIcon.PLAY
        )
        self.btn_start.clicked.connect(self._start_translation)
        self.btn_stop = PushButton(Localizer.localize("停止", "Stop"), icon=FluentIcon.CANCEL)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_translation)
        row.addWidget(self.btn_start)
        row.addWidget(self.btn_stop)
        row.addStretch(1)
        box.addLayout(row)

        self.progress_bar = ProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        box.addWidget(self.progress_bar)

        self.status_label = CaptionLabel(Localizer.localize("等待操作…", "Ready..."))
        box.addWidget(self.status_label)

        return card

    # ------------------------------------------------------------------ actions
    def _browse_game_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self, Localizer.localize("选择 game 目录", "Select Game Folder"), ""
        )
        if directory:
            self.game_dir_edit.setText(directory)

    def _on_single_file_changed(self, checked: bool):
        self.game_dir_row.setVisible(not checked)
        self.single_file_row.setVisible(checked)
        self._refresh_output_hint()

    def _browse_single_rpy_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            Localizer.localize(
                "选择要翻译的 .rpy 文件", "Select an .rpy File to Translate"
            ),
            "",
            Localizer.localize("Ren'Py 脚本 (*.rpy)", "Ren'Py Scripts (*.rpy)"),
        )
        if file_path:
            self.single_file_edit.setText(file_path)

    def _on_backup_external_changed(self, checked: bool):
        self.backup_external_edit.setVisible(checked)
        self.btn_browse_backup.setVisible(checked)

    def _browse_backup_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self, Localizer.localize("选择备份目录", "Select Backup Folder"), ""
        )
        if directory:
            self.backup_external_edit.setText(directory)

    def _build_safe_output_dir(self, target_path: Path, single_file: bool) -> Path:
        if single_file:
            return target_path.parent / f"{target_path.stem}_source_out"
        return target_path.parent / f"{target_path.name}_source_out"

    def _is_relative_to(self, path: Path, other: Path) -> bool:
        try:
            path.resolve().relative_to(other.resolve())
            return True
        except Exception:
            return False

    def _validate_source_output_layout(self, target_path: Path, output_dir: Path, single_file: bool) -> tuple[bool, str]:
        try:
            target_resolved = target_path.resolve()
            output_resolved = output_dir.resolve()
        except Exception:
            target_resolved = target_path
            output_resolved = output_dir

        if single_file:
            output_file = output_resolved / target_path.name
            try:
                if output_file.resolve() == target_resolved:
                    return False, Localizer.localize(
                        "源码翻译的输出目录不能直接写回原文件所在位置，请使用独立输出目录。",
                        "Source translation output cannot be written directly beside the original "
                        "file. Use a separate output folder.",
                    )
            except Exception:
                if str(output_file) == str(target_resolved):
                    return False, Localizer.localize(
                        "源码翻译的输出目录不能直接写回原文件所在位置，请使用独立输出目录。",
                        "Source translation output cannot be written directly beside the original "
                        "file. Use a separate output folder.",
                    )
            return True, ""

        if output_resolved == target_resolved:
            return False, Localizer.localize(
                "源码翻译要求输入目录和输出目录分离，不能写回到原 game 目录。",
                "Source translation requires separate input and output folders and cannot write "
                "back to the original game folder.",
            )
        if self._is_relative_to(output_resolved, target_resolved):
            return False, Localizer.localize(
                "输出目录不能放在输入目录内部，否则后续重新扫描时会污染原文缓存。",
                "The output folder cannot be inside the input folder because later scans would "
                "contaminate the source cache.",
            )
        if self._is_relative_to(target_resolved, output_resolved):
            return False, Localizer.localize(
                "输入目录不能放在输出目录内部，请使用完全分离的目录。",
                "The input folder cannot be inside the output folder. Use fully separate folders.",
            )
        return True, ""

    def _get_current_target_and_output(self) -> tuple[Optional[Path], Optional[Path], bool]:
        single_file = bool(getattr(self, "single_file_switch", None) and self.single_file_switch.isChecked())
        if single_file:
            file_path = self.single_file_edit.text().strip()
            if file_path == "":
                return None, None, True
            target_path = Path(file_path)
            if target_path.suffix.lower() != ".rpy":
                return target_path, None, True
            return target_path, self._build_safe_output_dir(target_path, True), True

        game_dir = self.game_dir_edit.text().strip()
        if game_dir == "":
            return None, None, False
        target_path = Path(game_dir)
        return target_path, self._build_safe_output_dir(target_path, False), False

    def _refresh_output_hint(self):
        target_path, output_dir, single_file = self._get_current_target_and_output()
        if target_path is None or output_dir is None:
            self.output_hint_text = ""
            self.output_hint_label.setText("")
            return

        ok, message = self._validate_source_output_layout(target_path, output_dir, single_file)
        if ok:
            self._output_hint_text = Localizer.localize(
                "源码翻译输出目录将自动写入：{output_dir}",
                "Source translation output will be written automatically to: {output_dir}",
            ).format(output_dir=output_dir)
        else:
            self._output_hint_text = Localizer.localize(
                "路径配置无效：{message}", "Invalid path configuration: {message}"
            ).format(message=message)
        self.output_hint_label.setText(self._output_hint_text)

    def _start_translation(self):
        single_file = bool(getattr(self, "single_file_switch", None) and self.single_file_switch.isChecked())

        target_path: Optional[Path] = None
        output_dir: Optional[Path] = None
        if single_file:
            file_path = self.single_file_edit.text().strip()
            if not file_path:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.localize("请选择 .rpy 文件", "Select an .rpy file."),
                    parent=self,
                )
                return
            target_path = Path(file_path)
            if not target_path.exists() or not target_path.is_file():
                InfoBar.error(
                    Localizer.get().error,
                    Localizer.localize("文件不存在", "The file does not exist."),
                    parent=self,
                )
                return
            if target_path.suffix.lower() != ".rpy":
                InfoBar.error(
                    Localizer.get().error,
                    Localizer.localize("请选择 .rpy 文件", "Select an .rpy file."),
                    parent=self,
                )
                return
            output_dir = self._build_safe_output_dir(target_path, True)
        else:
            game_dir = self.game_dir_edit.text().strip()
            if not game_dir:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.localize("请选择 game 目录", "Select a game folder."),
                    parent=self,
                )
                return
            target_path = Path(game_dir)
            if not target_path.exists():
                InfoBar.error(
                    Localizer.get().error,
                    Localizer.localize("目录不存在", "The folder does not exist."),
                    parent=self,
                )
                return
            output_dir = self._build_safe_output_dir(target_path, False)

        valid_layout, layout_message = self._validate_source_output_layout(target_path, output_dir, single_file)
        if not valid_layout:
            message_box = MessageBox(
                Localizer.localize("路径冲突", "Path Conflict"),
                layout_message,
                self.window or self,
            )
            message_box.yesButton.setText(Localizer.localize("知道了", "OK"))
            message_box.cancelButton.hide()
            message_box.exec()
            return

        backup = self.backup_switch.isChecked()
        backup_root = None
        if self.backup_external_switch.isChecked():
            backup_root = self.backup_external_edit.text().strip()
            if not backup_root:
                InfoBar.warning(
                    Localizer.get().notice,
                    Localizer.localize("请选择备份目录", "Select a backup folder."),
                    parent=self,
                )
                return

        try:
            config = Config().load()
            config.input_folder = str(target_path)
            config.output_folder = str(output_dir)
            src = self.source_lang_combo.currentData()
            if src:
                config.source_language = src
            tgt = self.target_lang_combo.currentData()
            if tgt:
                config.target_language = tgt
            config.renpy_backup_original = bool(backup)
            # 源码翻译走引擎时，启用源码解析模式
            config.renpy_source_translate = True
            config.renpy_hook_translate = False
        except Exception as exc:
            self.logger.error(f"加载/写入配置失败: {exc}")
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize(
                    "加载配置失败: {exc}", "Failed to load settings: {exc}"
                ).format(exc=exc),
                parent=self,
            )
            return

        def _start_engine_translation() -> None:
            # 更新 UI
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setValue(0)
            self.status_label.setText(Localizer.localize("预处理中…", "Preparing..."))

            # 触发 Engine 翻译
            self.emit(Base.Event.TRANSLATION_START, {
                "config": config,
                "status": Base.TranslationStatus.UNTRANSLATED,
                "input_folder": str(target_path),
                "output_folder": str(output_dir),
                "source_language": config.source_language,
                "target_language": config.target_language,
            })
            InfoBar.success(
                Localizer.localize("已开始", "Started"),
                Localizer.localize(
                    "已切换到统一翻译流程，输出目录：{output_dir}",
                    "Switched to the unified translation workflow. Output folder: {output_dir}",
                ).format(output_dir=output_dir),
                parent=self,
            )

        # 简单备份（外部目录或本地 .bak）
        if backup or backup_root:
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setValue(0)
            self.status_label.setText(
                Localizer.localize("正在备份源码…", "Backing up source code...")
            )

            def _backup_task() -> None:
                try:
                    self._backup_sources(target_path, backup_root)
                except Exception as exc:
                    self.logger.warning(f"备份源码失败: {exc}")
                QTimer.singleShot(0, _start_engine_translation)

            threading.Thread(target=_backup_task, daemon=True).start()
            return

        _start_engine_translation()

    def _stop_translation(self):

        self.emit(Base.Event.TRANSLATION_STOP, {})
        self.btn_stop.setEnabled(False)
        self.status_label.setText(
            Localizer.localize("正在请求停止...", "Requesting translation to stop...")
        )

    # ------------------------------------------------------------------ engine callbacks
    def _on_engine_update(self, event, extras):
        if not isinstance(extras, dict):
            return
        if extras.get("phase") == "preparing":
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            self.status_label.setText(Localizer.localize("预处理中…", "Preparing..."))
            return
        total = extras.get("total_line", 0) or 0
        current = extras.get("line", 0) or 0
        if total > 0:
            self.progress_bar.setRange(0, 100)
            percent = int(max(0.0, min(1.0, current / total)) * 100)
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(percent)
            self.status_label.setText(
                Localizer.localize(
                    "翻译中… {current}/{total}", "Translating... {current}/{total}"
                ).format(current=current, total=total)
            )
        else:
            self.status_label.setText(Localizer.localize("翻译中…", "Translating..."))

    def _on_engine_done(self, event, data):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText(Localizer.localize("翻译完成", "Translation Complete"))
        InfoBar.success(
            Localizer.get().complete,
            Localizer.localize(
                "统一翻译流程已完成", "The unified translation workflow is complete."
            ),
            parent=self,
        )

    def _on_engine_stop(self, event, data):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.status_label.setText(Localizer.localize("已停止", "Stopped"))
        self.progress_bar.setVisible(False)


    # ------------------------------------------------------------------ helpers
    def _backup_sources(self, target: Path, backup_root: Optional[str]) -> None:
        """简单备份 .rpy 源文件（目录模式：全部 .rpy；单文件模式：仅备份目标文件）。"""
        try:
            base_dir = target.parent if target.is_file() else target
            candidates = [target] if target.is_file() else list(Path(target).rglob("*.rpy"))
            for path in candidates:
                if not path.is_file():
                    continue
                if backup_root:
                    try:
                        rel = path.relative_to(base_dir)
                    except Exception:
                        rel = Path(path.name)
                    dest = Path(backup_root) / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(path.read_bytes())
                else:
                    bak = path.with_suffix(path.suffix + ".bak")
                    if not bak.exists():
                        bak.write_bytes(path.read_bytes())
        except Exception as exc:
            self.logger.warning(f"备份源码失败: {exc}")
