"""Ren'Py replace_text supplement translation page."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel,
    CardWidget,
    ComboBox,
    FluentIcon,
    InfoBar,
    LineEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SingleDirectionScrollArea,
    StrongBodyLabel,
    TitleLabel,
)

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from base.LogManager import LogManager
from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Project.ProjectStore import ProjectStore
from widget.ThemeHelper import mark_toolbox_scroll_area, mark_toolbox_widget


class HookSupplementPage(Base, QWidget):
    """replace_text supplement flow."""

    def __init__(self, object_name: str, parent: Optional[QWidget] = None) -> None:
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)

        self.window = parent
        self.logger = LogManager.get()
        self.config = Config().load()
        self._active = False

        self._init_ui()

        self.subscribe(Base.Event.TRANSLATION_UPDATE, self._on_engine_update)
        self.subscribe(Base.Event.TRANSLATION_DONE, self._on_engine_done)
        self.subscribe(Base.Event.TRANSLATION_STOP, self._on_engine_stop)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.addWidget(
            TitleLabel(Localizer.localize("补全翻译", "Supplement Translation"))
        )
        header.addStretch(1)
        layout.addLayout(header)

        scroll_area = SingleDirectionScrollArea(orient = Qt.Orientation.Vertical)
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
        card = CardWidget(self)
        box = QVBoxLayout(card)
        box.setSpacing(12)

        box.addWidget(
            StrongBodyLabel(
                Localizer.localize(
                    "replace_text 补全模式", "replace_text Supplement Mode"
                )
            )
        )
        intro = CaptionLabel(
            Localizer.localize(
                "扫描源码与现有 tl 的差集，翻译后生成 game/tl/<lang>/replace_text_auto.rpy。",
                "Scan for entries present in the source but missing from the existing tl, then "
                "translate them into game/tl/<lang>/replace_text_auto.rpy.",
            )
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #777;")
        box.addWidget(intro)

        row_game = QHBoxLayout()
        row_game.addWidget(QLabel(Localizer.localize("项目目录:", "Project Folder:")))
        self.game_dir_edit = LineEdit()
        self.game_dir_edit.setPlaceholderText(
            Localizer.localize(
                "选择包含 game 目录的项目根目录",
                "Select the project root containing the game folder",
            )
        )
        if self.config.renpy_game_folder:
            self.game_dir_edit.setText(self.config.renpy_game_folder)
        self.game_dir_edit.textChanged.connect(self._refresh_output_hint)
        btn_browse = PushButton(Localizer.get().browse, icon = FluentIcon.FOLDER)
        btn_browse.clicked.connect(self._browse_game_dir)
        row_game.addWidget(self.game_dir_edit, 1)
        row_game.addWidget(btn_browse)
        box.addLayout(row_game)

        row_tl = QHBoxLayout()
        row_tl.addWidget(QLabel(Localizer.localize("语言目录名:", "Language Folder Name:")))
        self.tl_name_edit = LineEdit()
        self.tl_name_edit.setText(self._guess_default_tl_name())
        self.tl_name_edit.setFixedWidth(160)
        self.tl_name_edit.textChanged.connect(self._refresh_output_hint)
        row_tl.addWidget(self.tl_name_edit)
        row_tl.addStretch(1)
        box.addLayout(row_tl)

        row_source = QHBoxLayout()
        row_source.addWidget(QLabel(Localizer.localize("源语言:", "Source Language:")))
        self.source_lang_combo = ComboBox()
        self.source_lang_combo.addItem(
            Localizer.localize("简体中文", "Simplified Chinese"),
            userData = BaseLanguage.Enum.ZH,
        )
        self.source_lang_combo.addItem(
            Localizer.localize("繁体中文", "Traditional Chinese"),
            userData = BaseLanguage.Enum.ZH,
        )
        self.source_lang_combo.addItem(
            Localizer.localize("英语", "English"), userData = BaseLanguage.Enum.EN
        )
        self.source_lang_combo.addItem(
            Localizer.localize("日语", "Japanese"), userData = BaseLanguage.Enum.JA
        )
        self.source_lang_combo.addItem(
            Localizer.localize("韩语", "Korean"), userData = BaseLanguage.Enum.KO
        )
        self.source_lang_combo.setCurrentIndex(2)
        row_source.addWidget(self.source_lang_combo, 1)
        box.addLayout(row_source)

        row_target = QHBoxLayout()
        row_target.addWidget(QLabel(Localizer.localize("目标语言:", "Target Language:")))
        self.target_lang_combo = ComboBox()
        self.target_lang_combo.addItem(
            Localizer.localize("简体中文", "Simplified Chinese"),
            userData = BaseLanguage.Enum.ZH,
        )
        self.target_lang_combo.addItem(
            Localizer.localize("繁体中文", "Traditional Chinese"),
            userData = BaseLanguage.Enum.ZH,
        )
        self.target_lang_combo.addItem(
            Localizer.localize("英语", "English"), userData = BaseLanguage.Enum.EN
        )
        self.target_lang_combo.addItem(
            Localizer.localize("日语", "Japanese"), userData = BaseLanguage.Enum.JA
        )
        self.target_lang_combo.addItem(
            Localizer.localize("韩语", "Korean"), userData = BaseLanguage.Enum.KO
        )
        self.target_lang_combo.setCurrentIndex(0)
        row_target.addWidget(self.target_lang_combo, 1)
        box.addLayout(row_target)

        self.output_hint_label = CaptionLabel("")
        self.output_hint_label.setWordWrap(True)
        self.output_hint_label.setStyleSheet("color: #8fb3ff;")
        box.addWidget(self.output_hint_label)

        tip = CaptionLabel(
            Localizer.localize(
                "这个页面只负责补全/replace_text，不是 EXE 运行时 HOOK 模式。",
                "This page handles supplementation/replace_text only, not EXE runtime HOOK mode.",
            )
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #666;")
        box.addWidget(tip)

        self._refresh_output_hint()
        return card

    def _create_action_card(self) -> CardWidget:
        card = CardWidget(self)
        box = QVBoxLayout(card)
        box.setSpacing(10)

        row = QHBoxLayout()
        self.btn_start = PrimaryPushButton(
            Localizer.localize("开始补全翻译", "Start Supplement Translation"),
            icon = FluentIcon.PLAY,
        )
        self.btn_start.clicked.connect(self._start_translation)
        self.btn_stop = PushButton(Localizer.localize("停止", "Stop"), icon = FluentIcon.CANCEL)
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

        self.status_label = CaptionLabel(Localizer.localize("等待开始", "Ready"))
        box.addWidget(self.status_label)

        return card

    def _guess_default_tl_name(self) -> str:
        configured_tl = str(getattr(self.config, "renpy_tl_folder", "") or "").strip()
        if configured_tl != "":
            try:
                name = Path(configured_tl).name
                if name:
                    return name
            except Exception:
                pass
        return "chinese"

    def _browse_game_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, Localizer.localize("选择项目目录", "Select Project Folder"), ""
        )
        if path:
            self.game_dir_edit.setText(path)

    def _resolve_project_root(self) -> Optional[Path]:
        raw_path = self.game_dir_edit.text().strip()
        if raw_path == "":
            return None

        path = Path(raw_path)
        if path.is_file():
            return path.parent
        if path.name.lower() == "game":
            return path.parent
        return path

    def _resolve_tl_dir(self) -> Optional[Path]:
        project_root = self._resolve_project_root()
        if project_root is None:
            return None
        tl_name = self.tl_name_edit.text().strip() or "chinese"
        # 保留项目设置中明确的自定义 tl 语言目录，避免补全流程把它
        # 覆盖成固定的 game/tl/<lang>。
        configured = RenpyProjectPaths.from_config(self.config, tl_name)
        if configured is not None:
            try:
                # 路径解析只负责保持项目契约；目录是否具备可补全的 TL 文件
                # 由启动前检查处理，不能在这里悄悄改回标准目录。
                if configured.project_root == project_root.resolve():
                    return configured.tl_language_dir
            except Exception:
                pass
        return project_root / "game" / "tl" / tl_name

    def _refresh_output_hint(self) -> None:
        tl_dir = self._resolve_tl_dir()
        if tl_dir is None:
            self.output_hint_label.setText("")
            return
        self.output_hint_label.setText(
            Localizer.localize(
                "补全输出文件：{output_file}",
                "Supplement output file: {output_file}",
            ).format(output_file=tl_dir / "replace_text_auto.rpy")
        )

    def _has_effective_tl_files(self, tl_dir: Path) -> bool:
        if not tl_dir.exists():
            return False

        for path in tl_dir.rglob("*.rpy"):
            name = path.name.lower()
            if name.startswith("miss_ready_replace"):
                continue
            if name.startswith("hook_"):
                continue
            if name in {"replace_text_auto.rpy", "set_default_language_at_startup.rpy"}:
                continue
            return True
        return False

    def _start_translation(self) -> None:
        project_root = self._resolve_project_root()
        tl_dir = self._resolve_tl_dir()

        if project_root is None:
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.localize("请先选择项目目录", "Select a project folder first."),
                parent = self,
            )
            return
        if not project_root.exists():
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("项目目录不存在", "The project folder does not exist."),
                parent = self,
            )
            return
        if not (project_root / "game").exists():
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize(
                    "未找到 game 目录：{game_dir}", "game folder not found: {game_dir}"
                ).format(game_dir=project_root / "game"),
                parent = self,
            )
            return
        if tl_dir is None:
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("无法解析 tl 目录", "Could not resolve the tl folder."),
                parent = self,
            )
            return
        if not tl_dir.exists():
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize(
                    "未找到 tl 目录：{tl_dir}", "tl folder not found: {tl_dir}"
                ).format(tl_dir=tl_dir),
                parent = self,
            )
            return
        if not self._has_effective_tl_files(tl_dir):
            InfoBar.warning(
                Localizer.get().notice,
                Localizer.localize(
                    "未检测到有效 tl 文件，请先完成 tl 抽取",
                    "No valid tl files were found. Complete tl extraction first.",
                ),
                parent = self,
            )
            return

        config = Config().load()
        paths = RenpyProjectPaths.from_path(
            tl_dir,
            self.tl_name_edit.text().strip() or "chinese",
        )
        if paths is None:
            InfoBar.error(
                Localizer.get().error,
                Localizer.localize("无法解析项目路径", "Could not resolve the project path."),
                parent = self,
            )
            return
        source_lang = self.source_lang_combo.currentData()
        target_lang = self.target_lang_combo.currentData()
        ProjectStore.get().apply_resolved(
            config,
            paths,
            input_folder = paths.tl_language_dir,
            output_folder = paths.tl_language_dir,
            mutate = lambda current: (
                setattr(current, "renpy_hook_translate", True),
                setattr(current, "renpy_source_translate", False),
                setattr(current, "source_language", source_lang) if source_lang else None,
                setattr(current, "target_language", target_lang) if target_lang else None,
            ),
        )

        self._active = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText(
            Localizer.localize(
                "正在生成补全条目…", "Generating supplement entries..."
            )
        )

        self.emit(
            Base.Event.TRANSLATION_START,
            {
                "config": config,
                "status": Base.TranslationStatus.UNTRANSLATED,
                "input_folder": str(tl_dir),
                "output_folder": str(tl_dir),
                "source_language": config.source_language,
                "target_language": config.target_language,
            },
        )
        InfoBar.success(
            Localizer.localize("已开始", "Started"),
            Localizer.localize(
                "补全翻译已启动", "Supplement translation has started."
            ),
            parent = self,
        )

    def _stop_translation(self) -> None:
        if not self._active:
            return
        self.emit(Base.Event.TRANSLATION_STOP, {})
        self.btn_stop.setEnabled(False)
        self.status_label.setText(
            Localizer.localize("正在请求停止…", "Requesting translation to stop...")
        )

    def _on_engine_update(self, event, extras) -> None:
        if not self._active or not isinstance(extras, dict):
            return

        if extras.get("phase") == "preparing":
            self.progress_bar.setRange(0, 0)
            self.status_label.setText(Localizer.localize("预处理中…", "Preparing..."))
            return

        total = extras.get("total_line", 0) or 0
        current = extras.get("line", 0) or 0
        if total > 0:
            percent = int(max(0.0, min(1.0, current / total)) * 100)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)
            self.status_label.setText(
                Localizer.localize(
                    "翻译中… {current}/{total}", "Translating... {current}/{total}"
                ).format(current=current, total=total)
            )
        else:
            self.status_label.setText(Localizer.localize("翻译中…", "Translating..."))

    def _on_engine_done(self, event, data) -> None:
        if not self._active:
            return
        self._active = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText(
            Localizer.localize("补全翻译完成", "Supplement Translation Complete")
        )
        InfoBar.success(
            Localizer.get().complete,
            Localizer.localize("补全翻译完成", "Supplement translation is complete."),
            parent = self,
        )

    def _on_engine_stop(self, event, data) -> None:
        if not self._active:
            return
        self._active = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText(Localizer.localize("已停止", "Stopped"))
