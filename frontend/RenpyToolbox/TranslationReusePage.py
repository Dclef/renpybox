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
from module.Localizer.Localizer import Localizer
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
        root.addWidget(TitleLabel(Localizer.localize("更新翻译复用", "Reuse Updated Translations"), self))

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
        strings = Localizer.get()
        layout.addWidget(StrongBodyLabel(Localizer.localize("翻译目录", "Translation Folders"), self))

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel(Localizer.localize("旧译文:", "Previous Translation:")))
        self.source_edit = LineEdit(self)
        self.source_edit.setPlaceholderText(Localizer.localize("旧版本 game/tl/<语言> 目录", "Previous game/tl/<language> folder"))
        source_row.addWidget(self.source_edit, 1)
        source_browse = PushButton(strings.browse, icon=FluentIcon.FOLDER, parent=self)
        source_browse.setToolTip(Localizer.localize("选择旧译文目录", "Select Previous Translation Folder"))
        source_browse.clicked.connect(self._browse_source)
        source_row.addWidget(source_browse)
        layout.addLayout(source_row)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel(Localizer.localize("新译文:", "New Translation:")))
        self.target_edit = LineEdit(self)
        self.target_edit.setPlaceholderText(Localizer.localize("新版本 game/tl/<语言> 目录", "New game/tl/<language> folder"))
        target_row.addWidget(self.target_edit, 1)
        target_browse = PushButton(strings.browse, icon=FluentIcon.FOLDER, parent=self)
        target_browse.setToolTip(Localizer.localize("选择目标译文目录", "Select Target Translation Folder"))
        target_browse.clicked.connect(self._browse_target)
        target_row.addWidget(target_browse)
        layout.addLayout(target_row)

        return card

    def _build_action_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(StrongBodyLabel(Localizer.localize("复用结果", "Reuse Result"), self))

        self.summary_label = CaptionLabel(Localizer.localize("尚未预览", "Not previewed"), self)
        self.summary_label.setWordWrap(True)
        self.summary_label.setMinimumHeight(42)
        layout.addWidget(self.summary_label)

        button_row = QHBoxLayout()
        self.preview_button = PushButton(Localizer.localize("预览", "Preview"), icon=FluentIcon.SEARCH, parent=self)
        self.preview_button.clicked.connect(lambda: self._start_operation("preview"))
        self.execute_button = PrimaryPushButton(Localizer.localize("执行复用", "Reuse Translations"), icon=FluentIcon.ACCEPT, parent=self)
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
        path = QFileDialog.getExistingDirectory(
            self, Localizer.localize("选择旧译文目录", "Select Previous Translation Folder"), self.source_edit.text()
        )
        if path:
            self.source_edit.setText(path)

    def _browse_target(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, Localizer.localize("选择目标译文目录", "Select Target Translation Folder"), self.target_edit.text()
        )
        if path:
            self.target_edit.setText(path)

    def _start_operation(self, mode: str) -> None:
        if self._running:
            return
        source = self.source_edit.text().strip()
        target = self.target_edit.text().strip()
        if not source or not target:
            InfoBar.warning(
                Localizer.localize("目录不完整", "Missing Folders"),
                Localizer.localize("请选择旧译文和目标译文目录", "Select both the previous and target translation folders."),
                parent=self,
            )
            return

        self._set_running(True)
        self.summary_label.setText(
            Localizer.localize("正在分析...", "Analyzing...")
            if mode == "preview"
            else Localizer.localize("正在复用译文...", "Reusing translations...")
        )

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
        summary = Localizer.localize(
            "可复用 {reusable} 条，冲突 {conflicts} 条，已一致 {existing} 条，无法匹配 {unmatched} 条",
            "Reusable: {reusable}; conflicts: {conflicts}; already matched: {existing}; unmatched: {unmatched}",
        ).format(
            reusable=result.reusable_entries,
            conflicts=result.conflicts,
            existing=result.already_reused,
            unmatched=result.unmatched_entries,
        )
        if result.applied_entries:
            summary = Localizer.localize("已写入 {count} 条。", "Applied {count}. ").format(
                count=result.applied_entries
            ) + summary
        if result.backup_path is not None:
            summary += Localizer.localize("\n备份: {path}", "\nBackup: {path}").format(path=result.backup_path)
        return summary

    def _on_operation_done(self, mode: str, result: TranslationReuseResult) -> None:
        self._set_running(False)
        self.summary_label.setText(self._format_result(result))
        if mode == "execute":
            InfoBar.success(
                Localizer.localize("复用完成", "Reuse Complete"),
                Localizer.localize("已写入 {count} 条译文", "Applied {count} translation(s).").format(
                    count=result.applied_entries
                ),
                parent=self,
            )

    def _on_operation_failed(self, mode: str, message: str) -> None:
        del mode
        self._set_running(False)
        self.summary_label.setText(Localizer.localize("操作失败", "Operation failed"))
        LogManager.get().error(f"更新翻译复用失败: {message}")
        InfoBar.error(
            Localizer.localize("复用失败", "Reuse Failed"),
            Localizer.localize(
                "操作失败，请查看日志了解详情。",
                "The operation failed. Check the logs for details.",
            ),
            parent=self,
        )
