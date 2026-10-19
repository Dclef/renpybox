"""Agent 会话历史的 API 桥接：落盘、切换、删除。"""

import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.agent import AgentSession
from api.routes import agent
from module.Agent.AgentService import AgentService
from module.Agent.AgentSessionStore import AgentSessionStore
from module.Agent.types import AgentRequestResult
from module.Config import Config
from module.Engine.TaskRequester import TaskRequester


@pytest.fixture
def history_app(monkeypatch, tmp_path):
    config = Config(agent_platform=0, activate_platform=1, platforms=[{
        "id": 0, "api_format": "OpenAI", "api_url": "https://example.invalid/v1",
        "model": "fixture-model", "api_key": [], "thinking": {"level": "OFF"},
    }])
    monkeypatch.setattr(
        TaskRequester,
        "request_tools",
        lambda *_args, **_kwargs: AgentRequestResult(
            True,
            text="已完成。",
            usage={"input_tokens": 10, "output_tokens": 5},
        ),
    )
    service = AgentService(config_loader=lambda: config)
    session = AgentSession(service, lambda _payload: None, store=AgentSessionStore(tmp_path))
    app = FastAPI()
    app.include_router(agent.router)
    app.state.agent = session
    app.state.config = config
    with TestClient(app) as client:
        bundle = SimpleNamespace(client=client, session=session, store=session.store)
        try:
            yield bundle
        finally:
            session.close()


def _wait_idle(client):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        snapshot = client.get("/api/agent").json()
        if snapshot["status"] == "idle":
            return snapshot
        time.sleep(0.01)
    raise AssertionError("Agent 快照未在时限内回到空闲")


def test_finished_run_is_saved_and_listed(history_app) -> None:
    client = history_app.client

    client.post("/api/agent/message", json={"message": "查看项目", "thinking_level": "OFF"})
    _wait_idle(client)

    sessions = client.get("/api/agent/sessions").json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["title"] == "查看项目"
    assert sessions[0]["message_count"] == 2
    assert history_app.store.load(sessions[0]["id"]) is not None


def test_new_task_keeps_previous_session_in_history(history_app) -> None:
    client = history_app.client
    client.post("/api/agent/message", json={"message": "第一个任务", "thinking_level": "OFF"})
    first = _wait_idle(client)
    first_id = first["session_id"]

    reset = client.post("/api/agent/reset").json()

    assert reset["session_id"] != first_id
    assert reset["messages"] == []
    sessions = client.get("/api/agent/sessions").json()["sessions"]
    assert any(item["id"] == first_id and item["title"] == "第一个任务" for item in sessions)


def test_open_session_restores_messages_and_context(history_app) -> None:
    client = history_app.client
    client.post("/api/agent/message", json={"message": "查看项目", "thinking_level": "OFF"})
    finished = _wait_idle(client)
    saved_id = finished["session_id"]
    saved_messages = finished["messages"]

    client.post("/api/agent/reset")
    opened = client.post(f"/api/agent/sessions/{saved_id}/open").json()

    assert opened["session_id"] == saved_id
    assert [item["content"] for item in opened["messages"]] == [
        item["content"] for item in saved_messages
    ]
    # 恢复的会话要能继续追问：service 上下文里有原来的 system + user 消息。
    assert any(item.get("role") == "user" for item in history_app.session.service.messages)


def test_open_missing_session_returns_404(history_app) -> None:
    assert history_app.client.post("/api/agent/sessions/missing/open").status_code == 404


def test_delete_session_removes_it_from_history(history_app) -> None:
    client = history_app.client
    client.post("/api/agent/message", json={"message": "第一个任务", "thinking_level": "OFF"})
    finished = _wait_idle(client)
    saved_id = finished["session_id"]
    client.post("/api/agent/reset")

    response = client.delete(f"/api/agent/sessions/{saved_id}")

    assert response.json() == {"deleted": True}
    assert client.get("/api/agent/sessions").json()["sessions"] == []
    assert history_app.store.load(saved_id) is None


def test_delete_current_session_branch_starts_clean(history_app) -> None:
    client = history_app.client
    client.post("/api/agent/message", json={"message": "第一个任务", "thinking_level": "OFF"})
    finished = _wait_idle(client)
    current_id = finished["session_id"]

    client.delete(f"/api/agent/sessions/{current_id}")

    snapshot = client.get("/api/agent").json()
    assert snapshot["session_id"] != current_id
    assert snapshot["messages"] == []


def test_delete_current_session_stays_deleted(history_app) -> None:
    """删掉当前会话后它不能又被写回历史（表现为「要删两次」）。"""
    client = history_app.client
    client.post("/api/agent/message", json={"message": "第一个任务", "thinking_level": "OFF"})
    finished = _wait_idle(client)
    current_id = finished["session_id"]
    assert history_app.store.load(current_id) is not None

    assert client.delete(f"/api/agent/sessions/{current_id}").json() == {"deleted": True}

    assert history_app.store.load(current_id) is None
    sessions = client.get("/api/agent/sessions").json()["sessions"]
    assert [item["id"] for item in sessions] == []


def test_delete_deletes_again_after_reload(history_app) -> None:
    """删完后重新拉历史列表仍然是空的，不需要用户再点一次。"""
    client = history_app.client
    client.post("/api/agent/message", json={"message": "第一个任务", "thinking_level": "OFF"})
    finished = _wait_idle(client)
    current_id = finished["session_id"]
    client.delete(f"/api/agent/sessions/{current_id}")

    # 面板关掉再打开 = 重新拉一次列表。
    assert client.get("/api/agent/sessions").json()["sessions"] == []
    assert history_app.store.load(current_id) is None


def test_busy_session_refuses_switch(history_app, monkeypatch) -> None:
    import threading

    release = threading.Event()

    def request(*_args, **_kwargs):
        release.wait(3)
        return AgentRequestResult(True, text="完成")

    monkeypatch.setattr(TaskRequester, "request_tools", request)
    client = history_app.client
    client.post("/api/agent/message", json={"message": "长任务", "thinking_level": "OFF"})
    try:
        assert client.post("/api/agent/sessions/anything/open").status_code == 409
    finally:
        release.set()
        _wait_idle(client)
