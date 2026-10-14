"""一键任务安全回归：派生路径、项目快照与配置落盘。"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes import onekey
from api.routes.jobs import router as jobs_router
from module.Config import Config
from module.Engine.Engine import Engine
from module.OneKey import flow
from module.Renpy.ProjectPaths import RenpyProjectPaths


@pytest.fixture
def safe_app(tmp_path, monkeypatch):
    project = tmp_path / "story"
    (project / "game" / "tl" / "chinese").mkdir(parents=True)
    paths = RenpyProjectPaths.from_path(project, "chinese")
    paths.translation_output_dir.mkdir(parents=True)
    config = Config()
    flow.configure_main_translation_paths(config, project, "chinese", remember_run=False)
    config.save(strict=True)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    monkeypatch.setattr(flow, "_replace_fallback", lambda *args: {})
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.include_router(onekey.router)
    app.include_router(jobs_router)
    with TestClient(app) as client:
        yield client, config, paths, engine
        app.state.jobs.shutdown()


def _finish(client, job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "failed", "cancelled"} and not job["result"]["worker_active"]:
            return job
        time.sleep(0.01)
    pytest.fail(f"任务未退出：{job}")


def _apply_body(paths, **values):
    return {"game_dir": str(paths.project_root), "language": "chinese", "confirm": True, **values}


@pytest.mark.parametrize("language", ["C:", "C:evil", "a:b", "../evil", "a\\b", "CON", "LPT1", "name.", "x\x00y", "chinese_new"])
def test_rejects_windows_unsafe_language(safe_app, language):
    client, _, paths, _ = safe_app
    response = client.post("/api/onekey/detect", json={"game_dir": str(paths.project_root), "language": language})
    assert response.status_code == 400


@pytest.mark.parametrize("field,target", [
    ("incremental_target", "main_tl"),
    ("incremental_target", "project"),
    ("incremental_output", "main_output"),
    ("main_output", "outside"),
])
def test_incremental_rejects_non_derived_paths_before_deleting(safe_app, tmp_path, field, target):
    client, _, paths, engine = safe_app
    choices = {"main_tl": paths.application_target_dir, "project": paths.project_root,
               "main_output": paths.translation_output_dir, "outside": tmp_path / "outside"}
    target_dir = choices[target]
    target_dir.mkdir(parents=True, exist_ok=True)
    sentinel = target_dir / "keep.txt"
    sentinel.write_text("必须保留", encoding="utf-8")
    response = client.post("/api/onekey/apply", json=_apply_body(paths, incremental=True, **{field: str(target_dir)}))
    assert response.status_code == 400
    assert sentinel.read_text(encoding="utf-8") == "必须保留"
    assert engine.get_status() == Engine.Status.IDLE


def test_shared_incremental_helper_rejects_main_tl_cleanup(safe_app):
    _, config, paths, _ = safe_app
    sentinel = paths.application_target_dir / "keep.rpy"
    sentinel.write_text("原译文", encoding="utf-8")
    with pytest.raises(ValueError, match="派生目录"):
        flow.apply_incremental_translation(
            extractor=object(), config=config, game_dir=str(paths.project_root), tl_name="chinese",
            output_dir=paths.translation_output_dir.parent / "chinese_new",
            main_output=paths.translation_output_dir, incremental_dir=paths.application_target_dir,
        )
    assert sentinel.read_text(encoding="utf-8") == "原译文"


def test_incremental_success_cleans_only_delta_directories(safe_app, monkeypatch):
    client, config, paths, _ = safe_app
    delta_output = paths.translation_output_dir.parent / "chinese_new"
    delta_input = paths.tl_root / "chinese_new"
    delta_output.mkdir()
    delta_input.mkdir()
    sentinel = paths.application_target_dir / "keep.rpy"
    sentinel.write_text("原译文", encoding="utf-8")
    class Extractor:
        def set_progress_callback(self, callback):
            pass
        def merge_incremental_folder(self, *args, **kwargs):
            return SimpleNamespace(success=True)
    monkeypatch.setattr(onekey, "UnifiedExtractor", Extractor)
    response = client.post("/api/onekey/apply", json=_apply_body(paths, incremental=True))
    assert response.status_code == 200, response.text
    assert _finish(client, response.json()["job"]["id"])["status"] == "done"
    assert sentinel.read_text(encoding="utf-8") == "原译文"
    assert not delta_output.exists() and not delta_input.exists()
    assert config.input_folder == str(paths.application_target_dir)


def test_apply_rejects_other_project_and_language(safe_app, tmp_path):
    client, _, paths, _ = safe_app
    other = tmp_path / "other"
    (other / "game").mkdir(parents=True)
    for values in ({"game_dir": str(other)}, {"language": "japanese"}):
        response = client.post("/api/onekey/apply", json=_apply_body(paths, **values))
        assert response.status_code == 409


def test_full_apply_uses_main_target_with_prepared_output(safe_app):
    client, config, paths, _ = safe_app
    (paths.translation_output_dir / "script.rpy").write_text("译文", encoding="utf-8")
    config.output_folder = str(paths.project_root / "wrong-output")
    response = client.post("/api/onekey/apply", json=_apply_body(
        paths, incremental_output=str(paths.translation_output_dir), incremental_target=None,
    ))
    assert response.status_code == 200, response.text
    assert _finish(client, response.json()["job"]["id"])["status"] == "done"
    assert (paths.application_target_dir / "script.rpy").read_text(encoding="utf-8") == "译文"


def test_apply_after_project_switch_never_saves_snapshot_config(safe_app, monkeypatch, tmp_path):
    client, config, paths, _ = safe_app
    (paths.translation_output_dir / "script.rpy").write_text("译文", encoding="utf-8")
    started, release = threading.Event(), threading.Event()
    real_apply = flow.apply_translation_files_transactionally
    def blocked_apply(*args):
        started.set()
        assert release.wait(5)
        return real_apply(*args)
    monkeypatch.setattr(flow, "apply_translation_files_transactionally", blocked_apply)
    try:
        response = client.post("/api/onekey/apply", json=_apply_body(paths))
        assert response.status_code == 200, response.text
        assert started.wait(2)
        other = tmp_path / "other"
        (other / "game").mkdir(parents=True)
        flow.configure_main_translation_paths(config, other, "japanese", remember_run=False)
        config.save(strict=True)
        expected_disk = Path(Config.CONFIG_PATH).read_bytes()
        release.set()
        assert _finish(client, response.json()["job"]["id"])["status"] == "done"
        assert Path(Config.CONFIG_PATH).read_bytes() == expected_disk
        assert config.renpy_project_path == str(other)
    finally:
        release.set()


@pytest.mark.parametrize("switch_project", [False, True])
def test_prepare_unbound_project_recovers_job_and_saves_only_if_owner_unchanged(safe_app, monkeypatch, tmp_path, switch_project):
    client, config, paths, _ = safe_app
    config.renpy_project_path = config.renpy_game_folder = config.renpy_tl_folder = ""
    config.input_folder = str(tmp_path / "input")
    config.output_folder = str(tmp_path / "output")
    config.save(strict=True)
    started, release = threading.Event(), threading.Event()
    monkeypatch.setattr(onekey, "detect_game_status", lambda *args, **kwargs: ("ready", "就绪"))
    def extract(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return True, "抽取完成", SimpleNamespace(success=True, cancelled=False)
    monkeypatch.setattr(onekey, "extract_project_text", extract)
    try:
        response = client.post("/api/onekey/prepare", json={
            "game_dir": str(paths.project_root), "language": "chinese", "confirm_write": True,
        })
        assert response.status_code == 200, response.text
        job_id = response.json()["job"]["id"]
        assert started.wait(2)
        assert client.get("/api/onekey").json()["job"]["id"] == job_id
        if switch_project:
            config.input_folder = str(tmp_path / "changed-input")
            config.save(strict=True)
            expected_disk = Path(Config.CONFIG_PATH).read_bytes()
        release.set()
        job = _finish(client, job_id)
        assert job["status"] == ("failed" if switch_project else "done")
        if switch_project:
            assert Path(Config.CONFIG_PATH).read_bytes() == expected_disk
            assert config.renpy_project_path == ""
        else:
            assert config.renpy_project_path == str(paths.project_root)
            assert json.loads(Path(Config.CONFIG_PATH).read_text(encoding="utf-8"))["renpy_project_path"] == str(paths.project_root)
    finally:
        release.set()


def test_failed_config_save_does_not_change_live_paths(safe_app, monkeypatch):
    _, config, paths, _ = safe_app
    import copy
    configured = copy.deepcopy(config)
    configured.input_folder = "changed"
    def fail_save(self, **kwargs):
        assert kwargs.get("strict") is True
        raise OSError("磁盘不可写")
    monkeypatch.setattr(Config, "save", fail_save)
    with pytest.raises(OSError, match="磁盘不可写"):
        onekey._persist_project_paths(config, configured)
    assert config.input_folder == str(paths.application_target_dir)


def test_prepare_discovers_game_executable_and_rejects_other_project(safe_app, monkeypatch, tmp_path):
    client, _, paths, _ = safe_app
    executable = paths.project_root / "Story.exe"
    executable.write_bytes(b"test")
    (paths.project_root / "Story.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(onekey, "detect_game_status", lambda *args, **kwargs: ("ready", "就绪"))
    observed = []
    def extract(*args, **kwargs):
        observed.append(kwargs["exe_path"])
        return True, "抽取完成", SimpleNamespace(success=True, cancelled=False)
    monkeypatch.setattr(onekey, "extract_project_text", extract)
    body = {"game_dir": str(paths.project_root), "language": "chinese", "confirm_write": True}
    other_exe = tmp_path / "other.exe"
    other_exe.write_bytes(b"test")
    assert client.post("/api/onekey/prepare", json={**body, "exe_path": str(other_exe)}).status_code == 400
    response = client.post("/api/onekey/prepare", json=body)
    assert response.status_code == 200, response.text
    assert _finish(client, response.json()["job"]["id"])["status"] == "done"
    assert observed == [str(executable)]


@pytest.mark.parametrize("official_extract,use_exe_path,expected", [
    (False, False, None),
    (None, False, "auto"),
    (True, True, "chosen"),
])
def test_prepare_official_extract_switch(safe_app, monkeypatch, official_extract, use_exe_path, expected):
    client, _, paths, _ = safe_app
    executables = {"auto": paths.project_root / "Auto.exe", "chosen": paths.project_root / "Chosen.exe"}
    for executable in executables.values():
        executable.write_bytes(b"test")
    lookups = []
    def find_game_exe(self, root):
        lookups.append(root)
        return str(executables["auto"])
    monkeypatch.setattr(onekey.RenpyDecompiler, "_find_game_exe", find_game_exe)
    monkeypatch.setattr(onekey, "detect_game_status", lambda *args, **kwargs: ("ready", "就绪"))
    observed = []
    def extract(*args, **kwargs):
        observed.append(kwargs["exe_path"])
        return True, "抽取完成", SimpleNamespace(success=True, cancelled=False)
    monkeypatch.setattr(onekey, "extract_project_text", extract)
    body = {"game_dir": str(paths.project_root), "language": "chinese", "confirm_write": True,
            "official_extract": official_extract}
    if use_exe_path:
        body["exe_path"] = str(executables["chosen"])
    response = client.post("/api/onekey/prepare", json=body)
    assert response.status_code == 200, response.text
    assert _finish(client, response.json()["job"]["id"])["status"] == "done"
    assert observed == [str(executables[expected]) if expected else None]
    assert lookups == ([paths.project_root] if expected == "auto" else [])


@pytest.mark.parametrize("remaining_status", ["empty", "error", "need_unpack"])
def test_unpack_must_leave_extractable_scripts(safe_app, monkeypatch, remaining_status):
    client, _, paths, _ = safe_app
    states = iter([("need_unpack", "需解包"), (remaining_status, "仍不可抽取")])
    monkeypatch.setattr(onekey, "detect_game_status", lambda *args, **kwargs: next(states))
    monkeypatch.setattr(onekey, "unpack_game", lambda *args, **kwargs: {"success": True})
    monkeypatch.setattr(onekey, "extract_project_text", lambda *args, **kwargs: pytest.fail("无脚本不应进入抽取"))
    response = client.post("/api/onekey/prepare", json={
        "game_dir": str(paths.project_root), "language": "chinese", "confirm_write": True,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed" and "仍不可抽取" in job["error"]


def test_cancel_does_not_raise_in_subprocess_progress_reader(safe_app, monkeypatch):
    client, _, paths, engine = safe_app
    started, release = threading.Event(), threading.Event()
    errors = []
    monkeypatch.setattr(onekey, "detect_game_status", lambda *args, **kwargs: ("need_decompile", "需反编译"))
    def decompile(*args, **kwargs):
        started.set()
        assert release.wait(5)
        def reader():
            try:
                kwargs["progress_callback"]("迟到的子进程日志")
            except BaseException as exc:
                errors.append(exc)
        thread = threading.Thread(target=reader)
        thread.start()
        thread.join(2)
        return {"success": True}
    monkeypatch.setattr(onekey, "decompile_target", decompile)
    monkeypatch.setattr(onekey, "extract_project_text", lambda *args, **kwargs: pytest.fail("取消后不应抽取"))
    try:
        response = client.post("/api/onekey/prepare", json={
            "game_dir": str(paths.project_root), "language": "chinese", "confirm_write": True,
        })
        assert response.status_code == 200, response.text
        job_id = response.json()["job"]["id"]
        assert started.wait(2)
        client.post(f"/api/jobs/{job_id}/cancel")
        assert engine.get_status() == Engine.Status.TESTING
        release.set()
        assert _finish(client, job_id)["status"] == "cancelled"
        assert errors == []
        assert engine.get_status() == Engine.Status.IDLE
    finally:
        release.set()
