"""批量单条翻译的并发与取消回归。"""

from __future__ import annotations

import threading
import time

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Engine.Engine import Engine


def _item(index: int) -> CacheItem:
    return CacheItem.from_dict({
        "src": f"Source {index}",
        "dst": f"译文 {index}",
        "status": Base.TranslationStatus.TRANSLATED.value,
        "file_path": f"tl/chinese/script_{index}.rpy",
        "row": index + 1,
    })


def _reset_engine() -> Engine:
    engine = Engine.get()
    engine.status = Engine.Status.IDLE
    engine.stop_barrier = False
    engine.single_task_count = 0
    return engine


def test_translate_items_respects_worker_limit(monkeypatch) -> None:
    engine = _reset_engine()
    items = [_item(index) for index in range(12)]

    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_task(self, item: CacheItem, config: object) -> bool:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        return True

    monkeypatch.setattr(Engine, "_translate_single_item_task", fake_task)

    completed = engine.translate_items(items, None, lambda item, success: None, max_workers = 4)

    assert completed == len(items)
    assert peak <= 4
    assert engine.has_single_tasks() is False


def test_translate_items_stops_pending_items_when_cancelled(monkeypatch) -> None:
    engine = _reset_engine()
    items = [_item(index) for index in range(6)]
    handled: list[int] = []

    monkeypatch.setattr(Engine, "_translate_single_item_task", lambda self, item, config: True)

    completed = engine.translate_items(
        items,
        None,
        lambda item, success: handled.append(id(item)),
        max_workers = 2,
        should_cancel = lambda: True,
    )

    assert completed == 0
    assert handled == []
    assert engine.has_single_tasks() is False


def test_translate_items_releases_busy_flag_after_engine_busy(monkeypatch) -> None:
    """引擎已被占用时整批拒绝，且不能留下忙碌计数。"""
    engine = _reset_engine()
    engine.set_status(Engine.Status.TRANSLATING)
    items = [_item(0)]
    handled: list[bool] = []

    try:
        completed = engine.translate_items(
            items,
            None,
            lambda item, success: handled.append(success),
        )
    finally:
        engine.set_status(Engine.Status.IDLE)

    assert completed == 0
    assert handled == [False]
    assert engine.has_single_tasks() is False


def test_batch_cancellation_keeps_completed_results_without_submitting_next_batch(monkeypatch):
    engine = _reset_engine()
    cancel = threading.Event()
    executed, reported = [], []

    def translate(self, item, config):
        executed.append(id(item))
        cancel.set()
        return True

    monkeypatch.setattr(Engine, "_translate_single_item_task", translate)
    count = engine.translate_items(
        [_item(i) for i in range(10)], None,
        lambda item, success: reported.append((id(item), success)),
        max_workers=2, should_cancel=cancel.is_set,
    )
    assert count == len(executed) == len(reported) == 2
    assert all(success for _, success in reported)
    assert not engine.has_single_tasks()
