"""平台 API 密钥的安全存储。

密钥默认写入 Windows 凭据管理器（Generic Credential，ctypes 调 advapi32，
无三方依赖）；非 Windows 或凭据写入失败时回退 config.json 明文，保证功能
不断。读取统一走 ``SecretStore.get().resolve_keys(platform)``：凭据优先，
无凭据回退 platform 的明文字段。

注意：本模块不得在持有 Config.CONFIG_LOCK 的路径里触发 Config().load()
（LogManager/Localizer 同理）——该锁不可重入，锁内加载会死锁。
"""

import ctypes
import json
import threading

from base.compat import Self


CRED_TARGET_PREFIX = "RenpyBox:secret:"


class MemoryBackend:
    """进程内字典实现，供测试与非 Windows 回退。"""

    def __init__(self) -> None:
        self.storage: dict[str, str] = {}

    def save(self, target: str, blob: str) -> bool:
        self.storage[target] = blob
        return True

    def load(self, target: str) -> str | None:
        return self.storage.get(target)

    def delete(self, target: str) -> bool:
        if target in self.storage:
            del self.storage[target]
            return True
        return False


class _FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.c_ulong),
        ("dwHighDateTime", ctypes.c_ulong),
    ]


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", ctypes.c_ulong),
        ("Type", ctypes.c_ulong),
        ("TargetName", ctypes.c_wchar_p),
        ("Comment", ctypes.c_wchar_p),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", ctypes.c_ulong),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
        ("Persist", ctypes.c_ulong),
        ("AttributeCount", ctypes.c_ulong),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", ctypes.c_wchar_p),
        ("UserName", ctypes.c_wchar_p),
    ]


class WindowsCredBackend:
    """Windows 凭据管理器实现（CredWriteW / CredReadW / CredDeleteW）。"""

    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    def __init__(self) -> None:
        self._ctypes = ctypes
        self._advapi32 = ctypes.windll.advapi32

    def save(self, target: str, blob: str) -> bool:
        ctypes = self._ctypes
        data = blob.encode("utf-8")
        buffer = ctypes.create_string_buffer(data, len(data))
        credential = _CREDENTIALW()
        credential.Type = self.CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.Comment = None
        credential.CredentialBlobSize = len(data)
        credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))
        credential.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        credential.AttributeCount = 0
        credential.Attributes = None
        credential.TargetAlias = None
        credential.UserName = None
        return bool(self._advapi32.CredWriteW(ctypes.byref(credential), 0))

    def load(self, target: str) -> str | None:
        ctypes = self._ctypes
        pointer = ctypes.POINTER(_CREDENTIALW)()
        if not self._advapi32.CredReadW(
            target,
            self.CRED_TYPE_GENERIC,
            0,
            ctypes.byref(pointer),
        ):
            return None
        try:
            credential = pointer.contents
            if not credential.CredentialBlob or credential.CredentialBlobSize <= 0:
                return None
            data = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            return data.decode("utf-8", errors = "replace")
        finally:
            self._advapi32.CredFree(pointer)

    def delete(self, target: str) -> bool:
        return bool(self._advapi32.CredDeleteW(
            target,
            self.CRED_TYPE_GENERIC,
            0,
        ))


class SecretStore:

    _instance: "SecretStore | None" = None

    def __init__(self, backend: MemoryBackend | WindowsCredBackend | None = None) -> None:
        if backend is None:
            import os

            backend = WindowsCredBackend() if os.name == "nt" else MemoryBackend()
        self.backend = backend
        # Windows 凭据是系统调用，请求轮换路径高频读取，只在 miss 时落凭据库；
        # 进程内 UI 编辑通过 store_keys 同步更新缓存
        self._cache: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    @classmethod
    def get(cls) -> Self:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def _platform_id(cls, platform: dict) -> str | None:
        raw = platform.get("id") if isinstance(platform, dict) else None
        text = str(raw).strip() if raw is not None else ""
        return text or None

    @classmethod
    def _target(cls, platform_id: str) -> str:
        return f"{CRED_TARGET_PREFIX}{platform_id}"

    def resolve_keys(self, platform: dict) -> list[str]:
        """密钥解析的唯一入口：凭据优先，回退明文字段。"""
        platform_id = self._platform_id(platform)
        if platform_id is not None:
            with self._lock:
                cached = self._cache.get(platform_id)
            if cached is None:
                cached = self._load_from_backend(platform_id)
            if cached:
                return list(cached)

        keys = platform.get("api_key") if isinstance(platform, dict) else None
        if isinstance(keys, list) and keys:
            return [str(key) for key in keys if str(key).strip()]
        return []

    def _load_from_backend(self, platform_id: str) -> list[str]:
        try:
            blob = self.backend.load(self._target(platform_id))
            keys = json.loads(blob) if blob else None
        except Exception:
            keys = None
        if not isinstance(keys, list):
            keys = []
        keys = [str(key) for key in keys if str(key).strip()]
        with self._lock:
            self._cache[platform_id] = keys
        return keys

    def store_keys(self, platform: dict, keys: list[str]) -> bool:
        """写入凭据库。返回 False 表示不可持久化（调用方保留明文回退）。"""
        platform_id = self._platform_id(platform)
        if platform_id is None:
            return False

        cleaned = [str(key).strip() for key in (keys or []) if str(key).strip()]
        try:
            if cleaned:
                ok = self.backend.save(
                    self._target(platform_id),
                    json.dumps(cleaned, ensure_ascii = False),
                )
            else:
                ok = self.backend.delete(self._target(platform_id))
        except Exception:
            ok = False

        if ok:
            with self._lock:
                self._cache[platform_id] = list(cleaned)
        return ok

    def clear_keys(self, platform: dict) -> None:
        platform_id = self._platform_id(platform)
        if platform_id is None:
            return
        try:
            self.backend.delete(self._target(platform_id))
        except Exception:
            pass
        with self._lock:
            self._cache.pop(platform_id, None)

    def migrate_platforms(self, platforms: list) -> int:
        """把明文密钥迁入凭据库并清空明文字段。返回迁移成功的平台数。"""
        migrated = 0
        for platform in platforms or []:
            if not isinstance(platform, dict):
                continue
            keys = platform.get("api_key")
            if not (isinstance(keys, list) and keys):
                continue
            if self.store_keys(platform, keys):
                platform["api_key"] = []
                migrated += 1
        return migrated
