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


def test_event_manager_drain_path_records_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    """emit→drain 链路产生延迟记录且 data 原样到达 process_event。

    M1 起EventManager 不再依赖 Qt signal：emit 只入队，drain 才投递并记录
    emit→投递的端到端延迟。
    """
    from base.Base import Base
    from base.EventManager import EventManager

    manager = EventManager()
    received: list[dict] = []
    monkeypatch.setattr(
        manager, "process_event", lambda event, data, sequence=None: received.append(data)
    )

    payload = {"progress": 42}
    manager.emit(Base.Event.TRANSLATION_UPDATE, payload)
    time.sleep(0.05)
    manager.drain()

    assert received == [payload]  # 订阅侧 data 无污染
    snapshot = EventTelemetry.get().snapshot()["TRANSLATION_UPDATE"]
    assert snapshot["count"] == 1
    assert snapshot["max"] >= 35  # 入队到排空之间的延迟被测到


def test_event_manager_emit_enqueues_payload_with_timestamp() -> None:
    """emit 只入队，队列元素携带 (事件, 数据, 发射时刻, 发射序号)。"""
    from base.Base import Base
    from base.EventManager import EventManager

    manager = EventManager()
    received: list[tuple] = []
    manager.subscribe(Base.Event.PROJECT_STATUS, lambda event, data: received.append((event, data)))

    payload = {"k": 1}
    before = time.monotonic()
    manager.emit(Base.Event.PROJECT_STATUS, payload)
    after = time.monotonic()

    assert len(manager._queue) == 1
    event, data, emitted_at, sequence = manager._queue[-1]
    assert event == Base.Event.PROJECT_STATUS
    assert data is payload  # data 不再被包装，订阅者拿到的就是原对象
    assert before <= emitted_at <= after

    manager.drain()
    assert received == [(Base.Event.PROJECT_STATUS, payload)]
    assert sequence == manager._emit_sequence  # 带发射序号，供订阅时刻过滤


@pytest.fixture()
def deepcopy_instrumented():
    from base.EventTelemetry import (
        install_deepcopy_instrumentation,
        restore_deepcopy_instrumentation,
    )

    install_deepcopy_instrumentation()
    yield
    restore_deepcopy_instrumentation()


def test_deepcopy_instrumentation_records_caller_module(deepcopy_instrumented) -> None:
    import copy

    payload = {"list": [1, 2, {"nested": True}]}
    cloned = copy.deepcopy(payload)
    cloned["list"][2]["nested"] = False
    assert payload["list"][2]["nested"] is True  # 行为等价：隔离语义保持

    snapshot = EventTelemetry.get().snapshot()
    key = f"__deepcopy__:{__name__}"
    assert key in snapshot
    assert snapshot[key]["count"] >= 1
    assert snapshot[key]["max"] >= 0


def test_deepcopy_instrumentation_is_idempotent(deepcopy_instrumented) -> None:
    import copy

    from base.EventTelemetry import install_deepcopy_instrumentation

    first = copy.deepcopy
    install_deepcopy_instrumentation()
    assert copy.deepcopy is first  # 二次安装不重复包装

    copy.deepcopy({"a": 1})
    snapshot = EventTelemetry.get().snapshot()
    assert snapshot[f"__deepcopy__:{__name__}"]["count"] == 1  # 只记一次


def test_deepcopy_instrumentation_propagates_exceptions(deepcopy_instrumented) -> None:
    import copy

    class UnCopyable:
        def __deepcopy__(self, memo):
            raise ValueError("no copy for you")

    with pytest.raises(ValueError, match = "no copy for you"):
        copy.deepcopy(UnCopyable())
    # 异常路径也留下记录
    assert EventTelemetry.get().snapshot()[f"__deepcopy__:{__name__}"]["count"] >= 1



def test_config_load_records_only_on_main_thread(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    import threading

    from module.Config import Config

    monkeypatch.setattr(Config, "CONFIG_PATH", str(tmp_path / "config.json"))

    recorded: list[str] = []

    def fake_record(event: str, latency_ms: float) -> None:
        recorded.append(event)

    import base.EventTelemetry as telemetry_module

    monkeypatch.setattr(telemetry_module, "record_latency", fake_record)
    # Config 模块是函数引用导入，需 patch 其命名空间
    import module.Config as config_module

    monkeypatch.setattr(config_module, "record_latency", fake_record)

    Config().load()
    assert "__ui_config_read__" in recorded  # pytest 主线程

    recorded.clear()
    result: list[str] = []

    def background_load():
        Config().load()
        result.append("done")

    thread = threading.Thread(target = background_load)
    thread.start()
    thread.join()
    assert result == ["done"]
    assert recorded == []  # 后台线程不计入 UI 读盘
