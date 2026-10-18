from types import SimpleNamespace

from base.Base import Base
from module.Agent import AgentRequester as AgentRequesterModule
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
            "api_format": Base.APIFormat.GOOGLEFREE,
            "model": "free",
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


def test_google_cumulative_stream_emits_only_new_text() -> None:
    requester = _requester()
    received = []

    def chunk(text: str):
        return SimpleNamespace(
            usage_metadata=None,
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(
                        parts=[SimpleNamespace(text=text, thought=False)]
                    )
                )
            ],
        )

    class Stream:
        def __init__(self) -> None:
            self.closed = False

        def __iter__(self):
            return iter((chunk("你"), chunk("你好"), chunk("你好")))

        def close(self) -> None:
            self.closed = True

    stream = Stream()
    client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content_stream=lambda **_kwargs: stream,
        )
    )

    result = requester._request_google_stream(
        client,
        [],
        {},
        received.append,
        None,
    )

    assert result.success is True
    assert result.text == "你好"
    assert received == ["你", "好"]
    assert stream.closed is True


def test_output_token_limit_ignores_translation_row_threshold() -> None:
    """token_threshold 是每次翻译的行数上限，不能拿来当 Agent 的输出上限。"""
    requester = _requester()
    requester.config.token_threshold = 20

    assert requester._output_token_limit() >= AgentRequesterModule.AGENT_MIN_OUTPUT_TOKENS


def test_output_token_limit_follows_platform_max_output() -> None:
    """平台里显式配的 max_output_tokens 优先于模型兜底。"""
    requester = _requester()
    requester.platform["max_output_tokens"] = 32_000

    assert requester._output_token_limit() == 32_000


def test_truncated_tool_arguments_are_reported_not_swallowed(monkeypatch) -> None:
    """参数被截断时不能退化成空 dict，否则界面只会显示「缺少必填参数」。"""
    requester = _requester()
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **_kwargs: SimpleNamespace(
                    choices=[SimpleNamespace(
                        finish_reason="length",
                        message=SimpleNamespace(
                            content="",
                            reasoning_content="",
                            tool_calls=[SimpleNamespace(
                                id="call-1",
                                function=SimpleNamespace(
                                    name="write_translation_batch",
                                    arguments='{"translations": [{"src": "a", "dst": "b"',
                                ),
                            )],
                        ),
                    )],
                    usage=None,
                ),
            ),
        ),
    )
    monkeypatch.setattr(requester, "_get_client", lambda: client)

    result = requester.request_tools(
        [{"role": "user", "content": "继续"}],
        list(ToolDispatcher().tools.values()),
    )

    assert result.success is False
    assert result.error_code == "TOOL_ARGUMENTS_TRUNCATED"
    assert str(requester._output_token_limit()) in result.error_message


def test_truncated_stream_arguments_are_reported(monkeypatch) -> None:
    """流式路径同样要识别半截 JSON，不能把它当成空参数。"""
    requester = _requester()

    class Chunk:
        def __init__(self, arguments: str) -> None:
            self.choices = [SimpleNamespace(
                delta=SimpleNamespace(
                    content="",
                    reasoning_content="",
                    tool_calls=[SimpleNamespace(
                        index=0,
                        id="call-1",
                        function=SimpleNamespace(
                            name="write_translation_batch",
                            arguments=arguments,
                        ),
                    )],
                ),
            )]

    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **_kwargs: iter([Chunk('{"translations": [{"src": "a"')]),
            ),
        ),
    )
    monkeypatch.setattr(requester, "_get_client", lambda: client)

    result = requester.request_tools(
        [{"role": "user", "content": "继续"}],
        list(ToolDispatcher().tools.values()),
        on_text_delta=lambda _text: None,
    )

    assert result.success is False
    assert result.error_code == "TOOL_ARGUMENTS_TRUNCATED"


def test_bad_request_on_max_tokens_shrinks_budget_and_retries(monkeypatch) -> None:
    """端点嫌输出上限太大时应当自动减半重试，而不是直接报请求失败。"""
    import httpx

    requester = _requester()
    observed = []

    def bad_request() -> Exception:
        request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        return AgentRequesterModule.openai.BadRequestError(
            "max_tokens is too large",
            response=httpx.Response(400, request=request),
            body=None,
        )

    def create(**kwargs):
        observed.append(kwargs)
        if len(observed) == 1:
            raise bad_request()
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))],
            usage=None,
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(requester, "_get_client", lambda: client)
    original = requester._output_token_limit()

    result = requester.request_tools(
        [{"role": "user", "content": "hi"}],
        list(ToolDispatcher().tools.values()),
    )

    assert result.success is True
    assert len(observed) == 2
    assert observed[1]["max_tokens"] < observed[0]["max_tokens"]
    assert requester._output_token_limit() == max(
        AgentRequesterModule.AGENT_MIN_OUTPUT_TOKENS, original // 2
    )
