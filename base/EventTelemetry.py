"""事件遥测：进程内延迟统计，为性能决策提供数字。

记录两类样本（毫秒）：
- 事件总线端到端延迟（emit → 实际分发，含合并窗口停留）；
- 主线程心跳漂移（事件名固定 ``__ui_heartbeat__``）。

数据只进内存环形缓冲（每事件最近 RING_SIZE 条），每累计 LOG_EVERY 条样本
向 LogManager 写一行摘要后重置计数。纯标准库，不依赖 Qt。
"""

import time


RING_SIZE = 512
LOG_EVERY = 1000
HEARTBEAT_EVENT = "__ui_heartbeat__"


def _percentile(sorted_values: list[float], ratio: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, round(ratio * (len(sorted_values) - 1))))
    return sorted_values[index]


class EventTelemetry:

    _instance: "EventTelemetry | None" = None

    def __init__(self) -> None:
        self._rings: dict[str, list[float]] = {}
        self._logged_count = 0

    @classmethod
    def get(cls) -> "EventTelemetry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """测试隔离用：清空单例状态。"""
        cls._instance = None

    def record(self, event: str, latency_ms: float) -> None:
        ring = self._rings.setdefault(str(event), [])
        ring.append(float(latency_ms))
        if len(ring) > RING_SIZE:
            del ring[: len(ring) - RING_SIZE]

        self._logged_count += 1
        if self._logged_count >= LOG_EVERY:
            self._logged_count = 0
            self._write_summary()

    def snapshot(self) -> dict[str, dict]:
        """每事件：count / p50 / p95 / max（毫秒，基于最近 RING_SIZE 条）。"""
        result: dict[str, dict] = {}
        for event, ring in self._rings.items():
            if not ring:
                continue
            ordered = sorted(ring)
            result[event] = {
                "count": len(ordered),
                "p50": round(_percentile(ordered, 0.50), 3),
                "p95": round(_percentile(ordered, 0.95), 3),
                "max": round(ordered[-1], 3),
            }
        return result

    def _write_summary(self) -> None:
        try:
            from base.LogManager import LogManager

            snapshot = self.snapshot()
            total = sum(item["count"] for item in snapshot.values())
            slowest = sorted(
                snapshot.items(), key = lambda pair: pair[1]["p95"], reverse = True
            )[:3]
            detail = ", ".join(
                f"{event} p95={item['p95']:.1f}ms" for event, item in slowest
            )
            LogManager.get().info(
                f"[Telemetry] events={total}"
                + (f", slowest: {detail}" if detail else ""),
                console = False,
            )
        except Exception:
            # 遥测自身绝不能影响业务路径
            pass


def record_latency(event: str, latency_ms: float) -> None:
    EventTelemetry.get().record(event, latency_ms)


class HeartbeatMonitor:
    """主线程心跳漂移测量：实际 tick 间隔与名义间隔之差。"""

    def __init__(self, *, interval_ms: int = 1000, min_drift_ms: float = 50.0) -> None:
        self.interval_ms = interval_ms
        self.min_drift_ms = min_drift_ms
        self._last: float | None = None

    def tick(self) -> float | None:
        """记录一次 tick，返回本次漂移（毫秒）；小于阈值的抖动不记录返回 None。"""
        now = time.monotonic()
        drift_ms: float | None = None
        if self._last is not None:
            drift_ms = max(0.0, (now - self._last) * 1000 - self.interval_ms)
            if drift_ms >= self.min_drift_ms:
                record_latency(HEARTBEAT_EVENT, drift_ms)
            else:
                drift_ms = None
        self._last = now
        return drift_ms
