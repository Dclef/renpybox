"""API 请求/响应模型。

这些 Pydantic 模型同时是「文档」和「类型来源」：
新增接口时先在这里定schema，再实现路由，TS 侧类型可以据此生成。
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


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


class ProjectInfo(BaseModel):
    renpy_project_path: str = ""
    renpy_game_folder: str = ""
    renpy_tl_folder: str = ""
    theme: str = ""
    app_language: str = ""


# ---------- WebSocket 指令 ----------

class WsCommand(BaseModel):
    type: str
    job_id: str | None = None
    events: list[str] | None = None