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

    def execute(self, name, arguments, *, confirmed=False, trusted_context=None, cancel_check=None, progress_callback=None):
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

    def execute(
        self,
        name,
        arguments,
        *,
        confirmed=False,
        trusted_context=None,
        cancel_check=None,
        progress_callback=None,
    ):
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


def test_service_runs_ui_confirmed_tool_once_without_model_request(monkeypatch) -> None:
    """界面确认的快捷工具直接执行一次，不再请求模型决定是否调用。"""
    monkeypatch.setattr(
        TaskRequester,
        "request_tools",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("快捷工具不应请求模型")
        ),
    )
    dispatcher = _ConfirmDispatcher()
    service = AgentService(config_loader=_agent_config, dispatcher=dispatcher)
    snapshot = {"game_dir": "E:/game/game", "count": 1}
    monkeypatch.setattr(service, "confirmation_context", lambda _name: dict(snapshot))
    events = []

    result = service.run_confirmed_tool(
        "unpack_rpa_files",
        trusted_context=snapshot,
        callback=lambda name, payload: events.append((name, payload)),
    )

    assert result.success is True
    assert dispatcher.calls == [
        ("unpack_rpa_files", {}, True, snapshot)
    ]
    assert [name for name, _payload in events] == ["tool_start", "tool_done"]


def test_service_rejects_stale_ui_confirmation_snapshot() -> None:
    """确认后项目发生变化时不得在新项目上执行解包。"""
    dispatcher = _ConfirmDispatcher()
    service = AgentService(config_loader=_agent_config, dispatcher=dispatcher)
    service.confirmation_context = lambda _name: {
        "game_dir": "E:/other/game",
        "count": 2,
    }

    result = service.run_confirmed_tool(
        "unpack_rpa_files",
        trusted_context={"game_dir": "E:/game/game", "count": 1},
    )

    assert result.success is False
    assert result.code == "CONFIRMATION_STALE"
    assert dispatcher.calls == []


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
    service._metrics.update({"iterations": 9, "steps": 40, "input_tokens": 1000})

    service.reset()

    assert service.messages == []
    assert service._project_key == ""
    # 新建任务必须连用量一起清零，否则状态栏会停在上一个任务的数字上。
    assert service.metrics_summary()["iterations"] == 0
    assert service.metrics_summary()["steps"] == 0
    assert service.metrics_summary()["total_tokens"] == 0
    assert service.metrics_summary()["cache_hit_rate"] is None


def test_service_trims_old_history_by_complete_user_round(monkeypatch) -> None:
    observed_messages = []
    monkeypatch.setattr(
        TaskRequester,
        "request_tools",
        lambda _self, messages, _tools: (
            observed_messages.append(list(messages))
            or AgentRequestResult(True, text="完成")
        ),
    )
    service = AgentService(
        config_loader=_agent_config,
        dispatcher=_Dispatcher(),
        max_context_chars=4096,
    )
    service.messages = [
        {"role": "system", "content": "系统提示"},
        {"role": "user", "content": "旧问题"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "old-call", "function": {"name": "old"}}],
        },
        {
            "role": "tool",
            "tool_call_id": "old-call",
            "name": "old",
            "content": "x" * 5000,
        },
        {"role": "user", "content": "最近问题"},
        {"role": "assistant", "content": "最近回答"},
    ]

    result = service.run("当前问题")

    assert result.success is True
    sent = observed_messages[0]
    assert [item["content"] for item in sent if item["role"] == "user"] == [
        "最近问题",
        "当前问题",
    ]
    assert all(item.get("tool_call_id") != "old-call" for item in sent)


def test_service_invalid_agent_platform_is_treated_as_unset() -> None:
    config = _agent_config()
    config.agent_platform = "invalid"
    service = AgentService(config_loader=lambda: config, dispatcher=_Dispatcher())

    result = service.run("查看项目")

    assert result.success is False
    assert result.code == "AGENT_PLATFORM_NOT_SET"


def test_service_recovers_from_truncated_tool_arguments(monkeypatch) -> None:
    """截断是可自愈错误：把原因回灌给模型后，下一轮正常写回应当成功。"""
    observed_messages = []
    responses = iter([
        AgentRequestResult.failure("TOOL_ARGUMENTS_TRUNCATED", "参数被截断，请降低单次条目数。"),
        AgentRequestResult(
            True,
            tool_calls=[AgentToolCall("call-1", "get_project_info", {})],
        ),
        AgentRequestResult(True, text="已经读取项目。"),
    ])

    def request_tools(_self, messages, _tools):
        observed_messages.append(list(messages))
        return next(responses)

    monkeypatch.setattr(TaskRequester, "request_tools", request_tools)
    service = AgentService(config_loader=_agent_config, dispatcher=_Dispatcher())

    result = service.run("继续写回")

    assert result.success is True
    assert result.message == "已经读取项目。"
    # 第二次请求必须能看到「截断原因」，否则模型无从修正。
    assert observed_messages[1][-1]["role"] == "user"
    assert "参数被截断" in observed_messages[1][-1]["content"]


def test_service_gives_up_after_repeated_truncation(monkeypatch) -> None:
    responses = iter([
        AgentRequestResult.failure("TOOL_ARGUMENTS_TRUNCATED", "参数被截断。")
        for _ in range(AgentService.MAX_TRUNCATION_RETRIES + 1)
    ])
    monkeypatch.setattr(TaskRequester, "request_tools", lambda *_args, **_kwargs: next(responses))
    service = AgentService(config_loader=_agent_config, dispatcher=_Dispatcher())

    result = service.run("继续写回")

    assert result.success is False
    assert result.code == "TOOL_ARGUMENTS_TRUNCATED"


def test_metrics_accumulate_usage_and_steps(monkeypatch) -> None:
    """状态栏数据：两轮请求、一次工具步，token 与缓存命中都要累加。"""
    responses = iter([
        AgentRequestResult(
            True,
            tool_calls=[AgentToolCall("call-1", "get_project_info", {})],
            usage={"input_tokens": 1000, "output_tokens": 200, "cached_tokens": 768},
        ),
        AgentRequestResult(
            True,
            text="完成。",
            usage={"input_tokens": 500, "output_tokens": 100, "cached_tokens": 0},
        ),
    ])
    monkeypatch.setattr(TaskRequester, "request_tools", lambda *_args, **_kwargs: next(responses))
    service = AgentService(config_loader=_agent_config, dispatcher=_Dispatcher())

    service.run("查看项目")
    metrics = service.metrics_summary()

    assert metrics["iterations"] == 2
    assert metrics["steps"] == 1
    assert metrics["requests"] == 2
    assert metrics["input_tokens"] == 1500
    assert metrics["output_tokens"] == 300
    assert metrics["cached_tokens"] == 768
    assert metrics["total_tokens"] == 1800
    # 命中率按「缓存命中 / 输入」算，供应商不回缓存字段时是 None。
    assert metrics["cache_hit_rate"] == round(768 / 1500, 4)
    assert metrics["context_percent"] > 0
    assert metrics["context_limit_chars"] > 0


def test_metrics_report_no_cache_hit_rate_without_provider_support(monkeypatch) -> None:
    monkeypatch.setattr(
        TaskRequester,
        "request_tools",
        lambda *_args, **_kwargs: AgentRequestResult(
            True,
            text="完成。",
            usage={"input_tokens": 100, "output_tokens": 50},
        ),
    )
    service = AgentService(config_loader=_agent_config, dispatcher=_Dispatcher())

    service.run("查看项目")
    metrics = service.metrics_summary()

    assert metrics["cached_tokens"] == 0
    assert metrics["cache_hit_rate"] is None


def test_metrics_freeze_after_run_finishes(monkeypatch) -> None:
    monkeypatch.setattr(
        TaskRequester,
        "request_tools",
        lambda *_args, **_kwargs: AgentRequestResult(
            True,
            text="完成。",
            usage={"input_tokens": 100, "output_tokens": 50},
        ),
    )
    service = AgentService(config_loader=_agent_config, dispatcher=_Dispatcher())

    service.run("查看项目")
    first = service.metrics_summary()
    second = service.metrics_summary()

    assert first["elapsed_seconds"] == second["elapsed_seconds"]
    assert first["tokens_per_second"] == second["tokens_per_second"]


def test_metrics_accumulate_across_messages_in_one_task(monkeypatch) -> None:
    """同一任务里追问要接着累计，而不是把「25 轮」打回「1 轮」。"""
    responses = iter([
        AgentRequestResult(True, text="第一次完成。", usage={"input_tokens": 100, "output_tokens": 40}),
        AgentRequestResult(
            True,
            tool_calls=[AgentToolCall("call-1", "get_project_info", {})],
            usage={"input_tokens": 200, "output_tokens": 60, "cached_tokens": 150},
        ),
        AgentRequestResult(True, text="第二次完成。", usage={"input_tokens": 300, "output_tokens": 80}),
    ])
    monkeypatch.setattr(TaskRequester, "request_tools", lambda *_args, **_kwargs: next(responses))
    service = AgentService(config_loader=_agent_config, dispatcher=_Dispatcher())

    service.run("查看项目")
    after_first = service.metrics_summary()
    service.run("继续")
    after_second = service.metrics_summary()

    assert after_first["iterations"] == 1
    assert after_second["iterations"] == 3  # 1 + 2 轮
    assert after_second["steps"] == 1
    assert after_second["input_tokens"] == 600
    assert after_second["output_tokens"] == 180
    assert after_second["cached_tokens"] == 150
    assert after_second["total_tokens"] == 780
    # 活跃时长跨轮累计，空闲时间不计入。
    assert after_second["elapsed_seconds"] >= after_first["elapsed_seconds"]
