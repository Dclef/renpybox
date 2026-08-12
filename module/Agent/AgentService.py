"""Agent 会话循环与工具调度。"""

from __future__ import annotations

import json
from typing import Any, Callable

from module.Config import Config
from module.Engine.TaskRequester import TaskRequester
from module.Renpy.ProjectPaths import RenpyProjectPaths

from .AgentPromptBuilder import AgentPromptBuilder
from .ToolDispatcher import ToolDispatcher
from .types import AgentRunResult, ToolResult


EventCallback = Callable[[str, dict[str, Any]], None]


class AgentService:
    """运行有限轮数、串行工具调用的 Agent 会话。"""

    def __init__(
        self,
        *,
        config_loader: Callable[[], Config] | None = None,
        dispatcher: ToolDispatcher | None = None,
        max_iterations: int = 8,
        result_limit: int = 2000,
    ) -> None:
        self.config_loader = config_loader or (lambda: Config().load())
        self.dispatcher = dispatcher or ToolDispatcher(config_loader=self.config_loader)
        self.max_iterations = max(1, int(max_iterations))
        self.result_limit = max(256, int(result_limit))
        self.messages: list[dict[str, Any]] = []
        self._project_key = ""
        self._requester: TaskRequester | None = None
        self._project_changed_during_run = False

    def cancel(self) -> None:
        if self._requester is not None:
            self._requester.cancel_tools()

    def _emit(self, callback: EventCallback | None, event: str, payload: dict[str, Any]) -> None:
        if callback is not None:
            callback(event, payload)

    def _current_project_key(self, config: Config) -> str:
        paths = RenpyProjectPaths.from_config(config)
        return paths.project_key if paths is not None else ""

    def _reset_for_project_change(self, config: Config) -> None:
        key = self._current_project_key(config)
        if self._project_key and key != self._project_key:
            self.messages = []
        self._project_key = key

    def _finalize(self, result: AgentRunResult) -> AgentRunResult:
        # 项目在本轮被切换后，下一条用户消息必须从新项目重新建立上下文。
        if self._project_changed_during_run:
            config = self.config_loader()
            self.messages = []
            self._project_key = self._current_project_key(config)
            self._project_changed_during_run = False
        return result

    @staticmethod
    def _platform(config: Config) -> tuple[dict[str, Any] | None, str | None]:
        platform_id = int(getattr(config, "agent_platform", 0) or 0)
        if platform_id == 0:
            return None, "尚未设定 Agent 接口，请先在 Agent 页面选择 OpenAI、Anthropic 或 Google 接口。"
        platform = config.get_platform(platform_id)
        if not isinstance(platform, dict):
            return None, "Agent 接口配置不存在，请重新选择接口。"
        return platform, None

    @staticmethod
    def _assistant_message(result: Any) -> dict[str, Any]:
        return {
            "role": "assistant",
            "content": result.text or "",
            "tool_calls": [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in result.tool_calls
            ],
        }

    def run(self, user_text: str, *, callback: EventCallback | None = None) -> AgentRunResult:
        text = str(user_text or "").strip()
        if not text:
            return AgentRunResult(False, "请输入要执行的任务。", code="EMPTY_MESSAGE")

        config = self.config_loader()
        self._reset_for_project_change(config)
        platform, error = self._platform(config)
        if platform is None:
            return AgentRunResult(False, error or "Agent 接口未设置。", code="AGENT_PLATFORM_NOT_SET")

        if not self.messages:
            self.messages.append({
                "role": "system",
                "content": AgentPromptBuilder.build_system_prompt(config),
            })
        self.messages.append({"role": "user", "content": text})
        self._requester = TaskRequester(config, platform, 0)
        self._project_changed_during_run = False
        details: list[dict[str, Any]] = []

        for iteration in range(self.max_iterations):
            self._emit(callback, "request", {"iteration": iteration + 1})
            if callback is None:
                result = self._requester.request_tools(
                    self.messages,
                    list(self.dispatcher.tools.values()),
                )
            else:
                # 增量只用于界面显示；完整文本仍由 requester 返回并写入会话上下文。
                result = self._requester.request_tools(
                    self.messages,
                    list(self.dispatcher.tools.values()),
                    on_text_delta=lambda text: self._emit(
                        callback,
                        "reply_delta",
                        {"text": str(text or "")},
                    ),
                )
            if not result.success:
                self._emit(callback, "error", {
                    "code": result.error_code,
                    "message": result.error_message,
                })
                return self._finalize(AgentRunResult(
                    False,
                    result.error_message,
                    data={"events": details},
                    code=result.error_code,
                ))

            if not result.tool_calls:
                final_text = result.text.strip() or "Agent 没有返回可显示的内容。"
                self.messages.append({"role": "assistant", "content": final_text})
                self._emit(callback, "reply", {"message": final_text})
                return self._finalize(AgentRunResult(True, final_text, data={"events": details}))

            self.messages.append(self._assistant_message(result))
            for call in result.tool_calls:
                self._emit(callback, "tool_start", {
                    "name": call.name,
                    "arguments": call.arguments,
                })
                tool_result: ToolResult = self.dispatcher.execute(call.name, call.arguments)
                if call.name == "set_project" and tool_result.success:
                    self._project_changed_during_run = True
                summary = tool_result.model_message(self.result_limit)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call.call_id,
                    "name": call.name,
                    "content": summary,
                })
                detail = {
                    "name": call.name,
                    "success": tool_result.success,
                    "code": tool_result.code,
                    "message": tool_result.message,
                    "data": tool_result.data,
                }
                details.append(detail)
                self._emit(callback, "tool_done", detail)

        message = "Agent 达到最大工具调用轮数，已停止继续执行。"
        self._emit(callback, "error", {"code": "MAX_ITERATIONS", "message": message})
        return self._finalize(AgentRunResult(False, message, data={"events": details}, code="MAX_ITERATIONS"))
