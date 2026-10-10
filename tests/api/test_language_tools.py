"""语言工具 API：绑定项目、确认、协作取消与写失败。"""
from __future__ import annotations

import ast
import subprocess
import textwrap
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes.jobs import router as jobs_router
from api.routes.language_tools import router
from module.Config import Config
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Tool.LanguageTools import DEFAULT_SCRIPT_NAME, HOOK_NAME


@pytest.fixture
def language_app(tmp_path, monkeypatch):
    project, game = _make_project(tmp_path)
    config = Config()
    paths = _bind(config, project)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.include_router(router)
    app.include_router(jobs_router)
    with TestClient(app) as client:
        yield client, config, engine, project, game, paths, app.state.jobs
        app.state.jobs.shutdown()


def _make_project(root: Path) -> tuple[Path, Path]:
    project = root / "Demo"
    game = project / "game"
    for name in ("chinese", "schinese", "tchinese", "chinese_new", "none"):
        (game / "tl" / name).mkdir(parents=True)
    return project, game


def _bind(config: Config, project: Path) -> RenpyProjectPaths:
    game = project / "game"
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(game / "tl" / "chinese")
    config.input_folder = str(game / "tl" / "chinese")
    config.output_folder = ""
    paths = RenpyProjectPaths.from_config(config)
    assert paths is not None
    return paths


def _finish(client, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        result = job.get("result") or {}
        if job["status"] in {"done", "failed", "cancelled"} and not result.get("worker_active"):
            return job
        time.sleep(0.01)
    pytest.fail(f"任务未结束：{job}")


def _entrance(key, **extra):
    return {"project_key": key, "confirm": True, **extra}


def _default(key, language="schinese", **extra):
    return {"project_key": key, "language": language, "confirm": True, **extra}


def _make_junction(link: Path, target: Path) -> None:
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not link.exists():
        pytest.skip(f"无法创建目录联接: {completed.stderr or completed.stdout}")


def test_get_reports_bound_project_without_abnormal_languages(language_app):
    client, _, _, project, game, paths, _ = language_app
    response = client.get("/api/language-tools")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project_key"] == paths.project_key
    assert Path(body["project_root"]) == project.resolve()
    assert Path(body["game_dir"]) == game.resolve()
    assert body["languages"] == ["chinese", "schinese", "tchinese"]
    assert body["entrance_exists"] is False
    assert body["default_script_exists"] is False
    assert body["default_language"] is None
    assert body["job"] is None


def test_writes_real_hooks_and_keeps_canonical_language(language_app):
    client, _, engine, _, game, paths, _ = language_app
    response = client.post("/api/language-tools/entrance", json=_entrance(paths.project_key))
    assert response.status_code == 200, response.text
    entrance = _finish(client, response.json()["job"]["id"])
    assert entrance["status"] == "done"
    assert entrance["result"]["action"] == "entrance"
    assert entrance["result"]["written"] is True
    assert entrance["result"]["worker_active"] is False
    assert (game / HOOK_NAME).is_file()

    response = client.post("/api/language-tools/default", json=_default(paths.project_key, "schinese"))
    assert response.status_code == 200, response.text
    finished = _finish(client, response.json()["job"]["id"])
    assert finished["status"] == "done"
    assert finished["result"]["language"] == "schinese"
    script = (game / DEFAULT_SCRIPT_NAME).read_text(encoding="utf-8-sig")
    tree = ast.parse(textwrap.dedent("\n".join(script.splitlines()[1:])))
    assert tree.body[0].value.value == "schinese"
    current = client.get("/api/language-tools").json()
    assert current["entrance_exists"] is True
    assert current["default_language"] == "schinese"
    assert current["job"]["id"] == finished["id"]
    assert engine.get_status() == Engine.Status.IDLE


def test_confirmation_project_key_and_foreign_path_are_rejected(language_app, tmp_path):
    client, config, engine, _, game, paths, manager = language_app
    refused = client.post(
        "/api/language-tools/entrance",
        json={"project_key": paths.project_key, "confirm": False},
    )
    assert refused.status_code == 400
    assert HOOK_NAME in refused.json()["detail"]
    assert client.post("/api/language-tools/default", json={"language": "schinese", "confirm": True}).status_code == 400
    assert client.post(
        "/api/language-tools/entrance",
        json=_entrance(paths.project_key + "-stale"),
    ).status_code == 409
    assert client.post(
        "/api/language-tools/entrance",
        json={**_entrance(paths.project_key), "game_dir": str(tmp_path)},
    ).status_code == 422
    config.renpy_project_path = config.renpy_game_folder = config.renpy_tl_folder = ""
    config.input_folder = config.output_folder = ""
    assert client.get("/api/language-tools").status_code == 400
    assert client.post(
        "/api/language-tools/default",
        json=_default("expired", "schinese"),
    ).status_code == 400
    assert not (game / HOOK_NAME).exists()
    assert not manager.list()
    assert engine.get_status() == Engine.Status.IDLE


@pytest.mark.parametrize("language", ["../evil", 'a"b', "a\\b", "CON", "chinese_new", "schinese.", ""])
def test_illegal_language_and_missing_tl_do_not_write(language_app, language):
    client, _, engine, _, game, paths, manager = language_app
    response = client.post("/api/language-tools/default", json=_default(paths.project_key, language))
    assert response.status_code == 400
    assert client.post(
        "/api/language-tools/default",
        json=_default(paths.project_key, "japanese"),
    ).status_code == 400
    assert not (game / DEFAULT_SCRIPT_NAME).exists()
    assert not manager.list()
    assert engine.get_status() == Engine.Status.IDLE


def test_directory_and_escaping_game_link_are_rejected(language_app, tmp_path):
    client, config, engine, project, game, paths, manager = language_app
    (game / HOOK_NAME).mkdir()
    response = client.post("/api/language-tools/entrance", json=_entrance(paths.project_key))
    assert response.status_code == 400
    assert (game / HOOK_NAME).is_dir()

    outside = tmp_path / "outside"
    (outside / "tl" / "chinese").mkdir(parents=True)
    linked = tmp_path / "linked"
    linked.mkdir()
    _make_junction(linked / "game", outside)
    _bind(config, linked)
    linked_paths = RenpyProjectPaths.from_config(config)
    assert linked_paths is not None
    response = client.post("/api/language-tools/entrance", json=_entrance(linked_paths.project_key))
    assert response.status_code == 400
    assert "越出" in response.json()["detail"]
    assert not (outside / HOOK_NAME).exists()
    assert not manager.list()
    assert engine.get_status() == Engine.Status.IDLE
    assert project.exists()


def test_missing_resource_and_failed_write_keep_old_file(language_app, monkeypatch):
    client, _, engine, _, game, paths, _ = language_app
    target = game / HOOK_NAME
    target.write_text("旧钩子", encoding="utf-8")
    import module.Tool.LanguageTools as tools
    monkeypatch.setattr(tools, "get_resource_path", lambda *parts: str(game / "missing-resource"))
    assert client.post("/api/language-tools/entrance", json=_entrance(paths.project_key)).status_code == 400
    assert target.read_text(encoding="utf-8") == "旧钩子"
    monkeypatch.setattr(tools, "get_resource_path", tools_resource())

    def fail_write(*args, **kwargs):
        raise OSError("磁盘写入失败")

    monkeypatch.setattr("module.Tool.LanguageTools.atomic_write_text", fail_write)
    response = client.post("/api/language-tools/entrance", json=_entrance(paths.project_key))
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"
    assert job["result"]["written"] is False
    assert "撤回" not in (job["result"]["message"] or "")
    assert target.read_text(encoding="utf-8") == "旧钩子"
    assert engine.get_status() == Engine.Status.IDLE


@pytest.mark.parametrize("busy", ["single", "barrier", "translation"])
def test_busy_engine_rejects_before_creating_job(language_app, busy):
    client, _, engine, _, _, paths, manager = language_app
    if busy == "single":
        assert engine.try_begin_single_task()
    elif busy == "barrier":
        engine.set_stop_barrier(True)
    else:
        assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
    assert client.post("/api/language-tools/entrance", json=_entrance(paths.project_key)).status_code == 409
    assert not manager.list()


def test_cancel_waits_and_does_not_claim_rollback(language_app, monkeypatch):
    client, _, engine, _, game, paths, _ = language_app
    entered, release = threading.Event(), threading.Event()
    real = install_real()

    def slow(raw):
        entered.set()
        assert release.wait(5)
        return real(raw)

    monkeypatch.setattr("api.routes.language_tools.install_language_entrance", slow)
    try:
        response = client.post("/api/language-tools/entrance", json=_entrance(paths.project_key))
        assert response.status_code == 200, response.text
        job_id = response.json()["job"]["id"]
        assert entered.wait(2)
        assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
        running = client.get(f"/api/jobs/{job_id}").json()
        assert running["result"]["worker_active"] is True
        assert "撤回" not in running["result"]["message"]
        assert engine.get_status() == Engine.Status.TESTING
        assert client.get("/api/language-tools").json()["job"]["id"] == job_id
        assert client.post("/api/language-tools/default", json=_default(paths.project_key)).status_code == 409
    finally:
        release.set()
    job = _finish(client, job_id)
    assert job["status"] == "cancelled"
    assert job["result"]["worker_active"] is False
    assert job["result"]["written"] is True
    assert "撤回" not in job["result"]["message"]
    assert (game / HOOK_NAME).is_file()
    assert engine.get_status() == Engine.Status.IDLE


def test_project_switch_does_not_write_the_new_project(language_app, monkeypatch, tmp_path):
    client, config, _, project, game, paths, _ = language_app
    entered, release = threading.Event(), threading.Event()
    real = language_tools_current()
    calls = {"n": 0}

    def wrapped(config_obj, language=""):
        calls["n"] += 1
        if calls["n"] > 1:
            entered.set()
            assert release.wait(5)
        return real(config_obj)

    monkeypatch.setattr("api.routes.language_tools.current_paths", wrapped)
    other, other_game = _make_project(tmp_path / "other-root")
    try:
        response = client.post("/api/language-tools/entrance", json=_entrance(paths.project_key))
        assert response.status_code == 200, response.text
        job_id = response.json()["job"]["id"]
        assert entered.wait(2)
        _bind(config, other)
        release.set()
        job = _finish(client, job_id)
    finally:
        release.set()
    assert job["status"] == "failed"
    assert "项目已切换" in (job["error"] or "")
    assert job["result"]["written"] is False
    assert "撤回" not in (job["result"]["message"] or "")
    assert not (game / HOOK_NAME).exists()
    assert not (other_game / HOOK_NAME).exists()
    assert client.get("/api/language-tools").json()["project_key"] != paths.project_key
    assert project.exists()


def test_modules_do_not_import_qt_or_desktop():
    root = Path(__file__).resolve().parents[2]
    for relative in ("api/routes/language_tools.py", "module/Tool/LanguageTools.py", "api/app.py"):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            assert not any(name.startswith("PyQt") or name.startswith("desktop") for name in names)
    app_source = (root / "api" / "app.py").read_text(encoding="utf-8")
    assert "language_tools.router" in app_source


def install_real():
    from module.Tool.LanguageTools import install_language_entrance
    return install_language_entrance


def language_tools_current():
    from api.routes.language_tools import current_paths
    return current_paths


def tools_resource():
    from base.PathHelper import get_resource_path
    return get_resource_path


def test_cancel_during_project_check_does_not_begin_write(language_app, monkeypatch):
    """核对项目期间收到取消，写入尚未开始时不产生文件。"""
    client, _, engine, _, game, paths, _ = language_app
    entered, release = threading.Event(), threading.Event()
    real = language_tools_current()
    calls = {"n": 0}
    def wrapped(config_obj):
        calls["n"] += 1
        if calls["n"] > 1:
            entered.set()
            assert release.wait(5)
        return real(config_obj)
    monkeypatch.setattr("api.routes.language_tools.current_paths", wrapped)
    try:
        response = client.post("/api/language-tools/entrance", json=_entrance(paths.project_key))
        assert response.status_code == 200, response.text
        job_id = response.json()["job"]["id"]
        assert entered.wait(2)
        assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
        assert engine.get_status() == Engine.Status.TESTING
        release.set()
        job = _finish(client, job_id)
    finally:
        release.set()
    assert job["status"] == "cancelled"
    assert job["result"]["written"] is False
    assert not (game / HOOK_NAME).exists()
    assert engine.get_status() == Engine.Status.IDLE
