"""工作台后台任务回归：只写草稿，取消、项目切换和冲突不得写入结果。"""
from __future__ import annotations

import asyncio
import copy
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager, JobStatus
from api.routes.jobs import router as jobs_router
from api.routes.workbench import router
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.TaskRequester import TaskRequester
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.Workbench.AnalysisService import AnalysisResult, WorkbenchAnalysisService
from module.Workbench.CharacterScanner import CharacterCandidate, CharacterScanner
from module.Workbench.WorkbenchData import create_default_character_card


_REAL_LOAD_SCOPE = WorkbenchAnalysisService.load_scope_items
_REAL_BUILD_CANDIDATES = CharacterScanner.build_candidates


@pytest.fixture
def workbench(tmp_path, monkeypatch):
    monkeypatch.setattr(ProjectAssetsRepository, "_resolve_active_project", lambda self: None)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    project = tmp_path / "story"
    (project / "game" / "tl" / "chinese").mkdir(parents=True)
    config = Config()
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(project / "game")
    config.renpy_tl_folder = str(project / "game" / "tl" / "chinese")
    config.input_folder = config.renpy_tl_folder
    config.output_folder = str(project / "RenpyBox_Translation" / "chinese")
    config.cache_use_sqlite = False
    repository = ProjectAssetsRepository.from_config(config)
    repository.load(config)
    alice = create_default_character_card("Alice")
    alice.update(id="character_manual_uuid", identity="正式身份", enabled=False, is_primary=True)
    config.renpy_workbench_character_cards = [alice]
    config.renpy_workbench_worldbook_data = {"genre": "正式背景"}
    old = create_default_character_card("Alice")
    old.update(identity="已有草稿身份", aliases=["旧别名"], name_translation="旧译名")
    config.renpy_workbench_generated_character_drafts = [old, create_default_character_card("Carol")]
    config.renpy_workbench_generated_worldbook_draft = {"tone_style": "旧草稿风格"}
    repository.save_workbench_view(config)
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.include_router(router)
    app.include_router(jobs_router)
    monkeypatch.setattr(WorkbenchAnalysisService, "ensure_analysis_ready", lambda self, config, **kwargs: {})
    monkeypatch.setattr(WorkbenchAnalysisService, "load_scope_items", lambda self, config, scope: ([], "测试语料"))
    monkeypatch.setattr(CharacterScanner, "build_candidates", lambda *args: [
        CharacterCandidate("Alice", aliases=["新别名"], sample_lines=["台词"], name_translation="新译名"),
        CharacterCandidate("Bob"),
    ])
    with TestClient(app) as client:
        yield client, config, repository, engine
        app.state.jobs.shutdown()


def _body(client, action="scan", scope="current"):
    snapshot = client.get("/api/workbench").json()
    return {"storage_key": snapshot["storage_key"], "revision": snapshot["revision"], "action": action, "scope": scope}


def _start(client, **kwargs):
    response = client.post("/api/workbench/analysis", json=_body(client, **kwargs))
    assert response.status_code == 200, response.text
    return response.json()["job"]


def _finish(client, job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        job = response.json()
        if job["status"] in {"done", "failed", "cancelled"} and not job["result"]["worker_active"]:
            return job
        time.sleep(0.01)
    pytest.fail(f"后台任务没有结束：{job}")


def test_scan_preserves_formal_and_old_drafts_then_applies_by_name(workbench):
    client, config, repository, engine = workbench
    original = client.get("/api/workbench").json()
    assert client.get("/api/workbench/analysis").json() == {"job": None}
    job = _finish(client, _start(client)["id"])
    assert job["status"] == "done"
    assert job["result"]["character_count"] == 2
    assert job["result"]["source_summary"] == "测试语料"
    snapshot = client.get("/api/workbench").json()
    assert snapshot["worldbook"] == original["worldbook"]
    assert snapshot["characters"] == original["characters"]
    assert snapshot["worldbook_draft"] == original["worldbook_draft"]
    alice = next(card for card in snapshot["character_drafts"] if card["name"] == "Alice")
    assert alice["identity"] == "已有草稿身份"
    assert alice["name_translation"] == "旧译名"
    assert alice["aliases"] == ["旧别名", "新别名"]
    assert {card["name"] for card in snapshot["character_drafts"]} == {"Alice", "Bob", "Carol"}
    assert config.renpy_workbench_character_cards == original["characters"]
    assert engine.get_status() == Engine.Status.IDLE
    assert client.get("/api/workbench/analysis").json()["job"]["id"] == job["id"]
    response = client.post("/api/workbench/apply-drafts", json={"storage_key": snapshot["storage_key"], "revision": snapshot["revision"]})
    assert response.status_code == 200
    cards = response.json()["characters"]
    assert len([card for card in cards if card["name"] == "Alice"]) == 1
    alice = next(card for card in cards if card["name"] == "Alice")
    assert alice["id"] == "character_manual_uuid" and not alice["enabled"] and alice["is_primary"]
    assert alice["identity"] == "已有草稿身份"


def test_scan_seed_does_not_clear_existing_character_on_apply(workbench):
    client, config, repository, _ = workbench
    config.renpy_workbench_generated_character_drafts = []
    repository.save_workbench_view(config)
    assert _finish(client, _start(client)["id"])["status"] == "done"
    snapshot = client.get("/api/workbench").json()
    response = client.post("/api/workbench/apply-drafts", json={"storage_key": snapshot["storage_key"], "revision": snapshot["revision"]})
    alice = next(card for card in response.json()["characters"] if card["name"] == "Alice")
    assert alice["identity"] == "正式身份" and not alice["enabled"] and alice["is_primary"]


@pytest.mark.parametrize("action", ["all", "worldbook", "characters"])
def test_ai_results_merge_only_drafts(workbench, monkeypatch, action):
    client, _, _, engine = workbench
    original = client.get("/api/workbench").json()
    alice = create_default_character_card("Alice")
    alice["personality"] = "新性格"
    def analyze(self, config, scope, *, engine_reserved):
        assert engine_reserved and engine.get_status() == Engine.Status.TESTING
        assert getattr(TaskRequester.RUN_CANCEL_CONTEXT, "event", None) is not None
        self._report_progress("测试生成阶段")
        return AnalysisResult(scope, {"genre": "新世界观"} if action != "characters" else {}, [alice] if action != "worldbook" else [])
    method = {"all": "analyze_all", "worldbook": "generate_worldbook_only", "characters": "generate_character_only"}[action]
    monkeypatch.setattr(WorkbenchAnalysisService, method, analyze)
    job = _finish(client, _start(client, action=action, scope="full")["id"])
    assert job["status"] == "done"
    snapshot = client.get("/api/workbench").json()
    assert snapshot["characters"] == original["characters"]
    assert snapshot["worldbook"] == original["worldbook"]
    assert snapshot["worldbook_draft"]["tone_style"] == "旧草稿风格"
    assert any(card["name"] == "Carol" for card in snapshot["character_drafts"])
    if action != "worldbook":
        alice = next(card for card in snapshot["character_drafts"] if card["name"] == "Alice")
        assert alice["identity"] == "已有草稿身份" and alice["personality"] == "新性格"
    if action != "characters":
        assert snapshot["worldbook_draft"]["genre"] == "新世界观"


@pytest.mark.parametrize("conflict", ["revision", "project", "draft"])
def test_late_result_rejects_changed_project_or_assets(workbench, monkeypatch, tmp_path, conflict):
    client, config, repository, engine = workbench
    started, finish = threading.Event(), threading.Event()
    def load(self, config, scope):
        started.set()
        assert finish.wait(5)
        return [], "固定来源"
    monkeypatch.setattr(WorkbenchAnalysisService, "load_scope_items", load)
    try:
        job = _start(client)
        assert started.wait(2)
        if conflict == "project":
            config.renpy_project_path = config.renpy_game_folder = config.renpy_tl_folder = ""
            config.input_folder = config.output_folder = str(tmp_path / "other")
            assert client.get("/api/workbench/analysis").json() == {"job": None}
        elif conflict == "revision":
            repository.save_workbench_view(config)
        else:
            state = repository.load()
            candidates = copy.deepcopy(state.analysis_candidates)
            candidates["worldbook_draft"] = {"genre": "并发新草稿"}
            repository.save_analysis_candidates(candidates)
        expected = repository.load()
        finish.set()
        completed = _finish(client, job["id"])
        assert completed["status"] == "failed" and "重新加载" in completed["error"]
        assert repository.load() == expected
        assert engine.get_status() == Engine.Status.IDLE
    finally:
        finish.set()


@pytest.mark.parametrize("cancel", [True, False])
def test_cancel_or_failure_never_saves_and_holds_engine_until_worker_exit(workbench, monkeypatch, cancel):
    client, _, repository, engine = workbench
    original = repository.load()
    started, finish = threading.Event(), threading.Event()
    observations = []
    def analyze(self, config, scope, *, engine_reserved):
        started.set()
        assert finish.wait(5)
        observations.append((TaskRequester.is_cancel_requested(), engine.get_status()))
        if not cancel:
            raise RuntimeError("测试接口失败")
        self._report_progress("不应继续到下一次模型请求")
        pytest.fail("取消后不应继续分析")
    monkeypatch.setattr(WorkbenchAnalysisService, "analyze_all", analyze)
    try:
        job = _start(client, action="all")
        assert started.wait(2)
        if cancel:
            response = client.post(f"/api/jobs/{job['id']}/cancel")
            assert response.status_code == 200 and response.json()["status"] == "running"
            assert response.json()["result"]["worker_active"]
            assert response.json()["cancel_requested"]
            assert client.get("/api/workbench/analysis").json()["job"]["cancel_requested"]
        assert engine.get_status() == Engine.Status.TESTING
        assert client.post("/api/workbench/analysis", json=_body(client)).status_code == 409
        finish.set()
        completed = _finish(client, job["id"])
        assert completed["status"] == ("cancelled" if cancel else "failed")
        assert observations == [(cancel, Engine.Status.TESTING)]
        assert repository.load() == original
        assert engine.get_status() == Engine.Status.IDLE
    finally:
        finish.set()


def test_shutdown_cancels_worker_without_early_engine_release(workbench, monkeypatch):
    client, _, repository, engine = workbench
    original = repository.load()
    started, finish = threading.Event(), threading.Event()
    def load(self, config, scope):
        started.set()
        assert finish.wait(5)
        return [], "停机来源"
    monkeypatch.setattr(WorkbenchAnalysisService, "load_scope_items", load)
    try:
        job = _start(client)
        assert started.wait(2)
        client.app.state.jobs.shutdown()
        assert engine.get_status() == Engine.Status.TESTING
        assert client.get("/api/workbench/analysis").json()["job"]["result"]["worker_active"]
        finish.set()
        assert _finish(client, job["id"])["status"] == "cancelled"
        assert repository.load() == original
        assert engine.get_status() == Engine.Status.IDLE
    finally:
        finish.set()


def test_start_validates_version_action_and_model_before_starting(workbench, monkeypatch):
    client, _, _, engine = workbench
    body = _body(client)
    assert client.post("/api/workbench/analysis", json={**body, "revision": body["revision"] - 1}).status_code == 409
    assert client.post("/api/workbench/analysis", json={**body, "action": "invalid"}).status_code == 422
    from module.Workbench.AnalysisService import AnalysisServiceError
    def not_ready(*args, **kwargs):
        raise AnalysisServiceError("没有有效接口")
    monkeypatch.setattr(WorkbenchAnalysisService, "ensure_analysis_ready", not_ready)
    assert client.post("/api/workbench/analysis", json={**body, "action": "all"}).status_code == 400
    assert engine.get_status() == Engine.Status.IDLE
    assert client.get("/api/workbench/analysis").json() == {"job": None}


def test_default_jobs_keep_immediate_cancel_and_cooperative_jobs_run_cleanup():
    async def scenario():
        manager = JobManager()
        ordinary = manager.create("ordinary")
        async def ordinary_worker(job):
            await asyncio.sleep(1)
        await manager.run(ordinary.id, ordinary_worker)
        assert manager.cancel(ordinary.id)
        assert ordinary.status == JobStatus.CANCELLED
        assert "cancel_requested" not in ordinary.snapshot()
        cooperative = manager.create("cooperative", cooperative_cancel=True)
        cleaned = []
        async def cleanup(job):
            cleaned.append(job.cancel_event.is_set())
        await manager.run(cooperative.id, cleanup)
        assert manager.cancel(cooperative.id)
        assert cooperative.status == JobStatus.RUNNING
        assert cooperative.snapshot()["cancel_requested"]
        await asyncio.sleep(0)
        assert cooperative.status == JobStatus.CANCELLED and cleaned == [True]
        manager.shutdown()
    asyncio.run(scenario())


def test_event_loop_shutdown_waits_for_actual_worker_before_releasing_engine(workbench, monkeypatch):
    from starlette.requests import Request
    from api.routes.workbench import AnalysisRequest, start_analysis
    client, _, repository, engine = workbench
    original = repository.load()
    started, shutdown_started, inspected, finish = (threading.Event() for _ in range(4))
    observations = []
    def load(self, config, scope):
        started.set()
        assert finish.wait(5)
        return [], "停机语料"
    monkeypatch.setattr(WorkbenchAnalysisService, "load_scope_items", load)
    body = AnalysisRequest(**_body(client))
    app = client.app
    app.state.jobs = JobManager()
    request = Request({"type": "http", "app": app})
    async def scenario():
        await start_analysis(request, body)
        while not started.is_set():
            await asyncio.sleep(0.001)
        shutdown_started.set()
    def run_loop():
        asyncio.run(scenario())
    def observe():
        assert shutdown_started.wait(3)
        deadline = time.monotonic() + 3
        job = app.state.jobs.list()[0]
        while not job.cancel_event.is_set() and time.monotonic() < deadline:
            time.sleep(0.001)
        observations.append((job.cancel_event.is_set(), engine.get_status(), job.result["worker_active"]))
        inspected.set()
    runner = threading.Thread(target=run_loop)
    inspector = threading.Thread(target=observe)
    try:
        runner.start()
        inspector.start()
        assert inspected.wait(4)
        assert observations == [(True, Engine.Status.TESTING, True)]
    finally:
        finish.set()
        runner.join(5)
        inspector.join(5)
    assert not runner.is_alive() and not inspector.is_alive()
    assert engine.get_status() == Engine.Status.IDLE
    assert repository.load() == original
    job = app.state.jobs.list()[0]
    assert job.status == JobStatus.CANCELLED and not job.result["worker_active"]


def test_failed_draft_write_does_not_pollute_disk_or_runtime(workbench, monkeypatch):
    client, config, repository, engine = workbench
    original = repository.load()
    runtime = copy.deepcopy(config.renpy_workbench_generated_character_drafts)
    def fail_write(self, project):
        raise OSError("模拟磁盘写入失败")
    monkeypatch.setattr(ProjectAssetsRepository, "_write_project_unlocked", fail_write)
    job = _finish(client, _start(client)["id"])
    assert job["status"] == "failed" and "模拟磁盘写入失败" in job["error"]
    assert repository.load() == original
    assert config.renpy_workbench_generated_character_drafts == runtime
    assert engine.get_status() == Engine.Status.IDLE



def test_scan_real_project_reads_script_and_persists_only_candidate_drafts(workbench, monkeypatch):
    from module.File.FileManager import FileManager
    client, config, repository, engine = workbench
    script = Path(config.renpy_game_folder) / "script.rpy"
    script.write_text(
        "define e = Character('Eileen')\n\nlabel start:\n"
        '    e "Welcome to the library."\n'
        '    e "I look after the old books."\n'
        '    e "Let me show you around."\n'
        "    return\n", encoding="utf-8",
    )
    original = client.get("/api/workbench").json()
    read_counts = []
    read_from_path = FileManager.read_from_path
    def observe_read(self):
        project, items = read_from_path(self)
        read_counts.append(len(items))
        return project, items
    def reject_network(*args, **kwargs):
        pytest.fail("本地角色扫描不应请求模型")
    monkeypatch.setattr(WorkbenchAnalysisService, "load_scope_items", _REAL_LOAD_SCOPE)
    monkeypatch.setattr(CharacterScanner, "build_candidates", _REAL_BUILD_CANDIDATES)
    monkeypatch.setattr(FileManager, "read_from_path", observe_read)
    monkeypatch.setattr(TaskRequester, "request", reject_network)
    job = _finish(client, _start(client, scope="full")["id"])
    assert job["status"] == "done", job
    assert job["result"]["source_summary"] == "全项目源码"
    assert read_counts and read_counts[0] >= 3
    snapshot = client.get("/api/workbench").json()
    assert snapshot["characters"] == original["characters"]
    assert snapshot["worldbook"] == original["worldbook"]
    candidate = next(card for card in snapshot["character_drafts"] if card["name"] == "Eileen")
    assert "Welcome to the library." in candidate["sample_lines"]
    persisted = repository.load().analysis_candidates["character_drafts"]
    assert any(card["name"] == "Eileen" for card in persisted)
    assert engine.get_status() == Engine.Status.IDLE
