"""Agent 工具注册与服务端参数校验。"""

from __future__ import annotations

import importlib
from copy import deepcopy
from typing import Any, Callable

from base.LogManager import LogManager
from module.Config import Config
from module.Engine.Engine import Engine
from module.Localizer.Localizer import Localizer

from .types import ToolDef, ToolResult


ConfigLoader = Callable[[], Config]


def _lazy_tool_handler(
    module_name: str,
    function_name: str,
    config_loader: ConfigLoader,
) -> Callable[..., ToolResult]:
    """延迟加载工具实现，避免打开 Agent 页面时初始化整套翻译依赖。"""

    def handler(**arguments: Any) -> ToolResult:
        module = importlib.import_module(f"module.Agent.tools.{module_name}")
        function = getattr(module, function_name)
        return function(config_loader=config_loader, **arguments)

    return handler


class ToolDispatcher:
    """注册受控 Agent 工具，不向模型暴露任意 Python 调用能力。"""

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
        localizer = Localizer.get()
        return {
            "set_project": ToolDef(
                name="set_project",
                description=localizer.agent_tool_set_project_description,
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": localizer.agent_tool_project_path_description,
                        },
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
                handler=_lazy_tool_handler(
                    "project_tools",
                    "set_project",
                    self.config_loader,
                ),
                requires_idle_engine=True,
            ),
            "get_project_info": ToolDef(
                name="get_project_info",
                description=localizer.agent_tool_get_project_info_description,
                parameters_schema=deepcopy(empty_schema),
                handler=_lazy_tool_handler(
                    "project_tools",
                    "get_project_info",
                    self.config_loader,
                ),
            ),
            "inspect_translation_project": ToolDef(
                name="inspect_translation_project",
                description=localizer.agent_tool_inspect_translation_project_description,
                parameters_schema=deepcopy(empty_schema),
                handler=_lazy_tool_handler(
                    "inspection_tools",
                    "inspect_translation_project",
                    self.config_loader,
                ),
            ),
            "list_rpa_files": ToolDef(
                name="list_rpa_files",
                description=localizer.agent_tool_list_rpa_files_description,
                parameters_schema=deepcopy(empty_schema),
                handler=_lazy_tool_handler(
                    "project_tools",
                    "list_rpa_files",
                    self.config_loader,
                ),
            ),
            "scan_script_errors": ToolDef(
                name="scan_script_errors",
                description=localizer.agent_tool_scan_script_errors_description,
                parameters_schema=deepcopy(empty_schema),
                handler=_lazy_tool_handler(
                    "project_tools",
                    "scan_script_errors",
                    self.config_loader,
                ),
            ),
            "unpack_rpa_files": ToolDef(
                name="unpack_rpa_files",
                description=localizer.agent_tool_unpack_rpa_files_description,
                parameters_schema=deepcopy(empty_schema),
                handler=_lazy_tool_handler(
                    "archive_tools",
                    "unpack_rpa_files",
                    self.config_loader,
                ),
                requires_confirmation=True,
                requires_idle_engine=True,
            ),
            "optimize_old_new_translations": ToolDef(
                name="optimize_old_new_translations",
                description=localizer.agent_tool_optimize_old_new_translations_description,
                parameters_schema=deepcopy(empty_schema),
                handler=_lazy_tool_handler(
                    "translation_tools",
                    "optimize_old_new_translations",
                    self.config_loader,
                ),
                requires_confirmation=True,
                requires_idle_engine=True,
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
        localizer = Localizer.get()
        if not isinstance(arguments, dict):
            return localizer.agent_tool_arguments_must_be_object
        schema = tool.parameters_schema
        properties = schema.get("properties", {})
        unknown = set(arguments) - set(properties)
        if unknown:
            names = ", ".join(sorted(str(item) for item in unknown))
            return localizer.agent_tool_undeclared_arguments.format(names=names)
        missing = [name for name in schema.get("required", []) if name not in arguments]
        if missing:
            names = ", ".join(missing)
            return localizer.agent_tool_missing_arguments.format(names=names)
        for name, value in arguments.items():
            expected = properties.get(name, {}).get("type")
            if expected == "string" and not isinstance(value, str):
                return localizer.agent_tool_argument_must_be_string.format(name=name)
            if expected == "object" and not isinstance(value, dict):
                return localizer.agent_tool_argument_must_be_object.format(name=name)
        return None

    def execute(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        confirmed: bool = False,
        trusted_context: dict[str, Any] | None = None,
    ) -> ToolResult:
        localizer = Localizer.get()
        tool = self._tools.get(str(name or ""))
        if tool is None:
            return ToolResult(
                False,
                localizer.agent_tool_unknown.format(name=name),
                code="UNKNOWN_TOOL",
            )

        payload = arguments if arguments is not None else {}
        invalid = self._validate_arguments(tool, payload)
        if invalid is not None:
            return ToolResult(False, invalid, code="INVALID_TOOL_ARGUMENTS")
        if tool.requires_confirmation and not confirmed:
            return ToolResult(
                False,
                localizer.agent_tool_confirmation_required,
                code="CONFIRMATION_REQUIRED",
            )

        handler_arguments = dict(payload)
        if tool.name == "unpack_rpa_files":
            confirmed_game_dir = str((trusted_context or {}).get("game_dir", "")).strip()
            if not confirmed_game_dir:
                return ToolResult(
                    False,
                    localizer.agent_tool_confirmation_stale,
                    code="CONFIRMATION_STALE",
                )
            handler_arguments["_confirmed_game_dir"] = confirmed_game_dir
        elif tool.name == "optimize_old_new_translations":
            if not trusted_context:
                return ToolResult(
                    False,
                    localizer.agent_tool_confirmation_stale,
                    code="CONFIRMATION_STALE",
                )
            handler_arguments["_confirmed_context"] = dict(trusted_context)

        acquired = False
        if tool.requires_idle_engine:
            acquired = self.engine.try_set_status(Engine.Status.IDLE, Engine.Status.AGENT)
            if not acquired:
                return ToolResult(
                    False,
                    localizer.agent_tool_engine_busy,
                    code="ENGINE_BUSY",
                )
        try:
            result = tool.handler(**handler_arguments)
            if not isinstance(result, ToolResult):
                return ToolResult(
                    False,
                    localizer.agent_tool_invalid_result,
                    code="INVALID_TOOL_RESULT",
                )
            return result
        except Exception as exc:
            LogManager.get().error(f"Agent 工具 {tool.name} 执行失败: {exc}")
            return ToolResult(
                False,
                localizer.agent_tool_failed_logged,
                code="TOOL_FAILED",
            )
        finally:
            if acquired:
                self.engine.release_status(Engine.Status.AGENT)
