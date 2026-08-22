import json
import threading
from types import SimpleNamespace

import pytest

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.Engine.Translator.TranslationTaskContext import ProjectAssets
from module.Engine.Translator.Translator import Translator
from module.Renpy.ProjectPaths import RenpyProjectPaths, read_run_manifest, write_run_manifest


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


def test_round_progress_keeps_prefiltered_rows_inside_total() -> None:
    translator = _translator()
    translator.extras = {"line": 0, "total_line": 12}

    translator._reconcile_round_progress(remaining=8, fresh_run=True)

    assert translator.extras["line"] == 4
    assert translator.extras["total_line"] == 12


def test_resumed_round_progress_uses_completed_plus_remaining() -> None:
    translator = _translator()
    translator.extras = {"line": 5, "total_line": 12}

    translator._reconcile_round_progress(remaining=3, fresh_run=False)

    assert translator.extras["line"] == 5
    assert translator.extras["total_line"] == 8


def test_verify_uppercase_untranslated_only_excludes_double_unchanged(
    tmp_path, monkeypatch
) -> None:
    """第二次整体翻译验证：两次都未被翻译才判定不译，翻译过/请求失败不误判。"""
    from module.Engine.Translator.Translator import Translator

    items = [
        CacheItem(src="TBD", dst="TBD", status=Base.TranslationStatus.UNTRANSLATED),
        CacheItem(src="GO", dst="GO", status=Base.TranslationStatus.UNTRANSLATED),
        CacheItem(src="ART", dst="ART", status=Base.TranslationStatus.UNTRANSLATED),
        CacheItem(src="Hello", dst="Hello", status=Base.TranslationStatus.UNTRANSLATED),
    ]
    config = Config(
        source_language=BaseLanguage.Enum.EN,
        target_language=BaseLanguage.Enum.ZH,
    )
    translator = Translator.__new__(Translator)
    translator.cache_manager = SimpleNamespace(get_items=lambda: items)
    translator.config = config
    translator.task_context = SimpleNamespace(to_runtime_config=lambda cfg: cfg)
    translator.platform = {"name": "test"}
    translator.data_lock = threading.Lock()
    translator.logger = SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        debug=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )
    translator._should_stop_requested = lambda *a, **k: False
    translator._merge_analysis_candidates_for_run = lambda *a, **k: None
    translator._record_verified_declined = lambda items: None

    class FakeTask:
        def __init__(
            self,
            task_context,
            platform,
            local_flag,
            items,
            precedings,
            runtime_config=None,
            candidate_sink=None,
        ):
            self.items = items

        def start(self, round_index):
            for item in self.items:
                if item.get_src() == "GO":
                    # 第二次被 AI 翻译 → 保留译文
                    item.set_dst("去")
                    item.set_status(Base.TranslationStatus.TRANSLATED)
                elif item.get_src() == "ART":
                    # 第二次请求失败（空响应）→ 不是“未翻译”证据
                    item.set_dst("")
                # TBD 第二次仍干净返回原文

    monkeypatch.setattr(
        "module.Engine.Translator.Translator.TranslatorTask", FakeTask
    )

    excluded = translator._verify_uppercase_untranslated(None, None, 1, True)

    assert excluded == 1
    statuses = {item.get_src(): item.get_status() for item in items}
    assert statuses["TBD"] == Base.TranslationStatus.EXCLUDED
    assert statuses["GO"] == Base.TranslationStatus.TRANSLATED
    assert statuses["ART"] == Base.TranslationStatus.UNTRANSLATED
    assert statuses["Hello"] == Base.TranslationStatus.UNTRANSLATED


def test_verify_uppercase_candidates_can_be_disabled(monkeypatch) -> None:
    item = CacheItem(
        src="TBD",
        dst="TBD",
        status=Base.TranslationStatus.UNTRANSLATED,
    )
    translator = Translator.__new__(Translator)
    translator.config = Config(renpy_verify_uppercase_candidates=False)
    translator.cache_manager = SimpleNamespace(get_items=lambda: [item])

    class UnexpectedTask:
        def __init__(self, *args, **kwargs):
            raise AssertionError("关闭开关后不应构造二次验证任务")

    monkeypatch.setattr(
        "module.Engine.Translator.Translator.TranslatorTask",
        UnexpectedTask,
    )

    assert translator._verify_uppercase_untranslated(None, None, 1, True) == 0
    assert item.get_status() == Base.TranslationStatus.UNTRANSLATED


def test_verify_uppercase_candidates_defaults_to_enabled() -> None:
    assert Config().renpy_verify_uppercase_candidates is True


def test_verify_uppercase_50_word_case(tmp_path, monkeypatch) -> None:
    """50 词真实案例：25 个需要翻译 + 25 个不需要翻译。

    需要翻译的词由 AI 在第一次或第二次整体翻译中译出；不需要翻译的词
    两次 AI 都原样返回，最终判定不译并连同文件溯源写入项目清单。
    """
    from module.Engine.Translator.Translator import Translator

    TRANSLATE = {
        "GO": "出发", "DAD": "爸爸", "MOM": "妈妈", "HI": "嗨",
        "ART": "美术", "CODE": "代码", "PIN": "密码", "SENT": "已发送",
        "SPAM": "垃圾邮件", "OK": "确定", "IT": "它", "TBD": "待定",
        "AM": "上午", "PM": "下午", "HR": "小时", "OPEN": "打开",
        "EDIT": "编辑", "SAVE": "保存", "LOAD": "读取", "STOP": "停止",
        "PLAY": "播放", "NEXT": "下一个", "HOME": "主页", "SEND": "发送",
        "DAY": "天",
    }
    MISSED_IN_PASS1 = {"TBD", "AM", "HR", "SENT"}
    KEEP = {
        "ATK", "DEF", "SPD", "INT", "STR", "VIT", "AGI", "MAG", "RES",
        "CRT", "CDR", "LUK", "MDEF", "PDEF", "ASPD", "MCRT", "DPS",
        "HPS", "TIC", "BUF", "DEB", "AOE", "CD", "GCD", "TP",
    }
    assert len(TRANSLATE) == 25
    assert len(KEEP) == 25

    # 模拟一个真实项目结构，供溯源记录解析项目根目录
    project = tmp_path / "fictional-game"
    tl_dir = project / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    files = [
        "src/menu/lewd.rpy",
        "src/menu/pref.rpy",
        "src/menu/logs.rpy",
        "src/gui/tel.rpy",
        "renpybox_bytecode_strings.rpy",
    ]

    items = []
    all_words = list(TRANSLATE) + list(KEEP)
    for index, word in enumerate(all_words):
        items.append(
            CacheItem.from_dict(
                {
                    "src": word,
                    "dst": word,
                    "status": Base.TranslationStatus.UNTRANSLATED,
                    "file_path": files[index % len(files)],
                    "text_type": CacheItem.TextType.RENPY,
                }
            )
        )

    config = Config(
        source_language=BaseLanguage.Enum.EN,
        target_language=BaseLanguage.Enum.ZH,
        input_folder=str(tl_dir),
        output_folder=str(tl_dir),
    )
    translator = Translator.__new__(Translator)
    translator.cache_manager = SimpleNamespace(get_items=lambda: items)
    translator.config = config
    translator.task_context = SimpleNamespace(to_runtime_config=lambda cfg: cfg)
    translator.platform = {"name": "test"}
    translator.data_lock = threading.Lock()
    translator.logger = SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        debug=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )
    translator._should_stop_requested = lambda *a, **k: False
    translator._merge_analysis_candidates_for_run = lambda *a, **k: None

    # 第一次整体翻译：25 个需要翻译的词中 21 个被译出，4 个漏译；
    # 25 个不需要翻译的词第一次原样返回。
    for item in items:
        word = item.get_src()
        if word in TRANSLATE and word not in MISSED_IN_PASS1:
            item.set_dst(TRANSLATE[word])
            item.set_status(Base.TranslationStatus.TRANSLATED)

    class FakeVerificationTask:
        def __init__(
            self,
            task_context,
            platform,
            local_flag,
            items,
            precedings,
            runtime_config=None,
            candidate_sink=None,
        ):
            self.items = items

        def start(self, round_index):
            for item in self.items:
                word = item.get_src()
                if word in MISSED_IN_PASS1:
                    # 第二次整体翻译把漏译的词译出 → 保留译文
                    item.set_dst(TRANSLATE[word])
                    item.set_status(Base.TranslationStatus.TRANSLATED)
                # 25 个不需要翻译的词第二次仍原样返回

    monkeypatch.setattr(
        "module.Engine.Translator.Translator.TranslatorTask", FakeVerificationTask
    )

    excluded = translator._verify_uppercase_untranslated(None, None, 1, True)

    assert excluded == 25
    statuses = {item.get_src(): item.get_status() for item in items}
    for word in TRANSLATE:
        assert statuses[word] == Base.TranslationStatus.TRANSLATED, word
    for word in KEEP:
        assert statuses[word] == Base.TranslationStatus.EXCLUDED, word

    # 判定不译清单：25 条，且每条都带文件溯源
    declined_file = (
        project / "RenpyBox_Translation" / ".renpybox_declined_chinese.json"
    )
    assert declined_file.exists()
    payload = json.loads(declined_file.read_text(encoding="utf-8"))
    assert set(payload["declined"]) == KEEP
    assert set(payload.get("sources", {})) == KEEP
    for word in KEEP:
        assert payload["sources"][word].endswith(".rpy")


def test_runtime_manifest_preserves_incremental_scope_on_resume(tmp_path) -> None:
    project = tmp_path / "fictional-game"
    main_input = project / "game" / "tl" / "chinese"
    delta_input = project / "game" / "tl" / "chinese_new"
    delta_output = project / "RenpyBox_Translation" / "chinese_new"
    main_input.mkdir(parents=True)
    delta_input.mkdir(parents=True)
    delta_output.mkdir(parents=True)
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
        input_folder=str(delta_input),
        output_folder=str(delta_output),
        renpy_source_translate=False,
        renpy_hook_translate=False,
    )

    Translator._remember_runtime_manifest(config)

    manifest = read_run_manifest(paths)
    assert manifest is not None
    assert manifest["run_kind"] == "incremental"
    assert manifest["input_folder"] == str(delta_input.resolve())
    assert manifest["output_folder"] == str(delta_output.resolve())
    assert manifest["application_target_dir"] == str(main_input.resolve())


def test_resume_completes_allowed_acronym_but_not_translatable_ui_word() -> None:
    translator = _translator()
    translator.config = Config(glossary_data=[])
    usb = CacheItem(src="USB", dst="USB", status=Base.TranslationStatus.UNTRANSLATED)
    start = CacheItem(src="START", dst="START", status=Base.TranslationStatus.UNTRANSLATED)

    accepted = translator.accept_preserved_untranslated_items([usb, start])

    assert accepted == 1
    assert usb.get_status() == Base.TranslationStatus.TRANSLATED
    assert start.get_status() == Base.TranslationStatus.UNTRANSLATED


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


def test_resume_provider_follows_stable_identity_after_numeric_reorder() -> None:
    persisted = {
        "request_policy": {
            "provider": {
                "id": 3,
                "credential_id": "a" * 32,
                "model": "snapshot-model",
            },
        },
    }
    config = Config(platforms=[{
        "id": 9,
        "credential_id": "a" * 32,
        "model": "current-model",
        "api_key": ["current-key"],
    }])

    provider = Translator._get_resume_runtime_provider(persisted, config)

    assert provider["id"] == 3
    assert provider["model"] == "snapshot-model"
    assert provider["api_key"] == ["current-key"]


def test_resume_provider_rejects_reused_numeric_id_with_new_identity() -> None:
    persisted = {
        "request_policy": {
            "provider": {
                "id": 3,
                "credential_id": "a" * 32,
                "model": "snapshot-model",
            },
        },
    }
    config = Config(platforms=[{
        "id": 3,
        "credential_id": "b" * 32,
        "api_key": ["other-key"],
    }])

    with pytest.raises(ValueError, match="接口已不存在"):
        Translator._get_resume_runtime_provider(persisted, config)


def test_legacy_snapshot_uses_explicit_legacy_identity_alias() -> None:
    persisted = {
        "request_policy": {
            "provider": {"id": 3, "model": "snapshot-model"},
        },
    }
    config = Config(platforms=[{
        "id": 8,
        "credential_id": "a" * 32,
        "legacy_credential_id": "3",
        "api_key": ["current-key"],
    }])

    provider = Translator._get_resume_runtime_provider(persisted, config)

    assert provider["model"] == "snapshot-model"
    assert provider["api_key"] == ["current-key"]
