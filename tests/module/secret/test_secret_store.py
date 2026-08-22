import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from module.Secret.SecretStore import MemoryBackend, SecretStore, WindowsCredBackend


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
    store.store_keys({"id": 1}, ["cred-a"])
    assert store.resolve_keys({"id": 1, "api_key": ["stale-plain"]}) == ["cred-a"]


def test_store_success_clears_plaintext_semantics() -> None:
    store = _store(MemoryBackend())
    platform = {"id": 2, "api_key": ["old"]}
    assert store.store_keys(platform, ["k1", " k2 "]) is True
    # 存储侧自动去空白；空 key 过滤
    assert store.resolve_keys({"id": 2}) == ["k1", "k2"]


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
    store.clear_keys(platform)
    assert store.resolve_keys({"id": 4, "api_key": ["plain"]}) == ["plain"]


def test_migrate_platforms_moves_plaintext_once() -> None:
    store = _store(MemoryBackend())
    platforms = [
        {"id": 10, "api_key": ["secret-1"]},
        {"id": 11, "api_key": []},
        {"id": 12},
        "not-a-dict",
    ]
    assert store.migrate_platforms(platforms) == 1
    assert platforms[0]["api_key"] == []
    assert store.resolve_keys({"id": 10}) == ["secret-1"]
    # 幂等：无明文后不再迁移
    assert store.migrate_platforms(platforms) == 0


def test_platform_without_id_never_touches_backend() -> None:
    store = _store(MemoryBackend())
    platform = {"api_key": ["plain"]}
    assert store.store_keys(platform, ["k"]) is False
    assert store.resolve_keys(platform) == ["plain"]
    assert store.backend.storage == {}


def test_resolve_returns_copy_not_internal_cache() -> None:
    store = _store(MemoryBackend())
    store.store_keys({"id": 20}, ["k"])
    keys = store.resolve_keys({"id": 20})
    keys.append("mutated")
    assert store.resolve_keys({"id": 20}) == ["k"]


def test_resolve_skips_blank_entries() -> None:
    store = _store(MemoryBackend())
    assert store.resolve_keys({"id": 21, "api_key": ["", "  ", "valid"]}) == ["valid"]


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
