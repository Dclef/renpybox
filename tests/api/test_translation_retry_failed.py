"""翻译页「重翻失败项」：只重置失败条目，不启动翻译，运行期间拒绝写缓存。"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import translation
from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheProject import CacheProject
from module.Config import Config
from module.Engine.Engine import Engine
from module.Response.ResponseChecker import ResponseChecker


def _retry_meta() -> dict:
    return {
        CacheItem.TRANSLATION_RETRY_KEY: {
            "schema_version": 1,
            "attempt": 2,
            "reasons": [{"code": "LINE_ERROR_SIMILARITY", "line_indices": [0]}],
        },
    }


def _items() -> list[CacheItem]:
    return [
        # 0 已正常翻译
        CacheItem(src = "Hello", dst = "你好", status = Base.TranslationStatus.TRANSLATED),
        # 1 失败待重试
        CacheItem(src = "Bye", dst = "", status = Base.TranslationStatus.UNTRANSLATED,
                  retry_count = 2, metadata = _retry_meta()),
        # 2 达到阈值被排除
        CacheItem(src = "Boom", dst = "", status = Base.TranslationStatus.EXCLUDED,
                  retry_count = ResponseChecker.RETRY_COUNT_THRESHOLD, metadata = _retry_meta()),
        # 3 旧语义：原译相同，且同时带重试元数据，只能计一次
        CacheItem(src = "Same", dst = "Same", status = Base.TranslationStatus.TRANSLATED,
                  metadata = _retry_meta()),
        # 4 人工译文残留旧元数据，不得清空
        CacheItem(src = "Manual", dst = "手工译文", status = Base.TranslationStatus.TRANSLATED,
                  metadata = _retry_meta()),
        # 5 规则排除，无失败元数据，不得改动
        CacheItem(src = "Rule", dst = "", status = Base.TranslationStatus.EXCLUDED),
        # 6 尚未翻译的普通条目
        CacheItem(src = "Todo", dst = "", status = Base.TranslationStatus.UNTRANSLATED),
    ]


def test_reset_failed_translation_items_counts_once_and_keeps_manual_dst() -> None:
    manager = CacheManager(service = False)
    items = _items()
    manager.set_items(items)

    assert manager.reset_failed_translation_items() == 3

    for index in (1, 2, 3):
        item = items[index]
        assert item.get_status() == Base.TranslationStatus.UNTRANSLATED
        assert item.get_dst() == ""
        assert item.get_retry_count() == 0
        assert CacheItem.TRANSLATION_RETRY_KEY not in item.get_metadata()
    assert items[0].get_dst() == "你好"
    assert items[4].get_dst() == "手工译文"
    assert items[4].get_status() == Base.TranslationStatus.TRANSLATED
    assert items[5].get_status() == Base.TranslationStatus.EXCLUDED
    assert manager.reset_failed_translation_items() == 0


def _save_cache(config: Config) -> None:
    manager = CacheManager(service = False)
    project = CacheProject(id = "p", status = Base.TranslationStatus.TRANSLATED)
    project.set_progress({"line": 3, "total_line": 4, "failed_line_count": 42, "time": 5})
    manager.set_project(project)
    manager.set_items(_items())
    assert manager.save_to_file(project, manager.get_items(), config.output_folder, strict = True)


def _client(config: Config) -> TestClient:
    app = FastAPI()
    app.state.config = config
    app.include_router(translation.router)
    return TestClient(app)


@pytest.mark.parametrize("sqlite", [False, True])
def test_retry_failed_resets_cache_and_refreshes_state(monkeypatch, sqlite) -> None:
    config = Config().load()
    config.cache_use_sqlite = sqlite
    config.save(strict = True)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    emitted: list[tuple] = []
    monkeypatch.setattr(translation, "_emit", lambda event, data: emitted.append((event, data)))
    _save_cache(config)

    with _client(config) as client:
        body = client.post("/api/translation/retry-failed").json()
        assert body["ok"] is True
        assert body["count"] == 3
        assert "继续任务" in body["detail"]

        state = client.get("/api/translation/state").json()
        progress = state["progress"]
        assert state["engine_status"] == "IDLE"
        assert progress["status"] == "TRANSLATING"
        # 已完成 = Hello + Manual；待译 = 3 条重置 + Todo
        assert progress["line"] == 2
        assert progress["total_line"] == 6
        # 仅残留在人工译文上的旧元数据仍计入失败统计
        assert progress["failed_line_count"] == 1

    # 只推送进度，不投递 TRANSLATION_START
    assert [event for event, _ in emitted] == [Base.Event.TRANSLATION_UPDATE]
    assert emitted[0][1]["total_line"] == 6

    reloaded = CacheManager(service = False)
    reloaded.load_from_file(config.output_folder, strict = True)
    statuses = [item.get_status() for item in reloaded.get_items()]
    assert statuses[1:4] == [Base.TranslationStatus.UNTRANSLATED] * 3
    assert reloaded.get_items()[4].get_dst() == "手工译文"


def test_retry_failed_without_failures_returns_detail(monkeypatch) -> None:
    config = Config().load()
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    monkeypatch.setattr(translation, "_emit", lambda event, data: pytest.fail("无重置时不应推送事件"))
    manager = CacheManager(service = False)
    project = CacheProject(id = "p")
    manager.set_project(project)
    manager.set_items([CacheItem(src = "Hello", dst = "你好", status = Base.TranslationStatus.TRANSLATED)])
    assert manager.save_to_file(project, manager.get_items(), config.output_folder, strict = True)

    with _client(config) as client:
        body = client.post("/api/translation/retry-failed").json()

    assert body["ok"] is True
    assert body["count"] == 0
    assert body["detail"]


@pytest.mark.parametrize("busy", ["translating", "stopping", "barrier", "single"])
def test_retry_failed_rejects_busy_engine_without_writing(monkeypatch, busy) -> None:
    config = Config().load()
    engine = Engine()
    if busy == "translating":
        engine.set_status(Engine.Status.TRANSLATING)
    elif busy == "stopping":
        engine.set_status(Engine.Status.STOPPING)
    elif busy == "barrier":
        engine.set_stop_barrier(True)
    else:
        assert engine.try_begin_single_task()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    monkeypatch.setattr(CacheManager, "save_to_file", lambda *a, **k: pytest.fail("忙碌时不得写缓存"))
    monkeypatch.setattr(translation, "_emit", lambda event, data: pytest.fail("忙碌时不得推送事件"))

    with _client(config) as client:
        response = client.post("/api/translation/retry-failed")

    assert response.status_code == 409
    assert response.json()["detail"]
