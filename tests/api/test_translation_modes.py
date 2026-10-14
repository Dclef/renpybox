"""工具箱翻译方式（mode=direct|source|supplement）在 /api/translation/start 上的契约。

不启动引擎/翻译线程：monkeypatch Engine.get、Config.load/save、EventManager.emit。
源码前置备份走真实 JobManager + 临时文件副作用。
"""
from __future__ import annotations

import copy
import dataclasses
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes import translation
from base.Base import Base
from base.BaseLanguage import BaseLanguage
from base.EventManager import EventManager
from module.Config import Config
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import RenpyProjectPaths


@pytest.fixture
def mode_app(tmp_path, monkeypatch):
    project = tmp_path / "Demo"
    game = project / "game"
    tl = game / "tl" / "chinese"
    tl.mkdir(parents=True)
    (tl / "script.rpy").write_text('translate chinese strings:\n    old "a"\n    new "a"\n', encoding="utf-8")
    source_in = tmp_path / "source_in"
    source_in.mkdir()

    config = Config()
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(tl)
    config.input_folder = str(tl)
    config.output_folder = str(tmp_path / "legacy_out")
    config.renpy_source_translate = False
    config.renpy_hook_translate = True
    config.renpy_backup_original = True
    config.auto_write_back = True
    config.target_language = BaseLanguage.Enum.ZH
    config.source_language = BaseLanguage.Enum.EN
    config.traditional_chinese_enable = False

    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))

    save_calls: list[dict] = []
    last_saved: dict = {"config": None}

    def save(self, path=None, *, strict=False):
        snapshot = copy.deepcopy(self)
        last_saved["config"] = snapshot
        save_calls.append(dataclasses.asdict(snapshot))
        return self

    def load(self, path=None):
        src = last_saved["config"] if last_saved["config"] is not None else config
        for field in dataclasses.fields(src):
            setattr(self, field.name, copy.deepcopy(getattr(src, field.name)))
        return self

    monkeypatch.setattr(Config, "save", save)
    monkeypatch.setattr(Config, "load", load)

    emitted: list[tuple] = []

    def emit(self, event, data=None):
        emitted.append((event, data))
        # 模拟 Translator 同步 START_RESULT，供 source 备份 job 等待真值。
        if event == Base.Event.TRANSLATION_START:
            payload = data if isinstance(data, dict) else {}
            EventManager.get().process_event(
                Base.Event.TRANSLATION_START_RESULT,
                {
                    "accepted": True,
                    "request_id": str(payload.get("request_id") or ""),
                    "run_id": 1,
                },
            )

    monkeypatch.setattr(EventManager, "emit", emit)

    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager(publish=None)

    @app.on_event("shutdown")
    def _shutdown():
        app.state.jobs.shutdown()

    app.include_router(translation.router)
    with TestClient(app) as client:
        yield {
            "client": client,
            "config": config,
            "engine": engine,
            "project": project,
            "game": game,
            "tl": tl,
            "tmp_path": tmp_path,
            "source_in": source_in,
            "save_calls": save_calls,
            "emitted": emitted,
            "last_saved": last_saved,
            "paths": RenpyProjectPaths.from_config(config),
            "app": app,
        }


def _wait_job(app, job_id: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = app.state.jobs.get(job_id)
        if job is not None and job.status.value in ("done", "failed", "cancelled"):
            return job.snapshot()
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} 未在超时内结束")


def _start(client, **extra):
    # UNTRANSLATED + preflight_confirmed：跳过缺资产拒绝，且不走续跑路径重绑 output。
    body = {
        "status": "UNTRANSLATED",
        "preflight_confirmed": True,
        "request_id": "mode-test",
        **extra,
    }
    return client.post("/api/translation/start", json=body)


def _translation_start_payload(emitted: list) -> dict:
    for event, data in emitted:
        if event == Base.Event.TRANSLATION_START:
            return data if isinstance(data, dict) else {}
    raise AssertionError(f"缺少 TRANSLATION_START：{[e for e, _ in emitted]}")


def _project_changed_events(emitted: list) -> list:
    return [data for event, data in emitted if event == Base.Event.PROJECT_CHANGED]


def test_mode_direct_writes_tl_paths_and_flags(mode_app):
    client = mode_app["client"]
    config = mode_app["config"]
    tl = mode_app["tl"]
    save_calls = mode_app["save_calls"]
    emitted = mode_app["emitted"]

    response = _start(
        client,
        mode="direct",
        target_language="EN",
        renpy_backup_original=False,
        auto_write_back=False,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] is True
    assert body["reason"] == "STARTED"
    assert len(save_calls) == 1
    assert config.input_folder == str(tl)
    assert config.output_folder == str(tl)
    assert config.renpy_source_translate is False
    assert config.renpy_hook_translate is False
    assert config.target_language == BaseLanguage.Enum.EN
    assert config.renpy_backup_original is False
    assert config.auto_write_back is False

    # 同项目可能因 apply_to_config 规范化触发广播；根路径不得漂到其它项目。
    for changed in _project_changed_events(emitted):
        assert Path(changed["project_root"]) == mode_app["project"]
    payload = _translation_start_payload(emitted)
    snapshot = payload["config"]
    assert snapshot.input_folder == str(tl)
    assert snapshot.output_folder == str(tl)
    assert snapshot.renpy_source_translate is False
    assert snapshot.renpy_hook_translate is False
    assert snapshot.target_language == BaseLanguage.Enum.EN
    assert snapshot.renpy_backup_original is False
    assert snapshot.auto_write_back is False


def test_mode_direct_tl_parent_always_appends_tl_name(mode_app, tmp_path):
    """tl_parent 始终拼接 tl_name，即使父目录 basename 与语言名相同。"""
    client = mode_app["client"]
    config = mode_app["config"]
    config.renpy_project_path = ""
    config.renpy_game_folder = ""
    config.renpy_tl_folder = ""

    tl_parent = tmp_path / "japanese"
    lang = tl_parent / "japanese"
    lang.mkdir(parents=True)
    (lang / "a.rpy").write_text("# ok\n", encoding="utf-8")

    response = _start(
        client,
        mode="direct",
        tl_parent=str(tl_parent),
        tl_name="japanese",
        target_language="JA",
    )
    assert response.status_code == 200, response.text
    assert Path(config.input_folder) == lang.resolve()
    assert Path(config.output_folder) == lang.resolve()


def test_mode_direct_custom_tl_paths_without_bound_project(mode_app, tmp_path):
    """显式 tl_parent + tl_name，不依赖事先绑定。"""
    client = mode_app["client"]
    config = mode_app["config"]
    # 清空绑定，强制走请求路径
    config.renpy_project_path = ""
    config.renpy_game_folder = ""
    config.renpy_tl_folder = ""

    other = tmp_path / "OtherGame"
    tl_parent = other / "game" / "tl"
    lang = tl_parent / "japanese"
    lang.mkdir(parents=True)
    (lang / "a.rpy").write_text("# ok\n", encoding="utf-8")

    response = _start(
        client,
        mode="direct",
        tl_parent=str(tl_parent),
        tl_name="japanese",
        target_language="JA",
    )
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] is True
    assert Path(config.input_folder) == lang.resolve()
    assert Path(config.output_folder) == lang.resolve()
    assert config.target_language == BaseLanguage.Enum.JA
    assert _project_changed_events(mode_app["emitted"])
    snapshot = _translation_start_payload(mode_app["emitted"])["config"]
    assert Path(snapshot.input_folder) == lang.resolve()


def test_mode_direct_traditional_chinese_enable(mode_app):
    client = mode_app["client"]
    config = mode_app["config"]

    response = _start(
        client,
        mode="direct",
        target_language="ZH",
        traditional_chinese_enable=True,
    )
    assert response.status_code == 200, response.text
    assert config.target_language == BaseLanguage.Enum.ZH
    assert config.traditional_chinese_enable is True
    snapshot = _translation_start_payload(mode_app["emitted"])["config"]
    assert snapshot.target_language == BaseLanguage.Enum.ZH
    assert snapshot.traditional_chinese_enable is True


def test_atomic_snapshot_rejects_assets_missing_without_save(mode_app, monkeypatch):
    """ASSETS_MISSING 拒绝时不得 save / 不得改 live / 不得 emit。"""
    client = mode_app["client"]
    config = mode_app["config"]
    before = (
        config.input_folder,
        config.output_folder,
        config.renpy_source_translate,
        config.renpy_hook_translate,
        config.target_language,
        config.traditional_chinese_enable,
    )

    class FakePreflight:
        should_prompt_for_missing_assets = True

    class FakeRepo:
        @classmethod
        def from_config(cls, _config):
            return cls()

        def load(self, _config):
            return type("S", (), {"assets": object()})()

    monkeypatch.setattr(
        "module.Engine.Translator.ProjectAssetsRepository.ProjectAssetsRepository",
        FakeRepo,
    )
    monkeypatch.setattr(
        "module.Engine.Translator.TranslationPreflightService.TranslationPreflightService.check",
        staticmethod(lambda _assets: FakePreflight()),
    )

    response = _start(
        client,
        mode="direct",
        target_language="EN",
        renpy_backup_original=False,
        preflight_confirmed=False,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] is False
    assert body["reason"] == "ASSETS_MISSING"
    assert mode_app["save_calls"] == []
    assert mode_app["emitted"] == []
    assert (
        config.input_folder,
        config.output_folder,
        config.renpy_source_translate,
        config.renpy_hook_translate,
        config.target_language,
        config.traditional_chinese_enable,
    ) == before


def test_atomic_snapshot_does_not_reload_config_for_payload(mode_app, monkeypatch):
    """受理快照必须用候选，禁止 Config().load() 污染。"""
    client = mode_app["client"]
    load_calls = {"n": 0}
    original_load = Config.load

    def counting_load(self, path=None):
        load_calls["n"] += 1
        return original_load(self, path)

    monkeypatch.setattr(Config, "load", counting_load)

    response = _start(client, mode="direct", target_language="KO")
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] is True
    assert load_calls["n"] == 0
    snapshot = _translation_start_payload(mode_app["emitted"])["config"]
    assert snapshot.target_language == BaseLanguage.Enum.KO


def test_mode_source_separates_io_and_enables_source(mode_app):
    client = mode_app["client"]
    config = mode_app["config"]
    source_in = mode_app["source_in"]
    expected_out = source_in.parent / f"{source_in.name}_source_out"
    save_calls = mode_app["save_calls"]
    emitted = mode_app["emitted"]

    response = _start(
        client,
        mode="source",
        input_folder=str(source_in),
        # 客户端伪造 output 必须被忽略
        output_folder=str(mode_app["tmp_path"] / "forged_out"),
        target_language="JA",
        source_language="EN",
        renpy_backup_original=False,
    )
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] is True
    assert len(save_calls) == 1
    assert Path(config.input_folder) == source_in.resolve()
    assert Path(config.output_folder) == expected_out.resolve()
    assert config.renpy_source_translate is True
    assert config.renpy_hook_translate is False
    assert config.target_language == BaseLanguage.Enum.JA
    assert config.renpy_backup_original is False
    # 源码只改 input/output/flags，绑定项目未变，不得编造 PROJECT_CHANGED。
    assert _project_changed_events(emitted) == []
    snapshot = _translation_start_payload(emitted)["config"]
    assert Path(snapshot.input_folder) == source_in.resolve()
    assert Path(snapshot.output_folder) == expected_out.resolve()
    assert snapshot.renpy_source_translate is True
    assert snapshot.renpy_hook_translate is False
    assert snapshot.target_language == BaseLanguage.Enum.JA
    assert snapshot.renpy_backup_original is False


def test_mode_source_default_output_path(mode_app, tmp_path):
    client = mode_app["client"]
    source_in = mode_app["source_in"]
    expected = source_in.parent / f"{source_in.name}_source_out"

    response = _start(
        client,
        mode="source",
        input_folder=str(source_in),
    )
    assert response.status_code == 200, response.text
    assert Path(mode_app["config"].output_folder) == expected.resolve()


def test_mode_source_local_bak_backup_via_job(mode_app):
    client = mode_app["client"]
    app = mode_app["app"]
    source_in = mode_app["source_in"]
    rpy = source_in / "story.rpy"
    rpy.write_text('label start:\n    "hi"\n', encoding="utf-8")

    response = _start(
        client,
        mode="source",
        input_folder=str(source_in),
        renpy_backup_original=True,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] is True
    assert body["stage"] == "backing_up"
    assert body["job"] and body["job"]["id"]
    job = _wait_job(app, body["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["translation_started"] is True
    bak = rpy.with_suffix(".rpy.bak")
    assert bak.is_file()
    assert bak.read_text(encoding="utf-8") == rpy.read_text(encoding="utf-8")
    assert mode_app["engine"].get_status() == Engine.Status.IDLE


def test_mode_source_external_backup_via_job(mode_app, tmp_path):
    client = mode_app["client"]
    app = mode_app["app"]
    source_in = mode_app["source_in"]
    rpy = source_in / "story.rpy"
    rpy.write_text('label start:\n    "hi"\n', encoding="utf-8")
    backup = tmp_path / "ext_backup"

    response = _start(
        client,
        mode="source",
        input_folder=str(source_in),
        external_backup_dir=str(backup),
        renpy_backup_original=False,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stage"] == "backing_up"
    job = _wait_job(app, body["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["translation_started"] is True
    assert (backup / "story.rpy").is_file()
    assert (backup / "story.rpy").read_text(encoding="utf-8") == rpy.read_text(encoding="utf-8")


def test_mode_source_cancel_keeps_backup_result(mode_app, tmp_path, monkeypatch):
    """取消发生在已备份之后：job.result 必须保留 copied/written_files。"""
    import threading

    from module.File import SourceBackup as sb

    client = mode_app["client"]
    app = mode_app["app"]
    source_in = mode_app["source_in"]
    for i in range(4):
        (source_in / f"f{i}.rpy").write_text(f"label l{i}:\n    pass\n", encoding="utf-8")
    backup = tmp_path / "cancel_bak"

    real_backup = sb.backup_source_rpy
    started = threading.Event()
    release = threading.Event()
    calls = {"n": 0}

    def gated_backup(*args, **kwargs):
        kwargs = dict(kwargs)
        user_progress = kwargs.get("progress_callback")

        def wrapped(current, total, message):
            nonlocal calls
            calls["n"] += 1
            if calls["n"] == 1:
                started.set()
                assert release.wait(5)
            if user_progress is not None:
                user_progress(current, total, message)

        kwargs["progress_callback"] = wrapped
        return real_backup(*args, **kwargs)

    monkeypatch.setattr("api.routes.translation.backup_source_rpy", gated_backup)

    response = _start(
        client,
        mode="source",
        input_folder=str(source_in),
        external_backup_dir=str(backup),
        renpy_backup_original=False,
        request_id="source-cancel-req",
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["job"]["id"]
    assert started.wait(3)

    # 协作取消 + 取消 runner：覆盖 CancelledError 后 shield 合并已备份结果
    assert app.state.jobs.cancel(job_id)
    task = app.state.jobs._tasks.get(job_id)
    assert task is not None
    task.get_loop().call_soon_threadsafe(task.cancel)
    release.set()

    job = _wait_job(app, job_id, timeout=8.0)
    assert job["status"] == "cancelled"
    result = job["result"] or {}
    assert int(result.get("copied") or 0) >= 1
    written = result.get("written_files") or []
    assert written
    assert result.get("translation_started") is False
    assert mode_app["engine"].get_status() == Engine.Status.IDLE


def test_mode_source_owner_mismatch_rejects_without_save(mode_app):
    client = mode_app["client"]
    before = mode_app["config"].input_folder

    response = _start(
        client,
        mode="source",
        input_folder=str(mode_app["source_in"]),
        project_key="someone-else|chinese",
        renpy_backup_original=False,
    )
    assert response.status_code == 409, response.text
    assert mode_app["save_calls"] == []
    assert mode_app["emitted"] == []
    assert mode_app["config"].input_folder == before


def test_mode_source_rejects_invalid_language_without_save(mode_app):
    client = mode_app["client"]
    before = mode_app["config"].target_language

    response = _start(
        client,
        mode="source",
        input_folder=str(mode_app["source_in"]),
        target_language="french",
    )
    assert response.status_code == 400, response.text
    assert "ZH" in response.json()["detail"] or "语言" in response.json()["detail"]
    assert mode_app["save_calls"] == []
    assert mode_app["emitted"] == []
    assert mode_app["config"].target_language is before


def test_mode_source_rejects_missing_input(mode_app, tmp_path):
    client = mode_app["client"]
    missing = tmp_path / "no_such_input"
    before = (
        mode_app["config"].input_folder,
        mode_app["config"].output_folder,
        mode_app["config"].renpy_source_translate,
    )

    response = _start(
        client,
        mode="source",
        input_folder=str(missing),
    )
    assert response.status_code == 400, response.text
    assert "不存在" in response.json()["detail"]
    assert mode_app["save_calls"] == []
    assert mode_app["emitted"] == []
    assert (
        mode_app["config"].input_folder,
        mode_app["config"].output_folder,
        mode_app["config"].renpy_source_translate,
    ) == before


def test_mode_source_rejects_non_rpy_file(mode_app, tmp_path):
    client = mode_app["client"]
    bad = tmp_path / "notes.txt"
    bad.write_text("x", encoding="utf-8")

    response = _start(
        client,
        mode="source",
        input_folder=str(bad),
    )
    assert response.status_code == 400, response.text
    assert ".rpy" in response.json()["detail"]
    assert mode_app["save_calls"] == []
    assert mode_app["emitted"] == []


def test_mode_source_derived_output_may_not_exist_yet(mode_app):
    """推导输出目录允许尚不存在（引擎会创建）。"""
    client = mode_app["client"]
    source_in = mode_app["source_in"]
    expected = source_in.parent / f"{source_in.name}_source_out"
    assert not expected.exists()

    response = _start(
        client,
        mode="source",
        input_folder=str(source_in),
        renpy_backup_original=False,
    )
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] is True
    assert Path(mode_app["config"].output_folder) == expected.resolve()


def test_mode_source_accepts_existing_rpy_file(mode_app, tmp_path):
    client = mode_app["client"]
    rpy = tmp_path / "script.rpy"
    rpy.write_text('label start:\n    "hi"\n', encoding="utf-8")
    expected = tmp_path / "script_source_out"

    response = _start(
        client,
        mode="source",
        input_folder=str(rpy),
        renpy_backup_original=False,
    )
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] is True
    assert Path(mode_app["config"].input_folder) == rpy.resolve()
    assert Path(mode_app["config"].output_folder) == expected.resolve()


def test_mode_supplement_preserves_configured_custom_tl(mode_app, tmp_path):
    client = mode_app["client"]
    config = mode_app["config"]
    project = tmp_path / "CustomTlProject"
    game = project / "game"
    game.mkdir(parents=True)
    custom_tl = project / "ExternalTranslations" / "chinese"
    custom_tl.mkdir(parents=True)
    (custom_tl / "script.rpy").write_text(
        'translate chinese strings:\n    old "a"\n    new "a"\n',
        encoding="utf-8",
    )
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(custom_tl)

    response = _start(
        client,
        mode="supplement",
        game_path=str(project),
        tl_name="chinese",
    )
    assert response.status_code == 200, response.text
    assert Path(config.input_folder) == custom_tl.resolve()
    assert Path(config.output_folder) == custom_tl.resolve()
    assert config.renpy_tl_folder == str(custom_tl.resolve())


def test_mode_supplement_sets_hook_flags(mode_app):
    client = mode_app["client"]
    config = mode_app["config"]
    tl = mode_app["tl"]
    project = mode_app["project"]

    response = _start(
        client,
        mode="supplement",
        game_path=str(project),
        tl_name="chinese",
        source_language="EN",
        target_language="ZH",
    )
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] is True
    assert Path(config.input_folder) == tl.resolve()
    assert Path(config.output_folder) == tl.resolve()
    assert config.renpy_source_translate is False
    assert config.renpy_hook_translate is True
    snapshot = _translation_start_payload(mode_app["emitted"])["config"]
    assert snapshot.renpy_hook_translate is True
    assert snapshot.renpy_source_translate is False


def test_mode_supplement_rejects_without_effective_tl(mode_app, tmp_path):
    client = mode_app["client"]
    project = tmp_path / "EmptyTl"
    game = project / "game"
    tl = game / "tl" / "chinese"
    tl.mkdir(parents=True)
    # 只有应忽略的文件
    (tl / "replace_text_auto.rpy").write_text("# auto\n", encoding="utf-8")
    (tl / "hook_runtime.rpy").write_text("# hook\n", encoding="utf-8")

    response = _start(
        client,
        mode="supplement",
        game_path=str(project),
        tl_name="chinese",
    )
    assert response.status_code == 400, response.text
    assert "有效 tl" in response.json()["detail"]
    assert mode_app["save_calls"] == []
    assert mode_app["emitted"] == []


def test_mode_hook_rejected_as_unknown_toolbox_mode(mode_app):
    """hook 已独立路由，mode=hook 必须 400。"""
    client = mode_app["client"]
    config = mode_app["config"]
    before_hook = config.renpy_hook_translate

    response = _start(client, mode="hook")
    assert response.status_code == 400, response.text
    assert "未知翻译方式" in response.json()["detail"]
    assert mode_app["save_calls"] == []
    assert mode_app["emitted"] == []
    assert config.renpy_hook_translate is before_hook


def test_mode_with_invalid_status_rejects_without_save_or_emit(mode_app):
    """带 mode 时若 status 非法，须在 mode 落盘之前就 400。"""
    client = mode_app["client"]
    config = mode_app["config"]
    source_in = mode_app["source_in"]
    before = (
        config.input_folder,
        config.output_folder,
        config.renpy_source_translate,
        config.renpy_hook_translate,
        config.target_language,
    )

    response = _start(
        client,
        status="NOT_A_REAL_STATUS",
        mode="source",
        input_folder=str(source_in),
        target_language="JA",
    )
    assert response.status_code == 400, response.text
    assert "未知翻译状态" in response.json()["detail"]
    assert mode_app["save_calls"] == []
    assert mode_app["emitted"] == []
    assert (
        config.input_folder,
        config.output_folder,
        config.renpy_source_translate,
        config.renpy_hook_translate,
        config.target_language,
    ) == before


def test_mode_source_rejects_when_derived_output_is_file(mode_app):
    """推导输出路径已存在且是文件时 400；不得 save / emit。"""
    client = mode_app["client"]
    config = mode_app["config"]
    source_in = mode_app["source_in"]
    derived = source_in.parent / f"{source_in.name}_source_out"
    derived.write_text("x", encoding="utf-8")
    before = (
        config.input_folder,
        config.output_folder,
        config.renpy_source_translate,
        config.renpy_hook_translate,
    )

    response = _start(
        client,
        mode="source",
        input_folder=str(source_in),
        renpy_backup_original=False,
    )
    assert response.status_code == 400, response.text
    assert "目录" in response.json()["detail"]
    assert mode_app["save_calls"] == []
    assert mode_app["emitted"] == []
    assert (
        config.input_folder,
        config.output_folder,
        config.renpy_source_translate,
        config.renpy_hook_translate,
    ) == before


def test_start_without_mode_keeps_legacy_flow(mode_app):
    """旧 body 不带 mode 时仍投递 TRANSLATION_START，且不改写翻译方式字段。"""
    client = mode_app["client"]
    config = mode_app["config"]
    before = (
        config.input_folder,
        config.output_folder,
        config.renpy_source_translate,
        config.renpy_hook_translate,
        config.target_language,
    )

    response = _start(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] is True
    assert body["reason"] == "STARTED"
    assert mode_app["save_calls"] == []
    assert (
        config.input_folder,
        config.output_folder,
        config.renpy_source_translate,
        config.renpy_hook_translate,
        config.target_language,
    ) == before
    assert len(mode_app["emitted"]) == 1
    event, payload = mode_app["emitted"][0]
    assert event == Base.Event.TRANSLATION_START
    assert payload["request_id"] == "mode-test"
    assert payload["status"] == "UNTRANSLATED"
    assert payload.get("preflight_confirmed") is True


def test_reinject_emits_cache_reinject_for_selected_tl(mode_app):
    client = mode_app["client"]
    tl = mode_app["tl"]
    (tl / "cache").mkdir()
    (tl / "cache" / "project.json").write_text("{}", encoding="utf-8")

    response = client.post(
        "/api/translation/reinject",
        json={
            "tl_parent": str(tl.parent),
            "tl_name": "chinese",
            "project_key": mode_app["paths"].project_key,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    assert len(mode_app["emitted"]) == 1
    event, payload = mode_app["emitted"][0]
    assert event == Base.Event.TRANSLATION_CACHE_REINJECT
    assert Path(payload["output_folder"]) == tl.resolve()


def test_reinject_rejects_without_cache_and_no_emit(mode_app):
    client = mode_app["client"]
    tl = mode_app["tl"]
    response = client.post(
        "/api/translation/reinject",
        json={"output_folder": str(tl)},
    )
    assert response.status_code == 404, response.text
    assert mode_app["emitted"] == []


def test_reinject_owner_mismatch_rejects_without_emit(mode_app):
    client = mode_app["client"]
    tl = mode_app["tl"]
    (tl / "cache").mkdir()
    (tl / "cache" / "project.json").write_text("{}", encoding="utf-8")

    response = client.post(
        "/api/translation/reinject",
        json={"output_folder": str(tl), "project_key": "other|chinese"},
    )
    assert response.status_code == 409, response.text
    assert mode_app["emitted"] == []


def test_mode_supplement_explicit_tl_parent(mode_app, tmp_path):
    """请求显式 tl_parent 保留自定义 TL，三 flags 互斥。"""
    client = mode_app["client"]
    config = mode_app["config"]
    project = tmp_path / "SuppCustom"
    game = project / "game"
    game.mkdir(parents=True)
    custom_parent = project / "ExternalTranslations"
    custom_tl = custom_parent / "chinese"
    custom_tl.mkdir(parents=True)
    (custom_tl / "script.rpy").write_text(
        'translate chinese strings:\n    old "a"\n    new "a"\n',
        encoding="utf-8",
    )

    response = _start(
        client,
        mode="supplement",
        game_path=str(project),
        tl_parent=str(custom_parent),
        tl_name="chinese",
    )
    assert response.status_code == 200, response.text
    assert Path(config.input_folder) == custom_tl.resolve()
    assert Path(config.output_folder) == custom_tl.resolve()
    assert config.renpy_source_translate is False
    assert config.renpy_hook_translate is True
    assert _project_changed_events(mode_app["emitted"])
    snapshot = _translation_start_payload(mode_app["emitted"])["config"]
    assert Path(snapshot.input_folder) == custom_tl.resolve()
    assert snapshot.renpy_hook_translate is True
    assert snapshot.renpy_source_translate is False


def test_mode_direct_flags_mutually_exclusive(mode_app):
    client = mode_app["client"]
    response = _start(
        client,
        mode="direct",
        renpy_backup_original=False,
        auto_write_back=True,
    )
    assert response.status_code == 200, response.text
    snapshot = _translation_start_payload(mode_app["emitted"])["config"]
    assert snapshot.renpy_source_translate is False
    assert snapshot.renpy_hook_translate is False


@pytest.mark.parametrize("mode", ["direct", "supplement"])
def test_manual_target_persists_global_and_emits_project_changed(mode_app, mode):
    """手动目标 B：保存成功先同步全局为 B 并发 PROJECT_CHANGED；旧 owner 再请求 409。"""
    from api.routes import project

    client = mode_app["client"]
    config = mode_app["config"]
    mode_app["app"].include_router(project.router)
    manual_b = mode_app["tmp_path"] / "ManualB"
    tl = manual_b / "game" / "tl" / "chinese"
    tl.mkdir(parents=True)
    (tl / "script.rpy").write_text(
        'translate chinese strings:\n    old "b"\n    new "b"\n',
        encoding="utf-8",
    )
    owner_a = RenpyProjectPaths.from_config(config).project_key

    response = _start(client, mode=mode, game_path=str(manual_b), project_key=owner_a)
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] is True
    owner_b = RenpyProjectPaths.from_config(config).project_key
    assert owner_b != owner_a
    assert Path(client.get("/api/project").json()["renpy_project_path"]) == manual_b
    changed = _project_changed_events(mode_app["emitted"])
    assert len(changed) == 1
    assert Path(changed[0]["project_root"]) == manual_b
    assert _translation_start_payload(mode_app["emitted"])
    # 事件顺序：绑定落盘广播先于 TRANSLATION_START
    event_names = [event for event, _ in mode_app["emitted"]]
    assert event_names.index(Base.Event.PROJECT_CHANGED) < event_names.index(Base.Event.TRANSLATION_START)

    again = _start(client, mode=mode, game_path=str(manual_b), project_key=owner_a)
    assert again.status_code == 409, again.text


def test_manual_target_save_failure_does_not_emit_project_changed(mode_app, monkeypatch):
    """保存异常不得广播 PROJECT_CHANGED，也不得投递 TRANSLATION_START。"""
    client = mode_app["client"]
    config = mode_app["config"]
    manual_b = mode_app["tmp_path"] / "ManualSaveFail"
    tl = manual_b / "game" / "tl" / "chinese"
    tl.mkdir(parents=True)
    (tl / "script.rpy").write_text(
        'translate chinese strings:\n    old "b"\n    new "b"\n',
        encoding="utf-8",
    )
    owner_a = RenpyProjectPaths.from_config(config).project_key
    before_root = config.renpy_project_path

    def boom(self, path=None, *, strict=False):
        raise OSError("disk full (test)")

    monkeypatch.setattr(Config, "save", boom)
    response = _start(client, mode="direct", game_path=str(manual_b), project_key=owner_a)
    assert response.status_code == 500, response.text
    assert mode_app["emitted"] == []
    assert config.renpy_project_path == before_root


def test_busy_reject_does_not_emit_project_changed(mode_app):
    """引擎忙拒绝时不落盘、不发 PROJECT_CHANGED。"""
    client = mode_app["client"]
    config = mode_app["config"]
    engine = mode_app["engine"]
    manual_b = mode_app["tmp_path"] / "ManualBusy"
    tl = manual_b / "game" / "tl" / "chinese"
    tl.mkdir(parents=True)
    (tl / "script.rpy").write_text(
        'translate chinese strings:\n    old "b"\n    new "b"\n',
        encoding="utf-8",
    )
    owner_a = RenpyProjectPaths.from_config(config).project_key
    before_root = config.renpy_project_path
    engine.set_status(Engine.Status.TRANSLATING)

    response = _start(client, mode="direct", game_path=str(manual_b), project_key=owner_a)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] is False
    assert body["reason"] in ("STOPPING", "ENGINE_BUSY")
    assert mode_app["save_calls"] == []
    assert mode_app["emitted"] == []
    assert config.renpy_project_path == before_root
    engine.set_status(Engine.Status.IDLE)
