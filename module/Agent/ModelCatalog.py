"""运行时的模型能力目录缓存。

不维护静态模型表：容量从供应商的 ``/models`` 接口现取（见
``module.Engine.API.ModelList.list_model_capabilities``），按 ``接口地址 + 格式``
缓存，过期后由后台线程静默刷新。

取不到（供应商只返回 id、网络失败、没配置密钥）时返回空目录，由
``ModelBudget`` 的内置兜底接管；查目录失败永远不会挡住翻译。
"""

from __future__ import annotations

import threading
import time
from typing import Any, Mapping


# 缓存有效期：目录变化不频繁，一小时足够，过期后后台刷新。
CATALOG_TTL_SECONDS = 3600.0
# 同一时间只允许一条刷新线程，避免连续开轮次把接口打满。
_REFRESHING: set[str] = set()
_LOCK = threading.Lock()
_CATALOG: dict[str, dict[str, tuple[int, int]]] = {}
_STAMP: dict[str, float] = {}


def _cache_key(platform: Mapping[str, Any] | None) -> str:
    config = platform if isinstance(platform, Mapping) else {}
    api_url = str(config.get("api_url") or "").strip().casefold()
    api_format = str(config.get("api_format") or "").strip().casefold()
    return f"{api_format}|{api_url}"


def _is_stale(key: str) -> bool:
    stamp = _STAMP.get(key)
    if stamp is None:
        return True
    return (time.monotonic() - stamp) > CATALOG_TTL_SECONDS


def get(platform: Mapping[str, Any] | None) -> dict[str, tuple[int, int]]:
    """返回缓存目录（不联网）；没有缓存时返回空字典。"""

    with _LOCK:
        return dict(_CATALOG.get(_cache_key(platform), {}))


def put(key: str, catalog: dict[str, tuple[int, int]]) -> None:
    """写入目录；供接口页读取模型列表时顺带回填。"""

    with _LOCK:
        _CATALOG[key] = dict(catalog)
        _STAMP[key] = time.monotonic()


def put_for(platform: Mapping[str, Any] | None, catalog: dict[str, tuple[int, int]]) -> None:
    put(_cache_key(platform), catalog)


def _fetch(platform: Mapping[str, Any], key: str) -> None:
    try:
        from module.Engine.API.ModelList import list_model_capabilities
        from module.Secret.SecretStore import SecretStore

        keys = SecretStore.get().resolve_keys(dict(platform))
        api_key = keys[0] if keys else ""
        catalog = list_model_capabilities(
            str(platform.get("api_url") or ""),
            api_key,
            str(platform.get("api_format") or "OpenAI"),
        )
        with _LOCK:
            _CATALOG[key] = dict(catalog)
            # 即使拿到空目录也记时间戳，避免每轮都重试网络。
            _STAMP[key] = time.monotonic()
    except Exception:  # noqa: BLE001 - 后台刷新失败保持旧缓存
        pass
    finally:
        with _LOCK:
            _REFRESHING.discard(key)


def ensure_async(platform: Mapping[str, Any] | None) -> None:
    """缓存缺失或过期时，起一个后台线程刷新，不等结果。"""

    if not isinstance(platform, Mapping):
        return
    key = _cache_key(platform)
    if not _is_stale(key):
        return
    with _LOCK:
        if key in _REFRESHING:
            return
        _REFRESHING.add(key)
    thread = threading.Thread(
        target=_fetch,
        args=(dict(platform), key),
        name="renpybox-model-catalog",
        daemon=True,
    )
    thread.start()


def capabilities(platform: Mapping[str, Any] | None) -> tuple[int, int]:
    """取当前模型在目录里的 (上下文窗口, 最大输出)；查不到返回 (0, 0)。"""

    model = str((platform or {}).get("model") or "").strip()
    if not model:
        return 0, 0
    catalog = get(platform)
    if not catalog:
        return 0, 0
    if model in catalog:
        return catalog[model]
    lowered = model.casefold()
    for name, capability in catalog.items():
        if name.casefold() == lowered:
            return capability
    return 0, 0


__all__ = [
    "CATALOG_TTL_SECONDS",
    "capabilities",
    "ensure_async",
    "get",
    "put",
    "put_for",
]
