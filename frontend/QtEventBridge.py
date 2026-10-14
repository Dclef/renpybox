"""Qt 事件循环桥接。

EventManager 已解除 Qt 依赖（见 base/EventManager.py），跨线程投递改为
「emit 入队 + drain 排空」。Qt 壳需要在事件循环里驱动 drain，
否则后台线程 emit 的事件永远不会被投递。

这个桥接只属于旧 Qt 壳层；Electron sidecar 由 api 层用 asyncio 周期调用
EventManager.drain_all()，不经过这里。
"""
from PyQt5.QtCore import QTimer

from base.EventManager import EventManager


def install(interval_ms: int = 0) -> QTimer:
    """把 drain 挂到 Qt 事件循环，返回的 timer 需要调用方持有引用（否则会被回收）。

    interval_ms 默认 0，语义对齐原来的 QueuedConnection：
    每轮事件循环排空一次队列。
    """
    timer = QTimer()
    timer.setInterval(interval_ms)
    timer.timeout.connect(EventManager.drain_all)
    timer.start()

    return timer