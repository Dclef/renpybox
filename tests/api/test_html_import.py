"""html-import API：独立路径、确认覆盖、忙碌拒绝、冻结 owner 守卫。"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes.html_import import router
from api.routes.jobs import router as jobs_router
from module.Config import Config
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import RenpyProjectPaths


@pytest.fixture
def html_app(tmp_path, monkeypatch):
    config = Config()
    # 默认未绑定：空字段 identity，供独立路径工具使用
    config.renpy_project_path = ""
    config.renpy_game_folder = ""
    config.renpy_tl_folder = ""
    config.input_folder = ""
    config.output_folder = ""
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.include_router(router)
    app.include_router(jobs_router)
    with TestClient(app) as client:
        yield client, config, engine, tmp_path, app.state.jobs
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


def _make_tl(root: Path) -> Path:
    tl = root / "game" / "tl" / "chinese"
    tl.mkdir(parents=True)
    (tl / "script.rpy").write_text(
        'translate chinese strings:\n    old "Hello"\n    new ""\n',
        encoding="utf-8",
    )
    return tl


def test_extract_apply_roundtrip_api(html_app):
    client, _, engine, tmp_path, _ = html_app
    tl = _make_tl(tmp_path / "Demo")
    txt = tmp_path / "pending.txt"
    response = client.post(
        "/api/html-import/extract",
        json={"tl_dir": str(tl), "txt_output": str(txt)},
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["count"] == 1
    assert list(job["result"]["owner_identity"]) == ["", "", "", "", ""]
    assert engine.get_status() == Engine.Status.IDLE

    manifest = job["result"]["manifest_path"]
    translated = tmp_path / "done.txt"
    translated.write_text("你好\n", encoding="utf-8")
    out = tmp_path / "Demo" / "game" / "tl" / "chinese_translated"
    response = client.post(
        "/api/html-import/apply",
        json={
            "manifest_path": manifest,
            "translated_txt": str(translated),
            "output_tl_dir": str(out),
            "source_tl_dir": str(tl),
            "confirm_overwrite": False,
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["filled"] == 1
    assert "你好" in (out / "script.rpy").read_text(encoding="utf-8")


def test_apply_overwrite_requires_confirm(html_app):
    client, _, _, tmp_path, _ = html_app
    tl = _make_tl(tmp_path / "Demo")
    txt = tmp_path / "pending.txt"
    job = _finish(
        client,
        client.post("/api/html-import/extract", json={"tl_dir": str(tl), "txt_output": str(txt)}).json()["job"]["id"],
    )
    out = tmp_path / "Demo" / "game" / "tl" / "chinese_translated"
    out.mkdir(parents=True)
    (out / "keep.txt").write_text("keep", encoding="utf-8")
    translated = tmp_path / "done.txt"
    translated.write_text("你好\n", encoding="utf-8")
    response = client.post(
        "/api/html-import/apply",
        json={
            "manifest_path": job["result"]["manifest_path"],
            "translated_txt": str(translated),
            "output_tl_dir": str(out),
            "confirm_overwrite": False,
        },
    )
    assert response.status_code == 400
    assert (out / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_busy_rejects_without_side_effect(html_app):
    client, _, engine, tmp_path, _ = html_app
    engine.set_status(Engine.Status.TESTING)
    tl = _make_tl(tmp_path / "Demo")
    response = client.post(
        "/api/html-import/extract",
        json={"tl_dir": str(tl), "txt_output": str(tmp_path / "x.txt")},
    )
    assert response.status_code == 409
    assert not (tmp_path / "x.txt").exists()


def test_html_txt_converter_endpoints(html_app):
    client, _, _, tmp_path, _ = html_app
    txt = tmp_path / "a.txt"
    txt.write_text("alpha\nbeta\n", encoding="utf-8")
    html = tmp_path / "a.html"
    response = client.post(
        "/api/html-import/txt-to-html",
        json={"txt_path": str(txt), "html_output": str(html), "keep_data": True, "confirm_overwrite": True},
    )
    assert response.status_code == 200
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert html.is_file()

    out = tmp_path / "b.txt"
    response = client.post(
        "/api/html-import/html-to-txt",
        json={"html_path": str(html), "txt_output": str(out), "pairs": False, "confirm_overwrite": True},
    )
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert out.read_text(encoding="utf-8").splitlines() == ["alpha", "beta"]


def test_empty_owner_bind_before_write_rejects_extract(html_app, monkeypatch, tmp_path):
    """未绑定空 owner 受理后、写前绑定项目 A：失败且不产出 TXT。"""
    client, config, engine, root, _ = html_app
    tl = _make_tl(root / "ManualTarget")
    out = root / "pending.txt"
    other = tmp_path / "BoundA"
    html_mod = __import__("api.routes.html_import", fromlist=["_project_identity"])
    real = html_mod._project_identity
    entered, release = threading.Event(), threading.Event()
    calls = {"n": 0}

    def wrapped(config_obj):
        calls["n"] += 1
        # 第 2 次起为写前 check_cancel/owner_still；在此同步点绑定 A
        if calls["n"] > 1:
            entered.set()
            assert release.wait(5)
        return real(config_obj)

    monkeypatch.setattr(html_mod, "_project_identity", wrapped)
    try:
        response = client.post(
            "/api/html-import/extract",
            json={"tl_dir": str(tl), "txt_output": str(out)},
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
    assert not out.exists()
    assert engine.get_status() == Engine.Status.IDLE


def test_bound_owner_switch_rejects_extract(html_app, monkeypatch, tmp_path):
    """已绑定 A 启动后切到 C：拒绝写入；手动 TL 目标不被 owner 污染。"""
    client, config, engine, root, _ = html_app
    project_a = root / "ProjectA"
    project_c = tmp_path / "ProjectC"
    _bind(config, project_a)
    # 手动目标在 A 之外，证明 target 与 owner 分离
    tl = _make_tl(root / "ManualElsewhere")
    out = root / "pending.txt"
    html_mod = __import__("api.routes.html_import", fromlist=["_project_identity"])
    real = html_mod._project_identity
    entered, release = threading.Event(), threading.Event()
    calls = {"n": 0}
    frozen_at_start = real(config)

    def wrapped(config_obj):
        calls["n"] += 1
        if calls["n"] > 1:
            entered.set()
            assert release.wait(5)
        return real(config_obj)

    monkeypatch.setattr(html_mod, "_project_identity", wrapped)
    try:
        response = client.post(
            "/api/html-import/extract",
            json={"tl_dir": str(tl), "txt_output": str(out)},
        )
        assert response.status_code == 200, response.text
        assert list(response.json()["job"]["result"]["owner_identity"]) == list(frozen_at_start)
        job_id = response.json()["job"]["id"]
        assert entered.wait(3)
        _bind(config, project_c)
        release.set()
        job = _finish(client, job_id)
    finally:
        release.set()

    assert job["status"] == "failed"
    assert job["result"]["written"] is False
    assert not out.exists()
    # 手动目标目录未被写成绑定项目路径
    assert RenpyProjectPaths.from_config(config) is not None
    assert str(config.renpy_project_path) == str(project_c)
    assert engine.get_status() == Engine.Status.IDLE


def test_unbound_stable_extract_succeeds(html_app):
    """合法未绑定且全程保持空 owner：可完成独立路径导出。"""
    client, config, engine, root, _ = html_app
    assert not any(
        [
            config.renpy_project_path,
            config.renpy_game_folder,
            config.renpy_tl_folder,
            config.input_folder,
            config.output_folder,
        ]
    )
    tl = _make_tl(root / "Solo")
    out = root / "pending.txt"
    response = client.post(
        "/api/html-import/extract",
        json={"tl_dir": str(tl), "txt_output": str(out)},
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["written"] is True
    assert list(job["result"]["owner_identity"]) == ["", "", "", "", ""]
    assert out.is_file()
    assert engine.get_status() == Engine.Status.IDLE


def test_status_returns_owner_identity_snapshot(html_app):
    client, config, _, tmp_path, _ = html_app
    status = client.get("/api/html-import").json()
    assert list(status["owner_identity"]) == ["", "", "", "", ""]
    _bind(config, tmp_path / "Bound")
    status = client.get("/api/html-import").json()
    assert status["owner_identity"][0]
    assert len(status["owner_identity"]) == 5


def test_stale_owner_identity_rejects_before_job(html_app):
    """携带过期 owner_identity → 创建任务前 409，不写盘、不占引擎。"""
    client, config, engine, tmp_path, _ = html_app
    _bind(config, tmp_path / "ProjectA")
    stale = client.get("/api/html-import").json()["owner_identity"]
    _bind(config, tmp_path / "ProjectB")
    tl = _make_tl(tmp_path / "Demo")
    out = tmp_path / "pending.txt"
    response = client.post(
        "/api/html-import/extract",
        json={"tl_dir": str(tl), "txt_output": str(out), "owner_identity": stale},
    )
    assert response.status_code == 409
    assert not out.exists()
    assert engine.get_status() == Engine.Status.IDLE


def test_owner_identity_type_rejected(html_app):
    client, _, _, tmp_path, _ = html_app
    tl = _make_tl(tmp_path / "Demo")
    response = client.post(
        "/api/html-import/extract",
        json={"tl_dir": str(tl), "txt_output": str(tmp_path / "x.txt"), "owner_identity": "bad"},
    )
    assert response.status_code == 422
    response = client.post(
        "/api/html-import/extract",
        json={"tl_dir": str(tl), "txt_output": str(tmp_path / "x.txt"), "owner_identity": [1, 2]},
    )
    assert response.status_code == 422


def test_cancel_after_write_reports_partial(html_app, monkeypatch):
    """执行器写入后取消 → written/partial=true、success=false，快照可见。"""
    client, _, engine, tmp_path, _ = html_app
    tl = _make_tl(tmp_path / "Demo")
    out = tmp_path / "pending.txt"
    html_mod = __import__("api.routes.html_import", fromlist=["extract_pending_from_tl"])
    real = html_mod.extract_pending_from_tl
    wrote, release = threading.Event(), threading.Event()

    def gated(*args, **kwargs):
        result = real(*args, **kwargs)
        wrote.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(html_mod, "extract_pending_from_tl", gated)
    try:
        response = client.post(
            "/api/html-import/extract",
            json={"tl_dir": str(tl), "txt_output": str(out)},
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
    assert out.is_file()
    assert engine.get_status() == Engine.Status.IDLE
