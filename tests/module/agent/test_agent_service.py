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
