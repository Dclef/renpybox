"""游戏模组注入页面。"""

import threading

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
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
from module.Tool.ModInjector import ModInjector
from widget.ThemeHelper import mark_toolbox_scroll_area, mark_toolbox_widget


class GameModPage(Base, QWidget):
    operation_done = pyqtSignal(str, str, str)
    operation_failed = pyqtSignal(str, str, str)

    def __init__(self, object_name: str, parent=None):
        Base.__init__(self)
        QWidget.__init__(self, parent)
        self.setObjectName(object_name)
        mark_toolbox_widget(self)

        self.injector = ModInjector()
        self._running = False
        self._init_ui()
        self.operation_done.connect(self._on_operation_done)
        self.operation_failed.connect(self._on_operation_failed)
        self._refresh_status()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(18)
        root.addWidget(TitleLabel("游戏模组注入", self))

        scroll = SingleDirectionScrollArea(orient=Qt.Orientation.Vertical, parent=self)
        scroll.setWidgetResizable(True)
        scroll.enableTransparentBackground()
        mark_toolbox_scroll_area(scroll)

        content = QWidget(scroll)
        mark_toolbox_widget(content, "toolboxScroll")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self._build_intro_card())
        layout.addWidget(self._build_game_dir_card())

        urm_card, self.urm_install_button, self.urm_uninstall_button = (
            self._build_mod_card(
                "urm",
                "修改器（0x52-URM 2.6.2 汉化版）",
                "将修改器 RPA 注入 game/。注入后按模组自带快捷键唤出；"
                "若出现 API.rpyc 错误，目前没有压缩包版兜底。",
            )
        )
        layout.addWidget(urm_card)

        quick_menu_card, self.quick_menu_install_button, self.quick_menu_uninstall_button = (
            self._build_mod_card(
                "quick_menu",
                "底部按钮栏（独木桥模组 6.27 版）",
                "会隐藏游戏原本的 quick_menu，并整体覆盖 config.overlay_screens，"
                "可能与其他模组的按钮冲突。",
            )
        )
        layout.addWidget(quick_menu_card)
        layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self._buttons = (
            self.browse_button,
            self.urm_install_button,
            self.urm_uninstall_button,
            self.quick_menu_install_button,
            self.quick_menu_uninstall_button,
        )

    def _build_intro_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(StrongBodyLabel("使用说明", self))

        copyright_label = CaptionLabel(
            "本页模组均为第三方作品，版权归各自作者（0x52、独木桥），用完建议卸载。",
            self,
        )
        copyright_label.setWordWrap(True)
        layout.addWidget(copyright_label)

        platform_label = CaptionLabel("仅支持 PC / 模拟器版，不支持安卓版。", self)
        platform_label.setWordWrap(True)
        layout.addWidget(platform_label)
        return card

    def _build_game_dir_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(StrongBodyLabel("游戏目录", self))

        path_row = QHBoxLayout()
        self.game_dir_edit = LineEdit(self)
        self.game_dir_edit.setPlaceholderText("选择项目根目录或 game 目录")
        self.game_dir_edit.editingFinished.connect(self._refresh_status)
        self.browse_button = PushButton("浏览", icon=FluentIcon.FOLDER, parent=self)
        self.browse_button.clicked.connect(self._browse_game_dir)
        path_row.addWidget(self.game_dir_edit, 1)
        path_row.addWidget(self.browse_button)
        layout.addLayout(path_row)

        self.urm_status_label = CaptionLabel("修改器：未选择游戏目录", self)
        self.quick_menu_status_label = CaptionLabel("底部按钮栏：未选择游戏目录", self)
        layout.addWidget(self.urm_status_label)
        layout.addWidget(self.quick_menu_status_label)
        return card

    def _build_mod_card(
        self,
        key: str,
        title: str,
        description: str,
    ) -> tuple[CardWidget, PrimaryPushButton, PushButton]:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(StrongBodyLabel(title, self))

        description_label = CaptionLabel(description, self)
        description_label.setWordWrap(True)
        layout.addWidget(description_label)

        button_row = QHBoxLayout()
        install_button = PrimaryPushButton(
            "安装", icon=FluentIcon.DOWNLOAD, parent=self
        )
        uninstall_button = PushButton("卸载", icon=FluentIcon.DELETE, parent=self)
        install_button.clicked.connect(
            lambda: self._start_operation("install", key)
        )
        uninstall_button.clicked.connect(
            lambda: self._start_operation("uninstall", key)
        )
        button_row.addWidget(install_button)
        button_row.addWidget(uninstall_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        return card, install_button, uninstall_button

    def _browse_game_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "选择游戏目录",
            self.game_dir_edit.text(),
        )
        if path:
            self.game_dir_edit.setText(path)
            self._refresh_status()

    def _refresh_status(self) -> None:
        game_dir = self.game_dir_edit.text().strip()
        if not game_dir:
            self.urm_status_label.setText("修改器：未选择游戏目录")
            self.quick_menu_status_label.setText("底部按钮栏：未选择游戏目录")
            return

        status = self.injector.status(game_dir)
        self.urm_status_label.setText(
            f"修改器：{'已安装' if status['urm'] else '未安装'}"
        )
        self.quick_menu_status_label.setText(
            f"底部按钮栏：{'已安装' if status['quick_menu'] else '未安装'}"
        )

    def _start_operation(self, action: str, key: str) -> None:
        if self._running:
            return

        game_dir = self.game_dir_edit.text().strip()
        if not game_dir:
            InfoBar.warning(
                "未选择游戏目录",
                "请选择项目根目录或 game 目录",
                parent=self,
            )
            return

        self._set_running(True)

        def task() -> None:
            try:
                operation = (
                    self.injector.install
                    if action == "install"
                    else self.injector.uninstall
                )
                success, message = operation(game_dir, key)
                signal = self.operation_done if success else self.operation_failed
                signal.emit(action, key, message)
            except Exception as exc:
                LogManager.get().error(f"游戏模组操作失败：{exc}")
                self.operation_failed.emit(action, key, str(exc))

        threading.Thread(target=task, daemon=True).start()

    def _set_running(self, running: bool) -> None:
        self._running = running
        for button in self._buttons:
            button.setEnabled(not running)

    def _on_operation_done(self, action: str, key: str, message: str) -> None:
        del key
        self._set_running(False)
        self._refresh_status()
        InfoBar.success(
            "安装完成" if action == "install" else "卸载完成",
            message,
            parent=self,
        )

    def _on_operation_failed(self, action: str, key: str, message: str) -> None:
        del key
        self._set_running(False)
        self._refresh_status()
        InfoBar.error(
            "安装失败" if action == "install" else "卸载失败",
            message,
            parent=self,
        )
