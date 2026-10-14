"""Qt 迁移提示：本地化、稍后操作、官方下载入口和每次启动一次提醒。"""
import importlib
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import QCoreApplication, QEvent
from PyQt5.QtWidgets import QApplication, QWidget
from qfluentwidgets import CaptionLabel

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from base.VersionManager import VersionManager
from frontend.AppFluentWindow import AppFluentWindow
from frontend.AppSettingsPage import AppSettingsPage
from frontend.Setting.UpdateDetailsDialog import UpdateDetailsDialog
from module.Localizer.Localizer import Localizer

APP = QApplication.instance() or QApplication([])
settings_module = importlib.import_module("frontend.AppSettingsPage")
window_module = importlib.import_module("frontend.AppFluentWindow")
LATEST = {
    "tag_name": "RenpyBox_v0.9.0", "delivery": "desktop",
    "asset": {"size": 1024}, "body": "Desktop changes",
}


@pytest.mark.parametrize("language,action,hint", [
    (BaseLanguage.Enum.ZH, "前往下载桌面版", "当前 Python 版及其配置会保留"),
    (BaseLanguage.Enum.EN, "Download Desktop App", "Your Python app and its settings will be kept"),
])
def test_desktop_dialog_explains_separate_installation(language, action, hint):
    Localizer.set_app_language(language)
    parent = QWidget()
    dialog = UpdateDetailsDialog(LATEST, parent)
    try:
        assert dialog.yesButton.text() == action
        assert dialog.cancelButton.text() == Localizer.get().later
        assert any(hint in label.text() for label in dialog.findChildren(CaptionLabel))
    finally:
        dialog.deleteLater()
        parent.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        Localizer.set_app_language(BaseLanguage.Enum.ZH)


@pytest.mark.parametrize("accepted", [False, True])
def test_desktop_action_opens_release_page_only_after_confirmation(monkeypatch, accepted):
    opened, events = [], []
    monkeypatch.setattr(settings_module, "UpdateDetailsDialog", lambda *args: SimpleNamespace(exec=lambda: accepted))
    monkeypatch.setattr(settings_module.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    page = SimpleNamespace(
        _update_state=lambda: {"latest": dict(LATEST)}, _window=None,
        emit=lambda *args: events.append(args), refresh_update_ui=lambda: None,
    )
    AppSettingsPage._show_update_details(page)
    assert opened == ([VersionManager.RELEASES_URL + "/tag/RenpyBox_v0.9.0"] if accepted else [])
    assert not events


def test_browser_failure_is_reported_without_starting_python_update(monkeypatch):
    events = []
    monkeypatch.setattr(settings_module, "UpdateDetailsDialog", lambda *args: SimpleNamespace(exec=lambda: True))
    monkeypatch.setattr(settings_module.QDesktopServices, "openUrl", lambda url: False)
    page = SimpleNamespace(
        _update_state=lambda: {"latest": dict(LATEST)}, _window=None,
        emit=lambda *args: events.append(args), refresh_update_ui=lambda: None,
    )
    AppSettingsPage._show_update_details(page)
    assert len(events) == 1
    assert events[0][0] == Base.Event.APP_TOAST_SHOW
    assert events[0][1]["type"] == Base.ToastType.ERROR


def test_automatic_migration_notice_is_scheduled_once_per_window(monkeypatch):
    scheduled, shown = [], []
    monkeypatch.setattr(window_module.QTimer, "singleShot", lambda delay, callback: scheduled.append(callback))
    window = SimpleNamespace(
        _refresh_update_indicator=lambda: None,
        app_settings_page=SimpleNamespace(_show_update_details=lambda: shown.append(True)),
    )
    payload = {"status": VersionManager.Status.DESKTOP_AVAILABLE, "manual": False, "error": ""}
    AppFluentWindow.app_update_check_done(window, "", {**payload, "manual": True})
    AppFluentWindow.app_update_check_done(window, "", {**payload, "error": "offline"})
    assert not scheduled
    AppFluentWindow.app_update_check_done(window, "", payload)
    AppFluentWindow.app_update_check_done(window, "", payload)
    assert len(scheduled) == 1
    scheduled[0]()
    assert shown == [True]


def test_same_version_migration_remains_available_in_settings(monkeypatch):
    monkeypatch.setattr(settings_module.Version, "CURRENT", "v0.9.0")
    assert AppSettingsPage._known_update_available(LATEST)
    assert not AppSettingsPage._known_update_available({"tag_name": "RenpyBox_v0.9.0"})
