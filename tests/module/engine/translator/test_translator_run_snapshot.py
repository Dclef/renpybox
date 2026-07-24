import json
import threading

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Cache.CacheManager import CacheManager
from module.Config import Config
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
