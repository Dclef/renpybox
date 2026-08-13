import json
import re
import threading
import time
from typing import Any, Iterable, Literal

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
from module.Engine.DegradationDetector import DegradationDetector
from module.Engine.Engine import Engine
from module.Localizer.Localizer import Localizer


class ThinkingLevel(StrEnum):
    """思考挡位枚举"""

    OFF = "OFF"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    MAX = "MAX"


ResponseShape = Literal["none", "json_object"]


class TaskRequester(Base):

    # 密钥索引
    API_KEY_INDEX: int = 0
    MAX_REQUEST_RETRY: int = 3
    DEFAULT_MAX_OUTPUT_TOKENS: int = 4 * 1024
    GOOGLE_GEMINI_25_FLASH_MAX_OUTPUT_TOKENS: int = 16 * 1024
    TRANSLATION_RESULT_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "translations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "request_index": {
                            "type": "integer",
                            "minimum": 0,
                        },
                        "text": {"type": "string"},
                    },
                    "required": ["request_index", "text"],
                    "additionalProperties": False,
                },
            },
            "new_glossary": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "src": {"type": "string"},
                        "dst": {"type": "string"},
                        "info": {"type": "string"},
                    },
                    "required": ["src", "dst"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["translations"],
        "additionalProperties": False,
    }

    # 连接缓存（用于停止任务时快速中断网络请求）
    CLIENT_REGISTRY: dict[tuple[str, str, Base.APIFormat, int], Any] = {}
    CLIENT_GENERATIONS: dict[tuple[str, str, Base.APIFormat, int], int] = {}
    CLIENT_GENERATION: int = 0
    CLIENT_GENERATION_LOCK: threading.Lock = threading.Lock()

    # 当前翻译运行的取消标记。停止任务时先设置标记，再异步关闭客户端，
    # 这样重试等待和流式请求可以立即返回，不必等待网络超时。
    CANCEL_EVENT: threading.Event = threading.Event()

    # 取消标记按线程对象隔离。全局 CANCEL_EVENT 需要在新一轮任务开始时
    # 清除；保留旧线程对象集合可以避免旧请求在新一轮开始后继续发起网络
    # 请求或写回缓存，同时不会误伤新建的线程。
    CANCELLED_THREADS: set[threading.Thread] = set()
    CANCELLED_THREADS_LOCK: threading.Lock = threading.Lock()

    # 每轮翻译都有独立取消事件。线程池工作线程通过线程局部上下文绑定
    # 对应事件，避免新一轮 reset 清除全局事件后让旧请求重新继续。
    RUN_CANCEL_CONTEXT = threading.local()

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
    RE_JSONLINE_FENCE: re.Pattern = re.compile(r"```(?:json|jsonline)\s*(.*?)\s*```", flags = re.IGNORECASE | re.DOTALL)
    RE_INLINE_JSON_OBJECT: re.Pattern = re.compile(r"\{[^{}]+\}")

    # 客户端注册表锁。请求入口历史上会在调用 get_client() 前先持锁，
    # get_client() 自身也需要检查/更新注册表，因此必须使用可重入锁，
    # 否则真实网络请求会在首次建连时自锁死。
    LOCK: threading.RLock = threading.RLock()

    @classmethod
    def _is_client_closed(cls, client: Any) -> bool:
        """尽量兼容不同 SDK，判断底层客户端是否已关闭。"""
        if client is None:
            return True

        try:
            direct_flag = getattr(client, "is_closed", None)
            if isinstance(direct_flag, bool):
                return direct_flag
        except Exception:
            pass

        inner = getattr(client, "_client", None)
        if inner is not None:
            try:
                inner_flag = getattr(inner, "is_closed", None)
                if isinstance(inner_flag, bool):
                    return inner_flag
            except Exception:
                pass

        return False

    @classmethod
    def _discard_client(cls, url: str, key: str, format: Base.APIFormat, timeout: int, client: Any = None) -> None:
        """从缓存中移除指定客户端，并尽量安全关闭。"""
        cache_key = (url, key, format, timeout)

        with cls.LOCK:
            cached = cls.CLIENT_REGISTRY.get(cache_key)
            # 旧请求可能在新一轮已经注册同键客户端后才收到“连接已关闭”
            # 异常。此时只能关闭旧请求实际使用的对象，不能摘掉新客户端。
            if client is None or cached is client:
                cached = cls.CLIENT_REGISTRY.pop(cache_key, None)
                cls.CLIENT_GENERATIONS.pop(cache_key, None)
            else:
                cached = None

        target = client if client is not None else cached
        if target is None:
            return

        try:
            close = getattr(target, "close", None)
            if callable(close):
                close()
        except Exception:
            pass

    @classmethod
    def _take_all_clients(cls) -> list[Any]:
        """在锁内摘除客户端；实际关闭必须在锁外执行。"""
        with cls.LOCK:
            clients: list[Any] = []
            seen: set[int] = set()
            for client in cls.CLIENT_REGISTRY.values():
                identity = id(client)
                if identity in seen:
                    continue
                seen.add(identity)
                clients.append(client)
            cls.CLIENT_REGISTRY.clear()
            cls.CLIENT_GENERATIONS.clear()
            return clients

    @classmethod
    def _advance_client_generation(cls) -> int:
        """切换客户端代次，返回停止前的代次。"""
        with cls.CLIENT_GENERATION_LOCK:
            cutoff = cls.CLIENT_GENERATION
            cls.CLIENT_GENERATION = cls.CLIENT_GENERATION + 1
            return cutoff

    @classmethod
    def _current_client_generation(cls) -> int:
        with cls.CLIENT_GENERATION_LOCK:
            return cls.CLIENT_GENERATION

    @classmethod
    def _take_clients_before_generation(cls, cutoff: int) -> list[Any]:
        """只摘取停止前的客户端，避免迟到清理关闭新一轮连接。"""
        with cls.LOCK:
            clients: list[Any] = []
            seen: set[int] = set()
            for cache_key, client in list(cls.CLIENT_REGISTRY.items()):
                generation = cls.CLIENT_GENERATIONS.get(cache_key, 0)
                if generation > cutoff:
                    continue
                identity = id(client)
                if identity not in seen:
                    seen.add(identity)
                    clients.append(client)
                cls.CLIENT_REGISTRY.pop(cache_key, None)
                cls.CLIENT_GENERATIONS.pop(cache_key, None)
            return clients

    @classmethod
    def _close_clients(cls, clients: list[Any]) -> None:
        """关闭一组客户端；此方法不持有客户端注册表锁。"""
        for client in clients:
            try:
                close = getattr(client, "close", None)
                if callable(close):
                    close()
            except Exception:
                # 关闭阶段的异常不能阻止其他连接继续释放。
                pass

    @classmethod
    def _close_stream(cls, stream: Any) -> None:
        """安全关闭流对象；不同 SDK 可能没有 close 方法。"""
        try:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
        except Exception:
            # 取消阶段以尽快退出为先，流关闭异常不能掩盖取消结果。
            pass

    def __init__(self, config: Config, platform: dict[str, Any], current_round: int) -> None:
        super().__init__()

        # 初始化
        self.config = config
        self.platform = platform
        self.current_round = current_round
        self.thinking_level = self.resolve_thinking_level(self.platform.get("thinking"))
        self.last_error_message = ""
        self._agent_requester = None

    def request_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[Any],
        *,
        on_text_delta=None,
        on_reasoning_delta=None,
    ):
        """调用与翻译请求隔离的 Agent 工具通道。"""
        from module.Agent.AgentRequester import AgentRequester

        if self._agent_requester is None:
            self._agent_requester = AgentRequester(
                self.config,
                self.platform,
                thinking_level=self.thinking_level,
            )
        if on_text_delta is None and on_reasoning_delta is None:
            return self._agent_requester.request_tools(messages, tools)
        return self._agent_requester.request_tools(
            messages,
            tools,
            on_text_delta=on_text_delta,
            on_reasoning_delta=on_reasoning_delta,
        )

    def cancel_tools(self) -> None:
        """只取消当前 Agent 请求，不设置翻译全局取消标记。"""
        if self._agent_requester is not None:
            self._agent_requester.cancel()

    def close_tools(self) -> None:
        """释放当前 Agent 请求的客户端，不改变取消状态。"""
        if self._agent_requester is not None:
            self._agent_requester.close()
            self._agent_requester = None

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
        # 停止超时后迟到的旧翻译线程不能重置全局客户端；否则它可能在新轮
        # 已开始后关闭新轮连接。该线程会在后续取消检查处自行退出。
        if cls._is_current_thread_cancelled() or cls._is_bound_run_cancelled():
            return
        cls._advance_client_generation()
        cls.API_KEY_INDEX: int = 0
        # 先取消旧请求，再同步释放旧连接；新一轮开始前清除标记。
        cls.CANCEL_EVENT.set()
        cls.close_all_clients()
        cls.CANCEL_EVENT.clear()
        cls._prune_cancelled_threads()

    @classmethod
    def _prune_cancelled_threads(cls) -> None:
        """清理已经退出的旧线程，避免取消集合无限增长。"""
        with cls.CANCELLED_THREADS_LOCK:
            cls.CANCELLED_THREADS = {
                thread
                for thread in cls.CANCELLED_THREADS
                if thread.is_alive()
            }

    @classmethod
    def _mark_cancelled_threads(
        cls,
        threads: Iterable[threading.Thread] | None = None,
    ) -> None:
        """登记本轮已有工作线程，使其与后续任务的取消状态隔离。"""
        if threads is None:
            threads = (
                thread
                for thread in threading.enumerate()
                if thread.name.startswith(Engine.TASK_PREFIX)
            )
        with cls.CANCELLED_THREADS_LOCK:
            cls.CANCELLED_THREADS.update(thread for thread in threads if thread is not None)

    @classmethod
    def _is_current_thread_cancelled(cls) -> bool:
        current = threading.current_thread()
        with cls.CANCELLED_THREADS_LOCK:
            cancelled = current in cls.CANCELLED_THREADS
            if not cancelled:
                # 顺便回收已经结束的旧线程引用。
                cls.CANCELLED_THREADS = {
                    thread
                    for thread in cls.CANCELLED_THREADS
                    if thread.is_alive()
                }
            return cancelled

    @classmethod
    def bind_run_cancel_event(cls, event: threading.Event | None) -> None:
        """把当前线程绑定到一次翻译运行的独立取消事件。"""
        cls.RUN_CANCEL_CONTEXT.event = event

    @classmethod
    def unbind_run_cancel_event(cls) -> None:
        """清理当前线程的运行取消上下文，供线程池复用该线程。"""
        if hasattr(cls.RUN_CANCEL_CONTEXT, "event"):
            del cls.RUN_CANCEL_CONTEXT.event

    @classmethod
    def _is_bound_run_cancelled(cls) -> bool:
        event = getattr(cls.RUN_CANCEL_CONTEXT, "event", None)
        return bool(event is not None and event.is_set())

    @classmethod
    def is_cancel_requested(cls) -> bool:
        """判断当前请求是否已被用户取消。"""
        if (
            cls._is_bound_run_cancelled()
            or cls._is_current_thread_cancelled()
            or cls.CANCEL_EVENT.is_set()
        ):
            return True
        try:
            return Engine.get().get_status() == Engine.Status.STOPPING
        except Exception:
            return False

    @classmethod
    def cancel_all_clients(
        cls,
        *,
        asynchronous: bool = True,
        threads: Iterable[threading.Thread] | None = None,
    ) -> threading.Thread | None:
        """设置取消标记并释放连接；默认不阻塞调用方线程。"""
        cutoff = cls._advance_client_generation()
        cls._mark_cancelled_threads(threads)
        cls.CANCEL_EVENT.set()
        if asynchronous:
            return cls.close_all_clients_async(cutoff = cutoff)
        cls.close_all_clients()
        return None

    # 关闭所有客户端连接（用于停止任务时快速中断网络请求）
    @classmethod
    def close_all_clients(cls) -> None:
        # 不能在 LOCK 内调用第三方 SDK 的 close()：请求线程的异常清理也
        # 需要同一把锁，某些 SDK 会因此形成锁互等或长时间阻塞。
        cls._close_clients(cls._take_all_clients())

    @classmethod
    def close_all_clients_async(cls, *, cutoff: int | None = None) -> threading.Thread | None:
        """异步关闭所有客户端，供 UI 停止操作使用。"""
        # 摘取注册表本身也需要等待 LOCK，必须和第三方 close 一起放到后台；
        # 否则请求线程正创建客户端时，Qt 停止回调仍可能卡在锁等待上。
        if cutoff is None:
            # 为“直接调用异步清理”建立代次屏障。否则新客户端可能在
            # 清理线程尚未取得 LOCK 时沿用同一代次，随后被误摘取关闭。
            cutoff = cls._advance_client_generation()

        def close_snapshot() -> None:
            cls._close_clients(cls._take_clients_before_generation(cutoff))

        thread = threading.Thread(
            target = close_snapshot,
            # 客户端释放线程不是翻译工作线程，不能被 Engine 的任务计数器
            # 纳入停止等待条件，否则 SDK close() 阻塞时 watcher 会误判仍有任务。
            name = "REN_TRANSLATION_CLIENT_CLOSE",
            daemon = True,
        )
        thread.start()
        return thread

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

        with cls.LOCK:
            cached = cls.CLIENT_REGISTRY.get(cache_key)
        if cached is not None:
            if cls._is_client_closed(cached):
                with cls.LOCK:
                    if cls.CLIENT_REGISTRY.get(cache_key) is cached:
                        cls.CLIENT_REGISTRY.pop(cache_key, None)
                        cls.CLIENT_GENERATIONS.pop(cache_key, None)
            else:
                return cached

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

        duplicate: Any = None
        with cls.LOCK:
            existing = cls.CLIENT_REGISTRY.get(cache_key)
            if existing is not None and not cls._is_client_closed(existing):
                # 第三方 SDK 的 close 可能阻塞，不能在注册表锁内执行。
                duplicate = client
            else:
                cls.CLIENT_REGISTRY[cache_key] = client
                cls.CLIENT_GENERATIONS[cache_key] = cls._current_client_generation()
                return client

        if duplicate is not None:
            try:
                close = getattr(duplicate, "close", None)
                if callable(close):
                    close()
            except Exception:
                pass
        return existing

    # 发起请求
    def request(
        self,
        messages: list[dict],
        *,
        response_shape: ResponseShape = "none",
    ) -> tuple[bool, str, str, int, int]:
        self.last_error_message = ""

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
                return self.request_google(
                    messages,
                    thinking_level,
                    args,
                    response_shape = response_shape,
                )
            elif self.platform.get('api_format') == Base.APIFormat.ANTHROPIC:
                return self.request_anthropic(messages, thinking_level, args)
            elif self.platform.get('api_format') == Base.APIFormat.DEEPL:
                return self.request_deepl(messages)
            elif self.platform.get('api_format') == Base.APIFormat.DEEPLX:
                return self.request_deeplx(messages)
            else:
                return self.request_openai(
                    messages,
                    thinking_level,
                    args,
                    response_shape = response_shape,
                )

        last_result: tuple[bool, str, str, int, int] = (True, None, None, None, None)
        for attempt in range(1, __class__.MAX_REQUEST_RETRY + 1):
            # If user has requested a stop, abort new requests immediately
            if __class__.is_cancel_requested():
                self.debug(f"[API-REQUEST] 用户请求停止，中断请求")
                return True, None, None, None, None

            self.debug(f"[API-REQUEST] 尝试 {attempt}/{__class__.MAX_REQUEST_RETRY}")
            try:
                last_result = dispatch()
            except openai.BadRequestError as e:
                self.last_error_message = str(e)
                self.error(f"{Localizer.get().log_task_fail}", e)
                self.warning("[API-REQUEST] 请求参数错误，不再重试")
                return True, None, None, None, None
            skip = last_result[0]
            if skip is False:
                self.last_error_message = ""
                self.debug(f"[API-REQUEST] 请求成功")
                return last_result

            # 取消造成的连接关闭不应进入退避重试，也不应把用户主动停止
            # 记录成普通请求失败。
            if __class__.is_cancel_requested():
                return True, None, None, None, None

            if attempt < __class__.MAX_REQUEST_RETRY:
                delay = min(2 ** (attempt - 1), 5)
                self.debug(f"[API-REQUEST] 请求失败，{delay}秒后重试")
                deadline = time.monotonic() + delay
                while time.monotonic() < deadline:
                    if __class__.is_cancel_requested():
                        return True, None, None, None, None
                    time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))

        self.warning(f"[API-REQUEST] 请求失败，已达最大重试次数")
        return last_result

    def _recover_closed_cached_client(
        self,
        exc: BaseException,
        *,
        client: Any = None,
        key: str | None = None,
    ) -> bool:
        """命中“client 已关闭”类错误时，清理缓存并允许上层重试。"""
        message = str(exc or "")
        lowered = message.lower()
        markers = (
            "client has been closed",
            "cannot send a request, as the client has been closed",
            "closed client",
        )
        if any(marker in lowered for marker in markers) is False:
            return False

        try:
            url = self.platform.get('api_url')
            format = self.platform.get('api_format')
            timeout = self.config.request_timeout
            self.warning("[API-REQUEST] 检测到已关闭的缓存客户端，正在丢弃并等待重试")
            if key is not None:
                __class__._discard_client(
                    url,
                    key,
                    format,
                    timeout,
                    client = client,
                )
            else:
                api_keys = self.platform.get('api_key') or []
                if isinstance(api_keys, list) and api_keys:
                    for api_key in api_keys:
                        __class__._discard_client(url, api_key, format, timeout)
                else:
                    __class__._discard_client(url, "no_key_required", format, timeout)
        except Exception:
            pass
        return True

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
        client = None
        client_key = None
        try:
            # 获取客户端
            with __class__.LOCK:
                client_key = __class__.get_key(self.platform.get('api_key'))
                client = __class__.get_client(
                    url = self.platform.get('api_url'),
                    key = client_key,
                    format = self.platform.get('api_format'),
                    timeout = self.config.request_timeout,
                )

            sakura_args = self.generate_sakura_args(messages, thinking_level, args)
            sakura_args["stream"] = True
            sakura_args["stream_options"] = {"include_usage": True}

            # 流式请求
            stream = client.chat.completions.create(**sakura_args)

            response_think_parts: list[str] = []
            response_result_parts: list[str] = []
            input_tokens = 0
            output_tokens = 0
            detector = DegradationDetector()
            degraded = False

            for chunk in stream:
                # 用户中断检测
                if __class__.is_cancel_requested():
                    stream.close()
                    return True, None, None, None, None

                if not chunk.choices and hasattr(chunk, 'usage') and chunk.usage is not None:
                    input_tokens = getattr(chunk.usage, 'prompt_tokens', 0) or 0
                    output_tokens = getattr(chunk.usage, 'completion_tokens', 0) or 0
                    continue

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                if delta is None:
                    continue

                reasoning = getattr(delta, 'reasoning_content', None)
                if isinstance(reasoning, str) and reasoning:
                    response_think_parts.append(reasoning)

                content = getattr(delta, 'content', None)
                if isinstance(content, str) and content:
                    response_result_parts.append(content)
                    if detector.feed(content):
                        degraded = True
                        self.warning("[STREAM] 检测到输出退化，提前中断")
                        stream.close()
                        break

            response_think = __class__.RE_LINE_BREAK.sub("\n", "".join(response_think_parts).strip())
            response_result = "".join(response_result_parts).strip()

            if not response_think and "</think>" in response_result:
                splited = response_result.split("</think>")
                response_think = __class__.RE_LINE_BREAK.sub("\n", splited[0].removeprefix("<think>").strip())
                response_result = splited[-1].strip()

            if degraded:
                return False, "", response_result, 0, 0

        except openai.BadRequestError:
            raise
        except Exception as e:
            self.last_error_message = str(e)
            self._recover_closed_cached_client(e, client = client, key = client_key)
            self.error(f"{Localizer.get().log_task_fail}", e)
            return True, None, None, None, None

        return False, "", response_result, input_tokens, output_tokens

    # 生成请求参数
    def generate_openai_args(
        self,
        messages: list[dict[str, str]],
        thinking_level: ThinkingLevel,
        args: dict[str, float],
        *,
        response_shape: ResponseShape = "none",
    ) -> dict:
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
                # DeepSeek V4 支持 reasoning_effort=low/high/max。
                # 这里仅对 DeepSeek 追加该参数，避免把未验证字段传给 GLM / Kimi。
                if "deepseek" in model.lower():
                    if thinking_level == ThinkingLevel.LOW:
                        extra_body["reasoning_effort"] = "low"
                    elif thinking_level == ThinkingLevel.MAX:
                        extra_body["reasoning_effort"] = "max"
                    else:
                        extra_body["reasoning_effort"] = "high"

        # 本地 qwen3 / Sakura 兼容源沿用 /no_think 兜底语义，避免破坏旧接口行为。
        elif __class__.RE_QWEN3.search(model) is not None:
            if thinking_level == ThinkingLevel.OFF and len(messages) > 0:
                if "/no_think" not in messages[-1].get("content", ""):
                    messages[-1]["content"] = messages[-1].get('content') + "\n" + "/no_think"

        if extra_body != {}:
            args["extra_body"] = extra_body

        # 结构化输出由本次请求声明，不能复用全局翻译协议。
        if response_shape == "json_object":
            if any("json" in str(message.get("content", "")) for message in messages):
                args["response_format"] = {"type": "json_object"}
            else:
                self.warning("[API-REQUEST] 提示词未包含小写 json，已跳过 json_object 输出约束")

        return args

    # 发起请求（流式 + 退化检测）
    def request_openai(
        self,
        messages: list[dict[str, str]],
        thinking_level: ThinkingLevel,
        args: dict[str, float],
        *,
        response_shape: ResponseShape = "none",
    ) -> tuple[bool, str, str, int, int]:
        client = None
        client_key = None
        try:
            # 获取客户端
            with __class__.LOCK:
                client_key = __class__.get_key(self.platform.get('api_key'))
                client = __class__.get_client(
                    url = self.platform.get('api_url'),
                    key = client_key,
                    format = self.platform.get('api_format'),
                    timeout = self.config.request_timeout,
                )

            openai_args = self.generate_openai_args(
                messages,
                thinking_level,
                args,
                response_shape = response_shape,
            )
            openai_args["stream"] = True
            openai_args["stream_options"] = {"include_usage": True}

            # 流式请求
            stream = client.chat.completions.create(**openai_args)

            response_think_parts: list[str] = []
            response_result_parts: list[str] = []
            input_tokens = 0
            output_tokens = 0
            detector = DegradationDetector()
            degraded = False

            for chunk in stream:
                # 用户中断检测
                if __class__.is_cancel_requested():
                    stream.close()
                    return True, None, None, None, None

                if not chunk.choices and hasattr(chunk, 'usage') and chunk.usage is not None:
                    # 最终的 usage 块（无 choices）
                    input_tokens = getattr(chunk.usage, 'prompt_tokens', 0) or 0
                    output_tokens = getattr(chunk.usage, 'completion_tokens', 0) or 0
                    continue

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                if delta is None:
                    continue

                # reasoning_content（思考内容）
                reasoning = getattr(delta, 'reasoning_content', None)
                if isinstance(reasoning, str) and reasoning:
                    response_think_parts.append(reasoning)

                # content（正文内容）
                content = getattr(delta, 'content', None)
                if isinstance(content, str) and content:
                    response_result_parts.append(content)
                    # 退化检测
                    if detector.feed(content):
                        degraded = True
                        self.warning("[STREAM] 检测到输出退化，提前中断")
                        stream.close()
                        break

            response_think = __class__.RE_LINE_BREAK.sub("\n", "".join(response_think_parts).strip())
            response_result = "".join(response_result_parts).strip()

            # 处理 <think> 标签（部分模型不通过 reasoning_content 返回）
            if not response_think and "</think>" in response_result:
                splited = response_result.split("</think>")
                response_think = __class__.RE_LINE_BREAK.sub("\n", splited[0].removeprefix("<think>").strip())
                response_result = splited[-1].strip()

            # 退化的响应仍然返回（让 ResponseChecker 做最终判定），但标记 token 为 0
            if degraded:
                return False, response_think, response_result, 0, 0

        except openai.BadRequestError:
            raise
        except Exception as e:
            self.last_error_message = str(e)
            self._recover_closed_cached_client(e, client = client, key = client_key)
            self.error(f"{Localizer.get().log_task_fail}", e)
            return True, None, None, None, None

        return False, response_think, response_result, input_tokens, output_tokens

    # 生成请求参数
    def generate_google_args(
        self,
        messages: list[dict[str, str]],
        thinking_level: ThinkingLevel,
        args: dict[str, float],
        *,
        response_shape: ResponseShape = "none",
    ) -> dict[str, str | int | float]:
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

        # 结构化输出由本次请求声明，避免给 JSONLINE 或纯文本套翻译 schema。
        if response_shape == "json_object":
            args["response_mime_type"] = "application/json"
            args["response_schema"] = __class__.TRANSLATION_RESULT_SCHEMA

        return {
            "model": self.platform.get('model'),
            "contents": [v.get('content') for v in messages if v.get('role') == "user"],
            "config": types.GenerateContentConfig(**args),
        }

    # 发起请求（流式 + 退化检测）
    def request_google(
        self,
        messages: list[dict[str, str]],
        thinking_level: ThinkingLevel,
        args: dict[str, float],
        *,
        response_shape: ResponseShape = "none",
    ) -> tuple[bool, str, str, int, int]:
        client = None
        client_key = None
        try:
            # 获取客户端
            with __class__.LOCK:
                client_key = __class__.get_key(self.platform.get('api_key'))
                client = __class__.get_client(
                    url = self.platform.get('api_url'),
                    key = client_key,
                    format = self.platform.get('api_format'),
                    timeout = self.config.request_timeout,
                )

            google_args = self.generate_google_args(
                messages,
                thinking_level,
                args,
                response_shape = response_shape,
            )

            # 流式请求
            stream = client.models.generate_content_stream(**google_args)

            response_think_parts: list[str] = []
            response_result_parts: list[str] = []
            input_tokens = 0
            output_tokens = 0
            detector = DegradationDetector()
            degraded = False
            finish_reason = None
            prompt_feedback = None

            for chunk in stream:
                # 用户中断检测
                if __class__.is_cancel_requested():
                    __class__._close_stream(stream)
                    return True, None, None, None, None

                # 记录安全过滤信息
                candidate = chunk.candidates[-1] if getattr(chunk, 'candidates', None) else None
                if candidate is not None:
                    fr = getattr(candidate, 'finish_reason', None)
                    if fr is not None:
                        finish_reason = fr

                pf = getattr(chunk, 'prompt_feedback', None)
                if pf is not None:
                    prompt_feedback = pf

                # 提取 usage
                usage = getattr(chunk, 'usage_metadata', None)
                if usage is not None:
                    pt = getattr(usage, 'prompt_token_count', None)
                    tt = getattr(usage, 'total_token_count', None)
                    if pt is not None:
                        input_tokens = int(pt)
                    if tt is not None and pt is not None:
                        output_tokens = int(tt) - int(pt)

                # 提取文本
                parts = []
                if candidate is not None:
                    content = getattr(candidate, 'content', None)
                    parts = getattr(content, 'parts', None) or []

                for part in parts:
                    text = getattr(part, 'text', None)
                    if not isinstance(text, str) or not text:
                        continue
                    if getattr(part, 'thought', False):
                        response_think_parts.append(text)
                    else:
                        response_result_parts.append(text)
                        if detector.feed(text):
                            degraded = True
                            self.warning("[STREAM] 检测到输出退化，提前中断")
                            break

                if degraded:
                    break

            response_think = __class__.RE_LINE_BREAK.sub("\n", "".join(response_think_parts).strip())
            response_result = "".join(response_result_parts).strip()

            if degraded:
                return False, response_think, response_result, 0, 0

            if not response_result:
                # 检查是否是内容审查导致的阻止
                is_prohibited = False
                if finish_reason and 'PROHIBITED' in str(finish_reason):
                    is_prohibited = True
                if prompt_feedback and 'PROHIBITED' in str(prompt_feedback):
                    is_prohibited = True

                if is_prohibited:
                    self.warning(f"Content blocked by safety filter (PROHIBITED_CONTENT), marking batch as blocked")
                    response_result = '{"translations":[],"glossary":[],"blocked":true}'
                    return False, "", response_result, 0, 0
                else:
                    self.warning(
                        f"Gemini response empty content, finish_reason={finish_reason}, prompt_feedback={prompt_feedback}"
                    )
                    return True, None, None, None, None
        except Exception as e:
            self.last_error_message = str(e)
            self._recover_closed_cached_client(e, client = client, key = client_key)
            self.error(f"{Localizer.get().log_task_fail}", e)
            return True, None, None, None, None

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

    # 发起请求（流式 + 退化检测）
    def request_anthropic(self, messages: list[dict[str, str]], thinking_level: ThinkingLevel, args: dict[str, float]) -> tuple[bool, str, str, int, int]:
        client = None
        client_key = None
        try:
            # 获取客户端
            with __class__.LOCK:
                client_key = __class__.get_key(self.platform.get('api_key'))
                client = __class__.get_client(
                    url = self.platform.get('api_url'),
                    key = client_key,
                    format = self.platform.get('api_format'),
                    timeout = self.config.request_timeout,
                )

            anthropic_args = self.generate_anthropic_args(messages, thinking_level, args)

            # 流式请求：text_stream 实时退化检测，最终消息提取思考内容和 usage
            detector = DegradationDetector()
            degraded = False
            response_result_parts: list[str] = []

            with client.messages.stream(**anthropic_args) as stream:
                for text in stream.text_stream:
                    # 用户中断检测
                    if __class__.is_cancel_requested():
                        return True, None, None, None, None

                    if not isinstance(text, str) or not text:
                        continue

                    response_result_parts.append(text)
                    if detector.feed(text):
                        degraded = True
                        self.warning("[STREAM] 检测到输出退化，提前中断")
                        break

                # 获取最终消息（包含 thinking 和 usage）
                if not degraded:
                    final_message = stream.get_final_message()
                else:
                    final_message = None

            response_result = "".join(response_result_parts).strip()

            if degraded:
                return False, "", response_result, 0, 0

            # 从最终消息提取思考内容
            response_think = ""
            if final_message is not None:
                think_messages = [
                    msg for msg in final_message.content
                    if hasattr(msg, "thinking") and isinstance(msg.thinking, str)
                ]
                if think_messages:
                    response_think = __class__.RE_LINE_BREAK.sub("\n", think_messages[-1].thinking.strip())

            # 获取 token 使用量
            input_tokens = 0
            output_tokens = 0
            if final_message is not None:
                usage = getattr(final_message, 'usage', None)
                if usage is not None:
                    input_tokens = getattr(usage, 'input_tokens', 0) or 0
                    output_tokens = getattr(usage, 'output_tokens', 0) or 0

        except Exception as e:
            self.last_error_message = str(e)
            self._recover_closed_cached_client(e, client = client, key = client_key)
            self.error(f"{Localizer.get().log_task_fail}", e)
            return True, None, None, None, None

        return False, response_think, response_result, input_tokens, output_tokens

    def _parse_jsonline_entries(self, text: str) -> list[tuple[int, str]]:
        entries: list[tuple[int, str]] = []
        if not isinstance(text, str) or text.strip() == "":
            return entries

        def parse_record(data: object) -> tuple[int, str] | None:
            if not isinstance(data, dict) or set(data) != {"request_index", "text"}:
                return None
            request_index = data.get("request_index")
            value = data.get("text")
            if type(request_index) is not int or request_index < 0 or not isinstance(value, str):
                return None
            return request_index, value

        def align(values: list[tuple[int, str]]) -> list[tuple[int, str]]:
            indices = [index for index, _ in values]
            if len(indices) != len(set(indices)) or set(indices) != set(range(len(values))):
                return []
            return sorted(values, key = lambda item: item[0])

        for raw in text.splitlines():
            line = raw.strip()
            if line == "":
                continue

            try:
                data = json.loads(line)
            except Exception:
                continue

            record = parse_record(data)
            if record is not None:
                entries.append(record)
                continue

            if isinstance(data, dict) and len(data) == 1:
                key, value = next(iter(data.items()))
                if str(key).isdigit() and isinstance(value, str):
                    entries.append((int(key), value))

        if entries != []:
            return align(entries)

        try:
            data = json.loads(text)
        except Exception:
            return []

        if not isinstance(data, dict):
            return []

        inputs = data.get("inputs")
        if isinstance(inputs, list):
            structured_entries: list[tuple[int, str]] = []
            for item in inputs:
                record = parse_record(item)
                if record is None:
                    return []
                structured_entries.append(record)
            return align(structured_entries)

        record = parse_record(data)
        if record is not None:
            return [record] if record[0] == 0 else []

        for key, value in data.items():
            if str(key).isdigit() and isinstance(value, str):
                entries.append((int(key), value))

        return align(entries)

    def _extract_translation_inputs(self, messages: list[dict[str, str]]) -> list[str]:
        for msg in messages:
            if msg.get("role") != "user":
                continue
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
                    if isinstance(data, dict) and set(data) == {"request_index", "text"}:
                        request_index = data.get("request_index")
                        value = data.get("text")
                        if type(request_index) is int and request_index >= 0 and isinstance(value, str):
                            inline_entries.append((request_index, value))
                    continue

                key, value = next(iter(data.items()))
                if str(key).isdigit() and isinstance(value, str):
                    inline_entries.append((int(key), value))

            if inline_entries != []:
                indices = [index for index, _ in inline_entries]
                if len(indices) != len(set(indices)) or set(indices) != set(range(len(indices))):
                    continue
                inline_entries.sort(key = lambda item: item[0])
                return [value for _, value in inline_entries]

        return []

    def _build_translation_jsonline_response(self, translations: list[str]) -> str:
        return "\n".join(
            json.dumps(
                {"request_index": i, "text": value},
                ensure_ascii = False,
            )
            for i, value in enumerate(translations)
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
        if __class__.is_cancel_requested():
            return True, None, None, None, None

        client = None
        key = None
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
            self.last_error_message = str(e)
            self._recover_closed_cached_client(e, client = client, key = key)
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
        if __class__.is_cancel_requested():
            return True, None, None, None, None

        client = None
        key = None
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
                if __class__.is_cancel_requested():
                    return True, None, None, None, None
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
            self.last_error_message = str(e)
            self._recover_closed_cached_client(e, client = client, key = key)
            self.error(f"{Localizer.get().log_task_fail}", e)
            return True, None, None, None, None

        input_tokens = sum(len(v) for v in srcs)
        output_tokens = sum(len(v) for v in dsts)
        return False, "", self._build_translation_jsonline_response(dsts), input_tokens, output_tokens
