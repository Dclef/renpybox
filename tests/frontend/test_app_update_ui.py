import importlib
import json
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtGui import QColor
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QSizePolicy
from qfluentwidgets import FluentIcon
from qfluentwidgets import FluentWindow

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from base.Version import Version
from base.VersionManager import VersionManager
from frontend.AppFluentWindow import AppFluentWindow
from frontend.AppSettingsPage import AppSettingsPage
from module.Config import Config
from module.Engine.Engine import Engine
from module.Localizer.Localizer import Localizer


APP = QApplication.instance() or QApplication([])
app_window_module = importlib.import_module("frontend.AppFluentWindow")
app_settings_module = importlib.import_module("frontend.AppSettingsPage")
changelog_dialog_module = importlib.import_module("frontend.Setting.ChangelogDialog")


def _set_state(manager, status, downloaded=0, total=0, version="v0.7.2"):
    with manager.lock:
        manager.status = status
        manager.latest = {
            "tag_name": version,
            "body": "- 更新说明",
            "published_at": "2026-07-31T00:00:00Z",
            "asset": {"size": total},
        }
        manager.downloaded_size = downloaded
        manager.total_size = total
        manager.error = ""


def _assert_status_icon(page, icon, color):
    actual = page.update_status_icon._icon
    expected = icon.icon(color=QColor(color))
    assert actual.pixmap(16, 16).toImage() == expected.pixmap(16, 16).toImage()


def test_update_group_rebuilds_all_manager_states_with_adaptive_status_row(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    Localizer.set_app_language(BaseLanguage.Enum.ZH)
    manager = VersionManager.get()
    original = manager.get_update_state()

    window = FluentWindow()
    window.resize(1100, 760)
    page = AppSettingsPage("app_settings_page", window)
    window.stackedWidget.addWidget(page)
    window.stackedWidget.setCurrentWidget(page)
    window.show()
    QTest.qWait(20)

    try:
        assert page.window() is window
        policy = page.update_status_row.sizePolicy()
        assert page.update_status_row.minimumHeight() == 0
        assert policy.horizontalPolicy() == QSizePolicy.Preferred
        assert policy.verticalPolicy() == QSizePolicy.Maximum
        assert page.update_status_icon.size().width() == 16
        assert page.update_status_icon.size().height() == 16
        assert page.update_progress_bar.minimumWidth() == 0
        assert page.update_progress_bar.height() == 4

        _set_state(manager, VersionManager.Status.NONE, version=Version.CURRENT)
        page.refresh_update_ui()
        assert page.update_status_label.text() == "已是最新版本"
        assert not page.update_action_button.isVisible()
        assert page.update_status_row.sizeHint().height() < 72
        _assert_status_icon(page, FluentIcon.ACCEPT, "#BCA483")

        _set_state(manager, VersionManager.Status.NEW_VERSION)
        page.refresh_update_ui()
        assert "v0.7.2" in page.update_status_label.text()
        assert page.update_action_button.text() == "查看详情"
        assert page.update_action_button.isVisible()
        _assert_status_icon(page, FluentIcon.UPDATE, "#BCA483")

        _set_state(
            manager,
            VersionManager.Status.UPDATING,
            downloaded=12 * 1024 * 1024,
            total=48 * 1024 * 1024,
        )
        page.refresh_update_ui()
        assert page.update_progress_bar.value() == 25
        assert page.update_progress_bar.isVisible()
        assert page.update_action_button.text() == "取消"
        _assert_status_icon(page, FluentIcon.CLOUD_DOWNLOAD, "#BCA483")

        _set_state(
            manager,
            VersionManager.Status.DOWNLOADED,
            downloaded=48 * 1024 * 1024,
            total=48 * 1024 * 1024,
        )
        page.refresh_update_ui()
        assert page.update_install_button.isVisible()
        assert page.update_progress_bar.value() == 0
        _assert_status_icon(page, FluentIcon.ACCEPT, "#BCA483")

        _set_state(manager, VersionManager.Status.NONE)
        page.refresh_update_ui()
        assert "v0.7.2" in page.update_status_label.text()
        assert page.update_action_button.text() == "查看详情"
        assert page.update_action_button.isVisible()
        assert page.update_progress_bar.value() == 0
        _assert_status_icon(page, FluentIcon.UPDATE, "#BCA483")
    finally:
        for event, handler in (
            (Base.Event.APP_UPDATE_CHECK_START, page._on_update_check_start),
            (Base.Event.APP_UPDATE_CHECK_DONE, page._on_update_event),
            (Base.Event.APP_UPDATE_DOWNLOAD_START, page._on_update_download_start),
            (Base.Event.APP_UPDATE_DOWNLOAD_UPDATE, page._on_update_event),
            (Base.Event.APP_UPDATE_DOWNLOAD_DONE, page._on_update_event),
            (Base.Event.APP_UPDATE_DOWNLOAD_ERROR, page._on_update_event),
        ):
            page.unsubscribe(event, handler)
        with manager.lock:
            manager.status = original["status"]
            manager.version = original["version"]
            manager.latest = original["latest"]
            manager.downloaded_size = original["downloaded_size"]
            manager.total_size = original["total_size"]
            manager.error = original["error"]
        window.close()


def test_install_update_emits_immediately_when_engine_is_idle(monkeypatch):
    events = []
    fake_engine = SimpleNamespace(get_status=lambda: Engine.Status.IDLE)
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: fake_engine))

    def unexpected_message_box(*args, **kwargs):
        raise AssertionError("idle installation must not ask for confirmation")

    monkeypatch.setattr(app_settings_module, "MessageBox", unexpected_message_box)
    fake_page = SimpleNamespace(
        _window=object(),
        emit=lambda event, data: events.append((event, data)),
    )

    AppSettingsPage._handle_install_update(fake_page)

    assert events == [(Base.Event.APP_UPDATE_EXTRACT, {})]


@pytest.mark.parametrize(
    ("confirmed", "expected_events"),
    [
        (False, []),
        (True, [(Base.Event.APP_UPDATE_EXTRACT, {})]),
    ],
)
def test_install_update_confirms_when_engine_is_busy(
    monkeypatch,
    confirmed,
    expected_events,
):
    Localizer.set_app_language(BaseLanguage.Enum.ZH)
    events = []
    dialogs = []
    parent = object()
    fake_engine = SimpleNamespace(get_status=lambda: Engine.Status.TRANSLATING)
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: fake_engine))

    class ButtonStub:
        def __init__(self):
            self.text = ""

        def setText(self, text):
            self.text = text

    class MessageBoxStub:
        def __init__(self, title, content, dialog_parent):
            self.title = title
            self.content = content
            self.parent = dialog_parent
            self.yesButton = ButtonStub()
            self.cancelButton = ButtonStub()
            dialogs.append(self)

        def exec(self):
            return confirmed

    monkeypatch.setattr(app_settings_module, "MessageBox", MessageBoxStub)
    fake_page = SimpleNamespace(
        _window=parent,
        emit=lambda event, data: events.append((event, data)),
    )

    AppSettingsPage._handle_install_update(fake_page)

    assert events == expected_events
    assert len(dialogs) == 1
    assert dialogs[0].title == "警告"
    assert dialogs[0].content == (
        "当前有任务正在运行，安装更新会中断任务并重启应用，确定继续吗"
    )
    assert dialogs[0].parent is parent
    assert dialogs[0].yesButton.text == "确认"
    assert dialogs[0].cancelButton.text == "取消"


def test_avatar_action_only_navigates_to_app_settings():
    settings_page = object()
    switched = []
    fake_window = SimpleNamespace(
        app_settings_page=settings_page,
        switchTo=lambda page: switched.append(page),
    )

    AppFluentWindow.open_app_settings_page(fake_window)

    assert switched == [settings_page]


def test_avatar_keeps_new_version_indicator_from_cached_release(monkeypatch):
    names = []
    manager = SimpleNamespace(
        get_update_state=lambda: {
            "status": VersionManager.Status.NONE,
            "version": Version.CURRENT,
            "latest": {"tag_name": "v99.0.0"},
            "downloaded_size": 0,
            "total_size": 0,
        },
    )
    monkeypatch.setattr(
        VersionManager,
        "get",
        classmethod(lambda cls: manager),
    )
    fake_window = SimpleNamespace(
        home_page_widget=SimpleNamespace(setName=names.append),
    )

    AppFluentWindow._refresh_update_indicator(fake_window)

    assert names == [Localizer.get().app_new_version]


def test_update_status_distinguishes_not_checked_and_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    Localizer.set_app_language(BaseLanguage.Enum.ZH)
    manager = VersionManager.get()
    original = manager.get_update_state()
    window = FluentWindow()
    page = AppSettingsPage("app_settings_page", window)

    try:
        with manager.lock:
            manager.status = VersionManager.Status.NONE
            manager.latest = {}
            manager.error = ""
        page.refresh_update_ui()
        assert page.update_status_label.text() == "尚未检查更新"
        _assert_status_icon(page, FluentIcon.INFO, "#909090")

        with manager.lock:
            manager.error = "offline"
        page.refresh_update_ui()
        assert page.update_status_label.text() == "检查更新失败，请重试"
        _assert_status_icon(page, FluentIcon.INFO, "#909090")
    finally:
        for event, handler in (
            (Base.Event.APP_UPDATE_CHECK_START, page._on_update_check_start),
            (Base.Event.APP_UPDATE_CHECK_DONE, page._on_update_event),
            (Base.Event.APP_UPDATE_DOWNLOAD_START, page._on_update_download_start),
            (Base.Event.APP_UPDATE_DOWNLOAD_UPDATE, page._on_update_event),
            (Base.Event.APP_UPDATE_DOWNLOAD_DONE, page._on_update_event),
            (Base.Event.APP_UPDATE_DOWNLOAD_ERROR, page._on_update_event),
        ):
            page.unsubscribe(event, handler)
        with manager.lock:
            manager.status = original["status"]
            manager.version = original["version"]
            manager.latest = original["latest"]
            manager.downloaded_size = original["downloaded_size"]
            manager.total_size = original["total_size"]
            manager.error = original["error"]
        window.close()


def test_legacy_config_marks_current_version_without_opening_dialog(
    monkeypatch,
    tmp_path,
):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"theme": "LIGHT"}', encoding="utf-8")
    monkeypatch.setattr(Config, "CONFIG_PATH", str(config_path))
    scheduled = []
    monkeypatch.setattr(
        app_window_module.QTimer,
        "singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )
    fake_window = SimpleNamespace(
        _show_post_update_changelog=lambda: None,
    )

    AppFluentWindow._schedule_post_update_changelog(fake_window)

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["last_seen_version"] == Version.CURRENT
    assert scheduled == []


def test_first_install_marks_current_version_without_opening_dialog(
    monkeypatch,
    tmp_path,
):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"last_seen_version": ""}', encoding="utf-8")
    monkeypatch.setattr(Config, "CONFIG_PATH", str(config_path))
    scheduled = []
    monkeypatch.setattr(
        app_window_module.QTimer,
        "singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )
    fake_window = SimpleNamespace(
        _show_post_update_changelog=lambda: None,
    )

    AppFluentWindow._schedule_post_update_changelog(fake_window)

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["last_seen_version"] == Version.CURRENT
    assert scheduled == []


def test_post_update_changelog_skips_blank_section_but_marks_version_seen(
    monkeypatch,
    tmp_path,
):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"last_seen_version": "v0.7.0"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(Config, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(
        changelog_dialog_module,
        "build_changelog_markdown",
        lambda **kwargs: " \n",
    )
    opened = []
    monkeypatch.setattr(
        app_window_module,
        "ChangelogDialog",
        lambda *args, **kwargs: opened.append((args, kwargs)),
    )

    AppFluentWindow._show_post_update_changelog(SimpleNamespace())

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["last_seen_version"] == Version.CURRENT
    assert opened == []


def test_post_update_changelog_opens_when_current_section_exists(
    monkeypatch,
    tmp_path,
):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"last_seen_version": "v0.7.0"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(Config, "CONFIG_PATH", str(config_path))
    requested_versions = []

    def build_markdown(*, current_only_version):
        requested_versions.append(current_only_version)
        return "## current release"

    monkeypatch.setattr(
        changelog_dialog_module,
        "build_changelog_markdown",
        build_markdown,
    )
    dialogs = []

    class _Dialog:
        def __init__(self, parent, *, current_only_version):
            dialogs.append((parent, current_only_version, "created"))

        def exec(self):
            dialogs.append((None, None, "executed"))

    monkeypatch.setattr(app_window_module, "ChangelogDialog", _Dialog)
    fake_window = SimpleNamespace()

    AppFluentWindow._show_post_update_changelog(fake_window)

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["last_seen_version"] == Version.CURRENT
    assert requested_versions == [Version.CURRENT]
    assert dialogs == [
        (fake_window, Version.CURRENT, "created"),
        (None, None, "executed"),
    ]


def test_older_seen_version_opens_post_update_changelog(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"last_seen_version": "v0.7.0"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(Config, "CONFIG_PATH", str(config_path))
    scheduled = []
    monkeypatch.setattr(
        app_window_module.QTimer,
        "singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )
    fake_window = SimpleNamespace(_show_post_update_changelog=lambda: None)

    AppFluentWindow._schedule_post_update_changelog(fake_window)

    assert scheduled == [(500, fake_window._show_post_update_changelog)]


def test_newer_seen_version_does_not_open_downgrade_changelog(
    monkeypatch,
    tmp_path,
):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"last_seen_version": "v99.0.0"}', encoding="utf-8")
    monkeypatch.setattr(Config, "CONFIG_PATH", str(config_path))
    scheduled = []
    monkeypatch.setattr(
        app_window_module.QTimer,
        "singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )
    fake_window = SimpleNamespace(
        _show_post_update_changelog=lambda: None,
    )

    AppFluentWindow._schedule_post_update_changelog(fake_window)

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["last_seen_version"] == "v99.0.0"
    assert scheduled == []


def test_equivalent_seen_version_format_does_not_reopen_changelog(
    monkeypatch,
    tmp_path,
):
    config_path = tmp_path / "config.json"
    equivalent = f"RenpyBox_{Version.CURRENT}"
    config_path.write_text(
        json.dumps({"last_seen_version": equivalent}),
        encoding="utf-8",
    )
    monkeypatch.setattr(Config, "CONFIG_PATH", str(config_path))
    scheduled = []
    monkeypatch.setattr(
        app_window_module.QTimer,
        "singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )
    fake_window = SimpleNamespace(
        _show_post_update_changelog=lambda: None,
    )

    AppFluentWindow._schedule_post_update_changelog(fake_window)

    assert scheduled == []
