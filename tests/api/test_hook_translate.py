"""/api/hook-translate：runtime_extract 失败不得 TRANSLATION_START；取消与锁释放。"""
from __future__ import annotations

import copy
import dataclasses
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes import hook_translate
from base.Base import Base
from base.BaseLanguage import BaseLanguage
from base.EventManager import EventManager
from module.Config import Config
from module.Engine.Engine import Engine
from module.Extract.RenpyExtractor import RenpyExtractor


@pytest.fixture
def hook_app(tmp_path, monkeypatch):
    project = tmp_path / "HookDemo"
    game = project / "game"
    tl = game / "tl" / "chinese"
    tl.mkdir(parents=True)
    (tl / "script.rpy").write_text("# base\n", encoding="utf-8")
    exe = project / "game.exe"
    exe.write_bytes(b"MZ")

    config = Config()
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(tl)
    config.input_folder = str(tl)
    config.output_folder = str(tl)
    config.source_language = BaseLanguage.Enum.EN
    config.target_language = BaseLanguage.Enum.ZH
    config.renpy_source_translate = False
    config.renpy_hook_translate = False

    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))

    save_calls: list = []

    def save(self, path=None, *, strict=False):
        save_calls.append(copy.deepcopy(self))
        return self

    def load(self, path=None):
        for field in dataclasses.fields(config):
            setattr(self, field.name, copy.deepcopy(getattr(config, field.name)))
        return self

    monkeypatch.setattr(Config, "save", save)
    monkeypatch.setattr(Config, "load", load)

    emitted: list[tuple] = []

    def emit(self, event, data=None):
        emitted.append((event, data))
        if event == Base.Event.TRANSLATION_START:
            payload = data if isinstance(data, dict) else {}
            EventManager.get().process_event(
                Base.Event.TRANSLATION_START_RESULT,
                {
                    "accepted": True,
                    "request_id": str(payload.get("request_id") or ""),
                    "run_id": 42,
                },
            )

    monkeypatch.setattr(EventManager, "emit", emit)

    # 跳过资产预检（默认视为无需提示）
    class FakePreflight:
        should_prompt_for_missing_assets = False

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

    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager(publish=None)

    @app.on_event("shutdown")
    def _shutdown():
        app.state.jobs.shutdown()

    app.include_router(hook_translate.router)
    with TestClient(app) as client:
        yield {
            "client": client,
            "config": config,
            "engine": engine,
            "project": project,
            "exe": exe,
            "tl": tl,
            "save_calls": save_calls,
            "emitted": emitted,
            "app": app,
        }


def _wait_job_terminal(client, timeout=5.0, *, project_key: str = "", request_id: str = ""):
    """按 owner/request 查询，与页面一致；勿裸查 status（owner≠target 持久化后会丢 job）。"""
    deadline = time.time() + timeout
    params = {}
    if project_key:
        params["project_key"] = project_key
    if request_id:
        params["request_id"] = request_id
    while time.time() < deadline:
        status = client.get("/api/hook-translate/status", params=params or None).json()
        job = status.get("job")
        if job and job.get("status") in ("done", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError("job 未在超时内结束")


def test_extract_failure_does_not_emit_translation_start(hook_app, monkeypatch):
    client = hook_app["client"]
    engine = hook_app["engine"]

    def boom(*_a, **_k):
        raise RuntimeError("抽取失败（测试）")

    monkeypatch.setattr(RenpyExtractor, "runtime_extract", boom)

    response = client.post(
        "/api/hook-translate/start",
        json={
            "game_path": str(hook_app["exe"]),
            "tl_name": "chinese",
            "preflight_confirmed": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] is True
    job = _wait_job_terminal(client)
    assert job["status"] == "failed"
    assert job["result"]["translation_started"] is False
    assert job["result"]["worker_active"] is False
    assert all(event != Base.Event.TRANSLATION_START for event, _ in hook_app["emitted"])
    assert engine.get_status() == Engine.Status.IDLE


def test_extract_success_emits_translation_start(hook_app, monkeypatch):
    client = hook_app["client"]
    tl = hook_app["tl"]
    engine = hook_app["engine"]

    def ok(_self, _path, _tl_name, **_kwargs):
        return tl

    monkeypatch.setattr(RenpyExtractor, "runtime_extract", ok)

    response = client.post(
        "/api/hook-translate/start",
        json={
            "game_path": str(hook_app["exe"]),
            "tl_name": "chinese",
            "source_language": "EN",
            "target_language": "ZH",
            "renpy_backup_original": False,
            "renpy_hook_incremental": True,
            "generate_empty": False,
            "preflight_confirmed": True,
        },
    )
    assert response.status_code == 200, response.text
    job = _wait_job_terminal(client)
    assert job["status"] == "done"
    assert job["result"]["translation_started"] is True
    assert job["result"]["translation_run_id"] == 42
    assert job["result"]["worker_active"] is False
    assert Path(job["result"]["tl_dir"]) == tl.resolve()
    starts = [p for e, p in hook_app["emitted"] if e == Base.Event.TRANSLATION_START]
    assert len(starts) == 1
    snapshot = starts[0]["config"]
    assert Path(snapshot.input_folder) == tl.resolve()
    assert Path(snapshot.output_folder) == tl.resolve()
    assert snapshot.renpy_source_translate is False
    assert snapshot.renpy_hook_translate is False
    assert engine.get_status() == Engine.Status.IDLE


def test_manual_target_different_from_owner_still_ok(hook_app, monkeypatch, tmp_path):
    """合法手动目标可与绑定 owner 不同；body.project_key 校验 owner 而非 target。"""
    client = hook_app["client"]
    other = tmp_path / "OtherGame"
    game = other / "game"
    tl = game / "tl" / "chinese"
    tl.mkdir(parents=True)
    (tl / "script.rpy").write_text("# other\n", encoding="utf-8")
    exe = other / "game.exe"
    exe.write_bytes(b"MZ")

    def ok(_self, _path, _tl_name, **_kwargs):
        return tl

    monkeypatch.setattr(RenpyExtractor, "runtime_extract", ok)
    from module.Renpy.ProjectPaths import RenpyProjectPaths
    owner = RenpyProjectPaths.from_config(hook_app["config"])

    owner_key = owner.project_key if owner else ""
    response = client.post(
        "/api/hook-translate/start",
        json={
            "game_path": str(exe),
            "tl_name": "chinese",
            "preflight_confirmed": True,
            "project_key": owner_key,
        },
    )
    assert response.status_code == 200, response.text
    job = _wait_job_terminal(client, project_key=owner_key)
    assert job["status"] == "done"
    assert job["result"]["translation_started"] is True
    assert Path(job["result"]["tl_dir"]) == tl.resolve()
    assert job["result"]["owner_key"] == owner_key
    assert job["result"]["target_key"] != job["result"]["owner_key"]


def test_manual_target_emits_project_changed_and_keeps_old_owner_job(hook_app, monkeypatch, tmp_path):
    """抽取成功保存 B 发 PROJECT_CHANGED；job 仍挂原 owner，status(owner=B) 为 null；owner guard 不削弱。"""
    from api.routes import project
    from module.Renpy.ProjectPaths import RenpyProjectPaths

    client = hook_app["client"]
    config = hook_app["config"]
    hook_app["app"].include_router(project.router)
    manual_b = tmp_path / "HookManualB"
    tl = manual_b / "game" / "tl" / "chinese"
    tl.mkdir(parents=True)
    (tl / "script.rpy").write_text("# generated\n", encoding="utf-8")

    def ok(_self, _path, _tl_name, **_kwargs):
        return tl

    monkeypatch.setattr(RenpyExtractor, "runtime_extract", ok)
    owner_a = RenpyProjectPaths.from_config(config).project_key

    response = client.post(
        "/api/hook-translate/start",
        json={
            "game_path": str(manual_b),
            "tl_name": "chinese",
            "project_key": owner_a,
            "preflight_confirmed": True,
            "request_id": "owner-hook-bind",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] is True
    # 受理响应已冻结 owner/target，供前端 status/stop 使用。
    start_job = response.json()["job"]
    assert start_job["result"]["owner_key"] == owner_a
    assert start_job["result"]["target_key"] != owner_a

    job = _wait_job_terminal(client, project_key=owner_a, request_id="owner-hook-bind")
    assert job["status"] == "done"
    assert job["result"]["translation_started"] is True
    owner_b = RenpyProjectPaths.from_config(config).project_key
    assert owner_b != owner_a
    assert Path(client.get("/api/project").json()["renpy_project_path"]) == manual_b

    changed = [data for event, data in hook_app["emitted"] if event == Base.Event.PROJECT_CHANGED]
    assert len(changed) == 1
    assert Path(changed[0]["project_root"]) == manual_b
    starts = [p for e, p in hook_app["emitted"] if e == Base.Event.TRANSLATION_START]
    assert len(starts) == 1
    event_names = [event for event, _ in hook_app["emitted"]]
    assert event_names.index(Base.Event.PROJECT_CHANGED) < event_names.index(Base.Event.TRANSLATION_START)

    old_status = client.get(
        "/api/hook-translate/status",
        params={"project_key": owner_a, "request_id": "owner-hook-bind"},
    ).json()
    new_status = client.get(
        "/api/hook-translate/status",
        params={"project_key": owner_b, "request_id": "owner-hook-bind"},
    ).json()
    assert old_status["job"]["id"] == job["id"]
    assert new_status["job"] is None

    # 原 owner + request 仍可 stop（翻译已启动时走 run 归属校验）。
    hook_app["engine"].set_status(Engine.Status.TRANSLATING)
    hook_app["engine"].translator = SimpleNamespace(
        _active_request_id="owner-hook-bind",
        _translation_run_id=int(job["result"]["translation_run_id"] or 0),
    )
    stop = client.post(
        "/api/hook-translate/stop",
        params={
            "project_key": owner_a,
            "request_id": "owner-hook-bind",
            "run_id": int(job["result"]["translation_run_id"] or 0),
        },
    )
    assert stop.status_code == 200, stop.text
    hook_app["engine"].set_status(Engine.Status.IDLE)

    again = client.post(
        "/api/hook-translate/start",
        json={
            "game_path": str(manual_b),
            "tl_name": "chinese",
            "project_key": owner_a,
            "preflight_confirmed": True,
        },
    )
    assert again.status_code == 409, again.text


def test_start_result_false_not_marked_started(hook_app, monkeypatch):
    client = hook_app["client"]
    tl = hook_app["tl"]

    def ok(_self, _path, _tl_name, **_kwargs):
        return tl

    monkeypatch.setattr(RenpyExtractor, "runtime_extract", ok)

    def emit_fail(self, event, data=None):
        hook_app["emitted"].append((event, data))
        if event == Base.Event.TRANSLATION_START:
            payload = data if isinstance(data, dict) else {}
            EventManager.get().process_event(
                Base.Event.TRANSLATION_START_RESULT,
                {
                    "accepted": False,
                    "request_id": str(payload.get("request_id") or ""),
                    "reason": "ENGINE_BUSY",
                },
            )

    monkeypatch.setattr(EventManager, "emit", emit_fail)

    response = client.post(
        "/api/hook-translate/start",
        json={
            "game_path": str(hook_app["exe"]),
            "tl_name": "chinese",
            "preflight_confirmed": True,
        },
    )
    assert response.status_code == 200, response.text
    job = _wait_job_terminal(client)
    assert job["status"] == "failed"
    assert job["result"]["translation_started"] is False


def test_cancel_during_extract_releases_lock(hook_app, monkeypatch):
    client = hook_app["client"]
    engine = hook_app["engine"]
    started = threading.Event()
    release = threading.Event()

    def slow(_self, _path, _tl_name, **kwargs):
        started.set()
        should_stop = kwargs.get("should_stop")
        while not release.is_set():
            if callable(should_stop) and should_stop():
                raise RuntimeError("已取消")
            time.sleep(0.02)
        return hook_app["tl"]

    monkeypatch.setattr(RenpyExtractor, "runtime_extract", slow)

    response = client.post(
        "/api/hook-translate/start",
        json={
            "game_path": str(hook_app["exe"]),
            "tl_name": "chinese",
            "preflight_confirmed": True,
        },
    )
    assert response.status_code == 200, response.text
    assert started.wait(timeout=2.0)
    assert engine.get_status() == Engine.Status.TESTING

    stop = client.post("/api/hook-translate/stop")
    assert stop.status_code == 200, stop.text
    release.set()
    job = _wait_job_terminal(client)
    assert job["status"] == "cancelled"
    assert job["result"]["worker_active"] is False
    assert job["result"]["translation_started"] is False
    assert all(event != Base.Event.TRANSLATION_START for event, _ in hook_app["emitted"])
    assert engine.get_status() == Engine.Status.IDLE


def test_stop_does_not_stop_foreign_translation(hook_app, monkeypatch):
    client = hook_app["client"]
    engine = hook_app["engine"]
    tl = hook_app["tl"]

    def ok(_self, _path, _tl_name, **_kwargs):
        return tl

    monkeypatch.setattr(RenpyExtractor, "runtime_extract", ok)

    response = client.post(
        "/api/hook-translate/start",
        json={
            "game_path": str(hook_app["exe"]),
            "tl_name": "chinese",
            "preflight_confirmed": True,
            "request_id": "hook-own-req",
        },
    )
    assert response.status_code == 200, response.text
    job = _wait_job_terminal(client)
    assert job["status"] == "done"
    assert job["result"]["translation_started"] is True

    engine.set_status(Engine.Status.TRANSLATING)
    engine.translator = SimpleNamespace(
        _active_request_id="someone-else",
        _translation_run_id=999,
    )

    stop = client.post(
        "/api/hook-translate/stop",
        params={"request_id": "hook-own-req", "project_key": job["result"]["owner_key"]},
    )
    assert stop.status_code == 409, stop.text
    assert engine.get_status() == Engine.Status.TRANSLATING
    engine.set_status(Engine.Status.IDLE)


def test_invalid_tl_name_rejected(hook_app):
    client = hook_app["client"]
    response = client.post(
        "/api/hook-translate/start",
        json={
            "game_path": str(hook_app["exe"]),
            "tl_name": "../evil",
            "preflight_confirmed": True,
        },
    )
    assert response.status_code == 400, response.text


def test_assets_missing_rejects_without_job(hook_app, monkeypatch):
    client = hook_app["client"]

    class FakePreflight:
        should_prompt_for_missing_assets = True

    monkeypatch.setattr(
        "module.Engine.Translator.TranslationPreflightService.TranslationPreflightService.check",
        staticmethod(lambda _assets: FakePreflight()),
    )

    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("不应抽取")

    monkeypatch.setattr(RenpyExtractor, "runtime_extract", boom)

    response = client.post(
        "/api/hook-translate/start",
        json={
            "game_path": str(hook_app["exe"]),
            "tl_name": "chinese",
            "preflight_confirmed": False,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] is False
    assert body["reason"] == "ASSETS_MISSING"
    assert body.get("job") is None
    assert called["n"] == 0
    assert hook_app["emitted"] == []
    assert hook_app["engine"].get_status() == Engine.Status.IDLE


def test_extract_fail_with_existing_tl_not_reported_as_partial(hook_app, monkeypatch):
    """旧 TL 已有文件但本次未写入：失败不得把旧树当 written/partial。"""
    client = hook_app["client"]
    tl = hook_app["tl"]
    assert (tl / "script.rpy").is_file()

    def boom(_self, _path, _tl_name, **kwargs):
        # 模拟异常前未回调任何本次写入
        assert kwargs.get("written_files") == [] or kwargs.get("written_files") is not None
        raise RuntimeError("抽取失败（无本次写入）")

    monkeypatch.setattr(RenpyExtractor, "runtime_extract", boom)

    response = client.post(
        "/api/hook-translate/start",
        json={
            "game_path": str(hook_app["exe"]),
            "tl_name": "chinese",
            "preflight_confirmed": True,
        },
    )
    assert response.status_code == 200, response.text
    job = _wait_job_terminal(client)
    assert job["status"] == "failed"
    result = job["result"] or {}
    assert result.get("written_files") == []
    assert result.get("partial") is not True
    assert result.get("translation_started") is False


def test_extract_mid_failure_keeps_session_written_files(hook_app, monkeypatch):
    """某文件写入成功后下一阶段失败：保留本次 written_files 并标 partial。"""
    client = hook_app["client"]
    tl = hook_app["tl"]
    new_file = tl / "session_new.rpy"

    def partial_then_fail(_self, _path, _tl_name, **kwargs):
        written = kwargs.get("written_files")
        new_file.write_text("# session write\n", encoding="utf-8")
        if isinstance(written, list):
            written.append(str(new_file))
        raise RuntimeError("后续失败")

    monkeypatch.setattr(RenpyExtractor, "runtime_extract", partial_then_fail)

    response = client.post(
        "/api/hook-translate/start",
        json={
            "game_path": str(hook_app["exe"]),
            "tl_name": "chinese",
            "preflight_confirmed": True,
        },
    )
    assert response.status_code == 200, response.text
    job = _wait_job_terminal(client)
    assert job["status"] == "failed"
    result = job["result"] or {}
    written = result.get("written_files") or []
    assert any(Path(p).name == "session_new.rpy" for p in written)
    assert result.get("partial") is True
    assert new_file.is_file()
    # 不得把预先存在的 script.rpy 误报为本次产物
    assert not any(Path(p).name == "script.rpy" for p in written)
