"""译文复用 API：预览只读、路径冲突、执行备份。"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes.jobs import router as jobs_router
from api.routes.translation_reuse import router
from module.Config import Config
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import RenpyProjectPaths


@pytest.fixture
def reuse_client(tmp_path, monkeypatch):
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


def _make_junction(link: Path, target: Path) -> None:
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not link.exists():
        pytest.skip(f"无法创建目录联接: {completed.stderr or completed.stdout}")


def _finish(client, job_id, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError("timeout")


def _pair(tmp_path: Path):
    source = tmp_path / "old" / "chinese"
    target = tmp_path / "game" / "tl" / "chinese"
    source.mkdir(parents=True)
    target.mkdir(parents=True)
    source.joinpath("a.rpy").write_text(
        'translate chinese strings:\n'
        '    old "Hello"\n'
        '    new "你好"\n'
        '    old "World"\n'
        '    new "世界"\n',
        encoding="utf-8",
    )
    target.joinpath("a.rpy").write_text(
        'translate chinese strings:\n'
        '    old "Hello"\n'
        '    new ""\n'
        '    old "World"\n'
        '    new "人工"\n',
        encoding="utf-8",
    )
    return source, target


def test_preview_is_readonly(reuse_client):
    client, engine, tmp_path, _ = reuse_client
    source, target = _pair(tmp_path)
    before = target.joinpath("a.rpy").read_text(encoding="utf-8")
    response = client.post("/api/translation-reuse/preview", json={
        "source_dir": str(source),
        "target_dir": str(target),
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["written"] is False
    assert job["result"]["reusable_entries"] >= 1
    assert job["result"]["conflicts"] >= 1
    assert target.joinpath("a.rpy").read_text(encoding="utf-8") == before
    assert engine.get_status() == Engine.Status.IDLE


def test_overlap_and_same_rejected(reuse_client):
    client, _, tmp_path, _ = reuse_client
    source, target = _pair(tmp_path)
    assert client.post("/api/translation-reuse/preview", json={
        "source_dir": str(target),
        "target_dir": str(target),
    }).status_code == 400
    nested = target / "nested"
    nested.mkdir()
    assert client.post("/api/translation-reuse/preview", json={
        "source_dir": str(target),
        "target_dir": str(nested),
    }).status_code == 400


def test_execute_requires_confirm_and_backs_up_outside_game(reuse_client):
    client, engine, tmp_path, _ = reuse_client
    source, target = _pair(tmp_path)
    assert client.post("/api/translation-reuse/execute", json={
        "source_dir": str(source),
        "target_dir": str(target),
        "confirm": False,
    }).status_code == 400
    response = client.post("/api/translation-reuse/execute", json={
        "source_dir": str(source),
        "target_dir": str(target),
        "confirm": True,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done", job
    result = job["result"]
    assert result["applied_entries"] >= 1
    assert "failed_files" in result
    if result.get("backup_path"):
        backup = Path(result["backup_path"])
        assert backup.is_dir()
        assert "game" not in [p.name.lower() for p in backup.parents if p != backup]
        # 备份应在 game 外（项目根）
        assert backup.parent == tmp_path or (tmp_path / "game") not in backup.parents
    content = target.joinpath("a.rpy").read_text(encoding="utf-8")
    assert "你好" in content
    assert "人工" in content  # 冲突保留
    assert engine.get_status() == Engine.Status.IDLE


def test_reuse_delayed_owner_replay_rejected(reuse_client):
    """探针 3（reuse）：owner 切走后旧 body 重放拒绝。"""
    client, engine, tmp_path, config = reuse_client
    owner = tmp_path / "Owner"
    other = tmp_path / "Other"
    owner_key = _bind(config, owner)
    source, target = _pair(tmp_path / "ManualB-reuse")
    status = client.get(
        "/api/translation-reuse",
        params={"source_dir": str(source), "target_dir": str(target)},
    ).json()
    assert status["owner_project_key"] == owner_key
    body = {
        "source_dir": str(source),
        "target_dir": str(target),
        "project_key": status["project_key"],
        "owner_project_key": owner_key,
        "confirm": True,
    }
    legal = client.post("/api/translation-reuse/execute", json=body)
    assert legal.status_code == 200, legal.text
    assert _finish(client, legal.json()["job"]["id"])["status"] == "done"

    # 重置目标后切 owner，旧 body 不得再写
    target.joinpath("a.rpy").write_text(
        'translate chinese strings:\n'
        '    old "Hello"\n'
        '    new ""\n',
        encoding="utf-8",
    )
    _bind(config, other)
    delayed = client.post("/api/translation-reuse/execute", json=body)
    assert delayed.status_code == 409
    assert 'new ""' in target.joinpath("a.rpy").read_text(encoding="utf-8")
    assert engine.get_status() == Engine.Status.IDLE


def test_reuse_rejects_junction_under_target(reuse_client):
    """探针 6（reuse）：目标含向外联接时拒绝。"""
    client, engine, tmp_path, _ = reuse_client
    source, target = _pair(tmp_path)
    outside = tmp_path / "OutsideReuse"
    outside.mkdir()
    (outside / "x.rpy").write_text('old "x"\n', encoding="utf-8")
    _make_junction(target / "linked", outside)
    before = (outside / "x.rpy").read_text(encoding="utf-8")
    response = client.post("/api/translation-reuse/execute", json={
        "source_dir": str(source),
        "target_dir": str(target),
        "confirm": True,
    })
    assert response.status_code in {400, 409}
    assert (outside / "x.rpy").read_text(encoding="utf-8") == before
    assert engine.get_status() == Engine.Status.IDLE
