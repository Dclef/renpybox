"""格式化 API：真实文本处理与失败反馈。"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes.formatter import router
from api.routes.jobs import router as jobs_router
from module.Config import Config
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Tool.Formatter import Formatter


@pytest.fixture
def formatter_client(tmp_path, monkeypatch):
    config = Config()
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    monkeypatch.setattr(Config, "save", lambda self, *args, **kwargs: self)
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.include_router(router)
    app.include_router(jobs_router)
    with TestClient(app) as client:
        yield client, engine, tmp_path, config
        app.state.jobs.shutdown()


def _finish(client, job_id, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError("timeout")


def _bind(config: Config, project: Path, language: str = "chinese") -> str:
    game = project / "game"
    tl = game / "tl" / language
    tl.mkdir(parents=True, exist_ok=True)
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(tl)
    config.input_folder = str(tl)
    paths = RenpyProjectPaths.from_config(config)
    assert paths is not None
    return paths.project_key


def test_shared_formatter_tabs_and_string_tabs(tmp_path):
    folder = tmp_path / "scripts"
    folder.mkdir()
    path = folder / "a.rpy"
    path.write_text('\tlabel start:\n\t    "has\ttab"  \n', encoding="utf-8")
    formatter = Formatter()
    count = formatter.format_folder(str(folder))
    assert count == 1
    text = path.read_text(encoding="utf-8")
    assert text.startswith("    label start:")
    assert '"has\ttab"' in text  # 字符串内 Tab 不动
    assert not text.rstrip().endswith(" ")
    # 第二次无变更仍计成功处理
    assert formatter.format_folder(str(folder)) == 1
    assert formatter.last_modified_count == 0
    assert formatter.last_failed_files == []


def test_format_api_success_count_not_modified_count(formatter_client):
    client, engine, tmp_path, _ = formatter_client
    folder = tmp_path / "game"
    folder.mkdir()
    (folder / "ok.rpy").write_text('label start:\n    pass\n', encoding="utf-8")
    (folder / "tab.rpy").write_text('\tpass\n', encoding="utf-8")
    assert client.post("/api/formatter/format", json={
        "folder": str(folder),
        "confirm": False,
    }).status_code == 400
    response = client.post("/api/formatter/format", json={
        "folder": str(folder),
        "preserve_comments": True,
        "fix_indent": True,
        "remove_trailing": True,
        "confirm": True,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done", job
    # 成功处理数 = 全部文件，含无需修改的
    assert job["result"]["success_count"] == 2
    assert job["result"]["written"] is True
    assert "改动" not in (job["result"].get("message") or "")
    assert "成功处理" in job["result"]["message"]
    assert engine.get_status() == Engine.Status.IDLE


def test_format_noop_written_false_success_count_one(formatter_client):
    """探针 2：已格式化文件 success_count=1 但 written=false。"""
    client, engine, tmp_path, _ = formatter_client
    folder = tmp_path / "AlreadyFormatted"
    folder.mkdir()
    (folder / "same.rpy").write_text('label start:\n    pass\n', encoding="utf-8")
    response = client.post("/api/formatter/format", json={
        "folder": str(folder),
        "confirm": True,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["success_count"] == 1
    assert job["result"]["written"] is False
    assert int(job["result"].get("modified_count") or 0) == 0
    assert engine.get_status() == Engine.Status.IDLE


def test_format_api_reports_failures(formatter_client, monkeypatch):
    client, engine, tmp_path, _ = formatter_client
    folder = tmp_path / "game"
    folder.mkdir()
    (folder / "a.rpy").write_text("pass\n", encoding="utf-8")

    def boom(self, *args, **kwargs):
        self.last_failed_files = ["a.rpy"]
        self.last_modified_count = 0
        return 0

    monkeypatch.setattr(Formatter, "format_folder", boom)
    response = client.post("/api/formatter/format", json={
        "folder": str(folder),
        "confirm": True,
    })
    job = _finish(client, response.json()["job"]["id"])
    assert job["result"]["partial"] is True or job["result"]["success"] is False
    assert job["result"]["failed_files"] == ["a.rpy"]
    assert engine.get_status() == Engine.Status.IDLE


def test_format_delayed_owner_replay_rejected(formatter_client):
    """探针 3（formatter）：owner 切走后旧 body 重放拒绝。"""
    client, engine, tmp_path, config = formatter_client
    owner = tmp_path / "Owner"
    other = tmp_path / "Other"
    manual = tmp_path / "ManualB-format"
    owner_key = _bind(config, owner)
    manual.mkdir()
    (manual / "scene.rpy").write_text('\tpass\n', encoding="utf-8")
    status = client.get("/api/formatter", params={"folder": str(manual)}).json()
    assert status["owner_project_key"] == owner_key
    body = {
        "folder": str(manual),
        "project_key": status["project_key"],
        "owner_project_key": owner_key,
        "confirm": True,
    }
    legal = client.post("/api/formatter/format", json=body)
    assert legal.status_code == 200
    assert _finish(client, legal.json()["job"]["id"])["status"] == "done"

    (manual / "scene.rpy").write_text('\tpass\n', encoding="utf-8")
    _bind(config, other)
    delayed = client.post("/api/formatter/format", json=body)
    assert delayed.status_code == 409
    assert "\t" in (manual / "scene.rpy").read_text(encoding="utf-8")
    assert engine.get_status() == Engine.Status.IDLE
