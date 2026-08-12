"""游戏模组注入页面。"""

import threading

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget
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
from module.Localizer.Localizer import Localizer
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
        root.addWidget(TitleLabel(Localizer.localize("游戏模组注入", "Game Mod Injection"), self))

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

        gallery_card, self.gallery_install_button, self.gallery_uninstall_button = (
            self._build_mod_card(
                "gallery_unlock",
                Localizer.localize(
                    "解锁画廊（ZLZK 通用画廊解锁器改写版）",
                    "Gallery Unlocker (adapted from the ZLZK universal gallery unlocker)",
                ),
                Localizer.localize(
                    "安装后游戏右上角会显示“MOD”按钮，可开启全部画廊，或恢复游戏原本的画廊进度；"
                    "F9 打开面板，F10 直接切换画廊状态。",
                    "Adds a MOD button at the top right of the game. Use it to unlock the full gallery or restore the original progress; press F9 to open the panel or F10 to toggle the gallery.",
                ),
            )
        )
        layout.addWidget(gallery_card)

        urm_card, self.urm_install_button, self.urm_uninstall_button = (
            self._build_mod_card(
                "urm",
                Localizer.localize("修改器（0x52-URM 2.6.2 汉化版）", "Utility Mod (0x52-URM 2.6.2 Chinese edition)"),
                Localizer.localize(
                    "将修改器和游戏内“修改器”按钮注入 game/，也可按 Alt+M 唤出；"
                    "若出现 API.rpyc 错误，目前没有压缩包版兜底。",
                    "Injects the utility and an in-game button into game/. Press Alt+M to open it. There is currently no archive fallback for API.rpyc errors.",
                ),
            )
        )
        layout.addWidget(urm_card)

        (
            simple_modifier_card,
            self.simple_modifier_install_button,
            self.simple_modifier_uninstall_button,
        ) = (
            self._build_mod_card(
                "simple_modifier",
                Localizer.localize("内置修改器（RenpyBox）", "Built-in Utility (RenpyBox)"),
                Localizer.localize(
                    "提供对话框、选项框和快捷菜单调整；可单独安装，和画廊解锁器同时安装时会在游戏内 MOD 面板中显示。",
                    "Adjusts dialogue boxes, choice screens, and the quick menu. It can be installed alone or shown in the in-game MOD panel alongside the gallery unlocker.",
                ),
            )
        )
        layout.addWidget(simple_modifier_card)

        layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self._buttons = (
            self.browse_button,
            self.gallery_install_button,
            self.gallery_uninstall_button,
            self.urm_install_button,
            self.urm_uninstall_button,
            self.simple_modifier_install_button,
            self.simple_modifier_uninstall_button,
            self.legacy_dumuqiao_cleanup_button,
        )

    def _build_intro_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(StrongBodyLabel(Localizer.localize("使用说明", "Instructions"), self))

        copyright_label = CaptionLabel(
            Localizer.localize(
                "画廊解锁器由 ZLZK 提供，修改器由 0x52 提供；游戏内 MOD 面板由 RenpyBox 提供。",
                "The gallery unlocker is provided by ZLZK, the utility by 0x52, and the in-game MOD panel by RenpyBox.",
            ),
            self,
        )
        copyright_label.setWordWrap(True)
        layout.addWidget(copyright_label)

        platform_label = CaptionLabel(
            Localizer.localize(
                "仅支持 PC / 模拟器版，不支持安卓版。",
                "Supports PC and emulator editions only; Android is not supported.",
            ),
            self,
        )
        platform_label.setWordWrap(True)
        layout.addWidget(platform_label)
        return card

    def _build_game_dir_card(self) -> CardWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(StrongBodyLabel(Localizer.localize("游戏目录", "Game Folder"), self))

        path_row = QHBoxLayout()
        self.game_dir_edit = LineEdit(self)
        self.game_dir_edit.setPlaceholderText(Localizer.localize("选择项目根目录或 game 目录", "Select the project root or game folder"))
        self.game_dir_edit.editingFinished.connect(self._refresh_status)
        self.browse_button = PushButton(Localizer.get().browse, icon=FluentIcon.FOLDER, parent=self)
        self.browse_button.clicked.connect(self._browse_game_dir)
        path_row.addWidget(self.game_dir_edit, 1)
        path_row.addWidget(self.browse_button)
        layout.addLayout(path_row)

        self.gallery_status_label = CaptionLabel(Localizer.localize("解锁画廊：未选择游戏目录", "Gallery unlocker: no game folder selected"), self)
        self.urm_status_label = CaptionLabel(Localizer.localize("修改器：未选择游戏目录", "Utility mod: no game folder selected"), self)
        self.simple_modifier_status_label = CaptionLabel(
            Localizer.localize("内置修改器：未选择游戏目录", "Built-in utility: no game folder selected"), self
        )
        self.legacy_dumuqiao_label = CaptionLabel("", self)
        self.legacy_dumuqiao_cleanup_button = PushButton(
            Localizer.localize("删除旧版独木桥", "Remove Legacy Dumuqiao"), icon=FluentIcon.DELETE, parent=self
        )
        self.legacy_dumuqiao_cleanup_button.clicked.connect(
            self._confirm_legacy_dumuqiao_cleanup
        )
        self.legacy_dumuqiao_label.hide()
        self.legacy_dumuqiao_cleanup_button.hide()
        layout.addWidget(self.gallery_status_label)
        layout.addWidget(self.urm_status_label)
        layout.addWidget(self.simple_modifier_status_label)
        layout.addWidget(self.legacy_dumuqiao_label)
        layout.addWidget(self.legacy_dumuqiao_cleanup_button)
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
            Localizer.localize("安装", "Install"), icon=FluentIcon.DOWNLOAD, parent=self
        )
        uninstall_button = PushButton(Localizer.localize("卸载", "Uninstall"), icon=FluentIcon.DELETE, parent=self)
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
            Localizer.localize("选择游戏目录", "Select Game Folder"),
            self.game_dir_edit.text(),
        )
        if path:
            self.game_dir_edit.setText(path)
            self._refresh_status()

    def _refresh_status(self) -> None:
        game_dir = self.game_dir_edit.text().strip()
        if not game_dir:
            self.gallery_status_label.setText(Localizer.localize("解锁画廊：未选择游戏目录", "Gallery unlocker: no game folder selected"))
            self.urm_status_label.setText(Localizer.localize("修改器：未选择游戏目录", "Utility mod: no game folder selected"))
            self.simple_modifier_status_label.setText(
                Localizer.localize("内置修改器：未选择游戏目录", "Built-in utility: no game folder selected")
            )
            self.legacy_dumuqiao_label.hide()
            self.legacy_dumuqiao_cleanup_button.hide()
            return

        status = self.injector.status(game_dir)
        self.gallery_status_label.setText(
            Localizer.localize("解锁画廊：{status}", "Gallery unlocker: {status}").format(
                status=Localizer.localize("已安装", "Installed") if status["gallery_unlock"] else Localizer.localize("未安装", "Not installed")
            )
        )
        self.urm_status_label.setText(
            Localizer.localize("修改器：{status}", "Utility mod: {status}").format(
                status=Localizer.localize("已安装", "Installed") if status["urm"] else Localizer.localize("未安装", "Not installed")
            )
        )
        self.simple_modifier_status_label.setText(
            Localizer.localize("内置修改器：{status}", "Built-in utility: {status}").format(
                status=Localizer.localize("已安装", "Installed") if status["simple_modifier"] else Localizer.localize("未安装", "Not installed")
            )
        )
        has_legacy_dumuqiao = self.injector.has_legacy_dumuqiao(game_dir)
        self.legacy_dumuqiao_label.setVisible(has_legacy_dumuqiao)
        self.legacy_dumuqiao_cleanup_button.setVisible(has_legacy_dumuqiao)
        if has_legacy_dumuqiao:
            self.legacy_dumuqiao_label.setText(
                Localizer.localize("检测到旧版独木桥，删除后重启游戏，避免覆盖原游戏菜单。", "A legacy Dumuqiao install was found. Remove it and restart the game to avoid replacing the original menu.")
            )

    def _confirm_legacy_dumuqiao_cleanup(self) -> None:
        result = QMessageBox.warning(
            self,
            Localizer.localize("删除旧版独木桥", "Remove Legacy Dumuqiao"),
            Localizer.localize(
                "将永久删除 game/dumuqiao.rpy 与 game/dumuqiao.rpyc。"
                "不会删除 .bak 或其他用户脚本。是否继续？",
                "This permanently deletes game/dumuqiao.rpy and game/dumuqiao.rpyc. Backups and other user scripts are not removed. Continue?",
            ),
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if result == QMessageBox.Yes:
            self._start_operation("cleanup_legacy", "legacy_dumuqiao")

    def _start_operation(self, action: str, key: str) -> None:
        if self._running:
            return

        game_dir = self.game_dir_edit.text().strip()
        if not game_dir:
            InfoBar.warning(
                Localizer.localize("未选择游戏目录", "No Game Folder Selected"),
                Localizer.localize("请选择项目根目录或 game 目录", "Select the project root or game folder."),
                parent=self,
            )
            return

        self._set_running(True)

        def task() -> None:
            try:
                if action == "cleanup_legacy":
                    success, message = self.injector.remove_legacy_dumuqiao(game_dir)
                elif action == "install":
                    success, message = self.injector.install(game_dir, key)
                else:
                    success, message = self.injector.uninstall(game_dir, key)
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
        del key, message
        self._set_running(False)
        self._refresh_status()
        InfoBar.success(
            (
                Localizer.localize("安装完成", "Installation Complete")
                if action == "install"
                else Localizer.localize("清理完成", "Cleanup Complete")
                if action == "cleanup_legacy"
                else Localizer.localize("卸载完成", "Uninstallation Complete")
            ),
            (
                Localizer.localize("模组安装成功", "The mod was installed successfully.")
                if action == "install"
                else Localizer.localize(
                    "旧版独木桥文件已删除",
                    "The legacy Dumuqiao files were removed.",
                )
                if action == "cleanup_legacy"
                else Localizer.localize(
                    "模组卸载成功", "The mod was uninstalled successfully."
                )
            ),
            parent=self,
        )

    def _on_operation_failed(self, action: str, key: str, message: str) -> None:
        del key, message
        self._set_running(False)
        self._refresh_status()
        InfoBar.error(
            (
                Localizer.localize("安装失败", "Installation Failed")
                if action == "install"
                else Localizer.localize("清理失败", "Cleanup Failed")
                if action == "cleanup_legacy"
                else Localizer.localize("卸载失败", "Uninstallation Failed")
            ),
            Localizer.localize(
                "操作失败，请查看日志了解详情。",
                "The operation failed. Check the logs for details.",
            ),
            parent=self,
        )
