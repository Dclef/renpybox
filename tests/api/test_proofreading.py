"""校对台真实 JSON/SQLite 往返与项目、版本、忙碌保护；全部写入临时目录。"""
import sys
from pathlib import Path
from types import SimpleNamespace

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


@pytest.mark.parametrize("sqlite", [False, True])
def test_proofreading_preserves_new_results_and_project_boundaries(tmp_path, monkeypatch, sqlite):
    config = Config()
    config.renpy_project_path = config.renpy_game_folder = config.renpy_tl_folder = ""
    config.input_folder = ""
    config.output_folder = str(tmp_path / "first")
    config.cache_use_sqlite = sqlite
    monkeypatch.setattr(Config, "load", lambda self: config)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    manager = CacheManager(service=False)
    manager.set_items([
        CacheItem(src="Hello [name]", dst="Hello 小猫", file_path="chapter.rpy", row=7, status=Base.TranslationStatus.TRANSLATED),
        CacheItem(src="Another line", dst="hello 世界", file_path="ending.rpy", row=12, status=Base.TranslationStatus.POLISHED),
    ])
    manager.set_project(CacheProject(id="fixture", status=Base.TranslationStatus.TRANSLATED, extras={"custom": "保留"}))
    manager.save_to_file(manager.get_project(), manager.get_items(), config.output_folder, strict=True)
    app = FastAPI()
    app.state.config = config
    app.include_router(proofreading.router)
    client = TestClient(app)

    data = client.get("/api/proofreading", params={"limit": 1, "page": 2}).json()
    assert data["total"] == data["matched"] == 2
    assert data["items"][0]["src"] == "Another line"
    filtered = client.get("/api/proofreading", params={"query": "小猫", "status": "TRANSLATED"}).json()
    assert filtered["matched"] == 1
    assert filtered["files"] == ["chapter.rpy", "ending.rpy"]
    report = client.get("/api/proofreading/report")
    assert report.status_code == 200
    assert report.json()["item_references"] == []
    assert client.get("/api/proofreading", params={"status": "UNKNOWN"}).status_code == 400

    def edit_payload(row, dst, token=None):
        return {"cache_token": token or filtered["cache_token"], "row": {"id": row["id"], "version": row["version"]}, "dst": dst}

    original = filtered["items"][0]
    assert client.patch("/api/proofreading/item", json=edit_payload(original, "你好 [name]")).status_code == 200
    assert client.patch("/api/proofreading/item", json=edit_payload(original, "覆盖旧版本")).status_code == 409
    manager.load_from_file(config.output_folder, strict=True)
    assert manager.get_items()[0].get_dst() == "你好 [name]"
    assert manager.get_project().get_extras()["custom"] == "保留"
    assert engine.get_status() == Engine.Status.IDLE

    current = client.get("/api/proofreading").json()
    replace = {
        "cache_token": current["cache_token"],
        "rows": [{"id": row["id"], "version": row["version"]} for row in current["items"]],
        "find": "hello", "replace": r"字面\1", "case_sensitive": False,
    }
    assert client.post("/api/proofreading/replace", json=replace).json()["changed"] == 1
    assert client.post("/api/proofreading/replace", json=replace).status_code == 409
    replace["find"], replace["replace"] = "你好", "不应部分落盘"
    assert client.post("/api/proofreading/replace", json=replace).status_code == 409
    manager.load_from_file(config.output_folder, strict=True)
    assert manager.get_items()[1].get_dst() == r"字面\1 世界"
    assert manager.get_items()[0].get_dst() == "你好 [name]"

    current = client.get("/api/proofreading").json()
    body = edit_payload(current["items"][0], "忙碌覆盖", current["cache_token"])
    engine.set_status(Engine.Status.TRANSLATING)
    assert client.get("/api/proofreading").json()["readonly"] is True
    assert client.patch("/api/proofreading/item", json=body).status_code == 409
    engine.set_status(Engine.Status.IDLE)
    engine.set_stop_barrier(True)
    assert client.patch("/api/proofreading/item", json=body).status_code == 409
    engine.set_stop_barrier(False)
    engine.try_begin_single_task()
    assert client.patch("/api/proofreading/item", json=body).status_code == 409
    engine.end_single_task()

    # 已停止翻译的自动保存仍有新结果时，先落盘并拒绝过期编辑。
    runtime = CacheManager(service=False)
    runtime.load_from_file(config.output_folder, strict=True)
    runtime.get_items()[0].set_dst("刚完成的翻译")
    runtime.require_save_to_file(config.output_folder)
    engine.translator = SimpleNamespace(cache_manager=runtime, _active_cache_output_folder=config.output_folder)
    assert client.patch("/api/proofreading/item", json=body).status_code == 409
    manager.load_from_file(config.output_folder, strict=True)
    assert manager.get_items()[0].get_dst() == "刚完成的翻译"
    current = client.get("/api/proofreading").json()
    assert client.patch("/api/proofreading/item", json=edit_payload(current["items"][0], "人工定稿", current["cache_token"])).status_code == 200
    assert runtime.get_items()[0].get_dst() == "人工定稿"
    assert runtime.require_flag is False

    # 相同条目复制到另一项目，也必须拒绝旧页面的项目令牌。
    config.output_folder = str(tmp_path / "second")
    manager.save_to_file(manager.get_project(), manager.get_items(), config.output_folder, strict=True)
    row = client.get("/api/proofreading").json()["items"][0]
    assert client.patch("/api/proofreading/item", json=edit_payload(row, "跨项目覆盖", current["cache_token"])).status_code == 409
    manager.load_from_file(config.output_folder, strict=True)
    assert manager.get_items()[0].get_dst() == "刚完成的翻译"
