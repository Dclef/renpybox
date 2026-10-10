"""一键翻译 API：检测、准备确认、应用与互斥。"""
from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes.jobs import router as jobs_router
from api.routes.onekey import router
from module.Config import Config
from module.Engine.Engine import Engine


@pytest.fixture
def onekey_app(tmp_path, monkeypatch):
    project = tmp_path / "story"
    game = project / "game"
    tl = game / "tl" / "chinese"
    tl.mkdir(parents=True)
    (game / "script.rpy").write_text('label start:\n    "hello"\n', encoding="utf-8")
    (tl / "script.rpy").write_text('translate chinese start:\n    "hello"\n', encoding="utf-8")
    config = Config()
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(tl)
    config.input_folder = str(tl)
    config.output_folder = str(project / "RenpyBox_Translation" / "chinese")
    config.cache_use_sqlite = False
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.include_router(router)
    app.include_router(jobs_router)
    with TestClient(app) as client:
        yield client, config, engine, project, game
        app.state.jobs.shutdown()


def _finish(client, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "failed", "cancelled"} and not (job.get("result") or {}).get("worker_active"):
            return job
        time.sleep(0.01)
    pytest.fail(f"任务未结束：{job}")


def test_detect_ready_and_rejects_language_traversal(onekey_app, monkeypatch):
    client, _, _, project, _ = onekey_app
    monkeypatch.setattr(
        "api.routes.onekey.detect_game_status",
        lambda game_dir, language, cancel_check=None: ("ready", "可抽取"),
    )
    response = client.post("/api/onekey/detect", json={"game_dir": str(project), "language": "chinese"})
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    bad = client.post("/api/onekey/detect", json={"game_dir": str(project), "language": "../evil"})
    assert bad.status_code == 400


def test_prepare_requires_confirm_and_does_not_start_translation(onekey_app, monkeypatch):
    client, config, engine, project, game = onekey_app
    response = client.post(
        "/api/onekey/prepare",
        json={"game_dir": str(project), "language": "chinese", "incremental": False, "confirm_write": False},
    )
    assert response.status_code == 400

    monkeypatch.setattr(
        "api.routes.onekey.detect_game_status",
        lambda game_dir, language, cancel_check=None: ("ready", "可抽取"),
    )
    monkeypatch.setattr(
        "api.routes.onekey.prepare_extraction_paths",
        lambda config, game_dir, tl_name, *, incremental: {
            "paths": None,
            "incremental_dir": None,
            "output_dir": config.output_folder,
            "main_tl_dir": config.input_folder,
            "main_output_dir": config.output_folder,
            "preserved_cache": None,
        },
    )
    monkeypatch.setattr(
        "api.routes.onekey.extract_project_text",
        lambda *args, **kwargs: (
            True,
            "抽取完成",
            SimpleNamespace(success=True, cancelled=False, incremental_dir=None, tl_dir=config.input_folder),
        ),
    )
    monkeypatch.setattr(
        "api.routes.onekey.configure_main_translation_paths",
        lambda config, game_dir, tl_name, *, remember_run=True: (config.input_folder, config.output_folder),
    )
    saved = {"count": 0}
    monkeypatch.setattr(
        type(config),
        "save",
        lambda self, *args, **kwargs: saved.__setitem__("count", saved["count"] + 1),
    )

    response = client.post(
        "/api/onekey/prepare",
        json={"game_dir": str(project), "language": "chinese", "incremental": False, "confirm_write": True},
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["stage"] == "ready"
    assert engine.get_status() == Engine.Status.IDLE
    # 准备成功只配置路径，不假装翻译已成功。
    assert "translation" not in job["kind"]


def test_apply_requires_confirm_and_rejects_busy_engine(onekey_app):
    client, config, engine, project, _ = onekey_app
    Path(config.output_folder).mkdir(parents=True, exist_ok=True)
    response = client.post(
        "/api/onekey/apply",
        json={"game_dir": str(project), "language": "chinese", "confirm": False},
    )
    assert response.status_code == 400
    assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
    response = client.post(
        "/api/onekey/apply",
        json={"game_dir": str(project), "language": "chinese", "confirm": True},
    )
    assert response.status_code == 409
    engine.release_status(Engine.Status.TRANSLATING)


def test_apply_full_uses_transaction_helper(onekey_app, monkeypatch, tmp_path):
    client, config, engine, project, game = onekey_app
    output = Path(config.output_folder)
    output.mkdir(parents=True)
    (output / "script.rpy").write_text('translate chinese start:\n    "你好"\n', encoding="utf-8")

    called = {}

    def fake_apply(**kwargs):
        called.update(kwargs)
        return True, "已应用 1 个文件", {"count": 1}

    monkeypatch.setattr("api.routes.onekey.apply_full_translation", fake_apply)
    response = client.post(
        "/api/onekey/apply",
        json={
            "game_dir": str(project),
            "language": "chinese",
            "incremental": False,
            "confirm": True,
            "incremental_output": None,
            "incremental_target": None,
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert called["output_files"]
    assert engine.get_status() == Engine.Status.IDLE


def test_detect_empty_path(onekey_app):
    client, config, *_ = onekey_app
    config.renpy_project_path = ""
    config.renpy_game_folder = ""
    response = client.post("/api/onekey/detect", json={"game_dir": "", "language": "chinese"})
    assert response.status_code == 400


@pytest.mark.parametrize("incremental", [False, True])
def test_real_prepare_and_apply_without_game_executable(onekey_app, incremental):
    """临时项目走真实检测、补充抽取与事务应用，不启动游戏或模型。"""
    client, config, engine, project, game = onekey_app
    (game / "script.rpy").write_text('label start:\n    show text "Standalone display text"\n    "hello"\n', encoding="utf-8")
    config.save(strict=True)
    source_before = (game / "script.rpy").read_bytes()
    response = client.post("/api/onekey/prepare", json={
        "game_dir": str(project), "language": "chinese", "confirm_write": True, "incremental": incremental,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"], timeout=15)
    assert job["status"] == "done", job
    assert job["result"]["stage"] == "ready"
    assert Path(config.input_folder).is_dir()
    assert not (game / "game").exists()
    extracted = list(Path(config.input_folder).rglob("*.rpy"))
    assert any("Standalone display text" in path.read_text(encoding="utf-8") for path in extracted)
    output = Path(config.output_folder)
    output.mkdir(parents=True, exist_ok=True)
    translated = 'translate chinese strings:\n    old "hello"\n    new "你好"\n'
    (output / "verified.rpy").write_text(translated, encoding="utf-8")
    response = client.post("/api/onekey/apply", json={
        "game_dir": str(project), "language": "chinese", "confirm": True, "incremental": incremental,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"], timeout=15)
    assert job["status"] == "done", job
    applied = (game / "tl" / "chinese" / "verified.rpy").read_text(encoding="utf-8")
    assert [line for line in applied.splitlines() if line.strip()] == translated.splitlines()
    assert (game / "script.rpy").read_bytes() == source_before
    assert engine.get_status() == Engine.Status.IDLE
