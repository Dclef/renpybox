"""Agent 工具协议的稳定数据结构。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable


ProgressCallback = Callable[[str, float], None]
ToolHandler = Callable[..., "ToolResult"]


@dataclass
class ToolResult:
    """工具同时面向模型和 UI 的结果。"""

    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    code: str = "OK"
    # 该结果是否说明「长任务仍在推进」。为真时本回合不计入普通轮次上限，
    # 让逐批翻译这类天然多轮的任务跑完，同时普通对话仍受 max_iterations 约束。
    continues: bool = False

    def model_message(self, limit: int = 2000) -> str:
        """返回限制长度的模型摘要，避免把完整扫描结果塞进上下文。"""
        text = str(self.message or "")
        if self.data:
            text = f"{text}\n{json.dumps(self.data, ensure_ascii=False, default=str)}"
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 24)] + "... [truncated]"

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "code": self.code,
            "message": self.message,
            "data": self.data,
        }


@dataclass(frozen=True)
class ToolDef:
    """一个可暴露给模型的工具定义。"""

    name: str
    description: str
    parameters_schema: dict[str, Any]
    handler: ToolHandler
    requires_confirmation: bool = False
    requires_idle_engine: bool = False
    # 该工具的结果可能较长（例如一次返回一整批待译条目），单独放大截断上限。
    result_limit: int | None = None

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }

    def anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters_schema,
        }

    def google_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema,
        }


@dataclass(frozen=True)
class AgentToolCall:
    """模型返回的一次工具调用。"""

    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class AgentRequestResult:
    """一次非流式 Agent 请求的统一结果。"""

    success: bool
    text: str = ""
    tool_calls: list[AgentToolCall] = field(default_factory=list)
    reasoning: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""

    @classmethod
    def failure(cls, code: str, message: str) -> "AgentRequestResult":
        return cls(
            success=False,
            error_code=code,
            error_message=message,
        )

    def tool_payload(self) -> str:
        """将工具调用编码为稳定文本，便于日志和测试。"""
        return json.dumps(
            [
                {
                    "id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
                for call in self.tool_calls
            ],
            ensure_ascii=False,
        )


@dataclass
class AgentRunResult:
    """一次完整会话回合的结果。"""

    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    code: str = "OK"
