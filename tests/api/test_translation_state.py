"""翻译页恢复缓存、切换项目与活动任务优先级。"""
from types import SimpleNamespace

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


@pytest.mark.parametrize("sqlite", [False, True])
def test_state_restores_saved_progress_without_loading_items(tmp_path, monkeypatch, sqlite):
    config = Config().load()
    config.cache_use_sqlite = sqlite
    config.save(strict=True)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    manager = CacheManager(service=False)
    progress = {"line": 2, "total_line": 3, "total_input_tokens": 120, "time": 8,
                "recent_items": [{"src": "Hello", "dst": "你好"}]}
    project = CacheProject(id="saved", status=Base.TranslationStatus.TRANSLATING)
    project.set_progress(progress)
    manager.set_project(project)
    manager.set_items([CacheItem(src="Hello", dst="你好", status=Base.TranslationStatus.TRANSLATED)])
    assert manager.save_to_file(project, manager.get_items(), config.output_folder, strict=True)
    monkeypatch.setattr(CacheManager, "load_from_file", lambda *args, **kwargs: pytest.fail("状态读取不得载入全量译文"))
    app = FastAPI()
    app.state.config = config
    app.include_router(translation.router)
    with TestClient(app) as client:
        body = client.get("/api/translation/state").json()
        assert body["progress_source"] == "cache"
        assert body["progress_error"] == ""
        assert body["engine_status"] == "IDLE"
        assert body["progress"]["line"] == 2
        assert body["progress"]["recent_items"] == progress["recent_items"]
        assert body["progress"]["total_input_tokens"] == 120
        engine.translator = SimpleNamespace(extras={"line": 9}, _active_cache_output_folder=config.output_folder)
        engine.set_status(Engine.Status.TRANSLATING)
        body = client.get("/api/translation/state").json()
        assert body["progress_source"] == "runtime"
        assert body["progress"] == {"line": 9}
        engine.set_status(Engine.Status.IDLE)
        config.output_folder = str(tmp_path / "another")
        body = client.get("/api/translation/state").json()
        assert body["progress"] == {}
        assert body["progress_source"] == "none"
        assert not (tmp_path / "another").exists()


def test_state_distinguishes_broken_cache_from_new_task(tmp_path, monkeypatch):
    config = Config().load()
    folder = tmp_path / "output" / "cache"
    folder.mkdir(parents=True)
    (folder / "project.json").write_text("broken", encoding="utf-8")
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: Engine()))
    app = FastAPI()
    app.state.config = config
    app.include_router(translation.router)
    with TestClient(app) as client:
        body = client.get("/api/translation/state").json()
    assert body["progress"] == {}
    assert body["progress_error"].startswith("缓存进度读取失败")
