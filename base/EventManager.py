import threading
import time
from typing import Callable

from base.compat import StrEnum, Self
from base.EventTelemetry import record_latency

from PyQt5.QtCore import Qt
from PyQt5.QtCore import QObject
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import pyqtSignal

# 事件名与 base/Base.py 的 Event 枚举值保持一致（此处不能 import Base，避免循环依赖）
# TRANSLATION_UPDATE 只承载中间态（preparing 消息 / progress 统计 / quality_task 进度），
# 终态由 TRANSLATION_DONE / TRANSLATION_STOP_DONE 独立通知，到达时先冲刷合并窗口保证顺序。
COALESCING_EVENTS = {"TRANSLATION_UPDATE"}
FLUSH_ON_EVENTS = {"TRANSLATION_DONE", "TRANSLATION_STOP_DONE"}
COALESCING_INTERVAL_MS = 200

class EventManager(QObject):

    # 自定义信号
    # 字典类型或者其他复杂对象应该使用 object 作为信号参数类型，这样可以传递任意 Python 对象，包括 dict
    signal: pyqtSignal = pyqtSignal(StrEnum, object)

    # 事件列表
    event_callbacks: dict[StrEnum, list[Callable]] = {}

    # 发射序号：自增计数，每条事件带上发射时刻的序号
    # 与 event_callbacks 同为类级：投递是排队延迟发生的，可能由另一个实例执行，
    # 序号若各实例自行计数，就无法跨实例判断订阅与发射的先后，过滤会漏掉历史事件
    _emit_sequence: int = 0
    # 序号跨实例共享，实例之间没有同一把锁。自增与订阅时刻的读取必须互斥，
    # 否则并发 emit 会读到同一个值，订阅过滤会把历史事件投给新订阅者。
    _sequence_lock = threading.Lock()

    # 订阅时刻的发射序号，键为 (event, handler)：绑定方法每次访问都是新对象，
    # 但相等性与哈希稳定，可用于识别「订阅之前就已发出」的历史事件
    _subscriber_sequences: dict[tuple[StrEnum, Callable], int] = {}

    def __init__(self) -> None:
        super().__init__()

        self.signal.connect(self._on_signal, Qt.ConnectionType.QueuedConnection)

        # 中间态事件 latest-value 合并：窗口内多次发射只分发最新值，
        # 状态全部在主线程（process_event / timer 回调）读写，与后台线程的 emit 无竞争
        self._coalescing: dict[StrEnum, tuple[dict, int | None]] = {}
        self._coalesce_timer = QTimer(self)
        self._coalesce_timer.setSingleShot(True)
        self._coalesce_timer.setInterval(COALESCING_INTERVAL_MS)
        self._coalesce_timer.timeout.connect(self._flush_coalesced)

    @classmethod
    def get(cls) -> Self:
        if not hasattr(cls, "__instance__"):
            cls.__instance__ = cls()

        return cls.__instance__

    # 处理事件
    # sequence 为事件的发射序号；None 表示不经 emit 直接调用（测试与内部冲刷）
    def process_event(self, event: StrEnum, data: dict, sequence: int | None = None) -> None:
        # 终态事件先冲刷合并窗口，订阅者先看到最后的中间状态再看到完成状态
        if event in FLUSH_ON_EVENTS:
            self._flush_coalesced()

        # 可合并事件暂存最新值，由单发 timer 统一冲刷
        if event in COALESCING_EVENTS:
            self._coalescing[event] = (data, sequence)
            if not self._coalesce_timer.isActive():
                self._coalesce_timer.start()
            return

        self._dispatch(event, data, sequence)

    # 冲刷合并窗口
    def _flush_coalesced(self) -> None:
        if not self._coalescing:
            return

        pending, self._coalescing = self._coalescing, {}
        for event, (data, sequence) in pending.items():
            self._dispatch(event, data, sequence)

    # 分发给订阅者
    def _dispatch(self, event: StrEnum, data: dict, sequence: int | None = None) -> None:
        for hanlder in tuple(self.event_callbacks.get(event, ())):
            # 信号是 QueuedConnection：事件要到下一次 process_events 才投递，
            # 此时若照当前订阅列表分发，事件与构造之间才订阅的订阅者也会收到这条
            # 历史事件（页面刚打开就被上一条排队事件打断）。按订阅时刻过滤掉历史事件。
            # 订阅时刻记录的是当时的发射序号，只有序号更大的（订阅之后发出的）才投递。
            if sequence is not None:
                subscribed_at = self._subscriber_sequences.get((event, hanlder))
                if subscribed_at is not None and subscribed_at >= sequence:
                    continue

            hanlder(event, data)

    # 信号槽：解包遥测时间戳与发射序号，测 emit→实际分发的端到端延迟（含合并窗口停留）
    def _on_signal(self, event: StrEnum, wrapped: tuple) -> None:
        data, emitted_at, sequence = wrapped
        record_latency(str(event), (time.monotonic() - emitted_at) * 1000)
        self.process_event(event, data, sequence)

    # 触发事件
    def emit(self, event: StrEnum, data: dict) -> None:
        # payload 包装时间戳随信号走，Qt 签名不变（object 装 tuple）；
        # 订阅者最终拿到的 data 保持原样
        cls = type(self)
        with cls._sequence_lock:
            cls._emit_sequence += 1
            sequence = cls._emit_sequence
        self.signal.emit(event, (data, time.monotonic(), sequence))

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