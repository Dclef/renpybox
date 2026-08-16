import importlib
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget

from base.BaseLanguage import BaseLanguage
from frontend.AppSettingsPage import AppSettingsPage
from frontend.AppFluentWindow import AppFluentWindow
from module.Config import Config
from module.Localizer.Localizer import Localizer


APP = QApplication.instance() or QApplication([])
app_settings_module = importlib.import_module("frontend.AppSettingsPage")


class _ButtonStub:
    def __init__(self) -> None:
        self.text = ""
        self.hidden = False

    def setText(self, text: str) -> None:
        self.text = text

    def hide(self) -> None:
        self.hidden = True


class _MessageBoxStub:
    instances = []

    def __init__(self, title: str, content: str, parent: QWidget) -> None:
        self.title = title
        self.content = content
        self.parent = parent
        self.yesButton = _ButtonStub()
        self.cancelButton = _ButtonStub()
        self.exec_count = 0
        self.instances.append(self)

    def exec(self) -> bool:
        self.exec_count += 1
        return True


def test_language_card_persists_selection_without_changing_live_localizer(
    monkeypatch,
) -> None:
    config = Config()
    config.app_language = BaseLanguage.Enum.EN
    saved = []
    monkeypatch.setattr(Config, "load", lambda self, path=None: config)
    monkeypatch.setattr(
        Config,
        "save",
        lambda self, path=None: saved.append(self.app_language) or self,
    )
    monkeypatch.setattr(app_settings_module, "MessageBox", _MessageBoxStub)
    _MessageBoxStub.instances.clear()

    original_language = Localizer.get_app_language()
    Localizer.set_app_language(BaseLanguage.Enum.EN)
    parent = QWidget()
    layout = QVBoxLayout(parent)
    try:
        AppSettingsPage.add_widget_language(parent, layout, config)
        card = layout.itemAt(0).widget()
        combo = card.get_combo_box()

        assert combo.currentIndex() == 1
        assert [combo.itemText(index) for index in range(combo.count())] == [
            "简体中文",
            "English",
        ]

        combo.setCurrentIndex(0)

        assert config.app_language == BaseLanguage.Enum.ZH
        assert saved == [BaseLanguage.Enum.ZH]
        assert Localizer.get_app_language() == BaseLanguage.Enum.EN
        assert len(_MessageBoxStub.instances) == 1
        assert "restart" in _MessageBoxStub.instances[0].content.lower()
        assert _MessageBoxStub.instances[0].cancelButton.hidden is True
    finally:
        Localizer.set_app_language(original_language)
        parent.close()


def test_main_navigation_exposes_english_language_button(monkeypatch) -> None:
    class NavigationStub:
        def __init__(self) -> None:
            self.widgets = []

        def addSeparator(self, _position) -> None:
            pass

        def addWidget(self, **kwargs) -> None:
            self.widgets.append(kwargs)

    localized_pages = []
    settings_page = object()
    app_window_module = importlib.import_module("frontend.AppFluentWindow")
    monkeypatch.setattr(
        app_window_module,
        "AppSettingsPage",
        lambda *_args, **_kwargs: settings_page,
    )

    original_language = Localizer.get_app_language()
    Localizer.set_app_language(BaseLanguage.Enum.EN)
    navigation = NavigationStub()
    fake_window = SimpleNamespace(
        navigationInterface=navigation,
        translation_page=object(),
        add_project_pages=lambda: None,
        add_workbench_pages=lambda: None,
        add_renpy_pages=lambda: None,
        add_task_pages=lambda: None,
        add_setting_pages=lambda: None,
        switchTo=lambda _page: None,
        switch_theme=lambda: None,
        open_app_settings_page=lambda: None,
        addSubInterface=lambda page, icon, title, position: localized_pages.append(
            (page, title)
        ),
        _refresh_update_indicator=lambda: None,
    )
    try:
        AppFluentWindow.add_pages(fake_window)

        bottom_text = {
            item["routeKey"]: item["widget"].text()
            for item in navigation.widgets
            if hasattr(item["widget"], "text")
        }
        assert bottom_text["theme_navigation_button"] == "Switch Theme"
        assert bottom_text["language_navigation_button"] == "Language"
        assert localized_pages == [(settings_page, "App Settings")]
    finally:
        Localizer.set_app_language(original_language)
