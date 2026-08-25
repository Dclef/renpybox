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

        # 窗口未冲刷前不分发，仅暂存最新值
        assert received == []
        assert manager._coalescing == {Base.Event.TRANSLATION_UPDATE: {"progress": 3}}

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
