import time

import pytest

from base.EventTelemetry import (
    HEARTBEAT_EVENT,
    EventTelemetry,
    HeartbeatMonitor,
    RING_SIZE,
)
import base.EventTelemetry as event_telemetry_module


@pytest.fixture(autouse = True)
def _fresh_telemetry():
    EventTelemetry.reset()
    yield
    EventTelemetry.reset()


def test_record_and_snapshot_percentiles() -> None:
    telemetry = EventTelemetry.get()
    for value in range(1, 101):
        telemetry.record("TEST_EVENT", float(value))

    snapshot = telemetry.snapshot()["TEST_EVENT"]
    assert snapshot["count"] == 100
    assert snapshot["p50"] == pytest.approx(50, abs = 1)
    assert snapshot["p95"] == pytest.approx(95, abs = 1)
    assert snapshot["max"] == 100


def test_ring_buffer_keeps_recent_samples_only() -> None:
    telemetry = EventTelemetry.get()
    for value in range(RING_SIZE + 500):
        telemetry.record("FLOOD", float(value))

    snapshot = telemetry.snapshot()["FLOOD"]
    assert snapshot["count"] == RING_SIZE
    assert snapshot["max"] == float(RING_SIZE + 499)


def test_summary_logged_every_1000_records(monkeypatch: pytest.MonkeyPatch) -> None:
    telemetry = EventTelemetry.get()
    logged: list[str] = []

    class _FakeLogManager:
        class _Inst:
            def info(self, msg, *args, **kwargs):
                logged.append(msg)

        get = classmethod(lambda cls: cls._Inst())

    monkeypatch.setattr(
        event_telemetry_module, "LogManager", _FakeLogManager, raising = False
    )
    # _write_summary 内部 import，需要 patch base.LogManager 模块本身
    import base.LogManager as real_log_manager

    monkeypatch.setattr(
        real_log_manager, "LogManager", _FakeLogManager, raising = False
    )

    for value in range(2500):
        telemetry.record("SLOW", 12.5)

    assert len(logged) == 2  # 1000 与 2000 处各一条
    assert "SLOW" in logged[0]


def test_telemetry_failure_never_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    telemetry = EventTelemetry.get()

    import base.LogManager as real_log_manager

    def broken_get():
        raise RuntimeError("log system down")

    monkeypatch.setattr(real_log_manager.LogManager, "get", staticmethod(broken_get))

    for value in range(1100):
        telemetry.record("X", 1.0)  # 触发摘要写入，内部异常被吞
    assert telemetry.snapshot()["X"]["count"] > 0


def test_heartbeat_monitor_skips_small_drift() -> None:
    monitor = HeartbeatMonitor(interval_ms = 1000, min_drift_ms = 50)
    monitor.tick()
    time.sleep(0.02)
    assert monitor.tick() is None  # 20ms 抖动不记录
    assert EventTelemetry.get().snapshot() == {}


def test_heartbeat_monitor_records_real_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    monitor = HeartbeatMonitor(interval_ms = 10, min_drift_ms = 5)
    monitor.tick()
    time.sleep(0.08)
    drift = monitor.tick()
    assert drift is not None and drift >= 5
    snapshot = EventTelemetry.get().snapshot()[HEARTBEAT_EVENT]
    assert snapshot["count"] == 1


def test_event_manager_signal_path_records_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    """emit→_on_signal 链路产生延迟记录且 data 原样到达 process_event。"""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from base.Base import Base
    from base.EventManager import EventManager

    manager = EventManager()
    received: list[dict] = []
    monkeypatch.setattr(
        manager, "process_event", lambda event, data: received.append(data)
    )

    payload = {"progress": 42}
    manager._on_signal(Base.Event.TRANSLATION_UPDATE, (payload, time.monotonic() - 0.5))

    assert received == [payload]  # 订阅侧 data 无污染
    snapshot = EventTelemetry.get().snapshot()["TRANSLATION_UPDATE"]
    assert snapshot["count"] == 1
    assert snapshot["max"] >= 400  # 预置 0.5s 延迟被测到


def test_event_manager_emit_wraps_payload_with_timestamp() -> None:
    """emit 走 signal 的包装格式（QueuedConnection 下信号暂存，验证包装结构）。"""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from base.Base import Base
    from base.EventManager import EventManager

    manager = EventManager()
    captured: list[tuple] = []

    def capture(event, wrapped):
        captured.append((event, wrapped))

    # 直连捕获（绕过 queued 以同步断言）
    manager.signal.connect(capture, 1)  # Qt.DirectConnection

    payload = {"k": 1}
    before = time.monotonic()
    manager.emit(Base.Event.PROJECT_STATUS, payload)
    after = time.monotonic()

    assert len(captured) == 1
    event, wrapped = captured[0]
    assert event == Base.Event.PROJECT_STATUS
    data, emitted_at = wrapped
    assert data == payload
    assert before <= emitted_at <= after
