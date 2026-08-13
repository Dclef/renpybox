import threading

from base.Base import Base
from module.Agent.AgentService import AgentService
from module.Agent.types import AgentRequestResult, AgentToolCall, ToolDef, ToolResult
from module.Config import Config
from module.Engine.TaskRequester import TaskRequester


class _Dispatcher:
    def __init__(self) -> None:
        self.calls = []
        self.tools = {
            "get_project_info": ToolDef(
                "get_project_info",
                "读取项目",
                {"type": "object", "properties": {}, "additionalProperties": False},
                lambda: ToolResult(True, "项目正常"),
            )
        }

    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return ToolResult(True, "项目正常", {"project_root": "E:/game"})


class _ConfirmDispatcher(_Dispatcher):
    def __init__(self) -> None:
        super().__init__()
        self.tools = {
            "unpack_rpa_files": ToolDef(
                "unpack_rpa_files",
                "解包",
                {"type": "object", "properties": {}, "additionalProperties": False},
                lambda: ToolResult(True, "完成"),
                requires_confirmation=True,
            )
        }

    def execute(self, name, arguments, *, confirmed=False, trusted_context=None):
        self.calls.append((name, arguments, confirmed, trusted_context))
        return ToolResult(True, "完成")


def _agent_config() -> Config:
    config = Config(agent_platform=0)
    config.platforms = [{
        "id": 0,
        "api_format": Base.APIFormat.OPENAI,
        "api_key": ["test"],
        "api_url": "https://example.invalid",
        "model": "test-model",
    }]
    return config


def test_service_executes_tool_calls_serially_and_returns_final_reply(monkeypatch) -> None:
    config = Config(agent_platform=1)
    config.platforms = [{
        "id": 1,
        "api_format": Base.APIFormat.OPENAI,
        "api_key": ["test"],
        "api_url": "https://example.invalid",
        "model": "test-model",
    }]
    dispatcher = _Dispatcher()
    responses = iter([
        AgentRequestResult(
            True,
            tool_calls=[AgentToolCall("call-1", "get_project_info", {})],
        ),
        AgentRequestResult(True, text="已经读取项目。"),
    ])
    observed_messages = []

    def request_tools(self, messages, tools):
        observed_messages.append(list(messages))
        return next(responses)

    monkeypatch.setattr(TaskRequester, "request_tools", request_tools)
    service = AgentService(config_loader=lambda: config, dispatcher=dispatcher)

    result = service.run("查看项目")

    assert result.success is True
    assert result.message == "已经读取项目。"
    assert dispatcher.calls == [("get_project_info", {})]
    assert len(observed_messages) == 2
    assert observed_messages[1][-1]["role"] == "tool"


def test_service_runs_confirmed_tool_and_rejects_unapproved_tool(monkeypatch) -> None:
    responses = iter([
        AgentRequestResult(True, tool_calls=[AgentToolCall("call-1", "unpack_rpa_files", {})]),
        AgentRequestResult(True, text="完成"),
    ])
    monkeypatch.setattr(TaskRequester, "request_tools", lambda *_args, **_kwargs: next(responses))
    approved_dispatcher = _ConfirmDispatcher()
    service = AgentService(config_loader=_agent_config, dispatcher=approved_dispatcher)
    monkeypatch.setattr(service, "confirmation_context", lambda _name: {"count": 1})

    result = service.run("解包", confirmation_callback=lambda _name, _payload: True)

    assert result.success is True
    assert approved_dispatcher.calls == [(
        "unpack_rpa_files",
        {},
        True,
        {"count": 1},
    )]

    responses = iter([
        AgentRequestResult(True, tool_calls=[AgentToolCall("call-2", "unpack_rpa_files", {})]),
    ])
    rejected_dispatcher = _ConfirmDispatcher()
    service = AgentService(config_loader=_agent_config, dispatcher=rejected_dispatcher)
    monkeypatch.setattr(service, "confirmation_context", lambda _name: {"count": 1})
    result = service.run("解包", confirmation_callback=lambda _name, _payload: False)

    assert result.success is False
    assert result.code == "USER_CANCELLED"
    assert rejected_dispatcher.calls == []
    assert result.data["events"][0]["code"] == "USER_CANCELLED"


def test_service_confirmation_timeout_does_not_execute_tool(monkeypatch) -> None:
    responses = iter([
        AgentRequestResult(True, tool_calls=[AgentToolCall("call-1", "unpack_rpa_files", {})]),
    ])
    monkeypatch.setattr(TaskRequester, "request_tools", lambda *_args, **_kwargs: next(responses))
    dispatcher = _ConfirmDispatcher()
    service = AgentService(config_loader=_agent_config, dispatcher=dispatcher)
    monkeypatch.setattr(service, "confirmation_context", lambda _name: {"count": 1})

    result = service.run("解包", confirmation_callback=lambda _name, _payload: None)

    assert dispatcher.calls == []
    assert result.success is False
    assert result.code == "CONFIRMATION_TIMEOUT"
    assert result.data["events"][0]["code"] == "CONFIRMATION_TIMEOUT"


def test_service_cancel_before_run_does_not_send_request(monkeypatch) -> None:
    cancel_event = threading.Event()
    cancel_event.set()
    monkeypatch.setattr(
        TaskRequester,
        "request_tools",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("不应发送请求")),
    )
    service = AgentService(config_loader=_agent_config, dispatcher=_Dispatcher())

    result = service.run("查看项目", cancel_event=cancel_event)

    assert result.success is False
    assert result.code == "CANCELLED"


def test_service_cancel_after_confirmation_does_not_execute_tool(monkeypatch) -> None:
    cancel_event = threading.Event()
    monkeypatch.setattr(
        TaskRequester,
        "request_tools",
        lambda *_args, **_kwargs: AgentRequestResult(
            True,
            tool_calls=[AgentToolCall("call-1", "unpack_rpa_files", {})],
        ),
    )
    dispatcher = _ConfirmDispatcher()
    service = AgentService(config_loader=_agent_config, dispatcher=dispatcher)
    monkeypatch.setattr(service, "confirmation_context", lambda _name: {"count": 1})

    def confirm(_name, _payload):
        cancel_event.set()
        return True

    result = service.run("解包", confirmation_callback=confirm, cancel_event=cancel_event)

    assert result.code == "USER_CANCELLED"
    assert dispatcher.calls == []


def test_service_rejection_completes_all_tool_call_history(monkeypatch) -> None:
    monkeypatch.setattr(
        TaskRequester,
        "request_tools",
        lambda *_args, **_kwargs: AgentRequestResult(
            True,
            tool_calls=[
                AgentToolCall("call-1", "unpack_rpa_files", {}),
                AgentToolCall("call-2", "unpack_rpa_files", {}),
            ],
        ),
    )
    service = AgentService(config_loader=_agent_config, dispatcher=_ConfirmDispatcher())
    monkeypatch.setattr(service, "confirmation_context", lambda _name: {"count": 1})

    result = service.run("解包", confirmation_callback=lambda _name, _payload: False)

    assert result.code == "USER_CANCELLED"
    tool_messages = [item for item in service.messages if item.get("role") == "tool"]
    assert [item["tool_call_id"] for item in tool_messages] == ["call-1", "call-2"]


def test_service_closes_agent_client_after_run(monkeypatch) -> None:
    closed = []
    monkeypatch.setattr(
        TaskRequester,
        "request_tools",
        lambda *_args, **_kwargs: AgentRequestResult(True, text="完成"),
    )
    monkeypatch.setattr(TaskRequester, "close_tools", lambda self: closed.append(self))
    service = AgentService(config_loader=_agent_config, dispatcher=_Dispatcher())

    result = service.run("查看项目")

    assert result.success is True
    assert len(closed) == 1


def test_service_reset_clears_conversation() -> None:
    service = AgentService(config_loader=_agent_config, dispatcher=_Dispatcher())
    service.messages = [{"role": "user", "content": "旧任务"}]
    service._project_key = "old"

    service.reset()

    assert service.messages == []
    assert service._project_key == ""
