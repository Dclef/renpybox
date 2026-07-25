from types import SimpleNamespace

from base.Base import Base
from module.Config import Config
from module.Engine.TaskRequester import TaskRequester, ThinkingLevel


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
    monkeypatch.setattr(requester, "generate_google_args", lambda *args: {})

    result = requester.request_google([], ThinkingLevel.OFF, {})

    assert result == (True, None, None, None, None)
    assert stream.closed is True


def test_close_stream_tolerates_missing_close_method() -> None:
    TaskRequester._close_stream(object())
