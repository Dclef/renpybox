"""接口默认模板、旧配置归一化与跨版本导入。

Qt5 端（``frontend/Project/PlatformPage.py``）与 Electron sidecar
（``api/app.py`` 启动播种、``api/routes/platforms.py`` 导入接口）必须使用同一套
默认接口与归一化规则，否则两端行为会漂移，因此规则收口在本模块。

设计要点：

- 默认接口从 ``resource/platforms/<界面语言>`` 读取，与 Qt5 完全一致；
- ``normalize_platforms`` 只做字段级修补（思考等级、DeepSeek 旧模型别名、机翻
  接口补齐、凭据身份、连续编号），不删除用户已有接口；
- 跨版本导入只搬运配置字段与 ``credential_id``：密钥本体存在 Windows 凭据管理器里
  且是全局的，只要身份一致就能自动认领，不必搬运密钥；旧配置里残留的明文密钥由
  ``SecretStore.migrate_platforms`` 落进凭据库后再从配置中清空。
"""

from __future__ import annotations

import copy
import json
import os
from typing import Callable

from base.Base import Base
from base.PathHelper import get_resource_path
from module.Localizer.Localizer import Localizer
from module.Project.PlatformNaming import deduplicate_platform_name
from module.Secret.SecretStore import SecretStore


# DeepSeek 官方接口已停用旧模型别名；自定义中转保持用户原值。
DEEPSEEK_OFFICIAL_URLS = ("https://api.deepseek.com", "https://api.deepseek.com/v1")
DEEPSEEK_LEGACY_MODEL = "deepseek-chat"
DEEPSEEK_CURRENT_MODEL = "deepseek-v4-flash"

# 思考等级合法值；旧版 bool 字段按 True -> HIGH 迁移。
THINKING_LEVELS = ("OFF", "LOW", "MEDIUM", "HIGH", "MAX")

# 名称以此开头的接口视为自定义接口，排序时排在最后。
CUSTOM_NAME_PREFIXES = ("自定义", "custom")


def is_custom_platform(platform: dict) -> bool:
    """名称以「自定义」/「custom」开头的接口排序时排在最后。"""
    name = str(platform.get("name", "")).strip().lower()
    return name.startswith(CUSTOM_NAME_PREFIXES)


def load_default_platforms() -> list[dict]:
    """读取内置默认接口模板，重设连续 id 并生成全新凭据身份。

    默认模板每次加载都生成新身份，不能继承可能属于旧平台的数字凭据别名，
    因此 ``preserve_legacy = False``。
    """
    platforms: list[dict] = []
    platforms_path = get_resource_path("resource", "platforms", str(Localizer.get_app_language()).lower())

    if not os.path.isdir(platforms_path):
        print(f"Warning: Platforms path not found: {platforms_path}")
        return []

    entries = [
        entry.path
        for entry in os.scandir(platforms_path)
        if entry.is_file() and entry.name.endswith(".json")
    ]
    for path in entries:
        try:
            with open(path, "r", encoding = "utf-8-sig") as reader:
                data = json.load(reader)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            platforms.append(data)

    # 重设 id 以避免 id 不连续的问题
    for index, platform in enumerate(sorted(platforms, key = lambda item: item.get("id"))):
        platform["id"] = index

    for platform in platforms:
        SecretStore.ensure_platform_identity(platform, preserve_legacy = False)

    return sorted(platforms, key = lambda item: item.get("id"))


def normalize_platforms(platforms: list[dict], defaults: list[dict] | None = None) -> bool:
    """就地修补接口列表，返回是否有改动。

    与 Qt5 ``PlatformPage.ensure_default_platforms`` 行为一致：补齐凭据身份、
    迁移 DeepSeek 旧模型别名、统一思考字段、补齐缺失的机翻接口、连续编号。

    ``defaults`` 用于补齐机翻接口，缺省时读取内置默认接口；显式传入空列表表示
    不做补齐（Qt5 页面沿用这一扩展点，便于测试注入固定模板）。
    """
    if not isinstance(platforms, list):
        return False

    changed = SecretStore.ensure_platform_identities(platforms) > 0
    if defaults is None:
        defaults = load_default_platforms()
    existing_formats = {str(item.get("api_format", "")) for item in platforms if isinstance(item, dict)}

    for item in platforms:
        if not isinstance(item, dict):
            continue
        api_url = str(item.get("api_url", "")).strip().lower().rstrip("/")
        if (
            str(item.get("api_format", "")) == str(Base.APIFormat.OPENAI)
            and api_url in DEEPSEEK_OFFICIAL_URLS
            and str(item.get("model", "")).strip().lower() == DEEPSEEK_LEGACY_MODEL
        ):
            item["model"] = DEEPSEEK_CURRENT_MODEL
            changed = True

    # 统一思考字段：旧版 bool -> 新版 {"level": "..."}，并修正非法值。
    for item in platforms:
        if not isinstance(item, dict):
            continue
        raw_thinking = item.get("thinking")
        level = "OFF"

        if isinstance(raw_thinking, dict):
            raw_level = str(raw_thinking.get("level", "OFF")).upper().strip()
            level = raw_level if raw_level in THINKING_LEVELS else "OFF"
        elif raw_thinking == True:
            level = "HIGH"

        normalized_thinking = {"level": level}
        if raw_thinking != normalized_thinking:
            item["thinking"] = normalized_thinking
            changed = True

    # 旧配置中没有机翻接口时，自动补齐到默认列表
    for fmt in Base.MACHINE_API_FORMATS:
        if str(fmt) in existing_formats:
            continue
        template = next((item for item in defaults if str(item.get("api_format", "")) == str(fmt)), None)
        if template is None:
            continue
        platforms.append(copy.deepcopy(template))
        existing_formats.add(str(fmt))
        changed = True

    if SecretStore.ensure_platform_identities(platforms) > 0:
        changed = True

    ids = [item.get("id") for item in platforms if isinstance(item, dict)]
    if len(ids) != len(set(ids)):
        changed = True

    if not changed:
        return False

    # 非自定义接口在前，自定义接口在后；并重新连续编号 id
    platforms.sort(key = lambda item: (1 if is_custom_platform(item) else 0, item.get("id", 0)))
    for index, item in enumerate(platforms):
        item["id"] = index

    return True


def seed_default_platforms(config: object) -> bool:
    """按 Qt5 的行为播种/归一化配置里的接口，返回是否写盘。

    桌面版此前没有这一步，全新安装会停在空接口列表；Python 版则在接口页构造时
    播种，两端因此表现不一致。启动时调用本函数即可对齐。
    """
    platforms = getattr(config, "platforms", None)
    if not isinstance(platforms, list):
        # platforms 为 null / 非法：整份换成内置默认接口
        config.platforms = load_default_platforms()
        normalize_platforms(config.platforms)
        config.save(strict = True)
        return True

    if normalize_platforms(platforms):
        config.save(strict = True)
        return True

    return False


def _import_identity(platform: dict) -> tuple:
    """导入去重键：优先稳定凭据身份，缺身份时退回名称 + 地址。"""
    credential_id = platform.get("credential_id")
    if isinstance(credential_id, str) and credential_id.strip():
        return ("credential", credential_id.strip().lower())
    return _weak_identity(platform)


def _weak_identity(platform: dict) -> tuple:
    """弱身份：名称 + 地址。用于识别「同一个接口」的两次不同安装。"""
    return ("name", str(platform.get("name", "")).strip().lower(), str(platform.get("api_url", "")).strip().lower())


def _has_credentials(platform: dict) -> bool:
    """当前条目是否已经存了密钥；读取异常按「有」处理，避免误覆盖。"""
    try:
        return SecretStore.get().has_persisted_credentials(platform)
    except Exception:
        return True


def merge_imported_platforms(
    current: list[dict] | None,
    imported: list[dict],
    is_protected: Callable[[dict], bool] | None = None,
) -> tuple[list[dict], int, int]:
    """把旧版配置里的接口合并进当前列表。

    返回 ``(合并结果, 导入数, 跳过数)``。

    匹配规则（顺序执行）：

    1. 稳定凭据身份相同 —— 同一台机器上的同一条接口，跳过；
    2. 名称 + 地址相同 —— 同一逻辑接口的两次安装。此时若当前条目还没有密钥
       （全新安装刚播种出来的默认接口就是这种状态），把旧版的凭据身份认领过来，
       用户的密钥就能直接恢复；已经有密钥的条目不动，只记为跳过；
    3. 其余条目追加到末尾，并按 ``PlatformNaming`` 的规则避免重名。

    ``is_protected`` 可覆盖「已有密钥就不动」的判断，便于测试与将来的扩展。
    """
    protected = is_protected or _has_credentials
    incoming = [copy.deepcopy(item) for item in imported if isinstance(item, dict)]
    if not isinstance(current, list) or not current:
        return incoming, len(incoming), 0

    merged = [copy.deepcopy(item) for item in current if isinstance(item, dict)]
    by_identity = {_import_identity(item): item for item in merged}
    by_weak = {_weak_identity(item): item for item in merged}
    # 追加的条目必须拿新编号：旧版的 id 从 0 开始，与当前列表撞号后归一化
    # 排序会把两批接口交叉混排，用户看到的就是乱序列表。
    next_id = max((item.get("id", -1) for item in merged if isinstance(item.get("id"), int)), default = -1) + 1
    imported_count = 0
    skipped = 0

    for item in incoming:
        identity = _import_identity(item)
        if identity in by_identity:
            skipped += 1
            continue

        existing = by_weak.get(_weak_identity(item))
        if existing is not None:
            credential_id = item.get("credential_id")
            if (
                isinstance(credential_id, str)
                and credential_id.strip()
                and not protected(existing)
            ):
                # 认领旧版条目：密钥本体在凭据管理器里，换成旧身份即可直接读到；
                # 字段也一并采用旧值，否则用户调过的模型、思考等级会被默认模板覆盖。
                existing.clear()
                existing.update(item)
                imported_count += 1
            else:
                skipped += 1
            continue

        item["id"] = next_id
        next_id += 1
        item["name"] = deduplicate_platform_name(
            str(item.get("name", "")),
            merged,
        )
        merged.append(item)
        by_identity[_import_identity(item)] = item
        by_weak[_weak_identity(item)] = item
        imported_count += 1

    return merged, imported_count, skipped


def read_legacy_platforms(payload: object) -> list[dict]:
    """从旧版配置对象里取出接口列表；结构不符时抛 ``ValueError``。"""
    if not isinstance(payload, dict):
        raise ValueError("配置文件内容不是有效的 JSON 对象。")
    platforms = payload.get("platforms")
    if not isinstance(platforms, list):
        raise ValueError("这份配置里没有接口列表，可能不是 RenpyBox 的配置文件。")
    return [item for item in platforms if isinstance(item, dict)]


def legacy_active_platform(payload: object) -> int | None:
    """旧版配置里的启用接口编号；非法值返回 ``None``。"""
    if not isinstance(payload, dict):
        return None
    value = payload.get("activate_platform")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
