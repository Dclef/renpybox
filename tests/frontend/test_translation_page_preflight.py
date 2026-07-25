from types import SimpleNamespace

from base.Base import Base
from frontend.TranslationPage import TranslationPage
from module.Config import Config
from module.Engine.Engine import Engine
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


class _RuntimeSignalStub:
    def __init__(self) -> None:
        self.events = []

    def emit(self, event, data) -> None:
        self.events.append((event, data))


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


def test_quality_update_preserves_translation_dashboard_progress() -> None:
    page = SimpleNamespace(
        data = {
            "line": 12,
            "total_line": 20,
            "total_output_tokens": 88,
        },
        runtime_status_updated = _RuntimeSignalStub(),
    )
    payload = {
        "quality_task": {
            "completed_count": 2,
            "total_count": 4,
        },
    }

    TranslationPage.translation_update(page, Base.Event.TRANSLATION_UPDATE, payload)

    assert page.data["line"] == 12
    assert page.data["total_line"] == 20
    assert page.data["total_output_tokens"] == 88
    assert page.data["quality_task"] == payload["quality_task"]
    assert page.runtime_status_updated.events == [(
        Base.Event.TRANSLATION_UPDATE,
        page.data,
    )]


def test_idle_dashboard_uses_frozen_elapsed_time(monkeypatch) -> None:
    """翻译结束后累计时间必须保持缓存快照，不能随系统时间继续增长。"""
    class CardStub:
        def __init__(self) -> None:
            self.value = None
            self.unit = None

        def set_value(self, value) -> None:
            self.value = value

        def set_unit(self, unit) -> None:
            self.unit = unit

    page = SimpleNamespace(
        data={
            "start_time": 1,
            "time": 7,
            "line": 0,
            "total_line": 0,
        },
        time=CardStub(),
        remaining_time=CardStub(),
    )
    monkeypatch.setattr(Engine.get(), "get_status", lambda: Engine.Status.IDLE)
    monkeypatch.setattr("frontend.TranslationPage.time.time", lambda: 9999)

    TranslationPage.update_time(page, page.data)

    assert page.time.value == "7"
    assert page.time.unit == "S"
    assert page.remaining_time.value == "0"


def test_token_estimate_dialog_uses_page_as_parent(monkeypatch) -> None:
    """Token 估算弹窗不能把 QWidget.window 方法误当成父控件。"""
    captured = {}

    class ActionStub:
        def setEnabled(self, enabled) -> None:
            captured["enabled"] = enabled

    class ButtonStub:
        def setText(self, text) -> None:
            captured["button_text"] = text

        def hide(self) -> None:
            captured["cancel_hidden"] = True

    class MessageBoxStub:
        def __init__(self, title, content, parent) -> None:
            captured["title"] = title
            captured["content"] = content
            captured["parent"] = parent
            self.yesButton = ButtonStub()
            self.cancelButton = ButtonStub()

        def exec(self) -> None:
            captured["executed"] = True

    page = SimpleNamespace(
        _token_estimate_running=True,
        action_estimate=ActionStub(),
        emit=lambda *args: None,
    )
    result = SimpleNamespace(
        untranslated_count=10,
        batch_count=2,
        total_source_tokens=100,
        estimated_input_tokens=200,
        estimated_output_tokens=50,
        estimated_cost=0,
    )
    monkeypatch.setattr("frontend.TranslationPage.MessageBox", MessageBoxStub)

    TranslationPage._on_token_estimate_done(page, result, "")

    assert captured["parent"] is page
    assert captured["executed"] is True
    assert captured["enabled"] is True
