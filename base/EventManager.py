"""事件总线（M1 已解除 Qt 依赖）。

原实现用 QObject + pyqtSignal(QueuedConnection) + QTimer：
  · signal 负责「后台线程 emit → 主线程投递」的跨线程语义
  · QTimer 负责 200ms 合并窗口的自动冲刷
这两件事都依赖 Qt 事件循环，因此 base/ 无法在 Electron sidecar 里复用。

现在改为纯 Python：
  · emit() 只做线程安全入队（后台线程调用）
  · drain() 由事件循环所在线程调用，完成投递与合并窗口冲刷
  · Qt 壳通过 frontend/QtEventBridge.py 把 drain 挂到事件循环上
  · Electron 侧由 api层的 asyncio 任务周期调用 drain

对外行为（订阅时刻过滤、合并窗口、终态先冲刷）与原实现保持一致。
"""
import threading
import time
import weakref
from collections import deque
from typing import Callable

from base.compat import StrEnum, Self
from base.EventTelemetry import record_latency

# 事件名与 base/Base.py 的 Event 枚举值保持一致（此处不能 import Base，避免循环依赖）
# TRANSLATION_UPDATE 只承载中间态（preparing 消息 / progress 统计 / quality_task 进度），
# 终态由 TRANSLATION_DONE / TRANSLATION_STOP_DONE 独立通知，到达时先冲刷合并窗口保证顺序。
COALESCING_EVENTS = {"TRANSLATION_UPDATE"}
FLUSH_ON_EVENTS = {"TRANSLATION_DONE", "TRANSLATION_STOP_DONE"}
COALESCING_INTERVAL_MS = 200


class EventManager():
    # 事件列表
    event_callbacks: dict[StrEnum, list[Callable]] = {}

    # 发射序号：自增计数，每条事件带上发射时刻的序号
    # 与 event_callbacks 同为类级：投递是排队延迟发生的，可能由另一个实例执行，
    # 序号若各实例自行计数，就无法跨实例判断订阅与发射的先后，过滤会漏掉历史事件
    _emit_sequence: int = 0
    # 序号跨实例共享，实例锁覆盖不到。自增与订阅时刻的读取必须用同一把锁，
    # 否则并发 emit 会读到同一个值，订阅过滤会把历史事件投给新订阅者。
    _sequence_lock = threading.Lock()

    # 订阅时刻的发射序号，键为 (event, handler)：绑定方法每次访问都是新对象，
    # 但相等性与哈希稳定，可用于识别「订阅之前就已发出」的历史事件
    _subscriber_sequences: dict[tuple[StrEnum, Callable], int] = {}

    # 活实例集合：drain_all 需要把测试或异常流程里新建的实例一并排空
    _instances: "weakref.WeakSet[EventManager]" = weakref.WeakSet()

    def __init__(self) -> None:
        super().__init__()

        self._lock = threading.RLock()
        self._queue: deque[tuple[StrEnum, dict, float, int]] = deque()

        # 中间态事件 latest-value 合并：窗口内多次发射只分发最新值
        self._coalescing: dict[StrEnum, tuple[dict, int | None]] = {}
        self._coalesce_since: float | None = None

        EventManager._instances.add(self)

    @classmethod
    def get(cls) -> Self:
        if not hasattr(cls, "__instance__"):
            cls.__instance__ = cls()

        return cls.__instance__

    # ---------- 跨线程投递 ----------

    # 触发事件：仅入队，不在当前线程分发
    def emit(self, event: StrEnum, data: dict) -> None:
        cls = type(self)
        with cls._sequence_lock:
            cls._emit_sequence += 1
            sequence = cls._emit_sequence
        with self._lock:
            self._queue.append((event, data, time.monotonic(), sequence))

    # 排空队列：必须由事件循环所在线程调用（与原 QueuedConnection 的投递语义一致）
    # 返回本次投递的事件数
    def drain(self, max_events: int | None = None) -> int:
        dispatched = 0

        while True:
            with self._lock:
                if len(self._queue) == 0:
                    break
                event, data, emitted_at, sequence = self._queue.popleft()

            # 测 emit→ 实际分发的端到端延迟（含合并窗口停留）
            record_latency(str(event), (time.monotonic() - emitted_at) * 1000)
            self.process_event(event, data, sequence)

            dispatched += 1
            if max_events is not None and dispatched >= max_events:
                return dispatched

        self.flush_coalesced_if_due()
        return dispatched

    @classmethod
    def drain_all(cls, max_rounds: int = 50, batch: int = 256) -> int:
        """排空所有活实例。分批 + 轮次上限，避免回调里再次 emit 时饿死事件循环。"""
        total = 0
        for _ in range(max_rounds):
            dispatched = sum(instance.drain(batch) for instance in list(cls._instances))
            total += dispatched
            if dispatched == 0:
                break
        return total

    # 处理事件
    # sequence 为事件的发射序号；None 表示不经 emit 直接调用（测试与内部冲刷）
    def process_event(self, event: StrEnum, data: dict, sequence: int | None = None) -> None:
        # 终态事件先冲刷合并窗口，订阅者先看到最后的中间状态再看到完成状态
        if event in FLUSH_ON_EVENTS:
            self._flush_coalesced()

        # 可合并事件暂存最新值，由 drain 到期后统一冲刷。
        # 与 flush 共用实例锁：drain 在不同线程同时 process / 检查超时时，
        # 不能让窗口起点被覆盖或让到期判断读到旧值。分发仍在锁外。
        if event in COALESCING_EVENTS:
            with self._lock:
                self._coalescing[event] = (data, sequence)
                if self._coalesce_since is None:
                    self._coalesce_since = time.monotonic()
            return

        self._dispatch(event, data, sequence)

    # 合并窗口是否已到期（替代原 QTimer 的单发冲刷）
    def flush_coalesced_if_due(self) -> None:
        with self._lock:
            since = self._coalesce_since
            if not self._coalescing or since is None:
                return
            if (time.monotonic() - since) * 1000 < COALESCING_INTERVAL_MS:
                return
            pending, self._coalescing = self._coalescing, {}
            self._coalesce_since = None

        for event, (data, sequence) in pending.items():
            self._dispatch(event, data, sequence)

    # 冲刷合并窗口
    def _flush_coalesced(self) -> None:
        with self._lock:
            if not self._coalescing:
                self._coalesce_since = None
                return
            pending, self._coalescing = self._coalescing, {}
            self._coalesce_since = None

        for event, (data, sequence) in pending.items():
            self._dispatch(event, data, sequence)

    # 分发给订阅者
    def _dispatch(self, event: StrEnum, data: dict, sequence: int | None = None) -> None:
        for hanlder in tuple(self.event_callbacks.get(event, ())):
            # 投递是排队延迟发生的：此时若照当前订阅列表分发，事件与构造之间才订阅的
            # 订阅者也会收到这条历史事件（页面刚打开就被上一条排队事件打断）。
            # 按订阅时刻过滤掉历史事件：订阅时刻记录的是当时的发射序号，
            # 只有序号更大的（订阅之后发出的）才投递。
            if sequence is not None:
                subscribed_at = self._subscriber_sequences.get((event, hanlder))
                if subscribed_at is not None and subscribed_at >= sequence:
                    continue

            hanlder(event, data)

    # 订阅事件
    def subscribe(self, event: StrEnum, hanlder: Callable) -> None:
        if callable(hanlder):
            # 截止序号与回调挂载放在同一把锁里，并先写序号。
            # 与 emit 的自增互斥，避免新订阅者读到偏小的序号后收到历史事件。
            with type(self)._sequence_lock:
                self._subscriber_sequences[(event, hanlder)] = type(self)._emit_sequence
                self.event_callbacks.setdefault(event, []).append(hanlder)

    # 取消订阅事件
    def unsubscribe(self, event: StrEnum, hanlder: Callable) -> None:
        callbacks = self.event_callbacks.get(event)
        if not callbacks:
            return

        # 退订可能重复触发（finished / destroyed 双路径），未注册过则不再抛错
        try:
            callbacks.remove(hanlder)
        except ValueError:
            return

        # 同一 handler 可能还订阅着其它事件，全部退订后才丢弃订阅时刻
        if all(hanlder not in group for group in self.event_callbacks.values()):
            for key in [key for key in self._subscriber_sequences if key[1] == hanlder]:
                self._subscriber_sequences.pop(key, None)