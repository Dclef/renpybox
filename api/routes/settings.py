"""配置读写。

密钥处理约定：
  * 真正的密钥不在顶层字段，而在 platforms 列表里（每个平台一个 dict，含 api_key）
  * 所以顶层只按「精确字段名」判断，不用key/token 之类的子串匹配——
    否则 onekey_inject_base_box、token_threshold 会被误判成密钥而查不到
  * platforms 这类嵌套结构做递归脱敏：命中精确密钥字段名的键值一律不出现在响应里
  * PATCH 同样拒绝写这些字段，密钥必须走SecretStore 流程
"""

from __future__ import annotations

import dataclasses
import copy
import threading
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from api.schemas import SettingsPatch, SettingsResponse

router = APIRouter(prefix = "/api/settings", tags = ["settings"])

# 精确匹配才会被当作密钥
SECRET_FIELDS = frozenset({
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "access_token",
    "refresh_token",
})

REDACTED = "***"
_SETTINGS_LOCK = threading.Lock()


def _is_secret(field_name: str) -> bool:
    return field_name.lower() in SECRET_FIELDS


def _sanitise(value: Any) -> Any:
    """递归脱敏：嵌套 dict 里命中密钥字段名的值替换为 ***。"""
    if isinstance(value, dict):
        return {
            k: (REDACTED if _is_secret(str(k)) else _sanitise(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitise(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "as_posix"):
        return value.as_posix()
    return repr(value)


@router.get("", response_model = SettingsResponse)
def read_settings(request: Request) -> SettingsResponse:
    config = request.app.state.config
    values: dict[str, Any] = {}
    masked: list[str] = []

    for field in dataclasses.fields(config):
        if _is_secret(field.name):
            masked.append(field.name)
            continue
        values[field.name] = _sanitise(getattr(config, field.name, None))

    return SettingsResponse(values = values, masked = masked)


@router.patch("", response_model = SettingsResponse)
def patch_settings(request: Request, patch: SettingsPatch) -> SettingsResponse:
    with _SETTINGS_LOCK:
        return _patch_settings(request, patch)


def _patch_settings(request: Request, patch: SettingsPatch) -> SettingsResponse:
    original = request.app.state.config
    config = copy.deepcopy(original)
    if set(patch.values) & {"text_preserve_data", "text_preserve_enable", "honorific_placeholder_titles", "honorific_placeholder_bridge_enable"}:
        from module.Engine.Engine import Engine
        engine = Engine.get()
        if engine.get_status() != Engine.Status.IDLE or engine.has_stop_barrier() or engine.has_single_tasks():
            raise HTTPException(status_code=409, detail="任务执行期间不能修改翻译规则。")
    known = {f.name for f in dataclasses.fields(config)}

    for key, value in patch.values.items():
        if key not in known:
            raise HTTPException(status_code = 400, detail = f"未知配置项：{key}")
        if _is_secret(key):
            raise HTTPException(status_code = 403, detail = f"{key} 需通过密钥流程修改")

        current = getattr(config, key, None)
        if isinstance(current, bool):
            if not isinstance(value, bool):
                raise HTTPException(status_code = 400, detail = f"{key} 期望布尔值")
        elif isinstance(current, int) and not isinstance(current, bool):
            if not isinstance(value, int):
                raise HTTPException(status_code = 400, detail = f"{key} 期望整数")
        elif isinstance(current, str):
            if not isinstance(value, str):
                raise HTTPException(status_code = 400, detail = f"{key} 期望字符串")
        elif isinstance(current, list) and not isinstance(value, list):
            raise HTTPException(status_code = 400, detail = f"{key} 期望列表")

        setattr(config, key, value)

    # 相对路径要重新固定成绝对路径，否则 sidecar 的 cwd一变就失效
    config._normalise_runtime_paths()

    if patch.save:
        try:
            config.save(strict=True)
        except Exception:
            raise HTTPException(status_code=500, detail="配置保存失败，修改未生效，请检查写入权限。") from None
    for field in dataclasses.fields(config):
        setattr(original, field.name, getattr(config, field.name))
    return read_settings(request)


@router.get("/honorific-defaults")
def honorific_defaults() -> dict:
    """返回翻译引擎的内置称呼词，只读，不覆盖用户配置。"""
    from module.TextProcessor import TextProcessor
    return {"titles": list(TextProcessor.DEFAULT_HONORIFIC_TITLES)}

@router.get("/prompt-preview")
def preview_prompt(request: Request) -> dict[str, str]:
    """读取当前配置的基础提示、写作风格和固定工程协议，不发起模型请求。"""
    from module.PromptBuilder import PromptBuilder

    try:
        return PromptBuilder(request.app.state.config).build_static_prompt_sections()
    except Exception as exc:
        raise HTTPException(status_code = 400, detail = f"提示词预览失败：{exc}") from exc