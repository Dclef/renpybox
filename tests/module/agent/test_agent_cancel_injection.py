"""取消信号要同时注入 should_cancel 和 __cancel_check__。"""

from module.Agent.AgentService import AgentService
from module.Agent.ToolDispatcher import ToolDispatcher, _lazy_tool_handler
from module.Agent.types import AgentRequestResult, AgentToolCall, ToolDef, ToolResult
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.TaskRequester import TaskRequester
from base.Base import Base


class _Engine:
    def try_set_status(self, expected, status) -> bool:
        return True

    def release_status(self, expected) -> bool:
        return True

    def get_status(self):
        return Engine.Status.IDLE

    def has_stop_barrier(self) -> bool:
        return False


def test_dunder_cancel_check_reaches_declared_tool(monkeypatch) -> None:
    seen: dict = {}

    def fake_decompile(*, config_loader=None, confirmed_game_dir=None, __cancel_check__=None):
        seen["cancel"] = __cancel_check__
        return ToolResult(True, "ok")

    monkeypatch.setattr(
        "module.Agent.tools.pipeline_tools.decompile_rpyc_files",
        fake_decompile,
    )
    marker = lambda: True
    dispatcher = ToolDispatcher(engine=_Engine(), cancel_check=marker)
    result = dispatcher.execute(
        "decompile_rpyc_files",
        confirmed=True,
        trusted_context={"game_dir": "E:/Game/game"},
        cancel_check=marker,
    )

    assert result.success is True
    assert seen["cancel"] is marker


def test_should_cancel_still_receives_the_same_callback(monkeypatch) -> None:
    seen: dict = {}

    def fake_scan(*, config=None, config_loader=None, should_cancel=None):
        seen["cancel"] = should_cancel
        return ToolResult(True, "ok")

    monkeypatch.setattr("module.Agent.tools.project_tools.scan_script_errors", fake_scan)
    marker = lambda: False
    dispatcher = ToolDispatcher(engine=_Engine())
    result = dispatcher.execute("scan_script_errors", cancel_check=marker)

    assert result.success is True
    assert seen["cancel"] is marker


def test_lazy_handler_can_inject_both_cancel_names(monkeypatch) -> None:
    seen: dict = {}

    def fake_scan(*, config_loader=None, should_cancel=None, __cancel_check__=None):
        seen["should"] = should_cancel
        seen["dunder"] = __cancel_check__
        return ToolResult(True, "ok")

    monkeypatch.setattr("module.Agent.tools.project_tools.scan_script_errors", fake_scan)
    marker = lambda: False
    handler = _lazy_tool_handler("project_tools", "scan_script_errors", lambda: Config())
    result = handler(__cancel_check__=marker)

    assert result.success is True
    assert seen["should"] is marker
    assert seen["dunder"] is marker


def test_confirmation_branch_passes_cancel_check(monkeypatch) -> None:
    seen: dict = {}

    class _Dispatcher:
        def __init__(self) -> None:
            self.tools = {
                "probe_confirm": ToolDef(
                    "probe_confirm",
                    "确认",
                    {"type": "object", "properties": {}, "additionalProperties": False},
                    lambda: ToolResult(True, "ok"),
                    requires_confirmation=True,
                )
            }

        def execute(self, name, arguments, **kwargs):
            seen["cancel"] = kwargs.get("cancel_check")
            seen["progress"] = kwargs.get("progress_callback")
            return ToolResult(True, "ok")

    calls = {"n": 0}

    def request_tools(self, messages, tools):
        calls["n"] += 1
        if calls["n"] == 1:
            return AgentRequestResult(
                True,
                tool_calls=[AgentToolCall("call-1", "probe_confirm", {})],
            )
        return AgentRequestResult(True, text="完成")

    monkeypatch.setattr(TaskRequester, "request_tools", request_tools)
    config = Config(agent_platform=0)
    config.platforms = [{
        "id": 0,
        "api_format": Base.APIFormat.OPENAI,
        "api_key": ["test"],
        "api_url": "https://example.invalid",
        "model": "test-model",
    }]
    service = AgentService(
        config_loader=lambda: config,
        dispatcher=_Dispatcher(),
        max_iterations=4,
    )
    result = service.run("执行", confirmation_callback=lambda name, payload: True)

    assert result.success is True
    # bound method 每次访问都是新对象，用相等比较而不是身份比较。
    assert seen["cancel"] == service._cancel_check
    assert seen["cancel"].__self__ is service
    assert callable(seen["progress"])
