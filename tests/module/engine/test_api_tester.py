import json
from types import SimpleNamespace

from base.Base import Base
from module.Config import Config
from module.Engine.API.APITester import APITester
import module.Engine.API.APITester as api_tester_module
from module.Engine.Engine import Engine
from module.Secret.SecretStore import SecretStore


def _tester(logs: list[str], events: list[tuple]) -> APITester:
    tester = object.__new__(APITester)
    tester.print = lambda message: logs.append(str(message))
    tester.info = lambda message: logs.append(str(message))
    tester.warning = lambda message: logs.append(str(message))
    tester.error = lambda message: logs.append(str(message))
    tester.emit = lambda event, data: events.append((event, data))
    return tester


def test_api_tester_uses_one_key_per_request_and_redacts_all_output(monkeypatch) -> None:
    secrets = ["fake-secret-a", "fake-secret-b"]
    platform = {
        "id": 3,
        "credential_id": "a" * 32,
        "api_format": Base.APIFormat.OPENAI,
        "api_key": [],
    }
    config = Config(platforms=[platform])
    logs: list[str] = []
    events: list[tuple] = []
    seen_platforms: list[dict] = []

    class RequesterStub:
        @classmethod
        def reset(cls) -> None:
            return None

        def __init__(self, _config: Config, test_platform: dict, _round: int) -> None:
            self.platform = test_platform
            self.last_error_message = ""
            seen_platforms.append(test_platform)

        def request(self, _messages: list[dict], **_kwargs):
            key = self.platform["api_key"][0]
            if key == secrets[1]:
                self.error("request failed", RuntimeError(f"echoed {key}"))
                self.last_error_message = f"upstream rejected {key}"
                return True, "", "", 0, 0
            return False, "", f"response echoed {key}", 0, 0

    engine = SimpleNamespace(set_status=lambda _status: None)
    secret_store = SimpleNamespace(resolve_keys=lambda _platform: list(secrets))
    monkeypatch.setattr(Config, "load", lambda self: config)
    monkeypatch.setattr(Engine, "get", lambda: engine)
    monkeypatch.setattr(SecretStore, "get", lambda: secret_store)
    monkeypatch.setattr(api_tester_module, "TaskRequester", RequesterStub)

    _tester(logs, events).platform_test_start_target("event", {"id": 3})

    assert [item["api_key"] for item in seen_platforms] == [
        [secrets[0]],
        [secrets[1]],
    ]
    assert all("id" not in item and "credential_id" not in item for item in seen_platforms)
    visible = json.dumps({"logs": logs, "events": events}, ensure_ascii = False)
    assert all(secret not in visible for secret in secrets)
    assert "共测试 2 个接口，成功 1 个，失败 1 个" in visible
    assert "#2" in visible
    assert events[-1][0] == Base.Event.PLATFORM_TEST_DONE
    assert events[-1][1]["result"] is False


def test_api_tester_without_keys_still_performs_one_request(monkeypatch) -> None:
    platform = {"id": 4, "api_format": Base.APIFormat.OPENAI, "api_key": []}
    config = Config(platforms=[platform])
    logs: list[str] = []
    events: list[tuple] = []
    attempts: list[str] = []

    class RequesterStub:
        last_error_message = ""

        @classmethod
        def reset(cls) -> None:
            return None

        def __init__(self, _config: Config, test_platform: dict, _round: int) -> None:
            self.platform = test_platform

        def request(self, _messages: list[dict], **_kwargs):
            attempts.append(self.platform["api_key"][0])
            return False, "", "ok", 0, 0

    engine = SimpleNamespace(set_status=lambda _status: None)
    secret_store = SimpleNamespace(resolve_keys=lambda _platform: [])
    monkeypatch.setattr(Config, "load", lambda self: config)
    monkeypatch.setattr(Engine, "get", lambda: engine)
    monkeypatch.setattr(SecretStore, "get", lambda: secret_store)
    monkeypatch.setattr(api_tester_module, "TaskRequester", RequesterStub)

    _tester(logs, events).platform_test_start_target("event", {"id": 4})

    assert attempts == ["no_key_required"]
    assert "共测试 1 个接口，成功 1 个，失败 0 个" in "\n".join(logs)
    assert events[-1][1]["result"] is True
