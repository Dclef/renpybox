"""词库 / 禁翻 API：导入导出、统计、翻译 mock、忙/取消/项目切换。"""
from __future__ import annotations

import base64
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.jobs import JobManager
from api.routes.jobs import router as jobs_router
from api.routes.lexicon import router
from module.Config import Config
from module.Engine.Engine import Engine
from module.Tool import LexiconOps


@pytest.fixture
def lexicon_app(tmp_path, monkeypatch):
    project = tmp_path / "game_project"
    game = project / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text(
        'define e = Character("Eileen")\nlabel start:\n    e "Hi [player_name]"\n',
        encoding="utf-8",
    )
    config = Config()
    config.renpy_project_path = str(project)
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(game / "tl" / "chinese")
    config.input_folder = str(game)
    config.output_folder = str(tmp_path / "out")
    (tmp_path / "out").mkdir()
    config.source_language = "EN"
    config.target_language = "ZH"
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    app = FastAPI()
    app.state.config = config
    app.state.jobs = JobManager()
    app.include_router(router)
    app.include_router(jobs_router)
    with TestClient(app) as client:
        yield client, config, engine, project, game
        app.state.jobs.shutdown()


def _finish(client, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "failed", "cancelled"} and not (job.get("result") or {}).get(
            "worker_active"
        ):
            return job
        time.sleep(0.01)
    pytest.fail(f"任务未结束：{job}")


def test_excel_import_export_roundtrip(lexicon_app):
    client, *_ = lexicon_app
    data = LexiconOps.export_glossary_excel_bytes(
        [{"src": "A", "dst": "甲", "type": "角色", "comment": ""}]
    )
    response = client.post(
        "/api/lexicon/excel/import",
        json={
            "kind": "glossary",
            "content_base64": base64.b64encode(data).decode("ascii"),
            "filename": "g.xlsx",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 1
    assert body["rows"][0]["src"] == "A"

    export = client.post(
        "/api/lexicon/excel/export",
        json={"kind": "glossary", "rows": body["rows"]},
    )
    assert export.status_code == 200
    assert export.json()["filename"] == "glossary.xlsx"
    assert export.json()["media_type"].startswith("application/")


def test_excel_invalid_schema(lexicon_app):
    client, *_ = lexicon_app
    response = client.post(
        "/api/lexicon/excel/import",
        json={"kind": "glossary", "content_base64": base64.b64encode(b"not-xlsx").decode()},
    )
    assert response.status_code == 400

    response = client.post("/api/lexicon/excel/export", json={"kind": "preserve", "rows": "bad"})
    assert response.status_code == 422


def test_statistics_with_mocked_cache_texts(lexicon_app, monkeypatch):
    client, _, engine, *_ = lexicon_app
    monkeypatch.setattr(
        "module.Tool.LexiconOps.load_counted_source_texts",
        lambda config: ("Hello Alice", "Alice walks"),
    )
    response = client.post(
        "/api/lexicon/statistics",
        json={
            "kind": "glossary",
            "rows": [{"src": "Alice", "dst": "爱丽丝", "case_sensitive": False}],
            "project_key": "",
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["counts"] == [2]
    assert job["result"]["counted_item_total"] == 2
    assert job["result"]["kind"] == "glossary"
    assert engine.get_status() == Engine.Status.IDLE
    assert client.get("/api/lexicon").json()["job"]["id"] == job["id"]


def test_translate_fast_mocked_and_confirm_required(lexicon_app, monkeypatch):
    client, _, engine, *_ = lexicon_app
    response = client.post(
        "/api/lexicon/glossary/translate",
        json={
            "mode": "fast",
            "rows": [{"src": "Hi", "dst": ""}],
            "engine": "bing",
            "confirm": False,
        },
    )
    assert response.status_code == 400

    monkeypatch.setattr(
        "module.Tool.LexiconOps.translate_glossary_fast",
        lambda tasks, source_lang, target_lang, engine="bing": [(tasks[0][0], "你好")],
    )
    response = client.post(
        "/api/lexicon/glossary/translate",
        json={
            "mode": "fast",
            "rows": [{"src": "Hi", "dst": ""}],
            "engine": "bing",
            "confirm": True,
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["results"] == [[0, "你好"]]
    assert engine.get_status() == Engine.Status.IDLE


def test_translate_llm_mocked_task_requester(lexicon_app, monkeypatch):
    client, config, *_ = lexicon_app
    config.platforms = [
        {
            "id": 0,
            "name": "mock",
            "api_format": "OpenAI",
            "api_url": "http://127.0.0.1",
            "api_key": "x",
            "model": "m",
        }
    ]
    config.activate_platform = 0

    class FakeRequester:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, messages, response_shape="none"):
            return False, None, '{"0": "译"}', None, None

    monkeypatch.setattr("module.Engine.TaskRequester.TaskRequester", FakeRequester)
    monkeypatch.setattr(
        "module.PromptBuilder.PromptBuilder.generate_prompt",
        lambda self, srcs, *a, **k: ([{"role": "user", "content": "x"}], None),
    )
    response = client.post(
        "/api/lexicon/glossary/translate",
        json={
            "mode": "llm",
            "rows": [{"src": "Hi", "dst": ""}],
            "confirm": True,
        },
    )
    assert response.status_code == 200, response.text
    job = _finish(client, response.json()["job"]["id"])
    assert job["status"] == "done"
    assert job["result"]["results"][0][1] == "译"


def test_busy_engine_and_project_switch(lexicon_app):
    client, config, engine, *_ = lexicon_app
    assert engine.try_set_status(Engine.Status.IDLE, Engine.Status.TRANSLATING)
    response = client.post(
        "/api/lexicon/statistics",
        json={"kind": "preserve", "rows": [{"src": "[x]"}], "project_key": ""},
    )
    assert response.status_code == 409
    engine.release_status(Engine.Status.TRANSLATING)

    response = client.post(
        "/api/lexicon/statistics",
        json={"kind": "preserve", "rows": [{"src": "[x]"}], "project_key": "other-project"},
    )
    assert response.status_code == 409


def test_classify_and_preserve_rescan(lexicon_app):
    client, *_ = lexicon_app
    response = client.post(
        "/api/lexicon/glossary/classify",
        json={"rows": [{"src": "dark forest", "type": ""}]},
    )
    assert response.status_code == 200
    assert response.json()["kw_count"] >= 1

    response = client.post(
        "/api/lexicon/preserve/rescan-variables",
        json={"confirm": False},
    )
    assert response.status_code == 400

    response = client.post(
        "/api/lexicon/preserve/rescan-variables",
        json={"confirm": True},
    )
    assert response.status_code == 200, response.text
    body = _finish(client, response.json()["job"]["id"])["result"]
    assert any(row["src"] == "[player_name]" for row in body["rows"])
    assert body["enabled"] is True


def test_scan_characters_sync(lexicon_app):
    client, *_ = lexicon_app
    response = client.post("/api/lexicon/glossary/scan-characters", json={"confirm": True})
    assert response.status_code == 200, response.text
    body = _finish(client, response.json()["job"]["id"])["result"]
    assert any(item.get("src") == "Eileen" for item in body.get("new_entries", []))
