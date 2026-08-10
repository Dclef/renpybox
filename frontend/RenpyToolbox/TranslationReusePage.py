"""游戏更新后的旧译文复用页面。"""

import threading
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel,
    CardWidget,
    FluentIcon,
    InfoBar,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SingleDirectionScrollArea,
    StrongBodyLabel,
    TitleLabel,
)

from base.Base import Base
from base.LogManager import LogManager
from module.Config import Config
from module.Extract.UnifiedExtractor import TranslationReuseResult, UnifiedExtractor
from widget.ThemeHelper import mark_toolbox_scroll_area, mark_toolbox_widget


class TranslationReusePage(Base, QWidget):
    operation_done = pyqtSignal(str, object)
    operation_failed = pyqtSignal(str, str)

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)

        self.extractor = UnifiedExtractor()
        self._running = False
        self._init_ui()
        self._load_configured_target()
        self.operation_done.connect(self._on_operation_done)
        self.operation_failed.connect(self._on_operation_failed)

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(18)
        root.addWidget(TitleLabel("更新翻译复用", self))

        scroll = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical, parent=self)
        scroll.setWidgetResizable(True)
        scroll.enableTransparentBackground()
        mark_toolbox_scroll_area(scroll)

        content = QWidget(scroll)
        mark_toolbox_widget(content, "toolboxScroll")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self._build_path_card())
        layout.addWidget(self._build_action_card())
        layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def _build_path_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(StrongBodyLabel("翻译目录", self))

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("旧译文:"))
        self.source_edit = LineEdit(self)
        self.source_edit.setPlaceholderText("旧版本 game/tl/<语言> 目录")
        source_row.addWidget(self.source_edit, 1)
        source_browse = PushButton("浏览", icon=FluentIcon.FOLDER, parent=self)
        source_browse.setToolTip("选择旧译文目录")
        source_browse.clicked.connect(self._browse_source)
        source_row.addWidget(source_browse)
        layout.addLayout(source_row)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("新译文:"))
        self.target_edit = LineEdit(self)
        self.target_edit.setPlaceholderText("新版本 game/tl/<语言> 目录")
        target_row.addWidget(self.target_edit, 1)
        target_browse = PushButton("浏览", icon=FluentIcon.FOLDER, parent=self)
        target_browse.setToolTip("选择目标译文目录")
        target_browse.clicked.connect(self._browse_target)
        target_row.addWidget(target_browse)
        layout.addLayout(target_row)

        return card

    def _build_action_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(StrongBodyLabel("复用结果", self))

        self.summary_label = CaptionLabel("尚未预览", self)
        self.summary_label.setWordWrap(True)
        self.summary_label.setMinimumHeight(42)
        layout.addWidget(self.summary_label)

        button_row = QHBoxLayout()
        self.preview_button = PushButton("预览", icon=FluentIcon.SEARCH, parent=self)
        self.preview_button.clicked.connect(lambda: self._start_operation("preview"))
        self.execute_button = PrimaryPushButton("执行复用", icon=FluentIcon.ACCEPT, parent=self)
        self.execute_button.clicked.connect(lambda: self._start_operation("execute"))
        button_row.addWidget(self.preview_button)
        button_row.addWidget(self.execute_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        return card

    def _load_configured_target(self) -> None:
        config = Config().load()
        configured = str(getattr(config, "renpy_tl_folder", "") or "").strip()
        if configured and Path(configured).is_dir():
            self.target_edit.setText(configured)

    def _browse_source(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择旧译文目录", self.source_edit.text())
        if path:
            self.source_edit.setText(path)

    def _browse_target(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择目标译文目录", self.target_edit.text())
        if path:
            self.target_edit.setText(path)

    def _start_operation(self, mode: str) -> None:
        if self._running:
            return
        source = self.source_edit.text().strip()
        target = self.target_edit.text().strip()
        if not source or not target:
            InfoBar.warning("目录不完整", "请选择旧译文和目标译文目录", parent=self)
            return

        self._set_running(True)
        self.summary_label.setText("正在分析..." if mode == "preview" else "正在复用译文...")

        def task() -> None:
            try:
                if mode == "preview":
                    result = self.extractor.preview_translation_reuse(source, target)
                else:
                    result = self.extractor.reuse_translations(source, target)
                self.operation_done.emit(mode, result)
            except Exception as exc:
                LogManager.get().error(f"更新翻译复用失败: {exc}")
                self.operation_failed.emit(mode, str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _set_running(self, running: bool) -> None:
        self._running = running
        self.preview_button.setEnabled(not running)
        self.execute_button.setEnabled(not running)

    def _format_result(self, result: TranslationReuseResult) -> str:
        summary = (
            f"可复用 {result.reusable_entries} 条，冲突 {result.conflicts} 条，"
            f"已一致 {result.already_reused} 条，无法匹配 {result.unmatched_entries} 条"
        )
        if result.applied_entries:
            summary = f"已写入 {result.applied_entries} 条。" + summary
        if result.backup_path is not None:
            summary += f"\n备份: {result.backup_path}"
        return summary

    def _on_operation_done(self, mode: str, result: TranslationReuseResult) -> None:
        self._set_running(False)
        self.summary_label.setText(self._format_result(result))
        if mode == "execute":
            InfoBar.success("复用完成", f"已写入 {result.applied_entries} 条译文", parent=self)

    def _on_operation_failed(self, mode: str, message: str) -> None:
        del mode
        self._set_running(False)
        self.summary_label.setText("操作失败")
        InfoBar.error("复用失败", message, parent=self)
