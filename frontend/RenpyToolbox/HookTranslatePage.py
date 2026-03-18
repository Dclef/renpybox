"""Ren'Py runtime HOOK translation page."""

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
from module.Engine.Engine import Engine
from module.Extract.RenpyExtractor import RenpyExtractor
from widget.ThemeHelper import mark_toolbox_scroll_area, mark_toolbox_widget


class HookTranslatePage(Base, QWidget):
    """Runtime EXE hook translation flow for Ren'Py."""

    def __init__(self, object_name: str, parent: Optional[QWidget] = None) -> None:
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)

        self.window = parent
        self.logger = LogManager.get()
        self.config = Config().load()
        self.extractor = RenpyExtractor()

        self._state = "idle"
        self._stop_requested = threading.Event()
        self._runtime_thread: threading.Thread | None = None

        self._init_ui()

        self.subscribe(Base.Event.TRANSLATION_UPDATE, self._on_engine_update)
        self.subscribe(Base.Event.TRANSLATION_DONE, self._on_engine_done)
        self.subscribe(Base.Event.TRANSLATION_STOP, self._on_engine_stop)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.addWidget(TitleLabel("HOOK翻译"))
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

        box.addWidget(StrongBodyLabel("运行时 EXE HOOK 抽取并翻译"))
        intro = CaptionLabel(
            "流程：向游戏 game 目录注入临时 hook，启动 EXE 进行运行时抽取，"
            "生成 tl/<lang> 后直接交给统一翻译引擎。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #777;")
        box.addWidget(intro)

        row_exe = QHBoxLayout()
        row_exe.addWidget(QLabel("游戏 EXE / 项目目录:"))
        self.exe_edit = LineEdit()
        self.exe_edit.setPlaceholderText("优先选择 .exe，也支持选择项目根目录自动查找")
        default_exe = self._guess_default_target()
        if default_exe:
            self.exe_edit.setText(str(default_exe))
        self.exe_edit.textChanged.connect(self._refresh_output_hint)
        btn_browse_exe = PushButton("选择 EXE", icon = FluentIcon.FOLDER)
        btn_browse_exe.clicked.connect(self._browse_exe)
        btn_browse_dir = PushButton("选择目录", icon = FluentIcon.FOLDER)
        btn_browse_dir.clicked.connect(self._browse_project_dir)
        row_exe.addWidget(self.exe_edit, 1)
        row_exe.addWidget(btn_browse_exe)
        row_exe.addWidget(btn_browse_dir)
        box.addLayout(row_exe)

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

        row_options = QHBoxLayout()
        self.backup_switch = SwitchButton("写回前自动备份 .bak")
        self.backup_switch.setChecked(False)
        row_options.addWidget(self.backup_switch)
        self.generate_empty_switch = SwitchButton("抽取时生成空白译文")
        self.generate_empty_switch.setChecked(False)
        row_options.addWidget(self.generate_empty_switch)
        row_options.addStretch(1)
        box.addLayout(row_options)

        self.output_hint_label = CaptionLabel("")
        self.output_hint_label.setWordWrap(True)
        self.output_hint_label.setStyleSheet("color: #8fb3ff;")
        box.addWidget(self.output_hint_label)

        tip = CaptionLabel(
            "这里的 HOOK翻译 指的是 EXE 运行时 hook 模式，不是 replace_text 补全。"
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
        self.btn_start = PrimaryPushButton("开始 HOOK翻译", icon = FluentIcon.PLAY)
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

    def _guess_default_target(self) -> Optional[Path]:
        raw = str(getattr(self.config, "renpy_game_folder", "") or "").strip()
        if raw == "":
            return None

        path = Path(raw)
        if path.is_file() and path.suffix.lower() == ".exe":
            return path

        project_root = path.parent if path.name.lower() == "game" else path
        if not project_root.exists():
            return None

        return self._auto_find_exe(project_root) or project_root

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

    def _browse_exe(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择游戏 EXE",
            "",
            "Executable (*.exe);;All Files (*)",
        )
        if path:
            self.exe_edit.setText(path)

    def _browse_project_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择项目目录", "")
        if path:
            self.exe_edit.setText(path)

    def _auto_find_exe(self, directory: Path) -> Optional[Path]:
        if not directory.exists() or not directory.is_dir():
            return None

        candidates = sorted(
            directory.glob("*.exe"),
            key = lambda item: item.stat().st_size if item.exists() else 0,
            reverse = True,
        )
        return candidates[0] if candidates else None

    def _resolve_project_root(self) -> Optional[Path]:
        raw_path = self.exe_edit.text().strip()
        if raw_path == "":
            return None

        path = Path(raw_path)
        if path.is_file():
            return path.parent
        if path.name.lower() == "game":
            return path.parent
        return path

    def _resolve_exe_path(self) -> Optional[Path]:
        raw_path = self.exe_edit.text().strip()
        if raw_path == "":
            return None

        path = Path(raw_path)
        if path.is_file() and path.suffix.lower() == ".exe":
            return path

        project_root = self._resolve_project_root()
        if project_root is None:
            return None
        return self._auto_find_exe(project_root)

    def _resolve_tl_dir(self) -> Optional[Path]:
        project_root = self._resolve_project_root()
        if project_root is None:
            return None
        tl_name = self.tl_name_edit.text().strip() or "chinese"
        return project_root / "game" / "tl" / tl_name

    def _refresh_output_hint(self) -> None:
        exe_path = self._resolve_exe_path()
        tl_dir = self._resolve_tl_dir()
        if tl_dir is None:
            self.output_hint_label.setText("")
            return

        if exe_path is None:
            self.output_hint_label.setText(f"输出目录：{tl_dir}\n当前还未找到可用 EXE。")
            return

        self.output_hint_label.setText(
            f"将使用 EXE：{exe_path}\n运行时抽取与翻译输出目录：{tl_dir}"
        )

    def _start_translation(self) -> None:
        if Engine.get().get_status() != Engine.Status.IDLE:
            InfoBar.warning("提示", "当前已有翻译任务在运行", parent = self)
            return

        exe_path = self._resolve_exe_path()
        project_root = self._resolve_project_root()
        tl_dir = self._resolve_tl_dir()
        tl_name = self.tl_name_edit.text().strip() or "chinese"

        if exe_path is None:
            InfoBar.error("错误", "未找到可用的游戏 EXE", parent = self)
            return
        if not exe_path.exists():
            InfoBar.error("错误", f"EXE 不存在：{exe_path}", parent = self)
            return
        if project_root is None or not project_root.exists():
            InfoBar.error("错误", "项目目录不存在", parent = self)
            return
        if not (project_root / "game").exists():
            InfoBar.error("错误", f"未找到 game 目录：{project_root / 'game'}", parent = self)
            return
        if tl_dir is None:
            InfoBar.error("错误", "无法解析 tl 输出目录", parent = self)
            return

        config = Config().load()
        config.input_folder = str(tl_dir)
        config.output_folder = str(tl_dir)
        config.renpy_game_folder = str(project_root)
        config.renpy_tl_folder = str(tl_dir)
        config.renpy_backup_original = self.backup_switch.isChecked()
        config.renpy_source_translate = False
        config.renpy_hook_translate = False

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

        self._stop_requested.clear()
        self._state = "extracting"
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("正在准备运行时 HOOK 抽取…")

        self._runtime_thread = threading.Thread(
            target = self._runtime_extract_and_translate,
            args = (exe_path, tl_name, config, self.generate_empty_switch.isChecked()),
            daemon = True,
        )
        self._runtime_thread.start()

    def _runtime_extract_and_translate(
        self,
        exe_path: Path,
        tl_name: str,
        config: Config,
        generate_empty: bool,
    ) -> None:
        try:
            tl_dir = self.extractor.runtime_extract(
                exe_path,
                tl_name,
                generate_empty = generate_empty,
                timeout = 300,
                progress_callback = self._queue_runtime_status,
                should_stop = self._stop_requested.is_set,
            )
            if self._stop_requested.is_set():
                QTimer.singleShot(0, self._finish_runtime_cancelled)
                return
            QTimer.singleShot(
                0,
                lambda cfg = config, out_dir = tl_dir: self._start_engine_translation(cfg, out_dir),
            )
        except Exception as exc:
            message = str(exc)
            if self._stop_requested.is_set() or "已取消" in message:
                QTimer.singleShot(0, self._finish_runtime_cancelled)
                return
            QTimer.singleShot(0, lambda msg = message: self._finish_runtime_failed(msg))

    def _queue_runtime_status(self, message: str) -> None:
        QTimer.singleShot(0, lambda msg = message: self._set_runtime_status(msg))

    def _set_runtime_status(self, message: str) -> None:
        if self._state != "extracting":
            return
        self.status_label.setText(message)

    def _start_engine_translation(self, config: Config, tl_dir: Path) -> None:
        if self._stop_requested.is_set():
            self._finish_runtime_cancelled()
            return

        if Engine.get().get_status() != Engine.Status.IDLE:
            self._finish_runtime_failed("运行时抽取完成，但当前已有翻译任务在运行")
            return

        self._state = "translating"
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("运行时抽取完成，正在启动统一翻译引擎…")

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
        InfoBar.success("已开始", f"运行时抽取完成，开始翻译：{tl_dir}", parent = self)

    def _stop_translation(self) -> None:
        if self._state == "extracting":
            self._stop_requested.set()
            self.btn_stop.setEnabled(False)
            self.status_label.setText("正在停止运行时抽取…")
            return

        if self._state == "translating":
            self.emit(Base.Event.TRANSLATION_STOP, {})
            self.btn_stop.setEnabled(False)
            self.status_label.setText("正在请求停止翻译…")

    def _finish_runtime_failed(self, message: str) -> None:
        self._state = "idle"
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("运行时 HOOK 抽取失败")
        self.logger.error(f"HOOK 翻译失败: {message}")
        InfoBar.error("错误", message, parent = self)

    def _finish_runtime_cancelled(self) -> None:
        self._state = "idle"
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("已停止")

    def _on_engine_update(self, event, extras) -> None:
        if self._state != "translating" or not isinstance(extras, dict):
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
        if self._state != "translating":
            return

        self._state = "idle"
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText("HOOK翻译完成")
        InfoBar.success("完成", "HOOK翻译完成", parent = self)

    def _on_engine_stop(self, event, data) -> None:
        if self._state != "translating":
            return

        self._state = "idle"
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("已停止")
