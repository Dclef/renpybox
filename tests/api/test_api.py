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