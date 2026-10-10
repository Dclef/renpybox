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

# 翻译规则字段：引擎忙碌时禁止修改
TRANSLATION_RULE_KEYS = frozenset({
    "text_preserve_data",
    "text_preserve_enable",
    "honorific_placeholder_titles",
    "honorific_placeholder_bridge_enable",
})
HONORIFIC_RULE_KEYS = frozenset({
    "honorific_placeholder_titles",
    "honorific_placeholder_bridge_enable",
})
HONORIFIC_TITLES_MAX_ROWS = 5000
HONORIFIC_TITLE_MAX_LEN = 200
HONORIFIC_COMMENT_MAX_LEN = 2000


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


def _normalize_honorific_titles(value: Any) -> list[str | dict[str, str]]:
    """校验并规范化称呼词：允许 str 或 {src, comment}，过滤空称呼。"""
    from module.TextProcessor import TextProcessor

    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail="honorific_placeholder_titles 期望列表")
    if len(value) > HONORIFIC_TITLES_MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"称呼词超过 {HONORIFIC_TITLES_MAX_ROWS} 行限制",
        )

    entries: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, str):
            src = item.strip().lower()
            comment = ""
        elif isinstance(item, dict):
            src_raw = item.get("src", "")
            comment_raw = item.get("comment", "")
            if src_raw is not None and not isinstance(src_raw, str):
                raise HTTPException(status_code=400, detail="称呼词 src 必须是字符串")
            if comment_raw is not None and not isinstance(comment_raw, str):
                raise HTTPException(status_code=400, detail="称呼词 comment 必须是字符串")
            src = str(src_raw or "").strip().lower()
            comment = str(comment_raw or "").strip()
        else:
            raise HTTPException(
                status_code=400,
                detail="称呼词条目必须是字符串或含 src/comment 的对象",
            )
        if not src:
            continue
        if len(src) > HONORIFIC_TITLE_MAX_LEN:
            raise HTTPException(
                status_code=400,
                detail=f"称呼词长度不能超过 {HONORIFIC_TITLE_MAX_LEN} 字符",
            )
        if len(comment) > HONORIFIC_COMMENT_MAX_LEN:
            raise HTTPException(
                status_code=400,
                detail=f"称呼词备注长度不能超过 {HONORIFIC_COMMENT_MAX_LEN} 字符",
            )
        entries.append({"src": src, "comment": comment})
    return TextProcessor.serialize_honorific_titles(entries)


def sync_output_protocol(config: Any, changed: frozenset[str] | set[str] = frozenset()) -> None:
    """让「翻译输出协议」与「单行翻译模式」保持同一状态。

    语义对齐 frontend/Setting/TranslationSettingsBinding.py（sidecar 打包排除了
    frontend 包，不能直接导入）：SINGLE_TEXT 只能走单行请求，批量请求遇到它会
    直接抛错。本次修改了哪一项就以哪一项为准，两项都没改时按旧配置规范化。
    """
    from module.Config import Config

    protocol = str(getattr(config, "translation_output_protocol", "") or "").strip().upper()
    if protocol not in Config.OUTPUT_PROTOCOLS:
        if "translation_output_protocol" in changed:
            raise HTTPException(status_code = 400, detail = f"未知翻译输出协议：{protocol}")
        protocol = Config.OUTPUT_PROTOCOL_STRUCTURED

    if "translation_output_protocol" in changed:
        single_line = protocol == Config.OUTPUT_PROTOCOL_SINGLE_TEXT
    elif "single_line_translation_enable" in changed:
        single_line = getattr(config, "single_line_translation_enable", False) is True
        if single_line:
            protocol = Config.OUTPUT_PROTOCOL_SINGLE_TEXT
        elif protocol == Config.OUTPUT_PROTOCOL_SINGLE_TEXT:
            protocol = Config.OUTPUT_PROTOCOL_STRUCTURED
    else:
        if getattr(config, "single_line_translation_enable", False) is True:
            protocol = Config.OUTPUT_PROTOCOL_SINGLE_TEXT
        single_line = protocol == Config.OUTPUT_PROTOCOL_SINGLE_TEXT

    config.translation_output_protocol = protocol
    config.single_line_translation_enable = single_line


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
        if not set(patch.values) & TRANSLATION_RULE_KEYS:
            return _patch_settings(request, patch)
        from module.Engine.Engine import Engine
        engine = Engine.get()
        if not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
            raise HTTPException(status_code=409, detail="任务执行期间不能修改翻译规则。")
        try:
            return _patch_settings(request, patch)
        finally:
            engine.release_status(Engine.Status.TESTING)


def _patch_settings(request: Request, patch: SettingsPatch) -> SettingsResponse:
    original = request.app.state.config
    config = copy.deepcopy(original)
    known = {f.name for f in dataclasses.fields(config)}

    for key, value in patch.values.items():
        if key not in known:
            raise HTTPException(status_code = 400, detail = f"未知配置项：{key}")
        if _is_secret(key):
            raise HTTPException(status_code = 403, detail = f"{key} 需通过密钥流程修改")

        if key == "honorific_placeholder_titles":
            value = _normalize_honorific_titles(value)
        elif key == "honorific_placeholder_bridge_enable":
            if not isinstance(value, bool):
                raise HTTPException(status_code=400, detail=f"{key} 期望布尔值")
        else:
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

    protocol_keys = {"translation_output_protocol", "single_line_translation_enable"} & patch.values.keys()
    if protocol_keys:
        sync_output_protocol(config, protocol_keys)

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
