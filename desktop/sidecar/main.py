"""RenpyBox desktop sidecar —— M0 spike.

职责边界（后续 M1 落地时替换为 api/ 路由层）：
  * 复用仓库现有的 module/ 与 base/ 业务逻辑，本文件只做性能验证
  * 对外只暴露 WebSocket 单连接：数据流 + 任务进度 + 控制指令
  * 所有推送强制节流聚合，验证渲染端在高压下是否掉帧

验证目标（M0 门槛）：
  1. /health 就绪 < 1.5s
  2. 10 万行分批推送，渲染端首屏 < 300ms
  3. 推送与高并发任务期间，UI 交互响应 < 50ms，滚动稳 60fps
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

APP_VERSION = "0.0.0-spike.1"
TOTAL_ROWS = 100_000
BATCH_SIZE = 500
PUSH_INTERVAL = 0.03
PROGRESS_THROTTLE = 0.1

app = FastAPI(title="RenpyBox sidecar", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATUSES = ("pending", "translated", "reviewed")


def make_row(index: int) -> dict:
    """构造一行校对数据。行高故意不一致，用来压测虚拟列表的动态行高测量。"""
    status = STATUSES[index % 3]
    pad = "追加说明。" * (index % 4)
    return {
        "id": index,
        "key": f"dialogue_{index:06d}",
        "source": f"「这是第 {index} 句日文原文，用于模拟视觉小说的对话文本。{pad}」",
        "target": f"“这是第 {index} 句译文，用于压测虚拟列表的动态行高。{pad}”" if status != "pending" else "",
        "status": status,
    }


@app.get("/health")
def health() -> dict:
    """Electron 主进程轮询这个接口决定何时开窗。"""
    return {"ok": True, "pid": os.getpid(), "version": APP_VERSION, "ts": time.time()}


jobs: dict[str, dict] = {}


async def safe_send(ws: WebSocket, payload: dict) -> bool:
    """窗口被关掉时推送会抛Disconnect，这里统一吞掉，避免刷栈。"""
    try:
        await ws.send_text(json.dumps(payload, ensure_ascii=False))
        return True
    except Exception:  # noqa: BLE001
        return False


async def stream_rows(ws: WebSocket, total: int, batch: int) -> None:
    started = time.perf_counter()
    sent = 0
    while sent < total:
        chunk = [make_row(i) for i in range(sent, min(sent + batch, total))]
        sent += len(chunk)
        if not await safe_send(ws, {"type": "rows", "rows": chunk, "sent": sent, "total": total}):
            return
        # 模拟真实解析/IO 节奏，同时给渲染端施加背压
        await asyncio.sleep(PUSH_INTERVAL)
    await safe_send(
        ws,
        {
            "type": "rows_done",
            "total": total,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        },
    )


async def run_job(ws: WebSocket, job_id: str, total: int, concurrency: int) -> None:
    """模拟高并发翻译任务：8 个 worker 持续产出，进度节流推送。"""
    state = jobs[job_id]
    done = 0

    async def worker(quota: int) -> None:
        nonlocal done
        for _ in range(quota):
            if state["cancelled"]:
                return
            await asyncio.sleep(random.uniform(0.05, 0.2))  # 模拟 LLM 往返
            done += 1

    workers = [asyncio.create_task(worker(total // concurrency)) for _ in range(concurrency)]
    last_sent = 0.0
    while done < total:
        await asyncio.sleep(0.02)
        now = time.perf_counter()
        if state["cancelled"]:
            await ws.send_text(json.dumps({"type": "job_cancelled", "job_id": job_id, "done": done}))
            break
        if now - last_sent >= PROGRESS_THROTTLE:
            last_sent = now
            await ws.send_text(
                json.dumps({"type": "job_progress", "job_id": job_id, "done": done, "total": total})
            )
    await asyncio.gather(*workers, return_exceptions=True)
    if not state["cancelled"]:
        await ws.send_text(json.dumps({"type": "job_done", "job_id": job_id, "done": done, "total": total}))


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            kind = msg.get("type")

            if kind == "load_rows":
                await stream_rows(ws, int(msg.get("total", TOTAL_ROWS)), int(msg.get("batch", BATCH_SIZE)))

            elif kind == "start_job":
                job_id = uuid.uuid4().hex[:8]
                jobs[job_id] = {"cancelled": False}
                await ws.send_text(json.dumps({"type": "job_started", "job_id": job_id}))
                asyncio.create_task(
                    run_job(ws, job_id, int(msg.get("total", 800)), int(msg.get("concurrency", 8)))
                )

            elif kind == "cancel_job":
                job = jobs.get(msg.get("job_id", ""))
                if job:
                    job["cancelled"] = True

            elif kind == "ping":
                await ws.send_text(json.dumps({"type": "pong", "ts": time.time()}))

            else:
                await ws.send_text(json.dumps({"type": "error", "message": f"unknown type: {kind}"}))
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        try:
            await ws.send_text(json.dumps({"type": "error", "message": repr(exc)}))
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=9712, app_dir=os.path.dirname(__file__))