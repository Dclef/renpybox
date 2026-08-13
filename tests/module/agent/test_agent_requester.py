from types import SimpleNamespace

from base.Base import Base
from module.Agent.AgentRequester import AgentRequester
from module.Agent.ToolDispatcher import ToolDispatcher
from module.Agent.types import AgentToolCall
from module.Config import Config
from module.Engine.TaskRequester import TaskRequester


def _requester() -> AgentRequester:
    config = Config()
    platform = {
        "api_key": ["test-key"],
        "api_url": "https://example.invalid/v1",
        "api_format": Base.APIFormat.OPENAI,
        "model": "test-model",
    }
    return AgentRequester(config, platform)


def test_openai_tool_payload_and_response_are_non_streaming(monkeypatch) -> None:
    requester = _requester()
    observed = {}
    function_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="get_project_info", arguments="{}"),
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: (
                    observed.update(kwargs)
                    or SimpleNamespace(
                        choices=[SimpleNamespace(
                            message=SimpleNamespace(
                                content="已读取",
                                reasoning_content="",
                                tool_calls=[function_call],
                            ),
                        )],
                        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=4),
                    )
                ),
            ),
        ),
    )
    monkeypatch.setattr(requester, "_get_client", lambda: client)
    tools = list(ToolDispatcher().tools.values())

    result = requester.request_tools([{"role": "user", "content": "查看项目"}], tools)

    assert result.success is True
    assert result.text == "已读取"
    assert result.tool_calls == [AgentToolCall("call-1", "get_project_info", {})]
    assert observed["tools"][1]["function"]["name"] == "get_project_info"
    assert "game_dir" not in observed["tools"][1]["function"]["parameters"].get("properties", {})
    assert "stream" not in observed


def test_openai_official_o_series_uses_completion_token_field(monkeypatch) -> None:
    requester = _requester()
    requester.platform["api_url"] = "https://api.openai.com/v1"
    requester.platform["model"] = "o4-mini"
    observed = {}
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: (
                    observed.update(kwargs)
                    or SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))],
                        usage=None,
                    )
                ),
            ),
        ),
    )
    monkeypatch.setattr(requester, "_get_client", lambda: client)

    requester.request_tools([{"role": "user", "content": "hi"}], list(ToolDispatcher().tools.values()))

    assert "max_completion_tokens" in observed
    assert "max_tokens" not in observed


def test_unsupported_platform_is_explicit_and_cancel_isolated() -> None:
    requester = AgentRequester(
        Config(),
        {
            "api_key": ["test-key"],
            "api_url": "http://localhost",
            "api_format": Base.APIFormat.DEEPL,
            "model": "deep-l",
        },
    )
    result = requester.request_tools([], list(ToolDispatcher().tools.values()))

    assert result.success is False
    assert result.error_code == "UNSUPPORTED_AGENT_PLATFORM"
    requester.cancel()
    assert requester.cancel_event.is_set()
    assert not TaskRequester.CANCEL_EVENT.is_set()


def test_cancelling_requester_does_not_close_another_agent_client(monkeypatch) -> None:
    first = _requester()
    second = _requester()
    closed = []

    class Client:
        def __init__(self, name):
            self.name = name

        def close(self):
            closed.append(self.name)

    monkeypatch.setattr("module.Agent.AgentRequester.openai.OpenAI", lambda **_kwargs: Client("first"))
    first_client = first._get_client()
    monkeypatch.setattr("module.Agent.AgentRequester.openai.OpenAI", lambda **_kwargs: Client("second"))
    second_client = second._get_client()

    assert first_client is not second_client
    first.cancel()
    assert closed == ["first"]
    assert second._get_client() is second_client
    second.cancel()
