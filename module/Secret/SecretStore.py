"""平台 API 密钥的安全存储。

密钥默认写入 Windows 凭据管理器（Generic Credential，ctypes 调 advapi32，
无三方依赖）；非 Windows 或凭据写入失败时回退 config.json 明文，保证功能
不断。凭据使用不随界面排序变化的 ``credential_id`` 定位，数字 ``id`` 只作
旧版迁移别名。读取统一走 ``SecretStore.get().resolve_keys(platform)``。

注意：本模块不得在持有 Config.CONFIG_LOCK 的路径里触发 Config().load()
（LogManager/Localizer 同理）——该锁不可重入，锁内加载会死锁。
"""

import ctypes
import copy
import json
import os
import threading
import uuid

from base.compat import Self


CRED_TARGET_PREFIX = "RenpyBox:secret:"
CRED_TARGET_V2_PREFIX = f"{CRED_TARGET_PREFIX}v2:"
CREDENTIAL_ID_FIELD = "credential_id"
LEGACY_CREDENTIAL_ID_FIELD = "legacy_credential_id"


class MemoryBackend:
    """进程内字典实现，仅供测试显式注入。"""

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


class UnavailableBackend:
    """不可持久化后端，让调用方明确保留配置明文。"""

    def save(self, target: str, blob: str) -> bool:
        return False

    def load(self, target: str) -> str | None:
        return None

    def delete(self, target: str) -> bool:
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

    def __init__(
        self,
        backend: MemoryBackend | UnavailableBackend | WindowsCredBackend | None = None,
    ) -> None:
        if backend is None:
            backend = WindowsCredBackend() if os.name == "nt" else UnavailableBackend()
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
    def _legacy_target(cls, platform_id: str) -> str:
        return f"{CRED_TARGET_PREFIX}{platform_id}"

    @classmethod
    def _credential_target(cls, credential_id: str) -> str:
        return f"{CRED_TARGET_V2_PREFIX}{credential_id}"

    @staticmethod
    def _normalize_credential_id(value: object) -> str | None:
        text = str(value).strip() if value is not None else ""
        if text == "":
            return None
        try:
            return uuid.UUID(text).hex
        except (ValueError, AttributeError):
            return None

    @classmethod
    def _legacy_id(cls, platform: dict) -> str | None:
        raw = (
            platform.get(LEGACY_CREDENTIAL_ID_FIELD)
            if isinstance(platform, dict)
            else None
        )
        text = str(raw).strip() if raw is not None else ""
        return text or None

    @classmethod
    def ensure_platform_identity(
        cls,
        platform: dict,
        *,
        preserve_legacy: bool = True,
    ) -> bool:
        """补齐单个平台的稳定凭据身份，返回是否修改。"""
        if not isinstance(platform, dict):
            return False

        raw = platform.get(CREDENTIAL_ID_FIELD)
        normalized = cls._normalize_credential_id(raw)
        if normalized is not None:
            if raw != normalized:
                platform[CREDENTIAL_ID_FIELD] = normalized
                return True
            return False

        if cls._platform_id(platform) is None:
            return False
        platform[CREDENTIAL_ID_FIELD] = uuid.uuid4().hex
        legacy_id = cls._platform_id(platform)
        if (
            preserve_legacy
            and legacy_id is not None
            and cls._legacy_id(platform) is None
        ):
            platform[LEGACY_CREDENTIAL_ID_FIELD] = legacy_id
        return True

    @classmethod
    def ensure_platform_identities(cls, platforms: list) -> int:
        """补齐并去重一组平台的稳定身份，返回修改的平台数。"""
        changed = 0
        seen: set[str] = set()
        for platform in platforms or []:
            if not isinstance(platform, dict):
                continue

            normalized = cls._normalize_credential_id(
                platform.get(CREDENTIAL_ID_FIELD)
            )
            if normalized is None:
                platform.pop(CREDENTIAL_ID_FIELD, None)
                if not cls.ensure_platform_identity(platform):
                    continue
                normalized = platform[CREDENTIAL_ID_FIELD]
                changed += 1
            elif normalized in seen:
                platform[CREDENTIAL_ID_FIELD] = uuid.uuid4().hex
                platform.pop(LEGACY_CREDENTIAL_ID_FIELD, None)
                normalized = platform[CREDENTIAL_ID_FIELD]
                changed += 1
            else:
                if platform.get(CREDENTIAL_ID_FIELD) != normalized:
                    platform[CREDENTIAL_ID_FIELD] = normalized
                    changed += 1
            seen.add(normalized)
        return changed

    @classmethod
    def _targets_for_read(cls, platform: dict) -> list[str]:
        credential_id = cls._normalize_credential_id(
            platform.get(CREDENTIAL_ID_FIELD) if isinstance(platform, dict) else None
        )
        if credential_id is not None:
            targets = [cls._credential_target(credential_id)]
            legacy_id = cls._legacy_id(platform)
            if legacy_id is not None:
                targets.append(cls._legacy_target(legacy_id))
            return targets

        platform_id = cls._platform_id(platform)
        return [cls._legacy_target(platform_id)] if platform_id is not None else []

    def resolve_keys(self, platform: dict) -> list[str]:
        """密钥解析的唯一入口：凭据优先，回退明文字段。"""
        for target in self._targets_for_read(platform):
            keys = self._load_target(target)
            if keys:
                return list(keys)

        keys = platform.get("api_key") if isinstance(platform, dict) else None
        if isinstance(keys, list) and keys:
            return [str(key) for key in keys if str(key).strip()]
        return []

    def _load_target(self, target: str) -> list[str]:
        with self._lock:
            cached = self._cache.get(target)
        if cached is not None:
            return list(cached)

        try:
            blob = self.backend.load(target)
            keys = json.loads(blob) if blob else None
        except Exception:
            keys = None
        if not isinstance(keys, list):
            keys = []
        keys = [str(key) for key in keys if str(key).strip()]
        with self._lock:
            self._cache[target] = keys
        return list(keys)

    def _store_target(self, target: str, keys: list[str]) -> bool:
        try:
            ok = self.backend.save(
                target,
                json.dumps(keys, ensure_ascii = False),
            )
        except Exception:
            ok = False
        if ok:
            with self._lock:
                self._cache[target] = list(keys)
        return ok

    def store_keys(self, platform: dict, keys: list[str]) -> bool:
        """写入凭据库。返回 False 表示不可持久化（调用方保留明文回退）。"""
        if not isinstance(platform, dict):
            return False

        self.ensure_platform_identity(platform)
        credential_id = self._normalize_credential_id(platform.get(CREDENTIAL_ID_FIELD))
        if credential_id is None:
            return False

        cleaned = [str(key).strip() for key in (keys or []) if str(key).strip()]
        if not cleaned:
            return self.clear_keys(platform)
        return self._store_target(self._credential_target(credential_id), cleaned)

    def has_persisted_credentials(self, platform: dict) -> bool:
        """判断是否存在会遮蔽明文回退的凭据；读取异常按存在处理。"""
        for target in self._targets_for_read(platform):
            with self._lock:
                cached = self._cache.get(target)
            if cached:
                return True
            try:
                if self.backend.load(target) is not None:
                    return True
            except Exception:
                return True
        return False

    def _delete_target(self, target: str) -> bool:
        try:
            blob = self.backend.load(target)
        except Exception:
            return False

        if blob is not None:
            try:
                if not self.backend.delete(target):
                    return False
            except Exception:
                return False

        with self._lock:
            self._cache.pop(target, None)
        return True

    def clear_keys(self, platform: dict) -> bool:
        """清除稳定身份及明确旧别名对应的凭据；失败时返回 False。"""
        targets = self._targets_for_read(platform)
        return all(self._delete_target(target) for target in targets)

    def migrate_platforms(self, platforms: list) -> int:
        """把旧凭据或明文写入 v2；成功后清空内存中的明文字段。"""
        migrated = 0
        for platform in platforms or []:
            if not isinstance(platform, dict):
                continue

            credential_id = self._normalize_credential_id(
                platform.get(CREDENTIAL_ID_FIELD)
            )
            if credential_id is None:
                continue

            target = self._credential_target(credential_id)
            secure_keys = self._load_target(target)
            plaintext = platform.get("api_key")
            plaintext_keys = (
                [str(key).strip() for key in plaintext if str(key).strip()]
                if isinstance(plaintext, list)
                else []
            )
            source_keys = secure_keys
            if not source_keys:
                legacy_id = self._legacy_id(platform)
                if legacy_id is not None:
                    source_keys = self._load_target(self._legacy_target(legacy_id))
            if not source_keys:
                source_keys = plaintext_keys
            if not source_keys:
                continue

            if not secure_keys and not self._store_target(target, source_keys):
                continue

            changed = not secure_keys
            if isinstance(plaintext, list) and plaintext:
                platform["api_key"] = []
                changed = True
            if changed:
                migrated += 1
        return migrated

    def _cleanup_legacy_keys(self, platforms: list) -> None:
        """v2 已确认可读后，尽力清理显式旧别名，不影响启动。"""
        for platform in platforms or []:
            if not isinstance(platform, dict):
                continue
            credential_id = self._normalize_credential_id(
                platform.get(CREDENTIAL_ID_FIELD)
            )
            legacy_id = self._legacy_id(platform)
            if credential_id is None or legacy_id is None:
                continue
            if not self._load_target(self._credential_target(credential_id)):
                continue
            self._delete_target(self._legacy_target(legacy_id))

    def migrate_config(self, config: object) -> int:
        """先持久化稳定身份，再迁移凭据，避免中途失败造成密钥失联。"""
        platforms = getattr(config, "platforms", None)
        if not isinstance(platforms, list):
            return 0

        original = copy.deepcopy(platforms)
        if self.ensure_platform_identities(platforms) > 0:
            try:
                config.save(strict = True)
            except Exception:
                platforms[:] = original
                raise

        migrated = self.migrate_platforms(platforms)
        if migrated > 0:
            config.save(strict = True)
        self._cleanup_legacy_keys(platforms)
        return migrated
