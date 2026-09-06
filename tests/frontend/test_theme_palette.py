import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QButtonGroup, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, PrimaryPushButton, Theme, qconfig, setTheme, setThemeColor

from frontend.AppFluentWindow import AppFluentWindow
from frontend.TranslationPage import TranslationPage
from widget.QuietPillButton import QuietPillButton
from widget.SearchCard import SearchCard
from widget.ThemeHelper import get_current_stylesheet, mark_app_page


APP = QApplication.instance() or QApplication([])


def contrast(foreground: QColor, background: QColor) -> float:
    def luminance(color: QColor) -> float:
        channels = [component / 255 for component in (color.red(), color.green(), color.blue())]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    bright, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (bright + 0.05) / (dark + 0.05)


@pytest.fixture(autouse=True)
def restore_theme():
    previous_theme = qconfig.theme
    previous_color = QColor(qconfig.get(qconfig.themeColor))
    previous_stylesheet = APP.styleSheet()
    setThemeColor(AppFluentWindow.APP_THEME_COLOR)
    yield
    setThemeColor(previous_color)
    setTheme(previous_theme)
    APP.setStyleSheet(previous_stylesheet)


@pytest.mark.parametrize("theme", [Theme.DARK, Theme.LIGHT])
def test_body_and_secondary_text_contrast(theme) -> None:
    setTheme(theme)
    APP.setStyleSheet(get_current_stylesheet())
    window = QWidget()
    mark_app_page(window)
    layout = QVBoxLayout(window)
    body = QLabel("Project workspace", window)
    secondary = CaptionLabel("Current project details", window)
    secondary.setTextColor(QColor("#586574"), QColor("#A8B4C1"))
    layout.addWidget(body)
    layout.addWidget(secondary)
    window.show()
    APP.processEvents()
    try:
        background = window.grab().toImage().pixelColor(1, 1)
        foreground = body.palette().color(QPalette.WindowText)
        assert contrast(foreground, background) >= 7
        assert contrast(secondary.palette().color(QPalette.WindowText), background) >= 4.5
        assert (foreground.lightnessF() > background.lightnessF()) == (theme == Theme.DARK)
    finally:
        window.close()
        window.deleteLater()


@pytest.mark.parametrize("initial_theme", [Theme.DARK, Theme.LIGHT])
def test_quiet_filters_preserve_selection_and_theme_contrast(initial_theme) -> None:
    setTheme(initial_theme)
    window = QWidget()
    layout = QVBoxLayout(window)
    group = QButtonGroup(window)
    buttons = [QuietPillButton("Worldbuilding", window), QuietPillButton("Characters", window)]
    for button in buttons:
        layout.addWidget(button)
        group.addButton(button)
    buttons[0].setChecked(True)
    window.show()
    try:
        for theme in (initial_theme, Theme.LIGHT, Theme.DARK, Theme.LIGHT):
            setTheme(theme)
            APP.setStyleSheet(get_current_stylesheet())
            APP.processEvents()
            selected = next(button for button in buttons if button.isChecked())
            background = selected.grab().toImage().pixelColor(6, selected.height() // 2)
            foreground = selected.palette().color(QPalette.ButtonText)
            assert background.name() == ("#303b47" if theme == Theme.DARK else "#e4e9ee")
            assert contrast(foreground, background) >= 4.5
            assert (foreground.lightnessF() > background.lightnessF()) == (theme == Theme.DARK)
            assert background.saturationF() < 0.4
            buttons[1].setFocus()
            QTest.keyClick(buttons[1], Qt.Key_Space)
            assert buttons[1].isChecked()
            assert not buttons[0].isChecked()
            buttons[0].click()
            assert buttons[0].isChecked()
        buttons[1].setEnabled(False)
        buttons[1].click()
        assert buttons[0].isChecked()
    finally:
        window.close()
        window.deleteLater()


@pytest.mark.parametrize("theme", [Theme.DARK, Theme.LIGHT])
def test_search_focus_keeps_readable_text_and_regex_toggle(theme) -> None:
    setTheme(theme)
    APP.setStyleSheet(get_current_stylesheet())
    window = QWidget()
    mark_app_page(window)
    layout = QVBoxLayout(window)
    card = SearchCard(window)
    layout.addWidget(card)
    window.show()
    try:
        card.line_edit.setText("Search project")
        card.line_edit.setFocus()
        APP.processEvents()
        background = card.line_edit.grab().toImage().pixelColor(6, card.line_edit.height() // 2)
        foreground = card.line_edit.palette().color(QPalette.Text)
        assert contrast(foreground, background) >= 4.5
        card.regex_btn.click()
        assert card.regex_btn.isChecked()
        assert card._regex_mode
    finally:
        window.close()
        window.deleteLater()


def test_primary_and_status_labels_follow_theme_changes() -> None:
    window = QWidget()
    layout = QVBoxLayout(window)
    button = PrimaryPushButton("Apply changes", window)
    label = TranslationPage._make_status_pill("Translated 50.0%")
    layout.addWidget(button)
    layout.addWidget(label)
    window.show()
    try:
        for theme in (Theme.DARK, Theme.LIGHT, Theme.DARK):
            setTheme(theme)
            APP.setStyleSheet(get_current_stylesheet())
            APP.processEvents()
            background = button.grab().toImage().pixelColor(6, button.height() // 2)
            assert contrast(button.palette().color(QPalette.ButtonText), background) >= 4.5
            label_background = label.grab().toImage().pixelColor(2, label.height() // 2)
            label_foreground = label.palette().color(QPalette.WindowText)
            assert contrast(label_foreground, label_background) >= 4.5
            assert (label_foreground.lightnessF() > label_background.lightnessF()) == (theme == Theme.DARK)
    finally:
        window.close()
        window.deleteLater()
