"""API 契约层的无头测试。

不启动 Qt、不需要真实 Ren'Py 项目：
用 TestClient 跑通「配置读写 / 术语表 / 项目路径 / 事件广播 / 任务模型」。

其中项目路径那一条同时验证了完整链路：
    ProjectStore → EventManager.emit → drain（由 lifespan 的 drain_loop 驱动）
    → EventBridge → WebSocket 消息
"""
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fastapi.testclient import TestClient  # noqa: E402

from api.app import create_app  # noqa: E402
from api.jobs import JobManager, JobStatus  # noqa: E402


def _client() -> TestClient:
    return TestClient(create_app())


# ---------- 系统 ----------

def test_health_reports_version_and_python() -> None:
    with _client() as client:
        body = client.get("/health").json()

    assert body["ok"] is True
    assert body["app_version"]
    assert body["python_version"]


def test_version_endpoint() -> None:
    with _client() as client:
        body = client.get("/api/version").json()

    assert body["api_version"] == "1"


# ---------- 配置 ----------

def test_settings_masks_nested_secrets_only() -> None:
    """顶层只按精确字段名判断，嵌套结构里的密钥才脱敏。

    防止误伤：onekey_inject_base_box / token_threshold 这类字段名里
    含 key / token 子串，但不是密钥，必须照常返回。
    """
    with _client() as client:
        client.patch("/api/settings", json = {
            "values": {"platforms": [{"id": 1, "name": "demo", "api_key": "sk-should-not-leak"}]},
            "save": False,
        })

        body = client.get("/api/settings").json()

    values = body["values"]
    # 含key/token 子串的普通字段不被误判
    for name in ("onekey_inject_base_box", "token_threshold", "max_batch_source_tokens"):
        assert name in values, name

    # 嵌套在 platforms 里的 api_key 被脱敏
    platform = next(p for p in values["platforms"] if p.get("id") == 1)
    assert platform["api_key"] == "***"
    assert "sk-should-not-leak" not in json.dumps(values, ensure_ascii = False)


def test_settings_patch_rejects_unknown_field() -> None:
    with _client() as client:
        unknown = client.patch("/api/settings", json = {"values": {"__nope__": 1}})
        assert unknown.status_code == 400

        good = client.patch("/api/settings", json = {"values": {"theme": "Light"}, "save": False})
        assert good.status_code == 200


def test_settings_rejects_secret_field_write() -> None:
    """密钥字段不允许从通用设置接口写入。

    真实 Config 里密钥嵌在 platforms 内，顶层没有 api_key 字段；
    这里用带该字段的 stub 覆盖这条防御分支。
    """
    import dataclasses

    @dataclasses.dataclass
    class StubConfig:
        theme: str = "Dark"
        api_key: str = ""

    with _client() as client:
        client.app.state.config = StubConfig()

        blocked = client.patch("/api/settings", json = {"values": {"api_key": "sk-x"}, "save": False})
        assert blocked.status_code == 403

        listed = client.get("/api/settings").json()
        assert "api_key" not in listed["values"]
        assert "api_key" in listed["masked"]


def test_settings_patch_validates_type() -> None:
    with _client() as client:
        bad = client.patch("/api/settings", json = {"values": {"font_hinting": "yes"}, "save": False})
        assert bad.status_code == 400


# ---------- 术语表 ----------

_ROWS = [
    {"src": "ソyma", "dst": "沙发", "info": "", "regex": False, "case_sensitive": False},
    {"src": "ソyma", "dst": "", "info": "", "regex": False, "case_sensitive": False},
    {"src": "おにぎり", "dst": "饭团", "info": "", "regex": False, "case_sensitive": False},
]


def test_glossary_sync_dedupes_by_src() -> None:
    with _client() as client:
        body = client.post("/api/glossary/sync", json = {"kind": "GLOSSARY", "rows": _ROWS}).json()

    srcs = [r["src"] for r in body["rows"]]
    assert len(srcs) == 2
    # 有译文的那条被保留
    assert any(r["dst"] == "沙发" for r in body["rows"])


def test_glossary_save_and_load_roundtrip() -> None:
    with _client() as client:
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "glossary")

            saved = client.post("/api/glossary/save", json = {
                "kind": "GLOSSARY",
                "rows": _ROWS,
                "path": base,
                "format": "both",
            }).json()
            assert saved["total"] == 2

            json_path = base + ".json"
            assert os.path.isfile(json_path)

            loaded = client.post("/api/glossary/load", json = {
                "kind": "GLOSSARY",
                "path": json_path,
            }).json()
            assert loaded["total"] == 2
            assert any(r["dst"] == "饭团" for r in loaded["rows"])


def test_glossary_load_rejects_missing_file() -> None:
    with _client() as client:
        response = client.post("/api/glossary/load", json = {
            "kind": "GLOSSARY",
            "path": "不存在的文件.json",
        })
        assert response.status_code == 404


def test_glossary_search_finds_keyword() -> None:
    with _client() as client:
        body = client.post("/api/glossary/search", json = {
            "kind": "GLOSSARY",
            "rows": _ROWS,
            "keyword": "饭团",
            "start": -1,
        }).json()

    assert body["index"] == 2


# ---------- 事件广播全链路 ----------

def test_project_path_change_broadcasts_event_over_ws() -> None:
    """ProjectStore发事件 → drain → EventBridge → WS 消息。"""
    with _client() as client:
        with client.websocket_connect("/ws") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"

            with client.websocket_connect("/ws") as observer:
                observer.receive_json()  # hello

                client.post("/api/project/path", json = {
                    "project_path": "/tmp/demo-project",
                    "game_folder": "/tmp/demo-project/game",
                })

                seen = []
                deadline = 30
                while deadline > 0:
                    message = ws.receive_json()
                    seen.append(message)
                    if message.get("type") == "event" and message.get("event") == "PROJECT_CHANGED":
                        break
                    deadline -= 1

            assert any(m.get("event") == "PROJECT_CHANGED" for m in seen), seen


def test_ws_ping_pong() -> None:
    with _client() as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_text(json.dumps({"type": "ping"}))

            message = ws.receive_json()
            assert message["type"] == "pong"


def test_ws_rejects_unknown_command() -> None:
    with _client() as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_text(json.dumps({"type": "nope"}))

            message = ws.receive_json()
            assert message["type"] == "error"


# ---------- 翻译主流程 ----------

def test_translation_state_reports_idle_engine() -> None:
    """空闲引擎的快照：状态为 IDLE，且带出并发上限，供命令栏决定按钮可用性。"""
    with _client() as client:
        body = client.get("/api/translation/state").json()

    assert body["engine_status"] == "IDLE"
    assert body["stop_barrier"] is False
    assert body["single_tasks"] is False
    assert "max" in body["running"]
    assert isinstance(body["progress"], dict)


def test_translation_start_rejects_busy_engine() -> None:
    """引擎忙时不得受理，且不能把 TRANSLATION_START 投进总线。

    这条同时守住「前端连点两次开始」的入口：被拒的请求根本不产生事件。
    """
    from module.Engine.Engine import Engine

    engine = Engine.get()
    engine.set_status(Engine.Status.TRANSLATING)
    try:
        with _client() as client:
            body = client.post("/api/translation/start", json = {"status": "UNTRANSLATED"}).json()

        assert body["accepted"] is False
        assert body["reason"] == "STOPPING"
    finally:
        engine.set_status(Engine.Status.IDLE)


def test_translation_start_rejects_unknown_status() -> None:
    with _client() as client:
        response = client.post("/api/translation/start", json = {"status": "NOT_A_STATUS"})

    assert response.status_code == 400


def test_translation_stop_without_run_conflicts() -> None:
    """空闲时停止必须 409，而不是静默成功让前端以为已停。"""
    with _client() as client:
        response = client.post("/api/translation/stop")

    assert response.status_code == 409


def test_translation_export_requires_output_folder() -> None:
    """没有输出目录时导出要报冲突，而不是把事件投出去让引擎空跑。"""
    import dataclasses

    @dataclasses.dataclass
    class StubConfig:
        output_folder: str = ""

    with _client() as client:
        client.app.state.config = StubConfig()
        response = client.post("/api/translation/export")

    assert response.status_code == 409


def test_translation_start_emits_event_without_starting_engine() -> None:
    """受理 → 事件总线 → drain_loop → EventBridge → WS。

    这是翻译主流程的端到端契约：前端点「开始翻译」后，真正确认线程状态的
    唯一通道就是 WS 上的 TRANSLATION_START。

    这里刻意摘掉真实 Translator 的订阅者：lifespan 里的 ``Engine.get().run()``
    已经建好了它，放行就会真的起线程去读目录、写缓存。这里只验证路由投递。
    """
    from base.Base import Base
    from base.EventManager import EventManager
    from module.Engine.Engine import Engine

    with _client() as client:
        translator = getattr(Engine.get(), "translator", None)
        manager = EventManager.get()
        detached = translator is not None and callable(getattr(translator, "translation_start", None))
        if detached:
            manager.unsubscribe(Base.Event.TRANSLATION_START, translator.translation_start)

        try:
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()  # hello

                client.post("/api/translation/start", json = {
                    "status": "TRANSLATING",
                    "request_id": "req-test-1",
                })

                seen = []
                deadline = 40
                while deadline > 0:
                    message = ws.receive_json()
                    seen.append(message)
                    if message.get("event") == "TRANSLATION_START":
                        break
                    deadline -= 1
        finally:
            if detached:
                translator.subscribe(Base.Event.TRANSLATION_START, translator.translation_start)

    payload = next((m["data"] for m in seen if m.get("event") == "TRANSLATION_START"), None)
    assert payload is not None, seen
    assert payload["request_id"] == "req-test-1"
    assert payload["status"] == "TRANSLATING"
    # 冻结快照只给翻译线程：广播里必须摘掉，否则渲染端收到的是 9KB 的 repr 假结构
    assert "config" not in payload
    # 真实引擎没被驱动起来
    assert Engine.get().get_status() == Engine.Status.IDLE


def test_translation_start_keeps_frozen_config_for_engine() -> None:
    """摘掉广播字段不影响引擎侧：Translator 必须拿到冻结的 Config 实例。

    两条断言对着看：广播里没有 config，总线里的 config 却是可用的对象。
    """
    from base.Base import Base
    from base.EventManager import EventManager
    from module.Engine.Engine import Engine

    with _client() as client:
        translator = getattr(Engine.get(), "translator", None)
        manager = EventManager.get()
        detached = translator is not None and callable(getattr(translator, "translation_start", None))
        if detached:
            manager.unsubscribe(Base.Event.TRANSLATION_START, translator.translation_start)

        captured = {}

        def capture(event, data):
            captured.update(data)

        manager.subscribe(Base.Event.TRANSLATION_START, capture)

        try:
            client.post("/api/translation/start", json = {
                "status": "TRANSLATING",
                "request_id": "req-frozen-1",
            })
            EventManager.drain_all()
        finally:
            manager.unsubscribe(Base.Event.TRANSLATION_START, capture)
            if detached:
                translator.subscribe(Base.Event.TRANSLATION_START, translator.translation_start)

    assert captured.get("request_id") == "req-frozen-1"
    snapshot = captured.get("config")
    assert snapshot is not None
    assert snapshot.input_folder is not None
    assert Engine.get().get_status() == Engine.Status.IDLE


def test_repeated_app_lifespans_keep_one_translator() -> None:
    """反复建 app 不得堆叠 TRANSLATION_START 订阅者。

    事件回调表是类级字典，不退订就会一直留着旧 Translator：一次开始请求
    会唤起多个翻译线程，同时写同一个输出目录。
    """
    from base.Base import Base
    from base.EventManager import EventManager

    for _ in range(3):
        with _client():
            pass

    manager = EventManager.get()
    assert len(manager.event_callbacks.get(Base.Event.TRANSLATION_START, [])) == 1
    assert len(manager.event_callbacks.get(Base.Event.TRANSLATION_STOP, [])) == 1


def test_translation_start_honours_preflight_confirmation() -> None:
    """缺资产时默认拒绝；用户明确「仍然继续」后必须真的受理。

    没有后一条，渲染端的 preflight 弹窗会永远停在那里：用户点了「仍然继续」，
    请求又被原样拒回。默认空配置没有资产，正好覆盖这个分支。
    """
    from base.Base import Base
    from base.EventManager import EventManager
    from module.Engine.Engine import Engine

    with _client() as client:
        manager = EventManager.get()
        translator = getattr(Engine.get(), "translator", None)
        detached = translator is not None and callable(getattr(translator, "translation_start", None))
        if detached:
            manager.unsubscribe(Base.Event.TRANSLATION_START, translator.translation_start)

        seen = []
        capture = lambda event, data: seen.append(data)
        manager.subscribe(Base.Event.TRANSLATION_START, capture)

        try:
            first = client.post("/api/translation/start", json = {"status": "UNTRANSLATED"}).json()
            confirmed = client.post("/api/translation/start", json = {
                "status": "UNTRANSLATED",
                "preflight_confirmed": True,
            }).json()
            EventManager.drain_all()
        finally:
            manager.unsubscribe(Base.Event.TRANSLATION_START, capture)
            if detached:
                translator.subscribe(Base.Event.TRANSLATION_START, translator.translation_start)

    assert first["accepted"] is False
    assert first["reason"] == "ASSETS_MISSING"
    # 只有带确认标记的那次才投进事件总线
    assert confirmed["accepted"] is True
    assert len(seen) == 1
    assert seen[0]["preflight_confirmed"] is True


# ---------- 任务模型 ----------

def test_job_manager_transitions_to_done() -> None:
    import asyncio

    async def scenario() -> None:
        manager = JobManager()
        job = manager.create("demo", total = 3)

        async def worker(j):
            for i in range(3):
                j.done = i + 1
            return {"ok": True}

        await manager.run(job.id, worker)
        await asyncio.sleep(0)

        snapshot = manager.snapshot(job.id)
        assert snapshot["status"] == JobStatus.DONE.value
        assert snapshot["done"] == 3
        assert snapshot["progress"] == 1.0

    asyncio.run(scenario())


def test_job_manager_marks_failure() -> None:
    import asyncio

    async def scenario() -> None:
        manager = JobManager()
        job = manager.create("boom")

        async def worker(j):
            raise ValueError("炸了")

        await manager.run(job.id, worker)
        await asyncio.sleep(0)

        snapshot = manager.snapshot(job.id)
        assert snapshot["status"] == JobStatus.FAILED.value
        assert "炸了" in snapshot["error"]

    asyncio.run(scenario())


def test_job_manager_cancel_running_task() -> None:
    import asyncio

    async def scenario() -> None:
        manager = JobManager()
        job = manager.create("slow")

        async def worker(j):
            await asyncio.sleep(5)
            return "完成"

        await manager.run(job.id, worker)
        assert manager.cancel(job.id) is True

        snapshot = manager.snapshot(job.id)
        assert snapshot["status"] == JobStatus.CANCELLED.value
        # 已终结的任务不能再取消
        assert manager.cancel(job.id) is False

        manager.shutdown()

    asyncio.run(scenario())


def test_job_cancel_stops_running_worker() -> None:
    import asyncio

    async def scenario() -> None:
        manager = JobManager()
        job = manager.create("slow")
        reached = []
        started = asyncio.Event()

        async def worker(j):
            started.set()
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                reached.append("cancelled")
                raise
            reached.append("after")

        await manager.run(job.id, worker)
        await started.wait()
        await asyncio.sleep(0)
        assert manager.cancel(job.id) is True
        await asyncio.sleep(0)
        assert reached == ["cancelled"]
        assert manager.snapshot(job.id)["status"] == JobStatus.CANCELLED.value
        manager.shutdown()

    asyncio.run(scenario())


def test_job_cancel_is_not_overwritten_by_worker_return() -> None:
    import asyncio

    async def scenario() -> None:
        manager = JobManager()
        job = manager.create("slow")

        async def worker(j):
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                return "swallowed"

        await manager.run(job.id, worker)
        assert manager.cancel(job.id) is True
        await asyncio.sleep(0)
        assert manager.snapshot(job.id)["status"] == JobStatus.CANCELLED.value
        manager.shutdown()

    asyncio.run(scenario())


def test_job_run_after_cancel_stays_cancelled() -> None:
    import asyncio

    async def scenario() -> None:
        manager = JobManager()
        job = manager.create("demo")
        called = []

        async def worker(j):
            called.append(j.id)

        assert manager.cancel(job.id) is True
        await manager.run(job.id, worker)
        await asyncio.sleep(0)
        assert called == []
        assert manager.snapshot(job.id)["status"] == JobStatus.CANCELLED.value

    asyncio.run(scenario())


def test_job_progress_is_throttled() -> None:
    import asyncio

    async def scenario() -> None:
        sink = []
        manager = JobManager(publish = sink.append, min_interval = 0.2)
        job = manager.create("demo", total = 100)

        async def worker(j):
            for index in range(100):
                manager.progress(job.id, done = index + 1)

        await manager.run(job.id, worker)
        await asyncio.sleep(0)
        progress = [item for item in sink if item["job"]["status"] == "running" and item["job"]["done"] > 0]
        assert len(progress) <= 2
        assert any(item["job"]["status"] == "done" for item in sink)

    asyncio.run(scenario())


def test_job_publish_payload_is_json_safe() -> None:
    import asyncio

    async def scenario() -> None:
        sink = []
        manager = JobManager(publish = sink.append)
        job = manager.create("demo")

        async def worker(j):
            return {"ok": True}

        await manager.run(job.id, worker)
        await asyncio.sleep(0)
        assert sink
        for item in sink:
            json.dumps(item)
            assert "result" not in item["job"]
            assert "cancel_event" not in item["job"]

    asyncio.run(scenario())


def test_job_snapshot_after_event_wait() -> None:
    import asyncio

    async def scenario() -> None:
        manager = JobManager()
        job = manager.create("wait")

        async def worker(j):
            try:
                await asyncio.wait_for(j.cancel_event.wait(), timeout = 0.01)
            except asyncio.TimeoutError:
                return "ok"

        await manager.run(job.id, worker)
        await asyncio.sleep(0.05)
        manager.snapshot(job.id)

    asyncio.run(scenario())


def test_job_publish_error_does_not_break_runner() -> None:
    import asyncio

    async def scenario() -> None:
        def explode(_payload):
            raise RuntimeError("推送失败")

        manager = JobManager(publish = explode)
        job = manager.create("demo")

        async def worker(j):
            return 1

        await manager.run(job.id, worker)
        await asyncio.sleep(0)
        assert manager.snapshot(job.id)["status"] == JobStatus.DONE.value

    asyncio.run(scenario())


def test_job_push_reaches_ws_client() -> None:
    with _client() as client:
        with client.websocket_connect("/ws") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"
            client.app.state.jobs.create("demo")
            seen = None
            deadline = 30
            while deadline > 0:
                message = ws.receive_json()
                if message.get("type") == "job":
                    seen = message
                    break
                deadline -= 1
            assert seen is not None and seen["job"]["kind"] == "demo", seen


def test_jobs_rest_contract_unchanged() -> None:
    with _client() as client:
        job = client.app.state.jobs.create("demo")
        listed = client.get("/api/jobs").json()
        assert set(listed) == {"jobs"}
        match = next(item for item in listed["jobs"] if item["id"] == job.id)
        assert "status" in match and "progress" in match
        missing = client.get("/api/jobs/不存在的id")
        assert missing.status_code == 404