import json
import threading
from types import SimpleNamespace

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Cache.CacheManager import CacheManager
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.Engine.Translator.TranslationTaskContext import ProjectAssets
from module.Engine.Translator.Translator import Translator


def _platform(*, model: str, api_key: str, api_url: str = "https://old.invalid/v1") -> dict:
    return {
        "id": 3,
        "name": "test",
        "api_url": api_url,
        "api_key": [api_key],
        "api_format": Base.APIFormat.OPENAI,
        "model": model,
        "temperature": 0.2,
    }


def _config(input_folder, output_folder, *, model: str, api_key: str) -> Config:
    return Config(
        cache_use_sqlite = False,
        input_folder = str(input_folder),
        output_folder = str(output_folder),
        source_language = BaseLanguage.Enum.EN,
        target_language = BaseLanguage.Enum.ZH,
        token_threshold = 24,
        translation_prompt_mode = Config.PROMPT_MODE_COT,
        translation_style_id = Config.STYLE_LITERARY,
        glossary_enable = True,
        glossary_data = [{"src": "Alice", "dst": "爱丽丝", "info": "name"}],
        activate_platform = 3,
        platforms = [_platform(model = model, api_key = api_key)],
    )


def _translator() -> Translator:
    translator = Translator.__new__(Translator)
    translator.cache_manager = CacheManager(service = False)
    translator.data_lock = threading.Lock()
    return translator


def test_continue_reuses_snapshot_semantics_and_only_refreshes_credentials(tmp_path) -> None:
    input_folder = tmp_path / "input"
    output_folder = tmp_path / "output"
    input_folder.mkdir()
    (input_folder / "story.txt").write_text("Hello", encoding = "utf-8")

    initial = _config(input_folder, output_folder, model = "old-model", api_key = "old-key")
    first = _translator()
    original_context = first._initialize_translation_run(
        initial,
        Base.TranslationStatus.UNTRANSLATED,
        {"preflight_confirmed": True},
    )

    changed = _config(input_folder, output_folder, model = "new-model", api_key = "new-key")
    changed.token_threshold = 99
    changed.translation_prompt_mode = Config.PROMPT_MODE_LOCAL
    changed.translation_style_id = Config.STYLE_R18
    changed.platforms[0]["api_url"] = "https://new.invalid/v1"
    resumed = _translator()
    resumed_context = resumed._initialize_translation_run(
        changed,
        Base.TranslationStatus.TRANSLATING,
        {"preflight_confirmed": True},
    )
    runtime = resumed_context.to_runtime_config(changed)
    runtime_platform = runtime.get_platform(runtime.activate_platform)

    assert resumed_context.snapshot_id == original_context.snapshot_id
    assert resumed_context.prompt["mode"] == Config.PROMPT_MODE_COT
    assert resumed_context.prompt["style_id"] == Config.STYLE_LITERARY
    assert runtime.token_threshold == 24
    assert runtime_platform["model"] == "old-model"
    assert runtime_platform["api_url"] == "https://old.invalid/v1"
    assert runtime_platform["api_key"] == ["new-key"]

    persisted = resumed.cache_manager.get_project().get_translation_snapshot()
    serialized = json.dumps(persisted, ensure_ascii = False)
    assert "old-key" not in serialized
    assert "new-key" not in serialized
    assert "api_key" not in serialized


def test_restart_replaces_run_data_but_preserves_project_assets_and_candidates(tmp_path) -> None:
    input_folder = tmp_path / "input"
    output_folder = tmp_path / "output"
    input_folder.mkdir()
    source_path = input_folder / "story.txt"
    source_path.write_text("First", encoding = "utf-8")

    config = _config(input_folder, output_folder, model = "model", api_key = "key")
    first = _translator()
    first_context = first._initialize_translation_run(
        config,
        Base.TranslationStatus.UNTRANSLATED,
        {"preflight_confirmed": True},
    )
    project = first.cache_manager.get_project()
    project_id = project.get_id()
    project.set_analysis_candidates({
        "schema_version": 1,
        "items": [{"source": "Bob", "target": "鲍勃", "origin": "ANALYSIS"}],
    })
    first.cache_manager.save_to_file(
        project,
        first.cache_manager.get_items(),
        str(output_folder),
    )

    source_path.write_text("Second", encoding = "utf-8")
    config.translation_prompt_mode = Config.PROMPT_MODE_THINK
    restarted = _translator()
    second_context = restarted._initialize_translation_run(
        config,
        Base.TranslationStatus.UNTRANSLATED,
        {"preflight_confirmed": True},
    )
    restarted_project = restarted.cache_manager.get_project()

    assert restarted_project.get_id() == project_id
    assert restarted_project.get_project_assets() == project.get_project_assets()
    assert restarted_project.get_analysis_candidates()["items"][0]["source"] == "Bob"
    assert [item.get_src() for item in restarted.cache_manager.get_items()] == ["Second"]
    assert second_context.snapshot_id != first_context.snapshot_id
    assert restarted_project.get_progress()["line"] == 0


def test_load_project_assets_prefers_newer_stable_revision(tmp_path, monkeypatch) -> None:
    """增量运行缓存较旧时，翻译上下文必须采用主工作台最新资产。"""
    config = _config(tmp_path / "input", tmp_path / "output", model = "model", api_key = "key")
    (tmp_path / "input").mkdir()

    runtime_project = CacheManager(service = False).get_project()
    runtime_project.set_project_assets({
        "revision": 2,
        "character_cards": {
            "enabled": True,
            "items": [{"name": "Alice", "name_translation": "旧爱丽丝"}],
        },
    })
    translator = _translator()
    translator.cache_manager.set_project(runtime_project)

    stable_assets = ProjectAssets.from_dict({
        "revision": 6,
        "character_cards": {
            "enabled": True,
            "items": [{"name": "Alice", "name_translation": "新爱丽丝"}],
        },
        "worldbook": {
            "enabled": True,
            "data": {"setting": "新世界观"},
        },
    })
    repository = SimpleNamespace(
        load = lambda _legacy_config: SimpleNamespace(assets = stable_assets),
    )
    monkeypatch.setattr(
        ProjectAssetsRepository,
        "from_config",
        staticmethod(lambda _config: repository),
    )

    loaded = translator._load_project_assets(config)

    assert loaded.revision == 6
    assert loaded.character_cards[0]["name_translation"] == "新爱丽丝"
    assert loaded.worldbook["setting"] == "新世界观"
    assert translator.cache_manager.get_project().get_project_assets()["revision"] == 6


def test_translation_start_binds_runtime_output_before_run_initialization(
    tmp_path,
    monkeypatch,
) -> None:
    config = Config(output_folder = str(tmp_path), renpy_source_translate = False)
    translator = _translator()
    translator._last_runtime_output_folder = "old-output"
    translator._active_cache_output_folder = "old-output"

    monkeypatch.setattr(translator, "_copy_entry_config", lambda data: config)
    monkeypatch.setattr(translator, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(translator, "error", lambda *args, **kwargs: None)

    def stop_after_binding(*args, **kwargs):
        assert translator._last_runtime_output_folder == str(tmp_path)
        assert translator._active_cache_output_folder == ""
        raise RuntimeError("stop after binding check")

    monkeypatch.setattr(translator, "_initialize_translation_run", stop_after_binding)

    translator.translation_start_task(
        Base.Event.TRANSLATION_START,
        {"status": Base.TranslationStatus.UNTRANSLATED},
    )

    assert translator._last_runtime_output_folder == str(tmp_path)
    assert translator._active_cache_output_folder == ""


def test_no_items_finishes_without_emitting_stop(monkeypatch) -> None:
    """空数据属于启动失败，不能显示成用户主动停止任务。"""
    translator = _translator()
    translator.cache_manager.get_project().set_progress({
        "start_time": 100,
        "time": 0,
        "total_line": 0,
        "line": 0,
    })
    events = []
    monkeypatch.setattr(translator, "emit", lambda event, data: events.append((event, data)))
    engine = Engine.get()
    previous_status = engine.get_status()
    engine.set_status(engine.Status.TRANSLATING)
    try:
        translator._finish_no_items_run(None)
    finally:
        engine.set_status(previous_status)

    assert all(event != Base.Event.TRANSLATION_STOP for event, _ in events)
    assert events[-1][0] == Base.Event.TRANSLATION_DONE
    assert events[-1][1]["error"] == "NO_ITEMS"
    assert events[-1][1]["no_items"] is True


def test_resume_provider_only_overlays_current_credentials() -> None:
    persisted = {
        "request_policy": {
            "provider": {
                "id": 3,
                "model": "snapshot-model",
                "api_url": "https://old-user:old-pass@snapshot.invalid/v1",
                "headers": {
                    "Authorization": "Bearer stale-secret",
                    "X-Region": "snapshot-region",
                },
                "refresh_token": "stale-refresh",
            },
        },
    }
    config = Config(
        activate_platform = 3,
        platforms = [{
            "id": 3,
            "model": "current-model",
            "api_url": "https://current-user:current-pass@current.invalid/v2",
            "headers": {
                "Authorization": "Bearer current-secret",
                "X-Region": "current-region",
            },
            "refresh_token": "current-refresh",
        }],
    )

    provider = Translator._get_resume_runtime_provider(persisted, config)

    assert provider["model"] == "snapshot-model"
    assert provider["api_url"] == "https://current-user:current-pass@snapshot.invalid/v1"
    assert provider["headers"]["X-Region"] == "snapshot-region"
    assert provider["headers"]["Authorization"] == "Bearer current-secret"
    assert provider["refresh_token"] == "current-refresh"
