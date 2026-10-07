"""RenpyBox desktop sidecar —— Electron 的 Python 侧进程。

两种模式：
  * api 模式（默认）：挂载仓库里的 api/ 契约层，暴露真实业务逻辑
  * bench 模式（--bench）：内置 10 万行生成器 + 高并发任务模拟，
    用于跑虚拟表格性能门禁，不依赖真实项目

api 模式复用项目自身解释器（Python 3.10，全套依赖已在其中）：
PyQt5 / qfluentwidgets / openpyxl / tiktoken / unrpa / opencc / translators 都可用。
module/ 与 base/ 已解除 Qt 依赖（见 commit 7478722），sidecar 不需要 QApplication。
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware


BENCH = "--bench" in sys.argv

if BENCH:
    app = FastAPI(title = "RenpyBox sidecar (bench)")
    app.add_middleware(
        CORSMiddleware,
        allow_origins = ["*"],
        allow_methods = ["*"],
        allow_headers = ["*"],
    )

    TOTAL_ROWS = 100_000
    BATCH_SIZE = 500
    PUSH_INTERVAL = 0.03
    PROGRESS_THROTTLE = 0.1
    STATUSES = ("pending", "translated", "reviewed")

    def make_row(index: int) -> dict:
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
    def bench_health() -> dict:
        return {"ok": True, "pid": os.getpid(), "mode": "bench", "ts": time.time()}

    jobs: dict[str, dict] = {}

    async def safe_send(ws: WebSocket, payload: dict) -> bool:
        try:
            await ws.send_text(json.dumps(payload, ensure_ascii = False))
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
            await asyncio.sleep(PUSH_INTERVAL)
        await safe_send(
            ws,
            {"type": "rows_done", "total": total, "elapsed_ms": round((time.perf_counter() - started) * 1000)},
        )

    async def run_job(ws: WebSocket, job_id: str, total: int, concurrency: int) -> None:
        state = jobs[job_id]
        done = 0

        async def worker(quota: int) -> None:
            nonlocal done
            for _ in range(quota):
                if state["cancelled"]:
                    return
                await asyncio.sleep(random.uniform(0.05, 0.2))
                done += 1

        workers = [asyncio.create_task(worker(total // concurrency)) for _ in range(concurrency)]
        last_sent = 0.0
        while done < total:
            await asyncio.sleep(0.02)
            now = time.perf_counter()
            if state["cancelled"]:
                await safe_send(ws, {"type": "job_cancelled", "job_id": job_id, "done": done})
                break
            if now - last_sent >= PROGRESS_THROTTLE:
                last_sent = now
                await safe_send(ws, {"type": "job_progress", "job_id": job_id, "done": done, "total": total})
        await asyncio.gather(*workers, return_exceptions = True)
        if not state["cancelled"]:
            await safe_send(ws, {"type": "job_done", "job_id": job_id, "done": done, "total": total})

    @app.websocket("/ws")
    async def bench_ws(ws: WebSocket) -> None:
        await ws.accept()
        try:
            while True:
                msg = json.loads(await ws.receive_text())
                kind = msg.get("type")

                if kind == "load_rows":
                    await stream_rows(ws, int(msg.get("total", TOTAL_ROWS)), int(msg.get("batch", BATCH_SIZE)))

                elif kind == "start_job":
                    import uuid

                    job_id = uuid.uuid4().hex[:8]
                    jobs[job_id] = {"cancelled": False}
                    await safe_send(ws, {"type": "job_started", "job_id": job_id})
                    asyncio.create_task(
                        run_job(ws, job_id, int(msg.get("total", 800)), int(msg.get("concurrency", 8)))
                    )

                elif kind == "cancel_job":
                    job = jobs.get(msg.get("job_id", ""))
                    if job:
                        job["cancelled"] = True

                elif kind == "ping":
                    await safe_send(ws, {"type": "pong", "ts": time.time()})

                else:
                    await safe_send(ws, {"type": "error", "message": f"unknown type: {kind}"})
        except WebSocketDisconnect:
            pass
        except Exception:  # noqa: BLE001
            pass

else:
    # api 模式：把仓库根目录加进 sys.path 后挂载真实契约层
    REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)

    from api.app import create_app  # noqa: E402

    app = create_app()
    app.add_middleware(
        CORSMiddleware,
        allow_origins = ["*"],
        allow_methods = ["*"],
        allow_headers = ["*"],
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host = "127.0.0.1", port = int(os.environ.get("RENPYBOX_SIDECAR_PORT", "9712")))