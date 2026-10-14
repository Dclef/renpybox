"""抽取到 TL API：选项传递、增量保护、合并/恢复、取消与项目切换（mock UnifiedExtractor）。"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes.extract_to_tl import (
    has_existing_translations,
    is_effective_tl_rpy,
    router,
)
from api.routes.jobs import router as jobs_router
from module.Config import Config
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import RenpyProjectPaths


@pytest.fixture
def extract_app(tmp_path, monkeypatch):
    project, game = _make_project(tmp_path)
    config = Config()
    paths = _bind(config, project)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    # 避免真实写盘：Config.save 落到临时配置
    monkeypatch.setattr(Config, "save", lambda self, *args, **kwargs: self)
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.include_router(router)
    app.include_router(jobs_router)
    with TestClient(app) as client:
        yield client, config, engine, project, game, paths, app.state.jobs
        app.state.jobs.shutdown()


def _make_project(root: Path) -> tuple[Path, Path]:
    project = root / "Demo"
    game = project / "game"
    (game / "tl" / "chinese").mkdir(parents=True)
    (game / "script.rpy").write_text('label start:\n    "Hello"\n', encoding="utf-8")
    return project, game


def _bind(config: Config, project: Path) -> RenpyProjectPaths:
    game = project / "game"
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(game / "tl" / "chinese")
    config.input_folder = str(game / "tl" / "chinese")
    config.output_folder = ""
    config.extract_use_official = True
    config.extract_use_custom = True
    config.extract_supplement_mode = "precise"
    config.extract_skip_hook_files = True
    config.renpy_filter_suspicious_bool_expr = True
    config.renpy_incremental_auto_merge_cleanup = True
    paths = RenpyProjectPaths.from_config(config)
    assert paths is not None
    return paths


def _finish(client, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        result = job.get("result") or {}
        if job["status"] in {"done", "failed", "cancelled"} and not result.get("worker_active"):
            return job
        time.sleep(0.01)
    pytest.fail(f"任务未结束：{job}")


def _extract_body(key, **extra):
    return {
        "project_key": key,
        "language": "chinese",
        "use_official": True,
        "use_custom": True,
        "supplement_mode": "aggressive",
        "skip_hook_files": False,
        "filter_suspicious_bool_expr": False,
        "auto_merge_cleanup": True,
        **extra,
    }


def _ok_result(**extra):
    base = dict(
        success=True,
        message="ok",
        tl_dir=Path("tl"),
        incremental_dir=None,
        preserved_count=0,
        new_strings=1,
        total_files=1,
        official_status="not_run",
        cancelled=False,
    )
    base.update(extra)
    return SimpleNamespace(**base)


def test_is_effective_tl_rpy_filters_hooks_and_auto():
    assert is_effective_tl_rpy(Path("strings.rpy")) is True
    assert is_effective_tl_rpy(Path("hook_add.rpy")) is False
    assert is_effective_tl_rpy(Path("miss_ready_replace_x.rpy")) is False
    assert is_effective_tl_rpy(Path("replace_text_auto.rpy")) is False
    assert is_effective_tl_rpy(Path("set_default_language_at_startup.rpy")) is False


def test_status_reports_options_and_incremental_flags(extract_app):
    client, config, _, project, game, paths, _ = extract_app
    tl = game / "tl" / "chinese"
    (tl / "hook_ignore.rpy").write_text("# hook\n", encoding="utf-8")
    (game / "tl" / "chinese_new").mkdir()
    backup = tl / "_filtered_suspicious" / "t1"
    backup.mkdir(parents=True)
    (backup / "restore_manifest.csv").write_text("file,old,new,restore\n", encoding="utf-8")

    response = client.get("/api/extract-to-tl")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project_key"] == paths.project_key
    assert Path(body["project_root"]) == project.resolve()
    assert body["has_existing_tl"] is False  # 仅 hook 不算有效译文
    assert body["incremental_dir_exists"] is True
    assert body["suspicious_backup_available"] is True
    assert body["options"]["supplement_mode"] == "precise"
    assert body["options"]["use_official"] is True
    assert config.extract_use_official is True


def test_protects_existing_translations_via_incremental(extract_app, monkeypatch):
    client, config, engine, project, game, paths, _ = extract_app
    tl = game / "tl" / "chinese"
    (tl / "common.rpy").write_text(
        'translate chinese strings:\n    old "Hi"\n    new "你好"\n',
        encoding="utf-8",
    )
    assert has_existing_translations(tl) is True

    calls = {"regular": 0, "incremental": 0, "merge": 0}

    class FakeExtractor:
        def set_progress_callback(self, cb):
            self._progress = cb

        def set_cancel_callback(self, cb):
            self._cancel = cb

        def extract_regular(self, *args, **kwargs):
            calls["regular"] += 1
            return _ok_result()

        def extract_incremental(self, game_dir, tl_name, exe_path=None, use_official=True, output_to_separate_folder=True, config_snapshot=None):
            calls["incremental"] += 1
            assert use_official is False  # 无 exe 时官方回退
            snap = config_snapshot
            assert snap is not None
            assert str(snap.extract_supplement_mode) == "aggressive"
            assert snap.extract_skip_hook_files is False
            assert snap.renpy_filter_suspicious_bool_expr is False
            inc = Path(game_dir) / "game" / "tl" / f"{tl_name}_new"
            inc.mkdir(parents=True, exist_ok=True)
            return _ok_result(incremental_dir=inc, preserved_count=1)

        def merge_incremental_folder(self, *args, **kwargs):
            calls["merge"] += 1
            return _ok_result(message="merged")

    monkeypatch.setattr("api.routes.extract_to_tl.UnifiedExtractor", FakeExtractor)
    monkeypatch.setattr("api.routes.extract_to_tl._rule_mode", lambda _root: "builtin")
    monkeypatch.setattr("api.routes.extract_to_tl.auto_find_exe", lambda _root: None)

    response = client.post("/api/extract-to-tl/extract", json=_extract_body(paths.project_key))
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done", job
    assert job["result"]["incremental"] is True
    assert calls["incremental"] == 1
    assert calls["regular"] == 0
    assert calls["merge"] == 1
    assert config.extract_supplement_mode == "aggressive"
    assert config.extract_use_custom is True
    assert engine.get_status() == Engine.Status.IDLE


def test_regular_extract_when_tl_empty(extract_app, monkeypatch):
    client, _, engine, _, _, paths, _ = extract_app
    calls = {"regular": 0, "incremental": 0}

    class FakeExtractor:
        def set_progress_callback(self, cb):
            pass

        def set_cancel_callback(self, cb):
            pass

        def extract_regular(self, *args, **kwargs):
            calls["regular"] += 1
            return _ok_result()

        def extract_incremental(self, *args, **kwargs):
            calls["incremental"] += 1
            return _ok_result()

    monkeypatch.setattr("api.routes.extract_to_tl.UnifiedExtractor", FakeExtractor)
    monkeypatch.setattr("api.routes.extract_to_tl._rule_mode", lambda _root: "builtin")

    response = client.post(
        "/api/extract-to-tl/extract",
        json=_extract_body(paths.project_key, use_official=False, auto_merge_cleanup=False),
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["incremental"] is False
    assert calls["regular"] == 1
    assert calls["incremental"] == 0
    assert engine.get_status() == Engine.Status.IDLE


def test_custom_rule_mode_forces_off_official_and_supplement(extract_app, monkeypatch):
    client, config, _, _, _, paths, _ = extract_app
    seen = {}

    class FakeExtractor:
        def set_progress_callback(self, cb):
            pass

        def set_cancel_callback(self, cb):
            pass

        def extract_regular(self, *args, **kwargs):
            seen["use_official"] = kwargs.get("use_official")
            return _ok_result()

    monkeypatch.setattr("api.routes.extract_to_tl.UnifiedExtractor", FakeExtractor)
    monkeypatch.setattr("api.routes.extract_to_tl._rule_mode", lambda _root: "custom")

    # custom 模式不应改写用户的 official/custom 开关
    before_official = config.extract_use_official
    before_custom = config.extract_use_custom
    response = client.post("/api/extract-to-tl/extract", json=_extract_body(paths.project_key))
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert seen["use_official"] is False
    assert config.extract_use_official is before_official
    assert config.extract_use_custom is before_custom


def test_merge_and_restore_with_tmp(extract_app, monkeypatch):
    client, _, engine, project, game, paths, _ = extract_app
    lang = "chinese"
    incremental = game / "tl" / f"{lang}_new"
    incremental.mkdir(parents=True)
    (incremental / "a.rpy").write_text("# new\n", encoding="utf-8")
    backup = game / "tl" / lang / "_filtered_suspicious" / "run1"
    backup.mkdir(parents=True)
    manifest = backup / "restore_manifest.csv"
    manifest.write_text(
        "file,old,new,restore\ncommon.rpy,Hello,你好,1\n",
        encoding="utf-8",
    )

    class FakeExtractor:
        def set_progress_callback(self, cb):
            pass

        def set_cancel_callback(self, cb):
            pass

        def merge_incremental_folder(self, game_dir, tl_name, incremental_dir=None, *, clean_duplicates=True, config_snapshot=None):
            assert Path(game_dir).resolve() == project.resolve()
            assert tl_name == lang
            assert Path(incremental_dir).resolve() == incremental.resolve()
            return _ok_result(message="merged", incremental_dir=incremental)

        def restore_flagged_suspicious_entries(self, game_dir, tl_name, manifest_path=None):
            assert Path(game_dir).resolve() == project.resolve()
            assert Path(manifest_path).resolve() == manifest.resolve()
            return _ok_result(message="restored 1")

    monkeypatch.setattr("api.routes.extract_to_tl.UnifiedExtractor", FakeExtractor)

    merge = client.post(
        "/api/extract-to-tl/merge-incremental",
        json={"project_key": paths.project_key, "language": lang},
    )
    assert merge.status_code == 200, merge.text
    merge_job = _finish(client, merge.json()["job"]["id"])
    assert merge_job["status"] == "done"
    assert merge_job["result"]["written"] is True

    listed = client.get("/api/extract-to-tl/suspicious-backups", params={"language": lang})
    assert listed.status_code == 200
    assert listed.json()["available"] is True
    assert listed.json()["manifests"][0]["path"] == str(manifest)

    opened = client.post(
        "/api/extract-to-tl/open-path",
        json={"project_key": paths.project_key, "path": str(manifest)},
    )
    assert opened.status_code == 200
    assert opened.json()["ok"] is True

    restore = client.post(
        "/api/extract-to-tl/restore-suspicious",
        json={
            "project_key": paths.project_key,
            "language": lang,
            "manifest_path": str(manifest),
        },
    )
    assert restore.status_code == 200, restore.text
    restore_job = _finish(client, restore.json()["job"]["id"])
    assert restore_job["status"] == "done"
    assert engine.get_status() == Engine.Status.IDLE


def test_cancel_and_project_switch(extract_app, monkeypatch, tmp_path):
    client, config, engine, _, _, paths, _ = extract_app
    entered, release = threading.Event(), threading.Event()

    class SlowExtractor:
        def set_progress_callback(self, cb):
            pass

        def set_cancel_callback(self, cb):
            self._cancel = cb

        def extract_regular(self, *args, **kwargs):
            entered.set()
            assert release.wait(5)
            if self._cancel and self._cancel():
                return _ok_result(success=False, cancelled=True, message="cancelled")
            return _ok_result()

    monkeypatch.setattr("api.routes.extract_to_tl.UnifiedExtractor", SlowExtractor)
    monkeypatch.setattr("api.routes.extract_to_tl._rule_mode", lambda _root: "builtin")

    try:
        response = client.post(
            "/api/extract-to-tl/extract",
            json=_extract_body(paths.project_key, use_official=False, auto_merge_cleanup=False),
        )
        assert response.status_code == 200, response.text
        job_id = response.json()["job"]["id"]
        assert entered.wait(2)
        assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
        assert engine.get_status() == Engine.Status.TESTING
    finally:
        release.set()
    job = _finish(client, job_id)
    assert job["status"] == "cancelled"
    assert job["result"]["worker_active"] is False
    assert engine.get_status() == Engine.Status.IDLE

    # 绑定配置被改绑：启动后改路径，任务应失败
    entered2, release2 = threading.Event(), threading.Event()
    real_identity = __import__("api.routes.extract_to_tl", fromlist=["_project_identity"])._project_identity
    calls = {"n": 0}

    def wrapped_identity(config_obj):
        calls["n"] += 1
        if calls["n"] > 1:
            entered2.set()
            assert release2.wait(5)
        return real_identity(config_obj)

    monkeypatch.setattr("api.routes.extract_to_tl._project_identity", wrapped_identity)
    other, _ = _make_project(tmp_path / "other")
    try:
        response = client.post(
            "/api/extract-to-tl/extract",
            json=_extract_body(paths.project_key, use_official=False, auto_merge_cleanup=False),
        )
        assert response.status_code == 200, response.text
        job_id = response.json()["job"]["id"]
        assert entered2.wait(2)
        _bind(config, other)
        release2.set()
        switched = _finish(client, job_id)
        assert switched["status"] == "failed"
        assert "切换" in (switched["result"].get("message") or switched.get("error") or "")
    finally:
        release2.set()
    assert engine.get_status() == Engine.Status.IDLE


def test_reject_stale_project_and_busy(extract_app, monkeypatch):
    client, config, engine, project, game, paths, manager = extract_app

    class QuickExtractor:
        def set_progress_callback(self, cb):
            pass

        def set_cancel_callback(self, cb):
            pass

        def extract_regular(self, *args, **kwargs):
            return _ok_result()

        def extract_incremental(self, *args, **kwargs):
            return _ok_result()

    monkeypatch.setattr("api.routes.extract_to_tl.UnifiedExtractor", QuickExtractor)
    monkeypatch.setattr("api.routes.extract_to_tl._rule_mode", lambda _root: "builtin")

    assert client.post(
        "/api/extract-to-tl/extract",
        json=_extract_body(paths.project_key + "-stale"),
    ).status_code == 409
    # 已绑定项目时 project_key 可省略
    omit_key = client.post(
        "/api/extract-to-tl/extract",
        json=_extract_body("", use_official=False, auto_merge_cleanup=False),
    )
    assert omit_key.status_code == 200, omit_key.text
    _finish(client, omit_key.json()["job"]["id"])

    persist_calls = {"n": 0}
    real_persist = __import__("api.routes.extract_to_tl", fromlist=["_persist_extract_fields"])._persist_extract_fields

    def track_persist(live, values):
        persist_calls["n"] += 1
        return real_persist(live, values)

    monkeypatch.setattr("api.routes.extract_to_tl._persist_extract_fields", track_persist)
    mkdir_calls = {"n": 0}
    real_mkdir = Path.mkdir

    def track_mkdir(self, *args, **kwargs):
        mkdir_calls["n"] += 1
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", track_mkdir)
    before_mode = config.extract_supplement_mode
    jobs_before_busy = len(manager.list())
    assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
    assert client.post(
        "/api/extract-to-tl/extract",
        json=_extract_body(paths.project_key, use_official=False, auto_merge_cleanup=False),
    ).status_code == 409
    assert persist_calls["n"] == 0
    assert mkdir_calls["n"] == 0
    assert config.extract_supplement_mode == before_mode
    assert len(manager.list()) == jobs_before_busy
    engine.set_status(Engine.Status.IDLE)


def test_unbound_extract_with_game_dir(tmp_path, monkeypatch):
    other, game = _make_project(tmp_path / "remote")
    config = Config()
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    monkeypatch.setattr(Config, "save", lambda self, *args, **kwargs: self)
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.include_router(router)
    app.include_router(jobs_router)

    class FakeExtractor:
        def set_progress_callback(self, cb):
            pass

        def set_cancel_callback(self, cb):
            pass

        def extract_regular(self, *args, **kwargs):
            return _ok_result()

        def extract_incremental(self, *args, **kwargs):
            return _ok_result()

    monkeypatch.setattr("api.routes.extract_to_tl.UnifiedExtractor", FakeExtractor)
    monkeypatch.setattr("api.routes.extract_to_tl._rule_mode", lambda _root: "builtin")

    with TestClient(app) as client:
        status = client.get("/api/extract-to-tl")
        assert status.status_code == 200
        assert status.json()["project_key"] == ""

        body = _extract_body("", game_dir=str(other), use_official=False, auto_merge_cleanup=False)
        response = client.post("/api/extract-to-tl/extract", json=body)
        assert response.status_code == 200, response.text
        job = _finish(client, response.json()["job"]["id"])
        assert job["status"] == "done"
        target_key = RenpyProjectPaths.from_path(other, "chinese").project_key
        assert job["result"]["project_key"] == target_key
        app.state.jobs.shutdown()


def test_extract_other_target_with_owner_key(extract_app, monkeypatch, tmp_path):
    """已绑定项目时，可用 owner project_key 抽取另一个合法目录（不对 target key）。"""
    client, config, engine, project, _, paths, _ = extract_app
    other, _ = _make_project(tmp_path / "OtherGame")

    class FakeExtractor:
        def set_progress_callback(self, cb):
            pass

        def set_cancel_callback(self, cb):
            pass

        def extract_regular(self, game_dir, *args, **kwargs):
            assert Path(game_dir).resolve() == other.resolve()
            return _ok_result()

        def extract_incremental(self, *args, **kwargs):
            return _ok_result()

    monkeypatch.setattr("api.routes.extract_to_tl.UnifiedExtractor", FakeExtractor)
    monkeypatch.setattr("api.routes.extract_to_tl._rule_mode", lambda _root: "builtin")

    response = client.post(
        "/api/extract-to-tl/extract",
        json=_extract_body(
            paths.project_key,
            game_dir=str(other),
            use_official=False,
            auto_merge_cleanup=False,
        ),
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    other_key = RenpyProjectPaths.from_path(other, "chinese").project_key
    assert job["result"]["project_key"] == other_key
    assert other_key != paths.project_key
    assert engine.get_status() == Engine.Status.IDLE


def test_unbound_merge_and_restore_chain(tmp_path, monkeypatch):
    """无绑定项目时，手选目标仍可合并/恢复整链。"""
    other, game = _make_project(tmp_path / "solo")
    lang = "chinese"
    incremental = game / "tl" / f"{lang}_new"
    incremental.mkdir(parents=True)
    (incremental / "a.rpy").write_text("# new\n", encoding="utf-8")
    backup = game / "tl" / lang / "_filtered_suspicious" / "run1"
    backup.mkdir(parents=True)
    manifest = backup / "restore_manifest.csv"
    manifest.write_text("file,old,new,restore\ncommon.rpy,Hello,你好,1\n", encoding="utf-8")

    config = Config()
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    monkeypatch.setattr(Config, "save", lambda self, *args, **kwargs: self)
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.include_router(router)
    app.include_router(jobs_router)

    seen = {"merge": 0, "restore": 0, "snap": None}

    class FakeExtractor:
        def set_progress_callback(self, cb):
            pass

        def set_cancel_callback(self, cb):
            pass

        def merge_incremental_folder(self, game_dir, tl_name, incremental_dir=None, *, clean_duplicates=True, config_snapshot=None):
            seen["merge"] += 1
            seen["snap"] = config_snapshot
            assert Path(game_dir).resolve() == other.resolve()
            assert Path(incremental_dir).resolve() == incremental.resolve()
            return _ok_result(message="merged", incremental_dir=incremental)

        def restore_flagged_suspicious_entries(self, game_dir, tl_name, manifest_path=None):
            seen["restore"] += 1
            assert Path(game_dir).resolve() == other.resolve()
            assert Path(manifest_path).resolve() == manifest.resolve()
            return _ok_result(message="restored 1")

    monkeypatch.setattr("api.routes.extract_to_tl.UnifiedExtractor", FakeExtractor)

    with TestClient(app) as client:
        merge = client.post(
            "/api/extract-to-tl/merge-incremental",
            json={"game_dir": str(other), "language": lang},
        )
        assert merge.status_code == 200, merge.text
        merge_job = _finish(client, merge.json()["job"]["id"])
        assert merge_job["status"] == "done"
        assert seen["merge"] == 1
        assert seen["snap"] is not None

        listed = client.get(
            "/api/extract-to-tl/suspicious-backups",
            params={"language": lang, "game_dir": str(other)},
        )
        assert listed.status_code == 200
        assert listed.json()["available"] is True

        restore = client.post(
            "/api/extract-to-tl/restore-suspicious",
            json={
                "game_dir": str(other),
                "language": lang,
                "manifest_path": str(manifest),
            },
        )
        assert restore.status_code == 200, restore.text
        restore_job = _finish(client, restore.json()["job"]["id"])
        assert restore_job["status"] == "done"
        assert seen["restore"] == 1
        assert engine.get_status() == Engine.Status.IDLE
        app.state.jobs.shutdown()


def test_extract_keeps_success_when_merge_fails(extract_app, monkeypatch):
    client, _, engine, project, game, paths, _ = extract_app
    tl = game / "tl" / "chinese"
    (tl / "common.rpy").write_text(
        'translate chinese strings:\n    old "Hi"\n    new "你好"\n',
        encoding="utf-8",
    )

    class FakeExtractor:
        def set_progress_callback(self, cb):
            pass

        def set_cancel_callback(self, cb):
            pass

        def extract_incremental(self, game_dir, tl_name, exe_path=None, use_official=True, output_to_separate_folder=True, config_snapshot=None):
            inc = Path(game_dir) / "game" / "tl" / f"{tl_name}_new"
            inc.mkdir(parents=True, exist_ok=True)
            return _ok_result(incremental_dir=inc, preserved_count=1, message="extract ok")

        def merge_incremental_folder(self, *args, **kwargs):
            return _ok_result(success=False, message="merge boom")

    monkeypatch.setattr("api.routes.extract_to_tl.UnifiedExtractor", FakeExtractor)
    monkeypatch.setattr("api.routes.extract_to_tl._rule_mode", lambda _root: "builtin")
    monkeypatch.setattr("api.routes.extract_to_tl.auto_find_exe", lambda _root: None)

    response = client.post(
        "/api/extract-to-tl/extract",
        json=_extract_body(paths.project_key, use_official=False, auto_merge_cleanup=True),
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["written"] is True
    assert job["result"]["success"] is True
    assert "extract ok" in (job["result"].get("message") or "")
    assert "merge boom" in (job["result"].get("message") or "")
    assert job["result"].get("merge", {}).get("success") is False
    assert engine.get_status() == Engine.Status.IDLE


def test_options_snapshot_beats_config_load(extract_app, monkeypatch):
    client, config, engine, project, _, paths, _ = extract_app
    load_calls = {"n": 0}
    real_load = Config.load

    def counting_load(self):
        load_calls["n"] += 1
        return real_load(self)

    monkeypatch.setattr(Config, "load", counting_load)
    # 磁盘配置仍为 precise；请求 aggressive 应通过 snapshot 生效
    config.extract_supplement_mode = "precise"

    class FakeExtractor:
        def set_progress_callback(self, cb):
            pass

        def set_cancel_callback(self, cb):
            pass

        def extract_regular(self, *args, **kwargs):
            snap = kwargs.get("config_snapshot")
            assert snap is not None
            assert snap.extract_supplement_mode == "aggressive"
            assert snap.extract_skip_hook_files is False
            return _ok_result()

    monkeypatch.setattr("api.routes.extract_to_tl.UnifiedExtractor", FakeExtractor)
    monkeypatch.setattr("api.routes.extract_to_tl._rule_mode", lambda _root: "builtin")

    response = client.post(
        "/api/extract-to-tl/extract",
        json=_extract_body(
            paths.project_key,
            use_official=False,
            auto_merge_cleanup=False,
            supplement_mode="aggressive",
            skip_hook_files=False,
        ),
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert load_calls["n"] == 0
    assert engine.get_status() == Engine.Status.IDLE


def test_restore_second_atomic_failure_keeps_partial_meta(extract_app, monkeypatch):
    """真实 restore：第2次 atomic OSError → failed + written/partial/written_files 仅首文件。"""
    from module.Extract import UnifiedExtractor as ue_mod

    client, _, engine, project, game, paths, _ = extract_app
    tl = game / "tl" / "chinese"
    backup = tl / "_filtered_suspicious" / "t1"
    backup.mkdir(parents=True)
    manifest = backup / "restore_manifest.csv"
    manifest.write_text(
        "file,old,new,restore\n"
        "a.rpy,A,甲,1\n"
        "b.rpy,B,乙,1\n",
        encoding="utf-8",
    )
    real_atomic = ue_mod.atomic_write_text
    calls = {"n": 0}

    def gated_atomic(path, text, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError("stub atomic failure")
        return real_atomic(path, text, **kwargs)

    monkeypatch.setattr(ue_mod, "atomic_write_text", gated_atomic)

    response = client.post(
        "/api/extract-to-tl/restore-suspicious",
        json={
            "project_key": paths.project_key,
            "language": "chinese",
            "manifest_path": str(manifest),
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"], timeout=8.0)
    assert job["status"] == "failed"
    result = job["result"] or {}
    assert result.get("written") is True
    assert result.get("partial") is True
    assert result.get("success") is False
    written = result.get("written_files") or []
    assert len(written) == 1
    assert Path(written[0]).name == "a.rpy"
    assert (tl / "a.rpy").is_file()
    assert "甲" in (tl / "a.rpy").read_text(encoding="utf-8")
    assert not (tl / "b.rpy").exists()
    assert engine.get_status() == Engine.Status.IDLE
