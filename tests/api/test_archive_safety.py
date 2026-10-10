"""归档 API 的路径快照、源档保留、线程取消与引擎释放回归。"""
from __future__ import annotations

import threading
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
from module.Tool.ArchiveOps import pack_directory, resolve_game_dir, resolve_pack_source, unpack_game


@pytest.fixture
def archive_client(tmp_path, monkeypatch):
    config = Config()
    config.renpy_project_path = config.renpy_game_folder = config.renpy_tl_folder = ""
    config.input_folder = config.output_folder = ""
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    app = FastAPI()
    app.state.config = config
    events = []
    app.state.jobs = JobManager(publish=events.append, min_interval=0)
    app.include_router(router)
    app.include_router(jobs_router)
    with TestClient(app) as client:
        yield client, engine, app.state.jobs, events
        app.state.jobs.shutdown()


def finish(client, job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "failed", "cancelled"}:
            assert job["result"]["worker_active"] is False
            return job
        time.sleep(0.01)
    pytest.fail(f"任务未结束：{job}")


def request_body(kind, game):
    if kind == "pack":
        return {"source_dir": str(game), "output_file": str(game.parent / "out.rpa"), "confirm": True}
    return {"path": str(game)}


def test_real_pack_unpack_roundtrip_keeps_rpa_and_rpyc_without_bound_project(archive_client, tmp_path, monkeypatch):
    client, engine, _, events = archive_client
    source = tmp_path / "source" / "game"
    target = tmp_path / "target" / "game"
    source.mkdir(parents=True)
    target.mkdir(parents=True)
    contents = {"script.rpy": b'label start:\n    "hello"\n', "script.rpyc": b"compiled-original", "images/icon.bin": bytes(range(64))}
    for name, data in contents.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    monkeypatch.chdir(tmp_path)
    output = target / "assets.rpa"
    response = client.post("/api/archive/pack", json={
        "source_dir": str(source), "output_file": "target/game/assets.rpa", "max_part_size": None, "confirm": True,
    })
    assert response.status_code == 200, response.text
    packed = finish(client, response.json()["job"]["id"])
    assert packed["status"] == "done", packed
    assert packed["result"]["output_file"] == str(output.resolve())
    assert any(event["job"]["total"] == len(contents) for event in events)
    assert client.get("/api/archive").json()["job"]["id"] == packed["id"]
    original_archive = output.read_bytes()
    response = client.post("/api/archive/unpack", json={"path": str(target), "direct": False})
    assert response.status_code == 200, response.text
    unpacked = finish(client, response.json()["job"]["id"])
    assert unpacked["status"] == "done", unpacked
    assert unpacked["result"]["archives_removed"] is False
    assert output.read_bytes() == original_archive
    for name, data in contents.items():
        assert (target / name).read_bytes() == data
        assert (source / name).read_bytes() == data
    assert client.get("/api/archive").json()["job"]["id"] == unpacked["id"]
    assert engine.get_status() == Engine.Status.IDLE


@pytest.mark.parametrize("endpoint, field", [
    ("unpack", "path"), ("decompile", "path"), ("pack", "source_dir"),
    ("cleanup-temp", "path"), ("cleanup-rpyc", "path"),
])
def test_blank_paths_rejected_without_jobs(archive_client, tmp_path, endpoint, field):
    client, engine, manager, _ = archive_client
    body = request_body(endpoint, tmp_path)
    body[field] = " \t "
    assert client.post(f"/api/archive/{endpoint}", json=body).status_code == 422
    assert not manager.list()
    assert engine.get_status() == Engine.Status.IDLE


@pytest.mark.parametrize("resolve", [resolve_game_dir, resolve_pack_source, unpack_game])
def test_shared_operations_reject_empty_paths(resolve):
    with pytest.raises(ValueError):
        resolve("")


def test_shared_pack_rejects_empty_output(tmp_path):
    with pytest.raises(ValueError):
        pack_directory(tmp_path, "")


@pytest.mark.parametrize("kind, operation", [("unpack", "unpack_game"), ("decompile", "decompile_target"), ("pack", "pack_directory")])
def test_failed_operation_releases_engine(archive_client, tmp_path, monkeypatch, kind, operation):
    client, engine, _, _ = archive_client
    game = tmp_path / "game"
    game.mkdir()

    def fail(*args, **kwargs):
        raise OSError("模拟磁盘失败")

    monkeypatch.setattr(f"api.routes.archive.{operation}", fail)
    response = client.post(f"/api/archive/{kind}", json=request_body(kind, game))
    assert response.status_code == 200, response.text
    job = finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"
    assert "模拟磁盘失败" in job["error"]
    assert engine.get_status() == Engine.Status.IDLE


@pytest.mark.parametrize("kind, operation", [("unpack", "unpack_game"), ("decompile", "decompile_target"), ("pack", "pack_directory")])
def test_cancel_waits_for_worker_and_blocks_other_tasks(archive_client, tmp_path, monkeypatch, kind, operation):
    client, engine, _, _ = archive_client
    game = tmp_path / "game"
    game.mkdir()
    entered, release = threading.Event(), threading.Event()
    after_cancel = []

    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        callback = kwargs["progress_callback"]
        after_cancel.append(True)
        if kind == "pack":
            assert kwargs["stop_check"]()
            callback(1, 2, "取消后的进度")
            raise RuntimeError("打包已取消")
        callback("取消后的日志仍可消费")
        return {"success": True, "message": "完成"}

    monkeypatch.setattr(f"api.routes.archive.{operation}", slow)
    try:
        response = client.post(f"/api/archive/{kind}", json=request_body(kind, game))
        assert response.status_code == 200, response.text
        job_id = response.json()["job"]["id"]
        assert entered.wait(2)
        assert client.get("/api/archive").json()["job"]["id"] == job_id
        assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
        assert engine.get_status() == Engine.Status.TESTING
        assert client.get(f"/api/jobs/{job_id}").json()["result"]["worker_active"] is True
        assert not engine.try_begin_single_task()
        assert not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
        assert client.post("/api/archive/unpack", json={"path": str(game)}).status_code == 409
    finally:
        release.set()
    # Qt5 只有打包可取消；解包/反编译收到取消请求仍跑完并如实报告完成。
    assert finish(client, job_id)["status"] == ("cancelled" if kind == "pack" else "done")
    assert after_cancel == [True]
    assert engine.get_status() == Engine.Status.IDLE


@pytest.mark.parametrize("busy", ["single", "barrier", "translation"])
def test_atomic_engine_acquisition_respects_all_busy_states(archive_client, tmp_path, busy):
    client, engine, manager, _ = archive_client
    game = tmp_path / "game"
    game.mkdir()
    if busy == "single":
        assert engine.try_begin_single_task()
    elif busy == "barrier":
        engine.set_stop_barrier(True)
    else:
        assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
    assert client.post("/api/archive/unpack", json={"path": str(game)}).status_code == 409
    assert not manager.list()


def test_stale_project_key_rejected_after_project_is_cleared(archive_client, tmp_path):
    client, engine, manager, _ = archive_client
    game = tmp_path / "game"
    game.mkdir()
    response = client.post("/api/archive/unpack", json={"path": str(game), "project_key": "old-project"})
    assert response.status_code == 409
    assert not manager.list()
    assert engine.get_status() == Engine.Status.IDLE


def test_decompile_api_preserves_existing_rpyc(archive_client, tmp_path, monkeypatch):
    client, engine, _, _ = archive_client
    game = tmp_path / "game"
    game.mkdir()
    compiled = game / "script.rpyc"
    compiled.write_bytes(b"original-compiled-data")

    class Decompiler:
        def decompile(self, target, *, overwrite, output_callback):
            assert overwrite is False
            (game / "script.rpy").write_text("label start:\n    pass\n", encoding="utf-8")
            output_callback("反编译完成")

    monkeypatch.setattr("module.Tool.ArchiveOps.RenpyDecompiler", Decompiler)
    response = client.post("/api/archive/decompile", json={"path": str(tmp_path), "use_unren": False})
    assert response.status_code == 200, response.text
    job = finish(client, response.json()["job"]["id"])
    assert job["status"] == "done", job
    assert compiled.read_bytes() == b"original-compiled-data"
    assert engine.get_status() == Engine.Status.IDLE
