import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_sessionstart(session) -> None:
    """给整个测试进程装上事件总线的 drain 驱动。

    M1 起 EventManager 不再依赖 Qt signal：emit 只做线程安全入队，跨线程投递
    由 drain 驱动。生产环境里这个驱动来自 app.py（Qt 壳）或 api 层（Electron），
    测试环境必须等价地补上，否则 emit 出去的事件永远不会被投递。
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PyQt5.QtWidgets import QApplication

    QApplication.instance() or QApplication([])

    from frontend.QtEventBridge import install as install_event_bridge

    session.config._event_bridge = install_event_bridge()


def pytest_sessionfinish(session, exitstatus) -> None:
    bridge = getattr(session.config, "_event_bridge", None)
    if bridge is not None:
        bridge.stop()