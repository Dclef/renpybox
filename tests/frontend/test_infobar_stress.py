import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from frontend.AppFluentWindow import AppFluentWindow


APP = QApplication.instance() or QApplication([])


def test_infobar_stress_100_toasts_no_exception() -> None:
    """QFW 1.11.3 压测：InfoBar workaround 已删除，Toast 风暴不得抛竞态异常。"""
    window = AppFluentWindow()

    # 100 个不同 key：每条都会真实创建 InfoBar（不同文案不走去重）
    for i in range(100):
        window.show_toast("APP_TOAST_SHOW", {
            "type": "info",
            "message": f"压测消息 {i}",
            "duration": 100,
        })

    # 同 key 连发：走去重路径，只创建 1 条
    for _ in range(20):
        window.show_toast("APP_TOAST_SHOW", {
            "type": "error",
            "message": "重复错误",
            "duration": 100,
        })

    # 推进事件循环，让 InfoBar 的创建/布局/动画信号得到处理
    for _ in range(20):
        APP.processEvents()

    # 断言 InfoBarManager 中无指向该窗口的死引用残留
    # （读取 infoBars 仅用于断言，生产代码已不再访问该私有结构）
    from qfluentwidgets.components.widgets.info_bar import InfoBarManager

    for manager_cls in (InfoBarManager.managers or {}).values():
        manager = manager_cls()
        info_bars = getattr(manager, "infoBars", None)
        if info_bars is None or window not in info_bars:
            continue
        for bar in info_bars.get(window, []):
            assert window._is_qobject_alive(bar), "InfoBarManager 残留已释放的 InfoBar 引用"

    window.deleteLater()
    for _ in range(10):
        APP.processEvents()
