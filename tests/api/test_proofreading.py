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


@pytest.mark.parametrize("task", ["polish", "proofread"])
def test_quality_actions_validate_scope_versions_and_restore_reports(tmp_path, monkeypatch, task):
    """使用真实临时缓存验证选中范围、冲突、取消与报告，不调用付费接口。"""
    from module.Engine.Quality.QualityTaskCoordinator import QualityTaskCoordinator

    config = Config()
    config.renpy_project_path = config.renpy_game_folder = config.renpy_tl_folder = ""
    config.input_folder = ""
    config.output_folder = str(tmp_path / "quality")
    config.cache_use_sqlite = False
    monkeypatch.setattr(Config, "load", lambda self: config)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    manager = CacheManager(service=False)
    manager.set_items([
        CacheItem(src="Hello", dst="你好", status=Base.TranslationStatus.TRANSLATED),
        CacheItem(src="Pending", dst="", status=Base.TranslationStatus.UNTRANSLATED),
    ])
    report = {"task_type": "PROOFREADER", "state": "COMPLETED", "total_count": 1,
              "completed_count": 1, "updated_count": 1, "failed_count": 0, "skipped_count": 0}
    manager.set_project(CacheProject(id="quality-fixture", extras={"proofreading_progress": report}))
    manager.save_to_file(manager.get_project(), manager.get_items(), config.output_folder, strict=True)
    calls = []

    def start(runtime, all_items, selected):
        calls.append((runtime.output_folder, [item.get_src() for item in selected]))
        return engine.try_set_status(Engine.Status.IDLE, Engine.Status.QUALITY)

    def cancel():
        return engine.release_status(Engine.Status.QUALITY)

    active = SimpleNamespace(as_dict=lambda: {"error_type_counts": {"ACTIVE": 3}})
    coordinator = SimpleNamespace(start_polishing=start, start_proofreading=start, cancel=cancel, get_progress=lambda: active)
    monkeypatch.setattr(QualityTaskCoordinator, "get", classmethod(lambda cls: coordinator))
    app = FastAPI()
    app.state.config = config
    app.include_router(proofreading.router)
    client = TestClient(app)
    data = client.get("/api/proofreading").json()
    assert data["quality_reports"] == [report]
    assert client.get("/api/proofreading/report").json()["error_type_counts"]["ACTIVE"] == 3
    body = {"cache_token": data["cache_token"], "task": task, "ids": [0, 1, 0],
            "rows": [{"id": row["id"], "version": row["version"]} for row in data["items"]]}
    assert client.post("/api/proofreading/quality", json={**body, "cache_token": "0" * 64}).status_code == 409
    assert client.post("/api/proofreading/quality", json={**body, "rows": [{"id": 0, "version": "0" * 64}, body["rows"][1]]}).status_code == 409
    assert client.post("/api/proofreading/quality", json={**body, "rows": body["rows"][:1]}).status_code == 400
    engine.set_stop_barrier(True)
    assert client.post("/api/proofreading/quality", json=body).status_code == 409
    engine.set_stop_barrier(False)
    engine.try_begin_single_task()
    assert client.post("/api/proofreading/quality", json=body).status_code == 409
    engine.end_single_task()
    assert calls == []
    # 待自动保存的翻译结果优先落盘，旧页面不能把它作为旧译文送去润色。
    runtime_cache = CacheManager(service=False)
    runtime_cache.load_from_file(config.output_folder, strict=True)
    runtime_cache.get_items()[0].set_dst("刚完成的翻译")
    runtime_cache.require_save_to_file(config.output_folder)
    engine.translator = SimpleNamespace(cache_manager=runtime_cache, _active_cache_output_folder=config.output_folder)
    original_save = runtime_cache.save_to_file
    monkeypatch.setattr(runtime_cache, "save_to_file", lambda *args, **kwargs: False)
    assert client.post("/api/proofreading/quality", json=body).status_code == 500
    assert calls == []
    monkeypatch.setattr(runtime_cache, "save_to_file", original_save)
    assert client.post("/api/proofreading/quality", json=body).status_code == 409
    manager.load_from_file(config.output_folder, strict=True)
    assert manager.get_items()[0].get_dst() == "刚完成的翻译"
    assert runtime_cache.require_flag is False
    data = client.get("/api/proofreading").json()
    body["rows"] = [{"id": row["id"], "version": row["version"]} for row in data["items"]]
    response = client.post("/api/proofreading/quality", json=body)
    assert response.status_code == 200
    assert response.json() == {"ok": True, "accepted": 1, "skipped": 1, "task": task}
    assert calls == [(config.output_folder, ["Hello"])]
    assert client.get("/api/proofreading").json()["readonly"] is True
    assert client.post("/api/proofreading/quality", json=body).status_code == 409
    assert client.post("/api/proofreading/quality/cancel").status_code == 200
    assert client.post("/api/proofreading/quality/cancel").status_code == 409
    assert client.get("/api/proofreading").json()["readonly"] is False
    # 原有仅 ids 调用方保持兼容。
    body.pop("rows")
    assert client.post("/api/proofreading/quality", json={**body, "ids": [-1]}).status_code == 400
    assert client.post("/api/proofreading/quality", json={**body, "ids": [1]}).status_code == 400
    assert client.post("/api/proofreading/quality", json={**body, "ids": [0]}).status_code == 200
    assert client.post("/api/proofreading/quality/cancel").status_code == 200
    config.output_folder = str(tmp_path / "missing")
    assert client.get("/api/proofreading").status_code == 404


@pytest.mark.parametrize("sqlite", [False, True])
def test_issue_filter_confirm_reset_and_export_preserve_boundaries(tmp_path, monkeypatch, sqlite):
    """覆盖旧版问题筛选、人工确认、重置及先保存再导出的完整边界。"""
    from module.File.FileManager import FileManager
    from module.Response.ResponseChecker import ResponseChecker

    config = Config()
    config.renpy_project_path = config.renpy_game_folder = config.renpy_tl_folder = ""
    config.input_folder = ""
    config.output_folder = str(tmp_path / "output")
    config.cache_use_sqlite = sqlite
    monkeypatch.setattr(Config, "load", lambda self: config)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    manager = CacheManager(service=False)
    manager.set_project(CacheProject(id="parity", extras={"progress": {"fallback_line_count": 2}}))
    manager.set_items([
        CacheItem(src="Hello", dst="你好", file_type=CacheItem.FileType.TXT, file_path="story.txt", status=Base.TranslationStatus.TRANSLATED,
                  retry_count=ResponseChecker.RETRY_COUNT_THRESHOLD, metadata={CacheItem.TRANSLATION_RETRY_KEY: {"reasons": ["FAIL_LINE_COUNT"]}}),
        CacheItem(src="Goodbye", dst="再见", file_type=CacheItem.FileType.TXT, file_path="story.txt", status=Base.TranslationStatus.TRANSLATED),
    ])
    manager.save_to_file(manager.get_project(), manager.get_items(), config.output_folder, strict=True)
    app = FastAPI()
    app.state.config = config
    app.include_router(proofreading.router)
    client = TestClient(app)

    def snapshot():
        data = client.get("/api/proofreading").json()
        return {"cache_token": data["cache_token"], "rows": [{"id": row["id"], "version": row["version"]} for row in data["items"]]}

    issues = client.get("/api/proofreading", params={"only_issues": True}).json()
    assert issues["matched"] == 1
    assert "RETRY_THRESHOLD" in issues["items"][0]["warnings"]
    assert client.get("/api/proofreading", params={"warning": "RETRY_THRESHOLD"}).json()["matched"] == 1
    assert client.get("/api/proofreading", params={"warning": "UNKNOWN"}).status_code == 400
    report = client.get("/api/proofreading/report").json()
    assert report["fallback_count"] == 2 and report["line_mismatch_count"] == 1
    assert report["item_references"][0]["item_index"] == 0
    original = snapshot()
    assert client.post("/api/proofreading/confirm", json=original).json()["changed"] == 1
    assert client.get("/api/proofreading", params={"only_issues": True}).json()["matched"] == 0
    assert client.get("/api/proofreading").json()["items"][0]["dst"] == "你好"
    assert client.post("/api/proofreading/reset", json=original).status_code == 409
    assert client.get("/api/proofreading").json()["items"][1]["dst"] == "再见"

    body = snapshot()
    token = {"cache_token": body["cache_token"]}
    engine.set_stop_barrier(True)
    for route in ("reset", "confirm", "export"):
        assert client.post("/api/proofreading/" + route, json=token if route == "export" else body).status_code == 409
    engine.set_stop_barrier(False)
    assert client.post("/api/proofreading/export", json={"cache_token": "0" * 64}).status_code == 409
    result = client.post("/api/proofreading/export", json=token)
    assert result.status_code == 200, result.text
    written = list(Path(config.output_folder).rglob("*.txt"))
    assert any(path.read_text(encoding="utf-8") == "你好\n再见" for path in written)

    # 保存失败时不能执行写文件；文件导出失败也必须返回错误，并释放引擎。
    with monkeypatch.context() as patch:
        exports = []
        patch.setattr(CacheManager, "save_to_file", lambda *args, **kwargs: False)
        patch.setattr(FileManager, "write_to_path", lambda *args: exports.append(True))
        assert client.post("/api/proofreading/export", json=token).status_code == 500
        assert exports == []
    with monkeypatch.context() as patch:
        def fail(*args):
            raise OSError("fixture 无法写入")
        patch.setattr(FileManager, "write_to_path", fail)
        assert client.post("/api/proofreading/export", json=token).status_code == 500
    assert engine.get_status() == Engine.Status.IDLE
    assert client.post("/api/proofreading/reset", json={**body, "rows": body["rows"][:1]}).json()["changed"] == 1
    data = client.get("/api/proofreading").json()
    assert data["items"][0]["dst"] == "" and data["items"][0]["status"] == "UNTRANSLATED"
    assert data["items"][1]["dst"] == "再见"


@pytest.mark.parametrize("sqlite", [False, True])
def test_pagination_reuses_snapshot_and_checks_only_requested_rows(tmp_path, monkeypatch, sqlite):
    """翻页不重载整库、不重扫问题；磁盘与设置变化必须失效。"""
    from module.ResultChecker import ResultChecker
    config = Config()
    config.renpy_project_path = config.renpy_game_folder = config.renpy_tl_folder = config.input_folder = ""
    config.output_folder = str(tmp_path)
    config.cache_use_sqlite = sqlite
    monkeypatch.setattr(Config, "load", lambda self: config)
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: Engine()))
    manager = CacheManager(service=False)
    manager.set_project(CacheProject(id="paging"))
    manager.set_items([CacheItem(src=f"Hello {index}", dst=f"你好 {index}", status=Base.TranslationStatus.TRANSLATED) for index in range(250)])
    manager.save_to_file(manager.get_project(), manager.get_items(), config.output_folder, strict=True)
    app = FastAPI()
    app.state.config = config
    app.include_router(proofreading.router)
    client = TestClient(app)
    loads, checks = [], []
    original_load = proofreading._load_cache
    def load(config):
        loads.append(True)
        return original_load(config)
    monkeypatch.setattr(proofreading, "_load_cache", load)
    def check(self, item):
        checks.append(item.get_src())
        return []
    monkeypatch.setattr(ResultChecker, "check_single_item", check)
    assert client.get("/api/proofreading").json()["items"][0]["id"] == 0
    assert len(checks) == 50 and len(loads) == 1
    assert client.get("/api/proofreading", params={"page": 2}).json()["items"][0]["id"] == 50
    assert len(checks) == 100 and len(loads) == 1
    client.get("/api/proofreading")
    assert len(checks) == 100 and len(loads) == 1
    manager.get_items()[0].set_dst("外部更新")
    manager.save_to_file(manager.get_project(), manager.get_items(), config.output_folder, strict=True)
    assert client.get("/api/proofreading").json()["items"][0]["dst"] == "外部更新"
    assert len(loads) == 2
    config.glossary_enable = not config.glossary_enable
    client.get("/api/proofreading")
    assert len(loads) == 3


def test_locate_and_retranslate_reuse_old_engine_safely(tmp_path, monkeypatch):
    import threading
    import time
    config = Config()
    config.renpy_project_path = config.renpy_game_folder = config.renpy_tl_folder = config.input_folder = ""
    config.output_folder = str(tmp_path)
    config.cache_use_sqlite = False
    monkeypatch.setattr(Config, "load", lambda self: config)
    monkeypatch.setattr(Config, "get_platform", lambda *args: {"name": "fixture"})
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    manager = CacheManager(service=False)
    manager.set_project(CacheProject(id="retranslate"))
    manager.set_items([
        CacheItem(src="Hello", dst="旧译文", file_path="story.rpy", row=1, status=Base.TranslationStatus.TRANSLATED,
                  extra_field={"renpy": {"pair": {"target_line": 2}}}),
        CacheItem(src="Goodbye", dst="另一行", file_path="story.rpy", row=3, status=Base.TranslationStatus.TRANSLATED),
    ])
    manager.save_to_file(manager.get_project(), manager.get_items(), str(tmp_path), strict=True)
    (tmp_path / "story.rpy").write_text("old\nnew\nend", encoding="utf-8")
    app = FastAPI()
    app.state.config = config
    app.include_router(proofreading.router)
    client = TestClient(app)
    def body():
        data = client.get("/api/proofreading").json()
        return {"cache_token": data["cache_token"], "rows": [{"id": row["id"], "version": row["version"]} for row in data["items"]]}
    payload = body()
    location = client.post("/api/proofreading/locate", json={**payload, "rows": payload["rows"][:1]}).json()
    assert location["row"] == 2 and location["lines"][1]["text"] == "new"
    assert client.post("/api/proofreading/locate", json=payload).status_code == 400
    assert client.post("/api/proofreading/retranslate", json={**payload, "cache_token": "0" * 64}).status_code == 409
    started, release = threading.Event(), threading.Event()
    def translate(items, config, callback, *, should_cancel):
        started.set()
        assert release.wait(5)
        items[0].set_dst("重新翻译")
        callback(items[0], True)
        if not should_cancel():
            callback(items[1], False)
        return 1
    monkeypatch.setattr(engine, "translate_items", translate)
    assert client.post("/api/proofreading/retranslate", json=payload).status_code == 200
    # 线程启动 + 单任务登记需要真实调度。CI 或并行跑全量时机器负载更高，
    # 2 秒会偶发超时（实测同一用例单独跑 3 次全过、全量随机顺序约半数失败），
    # 这里放宽到 10 秒：它只在异常变慢时才多等，正常情况仍是毫秒级返回。
    assert started.wait(10) and engine.has_single_tasks()
    assert client.post("/api/proofreading/reset", json=payload).status_code == 409
    assert client.post("/api/proofreading/retranslate", json=payload).status_code == 409
    assert client.post("/api/proofreading/retranslate/cancel").json()["state"] == "CANCELLING"
    release.set()
    # 等待后台任务真正收尾；同样是「负载高时窗口过窄」的加固，最长 5 秒。
    deadline = time.time() + 5
    state = {"state": "", "updated": 0}
    while time.time() < deadline:
        state = client.get("/api/proofreading/retranslate").json()
        if not engine.has_single_tasks():
            break
        time.sleep(0.01)
    assert state["state"] == "CANCELLED" and state["updated"] == 1, state
    data = client.get("/api/proofreading").json()
    assert [row["dst"] for row in data["items"]] == ["重新翻译", "另一行"]
    assert not engine.has_single_tasks()
    # 不信任缓存内的越界文件路径。
    manager.load_from_file(str(tmp_path), strict=True)
    manager.get_items()[0].set_file_path("../outside.txt")
    manager.save_to_file(manager.get_project(), manager.get_items(), str(tmp_path), strict=True)
    payload = body()
    assert client.post("/api/proofreading/locate", json={**payload, "rows": payload["rows"][:1]}).status_code == 400


def test_issue_filter_returns_incremental_results_and_reuses_checks(tmp_path, monkeypatch):
    config = Config().load()
    monkeypatch.setattr(Config, "load", lambda self: config)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    manager = CacheManager(service=False)
    manager.set_project(CacheProject(id="issues"))
    manager.set_items([CacheItem(src=str(index), dst="译文", status=Base.TranslationStatus.TRANSLATED) for index in range(9)])
    assert manager.save_to_file(manager.get_project(), manager.get_items(), config.output_folder, strict=True)
    app = FastAPI()
    app.state.config = config
    app.include_router(proofreading.router)
    counts = []
    def check(self, item):
        counts.append(item.get_src())
        return [proofreading.WarningType.SIMILARITY] if int(item.get_src()) % 2 else []
    monkeypatch.setattr(proofreading.ResultChecker, "check_single_item", check)
    tick = iter(index * 0.1 for index in range(100))
    # 只替换路由使用的时钟，不影响 HTTP 客户端和其他库。
    monkeypatch.setattr(proofreading, "time", SimpleNamespace(monotonic=lambda: next(tick)))
    with TestClient(app) as client:
        params = {"only_issues": True, "incremental": True}
        first = client.get("/api/proofreading", params=params).json()
        assert first["scan_complete"] is False
        assert 0 < first["checked"] < first["check_total"] == 9
        assert [row["id"] for row in first["items"]] == [1]
        data = first
        for _ in range(10):
            if data["scan_complete"]:
                break
            data = client.get("/api/proofreading", params=params).json()
        assert data["scan_complete"] is True
        assert [row["id"] for row in data["items"]] == [1, 3, 5, 7]
        assert len(counts) == 9
        assert client.get("/api/proofreading", params={**params, "warning": "SIMILARITY"}).json()["matched"] == 4
        assert len(counts) == 9
        assert client.get("/api/proofreading").json()["matched"] == 9
        assert len(counts) == 9


def test_confirm_reuses_warning_scan_without_rescanning(tmp_path, monkeypatch):
    """确认无误后再次打开「仅看问题」，不应把整份缓存从头检查一遍。"""
    config = Config().load()
    monkeypatch.setattr(Config, "load", lambda self: config)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    manager = CacheManager(service=False)
    manager.set_project(CacheProject(id="confirm-reuse"))
    manager.set_items([CacheItem(src=str(index), dst="译文", status=Base.TranslationStatus.TRANSLATED) for index in range(6)])
    assert manager.save_to_file(manager.get_project(), manager.get_items(), config.output_folder, strict=True)
    app = FastAPI()
    app.state.config = config
    app.include_router(proofreading.router)
    counts = []
    def check(self, item):
        counts.append(item.get_src())
        return [proofreading.WarningType.SIMILARITY] if int(item.get_src()) % 2 else []
    monkeypatch.setattr(proofreading.ResultChecker, "check_single_item", check)
    with TestClient(app) as client:
        params = {"only_issues": True}
        before = client.get("/api/proofreading", params=params).json()
        assert before["scan_complete"] is True
        assert [row["id"] for row in before["items"]] == [1, 3, 5]
        assert len(counts) == 6
        target = before["items"][0]
        payload = {
            "cache_token": before["cache_token"],
            "rows": [{"id": target["id"], "version": target["version"]}],
        }
        result = client.post("/api/proofreading/confirm", json=payload)
        assert result.status_code == 200 and result.json()["changed"] == 1
        # 确认操作本身会检查选中的这一行；之后刷新页面不能再新增检查。
        checks_after_confirm = len(counts)
        assert checks_after_confirm == 7
        after = client.get("/api/proofreading", params=params).json()
        assert after["scan_complete"] is True
        assert after["checked"] == after["check_total"] == 6
        assert [row["id"] for row in after["items"]] == [3, 5]
        assert len(counts) == checks_after_confirm


def test_server_side_multiselect_filters_cover_whole_cache(tmp_path, monkeypatch):
    """多选筛选由服务端对整份缓存求值，分页、legacy 参数与术语命中保持兼容。"""
    config = Config()
    config.renpy_project_path = config.renpy_game_folder = config.renpy_tl_folder = config.input_folder = ""
    config.output_folder = str(tmp_path / "filters")
    config.cache_use_sqlite = False
    monkeypatch.setattr(Config, "load", lambda self: config)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    manager = CacheManager(service=False)
    manager.set_project(CacheProject(id="filters"))
    manager.set_items([
        CacheItem(src="alpha", dst="一", file_path="a.rpy", status=Base.TranslationStatus.TRANSLATED),
        CacheItem(src="beta", dst="二", file_path="b.rpy", status=Base.TranslationStatus.POLISHED),
        CacheItem(src="gamma", dst="三", file_path="a.rpy", status=Base.TranslationStatus.TRANSLATED),
        CacheItem(src="delta", dst="", file_path="", status=Base.TranslationStatus.UNTRANSLATED),
        CacheItem(src="epsilon", dst="五", file_path="b.rpy", status=Base.TranslationStatus.TRANSLATED),
        CacheItem(src="zeta", dst="六", file_path="a.rpy", status=Base.TranslationStatus.EXCLUDED),
    ])
    assert manager.save_to_file(manager.get_project(), manager.get_items(), config.output_folder, strict=True)
    warnings_by_src = {"alpha": ["KANA"], "gamma": ["KANA"], "delta": ["SIMILARITY", "GLOSSARY"], "zeta": ["GLOSSARY"]}
    terms_by_src = {"delta": [("狗", "dog")], "zeta": [("猫", "cat")]}

    def check(self, item):
        return [getattr(proofreading.WarningType, name) for name in warnings_by_src.get(item.get_src(), [])]

    monkeypatch.setattr(proofreading.ResultChecker, "check_single_item", check)
    monkeypatch.setattr(proofreading.ResultChecker, "get_failed_glossary_terms",
                        lambda self, item: list(terms_by_src.get(item.get_src(), [])))
    app = FastAPI()
    app.state.config = config
    app.include_router(proofreading.router)
    client = TestClient(app)

    def ids(params):
        response = client.get("/api/proofreading", params=params)
        assert response.status_code == 200, response.text
        return [row["id"] for row in response.json()["items"]]

    # 状态多选按整份缓存匹配，再对匹配结果分页；翻页不回到全量。
    params = [("statuses", "TRANSLATED"), ("statuses", "POLISHED"), ("limit", 2)]
    data = client.get("/api/proofreading", params=params).json()
    assert data["total"] == 6 and data["matched"] == 4
    assert [row["id"] for row in data["items"]] == [0, 1]
    page2 = client.get("/api/proofreading", params=[*params, ("page", 2)]).json()
    assert page2["matched"] == 4
    assert [row["id"] for row in page2["items"]] == [2, 4]
    # legacy 单值参数继续生效，并与多选/搜索做 AND。
    assert ids({"status": "TRANSLATED"}) == [0, 2, 4]
    assert ids({"file_path": "a.rpy"}) == [0, 2, 5]
    assert ids([("files", "a.rpy"), ("files", "b.rpy")]) == [0, 1, 2, 4, 5]
    assert ids({"files": ""}) == [3]  # 空路径代表「未分类」
    assert ids({"query": "EPS"}) == [4]
    assert ids([("statuses", "TRANSLATED"), ("only_issues", "true")]) == [0, 2]
    assert ids([("statuses", "TRANSLATED"), ("files", "b.rpy")]) == [4]
    # 问题类型多选：有告警行按类型命中；NO_WARNING 只命中完全没有告警的行。
    assert ids([("warnings", "KANA")]) == [0, 2]
    assert ids([("warnings", "NO_WARNING")]) == [1, 4]
    assert ids([("warnings", "KANA"), ("warnings", "NO_WARNING")]) == [0, 1, 2, 4]
    assert ids([("warnings", "GLOSSARY")]) == [3, 5]
    assert ids({"warning": "SIMILARITY"}) == [3]
    assert ids([("only_issues", "true")]) == [0, 2, 3, 5]
    # 术语表未生效的行带上词条，术语筛选按词条精确匹配。
    glossary = client.get("/api/proofreading", params=[("warnings", "GLOSSARY")]).json()
    assert [(row["id"], row["glossary_terms"]) for row in glossary["items"]] == [
        (3, [{"src": "狗", "dst": "dog"}]), (5, [{"src": "猫", "dst": "cat"}])]
    assert ids([("terms", "猫\u0000cat")]) == [5]
    assert ids([("terms", "猫\u0000cat"), ("terms", "狗\u0000dog")]) == [3, 5]
    # 不合法值仍按 400 拒绝。
    assert client.get("/api/proofreading", params=[("statuses", "UNKNOWN")]).status_code == 400
    assert client.get("/api/proofreading", params=[("warnings", "UNKNOWN")]).status_code == 400


@pytest.mark.parametrize("sqlite", [False, True])
def test_batch_edit_writes_once_and_only_rechecks_touched_rows(tmp_path, monkeypatch, sqlite):
    """一次保存多行：整批版本校验、只落盘一次，且只让被改的行重新检查。"""
    config = Config()
    config.renpy_project_path = config.renpy_game_folder = config.renpy_tl_folder = ""
    config.input_folder = ""
    config.output_folder = str(tmp_path / "batch")
    config.cache_use_sqlite = sqlite
    monkeypatch.setattr(Config, "load", lambda self: config)
    engine = Engine()
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: engine))
    manager = CacheManager(service=False)
    manager.set_items([
        CacheItem(src="first", dst="第一", file_path="a.rpy", row=1, status=Base.TranslationStatus.TRANSLATED),
        CacheItem(src="second", dst="第二", file_path="a.rpy", row=2, status=Base.TranslationStatus.TRANSLATED),
        CacheItem(src="third", dst="第三", file_path="b.rpy", row=3, status=Base.TranslationStatus.TRANSLATED),
    ])
    manager.set_project(CacheProject(id="batch-fixture", status=Base.TranslationStatus.TRANSLATED))
    manager.save_to_file(manager.get_project(), manager.get_items(), config.output_folder, strict=True)
    app = FastAPI()
    app.state.config = config
    app.include_router(proofreading.router)
    client = TestClient(app)

    # 先跑一轮「仅看问题」，让逐行检查结果进入快照
    first = client.get("/api/proofreading", params={"only_issues": "true"}).json()
    assert first["scan_complete"] is True
    snapshot = app.state.proofreading_snapshot
    assert set(snapshot["warnings"]) == {0, 1, 2}

    rows = [
        {"id": row["id"], "version": row["version"], "dst": row["dst"] + "-改"}
        for row in client.get("/api/proofreading").json()["items"][:2]
    ]
    token = first["cache_token"]

    # 同一行重复提交 → 400
    dup = {"cache_token": token, "rows": [rows[0], dict(rows[0])]}
    assert client.patch("/api/proofreading/items", json=dup).status_code == 400

    # 任一行版本过期 → 整批不写入，磁盘保持原样
    stale = {"cache_token": token, "rows": [rows[0], {**rows[1], "version": "0" * 64}]}
    assert client.patch("/api/proofreading/items", json=stale).status_code == 409
    manager.load_from_file(config.output_folder, strict=True)
    assert [item.get_dst() for item in manager.get_items()] == ["第一", "第二", "第三"]

    # 正常批量保存：一次请求写入两行
    ok = client.patch("/api/proofreading/items", json={"cache_token": token, "rows": rows})
    assert ok.status_code == 200
    assert ok.json()["changed"] == 2
    manager.load_from_file(config.output_folder, strict=True)
    assert [item.get_dst() for item in manager.get_items()] == ["第一-改", "第二-改", "第三"]

    # 快照被复用：未改动的行保留旧检查结论，被改的行作废等待重新检查
    assert app.state.proofreading_snapshot is snapshot
    assert set(snapshot["warnings"]) == {2}
    rescan = client.get("/api/proofreading", params={"only_issues": "true"}).json()
    assert rescan["scan_complete"] is True
    assert engine.get_status() == Engine.Status.IDLE
