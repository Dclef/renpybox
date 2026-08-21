import time

from base.Base import Base
from frontend.AppFluentWindow import AppFluentWindow


def _dedupe_state() -> AppFluentWindow:
    # 只测去重状态机，不实例化整个 FluentWindow
    window = AppFluentWindow.__new__(AppFluentWindow)
    window._toast_dedupe = {}
    return window


def test_first_toast_passes_through_unchanged() -> None:
    window = _dedupe_state()
    message = window._dedupe_toast(Base.ToastType.ERROR, "请求失败")
    assert message == "请求失败"


def test_same_key_within_window_is_swallowed() -> None:
    window = _dedupe_state()
    assert window._dedupe_toast(Base.ToastType.ERROR, "请求失败") == "请求失败"
    assert window._dedupe_toast(Base.ToastType.ERROR, "请求失败") is None
    assert window._dedupe_toast(Base.ToastType.ERROR, "请求失败") is None


def test_different_type_or_message_not_swallowed() -> None:
    window = _dedupe_state()
    window._dedupe_toast(Base.ToastType.ERROR, "请求失败")
    # key 含类型与文案，任一不同都不吞
    assert window._dedupe_toast(Base.ToastType.WARNING, "请求失败") == "请求失败"
    assert window._dedupe_toast(Base.ToastType.ERROR, "另一个错误") == "另一个错误"


def test_after_window_next_toast_carries_merged_count() -> None:
    window = _dedupe_state()
    assert window._dedupe_toast(Base.ToastType.ERROR, "请求失败") == "请求失败"
    assert window._dedupe_toast(Base.ToastType.ERROR, "请求失败") is None
    assert window._dedupe_toast(Base.ToastType.ERROR, "请求失败") is None

    # 推进时间越过去重窗口（直接改上次放行时间）
    key = (str(Base.ToastType.ERROR), "请求失败")
    last_shown, swallowed = window._toast_dedupe[key]
    assert swallowed == 2
    window._toast_dedupe[key] = (last_shown - (window.TOAST_DEDUPE_WINDOW_SEC + 1), swallowed)

    message = window._dedupe_toast(Base.ToastType.ERROR, "请求失败")
    assert message is not None
    assert "3" in message  # 本条 + 吞掉的 2 条


def test_counter_resets_after_display() -> None:
    window = _dedupe_state()
    window._dedupe_toast(Base.ToastType.INFO, "提示")
    key = (str(Base.ToastType.INFO), "提示")
    window._toast_dedupe[key] = (time.monotonic() - 10, 5)

    message = window._dedupe_toast(Base.ToastType.INFO, "提示")
    assert message is not None and "6" in message

    # 显示后计数清零，窗口外下一条不再带计数
    window._toast_dedupe[key] = (time.monotonic() - 10, window._toast_dedupe[key][1])
    assert window._dedupe_toast(Base.ToastType.INFO, "提示") == "提示"
