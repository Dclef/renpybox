import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from base.Base import Base
from base.EventManager import EventManager


APP = QApplication.instance() or QApplication([])


def _fresh_manager() -> EventManager:
    manager = EventManager()
    assert manager._coalescing == {}
    return manager


def test_coalescing_event_defers_and_keeps_latest_value() -> None:
    manager = _fresh_manager()
    received: list[dict] = []
    handler = lambda event, data: received.append(data)
    manager.subscribe(Base.Event.TRANSLATION_UPDATE, handler)
    try:
        manager.process_event(Base.Event.TRANSLATION_UPDATE, {"progress": 1})
        manager.process_event(Base.Event.TRANSLATION_UPDATE, {"progress": 2})
        manager.process_event(Base.Event.TRANSLATION_UPDATE, {"progress": 3})

        # 窗口未冲刷前不分发，仅暂存最新值（值为 (数据, 发射序号)）
        assert received == []
        assert manager._coalescing == {Base.Event.TRANSLATION_UPDATE: ({"progress": 3}, None)}

        manager._flush_coalesced()
        assert received == [{"progress": 3}]
        assert manager._coalescing == {}
    finally:
        manager.unsubscribe(Base.Event.TRANSLATION_UPDATE, handler)


def test_non_coalescing_event_dispatches_immediately() -> None:
    manager = _fresh_manager()
    received: list[tuple] = []
    handler = lambda event, data: received.append((event, data))
    manager.subscribe(Base.Event.PROJECT_STATUS, handler)
    try:
        payload = {"status": "idle"}
        manager.process_event(Base.Event.PROJECT_STATUS, payload)
        assert received == [(Base.Event.PROJECT_STATUS, payload)]
    finally:
        manager.unsubscribe(Base.Event.PROJECT_STATUS, handler)


def test_terminal_event_flushes_pending_before_dispatch() -> None:
    manager = _fresh_manager()
    order: list[str] = []

    def on_update(event, data) -> None:
        order.append("update")

    def on_done(event, data) -> None:
        order.append("done")

    manager.subscribe(Base.Event.TRANSLATION_UPDATE, on_update)
    manager.subscribe(Base.Event.TRANSLATION_DONE, on_done)
    try:
        manager.process_event(Base.Event.TRANSLATION_UPDATE, {"progress": 9})
        manager.process_event(Base.Event.TRANSLATION_DONE, {"success": True})

        # 终态先冲刷合并窗口，订阅者先看到最后的中间状态再看到完成状态
        assert order == ["update", "done"]
        assert manager._coalescing == {}
    finally:
        manager.unsubscribe(Base.Event.TRANSLATION_UPDATE, on_update)
        manager.unsubscribe(Base.Event.TRANSLATION_DONE, on_done)


def test_flush_allows_recoalescing_afterwards() -> None:
    manager = _fresh_manager()
    received: list[dict] = []
    handler = lambda event, data: received.append(data)
    manager.subscribe(Base.Event.TRANSLATION_UPDATE, handler)
    try:
        manager.process_event(Base.Event.TRANSLATION_UPDATE, {"round": 1})
        manager._flush_coalesced()

        # 冲刷后可再次暂存（timer 复用场景）
        manager.process_event(Base.Event.TRANSLATION_UPDATE, {"round": 2})
        manager.process_event(Base.Event.TRANSLATION_UPDATE, {"round": 3})
        manager._flush_coalesced()

        assert received == [{"round": 1}, {"round": 3}]
    finally:
        manager.unsubscribe(Base.Event.TRANSLATION_UPDATE, handler)


def test_flush_without_pending_is_noop() -> None:
    manager = _fresh_manager()
    manager._flush_coalesced()
    assert manager._coalescing == {}


def test_event_emitted_before_subscription_is_not_delivered() -> None:
    """QueuedConnection 下事件延迟投递，订阅前发出的事件不应打扰后订阅者。

    信号用 QueuedConnection 连接，emit 只是把事件排进 Qt 队列，要到下一次
    process_events 才投递。若投递时才查订阅列表，事件与构造之间才订阅的
    订阅者会收到这条「历史事件」（页面刚打开就被上一条排队事件打断）。
    """
    manager = _fresh_manager()
    received: list[dict] = []
    handler = lambda event, data: received.append(data)

    # 先发出事件（序号 +1），handler 之后才订阅
    EventManager._emit_sequence += 1
    stale_sequence = EventManager._emit_sequence
    manager.subscribe(Base.Event.PROJECT_CHANGED, handler)
    try:
        # 模拟「先发出、后订阅、再投递」的时序
        manager.process_event(
            Base.Event.PROJECT_CHANGED, {"project_root": "old"}, stale_sequence
        )
        assert received == []

        # 订阅之后发出的事件照常投递
        EventManager._emit_sequence += 1
        manager.process_event(
            Base.Event.PROJECT_CHANGED,
            {"project_root": "new"},
            EventManager._emit_sequence,
        )
        assert received == [{"project_root": "new"}]
    finally:
        manager.unsubscribe(Base.Event.PROJECT_CHANGED, handler)


def test_unsubscribed_handler_skips_still_queued_event() -> None:
    """投递前退订的订阅者不应再被调用（否则会打到已销毁的窗口上）。"""
    manager = _fresh_manager()
    received: list[dict] = []
    handler = lambda event, data: received.append(data)
    manager.subscribe(Base.Event.PROJECT_CHANGED, handler)

    EventManager._emit_sequence += 1
    sequence = EventManager._emit_sequence
    manager.unsubscribe(Base.Event.PROJECT_CHANGED, handler)
    manager.process_event(Base.Event.PROJECT_CHANGED, {"project_root": "old"}, sequence)
    assert received == []


def test_queued_event_only_reaches_handlers_subscribed_when_it_was_emitted() -> None:
    """真实 emit 链路：事件只投递给「发射时就已经订阅」的订阅者。"""
    manager = _fresh_manager()
    events: list[str] = []
    early = lambda event, data: events.append("early")
    late = lambda event, data: events.append("late")

    manager.subscribe(Base.Event.PROJECT_CHANGED, early)

    # 先发出事件（此时 late 还没订阅），再让 Qt 投递
    manager.emit(Base.Event.PROJECT_CHANGED, {"project_root": "old"})
    manager.subscribe(Base.Event.PROJECT_CHANGED, late)
    APP.processEvents()

    assert events == ["early"]

    # 订阅之后发出的事件两个订阅者都收得到
    manager.emit(Base.Event.PROJECT_CHANGED, {"project_root": "new"})
    APP.processEvents()
    assert events == ["early", "early", "late"]


def test_queued_event_from_another_instance_is_not_delivered() -> None:
    """旧实例排队的事件不应被新实例刚订阅的处理器收到。

    事件在排队期间跨越实例投递（应用只有单例，测试会另建实例）。
    发射序号若按实例各自计数，新实例的订阅时刻会被当成「早于发射」，
    过滤失效，上一条排队事件就会打到刚订阅的订阅者上。
    """
    emitter = _fresh_manager()
    manager = _fresh_manager()
    received: list[dict] = []
    handler = lambda event, data: received.append(data)

    # emitter 发出事件后不再有订阅者，事件停在 Qt 队列里
    emitter.emit(Base.Event.PROJECT_CHANGED, {"project_root": "old"})
    manager.subscribe(Base.Event.PROJECT_CHANGED, handler)
    try:
        APP.processEvents()
        assert received == []

        # 新实例自己发出的事件照常投递
        manager.emit(Base.Event.PROJECT_CHANGED, {"project_root": "new"})
        APP.processEvents()
        assert received == [{"project_root": "new"}]
    finally:
        manager.unsubscribe(Base.Event.PROJECT_CHANGED, handler)


def test_process_event_without_sequence_keeps_current_behavior() -> None:
    """不经 emit 直接调用 process_event 时按当前订阅列表分发（合并窗口语义不变）。"""
    manager = _fresh_manager()
    received: list[tuple] = []
    handler = lambda event, data: received.append((event, data))
    manager.subscribe(Base.Event.PROJECT_STATUS, handler)
    try:
        payload = {"status": "idle"}
        manager.process_event(Base.Event.PROJECT_STATUS, payload)
        assert received == [(Base.Event.PROJECT_STATUS, payload)]
    finally:
        manager.unsubscribe(Base.Event.PROJECT_STATUS, handler)


def test_coalesced_event_keeps_its_own_sequence() -> None:
    """合并窗口暂存的值要带着发射序号，冲刷时才按订阅时刻过滤。"""
    manager = _fresh_manager()
    stale: list[dict] = []
    fresh: list[dict] = []

    EventManager._emit_sequence += 1
    stale_sequence = EventManager._emit_sequence
    stale_handler = lambda event, data: stale.append(data)
    manager.subscribe(Base.Event.TRANSLATION_UPDATE, stale_handler)

    EventManager._emit_sequence += 1
    fresh_sequence = EventManager._emit_sequence
    fresh_handler = lambda event, data: fresh.append(data)
    manager.subscribe(Base.Event.TRANSLATION_UPDATE, fresh_handler)

    try:
        # 窗口内最后一条（序号 2）覆盖前一条，冲刷时：
        # 订阅时刻为 1 的 stale_handler 收得到，订阅时刻为 2 的 fresh_handler 收不到
        manager.process_event(Base.Event.TRANSLATION_UPDATE, {"progress": 1}, stale_sequence)
        manager.process_event(Base.Event.TRANSLATION_UPDATE, {"progress": 2}, fresh_sequence)
        manager._flush_coalesced()
        assert stale == [{"progress": 2}]
        assert fresh == []
    finally:
        manager.unsubscribe(Base.Event.TRANSLATION_UPDATE, stale_handler)
        manager.unsubscribe(Base.Event.TRANSLATION_UPDATE, fresh_handler)


def test_repeated_unsubscribe_does_not_raise() -> None:
    """finished / destroyed 双路径重复退订不应抛 ValueError。"""
    manager = _fresh_manager()
    handler = lambda event, data: None
    manager.subscribe(Base.Event.PROJECT_CHANGED, handler)
    manager.unsubscribe(Base.Event.PROJECT_CHANGED, handler)
    manager.unsubscribe(Base.Event.PROJECT_CHANGED, handler)
