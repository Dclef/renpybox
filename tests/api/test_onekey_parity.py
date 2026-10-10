"""一键翻译旧 Qt 功能对齐：抽取模式、补充抽取/UI 包选项、合并清理与判定不译清单。"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes import onekey
from api.routes.jobs import router as jobs_router
from module.Config import Config
from module.Engine.Engine import Engine
from module.Extract.ReplaceGenerator import (
    declined_candidates_path,
    load_declined_candidates,
    record_declined_candidates,
)
from module.OneKey import flow
from module.Renpy.ProjectPaths import RenpyProjectPaths


@pytest.fixture
def parity_app(tmp_path, monkeypatch):
    project = tmp_path / "story"
    (project / "game" / "tl" / "chinese").mkdir(parents=True)
    (project / "game" / "script.rpy").write_text('label start:\n    "hello"\n', encoding="utf-8")
    paths = RenpyProjectPaths.from_path(project, "chinese")
    paths.translation_output_dir.mkdir(parents=True)
    config = Config()
    flow.configure_main_translation_paths(config, project, "chinese", remember_run=False)
    config.save(strict=True)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    monkeypatch.setattr(flow, "_replace_fallback", lambda *args: {})
    monkeypatch.setattr(onekey, "detect_game_status", lambda *args, **kwargs: ("ready", "就绪"))
    # 默认不让测试机上的真实 EXE 探测参与；需要时由用例覆盖。
    monkeypatch.setattr(onekey.RenpyDecompiler, "_find_game_exe", lambda self, root: None)
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


def _body(paths, **values):
    return {"game_dir": str(paths.project_root), "language": "chinese", "confirm_write": True, **values}


def _capture_extract(monkeypatch, observed: list):
    def extract(*args, **kwargs):
        # 抽取器从磁盘读配置，记录此刻落盘值才能证明选项先于抽取生效。
        disk = Config().load()
        observed.append({
            "incremental": kwargs["incremental"],
            "exe_path": kwargs["exe_path"],
            "supplement": disk.extract_supplement_mode,
            "use_custom": disk.extract_use_custom,
            "use_official": disk.extract_use_official,
            "inject": disk.onekey_inject_base_box,
        })
        return True, "抽取完成", SimpleNamespace(success=True, cancelled=False)
    monkeypatch.setattr(onekey, "extract_project_text", extract)


def test_existing_translation_summary_and_mode_resolution(tmp_path):
    project = tmp_path / "story"
    tl = project / "game" / "tl" / "chinese"
    (tl / "sub").mkdir(parents=True)
    paths = RenpyProjectPaths.from_path(project, "chinese")
    assert flow.existing_translation_summary(paths)["exists"] is True
    (tl / "sub").rmdir()
    assert flow.existing_translation_summary(paths) == {"exists": False, "rpy_count": 0, "tl_dir": str(tl)}
    (tl / "a.rpy").write_text("", encoding="utf-8")
    (tl / "b.txt").write_text("", encoding="utf-8")
    assert flow.existing_translation_summary(paths)["rpy_count"] == 1
    with pytest.raises(ValueError):
        flow.resolve_extraction_incremental("merge", True)


def test_detect_reports_existing_translation_layout_and_safe_auto_exe(parity_app, monkeypatch, tmp_path):
    client, _, paths, _ = parity_app
    (paths.tl_language_dir / "script.rpy").write_text("translate chinese strings:\n", encoding="utf-8")
    record_declined_candidates(paths.project_root, "chinese", {"HP", "MP"})
    exe = paths.project_root / "Story.exe"
    exe.write_bytes(b"exe")
    monkeypatch.setattr(onekey.RenpyDecompiler, "_find_game_exe", lambda self, root: exe)
    data = client.post("/api/onekey/detect", json={"game_dir": str(paths.project_root), "language": "chinese"}).json()
    assert data["existing_translation"]["exists"] is True
    assert data["existing_translation"]["rpy_count"] == 1
    assert data["layout"]["incremental_dir"] == str(paths.tl_root / "chinese_new")
    assert data["layout"]["ui_pack_dir"] == str(paths.tl_language_dir / "base_box")
    assert data["auto_exe"] == str(exe.resolve())
    assert data["declined_count"] == 2
    # 项目外 EXE 不能出现在确认范围里。
    outside = tmp_path / "outside.exe"
    outside.write_bytes(b"exe")
    monkeypatch.setattr(onekey.RenpyDecompiler, "_find_game_exe", lambda self, root: outside)
    data = client.post("/api/onekey/detect", json={"game_dir": str(paths.project_root), "language": "chinese"}).json()
    assert data["auto_exe"] is None


@pytest.mark.parametrize("mode,has_existing,legacy_incremental,expected", [
    ("auto", True, False, True),
    ("auto", False, True, False),
    ("full", True, True, False),
    ("incremental", True, False, True),
    ("incremental", False, False, False),
    (None, False, True, True),
])
def test_prepare_mode_is_resolved_and_passed_to_extraction(parity_app, monkeypatch, mode, has_existing, legacy_incremental, expected):
    client, _, paths, _ = parity_app
    if has_existing:
        (paths.tl_language_dir / "script.rpy").write_text("translate chinese strings:\n", encoding="utf-8")
    observed: list = []
    _capture_extract(monkeypatch, observed)
    body = _body(paths, incremental=legacy_incremental)
    if mode is not None:
        body["mode"] = mode
    response = client.post("/api/onekey/prepare", json=body)
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done", job
    assert [item["incremental"] for item in observed] == [expected]
    assert job["result"]["incremental"] is expected
    assert job["result"]["existing_translation"]["exists"] is has_existing


def test_prepare_rejects_unknown_mode(parity_app):
    client, _, paths, engine = parity_app
    response = client.post("/api/onekey/prepare", json=_body(paths, mode="merge"))
    assert response.status_code == 422
    assert engine.get_status() == Engine.Status.IDLE


def test_official_disabled_never_runs_executable_even_with_path(parity_app, monkeypatch):
    client, _, paths, _ = parity_app
    exe = paths.project_root / "Story.exe"
    exe.write_bytes(b"exe")
    lookups = []
    monkeypatch.setattr(onekey.RenpyDecompiler, "_find_game_exe", lambda self, root: lookups.append(root) or exe)
    observed: list = []
    _capture_extract(monkeypatch, observed)
    response = client.post("/api/onekey/prepare", json=_body(
        paths, official_extract=False, exe_path=str(exe), supplement_mode="precise",
    ))
    assert response.status_code == 200, response.text
    assert _finish(client, response.json()["job"]["id"])["status"] == "done"
    assert observed[0]["exe_path"] is None
    assert lookups == []


def test_off_supplement_without_official_is_rejected_without_side_effects(parity_app):
    client, config, paths, engine = parity_app
    before = (config.extract_supplement_mode, config.extract_use_custom)
    response = client.post("/api/onekey/prepare", json=_body(paths, official_extract=False, supplement_mode="off"))
    assert response.status_code == 400
    assert (config.extract_supplement_mode, config.extract_use_custom) == before
    assert Config().load().extract_use_custom is before[1]
    assert engine.get_status() == Engine.Status.IDLE


def test_supplement_and_ui_pack_options_are_persisted_before_extraction(parity_app, monkeypatch):
    client, config, paths, _ = parity_app
    exe = paths.project_root / "Story.exe"
    exe.write_bytes(b"exe")
    config.extract_use_official = False
    config.save(strict=True)
    observed: list = []
    _capture_extract(monkeypatch, observed)
    response = client.post("/api/onekey/prepare", json=_body(
        paths, official_extract=True, exe_path=str(exe), supplement_mode="off", inject_ui_pack=True,
    ))
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done", job
    assert observed == [{
        "incremental": False, "exe_path": str(exe.resolve()), "supplement": "off",
        "use_custom": False, "use_official": True, "inject": True,
    }]
    assert job["result"]["supplement_mode"] == "off" and job["result"]["inject_ui_pack"] is True
    assert config.onekey_inject_base_box is True

    observed.clear()
    response = client.post("/api/onekey/prepare", json=_body(paths, official_extract=False, supplement_mode="aggressive", inject_ui_pack=False))
    assert _finish(client, response.json()["job"]["id"])["status"] == "done"
    assert observed[0]["supplement"] == "aggressive" and observed[0]["use_custom"] is True
    assert observed[0]["inject"] is False


def test_option_save_failure_releases_engine_and_keeps_live_config(parity_app, monkeypatch):
    client, config, paths, engine = parity_app
    monkeypatch.setattr(Config, "save", lambda self, **kwargs: (_ for _ in ()).throw(OSError("只读")))
    monkeypatch.setattr(onekey, "extract_project_text", lambda *a, **k: pytest.fail("保存失败不应抽取"))
    response = client.post("/api/onekey/prepare", json=_body(paths, official_extract=False, supplement_mode="aggressive", inject_ui_pack=True))
    assert response.status_code == 500
    assert config.onekey_inject_base_box is False
    assert config.extract_supplement_mode == "precise"
    assert engine.get_status() == Engine.Status.IDLE


@pytest.mark.parametrize("configured,requested,expected", [
    (True, None, True),
    (False, None, False),
    (True, False, False),
    (False, True, True),
])
def test_incremental_apply_passes_auto_merge_cleanup(parity_app, monkeypatch, configured, requested, expected):
    client, config, paths, _ = parity_app
    config.renpy_incremental_auto_merge_cleanup = configured
    (paths.translation_output_dir.parent / "chinese_new").mkdir()
    (paths.tl_root / "chinese_new").mkdir()
    seen = []

    class Extractor:
        def set_progress_callback(self, callback):
            pass

        def merge_incremental_folder(self, *args, **kwargs):
            seen.append(kwargs["clean_duplicates"])
            return SimpleNamespace(success=True)

    monkeypatch.setattr(onekey, "UnifiedExtractor", Extractor)
    body = {"game_dir": str(paths.project_root), "language": "chinese", "confirm": True, "incremental": True}
    if requested is not None:
        body["auto_merge_cleanup"] = requested
    response = client.post("/api/onekey/apply", json=body)
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done", job
    assert seen == [expected]
    assert job["result"]["auto_merge_cleanup"] is expected


def test_declined_clear_requires_confirm_and_stays_in_project(parity_app, tmp_path):
    client, _, paths, engine = parity_app
    record_declined_candidates(paths.project_root, "chinese", {"HP", "MP"})
    record_declined_candidates(paths.project_root, "japanese", {"SP"})
    base = {"game_dir": str(paths.project_root), "language": "chinese"}
    assert client.post("/api/onekey/declined/clear", json=base).status_code == 400
    assert client.post("/api/onekey/declined/clear", json={**base, "confirm": True, "project_key": "other"}).status_code == 409
    other = tmp_path / "other"
    (other / "game").mkdir(parents=True)
    record_declined_candidates(other, "chinese", {"XP"})
    assert load_declined_candidates(paths.project_root, "chinese") == {"HP", "MP"}

    assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
    assert client.post("/api/onekey/declined/clear", json={**base, "confirm": True}).status_code == 409
    engine.release_status(Engine.Status.TRANSLATING)
    assert declined_candidates_path(paths.project_root, "chinese").exists()

    response = client.post("/api/onekey/declined/clear", json={**base, "confirm": True})
    assert response.status_code == 200, response.text
    assert response.json()["cleared"] == 2
    assert not declined_candidates_path(paths.project_root, "chinese").exists()
    assert load_declined_candidates(paths.project_root, "japanese") == {"SP"}
    assert load_declined_candidates(other, "chinese") == {"XP"}
    assert engine.get_status() == Engine.Status.IDLE
