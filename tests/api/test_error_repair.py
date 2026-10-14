"""错误修复 API：真实临时目录扫描/修复/导出/lint 边界。"""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes.error_repair import router
from api.routes.jobs import router as jobs_router
from module.Config import Config
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Tool.ErrorRepairer import ErrorRepairer


@pytest.fixture
def repair_client(tmp_path, monkeypatch):
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
        yield client, engine, tmp_path, app.state.jobs, config
        app.state.jobs.shutdown()


def _finish(client, job_id, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish")


def _tl(tmp_path: Path) -> Path:
    tl = tmp_path / "game" / "tl" / "chinese"
    tl.mkdir(parents=True)
    (tl / "script.rpy").write_text(
        'translate chinese strings:\n'
        '    old "Hello"\n'
        '    new "你好"\n'
        '\n'
        'translate chinese empty_block:\n'
        '    old "x"\n'
        '    new ""\n',
        encoding="utf-8",
    )
    # 含行首 Tab，供修复
    (tl / "tabs.rpy").write_text('\told "A"\n\tnew "A"\n', encoding="utf-8")
    return tl


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


def test_scan_quotes_always_on_and_empty_report_exportable(repair_client):
    client, engine, tmp_path, _, _ = repair_client
    tl = _tl(tmp_path)
    response = client.post("/api/error-repair/scan", json={
        "folder": str(tl),
        "check_indent": True,
        "check_indent_level": False,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done", job
    assert job["result"]["action"] == "scan"
    assert "report" not in job["result"]
    assert job["result"]["has_scan_report"] is True
    assert job["result"]["affected_files"] == 1
    # 空报告也应可导出
    out = tmp_path / "report.xlsx"
    exported = client.post("/api/error-repair/export", json={
        "folder": str(tl),
        "output_path": str(out),
        "report": {},
    })
    assert exported.status_code == 200, exported.text
    assert out.is_file()
    assert engine.get_status() == Engine.Status.IDLE


def test_fix_partial_counts_and_confirm_required(repair_client):
    client, engine, tmp_path, _, _ = repair_client
    tl = _tl(tmp_path)
    assert client.post("/api/error-repair/fix", json={
        "folder": str(tl),
        "confirm": False,
    }).status_code == 400
    response = client.post("/api/error-repair/fix", json={
        "folder": str(tl),
        "fix_indent": True,
        "fix_indent_level": False,
        "fix_quotes": False,
        "fix_dialogue_quotes": False,
        "confirm": True,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done", job
    result = job["result"]
    assert "fixed_files" in result and "fixed_items" in result and "failed_files" in result
    # Only explicitly selected operations are applied by the desktop API.
    assert result["action"] == "fix"
    assert engine.get_status() == Engine.Status.IDLE


def test_export_failure_not_fake_success(repair_client, monkeypatch):
    client, _, tmp_path, _, _ = repair_client
    tl = _tl(tmp_path)
    monkeypatch.setattr(
        "api.routes.error_repair.ErrorRepairer.export_error_report",
        lambda self, errors, output_path: False,
    )
    response = client.post("/api/error-repair/export", json={
        "folder": str(tl),
        "output_path": str(tmp_path / "nope.xlsx"),
        "report": {},
    })
    assert response.status_code == 500


def test_lint_none_fails_empty_succeeds(repair_client, monkeypatch):
    client, engine, tmp_path, _, _ = repair_client
    tl = _tl(tmp_path)
    exe = tmp_path / "game.exe"
    exe.write_bytes(b"MZ\0\0")

    monkeypatch.setattr(
        "api.routes.error_repair.ErrorRepairer.exec_renpy_lint",
        lambda self, path, **kwargs: None,
    )
    response = client.post("/api/error-repair/lint", json={
        "folder": str(tl),
        "game_exe": str(exe),
    })
    assert response.status_code == 200
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"

    monkeypatch.setattr(
        "api.routes.error_repair.ErrorRepairer.exec_renpy_lint",
        lambda self, path, **kwargs: "",
    )
    monkeypatch.setattr(
        "api.routes.error_repair.ErrorRepairer.parse_lint_errors",
        lambda self, output: [{"file": "game/script.rpy", "line": 1, "message": "x"}],
    )
    monkeypatch.setattr(
        "api.routes.error_repair.ErrorRepairer.filter_lint_errors",
        staticmethod(lambda errors, folder: []),
    )
    response = client.post("/api/error-repair/lint", json={
        "folder": str(tl),
        "game_exe": str(exe),
    })
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["error_count"] == 0
    assert engine.get_status() == Engine.Status.IDLE


def test_busy_engine_blocks_export_without_side_effects(repair_client):
    """探针 1：busy 下 export 必须 409 且不写盘；IDLE 可导出。"""
    client, engine, tmp_path, manager, _ = repair_client
    tl = _tl(tmp_path)
    out_busy = tmp_path / "busy.xlsx"
    out_idle = tmp_path / "idle.xlsx"
    assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
    busy = client.post("/api/error-repair/export", json={
        "folder": str(tl),
        "output_path": str(out_busy),
        "report": {},
    })
    assert busy.status_code == 409
    assert not out_busy.exists()
    assert not manager.list()
    assert engine.try_set_status(Engine.Status.TRANSLATING, Engine.Status.IDLE)
    idle = client.post("/api/error-repair/export", json={
        "folder": str(tl),
        "output_path": str(out_idle),
        "report": {},
    })
    assert idle.status_code == 200, idle.text
    assert out_idle.is_file()
    assert engine.get_status() == Engine.Status.IDLE


def test_busy_engine_no_side_effects(repair_client):
    client, engine, tmp_path, manager, _ = repair_client
    tl = _tl(tmp_path)
    assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
    assert client.post("/api/error-repair/scan", json={"folder": str(tl)}).status_code == 409
    assert not manager.list()


def test_status_exposes_owner_snapshot(repair_client):
    client, _, tmp_path, _, config = repair_client
    owner = tmp_path / "Owner"
    owner_key = _bind(config, owner)
    tl = owner / "game" / "tl" / "chinese"
    (tl / "a.rpy").write_text('old "x"\n', encoding="utf-8")
    status = client.get("/api/error-repair", params={"folder": str(tl)}).json()
    assert status["owner_project_key"] == owner_key
    assert status["project_key"]


def test_manual_target_with_owner_then_replay_rejected(repair_client):
    """探针 3：owner A 时手工 target B 合法；owner→C 后旧 body 重放 409。"""
    client, engine, tmp_path, _, config = repair_client
    owner = tmp_path / "Owner"
    other = tmp_path / "Other"
    manual = tmp_path / "ManualB-repair"
    owner_key = _bind(config, owner)
    _bind_other = other / "game" / "tl" / "chinese"
    _bind_other.mkdir(parents=True)
    manual.mkdir(parents=True)
    (manual / "scene.rpy").write_text('\told "A"\n\tnew "A"\n', encoding="utf-8")

    status = client.get("/api/error-repair", params={"folder": str(manual)}).json()
    assert status["owner_project_key"] == owner_key
    target_key = status["project_key"]
    body = {
        "folder": str(manual),
        "project_key": target_key,
        "owner_project_key": owner_key,
        "fix_indent": True,
        "confirm": True,
    }
    legal = client.post("/api/error-repair/fix", json=body)
    assert legal.status_code == 200, legal.text
    job = _finish(client, legal.json()["job"]["id"])
    assert job["status"] == "done"
    assert "\t" not in (manual / "scene.rpy").read_text(encoding="utf-8")

    # 切到 owner C，旧 body 必须拒绝且不再写入
    (manual / "scene.rpy").write_text('\told "B"\n\tnew "B"\n', encoding="utf-8")
    other_key = _bind(config, other)
    assert other_key != owner_key
    delayed = client.post("/api/error-repair/fix", json=body)
    assert delayed.status_code == 409
    assert "\t" in (manual / "scene.rpy").read_text(encoding="utf-8")
    assert engine.get_status() == Engine.Status.IDLE


def test_unbound_manual_target_allowed(repair_client):
    """未绑定 owner 时手工目录可合法执行。"""
    client, engine, tmp_path, _, config = repair_client
    config.renpy_project_path = config.renpy_game_folder = config.renpy_tl_folder = ""
    config.input_folder = ""
    manual = tmp_path / "UnboundB"
    manual.mkdir()
    (manual / "scene.rpy").write_text('\told "A"\n', encoding="utf-8")
    status = client.get("/api/error-repair", params={"folder": str(manual)}).json()
    assert status["owner_project_key"] == ""
    response = client.post("/api/error-repair/fix", json={
        "folder": str(manual),
        "project_key": status["project_key"],
        "owner_project_key": "",
        "fix_indent": True,
        "confirm": True,
    })
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert engine.get_status() == Engine.Status.IDLE


def test_fix_cancel_after_first_write_reports_partial(repair_client, monkeypatch):
    """探针 4：首文件已写后取消 → written/partial=true 与增量计数。"""
    client, engine, tmp_path, _, config = repair_client
    owner = tmp_path / "Owner"
    owner_key = _bind(config, owner)
    tl = owner / "game" / "tl" / "chinese"
    a = tl / "a.rpy"
    b = tl / "b.rpy"
    a.write_text('\told "A"\n', encoding="utf-8")
    b.write_text('\told "B"\n', encoding="utf-8")

    real_fix = ErrorRepairer.auto_fix_file
    wrote_first = threading.Event()
    release = threading.Event()
    calls = {"n": 0}

    def gated(self, file_path, *args, **kwargs):
        ok, count = real_fix(self, file_path, *args, **kwargs)
        calls["n"] += 1
        if calls["n"] == 1 and count > 0:
            wrote_first.set()
            assert release.wait(5)
        return ok, count

    monkeypatch.setattr(ErrorRepairer, "auto_fix_file", gated)

    status = client.get("/api/error-repair", params={"folder": str(tl)}).json()
    response = client.post("/api/error-repair/fix", json={
        "folder": str(tl),
        "project_key": status["project_key"],
        "owner_project_key": owner_key,
        "fix_indent": True,
        "confirm": True,
    })
    assert response.status_code == 200, response.text
    job_id = response.json()["job"]["id"]
    assert wrote_first.wait(3)
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
    release.set()
    job = _finish(client, job_id, timeout=8.0)
    assert job["status"] == "cancelled"
    result = job["result"] or {}
    assert result.get("written") is True
    assert result.get("partial") is True
    assert int(result.get("fixed_files") or 0) >= 1
    assert "\t" not in a.read_text(encoding="utf-8")
    assert engine.get_status() == Engine.Status.IDLE


def test_fix_owner_change_before_first_write_blocks(repair_client, monkeypatch):
    """探针 5：列表后、首写前切 owner → 阻止写入。"""
    client, engine, tmp_path, _, config = repair_client
    owner = tmp_path / "Owner"
    other = tmp_path / "Other"
    owner_key = _bind(config, owner)
    tl = owner / "game" / "tl" / "chinese"
    a = tl / "a.rpy"
    b = tl / "b.rpy"
    before_a = '\told "A"\n'
    before_b = '\told "B"\n'
    a.write_text(before_a, encoding="utf-8")
    b.write_text(before_b, encoding="utf-8")

    listed = threading.Event()
    proceed = threading.Event()
    real_list = ErrorRepairer.get_rpy_files

    def gated_list(folder_path):
        files = real_list(folder_path)
        listed.set()
        assert proceed.wait(5)
        return files

    monkeypatch.setattr(ErrorRepairer, "get_rpy_files", staticmethod(gated_list))

    status = client.get("/api/error-repair", params={"folder": str(tl)}).json()
    response = client.post("/api/error-repair/fix", json={
        "folder": str(tl),
        "project_key": status["project_key"],
        "owner_project_key": owner_key,
        "fix_indent": True,
        "confirm": True,
    })
    assert response.status_code == 200, response.text
    job_id = response.json()["job"]["id"]
    assert listed.wait(3)
    _bind(config, other)
    proceed.set()
    job = _finish(client, job_id, timeout=8.0)
    assert job["status"] in {"failed", "cancelled"}
    result = job["result"] or {}
    assert result.get("written") in (False, None)
    assert a.read_text(encoding="utf-8") == before_a
    assert b.read_text(encoding="utf-8") == before_b
    assert engine.get_status() == Engine.Status.IDLE


def test_fix_rejects_junction_escape(repair_client):
    """探针 6：选中目录下 junction 指向外部时拒绝，外部文件不得改写。"""
    client, engine, tmp_path, _, _ = repair_client
    root = tmp_path / "LinkedTL"
    outside = tmp_path / "Outside"
    root.mkdir()
    outside.mkdir()
    outside_file = outside / "outside.rpy"
    outside_file.write_text('\told "OUT"\n', encoding="utf-8")
    _make_junction(root / "linked", outside)
    before = outside_file.read_text(encoding="utf-8")
    response = client.post("/api/error-repair/fix", json={
        "folder": str(root),
        "fix_indent": True,
        "confirm": True,
    })
    assert response.status_code in {400, 409}
    assert outside_file.read_text(encoding="utf-8") == before
    assert engine.get_status() == Engine.Status.IDLE


def test_large_scan_status_stays_small_and_full_report_exports(repair_client):
    from openpyxl import load_workbook

    client, _, tmp_path, _, _ = repair_client
    tl = tmp_path / "tl"
    tl.mkdir()
    script = tl / "large.rpy"
    script.write_text('translate chinese strings:\n' + ''.join(
        f'    old "Hello {i} [name]"\n    new "你好 {i}"\n' for i in range(2000)
    ), encoding="utf-8")
    before = script.read_bytes()
    response = client.post("/api/error-repair/scan", json={"folder": str(tl)})
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done", job
    assert job["result"]["total_issues"] == 2000
    assert job["result"]["affected_files"] == 1
    assert job["result"]["scanned_files"] == 1
    for _ in range(2):
        status = client.get("/api/error-repair", params={"folder": str(tl)})
        assert len(status.content) < 3000
        assert "report" not in status.json()["job"]["result"]
        assert status.json()["has_scan_report"] is True
    output = tmp_path / "full.xlsx"
    exported = client.post("/api/error-repair/export", json={
        "folder": str(tl), "output_path": str(output),
    })
    assert exported.status_code == 200, exported.text
    with output.open("rb") as stream:
        workbook = load_workbook(stream, read_only=True)
        assert workbook.active.max_row == 2001
        workbook.close()
    assert script.read_bytes() == before


def test_scan_cancel_during_single_file_releases_engine_and_keeps_previous_report(repair_client, monkeypatch):
    from importlib import import_module

    client, engine, tmp_path, _, _ = repair_client
    tl = _tl(tmp_path)
    first = client.post("/api/error-repair/scan", json={"folder": str(tl)})
    assert _finish(client, first.json()["job"]["id"])["status"] == "done"
    module = import_module("module.Tool.ErrorRepairer")
    parse = module.parse_tl_document
    entered, release = threading.Event(), threading.Event()
    touched = False

    def gated_parse(lines, *, checkpoint):
        def tick():
            nonlocal touched
            if not touched:
                touched = True
                entered.set()
                assert release.wait(5)
            checkpoint()
        return parse(lines, checkpoint=tick)

    monkeypatch.setattr(module, "parse_tl_document", gated_parse)
    before = {path: path.read_bytes() for path in tl.glob("*.rpy")}
    response = client.post("/api/error-repair/scan", json={"folder": str(tl)})
    job_id = response.json()["job"]["id"]
    try:
        assert entered.wait(3)
        assert client.get("/api/error-repair", params={"folder": str(tl)}).status_code == 200
        assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
    finally:
        release.set()
    assert _finish(client, job_id)["status"] == "cancelled"
    assert engine.get_status() == Engine.Status.IDLE
    assert client.get("/api/error-repair", params={"folder": str(tl)}).json()["has_scan_report"]
    assert all(path.read_bytes() == value for path, value in before.items())


def test_fix_with_all_options_off_preserves_empty_blocks(repair_client):
    client, _, tmp_path, _, _ = repair_client
    tl = tmp_path / "tl"
    tl.mkdir()
    script = tl / "empty.rpy"
    original = b'translate chinese strings:\n    # intentionally empty\n'
    script.write_bytes(original)
    body = {"folder": str(tl), "fix_indent": False, "confirm": True}
    response = client.post("/api/error-repair/fix", json=body)
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done" and job["result"]["fixed_items"] == 0
    assert script.read_bytes() == original
    assert not list(tl.glob("*.bak"))
    response = client.post("/api/error-repair/fix", json={**body, "fix_empty_blocks": True})
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done" and job["result"]["fixed_items"] == 1
    assert script.read_bytes() == b""
    [backup] = list(tl.glob("*.bak"))
    assert backup.read_bytes() == original


def test_checker_failure_is_not_reported_as_clean_scan(repair_client, monkeypatch):
    client, engine, tmp_path, _, _ = repair_client
    tl = _tl(tmp_path)

    def fail_check(*args):
        raise ValueError("scan probe failed")

    monkeypatch.setattr(ErrorRepairer, "_detect_quote_issue", fail_check)
    response = client.post("/api/error-repair/scan", json={"folder": str(tl)})
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"
    assert "scan probe failed" in job["error"]
    assert "total_issues" not in job["result"]
    assert not client.get("/api/error-repair", params={"folder": str(tl)}).json()["has_scan_report"]
    assert engine.get_status() == Engine.Status.IDLE
