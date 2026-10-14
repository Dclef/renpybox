"""接口名称归一化。

新增接口时同名会让用户在列表里无法区分，也无法确认自己改的是哪一条。
Qt5 端（``frontend/Project/PlatformPage.py:250-265``）在 append 前会去重，
Electron 端经 ``POST /api/platforms`` 新增时也必须走同一规则，因此规则收口
在本模块，Qt5 页面改为引用同一实现。
"""

from __future__ import annotations


def deduplicate_platform_name(name: str, platforms: list[dict] | None) -> str:
    """按精确名称匹配，为重复接口名追加递增数字后缀（``名称 2``、``名称 3``）。

    与 Qt5 ``frontend/Project/PlatformPage.py:65-74`` 完全一致：
    名称不存在时原样返回；已存在时从 2 开始找第一个未被占用的编号。
    """
    existing_names = {
        str(platform.get("name", ""))
        for platform in (platforms or [])
        if isinstance(platform, dict)
    }
    if name not in existing_names:
        return name

    suffix = 2
    while f"{name} {suffix}" in existing_names:
        suffix += 1
    return f"{name} {suffix}"
