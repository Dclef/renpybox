"""API 请求/响应模型。

这些 Pydantic 模型同时是「文档」和「类型来源」：
新增接口时先在这里定schema，再实现路由，TS 侧类型可以据此生成。
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=16000)
    thinking_level: Literal["OFF", "LOW", "MEDIUM", "HIGH", "MAX"] = "OFF"


class AgentConfirmationRequest(BaseModel):
    confirmation_id: str = Field(min_length=32, max_length=32)
    approved: bool


# ---------- 通用 ----------

class HealthResponse(BaseModel):
    ok: bool = True
    pid: int
    app_version: str
    config_path: str
    python_version: str
    mode: str = "api"


class VersionResponse(BaseModel):
    app_version: str
    api_version: str = "1"


class ErrorResponse(BaseModel):
    ok: bool = False
    error: str


class OkResponse(BaseModel):
    ok: bool = True


# ---------- 设置 ----------

#字段名里命中这些片段的一律不出现在 GET 响应里
SECRET_HINTS = ("key", "token", "secret", "password", "credential")


class SettingsResponse(BaseModel):
    values: dict[str, Any]
    masked: list[str] = Field(default_factory=list)


class SettingsPatch(BaseModel):
    values: dict[str, Any]
    save: bool = True


# ---------- 术语表 / 替换规则 / 文本保护 ----------

class TableKind(str, Enum):
    GLOSSARY = "GLOSSARY"
    REPLACEMENT = "REPLACEMENT"
    TEXT_PRESERVE = "TEXT_PRESERVE"


class GlossaryLoadRequest(BaseModel):
    path: str
    kind: TableKind = TableKind.GLOSSARY


class GlossaryRows(BaseModel):
    kind: TableKind
    rows: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class GlossarySaveRequest(BaseModel):
    kind: TableKind = TableKind.GLOSSARY
    rows: list[dict[str, Any]] = Field(default_factory=list)
    path: str | None = None
    format: Literal["json", "xlsx", "both"] = "both"


class GlossarySyncRequest(BaseModel):
    kind: TableKind = TableKind.GLOSSARY
    rows: list[dict[str, Any]] = Field(default_factory=list)


class GlossarySearchRequest(BaseModel):
    kind: TableKind = TableKind.GLOSSARY
    rows: list[dict[str, Any]] = Field(default_factory=list)
    keyword: str
    start: int = -1


# ---------- 项目 ----------

class ProjectPathRequest(BaseModel):
    project_path: str
    game_folder: str | None = None


class ProjectResolveRequest(BaseModel):
    """按给定目录解析 Ren'Py 项目身份（选输入目录时顺带绑定项目）。"""

    path: str


class ProjectInfo(BaseModel):
    renpy_project_path: str = ""
    renpy_game_folder: str = ""
    renpy_tl_folder: str = ""
    theme: str = ""
    app_language: str = ""


# ---------- 翻译主流程 ----------

class TranslationStartRequest(BaseModel):
    status: str = "UNTRANSLATED"
    request_id: str | None = None
    # 用户对「无有效资产」的明确继续决定（渲染端 preflight 弹窗选「仍然继续」）。
    # 不带这个标志时缺资产会被拒，避免静默跑出一个没有项目背景的翻译。
    preflight_confirmed: bool = False


class TranslationStartResponse(BaseModel):
    """受理结果。

    ``accepted`` 只表示请求已被受理并投递到事件总线；线程是否真的起来、
    run_id 是多少，仍以 WS 上的 ``TRANSLATION_START_RESULT`` 为准。
    """

    accepted: bool
    request_id: str = ""
    reason: str = ""
    detail: str = ""


class TranslationStateResponse(BaseModel):
    engine_status: str = "IDLE"
    stop_barrier: bool = False
    single_tasks: bool = False
    request_id: str = ""
    run_id: int = 0
    running: dict[str, int] = Field(default_factory=dict)
    progress: dict[str, Any] = Field(default_factory=dict)
    active_output_folder: str = ""
    progress_source: str = "none"
    progress_error: str = ""


class TokenEstimateRequest(BaseModel):
    """Token 估算。目前没有参数，保留模型便于后续加「指定平台 / 范围」。"""

    platform_id: int | None = None


class TokenEstimateResult(BaseModel):
    total_source_tokens: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_cost: float = 0.0
    batch_count: int = 0
    untranslated_count: int = 0


# ---------- WebSocket 指令 ----------

class WsCommand(BaseModel):
    type: str
    job_id: str | None = None
    events: list[str] | None = None
