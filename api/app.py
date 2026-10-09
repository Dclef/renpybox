"""create_app() 工厂与生命周期。

sidecar（Electron 的 Python 侧）直接跑这个 app；
测试用 TestClient 无头跑，不依赖 Qt，也不需要真实项目。
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import AsyncIterator

from fastapi import FastAPI

from api.events import EventBridge
from api.hub import ConnectionHub
from api.jobs import JobManager
from api.routes import agent, glossary, jobs, platforms, proofreading, project, settings, system, translation, update, workbench, ws
from api.routes.ws import drain_loop


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from base.LogManager import LogManager
    from base.EventManager import EventManager
    from base.Version import Version
    from module.Config import Config
    from module.Engine.Engine import Engine
    from module.Localizer.Localizer import Localizer
    from module.Agent.AgentService import AgentService
    from api.agent import AgentSession

    config = Config().load()
    Localizer.set_app_language(config.app_language)
    LogManager.get().info(f"[api] RenpyBox {Version.CURRENT} 启动")

    hub = ConnectionHub()
    jobs = JobManager(publish=hub.broadcast_threadsafe)
    bridge = EventBridge(hub)

    app.state.config = config
    app.state.hub = hub
    app.state.jobs = jobs
    app.state.bridge = bridge
    app.state.app_version = Version.CURRENT
    app.state.bridge_event_names = (*bridge._events, "AGENT_UPDATE")
    app.state.agent = AgentSession(
        AgentService(config_loader=lambda: app.state.config),
        hub.broadcast_threadsafe,
    )

    # 事件总线单例要先于桥接创建，否则桥接订阅不到
    EventManager.get()
    # VersionManager 在构造时订阅检查/下载/安装事件，必须在桥接前实例化
    from base.VersionManager import VersionManager
    app.state.version_manager = VersionManager.get()
    bridge.start()

    # 翻译引擎依赖 APITester / Translator，初始化后任务接口才能用
    with contextlib.suppress(Exception):
        Engine.get().run()

    task = asyncio.create_task(drain_loop(app))

    try:
        yield
    finally:
        await asyncio.to_thread(app.state.agent.close)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        jobs.shutdown()
        bridge.stop()
        await hub.broadcast({"type": "bye"})


def create_app() -> FastAPI:
    app = FastAPI(
        title = "RenpyBox API",
        description = "RenpyBox 桌面端业务契约层（Electron sidecar）",
        version = "1",
        lifespan = lifespan,
    )

    app.include_router(system.router)
    app.include_router(update.router)
    app.include_router(agent.router)
    app.include_router(settings.router)
    app.include_router(glossary.router)
    app.include_router(platforms.router)
    app.include_router(workbench.router)
    app.include_router(proofreading.router)
    app.include_router(project.router)
    app.include_router(jobs.router)
    app.include_router(translation.router)
    app.include_router(ws.router)

    return app
