"""Agent 工具注册与服务端参数校验。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from base.LogManager import LogManager
from module.Config import Config
from module.Engine.Engine import Engine

from .tools import (
    get_project_info,
    list_rpa_files,
    scan_script_errors,
    set_project,
)
from .types import ToolDef, ToolResult


ConfigLoader = Callable[[], Config]


class ToolDispatcher:
    """固定注册一期四个工具，不向模型暴露任意 Python 调用能力。"""

    MAX_RESULT_CHARS = 2000

    def __init__(
        self,
        *,
        config_loader: ConfigLoader | None = None,
        engine: Engine | None = None,
    ) -> None:
        self.config_loader = config_loader or (lambda: Config().load())
        self.engine = engine or Engine.get()
        self._tools = self._build_tools()

    def _build_tools(self) -> dict[str, ToolDef]:
        empty_schema = {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
        return {
            "set_project": ToolDef(
                name="set_project",
                description="设定用户明确提供的 Ren'Py 项目目录。成功后返回规范项目根、game 目录和语言。",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "用户在对话中明确提供的项目路径。",
                        },
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
                handler=lambda path: set_project(path, config_loader=self.config_loader),
                requires_idle_engine=True,
            ),
            "get_project_info": ToolDef(
                name="get_project_info",
                description="读取当前已设定的项目目录和语言；未设定时返回 PROJECT_NOT_SET。",
                parameters_schema=deepcopy(empty_schema),
                handler=lambda: get_project_info(config_loader=self.config_loader),
            ),
            "list_rpa_files": ToolDef(
                name="list_rpa_files",
                description="列出当前项目 game 目录中的 RPA 文件。目录由服务端配置注入。",
                parameters_schema=deepcopy(empty_schema),
                handler=lambda: list_rpa_files(config_loader=self.config_loader),
            ),
            "scan_script_errors": ToolDef(
                name="scan_script_errors",
                description="扫描当前项目 game 目录中的 Ren'Py 脚本错误，不修改文件。",
                parameters_schema=deepcopy(empty_schema),
                handler=lambda: scan_script_errors(config_loader=self.config_loader),
            ),
        }

    @property
    def tools(self) -> dict[str, ToolDef]:
        return self._tools

    def get_tool_definitions(self, provider: str = "openai") -> list[dict[str, Any]]:
        """按供应商返回工具 schema。"""
        if provider == "anthropic":
            return [tool.anthropic_schema() for tool in self._tools.values()]
        if provider == "google":
            return [tool.google_schema() for tool in self._tools.values()]
        return [tool.openai_schema() for tool in self._tools.values()]

    def get_openai_tools(self) -> list[dict[str, Any]]:
        return self.get_tool_definitions("openai")

    def get_anthropic_tools(self) -> list[dict[str, Any]]:
        return self.get_tool_definitions("anthropic")

    def get_google_tools(self) -> list[dict[str, Any]]:
        return self.get_tool_definitions("google")

    @staticmethod
    def _validate_arguments(tool: ToolDef, arguments: Any) -> str | None:
        if not isinstance(arguments, dict):
            return "工具参数必须是 JSON 对象。"
        schema = tool.parameters_schema
        properties = schema.get("properties", {})
        unknown = set(arguments) - set(properties)
        if unknown:
            return f"包含未声明参数：{', '.join(sorted(str(item) for item in unknown))}。"
        missing = [name for name in schema.get("required", []) if name not in arguments]
        if missing:
            return f"缺少必填参数：{', '.join(missing)}。"
        for name, value in arguments.items():
            expected = properties.get(name, {}).get("type")
            if expected == "string" and not isinstance(value, str):
                return f"参数 {name} 必须是字符串。"
            if expected == "object" and not isinstance(value, dict):
                return f"参数 {name} 必须是对象。"
        return None

    def execute(self, name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        tool = self._tools.get(str(name or ""))
        if tool is None:
            return ToolResult(False, f"未知工具：{name}", code="UNKNOWN_TOOL")

        payload = arguments if arguments is not None else {}
        invalid = self._validate_arguments(tool, payload)
        if invalid is not None:
            return ToolResult(False, invalid, code="INVALID_TOOL_ARGUMENTS")

        acquired = False
        if tool.requires_idle_engine:
            acquired = self.engine.try_set_status(Engine.Status.IDLE, Engine.Status.AGENT)
            if not acquired:
                return ToolResult(
                    False,
                    "引擎正在运行，当前不能切换项目。",
                    code="ENGINE_BUSY",
                )
        try:
            result = tool.handler(**payload)
            if not isinstance(result, ToolResult):
                return ToolResult(False, "工具返回了无效结果。", code="INVALID_TOOL_RESULT")
            return result
        except Exception as exc:
            LogManager.get().error(f"Agent 工具 {tool.name} 执行失败: {exc}")
            return ToolResult(False, "工具执行失败，详细信息已写入日志。", code="TOOL_FAILED")
        finally:
            if acquired:
                self.engine.release_status(Engine.Status.AGENT)
