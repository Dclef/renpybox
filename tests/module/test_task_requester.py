from types import SimpleNamespace

import openai
import pytest
import requests

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.TaskRequester import TaskRequester, ThinkingLevel
from module.Localizer.Localizer import Localizer


class _ClosableStream:
    def __init__(self) -> None:
        self.closed = False

    def __iter__(self):
        return iter((SimpleNamespace(),))

    def close(self) -> None:
        self.closed = True


class _GoogleClient:
    def __init__(self, stream) -> None:
        self.models = SimpleNamespace(generate_content_stream=lambda **kwargs: stream)


def _openai_requester(
    *,
    model: str = "test-model",
    thinking: object = False,
) -> TaskRequester:
    config = Config(translation_output_protocol = Config.OUTPUT_PROTOCOL_STRUCTURED)
    platform = {
        "api_key": ["test-key"],
        "api_url": "https://example.invalid",
        "api_format": Base.APIFormat.OPENAI,
        "model": model,
        "thinking": thinking,
    }
    return TaskRequester(config, platform, 1)


def test_request_google_closes_stream_when_cancelled(monkeypatch) -> None:
    stream = _ClosableStream()
    client = _GoogleClient(stream)
    config = Config()
    platform = {
        "api_key": ["test-key"],
        "api_url": "https://example.invalid",
        "api_format": Base.APIFormat.GOOGLE,
        "model": "gemini-2.5-flash",
        "thinking": False,
    }
    requester = TaskRequester(config, platform, 1)

    monkeypatch.setattr(
        TaskRequester,
        "get_client",
        classmethod(lambda cls, **kwargs: client),
    )
    monkeypatch.setattr(
        TaskRequester,
        "is_cancel_requested",
        classmethod(lambda cls: True),
    )
    monkeypatch.setattr(requester, "generate_google_args", lambda *args, **kwargs: {})

    result = requester.request_google([], ThinkingLevel.OFF, {})

    assert result == (True, None, None, None, None)
    assert stream.closed is True


def test_close_stream_tolerates_missing_close_method() -> None:
    TaskRequester._close_stream(object())


def test_openai_none_shape_ignores_global_structured_protocol() -> None:
    requester = _openai_requester()

    args = requester.generate_openai_args(
        [{"role": "user", "content": "返回 json 对象"}],
        ThinkingLevel.OFF,
        {},
        response_shape = "none",
    )

    assert "response_format" not in args


def test_openai_json_object_shape_adds_response_format() -> None:
    requester = _openai_requester()

    args = requester.generate_openai_args(
        [{"role": "user", "content": "返回 json 对象"}],
        ThinkingLevel.OFF,
        {},
        response_shape = "json_object",
    )

    assert args["response_format"] == {"type": "json_object"}


def test_openai_json_object_shape_without_lowercase_json_is_dropped(monkeypatch) -> None:
    requester = _openai_requester()
    warnings: list[str] = []
    monkeypatch.setattr(requester, "warning", warnings.append)

    args = requester.generate_openai_args(
        [{"role": "user", "content": "只返回对象"}],
        ThinkingLevel.OFF,
        {},
        response_shape = "json_object",
    )

    assert "response_format" not in args
    assert warnings == ["[API-REQUEST] 提示词未包含小写 json，已跳过 json_object 输出约束"]


def test_google_response_schema_is_request_specific() -> None:
    config = Config(translation_output_protocol = Config.OUTPUT_PROTOCOL_STRUCTURED)
    platform = {
        "api_key": ["test-key"],
        "api_url": "https://example.invalid",
        "api_format": Base.APIFormat.GOOGLE,
        "model": "gemini-2.5-flash",
        "thinking": False,
    }
    requester = TaskRequester(config, platform, 1)
    messages = [{"role": "user", "content": "返回 json 对象"}]

    plain_args = requester.generate_google_args(
        messages,
        ThinkingLevel.OFF,
        {},
        response_shape = "none",
    )
    json_args = requester.generate_google_args(
        messages,
        ThinkingLevel.OFF,
        {},
        response_shape = "json_object",
    )

    assert plain_args["config"].response_mime_type is None
    assert plain_args["config"].response_schema is None
    assert json_args["config"].response_mime_type == "application/json"
    assert json_args["config"].response_schema is not None


def test_request_passes_response_shape_to_openai(monkeypatch) -> None:
    requester = _openai_requester()
    observed: list[str] = []
    monkeypatch.setattr(
        TaskRequester,
        "is_cancel_requested",
        classmethod(lambda cls: False),
    )

    def request_openai(messages, thinking_level, args, *, response_shape):
        observed.append(response_shape)
        return False, "", "ok", 1, 1

    monkeypatch.setattr(requester, "request_openai", request_openai)

    result = requester.request([], response_shape = "json_object")

    assert result == (False, "", "ok", 1, 1)
    assert observed == ["json_object"]


def test_openai_bad_request_is_not_retried(monkeypatch) -> None:
    requester = _openai_requester()
    attempts = 0

    class FakeBadRequestError(Exception):
        pass

    monkeypatch.setattr(openai, "BadRequestError", FakeBadRequestError)
    monkeypatch.setattr(
        TaskRequester,
        "is_cancel_requested",
        classmethod(lambda cls: False),
    )
    monkeypatch.setattr(requester, "error", lambda *args: None)
    monkeypatch.setattr(requester, "warning", lambda *args: None)

    def request_openai(messages, thinking_level, args, *, response_shape):
        nonlocal attempts
        attempts += 1
        raise FakeBadRequestError("参数错误")

    monkeypatch.setattr(requester, "request_openai", request_openai)

    result = requester.request([])

    assert result == (True, None, None, None, None)
    assert attempts == 1
    assert requester.last_error_message == "参数错误"


def test_openai_generic_error_message_is_preserved(monkeypatch) -> None:
    requester = _openai_requester()

    def create(**kwargs):
        raise RuntimeError("认证失败")

    client = SimpleNamespace(
        chat = SimpleNamespace(
            completions = SimpleNamespace(create = create),
        ),
    )
    monkeypatch.setattr(
        TaskRequester,
        "get_client",
        classmethod(lambda cls, **kwargs: client),
    )
    monkeypatch.setattr(requester, "error", lambda *args: None)

    result = requester.request_openai([], ThinkingLevel.OFF, {})

    assert result == (True, None, None, None, None)
    assert requester.last_error_message == "认证失败"


def test_sakura_bad_request_is_not_retried(monkeypatch) -> None:
    config = Config()
    platform = {
        "api_key": ["test-key"],
        "api_url": "https://example.invalid",
        "api_format": Base.APIFormat.SAKURALLM,
        "model": "test-model",
        "thinking": False,
    }
    requester = TaskRequester(config, platform, 1)
    attempts = 0

    class FakeBadRequestError(Exception):
        pass

    def create(**kwargs):
        nonlocal attempts
        attempts += 1
        raise FakeBadRequestError("参数错误")

    client = SimpleNamespace(
        chat = SimpleNamespace(
            completions = SimpleNamespace(create = create),
        ),
    )
    monkeypatch.setattr(openai, "BadRequestError", FakeBadRequestError)
    monkeypatch.setattr(
        TaskRequester,
        "get_client",
        classmethod(lambda cls, **kwargs: client),
    )
    monkeypatch.setattr(
        TaskRequester,
        "is_cancel_requested",
        classmethod(lambda cls: False),
    )
    monkeypatch.setattr(requester, "error", lambda *args: None)
    monkeypatch.setattr(requester, "warning", lambda *args: None)

    result = requester.request([])

    assert result == (True, None, None, None, None)
    assert attempts == 1
    assert requester.last_error_message == "参数错误"


@pytest.mark.parametrize(
    ("level", "expected"),
    (
        (ThinkingLevel.OFF, {"thinking": {"type": "disabled"}}),
        (
            ThinkingLevel.LOW,
            {"thinking": {"type": "enabled"}, "reasoning_effort": "low"},
        ),
        (
            ThinkingLevel.MEDIUM,
            {"thinking": {"type": "enabled"}, "reasoning_effort": "high"},
        ),
        (
            ThinkingLevel.HIGH,
            {"thinking": {"type": "enabled"}, "reasoning_effort": "high"},
        ),
        (
            ThinkingLevel.MAX,
            {"thinking": {"type": "enabled"}, "reasoning_effort": "max"},
        ),
    ),
)
def test_deepseek_thinking_levels(level: ThinkingLevel, expected: dict) -> None:
    requester = _openai_requester(model = "deepseek-v4-flash")

    args = requester.generate_openai_args([], level, {})

    assert args["extra_body"] == expected


class _FakeTranslateResponse:
    def __init__(self, text: str) -> None:
        self.translatedText = text


def _googlefree_requester() -> TaskRequester:
    config = Config(
        source_language = BaseLanguage.Enum.EN,
        target_language = BaseLanguage.Enum.ZH,
    )
    platform = {
        "api_key": ["no_key_required"],
        "api_url": "",
        "api_format": Base.APIFormat.GOOGLEFREE,
        "model": "free",
        "thinking": False,
    }
    return TaskRequester(config, platform, 1)


def test_request_googlefree_batch_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class FakeClient:
        def translate(self, q, **kwargs):
            captured["q"] = list(q)
            captured.update(kwargs)
            return [_FakeTranslateResponse(f"T:{v}") for v in q]

    requester = _googlefree_requester()
    monkeypatch.setattr(TaskRequester, "get_client", classmethod(lambda cls, **kwargs: FakeClient()))
    monkeypatch.setattr(TaskRequester, "is_cancel_requested", classmethod(lambda cls: False))

    messages = [{
        "role": "user",
        "content": '```jsonline\n{"0": "hello"}\n{"1": "world"}\n```',
    }]
    skip, _, response_result, input_tokens, output_tokens = requester.request_googlefree(messages)

    assert skip is False
    assert captured == {"q": ["hello", "world"], "source": "en", "target": "zh-CN"}
    assert "T:hello" in response_result
    assert "T:world" in response_result
    assert input_tokens > 0 and output_tokens > 0


@pytest.mark.parametrize("provider", [Base.APIFormat.GOOGLEFREE, Base.APIFormat.BING])
def test_free_translation_rate_limit_is_visible_and_does_not_spam(monkeypatch, provider):
    requester = _googlefree_requester()
    requester.platform["api_format"] = provider
    response = requests.Response()
    response.status_code = 429
    response.url = "https://example.invalid/translate"
    response.reason = "Too Many Requests"
    client = SimpleNamespace(translate=lambda *args, **kwargs: SimpleNamespace(response=response))
    monkeypatch.setattr(TaskRequester, "get_client", classmethod(lambda cls, **kwargs: client))
    monkeypatch.setattr(
        "module.Engine.TaskRequester.BingTranslate.translate_text",
        lambda *args, **kwargs: response.raise_for_status(),
    )
    monkeypatch.setattr(TaskRequester, "is_cancel_requested", classmethod(lambda cls: False))
    monkeypatch.setattr(TaskRequester, "FREE_QUOTA_NOTIFIED", set())
    monkeypatch.setattr(Engine, "get", classmethod(lambda cls: SimpleNamespace(get_status=lambda: Engine.Status.TRANSLATING)))
    toasts = []
    logged = []
    monkeypatch.setattr(requester, "emit", lambda event, data: toasts.append((event, data)))
    monkeypatch.setattr(requester, "error", lambda message, exc: logged.append(message))

    messages = [{"role": "user", "content": '```jsonline\n{"0": "hello"}\n```'}]
    call = requester.request_bing if provider == Base.APIFormat.BING else requester.request_googlefree
    for _ in range(2):
        assert call(messages)[0] is True
    hint = Localizer.get().free_translation_quota_hint
    assert hint in requester.last_error_message
    assert "429" in requester.last_error_message
    assert len(logged) == 2 and all(hint in message for message in logged)
    assert toasts == [(Base.Event.APP_TOAST_SHOW, {"type": Base.ToastType.WARNING, "message": hint})]


def test_quota_hint_distinguishes_access_errors_and_nonfree_providers():
    requester = _googlefree_requester()
    assert requester._free_translation_quota_hint(RuntimeError("QUOTA_EXCEEDED"))
    assert requester._free_translation_quota_hint(RuntimeError("请求过于频繁"))
    assert not requester._free_translation_quota_hint(RuntimeError("403: Forbidden"))
    assert not requester._free_translation_quota_hint(RuntimeError("SSL connection timeout"))
    requester.platform["api_format"] = Base.APIFormat.OPENAI
    assert not requester._free_translation_quota_hint(RuntimeError("HTTP 429: too many requests"))
