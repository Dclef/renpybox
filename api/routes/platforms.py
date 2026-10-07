"""接口管理：逐项保存配置，密钥只通过 SecretStore 写入且不回传。"""

from __future__ import annotations

import copy
import threading
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from api.routes.settings import REDACTED, read_settings
from api.schemas import SettingsResponse
from base.Base import Base
from base.EventManager import EventManager
from module.Engine.Engine import Engine
from module.Secret.SecretStore import CREDENTIAL_ID_FIELD, LEGACY_CREDENTIAL_ID_FIELD, SecretStore

router = APIRouter(prefix = "/api/platforms", tags = ["接口管理"])
_WRITE_LOCK = threading.Lock()


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
            platform = {
                "id": max((item.get("id", -1) for item in platforms), default = -1) + 1,
                "name": body.name.strip(), "group": "custom", "api_format": "OpenAI",
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