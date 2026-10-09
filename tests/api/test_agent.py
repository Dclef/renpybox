"""真实 AgentService 的 API 桥接，模型请求和写入工具均用受控替身。"""

import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.agent import AgentSession
from api.hub import ConnectionHub
from api.jobs import JobManager
from api.routes import agent, ws
from module.Agent.AgentService import AgentService
from module.Agent.types import AgentRequestResult, AgentToolCall, ToolDef, ToolResult
from module.Config import Config
from module.Engine.TaskRequester import TaskRequester


class Dispatcher:
    def __init__(self):
        self.calls = []
        self.tools = {"unpack_rpa_files": ToolDef(
            "unpack_rpa_files", "解包资源", {"type": "object", "properties": {}},
            lambda: ToolResult(True, "完成"), requires_confirmation=True,
        )}

    def execute(self, name, arguments, **options):
        self.calls.append((name, arguments, options))
        return ToolResult(True, "工具完成", {"api_key": "never-expose"})


@pytest.fixture
def agent_app(monkeypatch):
    config = Config(agent_platform=0, activate_platform=1, platforms=[{
        "id": 0, "api_format": "OpenAI", "api_url": "https://example.invalid/v1",
        "model": "fixture-model", "api_key": [], "thinking": {"level": "OFF"},
    }])
    dispatcher = Dispatcher()
    service = AgentService(config_loader=lambda: config, dispatcher=dispatcher)
    monkeypatch.setattr(service, "confirmation_context", lambda _name: {"game_dir": "C:/fixture/game", "count": 2})
    hub = ConnectionHub()
    updates = []

    def notify(payload):
        updates.append(payload)
        hub.broadcast_threadsafe(payload)

    session = AgentSession(service, notify)
    app = FastAPI()
    app.include_router(agent.router)
    app.include_router(ws.router)
    app.state.agent = session
    app.state.config = config
    app.state.hub = hub
    app.state.jobs = JobManager()
    app.state.app_version = "fixture"
    app.state.bridge_event_names = ("AGENT_UPDATE",)
    with TestClient(app) as client:
        try:
            yield SimpleNamespace(client=client, config=config, service=service, session=session, dispatcher=dispatcher, updates=updates)
        finally:
            session.close()


def wait_snapshot(client, predicate):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        snapshot = client.get("/api/agent").json()
        if predicate(snapshot):
            return snapshot
        time.sleep(0.01)
    raise AssertionError("Agent 快照未在时限内进入预期状态")


def test_streaming_busy_barrier_history_and_reset(agent_app, monkeypatch):
    release = threading.Event()
    platforms = []
    histories = []

    def request(requester, messages, tools, **callbacks):
        platforms.append(requester.platform)
        histories.append(list(messages))
        callbacks["on_text_delta"]("部分回复")
        callbacks["on_reasoning_delta"]("检查项目")
        assert release.wait(3)
        return AgentRequestResult(True, text="最终回复")

    monkeypatch.setattr(TaskRequester, "request_tools", request)
    client = agent_app.client
    assert client.post("/api/agent/message", json={"message": "第一条", "thinking_level": "HIGH"}).status_code == 200
    streaming = wait_snapshot(client, lambda snapshot: snapshot["messages"][-1]["content"] == "部分回复")
    assert streaming["status"] == "running"
    assert streaming["messages"][-1]["reasoning"] == "检查项目"
    assert client.post("/api/agent/message", json={"message": "重复"}).status_code == 409
    assert client.post("/api/agent/reset").status_code == 409
    release.set()
    completed = wait_snapshot(client, lambda snapshot: snapshot["status"] == "idle")
    assert completed["messages"][-1]["content"] == "最终回复"
    assert platforms[0]["thinking"]["level"] == "HIGH"
    assert agent_app.config.platforms[0]["thinking"]["level"] == "OFF"
    assert agent_app.config.activate_platform == 1
    assert client.post("/api/agent/message", json={"message": "第二条"}).status_code == 200
    wait_snapshot(client, lambda snapshot: snapshot["status"] == "idle")
    assert [entry["content"] for entry in histories[-1] if entry["role"] == "user"] == ["第一条", "第二条"]
    assert client.post("/api/agent/reset").json()["messages"] == []
    assert agent_app.service.messages == []


@pytest.mark.parametrize("approved", [True, False])
def test_confirmation_is_explicit_single_use_and_masks_keys(agent_app, monkeypatch, approved):
    replies = iter([
        AgentRequestResult(True, tool_calls=[AgentToolCall("call-1", "unpack_rpa_files", {})]),
        AgentRequestResult(True, text="操作完成"),
    ])
    monkeypatch.setattr(TaskRequester, "request_tools", lambda *_args, **_kwargs: next(replies))
    client = agent_app.client
    client.post("/api/agent/message", json={"message": "解包"})
    pending = wait_snapshot(client, lambda snapshot: snapshot["confirmation"] is not None)["confirmation"]
    assert not agent_app.dispatcher.calls
    assert pending["data"] == {"game_dir": "C:/fixture/game", "count": 2}
    assert client.post("/api/agent/confirm", json={"confirmation_id": "0" * 32, "approved": True}).status_code == 409
    response = client.post("/api/agent/confirm", json={"confirmation_id": pending["id"], "approved": approved})
    assert response.status_code == 200
    completed = wait_snapshot(client, lambda snapshot: snapshot["status"] == "idle")
    assert len(agent_app.dispatcher.calls) == int(approved)
    assert completed["messages"][-1]["status"] == ("done" if approved else "cancelled")
    if approved:
        assert agent_app.dispatcher.calls[0][2]["trusted_context"] == pending["data"]
        assert completed["messages"][-1]["tools"][0]["data"]["api_key"] == "***"
    assert "never-expose" not in client.get("/api/agent").text
    assert client.post("/api/agent/confirm", json={"confirmation_id": pending["id"], "approved": True}).status_code == 409


@pytest.mark.parametrize("mode", ["stop", "timeout", "project-change"])
def test_stop_timeout_and_project_change_never_run_stale_write(agent_app, monkeypatch, mode):
    replies = iter([
        AgentRequestResult(True, tool_calls=[AgentToolCall("call-1", "unpack_rpa_files", {})]),
        AgentRequestResult(True, text="已跳过工具"),
    ])
    monkeypatch.setattr(TaskRequester, "request_tools", lambda *_args, **_kwargs: next(replies))
    if mode == "timeout":
        agent_app.service.confirmation_timeout = 0.15
    client = agent_app.client
    client.post("/api/agent/message", json={"message": "解包"})
    pending = wait_snapshot(client, lambda snapshot: snapshot["confirmation"] is not None)["confirmation"]
    if mode == "stop":
        assert client.post("/api/agent/stop").status_code == 200
    elif mode == "project-change":
        monkeypatch.setattr(agent_app.service, "confirmation_context", lambda _name: {"game_dir": "C:/different/game", "count": 2})
        assert client.post("/api/agent/confirm", json={"confirmation_id": pending["id"], "approved": True}).status_code == 200
    completed = wait_snapshot(client, lambda snapshot: snapshot["status"] == "idle")
    assert not agent_app.dispatcher.calls
    assert completed["confirmation"] is None
    assert client.post("/api/agent/confirm", json={"confirmation_id": pending["id"], "approved": True}).status_code == 409
    expected = {"stop": "USER_CANCELLED", "timeout": "CONFIRMATION_TIMEOUT", "project-change": "CONFIRMATION_STALE"}
    assert completed["messages"][-1]["tools"][0]["code"] == expected[mode]


def test_errors_are_terminal_and_invalid_messages_never_start(agent_app, monkeypatch):
    client = agent_app.client
    agent_app.config.agent_platform = -1
    assert client.post("/api/agent/message", json={"message": "你好"}).status_code == 400
    agent_app.config.agent_platform = 0
    agent_app.config.platforms[0]["api_format"] = "SakuraLLM"
    assert client.post("/api/agent/message", json={"message": "你好"}).status_code == 400
    agent_app.config.platforms[0]["api_format"] = "OpenAI"
    assert client.post("/api/agent/message", json={"message": "   "}).status_code == 400
    assert client.post("/api/agent/message", json={"message": "x" * 16001}).status_code == 422
    assert client.post("/api/agent/message", json={"message": "你好", "thinking_level": "UNKNOWN"}).status_code == 422

    def fail(*_args, **_kwargs):
        raise RuntimeError("credential-must-not-leak")

    monkeypatch.setattr(TaskRequester, "request_tools", fail)
    client.post("/api/agent/message", json={"message": "检查"})
    completed = wait_snapshot(client, lambda snapshot: snapshot["status"] == "idle")
    assert completed["messages"][-1]["status"] == "failed"
    assert "credential-must-not-leak" not in client.get("/api/agent").text


def test_websocket_updates_and_reconnected_snapshot(agent_app, monkeypatch):
    monkeypatch.setattr(TaskRequester, "request_tools", lambda *_args, **_kwargs: AgentRequestResult(True, text="已检查"))
    client = agent_app.client
    with client.websocket_connect("/ws") as socket:
        assert "AGENT_UPDATE" in socket.receive_json()["events"]
        client.post("/api/agent/message", json={"message": "检查项目"})
        event = socket.receive_json()
        assert event["event"] == "AGENT_UPDATE"
        assert "messages" not in event["data"]
    completed = wait_snapshot(client, lambda snapshot: snapshot["status"] == "idle")
    assert completed["messages"][-1]["content"] == "已检查"
    with client.websocket_connect("/ws") as socket:
        assert socket.receive_json()["type"] == "hello"
        assert client.get("/api/agent").json() == completed
