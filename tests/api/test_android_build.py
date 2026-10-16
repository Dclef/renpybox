"""安卓打包 API：配置默认、构建顺序、忙碌拒绝、检测替换；不跑真实 SDK。"""
from __future__ import annotations

import sys
import time
import types
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# 轻量挂载 api 包，避免 api/__init__ 拉 create_app 时被无关路由语法错误阻断 B 收集
if "api" not in sys.modules:
    _api = types.ModuleType("api")
    _api.__path__ = [str(Path(__file__).resolve().parents[2] / "api")]
    _api.__file__ = str(Path(__file__).resolve().parents[2] / "api" / "__init__.py")
    sys.modules["api"] = _api

from api.jobs import JobManager
from api.routes.android_build import router
from api.routes.jobs import router as jobs_router
from module.Config import Config
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Tool.AndroidBuilder import AndroidBuilder


@pytest.fixture
def android_app(tmp_path, monkeypatch):
    project, game = _make_project(tmp_path)
    sdk = _make_sdk(tmp_path)
    config = Config()
    paths = _bind(config, project)
    config.renpy_sdk_path = str(sdk)
    config.android_app_name = "Demo"
    config.android_package_name = "com.example.demo"
    config.android_version = "1.0.0"
    config.android_shell_backup_enable = True
    config.android_shell_remove_dirs = "images,audio"
    config.android_dname = "CN=Test"
    config.android_update_always = True
    config.android_update_icons = True
    monkeypatch.setattr(Config, "save", lambda self, *a, **k: self)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.include_router(router)
    app.include_router(jobs_router)
    with TestClient(app) as client:
        yield client, config, engine, project, game, paths, sdk, app.state.jobs
        app.state.jobs.shutdown()


def _make_project(root: Path) -> tuple[Path, Path]:
    project = root / "Demo"
    game = project / "game"
    (game / "images").mkdir(parents=True)
    (game / "audio").mkdir(parents=True)
    (game / "gui").mkdir(parents=True)
    (game / "images" / "a.png").write_bytes(b"png")
    (game / "audio" / "b.ogg").write_bytes(b"ogg")
    (game / "gui" / "c.png").write_bytes(b"png")
    return project, game


def _make_sdk(root: Path) -> Path:
    sdk = root / "sdk"
    (sdk / "lib" / "py3-windows-x86_64").mkdir(parents=True)
    (sdk / "renpy.exe").write_bytes(b"MZ")
    (sdk / "lib" / "py3-windows-x86_64" / "python.exe").write_bytes(b"MZ")
    (sdk / "rapt" / "bin").mkdir(parents=True)
    return sdk


def _bind(config: Config, project: Path) -> RenpyProjectPaths:
    game = project / "game"
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(game / "tl" / "chinese")
    (game / "tl" / "chinese").mkdir(parents=True, exist_ok=True)
    config.input_folder = str(game / "tl" / "chinese")
    config.output_folder = ""
    paths = RenpyProjectPaths.from_config(config)
    assert paths is not None
    return paths


def _finish(client, job_id, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        result = job.get("result") or {}
        if job["status"] in {"done", "failed", "cancelled"} and not result.get("worker_active"):
            return job
        time.sleep(0.01)
    pytest.fail(f"任务未结束：{job}")


def test_status_defaults_and_hidden_fields(android_app):
    client, _, _, _, _, paths, _, _ = android_app
    payload = client.get("/api/android-build").json()
    assert payload["project_key"] == paths.project_key
    cfg = payload["config"]
    assert cfg["app_name"] == "Demo"
    assert cfg["package_name"] == "com.example.demo"
    assert cfg["version"] == "1.0.0"
    assert cfg["shell_backup_enable"] is True
    assert cfg["dname"] == "CN=Test"
    assert cfg["update_always"] is True
    assert cfg["update_icons"] is True
    assert payload["cancellable"] is False


def test_busy_rejects_without_side_effects(android_app):
    client, config, engine, project, _, paths, _, manager = android_app
    assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
    refused = client.post(
        "/api/android-build/write-json",
        json={
            "project_key": paths.project_key,
            "sdk_path": config.renpy_sdk_path,
            "app_name": "X",
            "package_name": "com.x",
            "version": "2",
        },
    )
    assert refused.status_code == 409
    assert not manager.list()
    assert not (project / "android.json").exists()
    engine.set_status(Engine.Status.IDLE)


def test_write_json_preserves_extra_keys(android_app):
    client, config, _, project, _, paths, _, _ = android_app
    existing = project / "android.json"
    existing.write_text('{"custom": 1, "permissions": ["INTERNET"]}', encoding="utf-8")
    response = client.post(
        "/api/android-build/write-json",
        json={
            "project_key": paths.project_key,
            "sdk_path": config.renpy_sdk_path,
            "app_name": "Demo",
            "package_name": "com.example.demo",
            "version": "1.0.1",
            "update_always": False,
            "update_icons": True,
        },
    )
    assert response.status_code == 200, response.text
    data = __import__("json").loads(existing.read_text(encoding="utf-8"))
    assert data["custom"] == 1
    assert data["permissions"] == ["INTERNET"]
    assert data["name"] == "Demo"
    assert data["update_always"] is False
    assert data["update_icons"] is True


def test_detect_replace_and_clear(android_app):
    client, _, _, _, _, paths, _, _ = android_app
    response = client.post(
        "/api/android-build/detect",
        json={
            "project_key": paths.project_key,
            "target": "archive",
            "hints": "images",
            "replace": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    assert "images" in body["detected"]
    assert "gui" not in body["detected"]
    assert body["value"].count("images") == 1


def test_build_order_distribute_fail_stops(android_app, monkeypatch):
    client, config, engine, project, _, paths, _, _ = android_app
    (project / "android.keystore").write_bytes(b"key")
    calls: list[str] = []

    def write_json(self, **kwargs):
        calls.append("write")
        return project / "android.json"

    def run_distribute(self, **kwargs):
        calls.append("distribute")
        return False

    def sanitize(*args, **kwargs):
        calls.append("sanitize")
        return {}

    def build_android(self, **kwargs):
        calls.append("build")
        return True

    monkeypatch.setattr(AndroidBuilder, "write_android_json", write_json)
    monkeypatch.setattr(AndroidBuilder, "run_distribute", run_distribute)
    monkeypatch.setattr(
        "api.routes.android_build.sanitize_android_dist_assets",
        sanitize,
    )
    monkeypatch.setattr(AndroidBuilder, "build_android", build_android)

    response = client.post(
        "/api/android-build/build",
        json={
            "project_key": paths.project_key,
            "sdk_path": config.renpy_sdk_path,
            "app_name": "Demo",
            "package_name": "com.example.demo",
            "version": "1.0.0",
            "confirm": True,
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"
    assert calls == ["write", "distribute"]
    assert job["result"].get("open_bin") is False
    assert engine.get_status() == Engine.Status.IDLE


def test_build_success_lists_history_and_new(android_app, monkeypatch):
    client, config, engine, project, _, paths, sdk, _ = android_app
    (project / "android.keystore").write_bytes(b"key")
    old_apk = sdk / "rapt" / "bin" / "old.apk"
    old_apk.write_bytes(b"old")
    new_apk = sdk / "rapt" / "bin" / "new.apk"

    monkeypatch.setattr(
        AndroidBuilder,
        "write_android_json",
        lambda self, **kwargs: project / "android.json",
    )
    monkeypatch.setattr(AndroidBuilder, "run_distribute", lambda self, **kwargs: True)
    monkeypatch.setattr(
        "api.routes.android_build.sanitize_android_dist_assets",
        lambda *a, **k: {"success": True, "removed": [], "failed": []},
    )

    def build_android(self, **kwargs):
        assert kwargs.get("install") is False
        assert kwargs.get("launch") is False
        new_apk.write_bytes(b"new")
        return True

    monkeypatch.setattr(AndroidBuilder, "build_android", build_android)

    response = client.post(
        "/api/android-build/build",
        json={
            "project_key": paths.project_key,
            "sdk_path": config.renpy_sdk_path,
            "app_name": "Demo",
            "package_name": "com.example.demo",
            "version": "1.0.0",
            "confirm": True,
        },
    )
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["open_bin"] is True
    assert job["result"]["outputs_include_history"] is True
    assert "old.apk" in job["result"]["output_names"]
    assert "new.apk" in job["result"]["new_output_names"]
    assert "old.apk" not in job["result"]["new_output_names"]
    assert engine.get_status() == Engine.Status.IDLE


def test_build_missing_keystore_and_confirm(android_app):
    client, config, _, _, _, paths, _, manager = android_app
    assert client.post(
        "/api/android-build/build",
        json={
            "project_key": paths.project_key,
            "sdk_path": config.renpy_sdk_path,
            "app_name": "Demo",
            "package_name": "com.example.demo",
            "version": "1.0.0",
            "confirm": False,
        },
    ).status_code == 400
    assert client.post(
        "/api/android-build/build",
        json={
            "project_key": paths.project_key,
            "sdk_path": config.renpy_sdk_path,
            "app_name": "Demo",
            "package_name": "com.example.demo",
            "version": "1.0.0",
            "confirm": True,
        },
    ).status_code == 400
    assert not manager.list()


def test_make_shell_job(android_app):
    client, _, engine, project, game, paths, _, _ = android_app
    response = client.post(
        "/api/android-build/make-shell",
        json={
            "project_key": paths.project_key,
            "archive_source_dir": "",
            "shell_remove_dirs": "images",
            "shell_backup_enable": True,
            "confirm": True,
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["success"] is True
    assert Path(job["result"]["archive_path"]).is_file()
    assert Path(job["result"]["backup_path"]).is_file()
    assert not (game / "images").exists()
    assert (project / "archive.rpa").is_file()
    assert job["result"]["cancellable"] is False
    assert engine.get_status() == Engine.Status.IDLE


def test_open_bin_rejects_missing(android_app, monkeypatch):
    client, config, _, _, _, paths, sdk, _ = android_app
    bin_dir = sdk / "rapt" / "bin"
    # 删掉 bin 模拟未构建
    for child in bin_dir.iterdir():
        child.unlink()
    bin_dir.rmdir()
    response = client.post(
        "/api/android-build/open-bin",
        json={"project_key": paths.project_key, "sdk_path": config.renpy_sdk_path},
    )
    assert response.status_code == 400


def test_stale_project_key(android_app):
    client, config, _, _, _, _, _, _ = android_app
    assert client.post(
        "/api/android-build/detect",
        json={"project_key": "stale-key", "target": "archive"},
    ).status_code == 409


def test_manual_target_owner_key_detect_ok(android_app, tmp_path):
    """绑定 owner A + 手动 project_path B：owner 键合法，不 409。"""
    client, _, _, _, _, paths, _, _ = android_app
    other = tmp_path / "ManualB"
    (other / "game" / "images").mkdir(parents=True)
    (other / "game" / "images" / "x.png").write_bytes(b"x")
    response = client.post(
        "/api/android-build/detect",
        json={
            "project_key": paths.project_key,
            "project_path": str(other),
            "target": "archive",
            "replace": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["owner_project_key"] == paths.project_key
    assert body["project_key"] != paths.project_key
    assert "images" in body["detected"]


def test_status_project_path_keeps_owner(android_app, tmp_path):
    client, _, _, _, _, paths, _, _ = android_app
    other = tmp_path / "StatusB"
    (other / "game").mkdir(parents=True)
    payload = client.get(
        "/api/android-build",
        params={"project_path": str(other)},
    ).json()
    assert payload["owner_project_key"] == paths.project_key
    assert Path(payload["project_root"]) == other


def test_invalid_cleanup_must_not_save(android_app, monkeypatch):
    """非法清理路径：预检失败，Config.save 不得先落盘。"""
    client, _, _, project, _, paths, _, _ = android_app
    saves: list[str] = []
    monkeypatch.setattr(
        Config,
        "save",
        lambda self, *a, **k: saves.append(self.android_shell_remove_dirs),
    )
    response = client.post(
        "/api/android-build/make-shell",
        json={
            "project_key": paths.project_key,
            "project_path": str(project),
            "shell_remove_dirs": "../outside",
            "confirm": True,
        },
    )
    assert response.status_code == 400
    assert saves == []


def test_build_exception_preserves_written(android_app, monkeypatch):
    """distribute 抛异常时保留 android.json 写入记录。"""
    client, config, _, project, _, paths, _, _ = android_app
    (project / "android.keystore").write_bytes(b"fixture")

    def explode(self, **kwargs):
        raise OSError("SDK fixture failed after JSON")

    monkeypatch.setattr(AndroidBuilder, "run_distribute", explode)
    response = client.post(
        "/api/android-build/build",
        json={
            "project_key": paths.project_key,
            "project_path": str(project),
            "sdk_path": config.renpy_sdk_path,
            "app_name": "Demo",
            "package_name": "com.demo",
            "version": "1",
            "confirm": True,
        },
    )
    job = _finish(client, response.json()["job"]["id"])
    assert (project / "android.json").exists()
    assert job["status"] == "failed"
    assert job["result"]["written"] is True
    assert job["result"].get("open_bin") is False
    assert any(
        Path(p).name == "android.json" for p in (job["result"].get("written_files") or [])
    )


def test_self_persist_target_does_not_invalidate_owner(android_app, monkeypatch):
    """任务自身把配置切到目标 B 后，worker 不得因新身份自我失效。"""
    client, config, _, project, _, paths, _, _ = android_app
    other = project.parent / "SelfPersistB"
    (other / "game" / "images").mkdir(parents=True)
    (other / "game" / "images" / "a.png").write_bytes(b"a")
    (other / "game" / "tl" / "chinese").mkdir(parents=True)

    response = client.post(
        "/api/android-build/make-shell",
        json={
            "project_key": paths.project_key,
            "project_path": str(other),
            "archive_source_dir": "images",
            "shell_remove_dirs": "images",
            "shell_backup_enable": True,
            "confirm": True,
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done", job
    assert Path(job["result"]["archive_path"]).is_file()
    # 全局已切到 B，但本任务仍完成
    assert Path(config.renpy_project_path) == other


def test_prefix_works_without_project_binding(android_app, tmp_path):
    """未绑定项目时 /prefix 仍可改名（不依赖项目、不取锁）。"""
    client, config, engine, _, _, _, _, _ = android_app
    config.renpy_project_path = ""
    config.renpy_game_folder = ""
    folder = tmp_path / "x-game"
    folder.mkdir()
    (folder / "x-a.txt").write_text("a", encoding="utf-8")
    response = client.post(
        "/api/android-build/prefix",
        json={
            "directory": str(folder),
            "prefix": "x-",
            "action": "strip",
            "apply": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["applied"] is True
    assert body["message"]
    assert Path(body["new_root"]).name == "game"
    assert (Path(body["new_root"]) / "a.txt").is_file()
    assert engine.get_status() == Engine.Status.IDLE


def test_prefix_validation_errors(android_app, tmp_path):
    client, _, _, _, _, _, _, _ = android_app
    assert client.post(
        "/api/android-build/prefix",
        json={"directory": "", "action": "strip"},
    ).status_code == 400
    assert client.post(
        "/api/android-build/prefix",
        json={"directory": str(tmp_path / "missing"), "action": "strip"},
    ).status_code == 400
    assert client.post(
        "/api/android-build/prefix",
        json={"directory": str(tmp_path), "action": "move"},
    ).status_code == 400


def test_prefix_dry_run_and_apply(android_app, tmp_path):
    client, _, _, _, _, _, _, _ = android_app
    folder = tmp_path / "x-game"
    folder.mkdir()
    (folder / "x-script.rpyc").write_bytes(b"s")
    dry = client.post(
        "/api/android-build/prefix",
        json={
            "directory": str(folder),
            "prefix": "x-",
            "action": "strip",
            "apply": False,
        },
    )
    assert dry.status_code == 200
    dry_body = dry.json()
    assert dry_body["total"] > 0
    assert dry_body["applied"] is False
    assert (folder / "x-script.rpyc").is_file()

    applied = client.post(
        "/api/android-build/prefix",
        json={
            "directory": str(folder),
            "prefix": "x-",
            "action": "strip",
            "apply": True,
        },
    )
    assert applied.status_code == 200
    body = applied.json()
    assert body["applied"] is True
    assert body["message"]
    assert (Path(body["new_root"]) / "script.rpyc").is_file()
