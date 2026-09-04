import os
import signal

from PyQt5.QtCore import QTimer
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QLayout
from PyQt5.QtWidgets import QSizePolicy
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import BodyLabel
from qfluentwidgets import CaptionLabel
from qfluentwidgets import FluentIcon
from qfluentwidgets import IconWidget
from qfluentwidgets import MessageBox
from qfluentwidgets import FluentWindow
from qfluentwidgets import PrimaryPushButton
from qfluentwidgets import PushButton
from qfluentwidgets import StrongBodyLabel
from qfluentwidgets import TitleLabel
from qfluentwidgets import SwitchButton
from qfluentwidgets import SingleDirectionScrollArea

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from base.Version import Version
from base.VersionManager import VersionManager
from frontend.Setting.ChangelogDialog import ChangelogDialog
from frontend.Setting.UpdateDetailsDialog import UpdateDetailsDialog
from module.Config import Config
from module.Engine.Engine import Engine
from module.Localizer.Localizer import Localizer
from widget.ComboBoxCard import ComboBoxCard
from widget.DownloadProgressBar import DownloadProgressBar
from widget.GroupCard import GroupCard
from widget.LineEditCard import LineEditCard
from widget.SwitchButtonCard import SwitchButtonCard
from widget.ThemeHelper import get_theme_accent_color, mark_app_page


class AppSettingsPage(QWidget, Base):

    def __init__(self, text: str, window: FluentWindow) -> None:
        super().__init__(window)
        self.setObjectName(text.replace(" ", "-"))
        mark_app_page(self)
        self._window = window
        self._checking_update = False
        self._cancelling_update = False

        # 载入并保存默认配置
        config = Config().load().save()

        # 设置主容器
        self.root = QVBoxLayout(self)
        self.root.setSpacing(8)
        self.root.setContentsMargins(24, 24, 24, 24) # 左、上、右、下

        header = QWidget(self)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 4)
        header_layout.setSpacing(2)
        header_layout.addWidget(TitleLabel(Localizer.get().app_settings_page, header))
        header_layout.addWidget(
            CaptionLabel(Localizer.get().app_settings_page_header_description, header)
        )
        self.root.addWidget(header)

        # 创建滚动区域的内容容器
        scroll_area_vbox_widget = QWidget()
        scroll_area_vbox = QVBoxLayout(scroll_area_vbox_widget)
        scroll_area_vbox.setContentsMargins(0, 0, 0, 0)

        # 创建滚动区域
        scroll_area = SingleDirectionScrollArea(orient = Qt.Orientation.Vertical)
        scroll_area.setWidget(scroll_area_vbox_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.enableTransparentBackground()

        # 将滚动区域添加到父布局
        self.root.addWidget(scroll_area)

        # 添加控件
        self.add_widget_language(scroll_area_vbox, config)
        self.add_widget_about_updates(scroll_area_vbox)
        self.add_widget_startup_sound(scroll_area_vbox, config, window)
        self.add_widget_expert_mode(scroll_area_vbox, config, window)
        self.add_widget_font_hinting(scroll_area_vbox, config, window)
        self.add_widget_scale_factor(scroll_area_vbox, config, window)
        self.add_widget_proxy(scroll_area_vbox, config, window)

        # 填充
        scroll_area_vbox.addStretch(1)

        self.subscribe(Base.Event.APP_UPDATE_CHECK_START, self._on_update_check_start)
        self.subscribe(Base.Event.APP_UPDATE_CHECK_DONE, self._on_update_event)
        self.subscribe(Base.Event.APP_UPDATE_DOWNLOAD_START, self._on_update_download_start)
        self.subscribe(Base.Event.APP_UPDATE_DOWNLOAD_UPDATE, self._on_update_event)
        self.subscribe(Base.Event.APP_UPDATE_DOWNLOAD_DONE, self._on_update_event)
        self.subscribe(Base.Event.APP_UPDATE_DOWNLOAD_ERROR, self._on_update_event)
        self.refresh_update_ui()

    def add_widget_language(self, parent: QLayout, config: Config) -> None:
        strings = Localizer.get()
        languages = (
            strings.app_settings_page_language_zh,
            strings.app_settings_page_language_en,
        )

        def init(widget: ComboBoxCard) -> None:
            index = 1 if config.app_language == BaseLanguage.Enum.EN else 0
            widget.get_combo_box().setCurrentIndex(index)

        def current_changed(widget: ComboBoxCard) -> None:
            language = (
                BaseLanguage.Enum.EN
                if widget.get_combo_box().currentIndex() == 1
                else BaseLanguage.Enum.ZH
            )
            current = Config().load()
            if current.app_language == language:
                return
            current.app_language = language
            current.save()

            message_box = MessageBox(
                strings.app_settings_page_language_title,
                strings.switch_language_toast,
                self,
            )
            message_box.yesButton.setText(strings.confirm)
            message_box.cancelButton.hide()
            message_box.exec()

        parent.addWidget(
            ComboBoxCard(
                title = strings.app_settings_page_language_title,
                description = strings.app_settings_page_language_content,
                items = languages,
                init = init,
                current_changed = current_changed,
            )
        )

    def add_widget_about_updates(self, parent: QLayout) -> None:
        strings = Localizer.get()
        group = GroupCard(
            self,
            strings.app_update_group_title,
            strings.app_update_group_description,
        )
        self.update_group = group

        current_row = QWidget(group)
        current_layout = QHBoxLayout(current_row)
        current_layout.setContentsMargins(0, 12, 0, 12)
        current_layout.setSpacing(16)
        current_text = QVBoxLayout()
        current_text.setContentsMargins(0, 0, 0, 0)
        current_text.setSpacing(2)
        current_text.addWidget(StrongBodyLabel(strings.app_update_current_version, current_row))
        current_text.addWidget(CaptionLabel(f"RenpyBox {Version.CURRENT}", current_row))
        current_layout.addLayout(current_text)
        current_layout.addStretch(1)
        self.update_check_button = PushButton(strings.app_update_check, current_row)
        self.update_check_button.setMinimumWidth(136)
        self.update_check_button.clicked.connect(self._check_updates)
        current_layout.addWidget(self.update_check_button)
        group.add_widget(current_row)

        status_row = QWidget(group)
        status_row.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.update_status_row = status_row
        status_layout = QHBoxLayout(status_row)
        status_layout.setContentsMargins(0, 12, 0, 12)
        status_layout.setSpacing(16)
        self.update_status_icon = IconWidget(
            FluentIcon.ACCEPT.icon(color=get_theme_accent_color()),
            status_row,
        )
        self.update_status_icon.setFixedSize(16, 16)
        status_layout.addWidget(self.update_status_icon)
        status_text = QVBoxLayout()
        status_text.setContentsMargins(0, 0, 0, 0)
        status_text.setSpacing(8)
        # 状态文案与百分比同行：文案左对齐、百分比右对齐贴着进度条右端。
        status_head = QHBoxLayout()
        status_head.setContentsMargins(0, 0, 0, 0)
        status_head.setSpacing(8)
        self.update_status_label = BodyLabel(strings.app_update_status_latest, status_row)
        status_head.addWidget(self.update_status_label)
        status_head.addStretch(1)
        self.update_progress_label = CaptionLabel("", status_row)
        self.update_progress_label.setAlignment(
            Qt.AlignRight | Qt.AlignVCenter
        )
        self.update_progress_label.hide()
        status_head.addWidget(self.update_progress_label)
        status_text.addLayout(status_head)

        self.update_progress_bar = DownloadProgressBar(status_row)
        self.update_progress_bar.setRange(0, 100)
        self.update_progress_bar.setValue(0)
        self.update_progress_bar.setMinimumWidth(0)
        self.update_progress_bar.hide()
        status_text.addWidget(self.update_progress_bar)
        status_layout.addLayout(status_text, 1)

        self.update_action_button = PushButton("", status_row)
        self.update_action_button.setMinimumWidth(168)
        self.update_action_button.clicked.connect(self._handle_update_action)
        self.update_action_button.hide()
        status_layout.addWidget(self.update_action_button)

        self.update_install_button = PrimaryPushButton(strings.app_update_install, status_row)
        self.update_install_button.setMinimumWidth(168)
        self.update_install_button.clicked.connect(self._handle_install_update)
        self.update_install_button.hide()
        status_layout.addWidget(self.update_install_button)
        group.add_widget(status_row)

        changelog_row = QWidget(group)
        changelog_layout = QHBoxLayout(changelog_row)
        changelog_layout.setContentsMargins(0, 12, 0, 0)
        changelog_layout.setSpacing(16)
        changelog_text = QVBoxLayout()
        changelog_text.setContentsMargins(0, 0, 0, 0)
        changelog_text.setSpacing(2)
        changelog_text.addWidget(StrongBodyLabel(strings.app_update_changelog_title, changelog_row))
        changelog_text.addWidget(CaptionLabel(strings.app_update_changelog_description, changelog_row))
        changelog_layout.addLayout(changelog_text)
        changelog_layout.addStretch(1)
        changelog_button = PushButton(strings.app_update_changelog_action, changelog_row)
        changelog_button.setMinimumWidth(136)
        changelog_button.clicked.connect(self._show_changelog)
        changelog_layout.addWidget(changelog_button)
        group.add_widget(changelog_row)

        parent.addWidget(group)

    def _check_updates(self) -> None:
        if self._checking_update:
            return
        self._checking_update = True
        self.refresh_update_ui()
        self.emit(Base.Event.APP_UPDATE_CHECK_START, {"manual": True})

    def _on_update_check_start(self, event: str, data: dict) -> None:
        if data.get("manual") is True:
            self._checking_update = True
            self.refresh_update_ui()

    def _on_update_download_start(self, event: str, data: dict) -> None:
        self._cancelling_update = False
        QTimer.singleShot(0, self.refresh_update_ui)

    def _on_update_event(self, event: str, data: dict) -> None:
        if event == Base.Event.APP_UPDATE_CHECK_DONE:
            if data.get("manual") is True:
                self._checking_update = False
                error = str(data.get("error", "") or "").strip()
                if error:
                    self.emit(Base.Event.APP_TOAST_SHOW, {
                        "type": Base.ToastType.ERROR,
                        "message": Localizer.get().app_update_check_failure + error,
                    })
                elif data.get("new_version") is not True:
                    self.emit(Base.Event.APP_TOAST_SHOW, {
                        "type": Base.ToastType.SUCCESS,
                        "message": Localizer.get().app_update_check_latest_toast,
                    })
        elif (
            event == Base.Event.APP_UPDATE_DOWNLOAD_ERROR
            and data.get("cancelled") is True
        ):
            self._cancelling_update = False
            self.emit(Base.Event.APP_TOAST_SHOW, {
                "type": Base.ToastType.INFO,
                "message": Localizer.get().app_update_cancelled,
            })
        elif event in (
            Base.Event.APP_UPDATE_DOWNLOAD_DONE,
            Base.Event.APP_UPDATE_DOWNLOAD_ERROR,
        ):
            self._cancelling_update = False
        self.refresh_update_ui()

    @staticmethod
    def _format_megabytes(size: object) -> str:
        try:
            value = max(0, int(size))
        except (TypeError, ValueError):
            value = 0
        return f"{value / (1024 * 1024):.1f} MB"

    def _update_state(self) -> dict:
        manager = VersionManager.get()
        if hasattr(manager, "get_update_state"):
            return manager.get_update_state()
        latest = manager.get_latest() if hasattr(manager, "get_latest") else {}
        return {
            "status": manager.get_status(),
            "latest": latest,
            "downloaded_size": 0,
            "total_size": 0,
        }

    @staticmethod
    def _known_update_available(latest: dict) -> bool:
        return (
            VersionManager.parse_version(Version.CURRENT)
            < VersionManager.parse_version(str(latest.get("tag_name", "")))
        )

    def refresh_update_ui(self) -> None:
        strings = Localizer.get()
        state = self._update_state()
        status = state.get("status", VersionManager.Status.NONE)
        latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
        version = VersionManager.display_version(latest.get("tag_name", ""))

        self.update_check_button.setText(
            strings.app_update_checking if self._checking_update else strings.app_update_check
        )
        self.update_check_button.setEnabled(
            not self._checking_update and status != VersionManager.Status.UPDATING
        )
        self.update_progress_bar.hide()
        self.update_progress_label.hide()
        if status != VersionManager.Status.UPDATING:
            self.update_progress_bar.stopShimmer()
            self.update_progress_bar.setError(False)
            self.update_progress_bar.setValue(0)
        self.update_action_button.hide()
        self.update_action_button.setEnabled(True)
        self.update_install_button.hide()

        if self._checking_update:
            self.update_status_icon.setIcon(
                FluentIcon.UPDATE.icon(color=get_theme_accent_color())
            )
            self.update_status_label.setText(strings.app_update_checking)
        elif status == VersionManager.Status.NEW_VERSION:
            self.update_status_icon.setIcon(
                FluentIcon.UPDATE.icon(color=get_theme_accent_color())
            )
            self.update_status_label.setText(
                strings.app_update_status_new.replace("{VERSION}", version)
            )
            self.update_action_button.setText(strings.app_update_view_details)
            self.update_action_button.show()
        elif status == VersionManager.Status.UPDATING:
            self.update_status_icon.setIcon(
                FluentIcon.CLOUD_DOWNLOAD.icon(color=get_theme_accent_color())
            )
            downloaded = state.get("downloaded_size", 0)
            total = state.get("total_size", 0)
            status_text = strings.app_update_status_downloading
            status_text = status_text.replace(
                "{DOWNLOADED}", self._format_megabytes(downloaded)
            )
            status_text = status_text.replace("{TOTAL}", self._format_megabytes(total))
            self.update_status_label.setText(status_text)
            try:
                progress = int(int(downloaded) / max(1, int(total)) * 100)
            except (TypeError, ValueError):
                progress = 0
            progress = max(0, min(100, progress))
            self.update_progress_bar.setValue(progress)
            self.update_progress_bar.show()
            self.update_progress_label.setText(f"{progress}%")
            self.update_progress_label.show()
            # 取消中就停掉流光，避免界面还在“正在传输”地跑。
            if self._cancelling_update:
                self.update_progress_bar.stopShimmer()
            else:
                self.update_progress_bar.startShimmer()
            self.update_action_button.setText(
                strings.app_update_cancelling
                if self._cancelling_update
                else strings.app_update_cancel
            )
            self.update_action_button.setEnabled(not self._cancelling_update)
            self.update_action_button.show()
        elif status == VersionManager.Status.DOWNLOADED:
            self.update_status_icon.setIcon(
                FluentIcon.ACCEPT.icon(color=get_theme_accent_color())
            )
            self.update_status_label.setText(strings.app_update_status_downloaded)
            self.update_install_button.show()
        elif self._known_update_available(latest):
            self.update_status_icon.setIcon(
                FluentIcon.UPDATE.icon(color=get_theme_accent_color())
            )
            self.update_status_label.setText(
                strings.app_update_status_new.replace("{VERSION}", version)
            )
            self.update_action_button.setText(strings.app_update_view_details)
            self.update_action_button.show()
        elif str(state.get("error", "") or "").strip():
            self.update_status_icon.setIcon(
                FluentIcon.INFO.icon(color=QColor("#909090"))
            )
            self.update_status_label.setText(strings.app_update_status_check_failed)
        elif not latest:
            self.update_status_icon.setIcon(
                FluentIcon.INFO.icon(color=QColor("#909090"))
            )
            self.update_status_label.setText(strings.app_update_status_not_checked)
        else:
            self.update_status_icon.setIcon(
                FluentIcon.ACCEPT.icon(color=get_theme_accent_color())
            )
            self.update_status_label.setText(strings.app_update_status_latest)

    def _handle_update_action(self) -> None:
        state = self._update_state()
        status = state.get("status", VersionManager.Status.NONE)
        latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
        if (
            status == VersionManager.Status.NEW_VERSION
            or (
                status == VersionManager.Status.NONE
                and self._known_update_available(latest)
            )
        ):
            self._show_update_details()
        elif status == VersionManager.Status.UPDATING:
            self._cancelling_update = True
            self.emit(Base.Event.APP_UPDATE_DOWNLOAD_CANCEL, {})
            self.refresh_update_ui()

    def _handle_install_update(self) -> None:
        if Engine.get().get_status() != Engine.Status.IDLE:
            message_box = MessageBox(
                Localizer.get().warning,
                Localizer.get().app_update_install_busy,
                self._window,
            )
            message_box.yesButton.setText(Localizer.get().confirm)
            message_box.cancelButton.setText(Localizer.get().cancel)
            if not message_box.exec():
                return
        self.emit(Base.Event.APP_UPDATE_EXTRACT, {})

    def _show_update_details(self) -> None:
        state = self._update_state()
        latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
        if not latest:
            return
        if UpdateDetailsDialog(latest, self._window).exec():
            self.emit(Base.Event.APP_UPDATE_DOWNLOAD_START, {})
            QTimer.singleShot(0, self.refresh_update_ui)

    def _show_changelog(self) -> None:
        state = self._update_state()
        latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
        ChangelogDialog(self._window, latest=latest).exec()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh_update_ui()

    # 启动音效
    def add_widget_startup_sound(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(
                bool(getattr(config, "startup_sound_enable", False))
            )

        def checked_changed(widget: SwitchButtonCard) -> None:
            config = Config().load()
            config.startup_sound_enable = widget.get_switch_button().isChecked()
            config.save()

        parent.addWidget(
            SwitchButtonCard(
                title = Localizer.get().app_settings_page_startup_sound_title,
                description = Localizer.get().app_settings_page_startup_sound_content,
                init = init,
                checked_changed = checked_changed,
            )
        )

    # 专家模式
    def add_widget_expert_mode(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(
                config.expert_mode
            )

        def checked_changed(widget: SwitchButtonCard) -> None:
            config = Config().load()
            config.reset_expert_settings()
            config.expert_mode = widget.get_switch_button().isChecked()
            config.save()

            message_box = MessageBox(Localizer.get().warning, Localizer.get().app_settings_page_close, self)
            message_box.yesButton.setText(Localizer.get().confirm)
            message_box.cancelButton.hide()

            # 关闭应用
            if message_box.exec():
                os.kill(os.getpid(), signal.SIGTERM)

        parent.addWidget(
            SwitchButtonCard(
                title = Localizer.get().app_settings_page_expert_title,
                description = Localizer.get().app_settings_page_expert_content,
                init = init,
                checked_changed = checked_changed,
            )
        )

    # 字体优化
    def add_widget_font_hinting(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init(widget: SwitchButtonCard) -> None:
            widget.get_switch_button().setChecked(
                config.font_hinting
            )

        def checked_changed(widget: SwitchButtonCard) -> None:
            config = Config().load()
            config.font_hinting =  widget.get_switch_button().isChecked()
            config.save()

            message_box = MessageBox(Localizer.get().warning, Localizer.get().app_settings_page_close, self)
            message_box.yesButton.setText(Localizer.get().confirm)
            message_box.cancelButton.hide()

            # 关闭应用
            if message_box.exec():
                os.kill(os.getpid(), signal.SIGTERM)

        parent.addWidget(
            SwitchButtonCard(
                title = Localizer.get().app_settings_page_font_hinting_title,
                description = Localizer.get().app_settings_page_font_hinting_content,
                init = init,
                checked_changed = checked_changed,
            )
        )

    # 全局缩放
    def add_widget_scale_factor(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def init(widget: ComboBoxCard) -> None:
            widget.get_combo_box().setCurrentIndex(
                max(0, widget.get_combo_box().findText(config.scale_factor))
            )

        def current_changed(widget: ComboBoxCard) -> None:
            config = Config().load()
            config.scale_factor = widget.get_combo_box().text()
            config.save()

            message_box = MessageBox(Localizer.get().warning, Localizer.get().app_settings_page_close, self)
            message_box.yesButton.setText(Localizer.get().confirm)
            message_box.cancelButton.hide()

            # 关闭应用
            if message_box.exec():
                os.kill(os.getpid(), signal.SIGTERM)

        parent.addWidget(
            ComboBoxCard(
                title = Localizer.get().app_settings_page_scale_factor_title,
                description = Localizer.get().app_settings_page_scale_factor_content,
                items = (Localizer.get().auto, *Config.UI_SCALE_FACTORS),
                init = init,
                current_changed = current_changed,
            )
        )

    # 网络代理
    def add_widget_proxy(self, parent: QLayout, config: Config, window: FluentWindow) -> None:

        def checked_changed(swicth_button: SwitchButton, checked: bool) -> None:
            config = Config().load()
            config.proxy_enable = checked
            config.save()

            message_box = MessageBox(Localizer.get().warning, Localizer.get().app_settings_page_close, self)
            message_box.yesButton.setText(Localizer.get().confirm)
            message_box.cancelButton.hide()

            # 关闭应用
            if message_box.exec():
                os.kill(os.getpid(), signal.SIGTERM)

        def init(widget: LineEditCard) -> None:
            widget.get_line_edit().setText(config.proxy_url)
            widget.get_line_edit().setFixedWidth(256)
            widget.get_line_edit().setPlaceholderText(Localizer.get().app_settings_page_proxy_url)

            swicth_button = SwitchButton()
            swicth_button.setOnText("")
            swicth_button.setOffText("")
            swicth_button.setChecked(config.proxy_enable)
            swicth_button.checkedChanged.connect(lambda checked: checked_changed(swicth_button, checked))
            widget.add_spacing(8)
            widget.add_widget(swicth_button)

        def text_changed(widget: LineEditCard, text: str) -> None:
            config = Config().load()
            config.proxy_url = text.strip()
            config.save()

        parent.addWidget(
            LineEditCard(
                title = Localizer.get().app_settings_page_proxy_url_title,
                description = Localizer.get().app_settings_page_proxy_url_content,
                init = init,
                text_changed = text_changed,
            )
        )
