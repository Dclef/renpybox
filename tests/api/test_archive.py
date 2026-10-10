"""解包 / 反编译 / 打包 API：协作取消、互斥与源档保留。"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes.archive import router
from api.routes.jobs import router as jobs_router
from module.Config import Config
from module.Engine.Engine import Engine


@pytest.fixture
def archive_app(tmp_path, monkeypatch):
    project = tmp_path / "game_project"
    game = project / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text('label start:\n    "hi"\n', encoding="utf-8")
    (game / "assets.rpa").write_bytes(b"RPA-TEST")
    config = Config()
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(game / "tl" / "chinese")
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


def test_unpack_rejects_missing_path(archive_app):
    client, *_ = archive_app
    response = client.post("/api/archive/unpack", json={"path": "E:/missing/game", "direct": True, "script_only": False})
    assert response.status_code == 400


def test_unpack_keeps_archives_and_releases_engine(archive_app, monkeypatch):
    client, _, engine, project, game = archive_app

    def fake_unpack(game_dir, *, direct, script_only, progress_callback=None, packer=None):
        assert Path(game_dir) == game
        assert (Path(game_dir) / "assets.rpa").exists()
        if progress_callback:
            progress_callback("direct")
        return {
            "success": True,
            "level": "success",
            "message": "解包完成",
            "method": "direct",
            "count": 1,
            "archives_removed": False,
            "game_dir": str(game_dir),
        }

    monkeypatch.setattr("api.routes.archive.unpack_game", fake_unpack)
    response = client.post("/api/archive/unpack", json={"path": str(game), "direct": True, "script_only": False})
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["archives_removed"] is False
    assert (game / "assets.rpa").exists()
    assert engine.get_status() == Engine.Status.IDLE
    assert client.get("/api/archive").json()["job"]["id"] == job["id"]


def test_decompile_overwrite_requires_confirm(archive_app):
    client, _, _, project, _ = archive_app
    response = client.post(
        "/api/archive/decompile",
        json={"path": str(project), "overwrite": True, "confirm_overwrite": False},
    )
    assert response.status_code == 400


def test_pack_requires_confirm_and_conflicts_with_busy_engine(archive_app, monkeypatch):
    client, _, engine, project, game = archive_app
    out = project / "out.rpa"
    response = client.post(
        "/api/archive/pack",
        json={"source_dir": str(game), "output_file": str(out), "max_part_size": "1G", "confirm": False},
    )
    assert response.status_code == 400
    assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
    response = client.post(
        "/api/archive/pack",
        json={"source_dir": str(game), "output_file": str(out), "max_part_size": "1G", "confirm": True},
    )
    assert response.status_code == 409
    engine.release_status(Engine.Status.TRANSLATING)


def _capture_pack(monkeypatch):
    calls = []

    def fake_pack(source_dir, output_file, *, max_part_size_bytes=None, progress_callback=None, stop_check=None):
        calls.append({"source": source_dir, "output": output_file, "max_part": max_part_size_bytes})
        return {"success": True, "message": "打包完成", "outputs": [output_file]}

    monkeypatch.setattr("api.routes.archive.pack_directory", fake_pack)
    return calls


@pytest.mark.parametrize("output_file", ["", "   "])
def test_pack_blank_output_is_derived_on_server(archive_app, monkeypatch, output_file):
    client, _, engine, project, game = archive_app
    calls = _capture_pack(monkeypatch)
    response = client.post(
        "/api/archive/pack",
        json={"source_dir": str(game), "output_file": output_file, "confirm": True},
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    expected = str((project / "game.rpa").resolve())
    assert job["status"] == "done", job
    assert job["result"]["output_file"] == expected
    assert calls == [{"source": str(game.resolve()), "output": expected, "max_part": None}]
    assert engine.get_status() == Engine.Status.IDLE


def test_pack_rejects_non_rpa_output(archive_app, monkeypatch):
    client, _, _, project, game = archive_app
    calls = _capture_pack(monkeypatch)
    response = client.post(
        "/api/archive/pack",
        json={"source_dir": str(game), "output_file": str(project / "out.zip"), "confirm": True},
    )
    assert response.status_code == 400
    assert calls == []


@pytest.mark.parametrize("part, expected", [(None, None), ("1G", 1024 ** 3), ("512M", 512 * 1024 ** 2)])
def test_pack_split_switch_passes_none_or_size(archive_app, monkeypatch, part, expected):
    client, _, _, project, game = archive_app
    calls = _capture_pack(monkeypatch)
    response = client.post(
        "/api/archive/pack",
        json={"source_dir": str(game), "output_file": str(project / "out.rpa"), "max_part_size": part, "confirm": True},
    )
    assert response.status_code == 200, response.text
    assert _finish(client, response.json()["job"]["id"])["status"] == "done"
    assert calls[0]["max_part"] == expected


def test_pack_split_enabled_still_validates_size(archive_app, monkeypatch):
    client, _, _, project, game = archive_app
    calls = _capture_pack(monkeypatch)
    for bad in ["", "abc", "0G"]:
        response = client.post(
            "/api/archive/pack",
            json={"source_dir": str(game), "output_file": str(project / "out.rpa"), "max_part_size": bad, "confirm": True},
        )
        assert response.status_code == 400, bad
    assert calls == []


def test_cleanup_rpyc_only_removes_rpyc_with_matching_rpy(archive_app):
    client, _, engine, project, game = archive_app
    (game / "script.rpyc").write_bytes(b"compiled")
    (game / "orphan.rpyc").write_bytes(b"only-source")
    tl = game / "tl" / "chinese"
    tl.mkdir(parents=True)
    (tl / "script.rpy").write_text("", encoding="utf-8")
    (tl / "script.rpyc").write_bytes(b"tl-compiled")
    (tl / "orphan.rpyc").write_bytes(b"tl-only")
    response = client.post("/api/archive/cleanup-rpyc", json={"path": str(project)})
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done", job
    assert job["result"]["count"] == 2
    assert not (game / "script.rpyc").exists()
    assert (game / "script.rpy").exists()
    assert (game / "orphan.rpyc").exists()
    assert not (tl / "script.rpyc").exists()
    assert (tl / "script.rpy").exists()
    assert (tl / "orphan.rpyc").exists()
    assert engine.get_status() == Engine.Status.IDLE


def test_cleanup_temp_job_uses_whitelist(archive_app):
    client, _, engine, project, game = archive_app
    (project / "unrpyc.py").write_text("tool", encoding="utf-8")
    (project / "notes.txt").write_text("user", encoding="utf-8")
    response = client.post("/api/archive/cleanup-temp", json={"path": str(game)})
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done", job
    assert not (project / "unrpyc.py").exists()
    assert (project / "notes.txt").exists()
    assert (game / "script.rpy").exists()
    assert engine.get_status() == Engine.Status.IDLE


def test_cleanup_rejects_missing_path_and_stale_project(archive_app):
    client, _, _, project, game = archive_app
    for endpoint in ("cleanup-temp", "cleanup-rpyc"):
        assert client.post(f"/api/archive/{endpoint}", json={"path": str(project / "missing")}).status_code == 400
        response = client.post(f"/api/archive/{endpoint}", json={"path": str(game), "project_key": "old"})
        assert response.status_code == 409


def test_unpack_cancel_waits_for_thread(archive_app, monkeypatch):
    client, _, engine, project, game = archive_app
    release = {"go": False}

    def slow_unpack(game_dir, *, direct, script_only, progress_callback=None, packer=None):
        while not release["go"]:
            time.sleep(0.01)
        return {
            "success": True,
            "level": "success",
            "message": "完成",
            "method": "direct",
            "count": 0,
            "archives_removed": False,
            "game_dir": str(game_dir),
        }

    monkeypatch.setattr("api.routes.archive.unpack_game", slow_unpack)
    job_id = client.post("/api/archive/unpack", json={"path": str(game)}).json()["job"]["id"]
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
    assert engine.get_status() == Engine.Status.TESTING
    release["go"] = True
    job = _finish(client, job_id)
    assert job["status"] == "cancelled"
    assert engine.get_status() == Engine.Status.IDLE
