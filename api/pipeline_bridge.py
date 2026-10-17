"""Agent 后台线程与主事件循环之间的翻译启停桥。

Agent 工具跑在后台线程，而翻译受理逻辑（``api.routes.translation``）绑定在
FastAPI 的事件循环上。本模块只做「投递协程 + 等待结果 + 统一错误形状」，
不复制任何受理逻辑，避免与翻译页的并发不变量分叉。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Callable

from fastapi import HTTPException

from api.routes.translation import request_translation_start, request_translation_stop
from api.schemas import TranslationOwnerRequest, TranslationStartRequest
from module.Renpy.ProjectPaths import RenpyProjectPaths

# start 的前置校验（资产预检、载荷冻结）可能触发磁盘扫描，给足等待时间。
START_TIMEOUT = 120.0
STOP_TIMEOUT = 30.0

_CONTEXT_MISSING_DETAIL = "主事件循环尚未就绪，无法执行翻译操作"


def _failure(reason: str, detail: str, **extra: Any) -> dict:
    """统一的失败结果；字段与 TranslationStartResponse 的命名保持一致。"""
    result: dict[str, Any] = {"accepted": False, "reason": reason, "detail": detail}
    result.update(extra)
    return result


def _build_start_request(payload: dict) -> TranslationStartRequest:
    """只取 TranslationStartRequest 已声明的字段，丢弃模型的多余参数。

    Agent 侧 status 默认是小写 ``untranslated``，而引擎状态枚举是大写；
    在桥接层做一次规范化，避免默认值直接变成 400。
    """
    declared = TranslationStartRequest.model_fields
    values = {key: value for key, value in payload.items() if key in declared}
    status = values.get("status")
    if isinstance(status, str) and status.strip():
        values["status"] = status.strip().upper()
    return TranslationStartRequest(**values)


def _owner_request(app: Any) -> TranslationOwnerRequest:
    """按当前绑定项目补 owner key。

    ``/stop`` 在项目已绑定时要求请求携带同一个 ``project_key``（防止跨项目
    误停）。Agent 不暴露该参数，由桥按 ``app.state.config`` 现算。
    """
    config = getattr(getattr(app, "state", None), "config", None)
    if config is None:
        return TranslationOwnerRequest()
    try:
        paths = RenpyProjectPaths.from_config(config)
    except Exception:  # noqa: BLE001 - 配置脏时交给 /stop 的 409 语义
        paths = None
    return TranslationOwnerRequest(project_key = paths.project_key if paths is not None else None)


def _invoke(
    app: Any,
    coro_factory: Callable[[], Any],
    *,
    timeout: float,
    transform: Callable[[Any], dict],
) -> dict:
    """把协程投递到主事件循环并同步等待结果。"""
    loop = getattr(getattr(app, "state", None), "loop", None)
    if loop is None:
        return _failure("ERROR", _CONTEXT_MISSING_DETAIL)

    try:
        coro = coro_factory()
    except Exception as exc:  # noqa: BLE001 - 协程构造失败也要转成结构化结果
        return _failure("ERROR", str(exc))
    try:
        future = asyncio.run_coroutine_threadsafe(coro, loop)
    except Exception as exc:  # noqa: BLE001 - 事件循环已关闭时协程不能悬空
        coro.close()
        return _failure("ERROR", str(exc))

    try:
        return transform(future.result(timeout = timeout))
    except concurrent.futures.TimeoutError:
        future.cancel()
        return _failure("TIMEOUT", "等待主线程响应超时")
    except HTTPException as exc:
        return _failure("ERROR", str(exc.detail), status_code = exc.status_code)
    except Exception as exc:  # noqa: BLE001 - 桥接层必须把异常转成结果
        return _failure("ERROR", str(exc))


def build_pipeline_callbacks(app: Any) -> dict[str, Callable[..., dict]]:
    """返回 Agent 工具用的同步启停回调（可在后台线程调用）。"""

    def start_translation(payload: dict) -> dict:
        data = payload if isinstance(payload, dict) else {}
        # source 前置备份要等一个后台 job 结束，会长时间占住 Agent 线程。
        if str(data.get("mode") or "").strip().casefold() == "source":
            return _failure(
                "UNSUPPORTED_MODE",
                "源码备份路径耗时较长，请在翻译页手动启动",
            )
        try:
            body = _build_start_request(data)
        except Exception as exc:  # noqa: BLE001 - 模型参数不合法时给结构化失败
            return _failure("ERROR", str(exc))
        return _invoke(
            app,
            lambda: request_translation_start(app, body),
            timeout = START_TIMEOUT,
            transform = lambda response: response.model_dump(),
        )

    def stop_translation(payload: dict) -> dict:
        body = _owner_request(app)
        return _invoke(
            app,
            lambda: request_translation_stop(app, body),
            timeout = STOP_TIMEOUT,
            transform = lambda response: dict(response),
        )

    return {
        "start_translation": start_translation,
        "stop_translation": stop_translation,
    }


__all__ = ["build_pipeline_callbacks"]
