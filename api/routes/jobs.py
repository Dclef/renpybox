"""任务查询与取消（长任务的启动接口在各业务域里）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.jobs import JobManager

router = APIRouter(prefix = "/api/jobs", tags = ["jobs"])


def _manager(request: Request) -> JobManager:
    return request.app.state.jobs


@router.get("")
def list_jobs(request: Request) -> dict:
    return {"jobs": _manager(request).snapshots()}


@router.get("/{job_id}")
def read_job(request: Request, job_id: str) -> dict:
    snapshot = _manager(request).snapshot(job_id)
    if snapshot is None:
        raise HTTPException(status_code = 404, detail = "任务不存在")
    return snapshot


@router.post("/{job_id}/cancel")
async def cancel_job(request: Request, job_id: str) -> dict:
    manager = _manager(request)
    if not manager.cancel(job_id):
        raise HTTPException(status_code = 409, detail = "任务已结束或不存在")
    return manager.snapshot(job_id) or {}