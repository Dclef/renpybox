"""文本提取 JSON API：tmp 最小游戏/tl 真文件往返（不跑真实官方抽取）。"""
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes.extract_json import router
from api.routes.jobs import router as jobs_router
from module.Config import Config
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import RenpyProjectPaths


@pytest.fixture
def unbound_json_app(tmp_path, monkeypatch):
    """未绑定项目：仅凭 game_file 操作。"""
    project, game = _make_project(tmp_path)
    config = Config()
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    monkeypatch.setattr(Config, "save", lambda self, *args, **kwargs: self)
    monkeypatch.setattr(
        "module.Extract.RenpyExtractor.RenpyExtractor.official_extract",
        lambda self, *args, **kwargs: project / "game" / "tl" / "chinese",
    )
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.include_router(router)
    app.include_router(jobs_router)
    with TestClient(app) as client:
        yield client, project, game, app.state.jobs
        app.state.jobs.shutdown()


@pytest.fixture
def json_app(tmp_path, monkeypatch):
    project, game = _make_project(tmp_path)
    config = Config()
    paths = _bind(config, project)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    monkeypatch.setattr(Config, "save", lambda self, *args, **kwargs: self)
    # 不跑真实官方抽取：collect_entries / export_to_json 只读已有 tl
    monkeypatch.setattr(
        "module.Extract.RenpyExtractor.RenpyExtractor.official_extract",
        lambda self, *args, **kwargs: True,
    )
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
    tl = game / "tl" / "chinese"
    tl.mkdir(parents=True)
    (game / "script.rpy").write_text('label start:\n    "Hello"\n', encoding="utf-8")
    # 假 EXE：RenpyExtractor 识别后缀即可；official_extract 已 mock
    (project / "Demo.exe").write_bytes(b"MZ" + b"\0" * 2048)
    (tl / "script_strings.rpy").write_text(
        'translate chinese strings:\n'
        '    old "Hello"\n'
        '    new "你好"\n'
        '    old "World"\n'
        '    new "世界"\n'
        '    old "say \\"hi\\""\n'
        '    new "说 \\"你好\\""\n',
        encoding="utf-8",
    )
    return project, game


def _bind(config: Config, project: Path) -> RenpyProjectPaths:
    game = project / "game"
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(game / "tl" / "chinese")
    config.input_folder = str(game / "tl" / "chinese")
    config.output_folder = ""
    config.renpy_duplicate_string_action = "comment"
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


def test_status_unbound_defaults(unbound_json_app):
    client, _, _, _ = unbound_json_app
    response = client.get("/api/extract-json")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project_key"] == ""
    assert body["project_root"] == ""
    assert body["job"] is None


def test_preview_unbound_game_file_only(unbound_json_app):
    client, project, _, _ = unbound_json_app
    response = client.post(
        "/api/extract-json/preview",
        json={
            "game_file": str(project / "Demo.exe"),
            "language": "chinese",
            "ensure_official": False,
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["entry_count"] >= 3


def test_status_bound_project(json_app):
    client, _, _, project, game, paths, _ = json_app
    response = client.get("/api/extract-json")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project_key"] == paths.project_key
    assert Path(body["project_root"]) == project.resolve()
    assert Path(body["game_dir"]) == game.resolve()
    assert body["language"] == "chinese"
    assert body["job"] is None


def test_preview_counts_entries(json_app):
    client, _, engine, project, _, paths, _ = json_app
    response = client.post(
        "/api/extract-json/preview",
        json={
            "project_key": paths.project_key,
            "game_file": str(project / "Demo.exe"),
            "language": "chinese",
            "ensure_official": False,
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["entry_count"] >= 2
    assert job["result"]["file_count"] >= 1
    assert engine.get_status() == Engine.Status.IDLE


def test_export_import_cleanup_roundtrip(json_app, tmp_path):
    client, _, engine, project, game, paths, _ = json_app
    export_path = tmp_path / "out.json"
    exe = str(project / "Demo.exe")

    export = client.post(
        "/api/extract-json/export-json",
        json={
            "project_key": paths.project_key,
            "game_file": exe,
            "language": "chinese",
            "output_path": str(export_path),
            "force_extract": False,
            "include_metadata": True,
        },
    )
    assert export.status_code == 200, export.text
    export_job = _finish(client, export.json()["job"]["id"])
    assert export_job["status"] == "done", export_job
    assert export_path.is_file()
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert "translations" in payload
    assert sum(len(v) for v in payload["translations"].values()) >= 1

    tl_json = tmp_path / "tl_export.json"
    export_tl_early = client.post(
        "/api/extract-json/export-tl-json",
        json={
            "project_key": paths.project_key,
            "game_file": str(project),
            "language": "chinese",
            "output_path": str(tl_json),
            "include_metadata": True,
        },
    )
    assert export_tl_early.status_code == 200, export_tl_early.text
    tl_job_early = _finish(client, export_tl_early.json()["job"]["id"])
    assert tl_job_early["status"] == "done"
    tl_payload_early = json.loads(tl_json.read_text(encoding="utf-8"))
    entries_early = tl_payload_early["translations"]["script_strings.rpy"]
    escaped = next(e for e in entries_early if "hi" in e["original"])
    assert escaped["original"] == 'say "hi"'
    assert escaped["translation"] == '说 "你好"'

    # 清空译文再导入
    tl_file = game / "tl" / "chinese" / "script_strings.rpy"
    tl_file.write_text(
        'translate chinese strings:\n'
        '    old "Hello"\n'
        '    new ""\n'
        '    old "World"\n'
        '    new ""\n',
        encoding="utf-8",
    )
    # 构造带译文的导入 JSON
    import_path = tmp_path / "import.json"
    import_path.write_text(
        json.dumps({
            "translations": {
                "script_strings.rpy": [
                    {"original": "Hello", "translation": "哈喽", "type": "strings", "line": 1},
                    {"original": "World", "translation": "世界", "type": "strings", "line": 3},
                ]
            }
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    applied = client.post(
        "/api/extract-json/import-apply",
        json={
            "project_key": paths.project_key,
            "game_file": exe,
            "language": "chinese",
            "json_path": str(import_path),
            "backup": True,
        },
    )
    assert applied.status_code == 200, applied.text
    apply_job = _finish(client, applied.json()["job"]["id"])
    assert apply_job["status"] == "done", apply_job
    assert apply_job["result"]["written"] is True
    assert apply_job["result"]["entry_count"] >= 1

    # 写入重复条目后清理
    tl_file.write_text(
        tl_file.read_text(encoding="utf-8")
        + '\n    old "Hello"\n    new "重复"\n',
        encoding="utf-8",
    )
    cleanup = client.post(
        "/api/extract-json/cleanup",
        json={
            "project_key": paths.project_key,
            "game_file": exe,
            "language": "chinese",
        },
    )
    assert cleanup.status_code == 200, cleanup.text
    cleanup_job = _finish(client, cleanup.json()["job"]["id"])
    assert cleanup_job["status"] == "done"

    tl_json = tmp_path / "tl_export.json"
    export_tl = client.post(
        "/api/extract-json/export-tl-json",
        json={
            "project_key": paths.project_key,
            "game_file": str(project),
            "language": "chinese",
            "output_path": str(tl_json),
            "include_metadata": True,
        },
    )
    assert export_tl.status_code == 200, export_tl.text
    tl_job = _finish(client, export_tl.json()["job"]["id"])
    assert tl_job["status"] == "done"
    assert tl_json.is_file()
    assert tl_job["result"]["entry_count"] >= 1
    assert engine.get_status() == Engine.Status.IDLE


def test_import_rejects_path_traversal(json_app, tmp_path):
    client, _, _, project, game, paths, _ = json_app
    import_path = tmp_path / "evil.json"
    import_path.write_text(
        json.dumps({
            "translations": {
                "../outside.rpy": [
                    {"original": "x", "translation": "y", "type": "strings", "line": 1},
                ]
            }
        }),
        encoding="utf-8",
    )
    response = client.post(
        "/api/extract-json/import-apply",
        json={
            "project_key": paths.project_key,
            "game_file": str(project / "Demo.exe"),
            "language": "chinese",
            "json_path": str(import_path),
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"
    assert not (game / "tl" / "chinese" / "outside.rpy").exists()


def test_reject_stale_key_and_busy(json_app):
    client, _, engine, project, _, paths, manager = json_app
    assert client.post(
        "/api/extract-json/preview",
        json={"project_key": paths.project_key + "-x", "language": "chinese"},
    ).status_code == 409
    assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
    assert client.post(
        "/api/extract-json/preview",
        json={
            "project_key": paths.project_key,
            "game_file": str(project),
            "language": "chinese",
        },
    ).status_code == 409
    assert not manager.list()
    engine.set_status(Engine.Status.IDLE)


def test_import_rejects_normcase_duplicate_targets(json_app, tmp_path):
    client, _, _, project, game, paths, _ = json_app
    import_path = tmp_path / "dup.json"
    import_path.write_text(
        json.dumps({
            "translations": {
                "a.rpy": [{"original": "A", "translation": "甲", "type": "strings", "line": 1}],
                "./a.rpy": [{"original": "B", "translation": "乙", "type": "strings", "line": 1}],
            }
        }),
        encoding="utf-8",
    )
    response = client.post(
        "/api/extract-json/import-apply",
        json={
            "project_key": paths.project_key,
            "game_file": str(project / "Demo.exe"),
            "language": "chinese",
            "json_path": str(import_path),
            "backup": True,
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"
    assert "重复" in (job["result"].get("message") or job.get("error") or "")
    assert not (game / "tl" / "chinese" / "a.rpy").exists()


def test_import_cancel_keeps_written_files_and_backups(json_app, tmp_path, monkeypatch):
    """取消发生在已写首个文件之后：job 必须保留 written_files/backup/partial。"""
    import threading
    from module.Renpy import json_handler as jh

    client, _, engine, project, game, paths, _ = json_app
    tl = game / "tl" / "chinese"
    first = tl / "one.rpy"
    second = tl / "two.rpy"
    first.write_text('translate chinese strings:\n    old "A"\n    new ""\n', encoding="utf-8")
    second.write_text('translate chinese strings:\n    old "B"\n    new ""\n', encoding="utf-8")

    import_path = tmp_path / "partial.json"
    import_path.write_text(
        json.dumps({
            "translations": {
                "one.rpy": [{"original": "A", "translation": "一", "type": "strings", "line": 1}],
                "two.rpy": [{"original": "B", "translation": "二", "type": "strings", "line": 1}],
            }
        }),
        encoding="utf-8",
    )

    real_atomic = jh.atomic_write_text
    wrote_first = threading.Event()
    release = threading.Event()
    calls = {"n": 0}

    def gated_atomic(path, text, **kwargs):
        calls["n"] += 1
        result = real_atomic(path, text, **kwargs)
        if calls["n"] == 1:
            wrote_first.set()
            assert release.wait(5)
        return result

    monkeypatch.setattr(jh, "atomic_write_text", gated_atomic)

    response = client.post(
        "/api/extract-json/import-apply",
        json={
            "project_key": paths.project_key,
            "game_file": str(project / "Demo.exe"),
            "language": "chinese",
            "json_path": str(import_path),
            "backup": True,
        },
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["job"]["id"]
    assert wrote_first.wait(3)
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
    release.set()
    job = _finish(client, job_id, timeout=8.0)
    assert job["status"] == "cancelled"
    assert job.get("cancel_requested") is True
    result = job["result"] or {}
    assert result.get("written") is True
    assert result.get("partial") is True
    assert result.get("success") is False
    written = result.get("written_files") or []
    assert any(Path(p).name == "one.rpy" for p in written)
    assert (tl / "one.rpy.bak").is_file() or any(
        Path(p).name == "one.rpy.bak" for p in (result.get("backup_paths") or [])
    )
    assert "一" in first.read_text(encoding="utf-8")
    assert "二" not in second.read_text(encoding="utf-8")
    assert engine.get_status() == Engine.Status.IDLE


def test_cleanup_cancel_keeps_written_files(json_app, monkeypatch):
    """真实清理已改首文件后取消：终态 cancelled，保留 written_files。"""
    import threading

    from module.Renpy import renpy_extract as rx

    client, _, engine, project, game, paths, _ = json_app
    tl = game / "tl" / "chinese"
    a = tl / "a.rpy"
    b = tl / "b.rpy"
    a.write_text(
        'translate chinese strings:\n'
        '    old "Dup"\n'
        '    new "一"\n'
        '    old "Dup"\n'
        '    new "二"\n',
        encoding="utf-8",
    )
    b.write_text(
        'translate chinese strings:\n'
        '    old "Keep"\n'
        '    new "留"\n'
        '    old "Keep"\n'
        '    new "丢"\n',
        encoding="utf-8",
    )
    real_remove = rx.remove_repeat_for_file
    wrote_a = threading.Event()
    release = threading.Event()
    calls = {"n": 0}

    def gated(path, duplicate_action="comment"):
        result = real_remove(path, duplicate_action=duplicate_action)
        calls["n"] += 1
        if Path(path).name == "a.rpy" and result:
            wrote_a.set()
            assert release.wait(5)
        return result

    monkeypatch.setattr(rx, "remove_repeat_for_file", gated)

    response = client.post(
        "/api/extract-json/cleanup",
        json={
            "project_key": paths.project_key,
            "game_file": str(project),
            "language": "chinese",
        },
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["job"]["id"]
    assert wrote_a.wait(3)
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
    release.set()
    job = _finish(client, job_id, timeout=8.0)
    assert job["status"] == "cancelled"
    result = job["result"] or {}
    assert result.get("written") is True
    assert result.get("partial") is True
    assert result.get("success") is False
    written = result.get("written_files") or []
    assert any(Path(p).name == "a.rpy" for p in written)
    assert "# old \"Dup\"" in a.read_text(encoding="utf-8") or 'old "Dup"' in a.read_text(encoding="utf-8")
    assert engine.get_status() == Engine.Status.IDLE


def test_cleanup_empty_tl_reports_no_write(json_app):
    """空 TL 目录清理成功但 written=False。"""
    client, _, engine, project, game, paths, _ = json_app
    tl = game / "tl" / "chinese"
    for child in tl.iterdir():
        if child.is_file():
            child.unlink()
    response = client.post(
        "/api/extract-json/cleanup",
        json={
            "project_key": paths.project_key,
            "game_file": str(project),
            "language": "chinese",
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["success"] is True
    assert job["result"]["written"] is False
    assert job["result"].get("written_files") == []
    assert engine.get_status() == Engine.Status.IDLE


def test_unbound_status_with_game_file_tracks_running_job(unbound_json_app, monkeypatch):
    """未绑定：GET 带 game_file/language 能持续读到运行中与终态 job。"""
    import threading

    client, project, _, jobs = unbound_json_app
    paths = RenpyProjectPaths.from_path(project, "chinese")
    assert paths is not None
    target_key = paths.project_key
    gate = threading.Event()
    started = threading.Event()

    def slow_collect(self, *args, **kwargs):
        started.set()
        assert gate.wait(5)
        return [{"file": "a.rpy", "original": "Hi", "translation": "", "type": "strings", "line": 1}]

    monkeypatch.setattr(
        "module.Extract.RenpyExtractor.RenpyExtractor.collect_entries",
        slow_collect,
    )
    response = client.post(
        "/api/extract-json/preview",
        json={
            "game_file": str(project / "Demo.exe"),
            "language": "chinese",
            "ensure_official": False,
        },
    )
    assert response.status_code == 200, response.text
    assert started.wait(3)
    bare = client.get("/api/extract-json")
    assert bare.status_code == 200
    assert bare.json()["project_key"] == ""
    assert bare.json()["job"] is None
    qs = urlencode({"game_file": str(project / "Demo.exe"), "language": "chinese"})
    tracked = client.get(f"/api/extract-json?{qs}")
    assert tracked.status_code == 200, tracked.text
    body = tracked.json()
    assert body["project_key"] == target_key
    assert body["job"] is not None
    assert body["job"]["status"] in {"pending", "running"}
    gate.set()
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    final = client.get(f"/api/extract-json?{qs}")
    assert final.json()["job"]["id"] == job["id"]
    assert final.json()["job"]["status"] == "done"


def test_bound_owner_other_target_uses_target_key(json_app, monkeypatch, tmp_path):
    """绑定 owner A + 合法目标 B：任务键是 B，执行目录是 B。"""
    client, _, engine, project, _, paths, _ = json_app
    other, _ = _make_project(tmp_path / "Other")
    other_key = RenpyProjectPaths.from_path(other, "chinese").project_key
    seen = {}

    def fake_collect(self, game_file, language, **kwargs):
        seen["game_file"] = game_file
        return [{"file": "a.rpy", "original": "X", "translation": "", "type": "strings", "line": 1}]

    monkeypatch.setattr(
        "module.Extract.RenpyExtractor.RenpyExtractor.collect_entries",
        fake_collect,
    )
    response = client.post(
        "/api/extract-json/preview",
        json={
            "project_key": paths.project_key,
            "game_file": str(other / "Demo.exe"),
            "language": "chinese",
            "ensure_official": False,
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["project_key"] == other_key
    assert other_key != paths.project_key
    assert Path(seen["game_file"]).resolve() == (other / "Demo.exe").resolve()
    status = client.get(
        "/api/extract-json?"
        + urlencode({"game_file": str(other / "Demo.exe"), "language": "chinese"})
    )
    assert status.json()["project_key"] == other_key
    assert status.json()["owner_project_key"] == paths.project_key
    assert engine.get_status() == Engine.Status.IDLE


def test_preview_default_ensure_official_and_force_false(json_app, monkeypatch):
    client, _, _, project, _, paths, _ = json_app
    seen = {}

    def fake_collect(self, game_file, language, *, ensure_official=False, force=False, should_stop=None, progress_callback=None):
        seen["ensure_official"] = ensure_official
        seen["force"] = force
        seen["should_stop"] = should_stop
        return [{"file": "a.rpy", "original": "Hi", "translation": "", "type": "strings", "line": 1}]

    monkeypatch.setattr(
        "module.Extract.RenpyExtractor.RenpyExtractor.collect_entries",
        fake_collect,
    )
    response = client.post(
        "/api/extract-json/preview",
        json={
            "project_key": paths.project_key,
            "game_file": str(project / "Demo.exe"),
            "language": "chinese",
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert seen["ensure_official"] is True
    assert seen["force"] is False
    assert callable(seen["should_stop"])
