"""抽取相关对话框在暗色主题下不应残留系统浅色底（issue #25）。"""
import os
from collections import Counter

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import QPoint
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme, setThemeColor

from frontend.RenpyToolbox.GameExtractionRulesDialog import GameExtractionRulesDialog
from module.Config import Config
from module.Extract.GameExtractionRules import RuleStore
from tests.frontend.test_theme_palette import contrast
from widget.ThemeHelper import get_current_stylesheet
from widget.ThemeTokens import DARK, LIGHT

APP = QApplication.instance() or QApplication([])

# QScrollArea.setWidget() 打开的 autoFillBackground 会画 QPalette::Window，
# Qt 默认是浅灰，两套主题下完全一致 —— 这就是暗色主题里那块亮斑。
SYSTEM_LIGHT = {'#efefef', '#f0f0f0', '#fafafa', '#f8f8f8'}


def _make_dialog(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'load', lambda self: self)
    root = tmp_path / 'project'
    game = root / 'game'
    tl = game / 'tl' / 'chinese'
    tl.mkdir(parents=True)
    (game / 'scene.rpy').write_text('e "Hello."\n', encoding='utf-8')
    store = RuleStore(tmp_path / 'rules.json')
    dialog = GameExtractionRulesDialog(root, 'chinese', store=store, category='tl', base=tl)
    dialog._add_rule()
    dialog.show()
    for _ in range(4):
        APP.processEvents()
    return dialog


def _sample(image, step=4):
    return Counter(
        image.pixelColor(x, y).name().lower()
        for y in range(0, image.height(), step)
        for x in range(0, image.width(), step)
    )


def _pixel_at(dialog, widget, dx, dy):
    image = dialog.grab().toImage()
    point = widget.mapTo(dialog, QPoint(dx, dy))
    return image.pixelColor(point.x(), point.y())


@pytest.mark.parametrize(('theme', 'expected'), [(Theme.DARK, DARK), (Theme.LIGHT, LIGHT)])
def test_rule_editor_has_no_system_light_surface(tmp_path, monkeypatch, theme, expected):
    setTheme(theme)
    setThemeColor('#2398D4')
    APP.setStyleSheet(get_current_stylesheet())
    dialog = _make_dialog(tmp_path, monkeypatch)
    try:
        colours = _sample(dialog.grab().toImage())
        sampled = sum(colours.values())
        leaked = sum(count for name, count in colours.items() if name in SYSTEM_LIGHT)
        assert leaked * 100 // sampled == 0, colours.most_common(5)

        background = _pixel_at(dialog, dialog.form_widget, 2, 2)
        assert background.name() in {expected.background.lower(), expected.surface.lower()}
        assert (background.lightnessF() > 0.5) == (theme == Theme.LIGHT)
    finally:
        dialog._dirty = False
        dialog.close()
        dialog.deleteLater()
        APP.processEvents()


@pytest.mark.parametrize(('theme', 'expected'), [(Theme.DARK, DARK), (Theme.LIGHT, LIGHT)])
def test_rule_editor_labels_stay_readable(tmp_path, monkeypatch, theme, expected):
    setTheme(theme)
    setThemeColor('#2398D4')
    APP.setStyleSheet(get_current_stylesheet())
    dialog = _make_dialog(tmp_path, monkeypatch)
    try:
        background = _pixel_at(dialog, dialog.form_widget, 2, 2)
        label = dialog.form_widget.findChild(type(dialog.status))
        assert label is not None
        foreground = label.palette().color(QPalette.WindowText)
        assert contrast(foreground, background) >= 4.5
        assert QColor(expected.text_primary).name() == foreground.name() or contrast(
            QColor(expected.text_primary), background
        ) >= 4.5
    finally:
        dialog._dirty = False
        dialog.close()
        dialog.deleteLater()
        APP.processEvents()
