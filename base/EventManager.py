from base.compat import StrEnum, Self
from typing import Callable

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

    def __init__(self) -> None:
        super().__init__()

        self.signal.connect(self.process_event, Qt.ConnectionType.QueuedConnection)

        # 中间态事件 latest-value 合并：窗口内多次发射只分发最新值，
        # 状态全部在主线程（process_event / timer 回调）读写，与后台线程的 emit 无竞争
        self._coalescing: dict[StrEnum, dict] = {}
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
    def process_event(self, event: StrEnum, data: dict) -> None:
        # 终态事件先冲刷合并窗口，订阅者先看到最后的中间状态再看到完成状态
        if event in FLUSH_ON_EVENTS:
            self._flush_coalesced()

        # 可合并事件暂存最新值，由单发 timer 统一冲刷
        if event in COALESCING_EVENTS:
            self._coalescing[event] = data
            if not self._coalesce_timer.isActive():
                self._coalesce_timer.start()
            return

        self._dispatch(event, data)

    # 冲刷合并窗口
    def _flush_coalesced(self) -> None:
        if not self._coalescing:
            return

        pending, self._coalescing = self._coalescing, {}
        for event, data in pending.items():
            self._dispatch(event, data)

    # 分发给订阅者
    def _dispatch(self, event: StrEnum, data: dict) -> None:
        if event in self.event_callbacks:
            for hanlder in self.event_callbacks[event]:
                hanlder(event, data)

    # 触发事件
    def emit(self, event: StrEnum, data: dict) -> None:
        self.signal.emit(event, data)

    # 订阅事件
    def subscribe(self, event: StrEnum, hanlder: Callable) -> None:
        if callable(hanlder):
            self.event_callbacks.setdefault(event, []).append(hanlder)

    # 取消订阅事件
    def unsubscribe(self, event: StrEnum, hanlder: Callable) -> None:
        if event in self.event_callbacks:
            self.event_callbacks[event].remove(hanlder)