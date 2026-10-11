"""game-mod API：真实 game 校验、未知键、确认与忙碌、冻结 owner 守卫。"""
from __future__ import annotations

import threading
import time
from importlib import import_module
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes.game_mod import router
from api.routes.jobs import router as jobs_router
from module.Config import Config
from module.Engine.Engine import Engine

mod_injector_module = import_module("module.Tool.ModInjector")


@pytest.fixture
def mod_app(tmp_path, monkeypatch):
    config = Config()
    config.renpy_project_path = ""
    config.renpy_game_folder = ""
    config.renpy_tl_folder = ""
    config.input_folder = ""
    config.output_folder = ""
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    resource_root = tmp_path / "resources"
    resources = {
        "hook_gallery_unlock.rpy": resource_root / "hook_gallery_unlock.rpy",
        "0x52-URM-2.6.2.rpa": resource_root / "0x52-URM-2.6.2.rpa",
        "hook_urm_button.rpy": resource_root / "hook_urm_button.rpy",
        "hook_simple_modifier.rpy": resource_root / "hook_simple_modifier.rpy",
    }
    for name, path in resources.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"resource:{name}", encoding="utf-8")
    monkeypatch.setattr(
        mod_injector_module,
        "get_resource_path",
        lambda *parts: str(resource_root if parts[-1] == "mods" else resources[parts[-1]]),
    )
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.include_router(router)
    app.include_router(jobs_router)
    game = tmp_path / "Demo" / "game"
    game.mkdir(parents=True)
    with TestClient(app) as client:
        yield client, config, engine, game, app.state.jobs
        app.state.jobs.shutdown()


def _bind(config: Config, project: Path) -> None:
    game = project / "game"
    game.mkdir(parents=True, exist_ok=True)
    (game / "tl" / "chinese").mkdir(parents=True, exist_ok=True)
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(game / "tl" / "chinese")
    config.input_folder = str(game / "tl" / "chinese")
    config.output_folder = ""


def _finish(client, job_id, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        result = job.get("result") or {}
        if job["status"] in {"done", "failed", "cancelled"} and not result.get("worker_active"):
            return job
        time.sleep(0.01)
    pytest.fail(f"任务未结束：{job}")


def test_install_uninstall_status(mod_app):
    client, _, engine, game, _ = mod_app
    status = client.get("/api/game-mod", params={"game_path": str(game)}).json()
    assert status["mods"]["gallery_unlock"] is False
    response = client.post(
        "/api/game-mod/install",
        json={"game_path": str(game), "key": "gallery_unlock", "confirm": True},
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert list(job["result"]["owner_identity"]) == ["", "", "", "", ""]
    assert (game / "hook_gallery_unlock.rpy").is_file()
    assert engine.get_status() == Engine.Status.IDLE

    status = client.get("/api/game-mod", params={"game_path": str(game.parent)}).json()
    assert status["mods"]["gallery_unlock"] is True

    response = client.post(
        "/api/game-mod/uninstall",
        json={"game_path": str(game), "key": "gallery_unlock", "confirm": True},
    )
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert not (game / "hook_gallery_unlock.rpy").exists()


def test_unknown_key_and_missing_confirm(mod_app):
    client, _, _, game, _ = mod_app
    response = client.post(
        "/api/game-mod/install",
        json={"game_path": str(game), "key": "not_a_mod", "confirm": True},
    )
    assert response.status_code == 422
    response = client.post(
        "/api/game-mod/install",
        json={"game_path": str(game), "key": "urm", "confirm": False},
    )
    assert response.status_code == 400


def test_reject_non_game_path(mod_app, tmp_path):
    client, _, _, _game, _ = mod_app
    # 使用与 Demo/game 无祖孙关系的孤立目录，避免 resolve 上溯误命中
    other = tmp_path / "orphan_root" / "data"
    other.mkdir(parents=True)
    response = client.post(
        "/api/game-mod/install",
        json={"game_path": str(other), "key": "urm", "confirm": True},
    )
    assert response.status_code == 400


def test_legacy_cleanup_requires_confirm_and_keeps_bak(mod_app):
    client, _, _, game, _ = mod_app
    (game / "dumuqiao.rpy").write_text("legacy", encoding="utf-8")
    (game / "dumuqiao.rpyc").write_bytes(b"c")
    (game / "dumuqiao.rpy.bak").write_text("bak", encoding="utf-8")
    status = client.get("/api/game-mod", params={"game_path": str(game)}).json()
    assert status["legacy_dumuqiao"] is True
    response = client.post(
        "/api/game-mod/cleanup-legacy",
        json={"game_path": str(game), "confirm": False},
    )
    assert response.status_code == 400
    assert (game / "dumuqiao.rpy").exists()
    response = client.post(
        "/api/game-mod/cleanup-legacy",
        json={"game_path": str(game), "confirm": True},
    )
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert not (game / "dumuqiao.rpy").exists()
    assert (game / "dumuqiao.rpy.bak").read_text(encoding="utf-8") == "bak"


def test_empty_owner_bind_before_write_rejects_install(mod_app, monkeypatch, tmp_path):
    """未绑定空 owner 受理后、写前绑定 A：失败且不安装模组文件。"""
    client, config, engine, game, _ = mod_app
    other = tmp_path / "BoundA"
    mod_api = __import__("api.routes.game_mod", fromlist=["_project_identity"])
    real = mod_api._project_identity
    entered, release = threading.Event(), threading.Event()
    calls = {"n": 0}

    def wrapped(config_obj):
        calls["n"] += 1
        if calls["n"] > 1:
            entered.set()
            assert release.wait(5)
        return real(config_obj)

    monkeypatch.setattr(mod_api, "_project_identity", wrapped)
    try:
        response = client.post(
            "/api/game-mod/install",
            json={"game_path": str(game), "key": "gallery_unlock", "confirm": True},
        )
        assert response.status_code == 200, response.text
        job_id = response.json()["job"]["id"]
        assert entered.wait(3), "未进入写前 owner 校验"
        _bind(config, other)
        release.set()
        job = _finish(client, job_id)
    finally:
        release.set()

    assert job["status"] == "failed"
    assert job["result"]["written"] is False
    assert "项目已切换" in (job["error"] or job["result"].get("message") or "")
    assert not (game / "hook_gallery_unlock.rpy").exists()
    assert engine.get_status() == Engine.Status.IDLE


def test_bound_owner_switch_rejects_install(mod_app, monkeypatch, tmp_path):
    """已绑定 A 启动后切到 C：拒绝写入；手动 game 目标不被 owner 混入。"""
    client, config, engine, game, _ = mod_app
    project_a = tmp_path / "ProjectA"
    project_c = tmp_path / "ProjectC"
    _bind(config, project_a)
    mod_api = __import__("api.routes.game_mod", fromlist=["_project_identity"])
    real = mod_api._project_identity
    entered, release = threading.Event(), threading.Event()
    calls = {"n": 0}
    frozen_at_start = real(config)

    def wrapped(config_obj):
        calls["n"] += 1
        if calls["n"] > 1:
            entered.set()
            assert release.wait(5)
        return real(config_obj)

    monkeypatch.setattr(mod_api, "_project_identity", wrapped)
    try:
        response = client.post(
            "/api/game-mod/install",
            json={"game_path": str(game), "key": "gallery_unlock", "confirm": True},
        )
        assert response.status_code == 200, response.text
        assert list(response.json()["job"]["result"]["owner_identity"]) == list(frozen_at_start)
        # project_key 是手动 game 目标键，不是绑定 owner 路径混写
        assert response.json()["job"]["result"]["game_dir"] == str(game)
        job_id = response.json()["job"]["id"]
        assert entered.wait(3)
        _bind(config, project_c)
        release.set()
        job = _finish(client, job_id)
    finally:
        release.set()

    assert job["status"] == "failed"
    assert job["result"]["written"] is False
    assert not (game / "hook_gallery_unlock.rpy").exists()
    assert str(config.renpy_project_path) == str(project_c)
    assert engine.get_status() == Engine.Status.IDLE


def test_unbound_stable_install_succeeds(mod_app):
    """合法未绑定且全程保持空 owner：可完成手动 game 安装。"""
    client, config, engine, game, _ = mod_app
    assert not any(
        [
            config.renpy_project_path,
            config.renpy_game_folder,
            config.renpy_tl_folder,
            config.input_folder,
            config.output_folder,
        ]
    )
    response = client.post(
        "/api/game-mod/install",
        json={"game_path": str(game), "key": "simple_modifier", "confirm": True},
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["written"] is True
    assert list(job["result"]["owner_identity"]) == ["", "", "", "", ""]
    assert (game / "hook_simple_modifier.rpy").is_file()
    assert engine.get_status() == Engine.Status.IDLE


def test_status_returns_owner_identity_snapshot(mod_app):
    client, config, _, game, _ = mod_app
    status = client.get("/api/game-mod", params={"game_path": str(game)}).json()
    assert list(status["owner_identity"]) == ["", "", "", "", ""]
    _bind(config, game.parent.parent / "Bound")
    status = client.get("/api/game-mod", params={"game_path": str(game)}).json()
    assert status["owner_identity"][0]
    assert len(status["owner_identity"]) == 5


def test_stale_owner_identity_rejects_before_job(mod_app, tmp_path):
    """携带过期 owner_identity → 创建任务前 409，不写模组文件。"""
    client, config, engine, game, _ = mod_app
    _bind(config, tmp_path / "ProjectA")
    stale = client.get("/api/game-mod", params={"game_path": str(game)}).json()["owner_identity"]
    _bind(config, tmp_path / "ProjectB")
    response = client.post(
        "/api/game-mod/install",
        json={
            "game_path": str(game),
            "key": "gallery_unlock",
            "confirm": True,
            "owner_identity": stale,
        },
    )
    assert response.status_code == 409
    assert not (game / "hook_gallery_unlock.rpy").exists()
    assert engine.get_status() == Engine.Status.IDLE


def test_owner_identity_type_rejected(mod_app):
    client, _, _, game, _ = mod_app
    response = client.post(
        "/api/game-mod/install",
        json={"game_path": str(game), "key": "urm", "confirm": True, "owner_identity": {"a": 1}},
    )
    assert response.status_code == 422


def test_cancel_after_write_reports_partial(mod_app, monkeypatch):
    """安装写入后取消 → written/partial=true、success=false。"""
    client, _, engine, game, _ = mod_app
    real_install = mod_injector_module.ModInjector.install
    wrote, release = threading.Event(), threading.Event()

    def gated(self, game_path, key):
        ok, message = real_install(self, game_path, key)
        wrote.set()
        assert release.wait(5)
        return ok, message

    monkeypatch.setattr(mod_injector_module.ModInjector, "install", gated)
    try:
        response = client.post(
            "/api/game-mod/install",
            json={"game_path": str(game), "key": "gallery_unlock", "confirm": True},
        )
        assert response.status_code == 200, response.text
        job_id = response.json()["job"]["id"]
        assert wrote.wait(3)
        assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
        release.set()
        job = _finish(client, job_id)
    finally:
        release.set()

    assert job["status"] == "cancelled"
    result = job["result"] or {}
    assert result.get("written") is True
    assert result.get("partial") is True
    assert result.get("success") is False
    assert (game / "hook_gallery_unlock.rpy").is_file()
    assert engine.get_status() == Engine.Status.IDLE
