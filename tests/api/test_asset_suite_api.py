"""资源套件 API：确认门闩、引擎互斥、取消与结果契约。"""
from __future__ import annotations

import json
import time
from pathlib import Path

import openpyxl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes.asset_suite import router
from api.routes.jobs import router as jobs_router
from module.Config import Config
from module.Engine.Engine import Engine


@pytest.fixture
def asset_app(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))
    from module.Project.ProjectStore import ProjectStore
    monkeypatch.setattr(ProjectStore, "persist", lambda *args, **kwargs: None)
    project = tmp_path / "game_project"
    game = project / "game"
    tl = game / "tl" / "chinese"
    tl.mkdir(parents=True)
    (game / "script.rpy").write_text(
        'define eileen = Character("Eileen")\nlabel start:\n    e "Hello"\n',
        encoding="utf-8",
    )
    (tl / "old.rpy").write_text(
        'translate chinese strings:\n\n    old "{b}Bold{/b}"\n    new "{b}粗体{/b}"\n',
        encoding="utf-8",
    )
    config = Config()
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(tl)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.include_router(router)
    app.include_router(jobs_router)
    with TestClient(app) as client:
        yield client, config, engine, project, game, tl
        app.state.jobs.shutdown()


def _finish(client, job_id, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "failed", "cancelled"} and not (job.get("result") or {}).get("worker_active"):
            return job
        time.sleep(0.02)
    pytest.fail(f"任务未结束：{job}")


def test_structure_requires_confirm_when_output_exists(asset_app):
    client, _, _, project, game, _ = asset_app
    out = project / "translate_output"
    out.mkdir()
    (out / "keep.txt").write_text("x", encoding="utf-8")
    response = client.post(
        "/api/asset-suite/structure",
        json={"path": str(project), "language": "chinese", "mode": "1", "confirm_overwrite": False},
    )
    assert response.status_code == 200
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"


def test_structure_and_status_and_engine_release(asset_app):
    client, _, engine, project, _, _ = asset_app
    response = client.post(
        "/api/asset-suite/structure",
        json={"path": str(project), "language": "chinese", "mode": "1", "gen_emoji": True, "confirm_overwrite": True},
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["names_count"] >= 1
    assert Path(job["result"]["output_dir"]).exists()
    assert engine.get_status() == Engine.Status.IDLE
    assert client.get("/api/asset-suite/status").json()["job"]["id"] == job["id"]


def test_emoji_requires_confirm(asset_app):
    client, _, _, project, _, tl = asset_app
    response = client.post(
        "/api/asset-suite/emoji",
        json={"path": str(project), "target_dir": str(tl), "mode": "prepare", "confirm": False},
    )
    assert response.status_code == 400


def test_corrections_apply_confirm_and_busy_engine(asset_app, tmp_path):
    client, _, engine, _, _, tl = asset_app
    checks = tmp_path / "checks"
    out = tmp_path / "out"
    checks.mkdir()
    out.mkdir()
    (checks / "result_check_demo.json").write_text(
        json.dumps({"script.rpy": {"Hello": "你好"}}),
        encoding="utf-8-sig",
    )
    export = client.post(
        "/api/asset-suite/corrections/export",
        json={"input_dir": str(checks), "output_dir": str(out), "confirm_overwrite": True},
    )
    job = _finish(client, export.json()["job"]["id"])
    assert job["status"] == "done"
    workbook = job["result"]["path"]
    book = openpyxl.load_workbook(workbook)
    book.active.cell(2, 5).value = "您好"
    book.save(workbook)

    denied = client.post(
        "/api/asset-suite/corrections/apply",
        json={"workbook": workbook, "translation_root": str(tl), "confirm": False},
    )
    assert denied.status_code == 400

    assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
    busy = client.post(
        "/api/asset-suite/corrections/apply",
        json={"workbook": workbook, "translation_root": str(tl), "confirm": True},
    )
    assert busy.status_code == 409
    engine.release_status(Engine.Status.TRANSLATING)


def test_names_extract_export_and_cancel(asset_app, monkeypatch):
    client, _, engine, project, game, _ = asset_app
    response = client.post("/api/asset-suite/names/extract", json={"input_dir": str(game)})
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["count"] >= 1
    entries = job["result"]["entries"]

    exported = client.post(
        "/api/asset-suite/names/export",
        json={"entries": entries, "format": "json"},
    )
    assert exported.status_code == 200
    payload = exported.json()
    assert payload["filename"].endswith(".json")
    assert json.loads(payload["content"])[0]["src"] == entries[0]["src"]

    release = {"go": False}

    def slow_extract(input_dir, *, cancel_check=None):
        while not release["go"]:
            if cancel_check and cancel_check():
                from module.Tool.AssetSuiteOps import AssetSuiteCancelled
                raise AssetSuiteCancelled()
            time.sleep(0.01)
        return {"success": True, "count": 0, "entries": [], "warnings": [], "empty": True, "message": "ok"}

    monkeypatch.setattr("api.routes.asset_suite.extract_character_names", slow_extract)
    job_id = client.post("/api/asset-suite/names/extract", json={"input_dir": str(game)}).json()["job"]["id"]
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
    assert engine.get_status() == Engine.Status.TESTING
    release["go"] = True
    cancelled = _finish(client, job_id)
    assert cancelled["status"] == "cancelled"
    assert engine.get_status() == Engine.Status.IDLE


def test_project_key_mismatch(asset_app):
    client, _, _, project, _, _ = asset_app
    response = client.post(
        "/api/asset-suite/structure",
        json={"path": str(project), "language": "chinese", "mode": "1", "confirm_overwrite": True, "project_key": "other"},
    )
    assert response.status_code == 409
