"""直接翻译 tl/.rpy 页面（精简版，统一走 Engine 流程）"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (
    CardWidget,
    ComboBox,
    FluentIcon,
    InfoBar,
    LineEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SwitchButton,
    TitleLabel,
    CaptionLabel,
)

from base.Base import Base
from base.LogManager import LogManager
from module.Config import Config
from module.Extract.SimpleRpyExtractor import SimpleRpyExtractor
from module.Localizer.Localizer import Localizer
from module.Renpy.ProjectPaths import RenpyProjectPaths, apply_to_config
from widget.ThemeHelper import mark_toolbox_widget, mark_toolbox_scroll_area




class DirectRpyTranslatePage(Base, QWidget):
    """精简版 tl/.rpy 翻译页面，仅负责参数收集并触发 Engine 翻译。"""

    def __init__(self, object_name: str, parent: Optional[QWidget] = None, source_page: Optional[QWidget] = None) -> None:
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)

        self.window = parent
        self.source_page = source_page
        self.logger = LogManager.get()

        # UI
        self._init_ui()

        # 监听 Engine 事件
        self.subscribe(Base.Event.TRANSLATION_UPDATE, self._on_engine_update)
        self.subscribe(Base.Event.TRANSLATION_DONE, self._on_engine_done)
        self.subscribe(Base.Event.TRANSLATION_STOP, self._on_engine_stop)

    # ------------------------------------------------------------------ UI
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部标题
        header = QHBoxLayout()
        title = TitleLabel(Localizer.get().direct_rpy_translate_tl_rpy_files_engine_workflow)
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        # 滚动区域
        from qfluentwidgets import SingleDirectionScrollArea

        scroll_area = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical)
        scroll_area.setWidgetResizable(True)
        scroll_area.enableTransparentBackground()
        mark_toolbox_scroll_area(scroll_area)

        scroll = QWidget()
        mark_toolbox_widget(scroll, "toolboxScroll")
        scroll_layout = QVBoxLayout(scroll)
        scroll_layout.setSpacing(14)
        scroll_layout.setContentsMargins(20, 10, 20, 20)

        scroll_layout.addWidget(self._create_target_card())
        scroll_layout.addWidget(self._create_action_card())
        scroll_layout.addStretch(1)

        scroll_area.setWidget(scroll)
        layout.addWidget(scroll_area, 1)

    def _create_target_card(self) -> CardWidget:
        from qfluentwidgets import BodyLabel, SubtitleLabel

        card = CardWidget(self)
        box = QVBoxLayout(card)
        box.setSpacing(10)

        box.addWidget(SubtitleLabel(Localizer.get().direct_rpy_path_settings))

        # 游戏/项目路径
        row_game = QHBoxLayout()
        row_game.addWidget(BodyLabel(Localizer.get().direct_rpy_game_file_folder))
        self.game_file_edit = LineEdit()
        self.game_file_edit.setPlaceholderText(Localizer.get().direct_rpy_select_game_exe_project_folder)
        btn_browse_game = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
        btn_browse_game.clicked.connect(self._browse_game_file)
        row_game.addWidget(self.game_file_edit, 1)
        row_game.addWidget(btn_browse_game)
        box.addLayout(row_game)

        # tl 目录
        row_tl = QHBoxLayout()
        row_tl.addWidget(BodyLabel(Localizer.get().direct_rpy_tl_folder))
        self.tl_dir_edit = LineEdit()
        self.tl_dir_edit.setPlaceholderText(Localizer.get().direct_rpy_optional_defaults_game_tl_language)
        btn_browse_tl = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER)
        btn_browse_tl.clicked.connect(self._browse_tl_dir)
        row_tl.addWidget(self.tl_dir_edit, 1)
        row_tl.addWidget(btn_browse_tl)
        box.addLayout(row_tl)

        # tl 名称
        row_name = QHBoxLayout()
        row_name.addWidget(BodyLabel(Localizer.get().direct_rpy_tl_language_folder_name))
        self.tl_edit = LineEdit()
        self.tl_edit.setText("chinese")
        row_name.addWidget(self.tl_edit, 1)
        box.addLayout(row_name)

        # 目标语言 + 备份
        row_lang = QHBoxLayout()
        row_lang.addWidget(BodyLabel(Localizer.get().direct_rpy_target_language))
        self.target_lang_combo = ComboBox()
        self.target_lang_combo.addItems([
            Localizer.get().direct_rpy_simplified_chinese,
            Localizer.get().direct_rpy_traditional_chinese,
            Localizer.get().direct_rpy_english,
            Localizer.get().direct_rpy_japanese,
            Localizer.get().direct_rpy_korean,
        ])
        self.target_lang_combo.setCurrentIndex(0)
        row_lang.addWidget(self.target_lang_combo, 1)

        self.backup_switch = SwitchButton(Localizer.get().direct_rpy_create_bak_backup_before_writing)
        self.backup_switch.setChecked(False)
        row_lang.addWidget(self.backup_switch)
        row_lang.addStretch(1)
        box.addLayout(row_lang)

        return card

    def _create_action_card(self) -> CardWidget:
        card = CardWidget(self)
        box = QVBoxLayout(card)
        box.setSpacing(10)

        row = QHBoxLayout()
        self.btn_start = PrimaryPushButton(Localizer.get().direct_rpy_start_translation, icon=FluentIcon.PLAY)
        self.btn_start.clicked.connect(self._start_translation)
        self.btn_stop = PushButton(Localizer.get().stop, icon=FluentIcon.CANCEL)
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

        self.status_label = CaptionLabel(Localizer.get().ready)
        box.addWidget(self.status_label)

        return card

    # ------------------------------------------------------------------ actions
    def _browse_game_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            Localizer.get().direct_rpy_select_game_exe_folder,
            "",
            Localizer.get().direct_rpy_executable_exe_all_files,
        )
        if path:
            self.game_file_edit.setText(path)

    def _browse_tl_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, Localizer.get().direct_rpy_select_tl_folder, "")
        if path:
            self.tl_dir_edit.setText(path)

    def _start_translation(self) -> None:
        game_path = self.game_file_edit.text().strip()
        tl_dir_text = self.tl_dir_edit.text().strip()
        tl_name = self.tl_edit.text().strip() or "chinese"

        try:
            tl_dir: Optional[Path] = None
            input_tl_dir: Optional[Path] = None
            if tl_dir_text:
                tl_dir = Path(tl_dir_text)
                if not tl_dir.exists():
                    raise RuntimeError(Localizer.get().direct_rpy_tl_folder_does_not_exist.format(tl_dir=tl_dir))
                # 用户填入的是 tl 根目录，追加语言子目录
                input_tl_dir = tl_dir / tl_name
                if not input_tl_dir.exists():
                    raise RuntimeError(Localizer.get().direct_rpy_tl_folder_does_not_exist_2.format(tl_name=tl_name, input_tl_dir=input_tl_dir))
            else:
                if not game_path:
                    raise RuntimeError(Localizer.get().direct_rpy_select_game_file_tl_folder_first)
                game = Path(game_path)
                project_dir = game.parent if game.is_file() else game
                input_tl_dir = SimpleRpyExtractor.find_tl_directory(project_dir, tl_name)
                if input_tl_dir is None:
                    raise RuntimeError(Localizer.get().direct_rpy_tl_folder_not_found_run_extraction_select.format(tl_name=tl_name))

            config = Config().load()
            paths = RenpyProjectPaths.from_path(input_tl_dir, tl_name)
            if paths is None:
                raise RuntimeError(Localizer.get().direct_rpy_could_not_resolve_ren_py_project_paths)
            apply_to_config(
                config,
                paths,
                input_folder = paths.tl_language_dir,
                output_folder = paths.tl_language_dir,
            )
            config.renpy_backup_original = self.backup_switch.isChecked()
            # 直接翻译 tl/.rpy，必须关闭源码翻译模式，否则 FileManager 会走 RENPYSOURCE 分支
            config.renpy_source_translate = False
            config.renpy_hook_translate = False

            language_codes = ("ZH", "ZH", "EN", "JA", "KO")
            current_index = self.target_lang_combo.currentIndex()
            tgt = language_codes[current_index] if 0 <= current_index < len(language_codes) else None
            if tgt:
                config.target_language = tgt

            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.progress_bar.setValue(0)
            self.status_label.setText(Localizer.get().direct_rpy_translation_has_been_sent_engine_please_wait)

            self.emit(Base.Event.TRANSLATION_START, {
                "config": config,
                "status": Base.TranslationStatus.UNTRANSLATED,
            })
            InfoBar.success(
                Localizer.get().direct_rpy_started,
                Localizer.get().direct_rpy_unified_engine_workflow_has_started_progress_appears,
                parent=self,
            )
        except Exception as exc:
            self.logger.error(f"启动翻译失败: {exc}")
            InfoBar.error(Localizer.get().error, str(exc), parent=self)

    def _stop_translation(self) -> None:
        self.emit(Base.Event.TRANSLATION_STOP, {})
        self.btn_stop.setEnabled(False)
        self.status_label.setText(Localizer.get().direct_rpy_requesting_stop)

    # ------------------------------------------------------------------ engine callbacks
    def _on_engine_update(self, event, extras):
        if not isinstance(extras, dict):
            return
        total = extras.get("total_line", 0) or 0
        current = extras.get("line", 0) or 0
        if total > 0:
            ratio = max(0.0, min(1.0, current / total))
            self.progress_bar.setValue(int(ratio * 100))
        self.status_label.setText(Localizer.get().direct_rpy_translating.format(current=current, total=total))

    def _on_engine_done(self, event, data):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setValue(100)
        self.status_label.setText(Localizer.get().direct_rpy_translation_complete)
        InfoBar.success(Localizer.get().complete, Localizer.get().direct_rpy_engine_translation_complete, parent=self)

    def _on_engine_stop(self, event, data):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText(Localizer.get().direct_rpy_stopped)
