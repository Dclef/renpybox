"""术语/人名入口：真实走 Agent 通道，失败不回退规则，且不破坏已有词库。"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes import lexicon
from api.routes.jobs import router as jobs_router
from module.Config import Config
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import RenpyProjectPaths


@pytest.fixture(autouse=True)
def _isolated_extraction_checkpoints(tmp_path_factory, monkeypatch):
    root = tmp_path_factory.mktemp('extraction-checkpoints')
    monkeypatch.setattr('module.Extract.ExtractionCheckpoint.default_checkpoint_root', lambda: root)


@pytest.fixture
def app_context(tmp_path, monkeypatch):
    project = tmp_path / "project"
    game = project / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text(
        'define e = Character("Alice")\nlabel start:\n    e "Hello [player]"\n',
        encoding = "utf-8",
    )
    config = Config()
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(game / "tl" / "chinese")
    config.input_folder = str(game)
    config.output_folder = str(tmp_path / "output")
    (tmp_path / "output").mkdir()
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
        if job["status"] in {"done", "failed", "cancelled"} and not (
            job.get("result") or {}
        ).get("worker_active"):
            return job
        time.sleep(0.01)
    pytest.fail("任务未收尾")


def request_body(config):
    paths = RenpyProjectPaths.from_config(config)
    return {"project_key": paths.project_key if paths else "", "confirm": True}


def enable_agent(config):
    config.agent_platform = 0
    config.platforms = [
        {
            "id": 0,
            "name": "agent",
            "api_format": "OpenAI",
            "api_url": "http://127.0.0.1",
            "api_key": "x",
            "model": "m",
        }
    ]


def use_repository(monkeypatch, config, state, writes):
    class Repo:
        has_storage = True
        output_folder = config.output_folder

        def load(self, current):
            return state

        def merge_analysis_terms(self, entries):
            writes.append([dict(entry) for entry in entries])
            return {"items": []}

        def replace_analysis_terms(self, entries, removed_record_ids = ()):
            writes.append([dict(entry) for entry in entries])
            return {"items": []}

    monkeypatch.setattr(lexicon, "_repository", lambda current: Repo())


def empty_state():
    return SimpleNamespace(
        assets = SimpleNamespace(glossary = [], revision = 7),
        analysis_candidates = {"items": [], "glossary_metadata": {}},
    )


def test_scan_candidates_fails_without_agent_platform(app_context, monkeypatch):
    client, config, _, _ = app_context
    writes = []
    use_repository(monkeypatch, config, empty_state(), writes)
    config.agent_platform = -1
    calls = []
    monkeypatch.setattr(
        lexicon,
        "extract_glossary_candidates",
        lambda **kwargs: calls.append(kwargs) or {"entries": [], "warnings": []},
    )

    response = client.post("/api/lexicon/glossary/scan-candidates", json=request_body(config))

    assert response.status_code == 200, response.text
    job = finish(client, response.json()["job"]["id"])
    assert job["status"] == "failed"
    assert writes == [], "没有 Agent 接口时不得写入任何候选"
    assert calls == [], "未配置 Agent 接口时必须明确失败，不能带空平台去跑抽取"
    assert "Agent" in job["result"]["message"] or "接口" in job["result"]["message"]


def test_failed_scan_summarizes_repeated_warnings(app_context, monkeypatch):
    client, config, _, _ = app_context
    writes = []
    use_repository(monkeypatch, config, empty_state(), writes)
    enable_agent(config)
    warnings = [f"第 {index} 块未能取得结果：401 Unauthorized" for index in range(30)]
    monkeypatch.setattr(
        lexicon,
        "extract_glossary_candidates",
        lambda **kwargs: {"entries": [], "warnings": warnings, "status": "failed"},
    )

    response = client.post("/api/lexicon/glossary/scan-candidates", json=request_body(config))
    job = finish(client, response.json()["job"]["id"])

    assert job["status"] == "failed"
    message = job["result"]["message"]
    assert len(message) < 200
    assert len(job["error"]) < 200
    assert "另有" in message and "29" in message
    assert job["result"]["warnings"] == warnings
    assert writes == []


def test_scan_candidates_uses_configured_agent_platform(app_context, monkeypatch):
    client, config, _, _ = app_context
    writes = []
    use_repository(monkeypatch, config, empty_state(), writes)
    enable_agent(config)
    captured = {}

    def fake_agent(**kwargs):
        captured.update(kwargs)
        return {
            "entries": [{"src": "East Square", "type": "地名", "count": 2}],
            "warnings": [],
            "status": "completed",
        }

    monkeypatch.setattr(lexicon, "extract_glossary_candidates", fake_agent)

    response = client.post("/api/lexicon/glossary/scan-candidates", json=request_body(config))
    job = finish(client, response.json()["job"]["id"])

    assert job["status"] == "done", job
    assert captured["platform"]["model"] == "m"
    assert writes and writes[0][0]["src"] == "East Square"


def test_scan_candidates_partial_still_writes_and_reports(app_context, monkeypatch):
    client, config, _, _ = app_context
    writes = []
    use_repository(monkeypatch, config, empty_state(), writes)
    enable_agent(config)
    monkeypatch.setattr(
        lexicon,
        "extract_glossary_candidates",
        lambda **kwargs: {
            "entries": [{"src": "Zyx", "type": "角色", "count": 1}],
            "warnings": ["第 2 块未能取得结果"],
            "status": "partial",
            "coverage_complete": False,
            "llm_chunks_total": 2,
            "llm_chunks_success": 1,
        },
    )

    response = client.post("/api/lexicon/glossary/scan-candidates", json=request_body(config))
    job = finish(client, response.json()["job"]["id"])

    assert job["status"] == "done", job
    assert job["result"]["status"] == "partial"
    assert job["result"]["coverage_complete"] is False
    assert writes and writes[0][0]["src"] == "Zyx"


def test_scan_candidates_empty_result_keeps_library(app_context, monkeypatch):
    client, config, _, _ = app_context
    writes = []
    use_repository(monkeypatch, config, empty_state(), writes)
    enable_agent(config)
    monkeypatch.setattr(
        lexicon,
        "extract_glossary_candidates",
        lambda **kwargs: {"entries": [], "warnings": [], "status": "completed"},
    )

    response = client.post("/api/lexicon/glossary/scan-candidates", json=request_body(config))
    job = finish(client, response.json()["job"]["id"])

    assert job["status"] == "done", job
    assert writes == [], "空结果不得清空或改写现有词库"
    assert job["result"]["written"] is False


def test_scan_candidates_does_not_touch_existing_entries(app_context, monkeypatch):
    client, config, _, _ = app_context
    writes = []
    state = SimpleNamespace(
        assets = SimpleNamespace(
            glossary = [SimpleNamespace(source = "Alice", target = "爱丽丝")], revision = 9
        ),
        analysis_candidates = {
            "items": [{"record_id": "r1", "source": "Alice", "target": "爱丽丝"}],
            "glossary_metadata": {},
        },
    )
    use_repository(monkeypatch, config, state, writes)
    enable_agent(config)
    monkeypatch.setattr(
        lexicon,
        "extract_glossary_candidates",
        lambda **kwargs: {
            "entries": [
                {"src": "Alice", "type": "角色", "count": 9},
                {"src": "Bob", "type": "角色", "count": 1},
            ],
            "warnings": [],
            "status": "completed",
        },
    )
    rows = [{"src": "Alice", "dst": "爱丽丝", "comment": "手工", "candidate": False}]

    response = client.post(
        "/api/lexicon/glossary/scan-candidates",
        json={**request_body(config), "rows": rows},
    )
    job = finish(client, response.json()["job"]["id"])

    assert job["status"] == "done", job
    assert writes, "新候选需要写入"
    written = {entry["src"] for entry in writes[0]}
    assert written == {"Bob"}, "已有条目不得被覆盖、重新启用或改注释"


def test_scan_characters_fails_without_agent_platform(app_context, monkeypatch):
    client, config, _, _ = app_context
    writes = []
    use_repository(monkeypatch, config, empty_state(), writes)
    config.agent_platform = -1
    calls = []
    monkeypatch.setattr(
        lexicon,
        "extract_character_candidates",
        lambda **kwargs: calls.append(kwargs) or {"names": [], "warnings": []},
    )

    response = client.post("/api/lexicon/glossary/scan-characters", json=request_body(config))
    job = finish(client, response.json()["job"]["id"])

    assert job["status"] == "failed"
    assert writes == []
    assert calls == [], "未配置 Agent 接口时不能带空平台去跑抽取"


def test_scan_characters_selects_agent_character_type(app_context, monkeypatch):
    client, config, _, _ = app_context
    writes = []
    use_repository(monkeypatch, config, empty_state(), writes)
    enable_agent(config)
    monkeypatch.setattr(
        lexicon,
        "extract_character_candidates",
        lambda **kwargs: {
            "names": ["Zyx"],
            "entries": [{"src": "Zyx"}],
            "warnings": [],
            "status": "completed",
        },
    )

    response = client.post("/api/lexicon/glossary/scan-characters", json=request_body(config))
    job = finish(client, response.json()["job"]["id"])

    assert job["status"] == "done", job
    assert writes and any(entry.get("src") == "Zyx" for entry in writes[0])
    assert all(
        "Agent" in str(entry.get("comment", "")) or "自动提取" in str(entry.get("comment", ""))
        for entry in writes[0]
    )



def test_scan_glossary_publishes_extraction_progress(app_context, monkeypatch):
    """事件必须落到 job.result.extraction_progress，且不污染最终 entries。"""
    client, config, _, _ = app_context
    writes: list = []
    use_repository(monkeypatch, config, empty_state(), writes)
    enable_agent(config)

    def fake_extract(**kwargs):
        callback = kwargs.get("event_callback")
        assert callback is not None, "路由必须把事件回调传下去"
        callback({
            "phase": "extracting",
            "total_chunks": 3,
            "completed_chunks": 1,
            "successful_chunks": 1,
            "failed_chunks": 0,
            "pending_chunks": 2,
            "elapsed_seconds": 1.5,
            "active_chunks": [{"index": 2, "sources": ["script.rpy"], "elapsed_seconds": 0.4}],
            "candidate_count": 1,
            "candidates": [{"src": "Zyx", "type": "角色"}],
        })
        return {
            "names": [],
            "entries": [],
            "warnings": [],
            "status": "completed",
        }

    monkeypatch.setattr(lexicon, "extract_glossary_candidates", fake_extract)

    response = client.post("/api/lexicon/glossary/scan-candidates", json=request_body(config))
    job = finish(client, response.json()["job"]["id"])

    assert job["status"] == "done", job
    progress = (job.get("result") or {}).get("extraction_progress")
    assert isinstance(progress, dict), progress
    assert progress["phase"] == "extracting"
    assert progress["pending_chunks"] == 2
    assert progress["candidates"][0]["src"] == "Zyx"
    # 临时候选只能出现在 extraction_progress，不能写进落盘结构。
    assert writes == [], "仅预览候选时不得产生任何持久化写入"
    assert job["result"]["entries"] == []
    assert job["result"]["written"] is False


def test_scan_glossary_without_events_leaves_progress_absent(app_context, monkeypatch):
    """旧行为兼容：没有事件时 result 里不出现 extraction_progress 字段。"""
    client, config, _, _ = app_context
    writes: list = []
    use_repository(monkeypatch, config, empty_state(), writes)
    enable_agent(config)
    monkeypatch.setattr(
        lexicon,
        "extract_glossary_candidates",
        lambda **kwargs: {"names": [], "entries": [], "warnings": [], "status": "completed"},
    )

    response = client.post("/api/lexicon/glossary/scan-candidates", json=request_body(config))
    job = finish(client, response.json()["job"]["id"])

    assert job["status"] == "done", job
    assert "extraction_progress" not in (job.get("result") or {})
def test_zero_result_returns_current_rows_and_candidate_ids(app_context, monkeypatch):
    client, config, _, _ = app_context
    writes = []
    state = SimpleNamespace(
        assets = SimpleNamespace(glossary = [], revision = 11),
        analysis_candidates = {"items": [{"record_id": "keep-1", "source": "Rose", "target": ""}], "glossary_metadata": {}}
    )
    use_repository(monkeypatch, config, state, writes)
    enable_agent(config)
    monkeypatch.setattr(
        lexicon,
        "extract_glossary_candidates",
        lambda **kwargs: {"entries": [], "warnings": [], "status": "completed"},
    )
    rows = [{"src": "Rose", "dst": "", "candidate": True, "record_id": "keep-1"}]

    response = client.post(
        "/api/lexicon/glossary/scan-candidates",
        json={**request_body(config), "rows": rows},
    )
    job = finish(client, response.json()["job"]["id"])

    assert job["status"] == "done", job
    assert writes == [], "零候选不得写入项目"
    assert job["result"]["entries"] == rows, "必须回传当前完整词表，前端不能清空"
    assert job["result"]["candidate_ids"] == ["keep-1"], "候选标记不能被清空"
    assert job["result"]["written"] is False


def test_existing_candidates_are_not_reenabled(app_context, monkeypatch):
    client, config, _, _ = app_context
    writes = []
    state = SimpleNamespace(
        assets = SimpleNamespace(glossary = [], revision = 12),
        analysis_candidates = {"items": [{"record_id": "r1", "source": "Rose", "target": ""}], "glossary_metadata": {}}
    )
    use_repository(monkeypatch, config, state, writes)
    enable_agent(config)
    monkeypatch.setattr(
        lexicon,
        "extract_glossary_candidates",
        lambda **kwargs: {
            "entries": [{"src": "Rose", "type": "角色", "count": 5}],
            "warnings": [],
            "status": "completed",
        },
    )
    # 用户已把 Rose 禁用并写过备注：重复扫描不得重新启用或改注释。
    rows = [
        {"src": "Rose", "dst": "", "comment": "人工备注", "candidate": True, "enabled": False, "record_id": "r1"}
    ]

    response = client.post(
        "/api/lexicon/glossary/scan-candidates",
        json={**request_body(config), "rows": rows},
    )
    job = finish(client, response.json()["job"]["id"])

    assert job["status"] == "done", job
    assert writes == [], "已存在的候选不得重复写入，否则会重新启用或改注释"
    assert job["result"]["entries"] == rows, "已有行必须原样保留"
    assert job["result"]["candidate_ids"] == ["r1"]


def test_partial_scan_reports_warnings_but_writes(app_context, monkeypatch):
    client, config, _, _ = app_context
    writes = []
    use_repository(monkeypatch, config, empty_state(), writes)
    enable_agent(config)
    monkeypatch.setattr(
        lexicon,
        "extract_glossary_candidates",
        lambda **kwargs: {
            "entries": [],
            "warnings": ["第 3 块未能取得结果"],
            "status": "partial",
            "coverage_complete": False,
        },
    )

    response = client.post(
        "/api/lexicon/glossary/scan-candidates",
        json={**request_body(config), "rows": []},
    )
    job = finish(client, response.json()["job"]["id"])

    assert job["status"] == "done", job
    assert job["result"]["status"] == "partial"
    assert job["result"]["warnings"] == ["第 3 块未能取得结果"]


@pytest.mark.parametrize("endpoint,extractor", [
    ("scan-candidates", "extract_glossary_candidates"),
    ("scan-characters", "extract_character_candidates"),
])
def test_both_entries_publish_temporary_preview_without_early_writes(app_context, monkeypatch, endpoint, extractor):
    import threading
    client, config, _, _ = app_context
    writes, callbacks = [], {}
    use_repository(monkeypatch, config, empty_state(), writes)
    enable_agent(config)
    entered, release = threading.Event(), threading.Event()
    detail = {
        "phase": "extracting", "total_chunks": 3, "completed_chunks": 1,
        "successful_chunks": 1, "failed_chunks": 0, "pending_chunks": 1,
        "elapsed_seconds": 1.2,
        "active_chunks": [{"index": 2, "sources": ["story/chapter.rpy"], "elapsed_seconds": 0.5}],
        "candidate_count": 1,
        "candidates": [{"src": "PreviewOnly", "type": "角色", "evidence": "PreviewOnly said", "source": "story/chapter.rpy", "line": 27}],
    }
    def fake(**kwargs):
        callbacks.update(kwargs)
        kwargs["event_callback"](detail)
        detail["candidates"][0]["src"] = "MUTATED"
        entered.set()
        assert release.wait(4)
        return {"entries": [{"src": "FinalOnly", "type": "角色"}], "names": ["FinalOnly"], "status": "completed", "warnings": []}
    monkeypatch.setattr(lexicon, extractor, fake)
    try:
        started = client.post("/api/lexicon/glossary/" + endpoint, json=request_body(config))
        assert started.status_code == 200
        identifier = started.json()["job"]["id"]
        assert entered.wait(2)
        live = client.get(f"/api/jobs/{identifier}").json()["result"]
        assert live["worker_active"]
        assert writes == [], "preview must never persist before extraction completes"
        assert "entries" not in live
        assert live["extraction_progress"]["candidates"][0]["src"] == "PreviewOnly"
        assert live["extraction_progress"]["candidates"][0]["line"] == 27
        release.set()
        job = finish(client, identifier)
    finally:
        release.set()
    assert job["status"] == "done"
    assert writes and {row["src"] for batch in writes for row in batch} == {"FinalOnly"}
    assert all("evidence" not in row for batch in writes for row in batch)
    assert all(row["src"] != "PreviewOnly" for row in job["result"]["entries"])
    callbacks["event_callback"]({**detail, "candidate_count": 999})
    callbacks["progress_callback"]("LATE", 1)
    again = client.get(f"/api/jobs/{identifier}").json()
    assert again["result"] == job["result"], "finished job must ignore late callbacks"


@pytest.mark.parametrize("endpoint,extractor", [
    ("scan-candidates", "extract_glossary_candidates"),
    ("scan-characters", "extract_character_candidates"),
])
@pytest.mark.parametrize("stop_kind", ["cancel", "project-switch"])
def test_both_entries_ignore_stopped_preview_and_never_write(app_context, monkeypatch, tmp_path, endpoint, extractor, stop_kind):
    import threading
    client, config, _, _ = app_context
    writes = []
    use_repository(monkeypatch, config, empty_state(), writes)
    enable_agent(config)
    entered, release = threading.Event(), threading.Event()
    def fake(**kwargs):
        entered.set()
        assert release.wait(4)
        kwargs["event_callback"]({"phase": "completed", "candidate_count": 9, "candidates": [{"src": "Late"}]})
        kwargs["progress_callback"]("late progress", 99)
        return {"entries": [{"src": "Late", "type": "角色"}], "names": ["Late"], "status": "completed", "warnings": []}
    monkeypatch.setattr(lexicon, extractor, fake)
    try:
        started = client.post("/api/lexicon/glossary/" + endpoint, json=request_body(config))
        identifier = started.json()["job"]["id"]
        assert entered.wait(2)
        if stop_kind == "cancel":
            assert client.post(f"/api/jobs/{identifier}/cancel").status_code == 200
        else:
            config.output_folder = str(tmp_path / "other-output")
        release.set()
        job = finish(client, identifier)
    finally:
        release.set()
    assert job["status"] == ("cancelled" if stop_kind == "cancel" else "failed")
    assert "extraction_progress" not in job["result"]
    assert writes == []
    assert not job["result"].get("written", False)



def test_character_agent_scan_keeps_auto_disabled_and_bracketed_names(app_context, monkeypatch):
    client, config, _, _ = app_context
    old = [
        {"src": "OldAuto", "dst": "保留人工译文", "type": "角色", "info": "角色名 (自动提取)", "comment": "手工备注", "candidate": True, "enabled": False},
        {"src": "Manual", "dst": "译名", "comment": "备注", "type": "角色", "candidate": False},
    ]
    writes = []
    use_repository(monkeypatch, config, empty_state(), writes)
    enable_agent(config)
    def legacy_builder_forbidden(*_args, **_kwargs):
        pytest.fail("Agent route cannot re-run name heuristics or remove old auto rows")
    monkeypatch.setattr(lexicon.LexiconOps, "build_character_scan_entries", legacy_builder_forbidden)
    monkeypatch.setattr(lexicon, "extract_character_candidates", lambda **kwargs: {
        "names": ["OldAuto", "[Archivist]", "Help", "History", "田中"],
        "entries": [], "status": "partial", "warnings": ["chunk timed out"],
        "coverage_complete": False, "llm_chunks_success": 2, "llm_chunks_total": 3,
    })
    response = client.post("/api/lexicon/glossary/scan-characters", json={**request_body(config), "rows": old})
    job = finish(client, response.json()["job"]["id"])
    assert job["status"] == "done", job
    result = job["result"]
    assert result["entries"][:2] == old
    assert result["removed_auto"] == 0
    assert {row["src"] for row in writes[0]} == {"[Archivist]", "Help", "History", "田中"}
    assert result["status"] == "partial" and result["warnings"] == ["chunk timed out"]
    assert not result["coverage_complete"] and result["llm_chunks_success"] == 2



@pytest.mark.parametrize('endpoint,extractor', [
    ('scan-candidates', 'extract_glossary_candidates'), ('scan-characters', 'extract_character_candidates')])
@pytest.mark.parametrize('options', [{}, {'resume': False}, {'resume': True, 'force': True}])
def test_resume_options_reach_both_api_extractors(app_context, monkeypatch, endpoint, extractor, options):
    client, config, _, _ = app_context
    enable_agent(config)
    writes, seen = [], []
    use_repository(monkeypatch, config, empty_state(), writes)
    def fake(**kwargs):
        seen.append(kwargs)
        return {'entries': [], 'names': [], 'status': 'completed', 'warnings': [],
                'checkpoint_status': 'complete', 'resume_available': False,
                'reused_chunks': 3, 'requested_chunks': 2}
    monkeypatch.setattr(lexicon, extractor, fake)
    response = client.post('/api/lexicon/glossary/' + endpoint, json={**request_body(config), **options})
    assert response.status_code == 200
    job = finish(client, response.json()['job']['id'])
    assert job['status'] == 'done'
    assert seen[0]['resume'] is options.get('resume', True)
    assert seen[0]['force'] is options.get('force', False)
    assert seen[0]['checkpoint_enabled'] is True
    assert job['result']['reused_chunks'] == 3 and job['result']['requested_chunks'] == 2
    assert writes == []


@pytest.mark.parametrize('endpoint,extractor', [
    ('scan-candidates', 'extract_glossary_candidates'), ('scan-characters', 'extract_character_candidates')])
def test_scan_api_keeps_old_extractor_signature(app_context, monkeypatch, endpoint, extractor):
    client, config, _, _ = app_context
    enable_agent(config)
    use_repository(monkeypatch, config, empty_state(), [])
    def old(*, config, target_path, platform, progress_callback, cancel_callback, event_callback):
        return {'entries': [], 'names': [], 'status': 'completed', 'warnings': []}
    monkeypatch.setattr(lexicon, extractor, old)
    response = client.post('/api/lexicon/glossary/' + endpoint, json={**request_body(config), 'force': True})
    assert finish(client, response.json()['job']['id'])['status'] == 'done'


def test_checkpoint_capability_snapshot_does_no_scan_or_cache_io(app_context, monkeypatch):
    import module.Extract.ExtractionCheckpoint as checkpoint
    client, _, _, _ = app_context
    def forbidden(*args, **kwargs):
        raise AssertionError('A capability snapshot cannot scan, open a cache or call a model')
    monkeypatch.setattr(lexicon, 'extract_glossary_candidates', forbidden)
    monkeypatch.setattr(lexicon, 'extract_character_candidates', forbidden)
    monkeypatch.setattr(checkpoint, 'default_checkpoint_root', forbidden)
    response = client.get('/api/lexicon')
    assert response.status_code == 200
    assert response.json()['extraction_capabilities'] == {'checkpoint_resume': True}


@pytest.mark.parametrize('endpoint', ['scan-candidates', 'scan-characters'])
@pytest.mark.parametrize('option,value', [('resume', 'true'), ('force', 1), ('checkpoint_root', '/tmp/cache'), ('checkpoint_enabled', False)])
def test_resume_api_rejects_invalid_or_internal_fields(app_context, endpoint, option, value):
    client, config, _, _ = app_context
    response = client.post('/api/lexicon/glossary/' + endpoint, json={**request_body(config), option: value})
    assert response.status_code == 422


@pytest.mark.parametrize('endpoint', ['scan-candidates', 'scan-characters'])
@pytest.mark.parametrize('failure', ['request', 'persist'])
def test_both_real_api_paths_resume_full_cached_results_with_fake_requester(app_context, monkeypatch, endpoint, failure):
    import json
    import module.Extract.GlossaryCandidateService as module
    client, config, _, _ = app_context
    enable_agent(config)
    fail_write = [failure == 'persist']
    class Writes(list):
        def append(self, entries):
            if fail_write[0]:
                fail_write[0] = False
                raise RuntimeError('simulated persistence failure')
            super().append(entries)
    writes, calls = Writes(), []
    use_repository(monkeypatch, config, empty_state(), writes)
    behavior = {'fail': failure == 'request'}
    rows = [{'id': i, 'text': f'Name{i} spoke.', 'source': 'story.rpy', 'line': i + 1} for i in range(3)]
    monkeypatch.setattr(module.GlossaryCandidateService, '_collect_corpus', lambda self: (rows, []))
    monkeypatch.setattr(module.GlossaryCandidateService, '_build_chunks', lambda self, items: [[item] for item in items])
    monkeypatch.setattr(module.GlossaryCandidateService, '_input_byte_limit', lambda self: 1000000)
    monkeypatch.setattr(module.GlossaryCandidateService, 'CHUNK_CONCURRENCY', 1)
    class FakeRequester:
        def __init__(self, config, platform, **kwargs):
            pass
        def request_text(self, messages):
            item = json.loads(messages[0]['content'].split('输入：' + chr(10), 1)[1])
            index = item['id']
            calls.append(index)
            if behavior['fail'] and index == 1:
                return SimpleNamespace(success=False, text='', error_code='fake', error_message='fake')
            return SimpleNamespace(success=True, text=json.dumps({'src': f'Name{index}', 'type': '角色', 'line': index}), error_code='', error_message='')
        def cancel(self):
            pass
        def close(self):
            pass
    monkeypatch.setattr(module, 'AgentRequester', FakeRequester)
    manual = {'src': 'Manual', 'dst': 'Keep', 'info': '人工保留', 'disabled': True}
    response = client.post('/api/lexicon/glossary/' + endpoint, json={**request_body(config), 'rows': [manual]})
    first = finish(client, response.json()['job']['id'])
    if failure == 'persist':
        assert first['status'] == 'failed'
        assert first['result']['extraction_progress']['resume_available']
        previous_rows = [manual]
    else:
        assert first['status'] == 'done'
        assert first['result']['status'] == 'partial' and first['result']['resume_available']
        previous_rows = first['result']['entries']
    assert calls == [0, 1, 2]
    behavior['fail'] = False
    calls.clear()
    response = client.post('/api/lexicon/glossary/' + endpoint, json={**request_body(config), 'rows': previous_rows})
    second = finish(client, response.json()['job']['id'])
    assert second['status'] == 'done'
    result = second['result']
    expected_reused = 3 if failure == 'persist' else 2
    assert calls == ([] if failure == 'persist' else [1])
    assert result['reused_chunks'] == expected_reused and result['requested_chunks'] == 3 - expected_reused
    assert result['checkpoint_status'] == 'complete' and result['resume_available'] is False
    assert result['extraction_progress']['reused_chunks'] == expected_reused
    assert result['extraction_progress']['completed_chunks'] == 3
    assert {entry['src'] for entry in result['entries']} == {'Manual', 'Name0', 'Name1', 'Name2'}
    assert next(entry for entry in result['entries'] if entry['src'] == 'Manual')['dst'] == 'Keep'
    expected_writes = [['Name0', 'Name1', 'Name2']] if failure == 'persist' else [['Name0', 'Name2'], ['Name1']]
    assert [[entry['src'] for entry in batch] for batch in writes] == expected_writes

