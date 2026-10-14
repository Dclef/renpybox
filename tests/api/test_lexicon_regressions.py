"""词表API安全回归；项目、缓存和网络均使用临时替身。"""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes.jobs import router as jobs_router
from api.routes import lexicon
from module.Config import Config
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import RenpyProjectPaths


@pytest.fixture
def app_context(tmp_path, monkeypatch):
    project = tmp_path / "project"
    game = project / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text('define e = Character("Alice")\n"Hello [player]"', encoding="utf-8")
    config = Config()
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(game / "tl" / "chinese")
    config.input_folder = str(game)
    config.output_folder = str(tmp_path / "output")
    (tmp_path / "output").mkdir()
    config.text_preserve_data = [{"src": "[keep]", "comment": "保留"}]
    config.text_preserve_enable = True
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    monkeypatch.setattr(Config, "save", lambda self, **kwargs: None)
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.include_router(lexicon.router)
    app.include_router(jobs_router)
    with TestClient(app) as client:
        yield client, config, engine, app
        app.state.jobs.shutdown()


def finish(client, identifier):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{identifier}").json()
        if job["status"] in {"done", "failed", "cancelled"} and not (job.get("result") or {}).get("worker_active"):
            return job
        time.sleep(0.01)
    pytest.fail("任务未收尾")


def body(config):
    return {"project_key": RenpyProjectPaths.from_config(config).project_key, "confirm": True}


@pytest.mark.parametrize("endpoint", ["glossary/scan-characters", "preserve/rescan-variables"])
@pytest.mark.parametrize("busy", ["translation", "barrier", "single"])
def test_scans_obey_engine_barrier_and_single_task(app_context, endpoint, busy):
    client, config, engine, _ = app_context
    if busy == "translation":
        engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
    elif busy == "barrier":
        engine.set_stop_barrier(True)
    else:
        assert engine.try_begin_single_task()
    response = client.post(f"/api/lexicon/{endpoint}", json=body(config))
    assert response.status_code == 409
    assert config.text_preserve_data == [{"src": "[keep]", "comment": "保留"}]


def test_preserve_save_failure_keeps_live_rules(app_context, monkeypatch):
    client, config, _, _ = app_context

    def fail_save(self, *, strict=False, **kwargs):
        if strict:
            raise OSError("模拟保存失败")

    monkeypatch.setattr(Config, "save", fail_save)
    response = client.post("/api/lexicon/preserve/rescan-variables", json=body(config))
    if response.status_code == 200 and "job" in response.json():
        assert finish(client, response.json()["job"]["id"])["status"] == "failed"
    else:
        assert response.status_code >= 400
    assert config.text_preserve_data == [{"src": "[keep]", "comment": "保留"}]
    assert config.text_preserve_enable is True


def test_candidate_scan_switch_does_not_write_either_project(app_context, monkeypatch, tmp_path):
    client, config, _, _ = app_context
    entered, release = threading.Event(), threading.Event()
    writes = []

    def slow_scan(**kwargs):
        entered.set()
        assert release.wait(4)
        return {"entries": [{"source": "Alice", "target": "", "count": 1}], "warnings": []}

    class Repo:
        has_storage = True
        def __init__(self, current):
            self.output_folder = current.output_folder
        def load(self, current):
            return SimpleNamespace(assets=SimpleNamespace(glossary=[], revision=0), analysis_candidates={"items": [], "glossary_metadata": {}})
        def merge_analysis_terms(self, entries):
            writes.append(self.output_folder)
            return {"items": [{"record_id": "new", "source": "Alice", "target": ""}]}

    monkeypatch.setattr(lexicon, "extract_glossary_candidates", slow_scan)
    monkeypatch.setattr(lexicon, "_repository", lambda current: Repo(current))
    try:
        response = client.post("/api/lexicon/glossary/scan-candidates", json=body(config))
        assert response.status_code == 200, response.text
        identifier = response.json()["job"]["id"]
        assert entered.wait(2)
        other_game = tmp_path / "other" / "game"
        other_game.mkdir(parents=True)
        config.renpy_project_path = str(other_game.parent)
        config.renpy_game_folder = str(other_game)
        config.renpy_tl_folder = str(other_game / "tl" / "chinese")
        config.input_folder = str(other_game)
        config.output_folder = str(tmp_path / "other-output")
        release.set()
        job = finish(client, identifier)
        assert job["status"] == "failed"
        assert writes == [], "项目切换后不可持久化旧扫描结果"
    finally:
        release.set()


def test_scan_candidate_ids_only_cover_returned_rows(app_context, monkeypatch):
    client, config, _, _ = app_context
    monkeypatch.setattr(lexicon, "extract_glossary_candidates", lambda **kwargs: {"entries": [{"source": "Alice", "target": "", "count": 1}], "warnings": []})

    class Repo:
        has_storage = True
        output_folder = config.output_folder
        def load(self, current):
            return SimpleNamespace(assets=SimpleNamespace(glossary=[], revision=0), analysis_candidates={"items": [], "glossary_metadata": {}})
        def merge_analysis_terms(self, entries):
            return {"items": [{"record_id": "new", "source": "Alice", "target": ""}, {"record_id": "late-hidden", "source": "Bob", "target": ""}]}

    monkeypatch.setattr(lexicon, "_repository", lambda current: Repo())
    response = client.post("/api/lexicon/glossary/scan-candidates", json=body(config))
    assert response.status_code == 200, response.text
    result = finish(client, response.json()["job"]["id"])["result"]
    rows = result.get("entries", result.get("rows", []))
    displayed_ids = {row.get("record_id") for row in rows if row.get("candidate")}
    assert "new" in displayed_ids, "新候选须携带持久化后的稳定ID"
    assert set(result["candidate_ids"]) <= displayed_ids, "不可消费未展示的晚到候选"


def test_fast_translation_all_originals_is_not_success(app_context, monkeypatch):
    client, config, _, _ = app_context
    monkeypatch.setattr(lexicon.LexiconOps, "translate_glossary_fast", lambda tasks, **kwargs: [(index, src) for index, src in tasks])
    response = client.post("/api/lexicon/glossary/translate", json={**body(config), "mode": "fast", "rows": [{"src": "Alice", "dst": ""}]})
    assert response.status_code == 200, response.text
    job = finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed", "网络失败保留原文不能宣称翻译完成"

def test_cancel_waits_for_worker_and_keeps_finished_translation_batches(app_context, monkeypatch):
    client, config, engine, _ = app_context
    entered, release = threading.Event(), threading.Event()
    calls = []

    def slow_translate(tasks, **kwargs):
        calls.append(len(tasks))
        entered.set()
        assert release.wait(4)
        return [(index, "译文" + src) for index, src in tasks]

    monkeypatch.setattr(lexicon.LexiconOps, "translate_glossary_fast", slow_translate)
    rows = [{"src": f"Name{i}", "dst": ""} for i in range(31)]
    try:
        response = client.post("/api/lexicon/glossary/translate", json={**body(config), "mode": "fast", "rows": rows})
        identifier = response.json()["job"]["id"]
        assert entered.wait(2)
        assert client.post(f"/api/jobs/{identifier}/cancel").status_code == 200
        running = client.get(f"/api/jobs/{identifier}").json()
        assert running["result"]["worker_active"] is True
        assert engine.get_status() == Engine.Status.TESTING
        release.set()
        job = finish(client, identifier)
    finally:
        release.set()
    assert job["status"] == "cancelled"
    assert len(job["result"]["results"]) == 30
    assert calls == [30]
    assert engine.get_status() == Engine.Status.IDLE
    assert len(job["result"]["row_snapshots"]) == 31


def test_cancel_variable_scan_keeps_saved_rules(app_context, monkeypatch):
    client, config, engine, _ = app_context
    entered, release = threading.Event(), threading.Event()
    def slow_scan(current, cancel_callback=None):
        entered.set()
        assert release.wait(4)
        if cancel_callback:
            cancel_callback()
        return {"entries": [], "enabled": False, "cleared": True}
    monkeypatch.setattr(lexicon.LexiconOps, "scan_preserve_variables", slow_scan)
    try:
        response = client.post("/api/lexicon/preserve/rescan-variables", json=body(config))
        identifier = response.json()["job"]["id"]
        assert entered.wait(2)
        client.post(f"/api/jobs/{identifier}/cancel")
        assert engine.get_status() == Engine.Status.TESTING
        release.set()
        job = finish(client, identifier)
    finally:
        release.set()
    assert job["status"] == "cancelled"
    assert config.text_preserve_data == [{"src": "[keep]", "comment": "保留"}]
    assert config.text_preserve_enable is True


def test_translation_request_failure_reports_failure_without_result(app_context, monkeypatch):
    client, config, _, _ = app_context
    def fail_translate(*args, **kwargs):
        raise OSError("模拟网络中断")
    monkeypatch.setattr(lexicon.LexiconOps, "translate_glossary_fast", fail_translate)
    response = client.post("/api/lexicon/glossary/translate", json={**body(config), "mode": "fast", "rows": [{"src": "Alice", "dst": ""}]})
    job = finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"
    assert job["result"]["results"] == []
    assert job["result"]["failed_count"] == 1
    assert any("网络中断" in warning for warning in job["result"]["warnings"])


def test_post_rejects_stale_output_identity(app_context):
    client, config, _, _ = app_context
    response = client.post("/api/lexicon/statistics", json={**body(config), "output_folder": config.output_folder + "-old", "kind": "preserve", "rows": [{"src": "[player]"}]})
    assert response.status_code == 422 or response.status_code == 409

def test_candidate_scan_keeps_same_source_regex_ids_on_disk(app_context, monkeypatch):
    from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository

    client, config, _, _ = app_context
    monkeypatch.setattr(lexicon, "extract_glossary_candidates", lambda **kwargs: {
        "entries": [
            {"source": "a.b", "regex": False, "target": "字面建议", "count": 2},
            {"source": "a.b", "regex": True, "target": "正则建议", "count": 3},
        ],
        "warnings": [],
    })
    response = client.post("/api/lexicon/glossary/scan-candidates", json={**body(config), "rows": []})
    assert response.status_code == 200, response.text
    result = finish(client, response.json()["job"]["id"])["result"]
    assert [(row["src"], row["dst"], row["regex"]) for row in result["entries"]] == [
        ("a.b", "字面建议", False), ("a.b", "正则建议", True),
    ]
    identifiers = {row["record_id"] for row in result["entries"]}
    assert len(identifiers) == 2
    assert set(result["candidate_ids"]) == identifiers
    state = ProjectAssetsRepository.from_config(config).load(config)
    persisted = state.analysis_candidates["items"]
    assert [(row["source"], row["target"], row["regex"]) for row in persisted] == [
        ("a.b", "字面建议", False), ("a.b", "正则建议", True),
    ]
    assert {row["record_id"] for row in persisted} == identifiers
