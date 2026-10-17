"""接口管理：逐项保存配置，密钥只通过 SecretStore 写入且不回传。"""

from __future__ import annotations

import copy
import json
import os
import threading
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from api.routes.settings import REDACTED, read_settings
from api.schemas import SettingsResponse
from base.Base import Base
from base.EventManager import EventManager
from base.PathHelper import get_resource_path
from module.Engine.Engine import Engine
from module.Localizer.Localizer import Localizer
from module.Project.PlatformDefaults import (
    legacy_active_platform,
    merge_imported_platforms,
    normalize_platforms,
    read_legacy_platforms,
)
from module.Project.PlatformNaming import deduplicate_platform_name
from module.Secret.SecretStore import CREDENTIAL_ID_FIELD, LEGACY_CREDENTIAL_ID_FIELD, SecretStore

router = APIRouter(prefix = "/api/platforms", tags = ["接口管理"])
_WRITE_LOCK = threading.Lock()

# 导入的配置文件体积上限：真实配置不到 100 KB，超过这个量级说明选错了文件。
MAX_IMPORT_BYTES = 8 * 1024 * 1024


class PlatformWrite(BaseModel):
    """仅允许编辑接口字段；省略 api_keys 表示保留密钥，空列表表示清空。"""

    model_config = ConfigDict(extra = "forbid")
    name: str | None = Field(default = None, min_length = 1, max_length = 128)
    group: Literal["local", "machine", "online", "custom"] | None = None
    api_format: Literal["OpenAI", "Google", "Anthropic", "SakuraLLM", "GoogleFree", "Bing"] | None = None
    api_url: str | None = Field(default = None, max_length = 2048)
    model: str | None = Field(default = None, max_length = 256)
    thinking_level: Literal["OFF", "LOW", "MEDIUM", "HIGH", "MAX"] | None = None
    api_keys: list[str] | None = Field(default = None, max_length = 100)
    top_p: float | None = Field(default = None, ge = 0, le = 1)
    temperature: float | None = Field(default = None, ge = 0, le = 2)
    presence_penalty: float | None = Field(default = None, ge = -2, le = 2)
    frequency_penalty: float | None = Field(default = None, ge = -2, le = 2)
    top_p_custom_enable: bool | None = None
    temperature_custom_enable: bool | None = None
    presence_penalty_custom_enable: bool | None = None
    frequency_penalty_custom_enable: bool | None = None


class PlatformImport(BaseModel):
    """导入旧版（Python / Qt5 版）配置里的接口。

    只接受配置文件的绝对路径：桌面版读文件、Qt5 版在别的目录，渲染层拿不到内容。
    ``activate`` 为真时一并采用旧配置里启用的接口。
    """

    model_config = ConfigDict(extra = "forbid")
    path: str = Field(min_length = 1, max_length = 4096)
    activate: bool = True


class PlatformImportResponse(SettingsResponse):
    """在设置快照之外补上导入结果，便于界面给出准确提示。"""

    imported: int = 0
    skipped: int = 0


def _idle() -> None:
    engine = Engine.get()
    if engine.get_status() != Engine.Status.IDLE or engine.has_stop_barrier() or engine.has_single_tasks():
        raise HTTPException(status_code = 409, detail = "任务执行中，请在任务结束后修改或测试接口。")


def _platform(config, platform_id: int) -> dict:
    platform = config.get_platform(platform_id)
    if platform is None:
        raise HTTPException(status_code = 404, detail = "接口不存在，请刷新列表。")
    return platform


def _save(config, platforms: list[dict], active: int | None = None, agent: int | None = None) -> None:
    """只替换接口相关字段；严格落盘失败时恢复内存，保留其他设置。"""
    previous = (config.platforms, config.activate_platform, config.agent_platform)
    config.platforms = platforms
    if active is not None:
        config.activate_platform = active
    if agent is not None:
        config.agent_platform = agent
    try:
        config.save(strict = True)
    except Exception:
        config.platforms, config.activate_platform, config.agent_platform = previous
        raise HTTPException(status_code = 500, detail = "接口保存失败，请检查配置目录的写入权限。") from None


def _apply(platform: dict, body: PlatformWrite) -> dict:
    values = body.model_dump(exclude_unset = True)
    if any(value is None for value in values.values()):
        raise HTTPException(status_code = 400, detail = "接口字段不能为 null。")
    keys = values.pop("api_keys", None)
    level = values.pop("thinking_level", None)
    for field in ("name", "api_url", "model"):
        if field in values:
            values[field] = values[field].strip()
    if "name" in values and not values["name"]:
        raise HTTPException(status_code = 400, detail = "接口名称不能为空。")
    if "api_url" in values and values["api_url"]:
        try:
            url = urlsplit(values["api_url"])
        except ValueError:
            raise HTTPException(status_code = 400, detail = "接口地址格式无效。") from None
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            raise HTTPException(status_code = 400, detail = "接口地址应为不含用户名和密码的 HTTP 或 HTTPS 地址。")
    platform.update(values)
    if level is not None:
        platform["thinking"] = {"level": level}
    if keys is not None:
        keys = [key.strip() for key in keys if key.strip()]
        if any(key == REDACTED or len(key) > 4096 for key in keys):
            raise HTTPException(status_code = 400, detail = "请输入真实密钥，不能保存脱敏标记或超长密钥。")
        # 新凭据身份先写好，配置成功落盘后才清理旧身份，失败不会覆盖旧密钥。
        platform.pop(CREDENTIAL_ID_FIELD, None)
        platform.pop(LEGACY_CREDENTIAL_ID_FIELD, None)
        SecretStore.ensure_platform_identity(platform, preserve_legacy = False)
        platform["api_key"] = [] if not keys or SecretStore.get().store_keys(platform, keys) else keys
    return platform


def _write(request: Request, body: PlatformWrite, platform_id: int | None = None) -> SettingsResponse:
    with _WRITE_LOCK:
        _idle()
        config = request.app.state.config
        original = _platform(config, platform_id) if platform_id is not None else None
        platforms = copy.deepcopy(config.platforms or [])
        if original is None:
            if not body.name or not body.name.strip():
                raise HTTPException(status_code = 400, detail = "新增接口需要名称。")
            # 同名接口会让用户无法区分两条记录；按 Qt5 PlatformPage.py:250-262
            # 的规则追加递增数字后缀。去重后的名字写回请求体，避免 _apply
            # 再用用户提交的原始名字覆盖。
            name = deduplicate_platform_name(body.name.strip(), platforms)
            body.name = name
            platform = {
                "id": max((item.get("id", -1) for item in platforms), default = -1) + 1,
                "name": name,
                "group": "custom", "api_format": "OpenAI",
                "api_url": "", "model": "", "api_key": [], "thinking": {"level": "OFF"},
                "top_p": 0.95, "temperature": 0.95, "presence_penalty": 0.0, "frequency_penalty": 0.0,
            }
            SecretStore.ensure_platform_identity(platform, preserve_legacy = False)
            platforms.append(platform)
        else:
            platform = next(item for item in platforms if item.get("id") == platform_id)
        try:
            _apply(platform, body)
            _save(config, platforms)
        except Exception:
            if body.api_keys is not None and platform.get(CREDENTIAL_ID_FIELD) != (original or {}).get(CREDENTIAL_ID_FIELD):
                SecretStore.get().clear_keys(platform)
            raise
        if original is not None and body.api_keys is not None:
            # 清理失败只留下不可达的旧凭据，不影响已落盘的新接口。
            SecretStore.get().clear_keys(original)
        return read_settings(request)


PRESET_SAFE_FIELDS = ("name", "group", "api_format", "api_url", "model")


def _presets_path() -> str:
    # 与 Qt5 端一致：预设按界面语言目录加载；资源缺失时回落中文目录。
    language = str(Localizer.get_app_language()).lower()
    path = get_resource_path("resource", "platforms", language)
    if not os.path.isdir(path) and language != "zh":
        path = get_resource_path("resource", "platforms", "zh")
    return path


def load_platform_presets() -> list[dict]:
    """读取内置接口预设；剔除密钥与凭据身份字段，只回传可安全预填的展示字段。"""
    path = _presets_path()
    if not os.path.isdir(path):
        return []
    presets: list[dict] = []
    # 文件名前缀（0_sakura → 19_bing）决定展示顺序，与 Qt5 的 id 排序一致。
    entries = sorted(
        (item for item in os.scandir(path) if item.is_file() and item.name.endswith(".json")),
        key = lambda item: item.name,
    )
    for entry in entries:
        try:
            with open(entry.path, "r", encoding="utf-8-sig") as reader:
                data = json.load(reader)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        preset = {field: data.get(field) for field in PRESET_SAFE_FIELDS}
        if isinstance(preset.get("name"), str) and preset["name"]:
            presets.append(preset)
    return presets


@router.get("/presets")
def read_presets() -> dict:
    """内置接口预设，用于「新增接口」菜单预填名称、协议与地址。"""
    return {"presets": load_platform_presets()}


def _legacy_active_platform(payload: object, imported: list[dict]) -> dict | None:
    """旧版配置里启用的那条接口；编号越界或缺失时返回 ``None``。"""
    index = legacy_active_platform(payload)
    if not isinstance(index, int) or not 0 <= index < len(imported):
        return None
    return imported[index]


def _resolve_active(platforms: list[dict], legacy_platform: dict | None, current: int) -> int:
    """确定导入后启用哪一条接口。

    优先沿用旧版的启用选择（按凭据身份定位，避免归一化重编号后指错条目），
    否则保留当前选择；当前选择已失效时退回第一条。
    """
    if legacy_platform is not None:
        identity = legacy_platform.get(CREDENTIAL_ID_FIELD)
        if isinstance(identity, str) and identity.strip():
            for item in platforms:
                if str(item.get(CREDENTIAL_ID_FIELD, "")).lower() == identity.strip().lower():
                    return int(item.get("id", 0))
    if 0 <= current < len(platforms):
        return current
    return 0


@router.post("/import", response_model = PlatformImportResponse)
def import_platforms(request: Request, body: PlatformImport) -> PlatformImportResponse:
    """从旧版（Python / Qt5）配置导入接口。

    桌面版与旧版把配置放在不同目录，用户升级后接口列表是空的；这里让用户
    自己选旧版的 config.json，只搬运接口字段与稳定凭据身份 —— 密钥本体存在
    Windows 凭据管理器里且是全局的，凭身份即可自动认领，不必复制密钥。
    旧配置里残留的明文密钥交给 ``SecretStore.migrate_platforms`` 落进凭据库
    后再从配置中清空，不会长期留在 JSON 里。
    """
    path = os.path.abspath(os.path.expanduser(body.path.strip()))
    if not os.path.isfile(path):
        raise HTTPException(status_code = 400, detail = "找不到这个文件，请选择旧版程序目录下的 config.json。")
    if os.path.getsize(path) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code = 400, detail = "配置文件过大，可能不是 RenpyBox 的配置文件。")
    try:
        with open(path, "r", encoding = "utf-8-sig") as reader:
            payload = json.load(reader)
    except (OSError, ValueError):
        raise HTTPException(status_code = 400, detail = "无法读取这份配置，请确认它是旧版程序目录下的 config.json。") from None
    try:
        imported = read_legacy_platforms(payload)
    except ValueError as error:
        raise HTTPException(status_code = 400, detail = str(error)) from None
    if not imported:
        raise HTTPException(status_code = 400, detail = "这份配置里没有可导入的接口。")

    with _WRITE_LOCK:
        _idle()
        config = request.app.state.config
        merged, added, skipped = merge_imported_platforms(config.platforms, imported)
        # 归一化会重排并重新编号，所以要在它之前记下旧版启用的是哪一条
        legacy_platform = _legacy_active_platform(payload, imported) if body.activate else None
        # 统一思考字段、补齐机翻接口、生成缺失的凭据身份并连续编号
        normalize_platforms(merged)
        # 先落盘稳定身份，再把旧配置里的明文密钥迁进凭据库
        _save(config, merged)
        try:
            migrated = SecretStore.get().migrate_platforms(merged)
        except Exception:
            migrated = 0
        if migrated > 0:
            _save(config, merged)

        # 按身份把旧版的启用选择映射到重编号后的条目
        active = _resolve_active(merged, legacy_platform, config.activate_platform)
        _save(config, merged, active = active)

    response = read_settings(request)
    return PlatformImportResponse(**response.model_dump(), imported = added, skipped = skipped)


@router.post("", response_model = SettingsResponse)
def create_platform(request: Request, body: PlatformWrite) -> SettingsResponse:
    """新增接口，返回脱敏后的最新配置。"""
    return _write(request, body)


@router.patch("/{platform_id}", response_model = SettingsResponse)
def update_platform(request: Request, platform_id: int, body: PlatformWrite) -> SettingsResponse:
    """只更新给出的接口字段，省略的参数与密钥保持原值。"""
    return _write(request, body, platform_id)


@router.delete("/{platform_id}", response_model = SettingsResponse)
def delete_platform(request: Request, platform_id: int) -> SettingsResponse:
    """删除接口后同步翻译与 Agent 引用，稳定凭据身份不随编号改变。"""
    with _WRITE_LOCK:
        _idle()
        config = request.app.state.config
        removed = _platform(config, platform_id)
        platforms = copy.deepcopy([item for item in config.platforms if item.get("id") != platform_id])
        SecretStore.ensure_platform_identities(platforms)
        remap = {}
        for index, platform in enumerate(sorted(platforms, key = lambda item: item.get("id", 0))):
            remap[platform["id"]] = index
            platform["id"] = index
        _save(config, platforms, remap.get(config.activate_platform, 0), remap.get(config.agent_platform, -1))
        SecretStore.get().clear_keys(removed)
        return read_settings(request)


@router.post("/{platform_id}/activate", response_model = SettingsResponse)
def activate_platform(request: Request, platform_id: int) -> SettingsResponse:
    """切换翻译接口，保留独立的 Agent 接口选择。"""
    with _WRITE_LOCK:
        _idle()
        config = request.app.state.config
        _platform(config, platform_id)
        _save(config, config.platforms, active = platform_id)
        return read_settings(request)


@router.post("/{platform_id}/test")
def test_platform(request: Request, platform_id: int) -> dict:
    """提交真实 APITester 测试，完成结果通过 PLATFORM_TEST_DONE 事件返回。"""
    with _WRITE_LOCK:
        _platform(request.app.state.config, platform_id)
        engine = Engine.get()
        tester = getattr(engine, "api_test", None)
        if tester is None:
            raise HTTPException(status_code = 503, detail = "接口测试服务尚未初始化。")
        if not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
            raise HTTPException(status_code = 409, detail = "任务执行中，请在任务结束后测试接口。")

    def run() -> None:
        try:
            tester._platform_test_start_guarded(Base.Event.PLATFORM_TEST_START, {"id": platform_id})
        except Exception:
            # SDK 错误可能带有密钥，意外异常只广播通用文案。
            EventManager.get().emit(Base.Event.PLATFORM_TEST_DONE, {"result": False, "result_msg": "接口测试失败，请检查接口配置及后台日志。"})
        finally:
            engine.release_status(Engine.Status.TESTING)

    try:
        threading.Thread(target = run, name = "PLATFORM_TEST", daemon = True).start()
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        raise HTTPException(status_code = 500, detail = "接口测试启动失败，请重试。") from None
    return {"accepted": True}

@router.get("/{platform_id}/models")
def read_models(request: Request, platform_id: int) -> dict:
    """读取已保存接口的模型列表；凭据留在后端，不回传 SDK 异常内容。"""
    from module.Agent.ModelCatalog import put_for
    from module.Engine.API.ModelList import list_model_capabilities, list_models

    with _WRITE_LOCK:
        _idle()
        platform = copy.deepcopy(_platform(request.app.state.config, platform_id))
        keys = SecretStore.get().resolve_keys(platform)
    try:
        models = list_models(platform.get("api_url", ""), keys[0] if keys else "", platform.get("api_format", "OpenAI"))
    except Exception:
        raise HTTPException(status_code=502, detail="读取模型列表失败，请检查已保存的接口地址、密钥和网络连接。") from None
    # 顺手把运行时模型目录（上下文窗口 / 最大输出）灌进 Agent 的缓存：
    # 用户打开模型列表就把容量信息带回来了，Agent 不必再自己猜。
    try:
        put_for(
            platform,
            list_model_capabilities(
                platform.get("api_url", ""),
                keys[0] if keys else "",
                platform.get("api_format", "OpenAI"),
            ),
        )
    except Exception:
        pass
    return {"models": models}
