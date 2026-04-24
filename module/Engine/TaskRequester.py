import json
import re
import threading
import time
from functools import lru_cache
from typing import Any

import anthropic
import httpx
import openai
from google import genai
from google.genai import types

from base.Base import Base
from base.BaseLanguage import BaseLanguage
from base.VersionManager import VersionManager
from base.compat import StrEnum
from module.Config import Config
from module.Engine.Engine import Engine
from module.Localizer.Localizer import Localizer


class ThinkingLevel(StrEnum):
    """思考挡位枚举"""

    OFF = "OFF"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TaskRequester(Base):

    # 密钥索引
    API_KEY_INDEX: int = 0
    MAX_REQUEST_RETRY: int = 3
    DEFAULT_MAX_OUTPUT_TOKENS: int = 4 * 1024
    GOOGLE_GEMINI_25_FLASH_MAX_OUTPUT_TOKENS: int = 16 * 1024

    # 连接缓存（用于停止任务时快速中断网络请求）
    CLIENT_REGISTRY: dict[tuple[str, str, Base.APIFormat, int], Any] = {}

    # qwen3_instruct_8b_q6k（本地/Sakura 常见命名）
    RE_QWEN3: re.Pattern = re.compile(r"qwen3", flags = re.IGNORECASE)

    # qwen3.5（OpenAI 兼容接口常见命名）
    RE_QWEN3_5: re.Pattern = re.compile(r"qwen3(?:\.|-)?5", flags = re.IGNORECASE)

    # gemini-2.5-pro
    RE_GEMINI_2_5_PRO: re.Pattern = re.compile(r"gemini-2\.5-pro", flags = re.IGNORECASE)

    # gemini-2.5-flash
    RE_GEMINI_2_5_FLASH: re.Pattern = re.compile(r"gemini-2\.5-flash", flags = re.IGNORECASE)

    # gemini-3-pro
    RE_GEMINI_3_PRO: re.Pattern = re.compile(r"gemini-3-pro", flags = re.IGNORECASE)

    # gemini-3-flash
    RE_GEMINI_3_FLASH: re.Pattern = re.compile(r"gemini-3-flash", flags = re.IGNORECASE)

    # gemini-3.1-pro
    RE_GEMINI_3_1_PRO: re.Pattern = re.compile(r"gemini-3\.1-pro", flags = re.IGNORECASE)

    # gpt-5 系列
    RE_GPT5: re.Pattern = re.compile(r"gpt-5", flags = re.IGNORECASE)

    # doubao-seed 系列（兼容 2.0 / 2-0 两种写法）
    RE_DOUBAO: tuple[re.Pattern, ...] = (
        re.compile(r"doubao-seed-1(?:\.|-)6", flags = re.IGNORECASE),
        re.compile(r"doubao-seed-1(?:\.|-)8", flags = re.IGNORECASE),
        re.compile(r"doubao-seed-2(?:\.|-)0", flags = re.IGNORECASE),
    )

    # thinking.type 系列（GLM / Kimi / DeepSeek）
    RE_THINKING: tuple[re.Pattern, ...] = (
        re.compile(r"glm", flags = re.IGNORECASE),
        re.compile(r"kimi", flags = re.IGNORECASE),
        re.compile(r"deepseek", flags = re.IGNORECASE),
    )

    # Claude
    RE_CLAUDE: tuple[re.Pattern] = (
        re.compile(r"claude-3-7-sonnet", flags = re.IGNORECASE),
        re.compile(r"claude-opus-4-0", flags = re.IGNORECASE),
        re.compile(r"claude-sonnet-4-0", flags = re.IGNORECASE),
    )

    # o1 o3-mini o4-mini-20240406
    RE_O_SERIES: re.Pattern = re.compile(r"o\d$|o\d-", flags = re.IGNORECASE)

    # 正则
    RE_LINE_BREAK: re.Pattern = re.compile(r"\n+")
    RE_JSONLINE_FENCE: re.Pattern = re.compile(r"```jsonline\s*(.*?)\s*```", flags = re.IGNORECASE | re.DOTALL)
    RE_INLINE_JSON_OBJECT: re.Pattern = re.compile(r"\{[^{}]+\}")

    # 类线程锁
    LOCK: threading.Lock = threading.Lock()

    def __init__(self, config: Config, platform: dict[str, Any], current_round: int) -> None:
        super().__init__()

        # 初始化
        self.config = config
        self.platform = platform
        self.current_round = current_round
        self.thinking_level = self.resolve_thinking_level(self.platform.get("thinking"))

    @classmethod
    def resolve_thinking_level(cls, thinking: Any) -> ThinkingLevel:
        """兼容旧布尔配置与新思考挡位配置，统一解析为 ThinkingLevel。"""

        if isinstance(thinking, dict):
            level = str(thinking.get("level", "OFF")).upper().strip()
            try:
                return ThinkingLevel(level)
            except ValueError:
                return ThinkingLevel.OFF

        if thinking == True:
            return ThinkingLevel.HIGH

        return ThinkingLevel.OFF

    # 重置
    @classmethod
    def reset(cls) -> None:
        cls.API_KEY_INDEX: int = 0
        cls.close_all_clients()

    # 关闭所有客户端连接（用于停止任务时快速中断网络请求）
    @classmethod
    def close_all_clients(cls) -> None:
        with cls.LOCK:
            for client in list(cls.CLIENT_REGISTRY.values()):
                try:
                    close = getattr(client, "close", None)
                    if callable(close):
                        close()
                except Exception:
                    pass

            cls.CLIENT_REGISTRY.clear()
            cls.get_client.cache_clear()

    @classmethod
    def get_key(cls, keys: list[str]) -> str:
        key: str = ""

        if len(keys) == 0:
            key = "no_key_required"
        elif len(keys) == 1:
            key = keys[0]
        else:
            key = keys[cls.API_KEY_INDEX % len(keys)]
            cls.API_KEY_INDEX = cls.API_KEY_INDEX + 1

        return key

    # 获取客户端
    @classmethod
    @lru_cache(maxsize = None)
    def get_client(cls, url: str, key: str, format: Base.APIFormat, timeout: int):
        # connect (连接超时):
        #   建议值: 5.0 到 10.0 秒。
        #   解释: 建立到 LLM API 服务器的 TCP 连接。通常这个过程很快，但网络波动时可能需要更长时间。设置过短可能导致在网络轻微抖动时连接失败。
        # read (读取超时):
        #   建议值: 非常依赖具体场景。
        #   对于快速响应的简单任务（如分类、简单问答）：10.0 到 30.0 秒。
        #   对于中等复杂任务或中等长度输出：30.0 到 90.0 秒。
        #   对于复杂任务或长文本生成（如 GPT-4 生成大段代码或文章）：60.0 到 180.0 秒，甚至更长。
        #   解释: 这是从发送完请求到接收完整个响应体的最大时间。这是 LLM 请求中最容易超时的部分。你需要根据你的模型、提示和期望输出来估算一个合理的上限。强烈建议监控你的P95/P99响应时间来调整这个值。
        # write (写入超时):
        #   建议值: 5.0 到 10.0 秒。
        #   解释: 发送请求体（包含你的 prompt）到服务器的时间。除非你的 prompt 非常巨大（例如，包含超长上下文），否则这个过程通常很快。
        # pool (从连接池获取连接超时):
        #   建议值: 5.0 到 10.0 秒 (如果并发量高，可以适当增加)。
        #   解释: 如果你使用 httpx.Client 并且并发发起大量请求，可能会耗尽连接池中的连接。此参数定义了等待可用连接的最长时间。
        cache_key = (url, key, format, timeout)

        if format == Base.APIFormat.SAKURALLM:
            client = openai.OpenAI(
                base_url = url,
                api_key = key,
                timeout = httpx.Timeout(
                    read = timeout,
                    pool = 8.00,
                    write = 8.00,
                    connect = 8.00,
                ),
                max_retries = 1,
            )
        elif format == Base.APIFormat.GOOGLE:
            # https://github.com/googleapis/python-genai
            client = genai.Client(
                api_key = key,
                http_options = types.HttpOptions(
                    base_url = url,
                    timeout = timeout * 1000,
                    headers = {
                        "User-Agent": f"RenpyBox/{VersionManager.get().get_version()} (https://github.com/dclef/RenpyBox",
                    },
                ),
            )
        elif format == Base.APIFormat.ANTHROPIC:
            client = anthropic.Anthropic(
                base_url = url,
                api_key = key,
                timeout = httpx.Timeout(
                    read = timeout,
                    pool = 8.00,
                    write = 8.00,
                    connect = 8.00,
                ),
                max_retries = 1,
            )
        elif format in (Base.APIFormat.DEEPL, Base.APIFormat.DEEPLX):
            client = httpx.Client(
                timeout = httpx.Timeout(
                    read = timeout,
                    pool = 8.00,
                    write = 8.00,
                    connect = 8.00,
                ),
                follow_redirects = True,
                headers = {
                    "User-Agent": f"Renpybox/{VersionManager.get().get_version()} (https://github.com/dclef/RenpyBox)",
                },
            )
        else:
            client = openai.OpenAI(
                base_url = url,
                api_key = key,
                timeout = httpx.Timeout(
                    read = timeout,
                    pool = 8.00,
                    write = 8.00,
                    connect = 8.00,
                ),
                max_retries = 1,
            )

        cls.CLIENT_REGISTRY[cache_key] = client
        return client

    # 发起请求
    def request(self, messages: list[dict]) -> tuple[bool, str, str, int, int]:
        # 添加请求入口日志
        self.debug(f"[API-REQUEST] 准备请求: model={self.platform.get('model')}, "
                   f"api_format={self.platform.get('api_format')}, "
                   f"messages={len(messages)}, round={self.current_round+1}")
        
        args: dict[str, float] = {}
        if self.platform.get('top_p_custom_enable') == True:
            args["top_p"] = self.platform.get('top_p')
        if self.platform.get('temperature_custom_enable') == True:
            args["temperature"] = self.platform.get('temperature')
        if self.platform.get('presence_penalty_custom_enable') == True:
            args["presence_penalty"] = self.platform.get('presence_penalty')
        if self.platform.get('frequency_penalty_custom_enable') == True:
            args["frequency_penalty"] = self.platform.get('frequency_penalty')

        thinking_level = self.thinking_level

        def dispatch() -> tuple[bool, str, str, int, int]:
            if self.platform.get('api_format') == Base.APIFormat.SAKURALLM:
                return self.request_sakura(messages, thinking_level, args)
            elif self.platform.get('api_format') == Base.APIFormat.GOOGLE:
                return self.request_google(messages, thinking_level, args)
            elif self.platform.get('api_format') == Base.APIFormat.ANTHROPIC:
                return self.request_anthropic(messages, thinking_level, args)
            elif self.platform.get('api_format') == Base.APIFormat.DEEPL:
                return self.request_deepl(messages)
            elif self.platform.get('api_format') == Base.APIFormat.DEEPLX:
                return self.request_deeplx(messages)
            else:
                return self.request_openai(messages, thinking_level, args)

        last_result: tuple[bool, str, str, int, int] = (True, None, None, None, None)
        for attempt in range(1, __class__.MAX_REQUEST_RETRY + 1):
            # If user has requested a stop, abort new requests immediately
            if Engine.get().get_status() == Engine.Status.STOPPING:
                self.debug(f"[API-REQUEST] 用户请求停止，中断请求")
                return True, None, None, None, None

            self.debug(f"[API-REQUEST] 尝试 {attempt}/{__class__.MAX_REQUEST_RETRY}")
            last_result = dispatch()
            skip = last_result[0]
            if skip is False:
                self.debug(f"[API-REQUEST] 请求成功")
                return last_result
            if attempt < __class__.MAX_REQUEST_RETRY:
                delay = min(2 ** (attempt - 1), 5)
                self.debug(f"[API-REQUEST] 请求失败，{delay}秒后重试")
                time.sleep(delay)

        self.warning(f"[API-REQUEST] 请求失败，已达最大重试次数")
        return last_result

    # 生成请求参数
    def generate_sakura_args(self, messages: list[dict[str, str]], thinking_level: ThinkingLevel, args: dict[str, float]) -> dict:
        args: dict = args | {
            "model": self.platform.get('model'),
            "messages": messages,
            "max_tokens": max(__class__.DEFAULT_MAX_OUTPUT_TOKENS, self.config.token_threshold),
            "extra_headers": {
                "User-Agent": f"Renpybox/{VersionManager.get().get_version()} (https://github.com/dclef/RenpyBox)"
            }
        }

        # 思考模式切换 - QWEN3（与 OpenAI 格式保持一致）
        if __class__.RE_QWEN3.search(self.platform.get('model')) is not None:
            if thinking_level == ThinkingLevel.OFF and len(messages) > 0:
                if "/no_think" not in messages[-1].get("content", ""):
                    messages[-1]["content"] = messages[-1].get('content') + "\n" + "/no_think"

        return args

    # 发起请求
    def request_sakura(self, messages: list[dict[str, str]], thinking_level: ThinkingLevel, args: dict[str, float]) -> tuple[bool, str, str, int, int]:
        try:
            # 获取客户端
            with __class__.LOCK:
                client = __class__.get_client(
                    url = self.platform.get('api_url'),
                    key = __class__.get_key(self.platform.get('api_key')),
                    format = self.platform.get('api_format'),
                    timeout = self.config.request_timeout,
                )

            # 发起请求
            response = client.chat.completions.create(
                **self.generate_sakura_args(messages, thinking_level, args)
            )

            # 提取回复内容（支持 Qwen3 的 <think> 标签）
            message = response.choices[0].message
            if hasattr(message, "reasoning_content") and isinstance(message.reasoning_content, str):
                response_think = __class__.RE_LINE_BREAK.sub("\n", message.reasoning_content.strip())
                response_result = message.content.strip()
            elif "</think>" in message.content:
                splited = message.content.split("</think>")
                response_think = __class__.RE_LINE_BREAK.sub("\n", splited[0].removeprefix("<think>").strip())
                response_result = splited[-1].strip()
            else:
                response_think = ""
                response_result = message.content.strip()
        except Exception as e:
            self.error(f"{Localizer.get().log_task_fail}", e)
            return True, None, None, None, None

        # 获取输入消耗
        try:
            input_tokens = int(response.usage.prompt_tokens)
        except Exception:
            input_tokens = 0

        # 获取输出消耗
        try:
            output_tokens = int(response.usage.completion_tokens)
        except Exception:
            output_tokens = 0

        return False, "", response_result, input_tokens, output_tokens

    # 生成请求参数
    def generate_openai_args(self, messages: list[dict[str, str]], thinking_level: ThinkingLevel, args: dict[str, float]) -> dict:
        args: dict = args | {
            "model": self.platform.get('model'),
            "messages": messages,
            "max_tokens": max(__class__.DEFAULT_MAX_OUTPUT_TOKENS, self.config.token_threshold),
            "extra_headers": {
                "User-Agent": f"Renpybox/{VersionManager.get().get_version()} (https://github.com/dclef/RenpyBox)"
            }
        }

        model = str(self.platform.get('model') or "")

        # OpenAI O-Series 模型兼容性处理
        if (
            self.platform.get('api_url').startswith("https://api.openai.com") or
            __class__.RE_O_SERIES.search(model) is not None
        ):
            args.pop("max_tokens", None)
            args["max_completion_tokens"] = max(__class__.DEFAULT_MAX_OUTPUT_TOKENS, self.config.token_threshold)

        extra_body: dict[str, Any] = {}

        # GPT-5 系列支持 reasoning_effort 多挡位控制。
        if __class__.RE_GPT5.search(model) is not None:
            if thinking_level == ThinkingLevel.OFF:
                extra_body["reasoning_effort"] = "none"
            else:
                extra_body["reasoning_effort"] = thinking_level.lower()

        # Qwen3.5 在 OpenAI 兼容接口上使用 enable_thinking 开关。
        elif __class__.RE_QWEN3_5.search(model) is not None:
            extra_body["enable_thinking"] = thinking_level != ThinkingLevel.OFF

        # 豆包 seed 系列通过 reasoning_effort 控制推理强度。
        elif any(v.search(model) is not None for v in __class__.RE_DOUBAO):
            if thinking_level == ThinkingLevel.OFF:
                extra_body["reasoning_effort"] = "minimal"
            else:
                extra_body["reasoning_effort"] = thinking_level.lower()

        # GLM / Kimi / DeepSeek 等模型通过 thinking.type 切换思考模式。
        elif any(v.search(model) is not None for v in __class__.RE_THINKING):
            if thinking_level == ThinkingLevel.OFF:
                extra_body["thinking"] = {"type": "disabled"}
            else:
                extra_body["thinking"] = {"type": "enabled"}

        # 本地 qwen3 / Sakura 兼容源沿用 /no_think 兜底语义，避免破坏旧接口行为。
        elif __class__.RE_QWEN3.search(model) is not None:
            if thinking_level == ThinkingLevel.OFF and len(messages) > 0:
                if "/no_think" not in messages[-1].get("content", ""):
                    messages[-1]["content"] = messages[-1].get('content') + "\n" + "/no_think"

        if extra_body != {}:
            args["extra_body"] = extra_body

        return args

    # 发起请求
    def request_openai(self, messages: list[dict[str, str]], thinking_level: ThinkingLevel, args: dict[str, float]) -> tuple[bool, str, str, int, int]:
        try:
            # 获取客户端
            with __class__.LOCK:
                client = __class__.get_client(
                    url = self.platform.get('api_url'),
                    key = __class__.get_key(self.platform.get('api_key')),
                    format = self.platform.get('api_format'),
                    timeout = self.config.request_timeout,
                )

            # 发起请求
            response = client.chat.completions.create(
                **self.generate_openai_args(messages, thinking_level, args)
            )

            # 提取回复内容
            message = response.choices[0].message
            if hasattr(message, "reasoning_content") and isinstance(message.reasoning_content, str):
                response_think = __class__.RE_LINE_BREAK.sub("\n", message.reasoning_content.strip())
                response_result = message.content.strip()
            elif "</think>" in message.content:
                splited = message.content.split("</think>")
                response_think = __class__.RE_LINE_BREAK.sub("\n", splited[0].removeprefix("<think>").strip())
                response_result = splited[-1].strip()
            else:
                response_think = ""
                response_result = message.content.strip()
        except Exception as e:
            self.error(f"{Localizer.get().log_task_fail}", e)
            return True, None, None, None, None

        # 获取输入消耗
        try:
            input_tokens = int(response.usage.prompt_tokens)
        except Exception:
            input_tokens = 0

        # 获取输出消耗
        try:
            output_tokens = int(response.usage.completion_tokens)
        except Exception:
            output_tokens = 0

        return False, response_think, response_result, input_tokens, output_tokens

    # 生成请求参数
    def generate_google_args(self, messages: list[dict[str, str]], thinking_level: ThinkingLevel, args: dict[str, float]) -> dict[str, str | int | float]:
        # Gemini 2.5 Flash 在长文本批次下容易命中 4096 输出上限导致截断。
        # 这里提高默认上限，降低 JSONLINE 行数不匹配（如 2/9）的重试概率。
        model = str(self.platform.get("model") or "")
        max_output_tokens = max(__class__.DEFAULT_MAX_OUTPUT_TOKENS, self.config.token_threshold)
        if __class__.RE_GEMINI_2_5_FLASH.search(model) is not None:
            max_output_tokens = max(__class__.GOOGLE_GEMINI_25_FLASH_MAX_OUTPUT_TOKENS, self.config.token_threshold)

        args: dict = args | {
            "max_output_tokens": max_output_tokens,
            "safety_settings": (
                types.SafetySetting(
                    category = "HARM_CATEGORY_HARASSMENT",
                    threshold = "BLOCK_NONE",
                ),
                types.SafetySetting(
                    category = "HARM_CATEGORY_HATE_SPEECH",
                    threshold = "BLOCK_NONE",
                ),
                types.SafetySetting(
                    category = "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    threshold = "BLOCK_NONE",
                ),
                types.SafetySetting(
                    category = "HARM_CATEGORY_DANGEROUS_CONTENT",
                    threshold = "BLOCK_NONE",
                ),
            ),
        }

        # 兼容不同 google-genai 版本：新版本支持 thinking_level，旧版本仅支持 thinking_budget。
        # 为避免旧环境报错，这里按档位提供等价 fallback budget。
        def set_google_thinking_config_by_level(level_name: str, fallback_budget: int, include_thoughts: bool = True) -> None:
            thinking_level_enum = getattr(types, "ThinkingLevel", None)
            if thinking_level_enum is not None and hasattr(thinking_level_enum, level_name):
                args["thinking_config"] = types.ThinkingConfig(
                    thinking_level = getattr(thinking_level_enum, level_name),
                    include_thoughts = include_thoughts,
                )
            else:
                args["thinking_config"] = types.ThinkingConfig(
                    thinking_budget = fallback_budget,
                    include_thoughts = include_thoughts,
                )

        # Gemini
        if __class__.RE_GEMINI_3_1_PRO.search(model) is not None:
            if thinking_level == ThinkingLevel.OFF:
                set_google_thinking_config_by_level("MINIMAL", 0, False)
            elif thinking_level == ThinkingLevel.LOW:
                set_google_thinking_config_by_level("LOW", 384, True)
            elif thinking_level == ThinkingLevel.MEDIUM:
                set_google_thinking_config_by_level("MEDIUM", 768, True)
            elif thinking_level == ThinkingLevel.HIGH:
                set_google_thinking_config_by_level("HIGH", 1024, True)

        elif __class__.RE_GEMINI_3_PRO.search(model) is not None:
            if thinking_level == ThinkingLevel.OFF:
                set_google_thinking_config_by_level("MINIMAL", 0, False)
            elif thinking_level in (ThinkingLevel.LOW, ThinkingLevel.MEDIUM):
                set_google_thinking_config_by_level("LOW", 384, True)
            elif thinking_level == ThinkingLevel.HIGH:
                set_google_thinking_config_by_level("HIGH", 1024, True)

        elif __class__.RE_GEMINI_3_FLASH.search(model) is not None:
            if thinking_level == ThinkingLevel.OFF:
                set_google_thinking_config_by_level("MINIMAL", 0, False)
            elif thinking_level == ThinkingLevel.LOW:
                set_google_thinking_config_by_level("LOW", 384, True)
            elif thinking_level == ThinkingLevel.MEDIUM:
                set_google_thinking_config_by_level("MEDIUM", 768, True)
            elif thinking_level == ThinkingLevel.HIGH:
                set_google_thinking_config_by_level("HIGH", 1024, True)

        elif __class__.RE_GEMINI_2_5_PRO.search(model) is not None:
            if thinking_level == ThinkingLevel.OFF:
                args["thinking_config"] = types.ThinkingConfig(
                    thinking_budget = 0,
                    include_thoughts = False,
                )
            elif thinking_level == ThinkingLevel.LOW:
                args["thinking_config"] = types.ThinkingConfig(
                    thinking_budget = 384,
                    include_thoughts = True,
                )
            elif thinking_level == ThinkingLevel.MEDIUM:
                args["thinking_config"] = types.ThinkingConfig(
                    thinking_budget = 768,
                    include_thoughts = True,
                )
            elif thinking_level == ThinkingLevel.HIGH:
                args["thinking_config"] = types.ThinkingConfig(
                    thinking_budget = 1024,
                    include_thoughts = True,
                )

        elif __class__.RE_GEMINI_2_5_FLASH.search(model) is not None:
            if thinking_level == ThinkingLevel.OFF:
                args["thinking_config"] = types.ThinkingConfig(
                    thinking_budget = 0,
                    include_thoughts = False,
                )
            elif thinking_level == ThinkingLevel.LOW:
                args["thinking_config"] = types.ThinkingConfig(
                    thinking_budget = 384,
                    include_thoughts = True,
                )
            elif thinking_level == ThinkingLevel.MEDIUM:
                args["thinking_config"] = types.ThinkingConfig(
                    thinking_budget = 768,
                    include_thoughts = True,
                )
            elif thinking_level == ThinkingLevel.HIGH:
                args["thinking_config"] = types.ThinkingConfig(
                    thinking_budget = 1024,
                    include_thoughts = True,
                )

        # 将 system 消息传为 Google 的 system_instruction
        system_parts = [v.get('content') for v in messages if v.get('role') == "system"]
        if system_parts:
            args["system_instruction"] = "\n".join(system_parts)

        return {
            "model": self.platform.get('model'),
            "contents": [v.get('content') for v in messages if v.get('role') == "user"],
            "config": types.GenerateContentConfig(**args),
        }

    # 发起请求


    def request_google(self, messages: list[dict[str, str]], thinking_level: ThinkingLevel, args: dict[str, float]) -> tuple[bool, str, str, int, int]:
        try:
            # 获取客户端
            with __class__.LOCK:
                client = __class__.get_client(
                    url = self.platform.get('api_url'),
                    key = __class__.get_key(self.platform.get('api_key')),
                    format = self.platform.get('api_format'),
                    timeout = self.config.request_timeout,
                )

            # 发起请求
            response = client.models.generate_content(
                **self.generate_google_args(messages, thinking_level, args)
            )

            # 获取回复内容
            response_think = ""
            response_result = ""
            candidate = response.candidates[-1] if getattr(response, 'candidates', None) else None
            parts = []
            if candidate is not None:
                content = getattr(candidate, 'content', None)
                parts = getattr(content, 'parts', None) or []

            if parts:
                think_messages = [v for v in parts if getattr(v, 'thought', False)]
                if think_messages:
                    response_think = __class__.RE_LINE_BREAK.sub("\n", think_messages[-1].text.strip())
                result_messages = [v for v in parts if not getattr(v, 'thought', False)]
                if result_messages:
                    response_result = result_messages[-1].text.strip()

            if not response_result:
                response_result = (getattr(response, 'text', None) or "").strip()

            if not response_result:
                finish_reason = getattr(candidate, 'finish_reason', None) if candidate else None
                prompt_feedback = getattr(response, 'prompt_feedback', None)
                
                # 检查是否是内容审查导致的阻止
                is_prohibited = False
                if finish_reason and 'PROHIBITED' in str(finish_reason):
                    is_prohibited = True
                if prompt_feedback and 'PROHIBITED' in str(prompt_feedback):
                    is_prohibited = True
                
                if is_prohibited:
                    # 内容被审查:返回特殊标记,表示内容被阻止
                    # TranslatorTask 会检测到这个标记并跳过这批内容
                    self.warning(f"Content blocked by safety filter (PROHIBITED_CONTENT), marking batch as blocked")
                    # 使用特殊的响应格式来标记内容被阻止
                    response_result = '{"translations":[],"glossary":[],"blocked":true}'
                    return False, "", response_result, 0, 0
                else:
                    # 其他错误:记录日志并重试
                    self.warning(
                        f"Gemini response empty content, finish_reason={finish_reason}, prompt_feedback={prompt_feedback}"
                    )
                    return True, None, None, None, None
        except Exception as e:
            self.error(f"{Localizer.get().log_task_fail}", e)
            return True, None, None, None, None

        # 获取消耗的输入 Token
        try:
            input_tokens = int(response.usage_metadata.prompt_token_count)
        except Exception:
            input_tokens = 0

        # 获取消耗的输出 Token
        try:
            total_token_count = int(response.usage_metadata.total_token_count)
            prompt_token_count = int(response.usage_metadata.prompt_token_count)
            output_tokens = total_token_count - prompt_token_count
        except Exception:
            output_tokens = 0

        return False, response_think, response_result, input_tokens, output_tokens

    def generate_anthropic_args(self, messages: list[dict[str, str]], thinking_level: ThinkingLevel, args: dict[str, float]) -> dict:
        # 提取 system 消息作为 Anthropic 的 system 参数
        system_parts = [v.get('content') for v in messages if v.get('role') == "system"]
        non_system_messages = [v for v in messages if v.get('role') != "system"]

        args: dict = args | {
            "model": self.platform.get('model'),
            "messages": non_system_messages,
            "max_tokens": max(__class__.DEFAULT_MAX_OUTPUT_TOKENS, self.config.token_threshold),
            "extra_headers": {
                "User-Agent": f"Renpybox/{VersionManager.get().get_version()} (https://github.com/dclef/RenpyBox"
            }
        }

        if system_parts:
            system_text = "\n".join(system_parts)
            # Anthropic Prompt Caching：将 system 消息标记为可缓存，
            # 大批量翻译时相同的 system 指令只在首次请求中计费输入 token。
            args["system"] = [
                {
                    "type": "text",
                    "text": system_text,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        # 移除 Anthropic 模型不支持的参数
        args.pop("presence_penalty", None)
        args.pop("frequency_penalty", None)

        # 思考模式切换
        if any(v.search(self.platform.get('model')) is not None for v in __class__.RE_CLAUDE):
            if thinking_level == ThinkingLevel.OFF:
                args["thinking"] = {"type": "disabled"}
            elif thinking_level == ThinkingLevel.LOW:
                args["thinking"] = {"type": "enabled", "budget_tokens": 384}
                args.pop("top_p", None)
                args.pop("temperature", None)
            elif thinking_level == ThinkingLevel.MEDIUM:
                args["thinking"] = {"type": "enabled", "budget_tokens": 768}
                args.pop("top_p", None)
                args.pop("temperature", None)
            elif thinking_level == ThinkingLevel.HIGH:
                args["thinking"] = {"type": "enabled", "budget_tokens": 1024}
                args.pop("top_p", None)
                args.pop("temperature", None)

        return args

    # 发起请求
    def request_anthropic(self, messages: list[dict[str, str]], thinking_level: ThinkingLevel, args: dict[str, float]) -> tuple[bool, str, str, int, int]:
        try:
            # 获取客户端
            with __class__.LOCK:
                client = __class__.get_client(
                    url = self.platform.get('api_url'),
                    key = __class__.get_key(self.platform.get('api_key')),
                    format = self.platform.get('api_format'),
                    timeout = self.config.request_timeout,
                )

            # 发起请求
            response = client.messages.create(
                **self.generate_anthropic_args(messages, thinking_level, args)
            )

            # 提取回复内容
            text_messages = [msg for msg in response.content if hasattr(msg, "text") and isinstance(msg.text, str)]
            think_messages = [msg for msg in response.content if hasattr(msg, "thinking") and isinstance(msg.thinking, str)]

            if text_messages != []:
                response_result = text_messages[-1].text.strip()
            else:
                response_result = ""

            if think_messages != []:
                response_think = __class__.RE_LINE_BREAK.sub("\n", think_messages[-1].thinking.strip())
            else:
                response_think = ""
        except Exception as e:
            self.error(f"{Localizer.get().log_task_fail}", e)
            return True, None, None, None, None

        # 获取输入消耗
        try:
            input_tokens = int(response.usage.input_tokens)
        except Exception:
            input_tokens = 0

        # 获取输出消耗
        try:
            output_tokens = int(response.usage.output_tokens)
        except Exception:
            output_tokens = 0

        return False, response_think, response_result, input_tokens, output_tokens

    def _parse_jsonline_entries(self, text: str) -> list[tuple[int, str]]:
        entries: list[tuple[int, str]] = []
        if not isinstance(text, str) or text.strip() == "":
            return entries

        for raw in text.splitlines():
            line = raw.strip()
            if line == "":
                continue

            try:
                data = json.loads(line)
            except Exception:
                continue

            if not isinstance(data, dict) or len(data) != 1:
                continue

            key, value = next(iter(data.items()))
            if not str(key).isdigit() or not isinstance(value, str):
                continue

            entries.append((int(key), value))

        if entries != []:
            entries.sort(key = lambda item: item[0])
            return entries

        try:
            data = json.loads(text)
        except Exception:
            return []

        if not isinstance(data, dict):
            return []

        for key, value in data.items():
            if str(key).isdigit() and isinstance(value, str):
                entries.append((int(key), value))

        entries.sort(key = lambda item: item[0])
        return entries

    def _extract_translation_inputs(self, messages: list[dict[str, str]]) -> list[str]:
        for msg in messages:
            content = msg.get("content", "")
            if not isinstance(content, str) or content.strip() == "":
                continue

            blocks = __class__.RE_JSONLINE_FENCE.findall(content)
            for block in blocks:
                entries = self._parse_jsonline_entries(block)
                if entries != []:
                    return [value for _, value in entries]

            entries = self._parse_jsonline_entries(content)
            if entries != []:
                return [value for _, value in entries]

            inline_entries: list[tuple[int, str]] = []
            for matched in __class__.RE_INLINE_JSON_OBJECT.findall(content):
                try:
                    data = json.loads(matched)
                except Exception:
                    continue

                if not isinstance(data, dict) or len(data) != 1:
                    continue

                key, value = next(iter(data.items()))
                if not str(key).isdigit() or not isinstance(value, str):
                    continue

                inline_entries.append((int(key), value))

            if inline_entries != []:
                inline_entries.sort(key = lambda item: item[0])
                return [value for _, value in inline_entries]

        return []

    def _build_translation_jsonline_response(self, translations: list[str]) -> str:
        return json.dumps(
            {str(i): v for i, v in enumerate(translations)},
            ensure_ascii = False,
        )

    def _get_deepl_language_codes(self) -> tuple[str, str]:
        source_lang = str(self.config.source_language or "").strip().upper()
        target_lang = str(self.config.target_language or "").strip().upper()

        if source_lang == "":
            source_lang = "AUTO"
        if target_lang == "":
            target_lang = str(BaseLanguage.Enum.ZH)

        return source_lang, target_lang

    def _resolve_deepl_endpoint(self, api_url: str) -> str:
        base = str(api_url or "").strip().rstrip("/")
        if base == "":
            base = "https://api.deepl.com"
        if base.endswith("/v2/translate"):
            return base
        if base.endswith("/v2"):
            return base + "/translate"
        return base + "/v2/translate"

    def _resolve_deeplx_endpoint(self, api_url: str) -> str:
        base = str(api_url or "").strip().rstrip("/")
        if base == "":
            base = "https://dplx.xi-xu.me"
        if base.endswith("/translate"):
            return base
        return base + "/translate"

    def request_deepl(self, messages: list[dict[str, str]]) -> tuple[bool, str, str, int, int]:
        srcs = self._extract_translation_inputs(messages)
        if srcs == []:
            self.warning("DeepL 请求失败：未从提示词中提取到待翻译文本")
            return True, None, None, None, None

        try:
            with __class__.LOCK:
                key = __class__.get_key(self.platform.get('api_key'))
                client = __class__.get_client(
                    url = self.platform.get('api_url'),
                    key = key,
                    format = self.platform.get('api_format'),
                    timeout = self.config.request_timeout,
                )

            source_lang, target_lang = self._get_deepl_language_codes()
            payload: dict[str, Any] = {
                "text": srcs,
                "target_lang": target_lang,
            }
            if source_lang != "AUTO":
                payload["source_lang"] = source_lang

            headers = {
                "Authorization": f"DeepL-Auth-Key {key}",
                "Content-Type": "application/json",
            }

            response = client.post(
                self._resolve_deepl_endpoint(self.platform.get('api_url')),
                json = payload,
                headers = headers,
            )
            response.raise_for_status()

            data = response.json()
            translations = data.get("translations", []) if isinstance(data, dict) else []
            dsts = [str(item.get("text", "")) for item in translations if isinstance(item, dict)]
            if len(dsts) != len(srcs):
                self.warning(f"DeepL 返回数量不匹配: {len(dsts)}/{len(srcs)}")
                return True, None, None, None, None
        except Exception as e:
            self.error(f"{Localizer.get().log_task_fail}", e)
            return True, None, None, None, None

        input_tokens = sum(len(v) for v in srcs)
        output_tokens = sum(len(v) for v in dsts)
        return False, "", self._build_translation_jsonline_response(dsts), input_tokens, output_tokens

    def request_deeplx(self, messages: list[dict[str, str]]) -> tuple[bool, str, str, int, int]:
        srcs = self._extract_translation_inputs(messages)
        if srcs == []:
            self.warning("DeepLX 请求失败：未从提示词中提取到待翻译文本")
            return True, None, None, None, None

        try:
            with __class__.LOCK:
                key = __class__.get_key(self.platform.get('api_key'))
                client = __class__.get_client(
                    url = self.platform.get('api_url'),
                    key = key,
                    format = self.platform.get('api_format'),
                    timeout = self.config.request_timeout,
                )

            source_lang, target_lang = self._get_deepl_language_codes()
            endpoint = self._resolve_deeplx_endpoint(self.platform.get('api_url'))

            headers = {"Content-Type": "application/json"}
            if key and key != "no_key_required":
                headers["Authorization"] = f"Bearer {key}"

            dsts: list[str] = []
            for text in srcs:
                payload: dict[str, str] = {
                    "text": text,
                    "source_lang": source_lang if source_lang != "" else "AUTO",
                    "target_lang": target_lang,
                }
                response = client.post(endpoint, json = payload, headers = headers)
                response.raise_for_status()

                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("DeepLX 返回格式错误")

                if int(data.get("code", 500)) != 200:
                    raise ValueError(str(data.get("message", "DeepLX translation failed")))

                dsts.append(str(data.get("data", "")))

            if len(dsts) != len(srcs):
                self.warning(f"DeepLX 返回数量不匹配: {len(dsts)}/{len(srcs)}")
                return True, None, None, None, None
        except Exception as e:
            self.error(f"{Localizer.get().log_task_fail}", e)
            return True, None, None, None, None

        input_tokens = sum(len(v) for v in srcs)
        output_tokens = sum(len(v) for v in dsts)
        return False, "", self._build_translation_jsonline_response(dsts), input_tokens, output_tokens
