"""Agent 专用的工具请求器。

翻译请求器的取消标记和客户端注册表是全局共享的，不能直接拿来跑 Agent。
本类保留相同的三家 SDK 依赖，但把生命周期完全隔离出来。
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any, Callable

import anthropic
import httpx
import openai
from google import genai
from google.genai import types

from base.Base import Base
from base.VersionManager import VersionManager
from module.Agent.types import AgentRequestResult, AgentToolCall, ToolDef, ToolResult
from module.Config import Config


TextDeltaCallback = Callable[[str], None]


THINKING_LEVELS = {"OFF", "LOW", "MEDIUM", "HIGH", "MAX"}


class AgentRequester:
    """执行一次 Agent 回合，并按需回报文本与思考增量。"""

    CLIENT_REGISTRY: dict[tuple[str, str, str, int], Any] = {}
    CLIENT_LOCK = threading.RLock()
    MAX_RETRY = 2
    RE_O_SERIES = re.compile(r"o\d(?:$|-)", re.IGNORECASE)
    RE_GPT5 = re.compile(r"gpt-5", re.IGNORECASE)
    RE_QWEN3_5 = re.compile(r"qwen3(?:\.|-)?5", re.IGNORECASE)
    RE_QWEN3 = re.compile(r"qwen3", re.IGNORECASE)
    RE_DOUBAO = (
        re.compile(r"doubao-seed-1(?:\.|-)6", re.IGNORECASE),
        re.compile(r"doubao-seed-1(?:\.|-)8", re.IGNORECASE),
        re.compile(r"doubao-seed-2(?:\.|-)0", re.IGNORECASE),
    )
    RE_THINKING = tuple(
        re.compile(name, re.IGNORECASE) for name in ("glm", "kimi", "deepseek")
    )
    RE_CLAUDE = tuple(
        re.compile(name, re.IGNORECASE)
        for name in ("claude-3-7-sonnet", "claude-opus-4-0", "claude-sonnet-4-0")
    )

    def __init__(
        self,
        config: Config,
        platform: dict[str, Any],
        *,
        thinking_level: Any = None,
    ) -> None:
        self.config = config
        self.platform = platform
        self.cancel_event = threading.Event()
        self.last_error_message = ""
        self.thinking_level = self._normalize_thinking_level(
            platform.get("thinking") if thinking_level is None else thinking_level
        )

    @staticmethod
    def _normalize_thinking_level(value: Any) -> str:
        """兼容平台旧布尔值与新档位结构，非法值保持关闭。"""
        if isinstance(value, dict):
            value = value.get("level", "OFF")
        elif value is True:
            value = "HIGH"
        level = str(value or "OFF").upper().strip()
        return level if level in THINKING_LEVELS else "OFF"

    @staticmethod
    def _value(value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    @staticmethod
    def _format_name(value: Any) -> str:
        return str(value or "").casefold()

    def _api_format(self) -> str:
        return self._format_name(self.platform.get("api_format"))

    def _api_key(self) -> str:
        keys = self.platform.get("api_key", [])
        if isinstance(keys, str):
            return keys
        if isinstance(keys, (list, tuple)):
            return str(keys[0]) if keys else "no_key_required"
        return "no_key_required"

    def _timeout(self) -> int:
        try:
            return max(1, int(getattr(self.config, "request_timeout", 120)))
        except (TypeError, ValueError):
            return 120

    def _client_key(self) -> tuple[str, str, str, int]:
        return (
            str(self.platform.get("api_url") or ""),
            self._api_key(),
            self._api_format(),
            self._timeout(),
        )

    @classmethod
    def _close_client(cls, client: Any) -> None:
        try:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        except Exception:
            pass

    def _get_client(self) -> Any:
        key = self._client_key()
        with self.CLIENT_LOCK:
            cached = self.CLIENT_REGISTRY.get(key)
            if cached is not None:
                return cached

        timeout = self._timeout()
        url = str(self.platform.get("api_url") or "")
        api_key = self._api_key()
        api_format = self._api_format()
        if api_format == str(Base.APIFormat.GOOGLE).casefold():
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    base_url=url,
                    timeout=timeout * 1000,
                    headers={
                        "User-Agent": f"RenpyBox/{VersionManager.get().get_version()} (https://github.com/dclef/RenpyBox",
                    },
                ),
            )
        elif api_format == str(Base.APIFormat.ANTHROPIC).casefold():
            client = anthropic.Anthropic(
                base_url=url,
                api_key=api_key,
                timeout=httpx.Timeout(read=timeout, pool=8.0, write=8.0, connect=8.0),
                max_retries=1,
            )
        else:
            client = openai.OpenAI(
                base_url=url,
                api_key=api_key,
                timeout=httpx.Timeout(read=timeout, pool=8.0, write=8.0, connect=8.0),
                max_retries=1,
            )

        with self.CLIENT_LOCK:
            existing = self.CLIENT_REGISTRY.get(key)
            if existing is not None:
                self._close_client(client)
                return existing
            self.CLIENT_REGISTRY[key] = client
            return client

    @classmethod
    def close_all_clients(cls) -> None:
        with cls.CLIENT_LOCK:
            clients = list({id(client): client for client in cls.CLIENT_REGISTRY.values()}.values())
            cls.CLIENT_REGISTRY.clear()
        for client in clients:
            cls._close_client(client)

    def cancel(self) -> None:
        self.cancel_event.set()
        # 只关闭当前 Agent 请求自己的客户端，不触碰翻译或其他 Agent 请求。
        key = self._client_key()
        with self.CLIENT_LOCK:
            client = self.CLIENT_REGISTRY.pop(key, None)
        if client is not None:
            self._close_client(client)

    def _cancelled(self) -> bool:
        return self.cancel_event.is_set()

    @staticmethod
    def _tool_defs(tools: list[ToolDef | dict[str, Any]]) -> list[ToolDef]:
        result: list[ToolDef] = []
        for item in tools:
            if isinstance(item, ToolDef):
                result.append(item)
                continue
            if not isinstance(item, dict):
                continue
            function = item.get("function", item)
            if not isinstance(function, dict) or not function.get("name"):
                continue
            schema = function.get("parameters") or item.get("input_schema") or {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            }
            result.append(ToolDef(
                name=str(function["name"]),
                description=str(function.get("description", "")),
                parameters_schema=schema,
                handler=lambda **_: ToolResult(False, "仅用于请求 schema。", code="SCHEMA_ONLY"),
            ))
        return result

    @staticmethod
    def _decode_arguments(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if not isinstance(value, str) or not value.strip():
            return {}
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}

    @staticmethod
    def _usage(value: Any, input_names: tuple[str, ...], output_names: tuple[str, ...]) -> dict[str, int]:
        result: dict[str, int] = {}
        for name in input_names:
            amount = AgentRequester._value(value, name, None)
            if amount is not None:
                result["input_tokens"] = int(amount)
                break
        for name in output_names:
            amount = AgentRequester._value(value, name, None)
            if amount is not None:
                result["output_tokens"] = int(amount)
                break
        return result

    @staticmethod
    def _emit_text(callback: TextDeltaCallback | None, text: Any) -> None:
        """把供应商增量安全地交给 UI；UI 回调异常不能中断网络流。"""
        if callback is None or not isinstance(text, str) or not text:
            return
        try:
            callback(text)
        except Exception:
            pass

    def request_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDef | dict[str, Any]],
        *,
        on_text_delta: TextDeltaCallback | None = None,
        on_reasoning_delta: TextDeltaCallback | None = None,
    ) -> AgentRequestResult:
        """执行一次工具请求；传入回调时按 token 增量回报可见文本。"""
        api_format = self._api_format()
        if api_format in {
            str(Base.APIFormat.DEEPL).casefold(),
            str(Base.APIFormat.DEEPLX).casefold(),
            str(Base.APIFormat.SAKURALLM).casefold(),
        }:
            return AgentRequestResult.failure(
                "UNSUPPORTED_AGENT_PLATFORM",
                "当前接口不支持 Agent 工具调用，请在 Agent 设置中选择 OpenAI、Anthropic 或 Google 接口。",
            )
        if api_format not in {
            str(Base.APIFormat.OPENAI).casefold(),
            str(Base.APIFormat.ANTHROPIC).casefold(),
            str(Base.APIFormat.GOOGLE).casefold(),
        }:
            return AgentRequestResult.failure("UNSUPPORTED_AGENT_PLATFORM", "当前接口格式不支持 Agent 工具调用。")

        definitions = self._tool_defs(tools)
        if not definitions:
            return AgentRequestResult.failure("NO_TOOLS", "没有可用的 Agent 工具。")

        last_error = "Agent 请求失败。"
        for attempt in range(self.MAX_RETRY):
            if self._cancelled():
                return AgentRequestResult.failure("CANCELLED", "Agent 请求已取消。")
            try:
                if api_format == str(Base.APIFormat.ANTHROPIC).casefold():
                    return self._request_anthropic(
                        messages,
                        definitions,
                        on_text_delta=on_text_delta,
                        on_reasoning_delta=on_reasoning_delta,
                    )
                if api_format == str(Base.APIFormat.GOOGLE).casefold():
                    return self._request_google(
                        messages,
                        definitions,
                        on_text_delta=on_text_delta,
                        on_reasoning_delta=on_reasoning_delta,
                    )
                return self._request_openai(
                    messages,
                    definitions,
                    on_text_delta=on_text_delta,
                    on_reasoning_delta=on_reasoning_delta,
                )
            except openai.BadRequestError as exc:
                self.last_error_message = str(exc)
                return AgentRequestResult.failure("BAD_REQUEST", "模型拒绝了 Agent 请求参数。")
            except Exception as exc:
                last_error = str(exc)
                self.last_error_message = last_error
                if self._cancelled():
                    return AgentRequestResult.failure("CANCELLED", "Agent 请求已取消。")
                if attempt + 1 < self.MAX_RETRY:
                    continue
        return AgentRequestResult.failure("REQUEST_FAILED", "Agent 请求失败，请检查接口配置或网络。")

    def _apply_openai_thinking(self, payload: dict[str, Any], messages: list[dict[str, Any]]) -> None:
        """按 OpenAI 兼容模型的约定写入思考控制参数。"""
        model = str(self.platform.get("model") or "")
        level = self.thinking_level
        extra_body = dict(payload.get("extra_body") or {})

        if self.RE_GPT5.search(model):
            extra_body["reasoning_effort"] = "none" if level == "OFF" else level.lower()
        elif self.RE_QWEN3_5.search(model):
            extra_body["enable_thinking"] = level != "OFF"
        elif any(pattern.search(model) for pattern in self.RE_DOUBAO):
            extra_body["reasoning_effort"] = "minimal" if level == "OFF" else level.lower()
        elif any(pattern.search(model) for pattern in self.RE_THINKING):
            if level == "OFF":
                extra_body["thinking"] = {"type": "disabled"}
            else:
                extra_body["thinking"] = {"type": "enabled"}
                if "deepseek" in model.casefold():
                    extra_body["reasoning_effort"] = (
                        "low" if level == "LOW" else "max" if level == "MAX" else "high"
                    )
        elif self.RE_QWEN3.search(model) and level == "OFF" and messages:
            # 旧版 Qwen 兼容端点没有 thinking 字段时，用提示后缀关闭思考。
            last = messages[-1]
            if last.get("role") == "user" and isinstance(last.get("content"), str):
                if "/no_think" not in last["content"]:
                    last["content"] = last["content"].rstrip() + "\n/no_think"

        if extra_body:
            payload["extra_body"] = extra_body

    @classmethod
    def _google_thinking_config(cls, model: str, level: str) -> Any:
        """构造 Gemini 思考配置；未知模型不强行注入供应商私有字段。"""
        lowered = model.casefold()
        known = any(token in lowered for token in ("gemini-2.5", "gemini-3"))
        if not known:
            return None

        budgets = {"OFF": 0, "LOW": 384, "MEDIUM": 768, "HIGH": 1024, "MAX": 1024}
        budget = budgets.get(level, 0)
        thinking_config_type = getattr(types, "ThinkingConfig", None)
        if not callable(thinking_config_type):
            return {"thinking_budget": budget, "include_thoughts": level != "OFF"}

        thinking_level_enum = getattr(types, "ThinkingLevel", None)
        if level != "OFF" and thinking_level_enum is not None:
            enum_name = "HIGH" if level == "MAX" else level
            enum_value = getattr(thinking_level_enum, enum_name, None)
            if enum_value is not None:
                try:
                    return thinking_config_type(
                        thinking_level=enum_value,
                        include_thoughts=True,
                    )
                except Exception:
                    pass
        try:
            return thinking_config_type(
                thinking_budget=budget,
                include_thoughts=level != "OFF",
            )
        except Exception:
            return {"thinking_budget": budget, "include_thoughts": level != "OFF"}

    def _request_openai(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDef],
        *,
        on_text_delta: TextDeltaCallback | None = None,
        on_reasoning_delta: TextDeltaCallback | None = None,
    ) -> AgentRequestResult:
        client = self._get_client()
        payload: dict[str, Any] = {
            "model": self.platform.get("model"),
            "messages": messages,
            "tools": [tool.openai_schema() for tool in tools],
            "tool_choice": "auto",
        }
        max_tokens = max(1024, int(getattr(self.config, "token_threshold", 0) or 0))
        model = str(self.platform.get("model") or "")
        api_url = str(self.platform.get("api_url") or "")
        if api_url.startswith("https://api.openai.com") or self.RE_O_SERIES.search(model):
            payload["max_completion_tokens"] = max_tokens
        else:
            payload["max_tokens"] = max_tokens
        self._apply_openai_thinking(payload, messages)
        if on_text_delta is not None or on_reasoning_delta is not None:
            return self._request_openai_stream(
                client,
                payload,
                on_text_delta,
                on_reasoning_delta,
            )

        response = client.chat.completions.create(**payload)
        return self._parse_openai_response(response)

    def _parse_openai_response(self, response: Any) -> AgentRequestResult:
        choices = self._value(response, "choices", []) or []
        message = self._value(choices[0], "message", {}) if choices else {}
        calls: list[AgentToolCall] = []
        for index, call in enumerate(self._value(message, "tool_calls", []) or []):
            function = self._value(call, "function", {})
            calls.append(
                AgentToolCall(
                    call_id=str(self._value(call, "id", f"call-{index}")),
                    name=str(self._value(function, "name", "")),
                    arguments=self._decode_arguments(self._value(function, "arguments", "{}")),
                )
            )
        usage = self._usage(
            self._value(response, "usage", None),
            ("prompt_tokens", "input_tokens"),
            ("completion_tokens", "output_tokens"),
        )
        return AgentRequestResult(
            success=True,
            text=str(self._value(message, "content", "") or ""),
            reasoning=str(self._value(message, "reasoning_content", "") or ""),
            tool_calls=calls,
            usage=usage,
        )

    def _request_openai_stream(
        self,
        client: Any,
        payload: dict[str, Any],
        callback: TextDeltaCallback | None,
        reasoning_callback: TextDeltaCallback | None,
    ) -> AgentRequestResult:
        """使用底层块流；SDK 的便捷管理器不接受 tools/tool_choice 参数。"""
        completions = client.chat.completions
        raw_stream = completions.create(**payload, stream=True)
        texts: list[str] = []
        reasoning: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        usage: dict[str, int] = {}
        try:
            for chunk in raw_stream:
                if self._cancelled():
                    return AgentRequestResult.failure("CANCELLED", "Agent 请求已取消。")
                usage = self._usage(
                    self._value(chunk, "usage", None),
                    ("prompt_tokens", "input_tokens"),
                    ("completion_tokens", "output_tokens"),
                ) or usage
                choices = self._value(chunk, "choices", []) or []
                delta = self._value(choices[0], "delta", {}) if choices else {}
                content = self._value(delta, "content", "")
                if isinstance(content, str) and content:
                    texts.append(content)
                    self._emit_text(callback, content)
                thought = self._value(delta, "reasoning_content", "")
                if isinstance(thought, str) and thought:
                    reasoning.append(thought)
                    self._emit_text(reasoning_callback, thought)
                for call_delta in self._value(delta, "tool_calls", []) or []:
                    index = int(self._value(call_delta, "index", len(calls)))
                    item = calls.setdefault(index, {"id": f"call-{index}", "name": "", "arguments": ""})
                    call_id = self._value(call_delta, "id", None)
                    if call_id:
                        item["id"] = str(call_id)
                    function = self._value(call_delta, "function", {})
                    name = self._value(function, "name", None)
                    if name:
                        item["name"] = str(name)
                    arguments = self._value(function, "arguments", "")
                    if isinstance(arguments, str):
                        item["arguments"] += arguments
        finally:
            close = getattr(raw_stream, "close", None)
            if callable(close):
                close()
        parsed_calls = [
            AgentToolCall(
                call_id=str(item["id"]),
                name=str(item["name"]),
                arguments=self._decode_arguments(item["arguments"]),
            )
            for _, item in sorted(calls.items())
        ]
        return AgentRequestResult(
            success=True,
            text="".join(texts),
            reasoning="".join(reasoning),
            tool_calls=parsed_calls,
            usage=usage,
        )

    @staticmethod
    def _anthropic_messages(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        system = "\n".join(str(item.get("content", "")) for item in messages if item.get("role") == "system")
        converted: list[dict[str, Any]] = []
        for item in messages:
            role = item.get("role")
            if role == "system":
                continue
            if role == "assistant" and item.get("tool_calls"):
                content: list[dict[str, Any]] = []
                if item.get("content"):
                    content.append({"type": "text", "text": str(item["content"])})
                for call in item["tool_calls"]:
                    function = call.get("function", {})
                    content.append({
                        "type": "tool_use",
                        "id": call.get("id", ""),
                        "name": function.get("name", ""),
                        "input": AgentRequester._decode_arguments(function.get("arguments", {})),
                    })
                converted.append({"role": "assistant", "content": content})
                continue
            if role == "tool":
                converted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": item.get("tool_call_id", ""),
                        "content": str(item.get("content", "")),
                    }],
                })
                continue
            converted.append({"role": role or "user", "content": item.get("content", "")})
        return system, converted

    def _request_anthropic(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDef],
        *,
        on_text_delta: TextDeltaCallback | None = None,
        on_reasoning_delta: TextDeltaCallback | None = None,
    ) -> AgentRequestResult:
        client = self._get_client()
        system, converted = self._anthropic_messages(messages)
        model = str(self.platform.get("model") or "")
        thinking_budget = {"LOW": 384, "MEDIUM": 768, "HIGH": 1024, "MAX": 1024}.get(
            self.thinking_level,
            0,
        )
        payload: dict[str, Any] = {
            "model": self.platform.get("model"),
            "messages": converted,
            "tools": [tool.anthropic_schema() for tool in tools],
            "max_tokens": max(
                1024,
                int(getattr(self.config, "token_threshold", 0) or 0),
                thinking_budget + 512,
            ),
        }
        if system:
            payload["system"] = system
        if any(pattern.search(model) for pattern in self.RE_CLAUDE):
            payload["thinking"] = (
                {"type": "disabled"}
                if self.thinking_level == "OFF"
                else {"type": "enabled", "budget_tokens": thinking_budget}
            )
        if on_text_delta is not None or on_reasoning_delta is not None:
            with client.messages.stream(**payload) as stream:
                for event in stream:
                    if self._cancelled():
                        return AgentRequestResult.failure("CANCELLED", "Agent 请求已取消。")
                    if str(self._value(event, "type", "")) != "content_block_delta":
                        continue
                    delta = self._value(event, "delta", {})
                    delta_type = str(self._value(delta, "type", ""))
                    if delta_type == "text_delta":
                        self._emit_text(on_text_delta, self._value(delta, "text", ""))
                    elif delta_type == "thinking_delta":
                        self._emit_text(
                            on_reasoning_delta,
                            self._value(delta, "thinking", ""),
                        )
                response = stream.get_final_message()
        else:
            response = client.messages.create(**payload)
        return self._parse_anthropic_response(response)

    def _parse_anthropic_response(self, response: Any) -> AgentRequestResult:
        calls: list[AgentToolCall] = []
        texts: list[str] = []
        thinking: list[str] = []
        for index, block in enumerate(self._value(response, "content", []) or []):
            block_type = self._value(block, "type", "")
            if block_type == "text":
                texts.append(str(self._value(block, "text", "") or ""))
            elif block_type == "thinking":
                thinking.append(str(self._value(block, "thinking", "") or ""))
            elif block_type == "tool_use":
                calls.append(AgentToolCall(
                    call_id=str(self._value(block, "id", f"call-{index}")),
                    name=str(self._value(block, "name", "")),
                    arguments=self._decode_arguments(self._value(block, "input", {})),
                ))
        usage = self._usage(
            self._value(response, "usage", None),
            ("input_tokens", "prompt_tokens"),
            ("output_tokens", "completion_tokens"),
        )
        return AgentRequestResult(
            success=True,
            text="".join(texts),
            reasoning="".join(thinking),
            tool_calls=calls,
            usage=usage,
        )

    @staticmethod
    def _google_content(role: str, parts: list[Any]) -> Any:
        try:
            return types.Content(role=role, parts=parts)
        except Exception:
            return {"role": role, "parts": parts}

    @staticmethod
    def _google_text_part(text: str) -> Any:
        try:
            return types.Part.from_text(text=text)
        except Exception:
            return {"text": text}

    @staticmethod
    def _google_function_call_part(name: str, args: dict[str, Any]) -> Any:
        try:
            return types.Part.from_function_call(name=name, args=args)
        except Exception:
            return {"function_call": {"name": name, "args": args}}

    @staticmethod
    def _google_function_response_part(name: str, content: str) -> Any:
        try:
            return types.Part.from_function_response(name=name, response={"content": content})
        except Exception:
            return {"function_response": {"name": name, "response": {"content": content}}}

    def _google_contents(self, messages: list[dict[str, Any]]) -> tuple[str, list[Any]]:
        system = "\n".join(str(item.get("content", "")) for item in messages if item.get("role") == "system")
        contents: list[Any] = []
        for item in messages:
            role = item.get("role")
            if role == "system":
                continue
            if role == "assistant" and item.get("tool_calls"):
                parts: list[Any] = []
                if item.get("content"):
                    parts.append(self._google_text_part(str(item["content"])))
                for call in item["tool_calls"]:
                    function = call.get("function", {})
                    parts.append(self._google_function_call_part(
                        str(function.get("name", "")),
                        self._decode_arguments(function.get("arguments", {})),
                    ))
                contents.append(self._google_content("model", parts))
                continue
            if role == "tool":
                name = str(item.get("name") or item.get("tool_call_id") or "tool")
                contents.append(self._google_content(
                    "user",
                    [self._google_function_response_part(name, str(item.get("content", "")))],
                ))
                continue
            contents.append(self._google_content(
                "user" if role != "assistant" else "model",
                [self._google_text_part(str(item.get("content", "") or ""))],
            ))
        return system, contents

    def _request_google(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDef],
        *,
        on_text_delta: TextDeltaCallback | None = None,
        on_reasoning_delta: TextDeltaCallback | None = None,
    ) -> AgentRequestResult:
        client = self._get_client()
        system, contents = self._google_contents(messages)
        declarations: list[Any] = []
        for tool in tools:
            try:
                declarations.append(types.FunctionDeclaration(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.parameters_schema,
                ))
            except Exception:
                declarations.append(tool.google_schema())
        try:
            google_tool = types.Tool(function_declarations=declarations)
        except Exception:
            google_tool = {"function_declarations": declarations}
        config_kwargs: dict[str, Any] = {
            "tools": [google_tool],
            "max_output_tokens": max(1024, int(getattr(self.config, "token_threshold", 0) or 0)),
        }
        thinking_config = self._google_thinking_config(
            str(self.platform.get("model") or ""),
            self.thinking_level,
        )
        if thinking_config is not None:
            config_kwargs["thinking_config"] = thinking_config
        if system:
            config_kwargs["system_instruction"] = system
        try:
            request_config = types.GenerateContentConfig(**config_kwargs)
        except Exception:
            request_config = config_kwargs
        if on_text_delta is not None or on_reasoning_delta is not None:
            return self._request_google_stream(
                client,
                contents,
                request_config,
                on_text_delta,
                on_reasoning_delta,
            )
        response = client.models.generate_content(
            model=self.platform.get("model"),
            contents=contents,
            config=request_config,
        )
        return self._parse_google_response(response)

    def _parse_google_response(self, response: Any) -> AgentRequestResult:
        candidates = self._value(response, "candidates", []) or []
        content = self._value(candidates[0], "content", {}) if candidates else {}
        parts = self._value(content, "parts", []) or []
        texts: list[str] = []
        reasoning: list[str] = []
        calls: list[AgentToolCall] = []
        for index, part in enumerate(parts):
            text = self._value(part, "text", None)
            if isinstance(text, str) and text:
                (reasoning if self._value(part, "thought", False) else texts).append(text)
            function_call = self._value(part, "function_call", None)
            if function_call is not None:
                calls.append(AgentToolCall(
                    call_id=str(self._value(function_call, "id", f"call-{index}")),
                    name=str(self._value(function_call, "name", "")),
                    arguments=self._decode_arguments(self._value(function_call, "args", {})),
                ))
        usage = self._usage(
            self._value(response, "usage_metadata", None),
            ("prompt_token_count", "input_tokens"),
            ("candidates_token_count", "output_token_count", "output_tokens"),
        )
        return AgentRequestResult(
            success=True,
            text="".join(texts),
            reasoning="".join(reasoning),
            tool_calls=calls,
            usage=usage,
        )

    def _request_google_stream(
        self,
        client: Any,
        contents: list[Any],
        request_config: Any,
        callback: TextDeltaCallback | None,
        reasoning_callback: TextDeltaCallback | None,
    ) -> AgentRequestResult:
        texts: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        usage: dict[str, int] = {}
        stream = client.models.generate_content_stream(
            model=self.platform.get("model"),
            contents=contents,
            config=request_config,
        )
        try:
            for chunk in stream:
                if self._cancelled():
                    return AgentRequestResult.failure("CANCELLED", "Agent 请求已取消。")
                usage = self._usage(
                    self._value(chunk, "usage_metadata", None),
                    ("prompt_token_count", "input_tokens"),
                    ("candidates_token_count", "output_token_count", "output_tokens"),
                ) or usage
                candidates = self._value(chunk, "candidates", []) or []
                content = self._value(candidates[0], "content", {}) if candidates else {}
                for index, part in enumerate(self._value(content, "parts", []) or []):
                    text = self._value(part, "text", None)
                    if isinstance(text, str) and text:
                        if bool(self._value(part, "thought", False)):
                            self._emit_text(reasoning_callback, text)
                            continue
                        # 兼容少数端点返回“累计文本”而不是增量文本。
                        current = "".join(texts)
                        delta = text[len(current):] if current and text.startswith(current) else text
                        if delta:
                            texts.append(delta)
                            self._emit_text(callback, delta)
                    function_call = self._value(part, "function_call", None)
                    if function_call is None:
                        continue
                    item = calls.setdefault(index, {
                        "id": f"call-{index}",
                        "name": "",
                        "arguments": {},
                    })
                    name = self._value(function_call, "name", None)
                    if name:
                        item["name"] = str(name)
                    args = self._value(function_call, "args", {})
                    if isinstance(args, dict):
                        item["arguments"].update(args)
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
        parsed_calls = [
            AgentToolCall(
                call_id=str(item["id"]),
                name=str(item["name"]),
                arguments=item["arguments"],
            )
            for _, item in sorted(calls.items())
        ]
        return AgentRequestResult(
            success=True,
            text="".join(texts),
            tool_calls=parsed_calls,
            usage=usage,
        )
