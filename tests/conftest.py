import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _DrainDriver:
    """测试进程的事件总线 drain 驱动。

    ``EventManager.emit`` 只做线程安全入队，跨线程投递由 drain 驱动完成。
    生产环境里驱动来自 Electron sidecar（``api`` 层用 asyncio 周期调用
    ``EventManager.drain_all``）；Qt 壳退役后，测试环境不再需要 QApplication，
    用一个后台线程等价地驱动即可。
    """

    def __init__(self, interval: float = 0.005) -> None:
        self._interval = interval
        self._stop = threading.Event()
        # 驱动与暂停共用一把锁：pause() 返回后保证没有 drain 正在执行
        self._gate = threading.Lock()
        self._paused = False
        self._thread = threading.Thread(
            target=self._run,
            name="renpybox-test-drain",
            daemon=True,
        )

    def start(self) -> "_DrainDriver":
        self._thread.start()
        return self

    def pause(self) -> None:
        """暂停自动 drain（延迟/遥测类测试需要独占事件总线时使用）。"""
        with self._gate:
            self._paused = True

    def resume(self) -> None:
        with self._gate:
            self._paused = False

    def _run(self) -> None:
        from base.EventManager import EventManager

        while not self._stop.is_set():
            with self._gate:
                if not self._paused:
                    try:
                        EventManager.drain_all()
                    except Exception:  # noqa: BLE001 - 测试驱动不能把进程带崩
                        pass
            time.sleep(self._interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)


def pytest_sessionstart(session) -> None:
    session.config._event_bridge = _DrainDriver().start()


def pytest_sessionfinish(session, exitstatus) -> None:
    bridge = getattr(session.config, "_event_bridge", None)
    if bridge is not None:
        bridge.stop()
