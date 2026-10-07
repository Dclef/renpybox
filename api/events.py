"""EventManager → WebSocket 广播桥。

业务逻辑（ProjectStore / 翻译引擎 / 更新器）通过 EventManager 发事件，
Qt 壳时代由页面订阅；这里把同样的事件转成 WS 消息推给 Electron 侧，
两端订阅的是同一份事件流，行为一致。

事件总线的跨线程投递由 drain 驱动（见 api/app.py 的 _drain_loop），
所以本回调运行在事件循环线程上；emit 可能来自后台线程，
推送统一走 call_soon_threadsafe。
"""

from __future__ import annotations

import asyncio
from typing import Callable

from api.hub import ConnectionHub, jsonable
from base.Base import Base
from base.EventManager import EventManager


# 默认转发的事件。TRANSLATION_UPDATE 已由 EventManager 做 200ms 合并，
# 这里不再重复节流，保持「一次合并窗口一条消息」。
#
# 注意：按名字过滤。EventManager.FLUSH_ON_EVENTS 里引用过
# TRANSLATION_STOP_DONE，但 Base.Event 并没有这个成员，写死会直接抛异常。
_EVENT_NAMES = (
    "PROJECT_CHANGED",
    "PROJECT_STATUS",
    "PROJECT_STATUS_CHECK_DONE",
    "GLOSSARY_REFRESH",
    "PLATFORM_TEST_START",
    "PLATFORM_TEST_DONE",
    "APP_TOAST_SHOW",
    "APP_UPDATE_CHECK_START",
    "APP_UPDATE_CHECK_DONE",
    "APP_UPDATE_DOWNLOAD_START",
    "APP_UPDATE_DOWNLOAD_CANCEL",
    "APP_UPDATE_DOWNLOAD_DONE",
    "APP_UPDATE_DOWNLOAD_ERROR",
    "APP_UPDATE_DOWNLOAD_UPDATE",
    "APP_UPDATE_EXTRACT",
    "TRANSLATION_START",
    "TRANSLATION_START_RESULT",
    "TRANSLATION_STOP",
    "TRANSLATION_DONE",
    "TRANSLATION_UPDATE",
    # 导出译文与缓存自动保存的完成信号：渲染端据此提示「导出成功」，
    # 否则用户只能看到 toast 消失、不知道写盘是否成功。
    "TRANSLATION_MANUAL_EXPORT",
    "CACHE_FILE_AUTO_SAVE",
)

DEFAULT_EVENTS: tuple[str, ...] = tuple(
    name for name in _EVENT_NAMES if hasattr(Base.Event, name)
)


class EventBridge:
    def __init__(self, hub: ConnectionHub, events: tuple[str, ...] = DEFAULT_EVENTS) -> None:
        self._hub = hub
        self._events = tuple(events)
        self._subscribed: list[tuple[str, Callable]] = []

    def start(self) -> None:
        manager = EventManager.get()
        for name in self._events:
            event = _resolve_event(name)
            if event is None:
                continue
            handler = self._make_handler(name)
            manager.subscribe(event, handler)
            self._subscribed.append((name, handler))

    def stop(self) -> None:
        manager = EventManager.get()
        for name, handler in self._subscribed:
            event = _resolve_event(name)
            if event is not None:
                manager.unsubscribe(event, handler)
        self._subscribed.clear()

    @property
    def event_count(self) -> int:
        return len(self._subscribed)

    def _make_handler(self, name: str) -> Callable:
        def handler(event, data) -> None:
            payload = {"type": "event", "event": name, "data": _for_clients(data)}
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # 不在事件循环线程（理论上 drain 保证不会发生），退回线程安全路径
                self._hub.broadcast_threadsafe(payload)
                return
            loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self._hub.broadcast(payload)))

        return handler


# TRANSLATION_START 载荷里的 ``config`` 是给翻译线程的冻结 Config 实例。
# jsonable() 遇到它只会吐出一个约 9KB 的 repr 字符串：渲染端读不出字段，
# 还得为这份假结构付出解析成本。渲染端的配置一律走 GET /api/settings，
# 所以广播前直接摘掉这个键，保留其余可序列化字段。
_BROADCAST_DROP_KEYS = frozenset({"config"})


def _for_clients(data: object) -> object:
    """按广播受众裁剪载荷：摘掉只有后端消费者才需要的键。"""
    if not isinstance(data, dict):
        return jsonable(data)
    return jsonable({k: v for k, v in data.items() if k not in _BROADCAST_DROP_KEYS})


def _resolve_event(name: str):
    """按名字取 Base.Event 成员；测试里可能传入不存在的名字，忽略即可。"""
    return getattr(Base.Event, name, None)