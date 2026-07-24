from types import SimpleNamespace

from base.Base import Base
from frontend.TranslationPage import TranslationPage
from module.Config import Config
from module.Engine.Translator.TranslationTaskContext import ProjectAssets


class _PageStub:
    def __init__(self) -> None:
        self.events = []
        self.workbench_opened = False

    def emit(self, event, payload) -> None:
        self.events.append((event, payload))

    def _open_workbench(self, window) -> None:
        del window
        self.workbench_opened = True


class _SignalStub:
    def __init__(self) -> None:
        self.callback = None

    def connect(self, callback) -> None:
        self.callback = callback

    def emit(self) -> None:
        if self.callback is not None:
            self.callback()


def _install_assets(monkeypatch, assets: ProjectAssets) -> None:
    config = SimpleNamespace(output_folder = "output", cache_use_sqlite = True)
    monkeypatch.setattr(Config, "load", lambda self: config)
    repository = SimpleNamespace(load = lambda legacy: SimpleNamespace(assets = assets))
    monkeypatch.setattr(
        "frontend.TranslationPage.ProjectAssetsRepository.from_config",
        lambda current: repository,
    )


def test_new_start_marks_successful_asset_preflight_as_confirmed(monkeypatch) -> None:
    assets = ProjectAssets.from_dict({
        "glossary": {
            "enabled": True,
            "items": [{"source": "Alice", "target": "爱丽丝"}],
        },
    })
    _install_assets(monkeypatch, assets)
    page = _PageStub()

    started = TranslationPage._request_translation_start(
        page,
        Base.TranslationStatus.UNTRANSLATED,
        None,
    )

    assert started is True
    assert page.events == [(
        Base.Event.TRANSLATION_START,
        {
            "status": Base.TranslationStatus.UNTRANSLATED,
            "preflight_confirmed": True,
        },
    )]


def test_missing_assets_can_open_workbench_without_starting(monkeypatch) -> None:
    _install_assets(monkeypatch, ProjectAssets())

    class MessageBoxStub:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs
            self.yesButton = SimpleNamespace(setText = lambda text: None)
            self.cancelButton = SimpleNamespace(setText = lambda text: None)
            self.cancelSignal = _SignalStub()

        def exec(self) -> bool:
            return True

    monkeypatch.setattr("frontend.TranslationPage.MessageBox", MessageBoxStub)
    page = _PageStub()

    started = TranslationPage._request_translation_start(
        page,
        Base.TranslationStatus.UNTRANSLATED,
        None,
    )

    assert started is False
    assert page.workbench_opened is True
    assert page.events == []


def test_missing_assets_continue_emits_one_confirmed_start(monkeypatch) -> None:
    _install_assets(monkeypatch, ProjectAssets())

    class MessageBoxStub:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs
            self.yesButton = SimpleNamespace(setText = lambda text: None)
            self.cancelButton = SimpleNamespace(setText = lambda text: None)
            self.cancelSignal = _SignalStub()

        def exec(self) -> bool:
            self.cancelSignal.emit()
            return False

    monkeypatch.setattr("frontend.TranslationPage.MessageBox", MessageBoxStub)
    page = _PageStub()

    started = TranslationPage._request_translation_start(
        page,
        Base.TranslationStatus.UNTRANSLATED,
        None,
    )

    assert started is True
    assert len(page.events) == 1
    assert page.events[0][1]["preflight_confirmed"] is True
