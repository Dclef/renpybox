"""源码翻译页面（精简版，统一走 Engine 流程）。"""

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
    SwitchButton,
    TitleLabel,
)

from base.Base import Base
from base.LogManager import LogManager
from module.Config import Config
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

        layout.addWidget(TitleLabel("🔧 源码翻译（Engine 流程）"))

        warn = CaptionLabel("统一走 Engine：请选择 game 目录、目标语言、备份，然后开始。")
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

        box.addWidget(StrongBodyLabel("📂 翻译目标"))

        # game 目录
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("game 目录:"))
        self.game_dir_edit = LineEdit()
        self.game_dir_edit.setPlaceholderText("选择游戏的 game 目录")
        btn_browse = PushButton("浏览", icon=FluentIcon.FOLDER)
        btn_browse.clicked.connect(self._browse_game_dir)
        row1.addWidget(self.game_dir_edit, 1)
        row1.addWidget(btn_browse)
        box.addLayout(row1)

        # 目标语言
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("目标语言:"))
        self.target_lang_combo = ComboBox()
        self.target_lang_combo.addItems(["简体中文", "繁体中文", "英语", "日语", "韩语"])
        self.target_lang_combo.setCurrentText("简体中文")
        lang_row.addWidget(self.target_lang_combo, 1)
        box.addLayout(lang_row)

        # 备份开关
        backup_row = QHBoxLayout()
        self.backup_switch = SwitchButton("自动备份 .bak")
        self.backup_switch.setChecked(True)
        backup_row.addWidget(self.backup_switch)
        self.backup_external_switch = SwitchButton("备份源码到外部")
        self.backup_external_switch.checkedChanged.connect(self._on_backup_external_changed)
        backup_row.addWidget(self.backup_external_switch)
        backup_row.addStretch(1)
        box.addLayout(backup_row)

        # 备份目录
        backup_row2 = QHBoxLayout()
        self.backup_external_edit = LineEdit()
        self.backup_external_edit.setPlaceholderText("选择备份目录")
        self.backup_external_edit.setVisible(False)
        self.btn_browse_backup = PushButton("浏览", icon=FluentIcon.FOLDER)
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
        self.btn_start = PrimaryPushButton("开始翻译", icon=FluentIcon.PLAY)
        self.btn_start.clicked.connect(self._start_translation)
        self.btn_stop = PushButton("停止", icon=FluentIcon.CANCEL)
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

        self.status_label = CaptionLabel("等待操作…")
        box.addWidget(self.status_label)

        return card

    # ------------------------------------------------------------------ actions
    def _browse_game_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "选择 game 目录", "")
        if directory:
            self.game_dir_edit.setText(directory)

    def _on_backup_external_changed(self, checked: bool):
        self.backup_external_edit.setVisible(checked)
        self.btn_browse_backup.setVisible(checked)

    def _browse_backup_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "选择备份目录", "")
        if directory:
            self.backup_external_edit.setText(directory)

    def _start_translation(self):
        game_dir = self.game_dir_edit.text().strip()
        if not game_dir:
            InfoBar.warning("提示", "请选择 game 目录", parent=self)
            return
        if not Path(game_dir).exists():
            InfoBar.error("错误", "目录不存在", parent=self)
            return

        backup = self.backup_switch.isChecked()
        backup_root = None
        if self.backup_external_switch.isChecked():
            backup_root = self.backup_external_edit.text().strip()
            if not backup_root:
                InfoBar.warning("提示", "请选择备份目录", parent=self)
                return

        try:
            config = Config().load()
            config.input_folder = str(Path(game_dir))
            config.output_folder = str(Path(game_dir))
            lang_map = {
                "简体中文": "ZH",
                "繁体中文": "ZH",
                "英语": "EN",
                "日语": "JA",
                "韩语": "KO",
            }
            tgt = lang_map.get(self.target_lang_combo.currentText())
            if tgt:
                config.target_language = tgt
            config.renpy_backup_original = bool(backup)
        except Exception as exc:
            self.logger.error(f"加载/写入配置失败: {exc}")
            InfoBar.error("错误", f"加载配置失败: {exc}", parent=self)
            return

        # 简单备份（外部目录或本地 .bak）
        if backup or backup_root:
            self._backup_sources(Path(game_dir), backup_root)

        # 更新 UI
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("已委托 Engine 翻译，请稍候...")

        # 触发 Engine 翻译
        self.emit(Base.Event.TRANSLATION_START, {
            "config": config,
            "status": Base.TranslationStatus.UNTRANSLATED,
        })
        InfoBar.success("已开始", "已切换到统一翻译流程，进度见日志/进度条。", parent=self)

    def _stop_translation(self):
        self.emit(Base.Event.TRANSLATION_STOP, {})
        self.btn_stop.setEnabled(False)
        self.status_label.setText("正在请求停止...")

    # ------------------------------------------------------------------ engine callbacks
    def _on_engine_update(self, event, extras):
        if not isinstance(extras, dict):
            return
        total = extras.get("total_line", 0) or 0
        current = extras.get("line", 0) or 0
        if total > 0:
            percent = int(max(0.0, min(1.0, current / total)) * 100)
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(percent)
            self.status_label.setText(f"翻译中… {current}/{total}")
        else:
            self.status_label.setText("翻译中…")

    def _on_engine_done(self, event, data):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("翻译完成")
        InfoBar.success("完成", "统一翻译流程已完成", parent=self)

    def _on_engine_stop(self, event, data):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.status_label.setText("已停止")
        self.progress_bar.setVisible(False)

    # ------------------------------------------------------------------ helpers
    def _backup_sources(self, game_dir: Path, backup_root: Optional[str]) -> None:
        """简单备份 .rpy 源文件"""
        try:
            candidates = list(Path(game_dir).rglob("*.rpy"))
            for path in candidates:
                if backup_root:
                    dest = Path(backup_root) / path.relative_to(game_dir)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(path.read_bytes())
                else:
                    bak = path.with_suffix(path.suffix + ".bak")
                    if not bak.exists():
                        bak.write_bytes(path.read_bytes())
        except Exception as exc:
            self.logger.warning(f"备份源码失败: {exc}")
