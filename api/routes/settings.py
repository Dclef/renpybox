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
    config = request.app.state.config
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
        config.save()

    return read_settings(request)