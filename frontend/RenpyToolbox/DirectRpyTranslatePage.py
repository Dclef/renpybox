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
        title = TitleLabel("📄 直接翻译 tl/.rpy（Engine 流程）")
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

        box.addWidget(SubtitleLabel("📁 路径设置"))

        # 游戏/项目路径
        row_game = QHBoxLayout()
        row_game.addWidget(BodyLabel("游戏文件或目录:"))
        self.game_file_edit = LineEdit()
        self.game_file_edit.setPlaceholderText("选择游戏 exe 或项目目录")
        btn_browse_game = PushButton("浏览", icon=FluentIcon.FOLDER)
        btn_browse_game.clicked.connect(self._browse_game_file)
        row_game.addWidget(self.game_file_edit, 1)
        row_game.addWidget(btn_browse_game)
        box.addLayout(row_game)

        # tl 目录
        row_tl = QHBoxLayout()
        row_tl.addWidget(BodyLabel("tl 目录:"))
        self.tl_dir_edit = LineEdit()
        self.tl_dir_edit.setPlaceholderText("可选，默认尝试 game/tl/<语言>")
        btn_browse_tl = PushButton("浏览", icon=FluentIcon.FOLDER)
        btn_browse_tl.clicked.connect(self._browse_tl_dir)
        row_tl.addWidget(self.tl_dir_edit, 1)
        row_tl.addWidget(btn_browse_tl)
        box.addLayout(row_tl)

        # tl 名称
        row_name = QHBoxLayout()
        row_name.addWidget(BodyLabel("tl 语言目录名:"))
        self.tl_edit = LineEdit()
        self.tl_edit.setText("chinese")
        row_name.addWidget(self.tl_edit, 1)
        box.addLayout(row_name)

        # 目标语言 + 备份
        row_lang = QHBoxLayout()
        row_lang.addWidget(BodyLabel("目标语言:"))
        self.target_lang_combo = ComboBox()
        self.target_lang_combo.addItems(["简体中文", "繁体中文", "英语", "日语", "韩语"])
        self.target_lang_combo.setCurrentText("简体中文")
        row_lang.addWidget(self.target_lang_combo, 1)

        self.backup_switch = SwitchButton("写入前自动备份 .bak")
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
    def _browse_game_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择游戏 exe 或目录", "", "Executable (*.exe);;All Files (*)")
        if path:
            self.game_file_edit.setText(path)

    def _browse_tl_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择 tl 目录", "")
        if path:
            self.tl_dir_edit.setText(path)

    def _start_translation(self) -> None:
        game_path = self.game_file_edit.text().strip()
        tl_dir_text = self.tl_dir_edit.text().strip()
        tl_name = self.tl_edit.text().strip() or "chinese"

        try:
            tl_dir: Optional[Path] = None
            if tl_dir_text:
                tl_dir = Path(tl_dir_text)
                if not tl_dir.exists():
                    raise RuntimeError(f"tl 目录不存在: {tl_dir}")
            else:
                if not game_path:
                    raise RuntimeError("请先选择游戏文件或 tl 目录")
                game = Path(game_path)
                project_dir = game.parent if game.is_file() else game
                tl_dir = SimpleRpyExtractor.find_tl_directory(project_dir, tl_name)
                if tl_dir is None:
                    raise RuntimeError(f"未找到 tl/{tl_name} 目录，请先执行抽取或指定 tl 目录")

            config = Config().load()
            config.input_folder = str(tl_dir)
            config.output_folder = str(tl_dir)
            config.renpy_backup_original = self.backup_switch.isChecked()

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

            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.progress_bar.setValue(0)
            self.status_label.setText("已委托 Engine 翻译，请稍候...")

            self.emit(Base.Event.TRANSLATION_START, {
                "config": config,
                "status": Base.TranslationStatus.UNTRANSLATED,
            })
            InfoBar.success("已开始", "已切换到统一 Engine 流程，进度见下方。", parent=self)
        except Exception as exc:
            self.logger.error(f"启动翻译失败: {exc}")
            InfoBar.error("错误", str(exc), parent=self)

    def _stop_translation(self) -> None:
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
            ratio = max(0.0, min(1.0, current / total))
            self.progress_bar.setValue(int(ratio * 100))
        self.status_label.setText(f"翻译中… {current}/{total}")

    def _on_engine_done(self, event, data):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setValue(100)
        self.status_label.setText("翻译完成")
        InfoBar.success("完成", "Engine 翻译完成", parent=self)

    def _on_engine_stop(self, event, data):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("已停止")
