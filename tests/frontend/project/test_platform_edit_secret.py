from types import SimpleNamespace

from base.Base import Base
from frontend.Project.PlatformEditPage import PlatformEditPage
from module.Config import Config
from module.Secret.SecretStore import (
    MemoryBackend,
    SecretStore,
    UnavailableBackend,
)


def _page(platform: dict, events: list[tuple]) -> SimpleNamespace:
    return SimpleNamespace(
        platform=platform,
        emit=lambda event, data: events.append((event, data)),
    )


def test_plaintext_key_save_failure_is_reported_and_keeps_edit_state(monkeypatch) -> None:
    platform = {"id": 0, "api_key": []}
    config = Config(platforms=[platform])
    events: list[tuple] = []
    strict_values: list[bool] = []

    def fail_save(self, *, strict: bool = False):
        strict_values.append(strict)
        raise OSError("disk full")

    monkeypatch.setattr(Config, "load", lambda self: config)
    monkeypatch.setattr(Config, "save", fail_save)
    monkeypatch.setattr(
        SecretStore,
        "get",
        lambda: SecretStore(UnavailableBackend()),
    )

    result = PlatformEditPage._save_api_keys(_page(platform, events), ["new-secret"])

    assert result is False
    assert platform["api_key"] == ["new-secret"]
    assert strict_values == [True]
    assert events[-1][0] == Base.Event.APP_TOAST_SHOW


def test_failed_credential_clear_does_not_save_empty_plaintext(monkeypatch) -> None:
    class DeleteFailBackend(MemoryBackend):
        def delete(self, target: str) -> bool:
            return False

    backend = DeleteFailBackend()
    store = SecretStore(backend)
    platform = {"id": 0, "api_key": []}
    assert store.store_keys(platform, ["kept-secret"]) is True
    config = Config(platforms=[platform])
    events: list[tuple] = []
    save_calls = []
    monkeypatch.setattr(Config, "load", lambda self: config)
    monkeypatch.setattr(Config, "save", lambda self, **_kwargs: save_calls.append(True))
    monkeypatch.setattr(SecretStore, "get", lambda: store)

    result = PlatformEditPage._save_api_keys(_page(platform, events), [])

    assert result is False
    assert store.resolve_keys(platform) == ["kept-secret"]
    assert save_calls == []
    assert events[-1][0] == Base.Event.APP_TOAST_SHOW


def test_failed_credential_update_does_not_get_shadowed_by_old_key(monkeypatch) -> None:
    class ToggleSaveBackend(MemoryBackend):
        fail_save = False

        def save(self, target: str, blob: str) -> bool:
            if self.fail_save:
                return False
            return super().save(target, blob)

    backend = ToggleSaveBackend()
    store = SecretStore(backend)
    platform = {"id": 0, "api_key": []}
    assert store.store_keys(platform, ["old-secret"]) is True
    backend.fail_save = True
    config = Config(platforms=[platform])
    events: list[tuple] = []
    save_calls = []
    monkeypatch.setattr(Config, "load", lambda self: config)
    monkeypatch.setattr(Config, "save", lambda self, **_kwargs: save_calls.append(True))
    monkeypatch.setattr(SecretStore, "get", lambda: store)

    result = PlatformEditPage._save_api_keys(_page(platform, events), ["new-secret"])

    assert result is False
    assert store.resolve_keys(platform) == ["old-secret"]
    assert platform["api_key"] == []
    assert save_calls == []
    assert events[-1][0] == Base.Event.APP_TOAST_SHOW
