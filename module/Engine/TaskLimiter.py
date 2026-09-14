import threading
import time
from typing import Callable
from typing import Optional

class TaskLimiter:

    def __init__(self, rps: int, rpm: int, max_concurrency: int = 0) -> None:
        self.rps = rps
        self.rpm = rpm
        self.max_capacity = self._calculate_max_capacity()
        self.rate_per_second = self._calculate_stricter_rate()
        self.current_capacity = self.max_capacity
        self.last_request_time = time.monotonic()
        self.lock = threading.Lock()

        # 并发控制
        self.semaphore = threading.BoundedSemaphore(max_concurrency) if max_concurrency > 0 else None

    # 计算最大容量
    def _calculate_max_capacity(self) -> float:
        rate = min(
            self.rps if self.rps > 0 else float("inf"),
            self.rpm / 60 if self.rpm > 0 else float("inf"),
        )
        return max(1.0, rate)

    # 计算每秒恢复的请求额度
    def _calculate_stricter_rate(self) -> float:
        return min(
            self.rps if self.rps > 0 else float("inf"),
            self.rpm / 60 if self.rpm > 0 else float("inf"),
        )

    # 尝试获取并发许可
    def acquire(self, stop_checker: Optional[Callable[[], bool]] = None) -> bool:
        if self.semaphore is None:
            return True

        while not self.semaphore.acquire(timeout = 0.1):
            if stop_checker is not None and stop_checker():
                return False
        return True

    # 释放并发许可
    def release(self, *args) -> None:
        if self.semaphore is not None:
            self.semaphore.release()

    # 等待直到有足够的请求额度
    def wait(self, stop_checker: Optional[Callable[[], bool]] = None) -> bool:
        while True:
            if stop_checker is not None and stop_checker():
                return False
            with self.lock:
                now = time.monotonic()
                self.current_capacity = min(
                    self.max_capacity,
                    self.current_capacity + (now - self.last_request_time) * self.rate_per_second,
                )
                self.last_request_time = now
                if self.current_capacity >= 1:
                    self.current_capacity -= 1
                    return True
                wait_time = (1 - self.current_capacity) / self.rate_per_second
            time.sleep(min(wait_time, 0.25))
