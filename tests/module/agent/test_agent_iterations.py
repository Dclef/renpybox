"""轮次预算：轮询豁免、模型推导、显式覆盖。"""

from module.Agent.AgentService import AgentService
from module.Agent.types import AgentRequestResult, AgentToolCall, ToolDef, ToolResult
from module.Config import Config
from module.Engine.TaskRequester import TaskRequester
from base.Base import Base


def _config() -> Config:
    config = Config(agent_platform=0)
    config.platforms = [{
        "id": 0,
        "api_format": Base.APIFormat.OPENAI,
        "api_key": ["test"],
        "api_url": "https://example.invalid",
        "model": "test-model",
    }]
    return config


class _Dispatcher:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0
        self.tools = {
            name: ToolDef(
                name,
                "工具",
                {"type": "object", "properties": {}, "additionalProperties": False},
                lambda: ToolResult(True, "ok"),
            )
        }

    def execute(self, name, arguments, **_kwargs):
        self.calls += 1
        return ToolResult(True, "ok")


def _patch_budget(monkeypatch, usable_tokens: int) -> None:
    monkeypatch.setattr("module.Agent.ModelCatalog.get", lambda _platform: {})
    monkeypatch.setattr("module.Agent.ModelCatalog.ensure_async", lambda _platform: None)

    def budget(_platform, _catalog=None):
        return {
            "usable_tokens": usable_tokens,
            "max_context_chars": 20000,
            "max_messages": 20,
            "max_output_tokens": 1024,
            "context_window": usable_tokens,
            "keep_recent_tokens": 1000,
        }

    monkeypatch.setattr("module.Agent.ModelBudget.agent_context_budget", budget)


def _run_until_reply(monkeypatch, service: AgentService, tool_name: str, tool_rounds: int):
    counter = {"n": 0}

    def request_tools(self, messages, tools):
        counter["n"] += 1
        if counter["n"] <= tool_rounds:
            return AgentRequestResult(
                True,
                tool_calls=[AgentToolCall(f"call-{counter['n']}", tool_name, {})],
            )
        return AgentRequestResult(True, text="完成")

    monkeypatch.setattr(TaskRequester, "request_tools", request_tools)
    return service.run("查看进度"), counter


def test_translation_status_polls_do_not_spend_iteration_budget(monkeypatch) -> None:
    dispatcher = _Dispatcher("translation_status")
    service = AgentService(
        config_loader=_config,
        dispatcher=dispatcher,
        max_iterations=8,
    )
    result, counter = _run_until_reply(monkeypatch, service, "translation_status", 10)

    assert result.success is True
    assert result.code == "OK"
    assert dispatcher.calls == 10
    assert counter["n"] == 11


def test_ordinary_tools_stop_at_eight_iterations(monkeypatch) -> None:
    dispatcher = _Dispatcher("get_project_info")
    service = AgentService(
        config_loader=_config,
        dispatcher=dispatcher,
        max_iterations=8,
    )
    result, _counter = _run_until_reply(monkeypatch, service, "get_project_info", 20)

    assert result.success is False
    assert result.code == "MAX_ITERATIONS"
    assert dispatcher.calls == 8


def test_iterations_are_derived_from_model_capacity(monkeypatch) -> None:
    _patch_budget(monkeypatch, 16000 * 10)
    dispatcher = _Dispatcher("get_project_info")
    service = AgentService(config_loader=_config, dispatcher=dispatcher)
    result, _counter = _run_until_reply(monkeypatch, service, "get_project_info", 0)

    assert result.success is True
    assert service.max_iterations == 10


def test_derived_iterations_are_clamped(monkeypatch) -> None:
    _patch_budget(monkeypatch, 16000 * 100)
    service = AgentService(config_loader=_config, dispatcher=_Dispatcher("get_project_info"))
    _run_until_reply(monkeypatch, service, "get_project_info", 0)
    assert service.max_iterations == 32

    _patch_budget(monkeypatch, 1000)
    small = AgentService(config_loader=_config, dispatcher=_Dispatcher("get_project_info"))
    _run_until_reply(monkeypatch, small, "get_project_info", 0)
    assert small.max_iterations == 8


def test_explicit_iteration_override_wins(monkeypatch) -> None:
    _patch_budget(monkeypatch, 16000 * 100)
    service = AgentService(
        config_loader=_config,
        dispatcher=_Dispatcher("get_project_info"),
        max_iterations=5,
    )
    _run_until_reply(monkeypatch, service, "get_project_info", 0)
    assert service.max_iterations == 5
