"""统一任务模型。

Electron 侧的长任务（翻译、提取、校对重跑、批量替换）统一语义：

    POST 启动→ 返回 job_id
    WS   订阅 → 收到 {"type": "job", ...} 的进度与终态
    POST /api/jobs/{id}/cancel → 取消

进度事件由 EventManager 的合并窗口负责节流（TRANSLATION_UPDATE 200ms），
任务级进度走这条独立通道，两者互不阻塞。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL = {JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED}


@dataclass
class Job:
    id: str
    kind: str
    status: JobStatus = JobStatus.PENDING
    total: int = 0
    done: int = 0
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)

    def snapshot(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("cancel_event", None)
        data["status"] = self.status.value
        data["progress"] = (self.done / self.total) if self.total else 0.0
        return data


class JobManager:
    """进程内任务表。任务体由调用方提供的协程函数执行。"""

    def __init__(self, limit: int = 64) -> None:
        self._jobs: dict[str, Job] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._order: list[str] = []
        self._limit = limit

    def create(self, kind: str, total: int = 0) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, total=total)
        self._jobs[job.id] = job
        self._order.append(job.id)
        self._evict()
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return [self._jobs[j] for j in reversed(self._order) if j in self._jobs]

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.status in TERMINAL:
            return False
        job.cancel_event.set()
        job.status = JobStatus.CANCELLED
        job.updated_at = time.time()
        return True

    def snapshot(self, job_id: str) -> dict[str, Any] | None:
        job = self._jobs.get(job_id)
        return job.snapshot() if job else None

    def snapshots(self) -> list[dict[str, Any]]:
        return [j.snapshot() for j in self.list()]

    async def run(
        self,
        job_id: str,
        worker: Callable[[Job], Coroutine[Any, Any, Any]],
    ) -> None:
        """把任务体跑起来，异常与取消都收敛成终态，不让asyncio 留下悬挂任务。"""
        job = self._jobs[job_id]
        job.status = JobStatus.RUNNING
        job.updated_at = time.time()

        async def runner() -> None:
            try:
                if job.cancel_event.is_set():
                    job.status = JobStatus.CANCELLED
                else:
                    job.result = await worker(job)
                    job.status = JobStatus.DONE
            except asyncio.CancelledError:
                job.status = JobStatus.CANCELLED
            except Exception as exc:  # noqa: BLE001
                job.status = JobStatus.FAILED
                job.error = f"{type(exc).__name__}: {exc}"
            finally:
                job.updated_at = time.time()
                self._tasks.pop(job_id, None)

        self._tasks[job_id] = asyncio.create_task(runner())

    def _evict(self) -> None:
        while len(self._order) > self._limit:
            oldest = self._order[0]
            job = self._jobs.get(oldest)
            if job is not None and job.status not in TERMINAL:
                break
            self._order.pop(0)
            self._jobs.pop(oldest, None)

    def shutdown(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
        self._tasks.clear()