"""WebSocket 连接集合。

一个客户端一条连接；广播时对每条连接做一次「可写性」检查，
不可写的连接直接剔除，避免异常传播拖垮整个广播。
"""

from __future__ import annotations

import asyncio
import json
from enum import Enum
from typing import Any

from starlette.websockets import WebSocket


def jsonable(value: Any) -> Any:
    """把业务侧 dict 转成能 JSON 序列化的结构。

    事件数据里混有 StrEnum、自定义对象、Path 等，直接 dumps 会炸。
    这里做一次保守转换：枚举转 value、Path 转字符串、其余对象转 repr。
    """
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Enum):
        return jsonable(value.value)
    if hasattr(value, "as_posix"):  # pathlib.Path
        return value.as_posix()
    return repr(value)


class ConnectionHub:
    def __init__(self) -> None:
        self._clients: dict[WebSocket, set[str] | None] = {}
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket, events: set[str] | None = None) -> None:
        async with self._lock:
            self._clients[ws] = events

    async def remove(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.pop(ws, None)

    @property
    def size(self) -> int:
        return len(self._clients)

    async def send_to(self, ws: WebSocket, payload: dict) -> None:
        try:
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception:
            await self.remove(ws)

    async def broadcast(self, payload: dict) -> None:
        event_name = payload.get("event")
        targets = list(self._clients.items())
        dead: list[WebSocket] = []

        for ws, events in targets:
            # 客户端订阅了子集时，只推它要的事件
            if event_name is not None and events is not None and event_name not in events:
                continue
            try:
                await ws.send_text(json.dumps(payload, ensure_ascii=False))
            except Exception:
                dead.append(ws)

        for ws in dead:
            await self.remove(ws)

    async def broadcast_threadsafe(self, payload: dict) -> None:
        """允许从工作线程调用（事件总线可能在后台线程 emit）。"""
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self.broadcast(payload)))