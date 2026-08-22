import copy
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import module.Secret.SecretStore as secret_store_module
from module.Secret.SecretStore import (
    CRED_TARGET_PREFIX,
    CRED_TARGET_V2_PREFIX,
    CREDENTIAL_ID_FIELD,
    LEGACY_CREDENTIAL_ID_FIELD,
    MemoryBackend,
    SecretStore,
    UnavailableBackend,
    WindowsCredBackend,
)


class _FailingBackend(MemoryBackend):
    """模拟凭据库不可用（写权限受限/已满）。"""

    def save(self, target: str, blob: str) -> bool:
        return False


def _store(backend) -> SecretStore:
    return SecretStore(backend=backend)


def test_resolve_falls_back_to_plaintext_without_credential() -> None:
    store = _store(MemoryBackend())
    platform = {"id": 1, "api_key": ["plain-a", "plain-b"]}
    assert store.resolve_keys(platform) == ["plain-a", "plain-b"]


def test_resolve_prefers_credential_over_plaintext() -> None:
    store = _store(MemoryBackend())
    platform = {"id": 1}
    store.store_keys(platform, ["cred-a"])
    platform["api_key"] = ["stale-plain"]
    assert store.resolve_keys(platform) == ["cred-a"]


def test_store_success_clears_plaintext_semantics() -> None:
    store = _store(MemoryBackend())
    platform = {"id": 2, "api_key": ["old"]}
    assert store.store_keys(platform, ["k1", " k2 "]) is True
    # 存储侧自动去空白；空 key 过滤
    assert store.resolve_keys(platform) == ["k1", "k2"]


def test_store_failure_returns_false_for_fallback() -> None:
    store = _store(_FailingBackend())
    platform = {"id": 3}
    assert store.store_keys(platform, ["k"]) is False
    # 失败后 resolve 仍回退明文
    platform["api_key"] = ["fallback"]
    assert store.resolve_keys(platform) == ["fallback"]


def test_clear_keys_removes_credential_and_cache() -> None:
    store = _store(MemoryBackend())
    platform = {"id": 4}
    store.store_keys(platform, ["k"])
    assert store.clear_keys(platform) is True
    platform["api_key"] = ["plain"]
    assert store.resolve_keys(platform) == ["plain"]


def test_migrate_config_moves_plaintext_once() -> None:
    store = _store(MemoryBackend())

    class ConfigStub:
        def __init__(self) -> None:
            self.platforms = [
                {"id": 10, "api_key": ["secret-1"]},
                {"id": 11, "api_key": []},
                {"id": 12},
                "not-a-dict",
            ]
            self.saved: list[list] = []

        def save(self, *, strict: bool = False) -> None:
            assert strict is True
            self.saved.append(copy.deepcopy(self.platforms))

    config = ConfigStub()
    assert store.migrate_config(config) == 1
    assert config.platforms[0]["api_key"] == []
    assert store.resolve_keys(config.platforms[0]) == ["secret-1"]
    assert len(config.saved) == 2
    # 幂等：无明文、v2 已就绪后不再迁移
    assert store.migrate_config(config) == 0


def test_platform_without_id_never_touches_backend() -> None:
    store = _store(MemoryBackend())
    platform = {"api_key": ["plain"]}
    assert store.store_keys(platform, ["k"]) is False
    assert store.resolve_keys(platform) == ["plain"]
    assert store.backend.storage == {}


def test_resolve_returns_copy_not_internal_cache() -> None:
    store = _store(MemoryBackend())
    platform = {"id": 20}
    store.store_keys(platform, ["k"])
    keys = store.resolve_keys(platform)
    keys.append("mutated")
    assert store.resolve_keys(platform) == ["k"]


def test_resolve_skips_blank_entries() -> None:
    store = _store(MemoryBackend())
    assert store.resolve_keys({"id": 21, "api_key": ["", "  ", "valid"]}) == ["valid"]


def test_stable_identity_survives_numeric_reorder() -> None:
    backend = MemoryBackend()
    store = _store(backend)
    first = {"id": 0}
    second = {"id": 1}
    assert store.store_keys(first, ["key-a"]) is True
    assert store.store_keys(second, ["key-b"]) is True

    first["id"], second["id"] = second["id"], first["id"]

    assert store.resolve_keys(first) == ["key-a"]
    assert store.resolve_keys(second) == ["key-b"]


def test_stable_identity_never_falls_back_to_reused_numeric_target() -> None:
    backend = MemoryBackend()
    backend.storage[f"{CRED_TARGET_PREFIX}3"] = '["orphan-key"]'
    store = _store(backend)
    platform = {"id": 3, "api_key": ["new-key"]}
    SecretStore.ensure_platform_identity(platform, preserve_legacy = False)

    assert store.resolve_keys(platform) == ["new-key"]


def test_legacy_credential_migrates_to_v2_after_identity_save() -> None:
    backend = MemoryBackend()
    backend.storage[f"{CRED_TARGET_PREFIX}7"] = '["legacy-key"]'
    store = _store(backend)

    class ConfigStub:
        def __init__(self) -> None:
            self.platforms = [{"id": 7, "api_key": []}]
            self.saved: list[list[dict]] = []

        def save(self, *, strict: bool = False) -> None:
            assert strict is True
            self.saved.append(copy.deepcopy(self.platforms))

    config = ConfigStub()
    assert store.migrate_config(config) == 1

    platform = config.platforms[0]
    credential_id = platform[CREDENTIAL_ID_FIELD]
    assert config.saved[0][0][LEGACY_CREDENTIAL_ID_FIELD] == "7"
    assert backend.storage[f"{CRED_TARGET_V2_PREFIX}{credential_id}"] == '["legacy-key"]'
    assert f"{CRED_TARGET_PREFIX}7" not in backend.storage
    assert _store(backend).resolve_keys(platform) == ["legacy-key"]


def test_identity_save_failure_keeps_legacy_and_plaintext_untouched() -> None:
    backend = MemoryBackend()
    backend.storage[f"{CRED_TARGET_PREFIX}8"] = '["legacy-key"]'
    store = _store(backend)

    class ConfigStub:
        def __init__(self) -> None:
            self.platforms = [{"id": 8, "api_key": ["plain-key"]}]

        def save(self, *, strict: bool = False) -> None:
            raise OSError("disk full")

    config = ConfigStub()
    with pytest.raises(OSError, match="disk full"):
        store.migrate_config(config)

    assert config.platforms == [{"id": 8, "api_key": ["plain-key"]}]
    assert backend.storage == {f"{CRED_TARGET_PREFIX}8": '["legacy-key"]'}


def test_plaintext_save_failure_keeps_v1_and_v2_recovery_paths() -> None:
    backend = MemoryBackend()
    backend.storage[f"{CRED_TARGET_PREFIX}8"] = '["legacy-key"]'
    store = _store(backend)

    class ConfigStub:
        def __init__(self) -> None:
            self.platforms = [{"id": 8, "api_key": ["plain-key"]}]
            self.saved: list[list[dict]] = []

        def save(self, *, strict: bool = False) -> None:
            assert strict is True
            if self.saved:
                raise OSError("disk full")
            self.saved.append(copy.deepcopy(self.platforms))

    config = ConfigStub()
    with pytest.raises(OSError, match="disk full"):
        store.migrate_config(config)

    disk_platform = config.saved[0][0]
    credential_id = disk_platform[CREDENTIAL_ID_FIELD]
    assert disk_platform["api_key"] == ["plain-key"]
    assert f"{CRED_TARGET_PREFIX}8" in backend.storage
    assert f"{CRED_TARGET_V2_PREFIX}{credential_id}" in backend.storage
    assert _store(backend).resolve_keys(disk_platform) == ["legacy-key"]


def test_non_windows_default_backend_preserves_plaintext(monkeypatch) -> None:
    monkeypatch.setattr(secret_store_module.os, "name", "posix")
    store = SecretStore()
    assert isinstance(store.backend, UnavailableBackend)

    platform = {"id": 9, "api_key": ["plain-key"]}
    assert store.store_keys(platform, ["secure-key"]) is False
    assert store.resolve_keys(platform) == ["plain-key"]

    class ConfigStub:
        def __init__(self) -> None:
            self.platforms = [platform]

        def save(self, *, strict: bool = False) -> None:
            assert strict is True

    assert store.migrate_config(ConfigStub()) == 0
    assert platform["api_key"] == ["plain-key"]


def test_clear_removes_v2_and_explicit_legacy_targets() -> None:
    backend = MemoryBackend()
    store = _store(backend)
    platform = {"id": 5}
    SecretStore.ensure_platform_identity(platform)
    credential_id = platform[CREDENTIAL_ID_FIELD]
    backend.storage[f"{CRED_TARGET_PREFIX}5"] = '["legacy-key"]'
    backend.storage[f"{CRED_TARGET_V2_PREFIX}{credential_id}"] = '["stable-key"]'

    assert store.clear_keys(platform) is True
    assert backend.storage == {}


def test_duplicate_stable_id_is_regenerated_without_legacy_alias() -> None:
    shared_id = uuid.uuid4().hex
    platforms = [
        {"id": 1, CREDENTIAL_ID_FIELD: shared_id},
        {"id": 2, CREDENTIAL_ID_FIELD: shared_id},
    ]

    assert SecretStore.ensure_platform_identities(platforms) == 1
    assert platforms[0][CREDENTIAL_ID_FIELD] != platforms[1][CREDENTIAL_ID_FIELD]
    assert LEGACY_CREDENTIAL_ID_FIELD not in platforms[1]


@pytest.mark.skipif(sys.platform != "win32", reason = "Windows credential manager only")
class TestWindowsCredBackendRoundTrip:
    def test_write_read_delete_round_trip(self) -> None:
        backend = WindowsCredBackend()
        target = f"RenpyBox:test:{uuid.uuid4().hex[:12]}"
        try:
            assert backend.save(target, '["real-key"]') is True
            assert backend.load(target) == '["real-key"]'
            # 覆盖写
            assert backend.save(target, '["real-key-2"]') is True
            assert backend.load(target) == '["real-key-2"]'
        finally:
            assert backend.delete(target) is True
        assert backend.load(target) is None

    def test_load_missing_target_returns_none(self) -> None:
        backend = WindowsCredBackend()
        assert backend.load(f"RenpyBox:test:missing-{uuid.uuid4().hex[:8]}") is None
