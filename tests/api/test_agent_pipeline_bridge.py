import asyncio
import threading
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api import pipeline_bridge
from api.pipeline_bridge import build_pipeline_callbacks
from api.schemas import TranslationStartResponse


@pytest.fixture
def running_loop():
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target = loop.run_forever, daemon = True)
    thread.start()

    def shutdown() -> None:
        async def _drain() -> None:
            tasks = [
                task
                for task in asyncio.all_tasks()
                if task is not asyncio.current_task()
            ]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions = True)

        asyncio.run_coroutine_threadsafe(_drain(), loop).result(timeout = 5)
        loop.call_soon_threadsafe(loop.stop)

    try:
        yield loop
    finally:
        shutdown()
        thread.join(timeout = 5)
        if not thread.is_alive():
            loop.close()


def _app(loop = None, config = None) -> SimpleNamespace:
    return SimpleNamespace(state = SimpleNamespace(loop = loop, config = config))


def test_source_mode_is_rejected_before_dispatch(monkeypatch) -> None:
    calls: list[object] = []

    async def unexpected(_app, _body):
        calls.append(True)
        raise AssertionError("source mode must not reach the main loop")

    monkeypatch.setattr(pipeline_bridge, "request_translation_start", unexpected)
    callbacks = build_pipeline_callbacks(_app())

    result = callbacks["start_translation"]({
        "mode": "source",
        "status": "untranslated",
    })

    assert result == {
        "accepted": False,
        "reason": "UNSUPPORTED_MODE",
        "detail": "源码备份路径耗时较长，请在翻译页手动启动",
    }
    assert calls == []


def test_start_timeout_cancels_and_converts(monkeypatch, running_loop) -> None:
    async def slow_start(_app, _body):
        await asyncio.sleep(10)

    monkeypatch.setattr(pipeline_bridge, "request_translation_start", slow_start)
    monkeypatch.setattr(pipeline_bridge, "START_TIMEOUT", 0.05)
    callbacks = build_pipeline_callbacks(_app(running_loop))

    result = callbacks["start_translation"]({"status": "TRANSLATED"})

    assert result == {
        "accepted": False,
        "reason": "TIMEOUT",
        "detail": "等待主线程响应超时",
    }


def test_http_exception_is_converted(monkeypatch, running_loop) -> None:
    async def failing_stop(_app, _body):
        raise HTTPException(status_code = 409, detail = "当前没有正在运行的翻译任务")

    monkeypatch.setattr(pipeline_bridge, "request_translation_stop", failing_stop)
    callbacks = build_pipeline_callbacks(_app(running_loop))

    result = callbacks["stop_translation"]({})

    assert result == {
        "accepted": False,
        "reason": "ERROR",
        "detail": "当前没有正在运行的翻译任务",
        "status_code": 409,
    }


def test_start_success_returns_model_dump(monkeypatch, running_loop) -> None:
    captured: dict = {}

    async def fake_start(_app, body):
        captured["status"] = body.status
        captured["preflight_confirmed"] = body.preflight_confirmed
        captured["unknown"] = hasattr(body, "unknown_key")
        return TranslationStartResponse(
            accepted = True,
            request_id = "req-1",
            reason = "STARTED",
            detail = "已受理",
            stage = "translating",
        )

    monkeypatch.setattr(pipeline_bridge, "request_translation_start", fake_start)
    callbacks = build_pipeline_callbacks(_app(running_loop))

    result = callbacks["start_translation"]({
        "status": "untranslated",
        "preflight_confirmed": True,
        "unknown_key": "ignored",
    })

    assert result["accepted"] is True
    assert result["request_id"] == "req-1"
    assert result["stage"] == "translating"
    # 小写默认值被规范化为引擎枚举值，未知参数被丢弃。
    assert captured == {
        "status": "UNTRANSLATED",
        "preflight_confirmed": True,
        "unknown": False,
    }


def test_start_with_agent_platform_source_overrides_platform(monkeypatch, running_loop) -> None:
    captured: dict = {}

    async def fake_start(_app, body):
        captured["platform_id"] = body.platform_id
        return TranslationStartResponse(
            accepted = True,
            request_id = "req-2",
            reason = "STARTED",
            detail = "已受理",
            stage = "translating",
        )

    monkeypatch.setattr(pipeline_bridge, "request_translation_start", fake_start)
    callbacks = build_pipeline_callbacks(_app(running_loop, SimpleNamespace(agent_platform = 3)))

    result = callbacks["start_translation"]({"platform_source": "agent"})

    assert result["accepted"] is True
    # 只改写本轮快照的平台，不触碰翻译页设置
    assert captured["platform_id"] == 3


def test_start_with_agent_platform_source_requires_agent_platform(running_loop) -> None:
    callbacks = build_pipeline_callbacks(_app(running_loop, SimpleNamespace(agent_platform = -1)))

    result = callbacks["start_translation"]({"platform_source": "agent"})

    assert result["accepted"] is False
    assert result["reason"] == "ERROR"
    assert "Agent" in result["detail"]


def test_stop_success_returns_stop_dict(monkeypatch, running_loop) -> None:
    async def fake_stop(_app, _body):
        return {"ok": True, "status": "STOPPING"}

    monkeypatch.setattr(pipeline_bridge, "request_translation_stop", fake_stop)
    callbacks = build_pipeline_callbacks(_app(running_loop))

    result = callbacks["stop_translation"]({})

    assert result == {"ok": True, "status": "STOPPING"}


def test_stop_injects_bound_project_key(monkeypatch, running_loop, tmp_path) -> None:
    from module.Config import Config
    from module.Renpy.ProjectPaths import RenpyProjectPaths

    root = tmp_path / "MyGame"
    (root / "game" / "tl" / "chinese").mkdir(parents = True)
    config = Config()
    config.renpy_project_path = str(root)
    config.renpy_game_folder = str(root / "game")
    paths = RenpyProjectPaths.from_config(config)
    assert paths is not None

    captured: dict = {}

    async def fake_stop(_app, body):
        captured["project_key"] = body.project_key if body is not None else None
        return {"ok": True, "status": "STOPPING"}

    monkeypatch.setattr(pipeline_bridge, "request_translation_stop", fake_stop)
    callbacks = build_pipeline_callbacks(_app(running_loop, config))

    result = callbacks["stop_translation"]({})

    assert result == {"ok": True, "status": "STOPPING"}
    assert captured["project_key"] == paths.project_key


def test_missing_loop_returns_error_without_crashing() -> None:
    callbacks = build_pipeline_callbacks(_app())

    result = callbacks["stop_translation"]({})

    assert result["accepted"] is False
    assert result["reason"] == "ERROR"
    assert "主事件循环" in result["detail"]
