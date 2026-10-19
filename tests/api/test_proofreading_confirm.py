"""校对台「确认无误」对任意警告类型生效，并在译文改动后自动失效。"""
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.routes import proofreading
from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheProject import CacheProject
from module.Config import Config
from module.Engine.Engine import Engine
from module.ResultChecker import ResultChecker


def test_confirm_clears_any_warning_type_and_expires_after_edit(tmp_path, monkeypatch):
    """确认无误不能只认 RETRY_THRESHOLD：文本保护失效也该被抹掉，改译文后重新报出。"""
    config = Config()
    config.renpy_project_path = config.renpy_game_folder = config.renpy_tl_folder = ""
    config.input_folder = ""
    config.output_folder = str(tmp_path)
    config.cache_use_sqlite = False
    monkeypatch.setattr(Config, "load", lambda self: config)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    manager = CacheManager(service=False)
    manager.set_project(CacheProject(id="confirm"))
    manager.set_items([CacheItem(
        src="It makes [ffairy] proud!",
        dst="看到[yamiyo]的样子，让[ffairy]感到自豪！",
        file_path="story.rpy", row=3, text_type=CacheItem.TextType.RENPY,
        status=Base.TranslationStatus.TRANSLATED, retry_count=2,
        metadata={CacheItem.TRANSLATION_RETRY_KEY: {"schema_version": 1, "attempt": 2, "reasons": []}},
    )])
    assert manager.save_to_file(manager.get_project(), manager.get_items(), config.output_folder, strict=True)
    app = FastAPI()
    app.state.config = config
    app.include_router(proofreading.router)
    client = TestClient(app)

    data = client.get("/api/proofreading", params={"only_issues": True}).json()
    # 两条告警同时存在：文本保护失效 + 达到重试阈值，且确认入口不再只认后者。
    assert data["matched"] == 1 and data["items"][0]["warnings"] == ["TEXT_PRESERVE", "RETRY_THRESHOLD"], data
    payload = {"cache_token": data["cache_token"], "rows": [{"id": row["id"], "version": row["version"]} for row in data["items"]]}
    assert client.post("/api/proofreading/confirm", json=payload).json()["changed"] == 1
    assert client.get("/api/proofreading", params={"only_issues": True}).json()["matched"] == 0

    saved = CacheManager(service=False)
    saved.load_from_file(config.output_folder, strict=True)
    item = saved.get_items()[0]
    assert item.get_retry_count() == 0
    assert CacheItem.TRANSLATION_RETRY_KEY not in item.get_metadata()
    assert item.get_dst() == "看到[yamiyo]的样子，让[ffairy]感到自豪！"

    # 译文一改，人工确认按摘要自动失效，问题重新上报。
    item.set_dst("结果全都变了，占位符也丢了")
    assert item.get_manual_confirm() is None
    assert [str(value) for value in ResultChecker(config, [item]).check_single_item(item)] == ["TEXT_PRESERVE"]
