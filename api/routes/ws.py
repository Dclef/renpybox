"""WebSocket 端点：一条连接承载数据流、任务快照与控制指令。

对齐 DeepSeek Harness 的做法（它用 ws 而非 SSE）：
  · 业务事件推送（由 events.EventBridge 转发）
  · 任务状态查询 / 取消
  · 订阅过滤（客户端可以只关心自己需要的几类事件）
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.schemas import WsCommand

router = APIRouter(tags = ["ws"])

DRAIN_INTERVAL = 0.016
# 没有 WS 客户端时，把排空频率降下来，别白烧CPU
IDLE_DRAIN_INTERVAL = 0.2


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    hub = websocket.app.state.hub
    jobs = websocket.app.state.jobs
    await hub.add(websocket)

    try:
        await websocket.send_text(json.dumps({
            "type": "hello",
            "app_version": websocket.app.state.app_version,
            "events": websocket.app.state.bridge_event_names,
        }, ensure_ascii = False))

        while True:
            raw = await websocket.receive_text()
            try:
                command = WsCommand.model_validate_json(raw)
            except Exception:
                await hub.send_to(websocket, {"type": "error", "message": "指令格式非法"})
                continue

            if command.type == "ping":
                await hub.send_to(websocket, {"type": "pong"})

            elif command.type == "subscribe":
                await hub.add(websocket, set(command.events) if command.events else None)
                await hub.send_to(websocket, {
                    "type": "subscribed",
                    "events": sorted(command.events) if command.events else None,
                })

            elif command.type == "job.get":
                snapshot = jobs.snapshot(command.job_id) if command.job_id else None
                await hub.send_to(websocket, {"type": "job", "job": snapshot})

            elif command.type == "job.list":
                await hub.send_to(websocket, {"type": "job", "jobs": jobs.snapshots()})

            elif command.type == "job.cancel":
                ok = jobs.cancel(command.job_id) if command.job_id else False
                await hub.send_to(websocket, {
                    "type": "job",
                    "job": jobs.snapshot(command.job_id) if command.job_id else None,
                    "cancelled": ok,
                })

            else:
                await hub.send_to(websocket, {
                    "type": "error",
                    "message": f"未知指令：{command.type}",
                })

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await hub.remove(websocket)


async def drain_loop(app) -> None:
    """周期性排空事件总线。

    EventManager 已解除 Qt 依赖，emit 只入队；必须有人调用 drain。
    有客户端连接时按 16ms 走一帧，空闲时降到 200ms。
    """
    from base.EventManager import EventManager

    while True:
        EventManager.drain_all()
        await asyncio.sleep(DRAIN_INTERVAL if app.state.hub.size else IDLE_DRAIN_INTERVAL)