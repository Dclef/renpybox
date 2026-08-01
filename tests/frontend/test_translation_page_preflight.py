from types import SimpleNamespace

from base.Base import Base
from frontend.TranslationPage import TranslationPage, restore_resumable_translation_paths
from module.Renpy.ProjectPaths import RenpyProjectPaths, write_run_manifest
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.Quality.QualityTaskCoordinator import QualityTaskType
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


class _MetricCardStub:
    def __init__(self) -> None:
        self.unit = None
        self.value = None

    def set_unit(self, unit) -> None:
        self.unit = unit

    def set_value(self, value) -> None:
        self.value = value


def test_dashboard_never_displays_negative_remaining_values(monkeypatch) -> None:
    monkeypatch.setattr(Engine.get(), "get_status", lambda: Engine.Status.TRANSLATING)
    page = SimpleNamespace(
        data={"line": 14, "total_line": 9, "start_time": 100},
        time=_MetricCardStub(),
        remaining_time=_MetricCardStub(),
        line_card=_MetricCardStub(),
        remaining_line=_MetricCardStub(),
    )
    monkeypatch.setattr("frontend.TranslationPage.time.time", lambda: 160)

    TranslationPage.update_time(page, page.data)
    TranslationPage.update_line(page, page.data)

    assert page.remaining_time.value == "0"
    assert page.remaining_line.value == "0"


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


def test_quality_status_uses_explicit_task_name(monkeypatch) -> None:
    strings = SimpleNamespace(
        translation_page_status_polishing = "AI 润色中",
        translation_page_status_proofreading = "AI 校对中",
        translation_page_status_stopping_polishing = "正在停止 AI 润色",
        translation_page_status_stopping_proofreading = "正在停止 AI 校对",
        translation_page_status_quality = "质量处理中",
    )
    monkeypatch.setattr("frontend.TranslationPage.Localizer.get", lambda: strings)

    assert TranslationPage._quality_status_label({
        "task_type": QualityTaskType.POLISHER.value,
    }) == "AI 润色中"
    assert TranslationPage._quality_status_label({
        "task_type": QualityTaskType.PROOFREADER.value,
    }) == "AI 校对中"
    assert TranslationPage._quality_status_label({
        "task_type": QualityTaskType.POLISHER.value,
        "cancel_requested": True,
    }) == "正在停止 AI 润色"


def test_main_page_stop_cancels_quality_task_without_translation_event(monkeypatch) -> None:
    class ActionStub:
        def __init__(self) -> None:
            self.enabled = True

        def setEnabled(self, enabled: bool) -> None:
            self.enabled = enabled

    progress = SimpleNamespace(as_dict = lambda: {
        "task_type": QualityTaskType.POLISHER.value,
        "cancel_requested": True,
    })
    coordinator = SimpleNamespace(
        cancel = lambda: True,
        get_progress = lambda: progress,
    )
    strings = SimpleNamespace(
        translation_page_status_stopping_polishing = "正在停止 AI 润色",
    )
    monkeypatch.setattr(Engine.get(), "get_status", lambda: Engine.Status.QUALITY)
    monkeypatch.setattr("frontend.TranslationPage.Localizer.get", lambda: strings)
    monkeypatch.setattr(
        "frontend.TranslationPage.QualityTaskCoordinator.get",
        lambda: coordinator,
    )
    page = SimpleNamespace(
        data = {},
        action_stop = ActionStub(),
        events = [],
        labels = [],
        emit = lambda event, payload: page.events.append((event, payload)),
        update_status = lambda data: None,
        indeterminate_show = lambda label: page.labels.append(label),
        _quality_status_label = TranslationPage._quality_status_label,
    )

    TranslationPage._on_stop_clicked(page, None)

    assert page.action_stop.enabled is False
    assert page.events == []
    assert page.data["quality_task"]["cancel_requested"] is True
    assert page.labels == ["正在停止 AI 润色"]


def test_quality_status_enables_main_page_stop_button(monkeypatch) -> None:
    class ActionStub:
        def __init__(self) -> None:
            self.enabled = None

        def setEnabled(self, enabled: bool) -> None:
            self.enabled = enabled

    actions = [ActionStub() for _ in range(6)]
    page = SimpleNamespace(
        data = {"quality_task": {"cancel_requested": False}},
        action_start = actions[0],
        action_stop = actions[1],
        action_export = actions[2],
        action_reinject_cache = actions[3],
        action_continue = actions[4],
        action_retry_failed = actions[5],
    )
    monkeypatch.setattr(Engine.get(), "get_status", lambda: Engine.Status.QUALITY)

    TranslationPage.update_button_status(page, Base.Event.TRANSLATION_UPDATE, {})

    assert page.action_stop.enabled is True
    assert page.action_start.enabled is False
    assert page.action_export.enabled is False


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
def test_resume_restores_incremental_input_and_output_from_manifest(tmp_path) -> None:
    project = tmp_path / "fictional-game"
    main_input = project / "game" / "tl" / "chinese"
    delta_input = project / "game" / "tl" / "chinese_new"
    delta_output = project / "RenpyBox_Translation" / "chinese_new"
    main_input.mkdir(parents=True)
    delta_input.mkdir(parents=True)
    cache = delta_output / "cache"
    cache.mkdir(parents=True)
    (cache / "items.json").write_text("[]", encoding="utf-8")
    (cache / "project.json").write_text("{}", encoding="utf-8")

    paths = RenpyProjectPaths.from_path(project, "chinese")
    assert paths is not None
    write_run_manifest(
        paths,
        delta_output,
        input_folder=delta_input,
        application_target_dir=main_input,
        run_kind="incremental",
    )
    config = Config(
        renpy_project_path=str(project),
        renpy_game_folder=str(project),
        renpy_tl_folder=str(main_input),
        input_folder=str(main_input),
        output_folder=str(paths.translation_output_dir),
    )

    restored = restore_resumable_translation_paths(config)

    assert restored.input_folder == str(delta_input.resolve())
    assert restored.output_folder == str(delta_output.resolve())
