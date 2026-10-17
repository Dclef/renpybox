"""Agent 会话循环与工具调度。"""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING, Any, Callable

from module.Config import Config
from module.Localizer.Localizer import Localizer
from module.Renpy.ProjectPaths import RenpyProjectPaths

from .AgentPromptBuilder import AgentPromptBuilder
from .ToolDispatcher import ToolDispatcher
from .types import AgentRunResult, ToolResult

if TYPE_CHECKING:
    from module.Engine.TaskRequester import TaskRequester


EventCallback = Callable[[str, dict[str, Any]], None]
ConfirmationCallback = Callable[[str, dict[str, Any]], bool | None]


class AgentService:
    """运行有限轮数、串行工具调用的 Agent 会话。"""

    # 会话历史按字符数设置上限；这是近似 token 预算，避免多轮对话无限增长。
    DEFAULT_MAX_CONTEXT_CHARS = 128_000
    # 长任务（逐批翻译）的额外轮次预算：普通对话仍受 max_iterations 限制，
    # 只有工具声称「还在推进」的迭代才从这笔预算里扣。
    DEFAULT_MAX_LONG_ITERATIONS = 240

    def __init__(
        self,
        *,
        config_loader: Callable[[], Config] | None = None,
        dispatcher: ToolDispatcher | None = None,
        pipeline_callbacks: dict[str, Callable[..., dict]] | None = None,
        max_iterations: int = 8,
        max_long_iterations: int = DEFAULT_MAX_LONG_ITERATIONS,
        result_limit: int = 2000,
        confirmation_timeout: float = 120.0,
        max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    ) -> None:
        self.config_loader = config_loader or (lambda: Config().load())
        self.dispatcher = dispatcher or ToolDispatcher(
            config_loader = self.config_loader,
            pipeline_callbacks = pipeline_callbacks,
        )
        self.max_iterations = max(1, int(max_iterations))
        self.max_long_iterations = max(0, int(max_long_iterations))
        self.result_limit = max(256, int(result_limit))
        self.confirmation_timeout = max(0.01, float(confirmation_timeout))
        self.max_context_chars = max(4096, int(max_context_chars))
        self.messages: list[dict[str, Any]] = []
        self._project_key = ""
        self._requester: "TaskRequester | None" = None
        self._project_changed_during_run = False
        self._cancel_event = threading.Event()
        self._run_state_lock = threading.Lock()
        # 本轮请求绑定的取消事件，供工具在执行期间检查停止信号。
        self._run_cancel_event: threading.Event | None = None

    def cancel(self) -> None:
        with self._run_state_lock:
            self._cancel_event.set()
        if self._requester is not None:
            self._requester.cancel_tools()

    def reset(self) -> None:
        """清空会话；仅在当前 Worker 结束后由页面调用。"""
        self._close_requester()
        self.messages = []
        self._project_key = ""
        self._project_changed_during_run = False

    def _close_requester(self) -> None:
        requester = self._requester
        self._requester = None
        if requester is not None:
            requester.close_tools()

    def _is_cancelled(self, run_cancel_event: threading.Event | None) -> bool:
        return self._cancel_event.is_set() or (
            run_cancel_event is not None and run_cancel_event.is_set()
        )

    def _cancel_check(self) -> bool:
        """供工具在本轮执行期间查询是否已请求停止。"""
        return self._is_cancelled(self._run_cancel_event)

    def _begin_tool_execution(self, run_cancel_event: threading.Event | None) -> bool:
        """原子确定停止与写工具启动的先后；启动后不承诺强制终止。"""
        with self._run_state_lock:
            return not self._is_cancelled(run_cancel_event)

    @staticmethod
    def _cancelled_message() -> str:
        return Localizer.get().agent_tool_cancelled

    def _append_skipped_tool_results(
        self,
        calls: list[Any],
        *,
        message: str,
    ) -> None:
        """补齐同轮未执行工具的结果，保持下一轮请求协议完整。"""
        for call in calls:
            self.messages.append({
                "role": "tool",
                "tool_call_id": call.call_id,
                "name": call.name,
                "content": message,
            })

    def confirmation_context(self, name: str) -> dict[str, Any]:
        """返回页面确认框所需的服务端可信上下文。"""
        if name == "optimize_old_new_translations":
            from .tools.translation_tools import old_new_replace_confirmation_context

            return old_new_replace_confirmation_context(config_loader=self.config_loader)
        if name == "refresh_replace_fallback":
            from .tools.translation_tools import old_new_replace_confirmation_context

            return old_new_replace_confirmation_context(config_loader=self.config_loader)
        if name == "apply_translation":
            from .tools.pipeline_tools import translation_apply_confirmation_context

            return translation_apply_confirmation_context(config_loader=self.config_loader)
        if name == "run_project_extraction":
            from module.OneKey.flow import (
                existing_translation_summary,
                resolve_extraction_incremental,
            )

            paths = RenpyProjectPaths.from_config(self.config_loader())
            if paths is None or not paths.game_dir.is_dir():
                return {}
            existing = existing_translation_summary(paths)
            incremental = resolve_extraction_incremental(
                "auto",
                bool(existing["exists"]),
            )
            return {
                "project_root": str(paths.project_root.resolve()),
                "language": paths.language,
                "incremental": incremental,
            }
        if name == "decompile_rpyc_files":
            paths = RenpyProjectPaths.from_config(self.config_loader())
            if paths is None or not paths.game_dir.is_dir():
                return {}
            return {"game_dir": str(paths.game_dir.resolve())}
        if name != "unpack_rpa_files":
            return {}
        paths = RenpyProjectPaths.from_config(self.config_loader())
        if paths is None or not paths.game_dir.is_dir():
            return {}
        game_dir = paths.game_dir.resolve()
        return {
            "game_dir": str(game_dir),
            "count": len(list(game_dir.glob("*.rpa"))),
        }

    def run_confirmed_tool(
        self,
        name: str,
        *,
        trusted_context: dict[str, Any],
        callback: EventCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> AgentRunResult:
        """执行一次已由界面确认的工具，并在执行前复核项目快照。"""
        with self._run_state_lock:
            self._cancel_event.clear()
        self._run_cancel_event = cancel_event

        tool_name = str(name or "")
        tool = self.dispatcher.tools.get(tool_name)
        localizer = Localizer.get()
        if tool is None:
            tool_result = ToolResult(
                False,
                localizer.agent_tool_unknown.format(name=tool_name),
                code="UNKNOWN_TOOL",
            )
        elif not tool.requires_confirmation:
            tool_result = ToolResult(
                False,
                localizer.agent_tool_confirmation_required,
                code="CONFIRMATION_REQUIRED",
            )
        elif self._is_cancelled(cancel_event):
            tool_result = ToolResult(
                False,
                self._cancelled_message(),
                code="USER_CANCELLED",
            )
        elif self.confirmation_context(tool_name) != dict(trusted_context or {}):
            tool_result = ToolResult(
                False,
                localizer.agent_project_changed,
                code="CONFIRMATION_STALE",
            )
        else:
            self._emit(callback, "tool_start", {"name": tool_name, "arguments": {}})
            if not self._begin_tool_execution(cancel_event):
                tool_result = ToolResult(
                    False,
                    self._cancelled_message(),
                    code="USER_CANCELLED",
                )
            else:
                tool_result = self.dispatcher.execute(
                    tool_name,
                    {},
                    confirmed=True,
                    trusted_context=dict(trusted_context),
                    cancel_check=self._cancel_check,
                )

        detail = {
            "name": tool_name,
            "success": tool_result.success,
            "code": tool_result.code,
            "message": tool_result.message,
            "data": tool_result.data,
        }
        self._emit(callback, "tool_done", detail)
        return AgentRunResult(
            tool_result.success,
            tool_result.message,
            data={"events": [detail]},
            code=tool_result.code,
        )

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

    def _context_size(self) -> int:
        """估算当前会话占用的上下文字符数。"""
        try:
            return len(json.dumps(self.messages, ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            return sum(len(str(message)) for message in self.messages)

    def _trim_history(self) -> None:
        """按完整用户回合裁掉最旧历史，避免留下孤立的工具调用消息。"""
        while self._context_size() > self.max_context_chars:
            user_indices = [
                index
                for index, message in enumerate(self.messages)
                if message.get("role") == "user"
            ]
            if len(user_indices) < 2:
                # 只剩当前回合时（逐批翻译就是这样），按「助手轮次」为边界
                # 丢掉较早的工具往返，保留系统提示与用户诉求。
                if not self._trim_within_turn():
                    return
                continue
            del self.messages[user_indices[0]:user_indices[1]]

    def _trim_within_turn(self) -> bool:
        """单回合内裁剪：切到下一个助手消息边界，保证不会留下孤立工具消息。"""

        if len(self.messages) < 4:
            return False
        if self.messages[0].get("role") != "system":
            return False
        if self.messages[1].get("role") != "user":
            return False
        boundary = None
        for index in range(3, len(self.messages)):
            if self.messages[index].get("role") == "assistant":
                boundary = index
                break
        if boundary is None:
            return False
        del self.messages[2:boundary]
        return True

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
        try:
            platform_id = int(getattr(config, "agent_platform", -1))
        except (TypeError, ValueError):
            # 配置文件可能被手工编辑；非法索引按未设置处理，不能让 Worker 崩溃。
            platform_id = -1
        if platform_id < 0:
            return None, Localizer.get().agent_api_unset
        platform = config.get_platform(platform_id)
        if not isinstance(platform, dict):
            return None, Localizer.get().agent_api_missing
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

    def run(
        self,
        user_text: str,
        *,
        callback: EventCallback | None = None,
        confirmation_callback: ConfirmationCallback | None = None,
        thinking_level: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> AgentRunResult:
        self._close_requester()
        with self._run_state_lock:
            self._cancel_event.clear()
        self._run_cancel_event = cancel_event
        try:
            return self._run(
                user_text,
                callback=callback,
                confirmation_callback=confirmation_callback,
                thinking_level=thinking_level,
                cancel_event=cancel_event,
            )
        finally:
            self._run_cancel_event = None
            self._close_requester()

    def _run(
        self,
        user_text: str,
        *,
        callback: EventCallback | None = None,
        confirmation_callback: ConfirmationCallback | None = None,
        thinking_level: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> AgentRunResult:
        text = str(user_text or "").strip()
        if not text:
            return AgentRunResult(
                False,
                Localizer.get().agent_task_empty,
                code="EMPTY_MESSAGE",
            )
        if self._is_cancelled(cancel_event):
            return AgentRunResult(False, self._cancelled_message(), code="CANCELLED")

        config = self.config_loader()
        self._reset_for_project_change(config)
        platform, error = self._platform(config)
        if platform is None:
            return AgentRunResult(
                False,
                error or Localizer.get().agent_api_not_set,
                code="AGENT_PLATFORM_NOT_SET",
            )

        if not self.messages:
            self.messages.append({
                "role": "system",
                "content": AgentPromptBuilder.build_system_prompt(config),
            })
        self.messages.append({"role": "user", "content": text})
        self._trim_history()
        # Agent 的思考等级是本次 Agent 请求的覆盖项，不写回平台配置，
        # 这样平台页面保持 OFF 时，助手也不会悄悄替用户打开思考模式。
        request_platform = dict(platform)
        if thinking_level is not None:
            request_platform["thinking"] = {"level": str(thinking_level).upper().strip()}
        # 翻译请求器依赖三家 SDK，只在 Agent 真正开始联网时加载。
        from module.Engine.TaskRequester import TaskRequester

        self._requester = TaskRequester(config, request_platform, 0)
        self._project_changed_during_run = False
        details: list[dict[str, Any]] = []

        iteration = 0
        long_iterations = 0
        while iteration < self.max_iterations:
            iteration_results: list[ToolResult] = []
            # 工具结果会在本轮继续增长；每次请求前再次裁剪旧回合。
            self._trim_history()
            if self._is_cancelled(cancel_event):
                return self._finalize(AgentRunResult(
                    False,
                    self._cancelled_message(),
                    data={"events": details},
                    code="CANCELLED",
                ))
            self._emit(callback, "request", {"iteration": iteration + 1})
            if callback is None:
                result = self._requester.request_tools(
                    self.messages,
                    list(self.dispatcher.tools.values()),
                )
            else:
                # 增量只用于界面显示；完整文本仍由 requester 返回并写入会话上下文。
                reasoning_seen = False

                def emit_reasoning(text: str) -> None:
                    nonlocal reasoning_seen
                    if text:
                        reasoning_seen = True
                        self._emit(callback, "reasoning_delta", {"text": str(text)})

                result = self._requester.request_tools(
                    self.messages,
                    list(self.dispatcher.tools.values()),
                    on_text_delta=lambda text: self._emit(
                        callback,
                        "reply_delta",
                        {"text": str(text or "")},
                    ),
                    on_reasoning_delta=emit_reasoning,
                )
                # 某些兼容端点只在最终响应中提供 reasoning_content。
                if result.success and result.reasoning and not reasoning_seen:
                    emit_reasoning(result.reasoning)
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
                final_text = result.text.strip() or Localizer.get().agent_reply_empty
                self.messages.append({"role": "assistant", "content": final_text})
                self._emit(callback, "reply", {"message": final_text})
                return self._finalize(AgentRunResult(True, final_text, data={"events": details}))

            self.messages.append(self._assistant_message(result))
            for call_index, call in enumerate(result.tool_calls):
                tool = self.dispatcher.tools.get(call.name)
                if self._is_cancelled(cancel_event):
                    tool_result = ToolResult(
                        False,
                        self._cancelled_message(),
                        code="USER_CANCELLED",
                    )
                elif tool is not None and tool.requires_confirmation:
                    confirmation = {
                        "name": call.name,
                        "arguments": call.arguments,
                        "data": self.confirmation_context(call.name),
                    }
                    if confirmation_callback is None:
                        approved = False
                    else:
                        approved = confirmation_callback(call.name, confirmation)
                    if approved is not True:
                        code = (
                            "USER_CANCELLED"
                            if approved is False or self._is_cancelled(cancel_event)
                            else "CONFIRMATION_TIMEOUT"
                        )
                        message = (
                            self._cancelled_message()
                            if code == "USER_CANCELLED"
                            else Localizer.get().agent_confirmation_timeout
                        )
                        tool_result = ToolResult(False, message, code=code)
                    elif self._is_cancelled(cancel_event):
                        tool_result = ToolResult(
                            False,
                            self._cancelled_message(),
                            code="USER_CANCELLED",
                        )
                    else:
                        current_context = self.confirmation_context(call.name)
                        if self._is_cancelled(cancel_event):
                            tool_result = ToolResult(
                                False,
                                self._cancelled_message(),
                                code="USER_CANCELLED",
                            )
                        elif current_context != confirmation["data"]:
                            tool_result = ToolResult(
                                False,
                                Localizer.get().agent_project_changed,
                                code="CONFIRMATION_STALE",
                            )
                        else:
                            self._emit(callback, "tool_start", {
                                "name": call.name,
                                "arguments": call.arguments,
                            })
                            if not self._begin_tool_execution(cancel_event):
                                tool_result = ToolResult(
                                    False,
                                    self._cancelled_message(),
                                    code="USER_CANCELLED",
                                )
                            else:
                                tool_result = self.dispatcher.execute(
                                    call.name,
                                    call.arguments,
                                    confirmed=True,
                                    trusted_context=confirmation["data"],
                                )
                else:
                    self._emit(callback, "tool_start", {
                        "name": call.name,
                        "arguments": call.arguments,
                    })
                    tool_result = self.dispatcher.execute(
                        call.name,
                        call.arguments,
                        cancel_check=self._cancel_check,
                    )
                if call.name == "set_project" and tool_result.success:
                    self._project_changed_during_run = True
                summary = tool_result.model_message(
                    tool.result_limit if tool is not None and tool.result_limit else self.result_limit
                )
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call.call_id,
                    "name": call.name,
                    "content": summary,
                })
                iteration_results.append(tool_result)
                detail = {
                    "name": call.name,
                    "success": tool_result.success,
                    "code": tool_result.code,
                    "message": tool_result.message,
                    "data": tool_result.data,
                }
                details.append(detail)
                self._emit(callback, "tool_done", detail)
                if tool_result.code in {"USER_CANCELLED", "CONFIRMATION_TIMEOUT"}:
                    self._append_skipped_tool_results(
                        result.tool_calls[call_index + 1:],
                        message=tool_result.message,
                    )
                    return self._finalize(AgentRunResult(
                        False,
                        tool_result.message,
                        data={"events": details},
                        code=tool_result.code,
                    ))

            # 长任务（例如逐批翻译）每个迭代都在推进时不占用普通轮次预算，
            # 否则普通的 8 轮上限会让一盘游戏的翻译在半路被截断。
            if any(item.continues for item in iteration_results):
                long_iterations += 1
                if long_iterations >= self.max_long_iterations:
                    message = Localizer.get().agent_max_iterations
                    self._emit(callback, "error", {
                        "code": "MAX_ITERATIONS",
                        "message": message,
                    })
                    return self._finalize(AgentRunResult(
                        False,
                        message,
                        data={"events": details},
                        code="MAX_ITERATIONS",
                    ))
            else:
                iteration += 1

        message = Localizer.get().agent_max_iterations
        self._emit(callback, "error", {"code": "MAX_ITERATIONS", "message": message})
        return self._finalize(AgentRunResult(False, message, data={"events": details}, code="MAX_ITERATIONS"))