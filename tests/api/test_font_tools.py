"""字体注入 API：绑定项目、确认、忙碌拒绝、协作取消与成功写入。"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes.font_tools import router
from api.routes.jobs import router as jobs_router
from module.Config import Config
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import RenpyProjectPaths


@pytest.fixture
def font_app(tmp_path, monkeypatch):
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
    (game / "tl" / "chinese").mkdir(parents=True)
    (game / "tl" / "schinese").mkdir(parents=True)
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


def _finish(client, job_id, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        result = job.get("result") or {}
        if job["status"] in {"done", "failed", "cancelled"} and not result.get("worker_active"):
            return job
        time.sleep(0.01)
    pytest.fail(f"任务未结束：{job}")


def _inject(key, language="chinese", **extra):
    return {
        "project_key": key,
        "language": language,
        "generate_gui_hook": False,
        "custom_font": "",
        "confirm": True,
        **extra,
    }


def _make_junction(link: Path, target: Path) -> None:
    """优先目录联接；不可用时 skip，避免在无权限环境误报失败。"""
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not link.exists():
        pytest.skip(f"无法创建目录联接: {completed.stderr or completed.stdout}")


def _make_file_symlink(link: Path, target: Path) -> None:
    """创建文件符号链接；Windows 无权限或环境不支持时 skip。"""
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target)
    except OSError:
        completed = subprocess.run(
            ["cmd", "/c", "mklink", str(link), str(target)],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0 or not link.exists():
            pytest.skip(
                f"无法创建文件符号链接: {completed.stderr or completed.stdout or 'OSError'}"
            )
    if not link.exists():
        pytest.skip("无法创建文件符号链接")


def test_inject_writes_base_box_and_fonts(font_app):
    client, _, engine, _, game, paths, _ = font_app
    response = client.post("/api/font-tools/inject", json=_inject(paths.project_key))
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["written"] is True
    assert job["result"]["worker_active"] is False
    assert job["result"]["language"] == "chinese"
    assert (game / "tl" / "chinese" / "base_box").is_dir()
    assert any((game / "tl" / "chinese" / "fonts").glob("*.ttf"))
    assert engine.get_status() == Engine.Status.IDLE
    status = client.get("/api/font-tools").json()
    assert status["project_key"] == paths.project_key
    assert "chinese" in status["languages"]
    assert status["job"]["id"] == job["id"]


def test_reject_confirm_project_mismatch_and_busy(font_app):
    client, _, engine, _, game, paths, manager = font_app
    refused = client.post(
        "/api/font-tools/inject",
        json={**_inject(paths.project_key), "confirm": False},
    )
    assert refused.status_code == 400
    assert "confirm" in refused.json()["detail"]
    assert client.post("/api/font-tools/inject", json=_inject("")).status_code == 400
    assert client.post(
        "/api/font-tools/inject",
        json=_inject(paths.project_key + "-stale"),
    ).status_code == 409
    assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
    assert client.post("/api/font-tools/inject", json=_inject(paths.project_key)).status_code == 409
    assert not manager.list()
    engine.set_status(Engine.Status.IDLE)
    assert not (game / "tl" / "chinese" / "base_box").exists()


def test_cancel_before_write_is_safe(font_app, monkeypatch):
    client, _, engine, _, game, paths, _ = font_app
    entered, release = threading.Event(), threading.Event()
    real = __import__("api.routes.font_tools", fromlist=["_run_inject"])._run_inject

    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        kwargs["check_cancel"]()
        return real(*args, **kwargs)

    monkeypatch.setattr("api.routes.font_tools._run_inject", slow)
    try:
        response = client.post("/api/font-tools/inject", json=_inject(paths.project_key))
        assert response.status_code == 200, response.text
        job_id = response.json()["job"]["id"]
        assert entered.wait(2)
        assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
        assert engine.get_status() == Engine.Status.TESTING
    finally:
        release.set()
    job = _finish(client, job_id)
    assert job["status"] == "cancelled"
    assert job["result"]["worker_active"] is False
    # 取消发生在真正写入前（check_cancel），不应留下完整注入产物
    assert not (game / "tl" / "chinese" / "base_box").exists()
    assert engine.get_status() == Engine.Status.IDLE


def test_project_switch_rejects_stale_write(font_app, monkeypatch, tmp_path):
    """worker 内 check_cancel 发现冻结 owner 已变 → 拒绝写入。"""
    client, config, engine, _, game, paths, _ = font_app
    entered, release = threading.Event(), threading.Event()
    font_mod = __import__("api.routes.font_tools", fromlist=["_project_identity"])
    real = font_mod._project_identity
    calls = {"n": 0}

    def wrapped(config_obj):
        calls["n"] += 1
        if calls["n"] > 1:
            entered.set()
            assert release.wait(5)
        return real(config_obj)

    monkeypatch.setattr("api.routes.font_tools._project_identity", wrapped)
    other, other_game = _make_project(tmp_path / "other-root")
    try:
        response = client.post("/api/font-tools/inject", json=_inject(paths.project_key))
        assert response.status_code == 200, response.text
        job_id = response.json()["job"]["id"]
        assert entered.wait(2)
        _bind(config, other)
        release.set()
        job = _finish(client, job_id)
    finally:
        release.set()
    assert job["status"] == "failed"
    assert "项目已切换" in (job["error"] or job["result"].get("message") or "")
    assert job["result"]["written"] is False
    assert not (game / "tl" / "chinese" / "base_box").exists()
    assert not (other_game / "tl" / "chinese" / "base_box").exists()
    assert engine.get_status() == Engine.Status.IDLE


def test_inject_rejects_escaping_tl_junction(font_app, tmp_path):
    """game/tl 若是指向项目外的目录联接，注入须 400 且不写出 base_box/fonts。"""
    client, _, engine, _, game, paths, manager = font_app
    outside = tmp_path / "outside_tl"
    (outside / "chinese").mkdir(parents=True)
    shutil.rmtree(game / "tl")
    _make_junction(game / "tl", outside)

    response = client.post("/api/font-tools/inject", json=_inject(paths.project_key))
    assert response.status_code == 400, response.text
    assert "越出" in response.json()["detail"]
    assert not (outside / "chinese" / "base_box").exists()
    assert not (outside / "chinese" / "fonts").exists()
    assert list(outside.rglob("base_box")) == []
    assert list(outside.rglob("fonts")) == []
    assert not manager.list()
    assert engine.get_status() == Engine.Status.IDLE


def test_inject_rejects_base_box_child_symlink_outside(font_app, tmp_path):
    """base_box 内文件若是指向项目外的链接，注入须 400 且不覆盖外部文件。"""
    client, _, engine, _, game, paths, manager = font_app
    outside_file = tmp_path / "outside_secret.txt"
    outside_file.write_text("do-not-touch", encoding="utf-8")
    base_box = game / "tl" / "chinese" / "base_box"
    base_box.mkdir(parents=True)
    marker = base_box / "keep_me.txt"
    marker.write_text("user-file", encoding="utf-8")
    _make_file_symlink(base_box / "escape.txt", outside_file)

    response = client.post("/api/font-tools/inject", json=_inject(paths.project_key))
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "链接" in detail or "越出" in detail or "联接" in detail
    assert outside_file.read_text(encoding="utf-8") == "do-not-touch"
    assert marker.read_text(encoding="utf-8") == "user-file"
    assert not manager.list()
    assert engine.get_status() == Engine.Status.IDLE


def _seed_fonts(game: Path) -> Path:
    fonts = game / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    (fonts / "used.ttf").write_bytes(b"used-font")
    (fonts / "orphan.otf").write_bytes(b"orphan-font")
    (game / "gui.rpy").write_text(
        'define gui.text_font = "fonts/used.ttf"\n'
        'define gui.name_text_font = "fonts/used.ttf"\n',
        encoding="utf-8",
    )
    source = game.parent / "replacement.ttf"
    source.write_bytes(b"replacement-font")
    return source


def _replace(key, **extra):
    return {
        "project_key": key,
        "replace_all": False,
        "selected_font": "",
        "original_font": "fonts/used.ttf",
        "custom_font": "",
        "create_backup": True,
        "confirm": True,
        **extra,
    }


def test_scan_distinguishes_refs_and_files(font_app):
    client, _, engine, _, game, paths, _ = font_app
    _seed_fonts(game)
    response = client.post("/api/font-tools/scan", json={"project_key": paths.project_key})
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["written"] is False
    assert job["result"]["action"] == "scan"
    assert "fonts/used.ttf" in job["result"]["font_refs"]
    assert "fonts/orphan.otf" not in job["result"]["font_refs"]
    assert "fonts/used.ttf" in job["result"]["font_files"]
    assert "fonts/orphan.otf" in job["result"]["font_files"]
    assert job["result"]["font_ref_count"] == 1
    assert job["result"]["font_file_count"] == 2
    status = client.get("/api/font-tools").json()
    assert status["font_ref_count"] == 1
    assert status["font_file_count"] == 2
    assert "schinese" in status["languages"]
    assert engine.get_status() == Engine.Status.IDLE


def test_replace_one_font_and_backup_uses_bak(font_app):
    client, _, engine, _, game, paths, _ = font_app
    source = _seed_fonts(game)
    response = client.post(
        "/api/font-tools/replace",
        json=_replace(paths.project_key, custom_font=str(source)),
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["written"] is True
    assert job["result"]["replaced_files"] >= 1
    assert job["result"]["replaced_count"] >= 1
    script = (game / "gui.rpy").read_text(encoding="utf-8")
    assert "fonts/replacement.ttf" in script
    assert "fonts/used.ttf" not in script
    backup_name = job["result"]["backup_name"]
    assert backup_name
    backup_script = game / "fonts_backup" / backup_name / "original" / "gui.rpy.bak"
    assert backup_script.is_file()
    assert not (game / "fonts_backup" / backup_name / "original" / "gui.rpy").exists()
    assert engine.get_status() == Engine.Status.IDLE


def test_replace_all_detected_fonts(font_app):
    client, _, _, _, game, paths, _ = font_app
    source = _seed_fonts(game)
    (game / "extra.rpy").write_text('define gui.title_font = "fonts/orphan.otf"\n', encoding="utf-8")
    response = client.post(
        "/api/font-tools/replace",
        json=_replace(
            paths.project_key,
            replace_all=True,
            original_font="",
            selected_font="",
            custom_font=str(source),
        ),
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["replaced_count"] >= 2
    assert "fonts/replacement.ttf" in (game / "gui.rpy").read_text(encoding="utf-8")
    assert "fonts/replacement.ttf" in (game / "extra.rpy").read_text(encoding="utf-8")


def test_missing_custom_font_has_zero_side_effects(font_app):
    client, _, engine, _, game, paths, manager = font_app
    _seed_fonts(game)
    before = (game / "gui.rpy").read_text(encoding="utf-8")
    response = client.post(
        "/api/font-tools/replace",
        json=_replace(paths.project_key, custom_font=str(game / "missing-font.ttf")),
    )
    assert response.status_code == 400, response.text
    assert "不存在" in response.json()["detail"]
    assert (game / "gui.rpy").read_text(encoding="utf-8") == before
    assert not list((game / "fonts_backup").glob("*")) if (game / "fonts_backup").exists() else True
    assert not manager.list()
    assert engine.get_status() == Engine.Status.IDLE


def test_inject_gui_rejects_fonts_junction(font_app, tmp_path):
    """GUI 写入 game/fonts 时若 fonts 是越界联接则拒绝。"""
    client, _, engine, _, game, paths, manager = font_app
    outside = tmp_path / "outside_fonts"
    outside.mkdir()
    _make_junction(game / "fonts", outside)
    custom = tmp_path / "hook.ttf"
    custom.write_bytes(b"hook")
    response = client.post(
        "/api/font-tools/inject",
        json=_inject(
            paths.project_key,
            generate_gui_hook=True,
            custom_font=str(custom),
        ),
    )
    assert response.status_code == 400, response.text
    assert not manager.list()
    assert engine.get_status() == Engine.Status.IDLE
    assert list(outside.iterdir()) == []


def test_inject_backup_scripts_use_bak_extension(font_app):
    client, _, _, _, game, paths, _ = font_app
    base_box = game / "tl" / "chinese" / "base_box"
    base_box.mkdir(parents=True)
    (base_box / "old_style.rpy").write_text("translate chinese style:\n    pass\n", encoding="utf-8")
    response = client.post("/api/font-tools/inject", json=_inject(paths.project_key))
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    backup = Path(job["result"]["backup_path"])
    assert backup.is_dir()
    assert list(backup.rglob("*.rpy")) == []
    assert list(backup.rglob("*.rpy.bak")) or list(backup.rglob("*.bak"))


def _assert_no_live_scripts(root: Path) -> None:
    live = [
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".rpy", ".rpym", ".rpyc", ".rpymc"}
    ]
    assert live == [], f"backup still has live scripts: {live}"


def test_scan_cancel_and_busy_guard(font_app, monkeypatch):
    client, _, engine, _, game, paths, manager = font_app
    _seed_fonts(game)
    entered, release = threading.Event(), threading.Event()
    real = __import__("api.routes.font_tools", fromlist=["_run_scan"])._run_scan

    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        kwargs["check_cancel"]()
        return real(*args, **kwargs)

    monkeypatch.setattr("api.routes.font_tools._run_scan", slow)
    try:
        response = client.post("/api/font-tools/scan", json={"project_key": paths.project_key})
        assert response.status_code == 200, response.text
        job_id = response.json()["job"]["id"]
        assert entered.wait(2)
        assert client.post(
            "/api/font-tools/inject",
            json=_inject(paths.project_key),
        ).status_code == 409
        assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 200
    finally:
        release.set()
    job = _finish(client, job_id)
    assert job["status"] == "cancelled"
    assert job["result"]["written"] is False
    assert engine.get_status() == Engine.Status.IDLE
    assert not (game / "tl" / "chinese" / "base_box").exists()
    # busy 期间未创建注入任务
    assert all(item.kind != "font_inject" for item in manager.list())


def test_replace_rejects_missing_original_selection(font_app):
    client, _, _, _, game, paths, _ = font_app
    source = _seed_fonts(game)
    response = client.post(
        "/api/font-tools/replace",
        json=_replace(
            paths.project_key,
            replace_all=False,
            selected_font="",
            original_font="",
            custom_font=str(source),
        ),
    )
    assert response.status_code == 400
    assert "原字体" in response.json()["detail"] or "替换" in response.json()["detail"]


def test_inject_deploy_partial_failure_keeps_backup_and_written(font_app, monkeypatch):
    """部署写了一部分后失败：Job 保留 written/partial/backup，不得谎称未写入。"""
    client, _, engine, _, game, paths, _ = font_app
    base_box = game / "tl" / "chinese" / "base_box"
    base_box.mkdir(parents=True)
    (base_box / "old_style.rpy").write_text("translate chinese style:\n    pass\n", encoding="utf-8")

    def partial_deploy(self, game_dir, tl_name="base_box"):
        resolved = Path(self._resolve_game_dir(game_dir)) / "tl" / tl_name / "base_box"
        resolved.mkdir(parents=True, exist_ok=True)
        (resolved / "partial.rpy").write_text("# partial\n", encoding="utf-8")
        return False, "模拟部署中断"

    monkeypatch.setattr(
        "module.Tool.FontReplacer.FontReplacer.deploy_builtin_font_pack",
        partial_deploy,
    )
    response = client.post("/api/font-tools/inject", json=_inject(paths.project_key))
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"
    result = job["result"]
    assert result["written"] is True
    assert result["partial"] is True
    assert result.get("backup_path")
    assert Path(result["backup_path"]).is_dir()
    assert list(Path(result["backup_path"]).rglob("*.rpy")) == []
    assert "未写入" not in (result.get("message") or "")
    assert engine.get_status() == Engine.Status.IDLE


def test_inject_gui_exception_keeps_written_backup(font_app, monkeypatch, tmp_path):
    """部署成功后 GUI 异常：仍保留 written/partial/backup。"""
    client, _, _, _, game, paths, _ = font_app
    custom = tmp_path / "hook.ttf"
    custom.write_bytes(b"hook-font")

    def boom(*args, **kwargs):
        raise RuntimeError("模拟 GUI 异常")

    monkeypatch.setattr("module.Tool.FontReplacer.FontReplacer.gen_gui_fonts", boom)
    response = client.post(
        "/api/font-tools/inject",
        json=_inject(paths.project_key, generate_gui_hook=True, custom_font=str(custom)),
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"
    result = job["result"]
    assert result["written"] is True
    assert result["partial"] is True
    assert result.get("gui_hook") is False
    assert (game / "tl" / "chinese" / "base_box").is_dir()


def test_inject_backup_copy_failure_leaves_no_live_rpy(font_app, monkeypatch):
    """注入备份复制失败：不留下 live .rpy，且不继续部署。"""
    client, _, engine, _, game, paths, _ = font_app
    base_box = game / "tl" / "chinese" / "base_box"
    base_box.mkdir(parents=True)
    (base_box / "old_style.rpy").write_text("translate chinese style:\n    pass\n", encoding="utf-8")

    def fail_copy(*args, **kwargs):
        raise OSError("simulated backup copy failure")

    monkeypatch.setattr("api.routes.font_tools._copy_path_into_backup", fail_copy)
    response = client.post("/api/font-tools/inject", json=_inject(paths.project_key))
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"
    result = job["result"]
    assert result["written"] is False
    assert "备份失败" in (result.get("message") or job.get("error") or "")
    # 不继续部署：base_box 仍只有原文件
    assert list(base_box.glob("*.rpy")) == [base_box / "old_style.rpy"]
    backup_root = game / "fonts_backup"
    assert backup_root.is_dir()
    assert list(backup_root.rglob("*.rpy")) == []
    assert result.get("backup_path")
    assert engine.get_status() == Engine.Status.IDLE


def test_replace_failure_preserves_details_and_backup(font_app, monkeypatch):
    client, _, _, _, game, paths, _ = font_app
    source = _seed_fonts(game)
    before = (game / "gui.rpy").read_text(encoding="utf-8")

    def fail_replace(self, **kwargs):
        return False, "模拟替换失败", {
            "backup_name": "backup_keep_me",
            "replaced_files": 0,
            "replaced_count": 0,
            "restored": False,
        }

    monkeypatch.setattr(
        "module.Tool.FontReplacer.FontReplacer.safe_replace_font",
        fail_replace,
    )
    # 预置可恢复路径目录，模拟真实备份名
    keep = game / "fonts_backup" / "backup_keep_me"
    keep.mkdir(parents=True)
    response = client.post(
        "/api/font-tools/replace",
        json=_replace(paths.project_key, custom_font=str(source)),
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"
    result = job["result"]
    assert result["backup_name"] == "backup_keep_me"
    assert result["backup_path"]
    assert "backup_keep_me" in result["backup_path"]
    assert "模拟替换失败" in (result.get("message") or "")
    assert (game / "gui.rpy").read_text(encoding="utf-8") == before


def test_replace_success_marks_scan_stale_until_rescan(font_app):
    client, _, _, _, game, paths, _ = font_app
    source = _seed_fonts(game)
    scan = client.post("/api/font-tools/scan", json={"project_key": paths.project_key})
    assert scan.status_code == 200
    _finish(client, scan.json()["job"]["id"])
    status = client.get("/api/font-tools").json()
    assert status["fonts_scanned"] is True
    assert status["font_ref_count"] >= 1
    assert status.get("scan_stale") is False

    replace = client.post(
        "/api/font-tools/replace",
        json=_replace(paths.project_key, custom_font=str(source)),
    )
    assert replace.status_code == 200
    job = _finish(client, replace.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["written"] is True

    status = client.get("/api/font-tools").json()
    assert status.get("scan_stale") is True
    assert status.get("fonts_scanned") is False
    assert status.get("font_ref_count") == 0
    assert status.get("font_refs") == []

    rescan = client.post("/api/font-tools/scan", json={"project_key": paths.project_key})
    _finish(client, rescan.json()["job"]["id"])
    status = client.get("/api/font-tools").json()
    assert status.get("scan_stale") is False
    assert status.get("fonts_scanned") is True


def test_scan_zero_refs_reports_scanned(font_app):
    client, _, _, _, game, paths, _ = font_app
    (game / "empty.rpy").write_text("# no fonts\n", encoding="utf-8")
    response = client.post("/api/font-tools/scan", json={"project_key": paths.project_key})
    assert response.status_code == 200
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["font_ref_count"] == 0
    status = client.get("/api/font-tools").json()
    assert status["fonts_scanned"] is True
    assert status["font_ref_count"] == 0
    assert status.get("scan_stale") is False


def test_replace_partial_script_write_propagates_not_full_success(font_app, monkeypatch):
    """两脚本其一 atomic 写失败：API 不得报全成功；须 partial + failed_files。"""
    import module.Tool.FontReplacer as font_module

    client, _, engine, _, game, paths, _ = font_app
    source = _seed_fonts(game)
    (game / "extra.rpy").write_text(
        'define gui.title_font = "fonts/used.ttf"\n',
        encoding="utf-8",
    )
    real_atomic = font_module.atomic_write_text

    def flaky_atomic(path, text, **kwargs):
        if Path(path).name == "extra.rpy":
            raise OSError("simulated second-script write failure")
        return real_atomic(path, text, **kwargs)

    monkeypatch.setattr(font_module, "atomic_write_text", flaky_atomic)
    response = client.post(
        "/api/font-tools/replace",
        json=_replace(
            paths.project_key,
            custom_font=str(source),
            create_backup=False,
        ),
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"
    result = job["result"]
    assert result.get("partial") is True
    assert result.get("written") is True
    assert int(result.get("replaced_files") or 0) >= 1
    assert any(str(item).endswith("extra.rpy") for item in (result.get("failed_files") or []))
    assert result.get("font_copied") is True
    assert "fonts/replacement.ttf" in (game / "gui.rpy").read_text(encoding="utf-8")
    assert "fonts/used.ttf" in (game / "extra.rpy").read_text(encoding="utf-8")
    assert engine.get_status() == Engine.Status.IDLE


def test_replace_no_backup_batch_error_reports_font_copied(font_app, monkeypatch):
    """无备份：字体已复制后 batch 抛错，written/partial 不能靠 backup_name 猜成未写入。"""
    client, _, _, _, game, paths, _ = font_app
    source = _seed_fonts(game)

    def boom_folder(self, *args, **kwargs):
        raise RuntimeError("simulated batch boom")

    monkeypatch.setattr(
        "module.Tool.FontReplacer.FontReplacer.replace_fonts_in_folder",
        boom_folder,
    )
    response = client.post(
        "/api/font-tools/replace",
        json=_replace(
            paths.project_key,
            custom_font=str(source),
            create_backup=False,
        ),
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"
    result = job["result"]
    # 撤回新建字体成功 → 可无 written；若残留则必须 written/partial
    if (game / "fonts" / "replacement.ttf").exists():
        assert result.get("written") is True
        assert result.get("partial") is True
        assert result.get("font_residue") or result.get("font_copied")
    else:
        # 已撤回复制：磁盘干净，但不得用 backup 存在性谎报
        assert not result.get("backup_name")
        assert result.get("written") is False
    assert "fonts/used.ttf" in (game / "gui.rpy").read_text(encoding="utf-8")


def test_inject_or_failed_write_marks_scan_stale(font_app):
    """注入写入后旧扫描作废；失败但 written 的替换同样 scan_stale。"""
    client, _, _, _, game, paths, _ = font_app
    source = _seed_fonts(game)
    scan = client.post("/api/font-tools/scan", json={"project_key": paths.project_key})
    _finish(client, scan.json()["job"]["id"])
    assert client.get("/api/font-tools").json().get("fonts_scanned") is True

    inject = client.post("/api/font-tools/inject", json=_inject(paths.project_key))
    inject_job = _finish(client, inject.json()["job"]["id"])
    assert inject_job["status"] == "done"
    assert inject_job["result"]["written"] is True
    status = client.get("/api/font-tools").json()
    assert status.get("scan_stale") is True
    assert status.get("fonts_scanned") is False


def test_inject_backup_compiled_scripts_use_bak_on_second_inject(font_app):
    """二次注入：备份树内 .rpy/.rpym/.rpyc/.rpymc 一律以 .bak 落盘，无 live 可执行脚本。"""
    client, _, _, _, game, paths, _ = font_app
    base_box = game / "tl" / "chinese" / "base_box"
    base_box.mkdir(parents=True)
    (base_box / "style.rpy").write_text("translate chinese style:\n    pass\n", encoding="utf-8")
    (base_box / "mod.rpym").write_text("# mod\n", encoding="utf-8")
    (base_box / "style.rpyc").write_bytes(b"compiled-rpy")
    (base_box / "mod.rpymc").write_bytes(b"compiled-rpym")

    first = client.post("/api/font-tools/inject", json=_inject(paths.project_key))
    assert first.status_code == 200, first.text
    assert _finish(client, first.json()["job"]["id"])["status"] == "done"

    # 部署后若仍有编译脚本，再注入一次走完整备份路径
    target = game / "tl" / "chinese" / "base_box"
    (target / "keep.rpyc").write_bytes(b"keep-compiled")
    (target / "keep.rpymc").write_bytes(b"keep-compiled-m")
    (target / "keep.rpy").write_text("# keep\n", encoding="utf-8")

    second = client.post("/api/font-tools/inject", json=_inject(paths.project_key))
    assert second.status_code == 200, second.text
    job = _finish(client, second.json()["job"]["id"])
    assert job["status"] == "done"
    backup = Path(job["result"]["backup_path"])
    assert backup.is_dir()
    _assert_no_live_scripts(backup)
    assert list(backup.rglob("*.rpyc.bak")) or list(backup.rglob("*keep.rpyc.bak"))
    assert any(path.name.endswith(".rpymc.bak") for path in backup.rglob("*"))
    assert any(path.name.endswith(".rpy.bak") for path in backup.rglob("*"))


def test_owner_switch_during_prewrite_blocks_both_projects(font_app, monkeypatch, tmp_path):
    """阻塞 worker 写前阶段后切 owner：放行后新旧项目均不写入。"""
    client, config, engine, project, game, paths, _ = font_app
    other_project, other_game = _make_project(tmp_path / "OtherDemo")
    entered, release = threading.Event(), threading.Event()
    real = __import__("api.routes.font_tools", fromlist=["_run_inject"])._run_inject

    def slow(*args, **kwargs):
        check_cancel = kwargs["check_cancel"]
        check_cancel()
        entered.set()
        assert release.wait(5)
        # 写前再次校验：owner 已变应直接失败，不得进入真实写入
        check_cancel()
        return real(*args, **kwargs)

    monkeypatch.setattr("api.routes.font_tools._run_inject", slow)
    try:
        response = client.post("/api/font-tools/inject", json=_inject(paths.project_key))
        assert response.status_code == 200, response.text
        job_id = response.json()["job"]["id"]
        assert entered.wait(2)
        _bind(config, other_project)
    finally:
        release.set()

    job = _finish(client, job_id)
    assert job["status"] == "failed"
    assert job["result"].get("written") is False
    assert "项目已切换" in (job["result"].get("message") or job.get("error") or "")
    assert not (game / "tl" / "chinese" / "base_box").exists()
    assert not (other_game / "tl" / "chinese" / "base_box").exists()
    assert engine.get_status() == Engine.Status.IDLE
    _bind(config, project)


def test_manual_game_path_uses_target_key_without_rebinding(font_app, tmp_path):
    """已有 owner 时可手动指定另一目标；不改全局绑定路径。"""
    client, config, _, project, game, paths, _ = font_app
    other_project, other_game = _make_project(tmp_path / "ManualTarget")
    other_paths = RenpyProjectPaths.from_path(other_project, "chinese")
    assert other_paths is not None
    owner_before = (
        config.renpy_project_path,
        config.renpy_game_folder,
        config.renpy_tl_folder,
    )

    status = client.get(f"/api/font-tools?game_path={other_project}")
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["project_key"] == other_paths.project_key
    assert body["project_key"] != paths.project_key

    response = client.post(
        "/api/font-tools/inject",
        json=_inject(other_paths.project_key, game_path=str(other_project)),
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["project_key"] == other_paths.project_key
    assert job["result"]["written"] is True
    assert (other_game / "tl" / "chinese" / "base_box").is_dir()
    assert not (game / "tl" / "chinese" / "base_box").exists()
    assert (
        config.renpy_project_path,
        config.renpy_game_folder,
        config.renpy_tl_folder,
    ) == owner_before


def test_last_write_job_survives_rescan(font_app):
    """自动重扫后 status.job 可为 scan，但 last_write_job 保留写入计数/备份路径。"""
    client, _, _, _, game, paths, _ = font_app
    _seed_fonts(game)
    inject = client.post("/api/font-tools/inject", json=_inject(paths.project_key))
    inject_job = _finish(client, inject.json()["job"]["id"])
    assert inject_job["status"] == "done"
    assert inject_job["result"]["written"] is True
    backup_path = inject_job["result"].get("backup_path")

    status = client.get("/api/font-tools").json()
    assert status["job"]["kind"] == "font_inject"
    assert status["last_write_job"]["id"] == inject_job["id"]
    assert status["last_write_job"]["result"]["written"] is True

    rescan = client.post("/api/font-tools/scan", json={"project_key": paths.project_key})
    scan_job = _finish(client, rescan.json()["job"]["id"])
    assert scan_job["status"] == "done"

    status = client.get("/api/font-tools").json()
    assert status["job"]["kind"] == "font_scan"
    assert status["job"]["id"] == scan_job["id"]
    write = status["last_write_job"]
    assert write is not None
    assert write["id"] == inject_job["id"]
    assert write["result"]["written"] is True
    assert write["result"].get("action") == "inject"
    if backup_path:
        assert write["result"].get("backup_path") == backup_path
    assert status.get("fonts_scanned") is True
    assert status.get("scan_stale") is False


def test_manual_target_key_not_confused_with_owner(font_app, tmp_path):
    """目标键≠owner 键时不得误判为切项目；project_key 必须匹配 target。"""
    client, _, _, _, _, paths, _ = font_app
    other_project, _ = _make_project(tmp_path / "AltTarget")
    other_paths = RenpyProjectPaths.from_path(other_project, "chinese")
    assert other_paths is not None

    ok = client.post(
        "/api/font-tools/scan",
        json={"project_key": other_paths.project_key, "game_path": str(other_project)},
    )
    assert ok.status_code == 200, ok.text
    assert _finish(client, ok.json()["job"]["id"])["status"] == "done"

    # owner 的 key + 另一目标 → 409（不得把合法手动目标当成切项目成功）
    mismatch = client.post(
        "/api/font-tools/scan",
        json={"project_key": paths.project_key, "game_path": str(other_project)},
    )
    assert mismatch.status_code == 409


def test_explicit_empty_game_path_rejected_omit_still_bound(font_app):
    """显式空 game_path → 400；省略字段仍回退绑定项目（旧调用兼容）。"""
    client, _, _, _, game, paths, _ = font_app
    _seed_fonts(game)

    empty_get = client.get("/api/font-tools?game_path=")
    assert empty_get.status_code == 400
    assert "空" in empty_get.json()["detail"]

    omit_get = client.get("/api/font-tools")
    assert omit_get.status_code == 200
    assert omit_get.json()["project_key"] == paths.project_key

    empty_scan = client.post(
        "/api/font-tools/scan",
        json={"project_key": paths.project_key, "game_path": ""},
    )
    assert empty_scan.status_code == 400

    omit_scan = client.post(
        "/api/font-tools/scan",
        json={"project_key": paths.project_key},
    )
    assert omit_scan.status_code == 200, omit_scan.text
    assert _finish(client, omit_scan.json()["job"]["id"])["status"] == "done"

    empty_inject = client.post(
        "/api/font-tools/inject",
        json=_inject(paths.project_key, game_path=""),
    )
    assert empty_inject.status_code == 400
    assert not (game / "tl" / "chinese" / "base_box").exists()
