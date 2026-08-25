import time

from base.Base import Base
from frontend.NotificationService import NotificationService


def test_first_toast_passes_through_unchanged() -> None:
    service = NotificationService()
    assert service._dedupe_toast(Base.ToastType.ERROR, "请求失败") == "请求失败"


def test_same_key_within_window_is_swallowed() -> None:
    service = NotificationService()
    assert service._dedupe_toast(Base.ToastType.ERROR, "请求失败") == "请求失败"
    assert service._dedupe_toast(Base.ToastType.ERROR, "请求失败") is None
    assert service._dedupe_toast(Base.ToastType.ERROR, "请求失败") is None


def test_different_type_or_message_not_swallowed() -> None:
    service = NotificationService()
    service._dedupe_toast(Base.ToastType.ERROR, "请求失败")
    # key 含类型与文案，任一不同都不吞
    assert service._dedupe_toast(Base.ToastType.WARNING, "请求失败") == "请求失败"
    assert service._dedupe_toast(Base.ToastType.ERROR, "另一个错误") == "另一个错误"


def test_after_window_next_toast_carries_merged_count() -> None:
    service = NotificationService()
    assert service._dedupe_toast(Base.ToastType.ERROR, "请求失败") == "请求失败"
    assert service._dedupe_toast(Base.ToastType.ERROR, "请求失败") is None
    assert service._dedupe_toast(Base.ToastType.ERROR, "请求失败") is None

    # 推进时间越过去重窗口（直接改上次放行时间）
    key = (str(Base.ToastType.ERROR), "请求失败")
    last_shown, swallowed = service._toast_dedupe[key]
    assert swallowed == 2
    service._toast_dedupe[key] = (last_shown - (service.TOAST_DEDUPE_WINDOW_SEC + 1), swallowed)

    message = service._dedupe_toast(Base.ToastType.ERROR, "请求失败")
    assert message is not None
    assert "3" in message  # 本条 + 吞掉的 2 条


def test_counter_resets_after_display() -> None:
    service = NotificationService()
    service._dedupe_toast(Base.ToastType.INFO, "提示")
    key = (str(Base.ToastType.INFO), "提示")
    service._toast_dedupe[key] = (time.monotonic() - 10, 5)

    message = service._dedupe_toast(Base.ToastType.INFO, "提示")
    assert message is not None and "6" in message

    # 显示后计数清零，窗口外下一条不再带计数
    service._toast_dedupe[key] = (time.monotonic() - 10, service._toast_dedupe[key][1])
    assert service._dedupe_toast(Base.ToastType.INFO, "提示") == "提示"


def test_show_without_window_only_dedupes() -> None:
    """无窗口实例（纯决策模式）：去重生效且不触碰 Qt。"""
    service = NotificationService()
    service.show(Base.ToastType.ERROR, "无窗口提示")  # 不抛异常
    assert service._dedupe_toast(Base.ToastType.ERROR, "无窗口提示") is None
