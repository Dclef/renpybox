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

# 工具箱「翻译方式」白名单；未知值由路由返回 400。
# hook（运行时 EXE 抽取）走独立 /api/hook-translate，不在此列。
TRANSLATION_TOOLBOX_MODES = ("direct", "source", "supplement")

# 工具箱语言码：与 BaseLanguage.Enum 对齐；繁体由 traditional_chinese_enable 单独控制。
TRANSLATION_TOOLBOX_LANG_CODES = ("ZH", "EN", "JA", "KO")


class TranslationStartRequest(BaseModel):
    status: str = "UNTRANSLATED"
    request_id: str | None = None
    # 当前配置所属项目 owner；与手动 target 分开。有绑定且传入时须匹配 owner，
    # 不能拿 target.project_key 误判合法的另一个目录任务。
    project_key: str | None = None
    # 用户对「无有效资产」的明确继续决定（渲染端 preflight 弹窗选「仍然继续」）。
    # 不带这个标志时缺资产会被拒，避免静默跑出一个没有项目背景的翻译。
    preflight_confirmed: bool = False
    # 工具箱翻译方式：缺省则走普通 start（兼容既有调用）。
    # 取值仅允许 direct / source / supplement；带 mode 时先建请求级候选，
    # 受理后再落盘变更字段并发 TRANSLATION_START（拒绝时不写盘）。
    mode: str | None = None
    # 路径：direct 可用 game_path 或 tl_parent+tl_name；source 用 input（输出由服务端推导）；
    # supplement 用 game_path + tl_name（可带 tl_parent 保留自定义 TL）。
    game_path: str | None = None
    tl_parent: str | None = None
    tl_name: str | None = None
    language: str | None = None  # tl 语言目录名别名，与 tl_name 等价
    input_folder: str | None = None
    output_folder: str | None = None  # source 忽略；服务端按 Qt 推导 _source_out
    source_language: str | None = None
    target_language: str | None = None
    traditional_chinese_enable: bool | None = None
    renpy_backup_original: bool | None = None
    auto_write_back: bool | None = None
    external_backup_dir: str | None = None
    renpy_hook_incremental: bool | None = None
    generate_empty: bool | None = None
    # 请求级平台覆盖：只改写本轮冻结快照里的 activate_platform，不落盘、
    # 不影响翻译页设置。Agent 的「用 Agent 自己的模型跑批量翻译」走这条。
    platform_id: int | None = None
    # Agent 一条龙时沿用 Agent 的思考等级（OFF/LOW/MEDIUM/HIGH/MAX），
    # 只作用于本轮冻结快照，避免平台里为人工翻译配的 MAX 拖慢流水线。
    thinking_level: str | None = None


class TranslationReinjectRequest(BaseModel):
    """手动把缓存译文写回选定 TL（TRANSLATION_CACHE_REINJECT）。"""

    output_folder: str | None = None
    # 与 direct 相同的选定 TL 解析：显式 tl_parent+tl_name 优先。
    tl_parent: str | None = None
    tl_name: str | None = None
    game_path: str | None = None
    project_key: str | None = None
    request_id: str | None = None


class TranslationOwnerRequest(BaseModel):
    """只带 owner 标识的写操作请求（停止 / 导出 / 重试失败项）。

    缺省体视为未携带 key：当前没有绑定项目时放行，有绑定项目时被 409 拒绝，
    防止切项目后仍开着的旧页面驱动新项目的缓存写入与译文导出。
    """

    project_key: str | None = None


class TranslationStartResponse(BaseModel):
    """受理结果。

    ``accepted`` 对无备份的 mode/普通 start 表示事件已投递；线程是否真的起来、
    run_id 是多少，仍以 WS 上的 ``TRANSLATION_START_RESULT`` 为准。
    source 前置备份时 ``job`` 非空，``stage=backing_up``，翻译启动以 job 终态为准。
    """

    accepted: bool
    request_id: str = ""
    reason: str = ""
    detail: str = ""
    warnings: list[str] = []
    stage: str = ""
    job: dict[str, Any] | None = None


class TranslationResumableResponse(BaseModel):
    """工具箱续跑探测：按 mode 推导出的输出目录上是否有可继续的翻译缓存。

    源码翻译停止后再点「开始」应继续而不是重扫重翻；渲染端先问这个接口，
    有可续跑缓存就发 ``status=TRANSLATING``（继续），否则发 ``UNTRANSLATED``。
    只读缓存项目元数据，不载入条目。
    """

    resumable: bool = False
    output_folder: str = ""
    # 缓存项目状态：TRANSLATING（可续跑）/ TRANSLATED / UNTRANSLATED / 空。
    status: str = ""
    line: int = 0
    total_line: int = 0
    detail: str = ""


class TranslationStateResponse(BaseModel):
    engine_status: str = "IDLE"
    stop_barrier: bool = False
    single_tasks: bool = False
    # 当前绑定项目的 owner key；渲染端据此给写操作带上 project_key。
    owner_project_key: str = ""
    request_id: str = ""
    run_id: int = 0
    running: dict[str, int] = Field(default_factory=dict)
    progress: dict[str, Any] = Field(default_factory=dict)
    active_output_folder: str = ""
    progress_source: str = "none"
    progress_error: str = ""


class TokenEstimateRequest(BaseModel):
    """Token 估算请求。整个 body 可省略；platform_id 缺省时用当前激活平台。"""

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
