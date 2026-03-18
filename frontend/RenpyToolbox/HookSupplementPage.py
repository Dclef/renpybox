"""Ren'Py replace_text supplement translation page."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
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
        header.addWidget(TitleLabel("补全翻译"))
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

        box.addWidget(StrongBodyLabel("replace_text 补全模式"))
        intro = CaptionLabel(
            "扫描源码与现有 tl 的差集，翻译后生成 game/tl/<lang>/replace_text_auto.rpy。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #777;")
        box.addWidget(intro)

        row_game = QHBoxLayout()
        row_game.addWidget(QLabel("项目目录:"))
        self.game_dir_edit = LineEdit()
        self.game_dir_edit.setPlaceholderText("选择包含 game 目录的项目根目录")
        if self.config.renpy_game_folder:
            self.game_dir_edit.setText(self.config.renpy_game_folder)
        self.game_dir_edit.textChanged.connect(self._refresh_output_hint)
        btn_browse = PushButton("浏览", icon = FluentIcon.FOLDER)
        btn_browse.clicked.connect(self._browse_game_dir)
        row_game.addWidget(self.game_dir_edit, 1)
        row_game.addWidget(btn_browse)
        box.addLayout(row_game)

        row_tl = QHBoxLayout()
        row_tl.addWidget(QLabel("语言目录名:"))
        self.tl_name_edit = LineEdit()
        self.tl_name_edit.setText(self._guess_default_tl_name())
        self.tl_name_edit.setFixedWidth(160)
        self.tl_name_edit.textChanged.connect(self._refresh_output_hint)
        row_tl.addWidget(self.tl_name_edit)
        row_tl.addStretch(1)
        box.addLayout(row_tl)

        row_source = QHBoxLayout()
        row_source.addWidget(QLabel("源语言:"))
        self.source_lang_combo = ComboBox()
        self.source_lang_combo.addItems(["简体中文", "繁体中文", "英语", "日语", "韩语"])
        self.source_lang_combo.setCurrentText("英语")
        row_source.addWidget(self.source_lang_combo, 1)
        box.addLayout(row_source)

        row_target = QHBoxLayout()
        row_target.addWidget(QLabel("目标语言:"))
        self.target_lang_combo = ComboBox()
        self.target_lang_combo.addItems(["简体中文", "繁体中文", "英语", "日语", "韩语"])
        self.target_lang_combo.setCurrentText("简体中文")
        row_target.addWidget(self.target_lang_combo, 1)
        box.addLayout(row_target)

        self.output_hint_label = CaptionLabel("")
        self.output_hint_label.setWordWrap(True)
        self.output_hint_label.setStyleSheet("color: #8fb3ff;")
        box.addWidget(self.output_hint_label)

        tip = CaptionLabel("这个页面只负责补全/replace_text，不是 EXE 运行时 HOOK 模式。")
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
        self.btn_start = PrimaryPushButton("开始补全翻译", icon = FluentIcon.PLAY)
        self.btn_start.clicked.connect(self._start_translation)
        self.btn_stop = PushButton("停止", icon = FluentIcon.CANCEL)
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

        self.status_label = CaptionLabel("等待开始")
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
        path = QFileDialog.getExistingDirectory(self, "选择项目目录", "")
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
        return project_root / "game" / "tl" / tl_name

    def _refresh_output_hint(self) -> None:
        tl_dir = self._resolve_tl_dir()
        if tl_dir is None:
            self.output_hint_label.setText("")
            return
        self.output_hint_label.setText(
            f"补全输出文件：{tl_dir / 'replace_text_auto.rpy'}"
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
            InfoBar.warning("提示", "请先选择项目目录", parent = self)
            return
        if not project_root.exists():
            InfoBar.error("错误", "项目目录不存在", parent = self)
            return
        if not (project_root / "game").exists():
            InfoBar.error("错误", f"未找到 game 目录：{project_root / 'game'}", parent = self)
            return
        if tl_dir is None:
            InfoBar.error("错误", "无法解析 tl 目录", parent = self)
            return
        if not tl_dir.exists():
            InfoBar.error("错误", f"未找到 tl 目录：{tl_dir}", parent = self)
            return
        if not self._has_effective_tl_files(tl_dir):
            InfoBar.warning("提示", "未检测到有效 tl 文件，请先完成 tl 抽取", parent = self)
            return

        config = Config().load()
        config.input_folder = str(tl_dir)
        config.output_folder = str(tl_dir)
        config.renpy_game_folder = str(project_root)
        config.renpy_tl_folder = str(tl_dir)
        config.renpy_hook_translate = True
        config.renpy_source_translate = False

        lang_map = {
            "简体中文": BaseLanguage.Enum.ZH,
            "繁体中文": BaseLanguage.Enum.ZH,
            "英语": BaseLanguage.Enum.EN,
            "日语": BaseLanguage.Enum.JA,
            "韩语": BaseLanguage.Enum.KO,
        }
        source_lang = lang_map.get(self.source_lang_combo.currentText())
        if source_lang:
            config.source_language = source_lang
        target_lang = lang_map.get(self.target_lang_combo.currentText())
        if target_lang:
            config.target_language = target_lang

        self._active = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("正在生成补全条目…")

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
        InfoBar.success("已开始", "补全翻译已启动", parent = self)

    def _stop_translation(self) -> None:
        if not self._active:
            return
        self.emit(Base.Event.TRANSLATION_STOP, {})
        self.btn_stop.setEnabled(False)
        self.status_label.setText("正在请求停止…")

    def _on_engine_update(self, event, extras) -> None:
        if not self._active or not isinstance(extras, dict):
            return

        if extras.get("phase") == "preparing":
            self.progress_bar.setRange(0, 0)
            self.status_label.setText(extras.get("message") or "预处理中…")
            return

        total = extras.get("total_line", 0) or 0
        current = extras.get("line", 0) or 0
        if total > 0:
            percent = int(max(0.0, min(1.0, current / total)) * 100)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)
            self.status_label.setText(f"翻译中… {current}/{total}")
        else:
            self.status_label.setText("翻译中…")

    def _on_engine_done(self, event, data) -> None:
        if not self._active:
            return
        self._active = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText("补全翻译完成")
        InfoBar.success("完成", "补全翻译完成", parent = self)

    def _on_engine_stop(self, event, data) -> None:
        if not self._active:
            return
        self._active = False
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("已停止")
