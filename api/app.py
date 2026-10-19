"""create_app() 工厂与生命周期。

sidecar（Electron 的 Python 侧）直接跑这个 app；

"""

from __future__ import annotations

import asyncio
import contextlib
from typing import AsyncIterator

from fastapi import FastAPI

from api.events import EventBridge
from api.hub import ConnectionHub
from api.jobs import JobManager
from api.routes import agent, android_build, archive, asset_suite, error_repair, extract_json, extract_to_tl, font_tools, formatter, game_mod, glossary, hook_translate, html_import, jobs, language_tools, lexicon, onekey, platforms, proofreading, project, rpy_extraction, settings, system, translation, translation_reuse, update, workbench, ws
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
    from module.Agent.AgentSessionStore import AgentSessionStore
    from api.agent import AgentSession
    from api.pipeline_bridge import build_pipeline_callbacks

    config = Config().load()
    Localizer.set_app_language(config.app_language)
    LogManager.get().info(f"[api] RenpyBox {Version.CURRENT} 启动")

    # 与 Qt5 接口页一致：首次启动播种内置接口并做字段归一化，否则全新安装
    # 会停在空接口列表，用户会以为接口「丢了」。
    try:
        from module.Project.PlatformDefaults import seed_default_platforms

        if seed_default_platforms(config):
            LogManager.get().info("[api] 已补齐默认接口配置")
    except Exception as error:
        LogManager.get().warning(f"[api] 默认接口初始化失败，保留原配置: {error}")

    hub = ConnectionHub()
    jobs = JobManager(publish=hub.broadcast_threadsafe)
    bridge = EventBridge(hub)

    app.state.config = config
    app.state.hub = hub
    app.state.jobs = jobs
    app.state.bridge = bridge
    app.state.app_version = Version.CURRENT
    app.state.bridge_event_names = (*bridge._events, "AGENT_UPDATE")
    # Agent 工具跑在后台线程，启停翻译要投递回这个主事件循环。
    app.state.loop = asyncio.get_running_loop()
    app.state.agent = AgentSession(
        AgentService(
            config_loader = lambda: app.state.config,
            pipeline_callbacks = build_pipeline_callbacks(app),
        ),
        hub.broadcast_threadsafe,
        store=AgentSessionStore(),
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
    app.include_router(archive.router)
    app.include_router(asset_suite.router)
    app.include_router(lexicon.router)
    app.include_router(onekey.router)
    app.include_router(language_tools.router)
    app.include_router(font_tools.router)
    app.include_router(rpy_extraction.router)
    app.include_router(extract_to_tl.router)
    app.include_router(extract_json.router)
    app.include_router(hook_translate.router)
    app.include_router(error_repair.router)
    app.include_router(translation_reuse.router)
    app.include_router(formatter.router)
    app.include_router(android_build.router)
    app.include_router(html_import.router)
    app.include_router(game_mod.router)
    app.include_router(jobs.router)
    app.include_router(translation.router)
    app.include_router(ws.router)

    return app
