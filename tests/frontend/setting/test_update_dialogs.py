import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QCoreApplication, QEvent
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication, QFrame, QWidget
from qfluentwidgets import (
    TextBrowser,
    Theme,
    ThemeColor,
    qconfig,
    setTheme,
    setThemeColor,
)

import frontend.Setting.ChangelogDialog as changelog_dialog_module
from frontend.AppFluentWindow import AppFluentWindow
from base.BaseLanguage import BaseLanguage
from base.VersionManager import VersionManager
from frontend.Setting.ChangelogDialog import ChangelogDialog
from frontend.Setting.UpdateDetailsDialog import UpdateDetailsDialog
from module.Localizer.Localizer import Localizer


APP = QApplication.instance() or QApplication([])


def _dispose_widgets(dialog, parent: QWidget) -> None:
    dialog.close()
    dialog.deleteLater()
    parent.close()
    parent.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    APP.processEvents()


def test_update_details_dialog_renders_release_metadata() -> None:
    Localizer.set_app_language(BaseLanguage.Enum.ZH)
    parent = QWidget()
    dialog = UpdateDetailsDialog(
        {
            "tag_name": "v9.9.9",
            "body": "## 修复\n\n- 更新下载流程",
            "published_at": "2026-07-31T08:00:00Z",
            "asset": {"size": 48 * 1024 * 1024},
        },
        parent,
    )

    browser = dialog.findChild(TextBrowser)
    assert browser is not None
    assert "更新下载流程" in browser.toPlainText()
    assert dialog.yesButton.text() == "下载更新"
    assert dialog.cancelButton.text() == "稍后"
    assert dialog.widget.minimumWidth() == 720
    assert not dialog.yesButton.icon().isNull()

    # 主按钮底色必须跟随主题主色，不能再被控件级 setStyleSheet 钉成固定棕色——那样
    # 会整片顶掉 qfluentwidgets 基础 qss（圆角、内边距、color 一起丢），按钮退化成
    # 方角色块，也和全应用其他主按钮不同色。
    accent_qss = dialog.yesButton.styleSheet()
    assert "border-radius" in accent_qss
    accent_block = re.search(r"PrimaryPushButton[^{]*\{[^}]*\}", accent_qss)
    assert accent_block is not None, "主按钮缺少 PrimaryPushButton 规则"
    assert ThemeColor.PRIMARY.color().name() in accent_block.group(0).lower()

    _dispose_widgets(dialog, parent)


def test_changelog_dialog_renders_html_and_opens_full_history(
    monkeypatch,
) -> None:
    Localizer.set_app_language(BaseLanguage.Enum.ZH)
    monkeypatch.setattr(
        changelog_dialog_module,
        "read_local_changelog",
        lambda: "# 更新日志\n\n## v0.7.1\n\n- 本地记录",
    )
    opened = []
    monkeypatch.setattr(
        changelog_dialog_module.QDesktopServices,
        "openUrl",
        lambda url: opened.append(url.toString()),
    )
    parent = QWidget()
    dialog = ChangelogDialog(parent)
    finished = []
    dialog.finished.connect(finished.append)

    browser = dialog.findChild(TextBrowser)
    assert browser is not None
    assert "本地记录" in browser.toPlainText()
    assert "更新日志" not in browser.toPlainText()
    assert browser.frameShape() == QFrame.NoFrame
    assert browser.scrollDelegate.vScrollBar._isForceHidden is False
    assert "background: transparent" in browser.styleSheet()
    assert browser.height() == max(
        240,
        min(460, int(browser.document().size().height()) + 12),
    )
    margins = dialog.viewLayout.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        24,
        20,
        24,
        8,
    )
    assert dialog.yesButton.isHidden()
    assert dialog.link_button.text() == "在浏览器打开完整记录"
    assert dialog.buttonLayout.indexOf(dialog.link_button) == 0
    assert dialog.cancelButton.text() == "关闭"

    dialog.link_button.click()
    APP.processEvents()
    assert opened == [VersionManager.RELEASES_URL]
    assert finished == []

    _dispose_widgets(dialog, parent)


def test_changelog_dialog_uses_dark_theme_content_colors(monkeypatch) -> None:
    Localizer.set_app_language(BaseLanguage.Enum.ZH)
    monkeypatch.setattr(
        changelog_dialog_module,
        "read_local_changelog",
        lambda: "# 更新日志\n\n## v0.7.1\n### 修复\n- 修复 `res/xml/backup.xml`",
    )
    previous_theme = qconfig.theme
    setTheme(Theme.DARK)
    parent = QWidget()
    dialog = ChangelogDialog(parent)
    dialog.show()
    APP.processEvents()

    try:
        rendered = dialog.browser.toHtml().lower()
        assert "#9a9a9a" in rendered
        assert "#2d2d2d" in rendered
        assert dialog.browser.palette().color(QPalette.Text).name() == "#ffffff"
    finally:
        _dispose_widgets(dialog, parent)
        setTheme(previous_theme)


def _contrast(fg: QColor, bg: QColor) -> float:
    def channel(value: int) -> float:
        srgb = value / 255
        return srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4

    def luminance(color: QColor) -> float:
        return (
            0.2126 * channel(color.red())
            + 0.7152 * channel(color.green())
            + 0.0722 * channel(color.blue())
        )

    high, low = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_primary_button_accent_contrast_is_tracked() -> None:
    """明暗主题下的主按钮文字与常态、悬停底色均保持可读反差。"""
    previous_theme = qconfig.theme
    previous_color = QColor(qconfig.get(qconfig.themeColor))
    setThemeColor(AppFluentWindow.APP_THEME_COLOR)
    try:
        setTheme(Theme.DARK)
        assert _contrast(ThemeColor.PRIMARY.color(), QColor("black")) >= 4.5
        assert _contrast(ThemeColor.DARK_1.color(), QColor("black")) >= 4.5

        setTheme(Theme.LIGHT)
        light_contrast = _contrast(ThemeColor.PRIMARY.color(), QColor("white"))
        assert light_contrast >= 4.5
        assert _contrast(ThemeColor.LIGHT_1.color(), QColor("white")) >= 4.5
        assert QColor(AppFluentWindow.APP_THEME_COLOR).saturationF() < 0.4
    finally:
        setThemeColor(previous_color)
        setTheme(previous_theme)
