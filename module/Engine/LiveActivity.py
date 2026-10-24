"""模型请求的实时进度缓冲。

界面上的「等待模型响应中，已耗时 15 秒」是个心跳，看不出模型在干什么。
流式请求其实每一个 chunk 都带着 reasoning_content / content，只是被丢进局部变量了。
这里开一个进程级的环形缓冲，让流式循环把增量写进来，HTTP 层再提供一个只读快照接口，
前端轮询就能把思考过程实时显示出来。

只读快照不加业务锁：分析请求期间全局缓存锁是放开的，
这里再用同一把锁会和正在跑的请求互相等。
"""
from __future__ import annotations

import threading
import time
from typing import Any, Literal

Kind = Literal["think", "content"]

_LIMIT = 12000
_lock = threading.Lock()
_label = ""
_started_at = 0.0
_updated_at = 0.0
_active = False
_buffers: dict[str, list[str]] = {"think": [], "content": []}


def _trim(parts: list[str]) -> list[str]:
    total = sum(len(part) for part in parts)
    while total > _LIMIT and len(parts) > 1:
        total -= len(parts.pop(0))
    return parts


def begin(label: str) -> None:
    """开始一次请求：清空缓冲，记下标签和起始时间。"""
    global _label, _started_at, _updated_at, _active
    with _lock:
        _label = str(label or "")
        _started_at = _updated_at = time.time()
        _active = True
        _buffers["think"] = []
        _buffers["content"] = []


def append(kind: Kind, text: str) -> None:
    """流式循环每来一个 chunk 调一次；空串直接忽略。"""
    global _updated_at
    if not text:
        return
    with _lock:
        if not _active:
            return
        parts = _buffers.get(kind)
        if parts is None:
            return
        parts.append(text)
        _buffers[kind] = _trim(parts)
        _updated_at = time.time()


def finish() -> None:
    """请求结束：停止写入，但保留文本，让界面还能看到最终结果。"""
    global _active, _updated_at
    with _lock:
        _active = False
        _updated_at = time.time()


def snapshot() -> dict[str, Any]:
    """给前端用的只读快照。"""
    with _lock:
        think = "".join(_buffers["think"])
        content = "".join(_buffers["content"])
        now = time.time()
        return {
            "active": _active,
            "label": _label,
            "think": think,
            "content": content,
            "elapsed": round((now - _started_at) if _started_at else 0.0, 1),
            "idle": round((now - _updated_at) if _updated_at else 0.0, 1),
        }
