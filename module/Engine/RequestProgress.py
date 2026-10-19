"""Emit bounded status logs while a model request is still in flight."""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Callable, Iterator


@contextmanager
def request_progress(
    report: Callable[[str], None],
    label: str,
    *,
    interval: float = 5.0,
) -> Iterator[None]:
    """Log elapsed waiting time; stop the observer before leaving the request."""
    stopped = threading.Event()
    started_at = time.perf_counter()

    def heartbeat() -> None:
        while not stopped.wait(interval):
            elapsed = int(time.perf_counter() - started_at)
            report(f"{label} 等待模型响应中，已耗时 {elapsed} 秒")

    observer = threading.Thread(target=heartbeat, name="model-progress", daemon=True)
    observer.start()
    try:
        yield
    finally:
        stopped.set()
        observer.join()
