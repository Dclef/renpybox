"""通知服务：Toast 的去重判定、级别映射与 InfoBar 展示。

从主窗口抽出的决策层——去重状态机与文案聚合可脱离 Qt 窗口独立实例化
（``NotificationService()``）供单测；带窗口实例化后 ``show`` 直接创建
InfoBar。窗口侧只保留 Qt 生命周期守卫（app closing / qobject alive）。
"""

import time

from PyQt5.QtCore import Qt
from qfluentwidgets import InfoBar
from qfluentwidgets import InfoBarPosition

from base.Base import Base
from module.Localizer.Localizer import Localizer


class NotificationService:

    # Toast 同 key 滑窗去重：窗口内重复的提示不再新建 InfoBar，风暴结束后下一条带聚合计数
    TOAST_DEDUPE_WINDOW_SEC = 2.5

    def __init__(self, window = None) -> None:
        self._window = window
        self._toast_dedupe: dict[tuple, tuple] = {}

    def _dedupe_toast(self, toast_type: object, toast_message: str) -> str | None:
        """返回应展示的文案；窗口内重复时返回 None（吞掉）。"""
        key = (str(toast_type), toast_message)
        now = time.monotonic()
        last_shown, swallowed = self._toast_dedupe.get(key, (0.0, 0))

        if now - last_shown < self.TOAST_DEDUPE_WINDOW_SEC:
            self._toast_dedupe[key] = (last_shown, swallowed + 1)
            return None

        message = toast_message
        if swallowed > 0:
            message = message + Localizer.get().toast_merged_count.format(swallowed + 1)
        self._toast_dedupe[key] = (now, 0)
        return message

    def show(self, toast_type: object, toast_message: str, duration: int = 2500) -> None:
        deduped_message = self._dedupe_toast(toast_type, toast_message)
        if deduped_message is None:
            return

        if toast_type == Base.ToastType.ERROR:
            toast_func = InfoBar.error
        elif toast_type == Base.ToastType.WARNING:
            toast_func = InfoBar.warning
        elif toast_type == Base.ToastType.SUCCESS:
            toast_func = InfoBar.success
        else:
            toast_func = InfoBar.info

        if self._window is None:
            return

        toast_func(
            title = "",
            content = deduped_message,
            parent = self._window,
            duration = duration,
            orient = Qt.Orientation.Horizontal,
            position = InfoBarPosition.TOP,
            isClosable = True,
        )
