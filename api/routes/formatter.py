"""代码格式化：对齐 Qt FormatterPage，后台任务 + 原子写。"""

from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from api.jobs import Job
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Extract.GameExtractionRules import project_key as derive_project_key
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Tool.Formatter import Formatter
from module.Tool.LexicalFs import lexical_abs, require_no_link_escape

router = APIRouter(prefix="/api/formatter", tags=["formatter"])

KIND_FORMAT = "formatter_format"
KINDS = (KIND_FORMAT,)
_BUSY = "已有任务正在运行或收尾，请稍后再试"


def _norm(value: str) -> str:
    return os.path.normcase(os.path.abspath(value)) if value else ""


def _project_identity(config: Any) -> tuple[str, ...]:
    return tuple(
        _norm(str(getattr(config, field, "") or ""))
        for field in (
            "renpy_project_path",
            "renpy_game_folder",
            "renpy_tl_folder",
            "input_folder",
            "output_folder",
        )
    )


class FormatBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    folder: str = Field(min_length=1, pattern=r"\S")
    project_key: str = ""
    owner_project_key: str = ""
    preserve_comments: bool = True
    fix_indent: bool = True
    remove_trailing: bool = True
    confirm: bool = False


def current_paths(config: Any) -> RenpyProjectPaths | None:
    return RenpyProjectPaths.from_config(config)


def _resolve_folder(
    config: Any,
    *,
    folder: str,
    body_project_key: str,
    body_owner_key: str,
) -> tuple[str, Path, str, tuple[str, ...] | None]:
    bound = current_paths(config)
    owner_key = bound.project_key if bound is not None else ""
    owner_identity = _project_identity(config) if bound is not None else None
    try:
        path = require_no_link_escape(folder, label="格式化目录")
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if path.parent == path:
        raise HTTPException(status_code=400, detail="不能对磁盘根目录操作")
    target_key = derive_project_key(path)
    body_key = str(body_project_key or "").strip()
    body_owner = str(body_owner_key or "").strip()
    if body_key and body_key != target_key:
        raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    if owner_key:
        if body_owner != owner_key:
            raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    elif body_owner:
        raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    return target_key, path, owner_key, owner_identity


def _latest_job(request: Request, project_key: str) -> Job | None:
    return next(
        (
            job for job in request.app.state.jobs.list()
            if job.kind in KINDS and isinstance(job.result, dict)
            and job.result.get("project_key") == project_key
        ),
        None,
    )


def _acquire_engine() -> Engine:
    engine = Engine.get()
    if not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
        raise HTTPException(status_code=409, detail=_BUSY)
    return engine


@router.get("")
def read_status(request: Request, folder: str = Query(default="")) -> dict:
    with CacheManager.LOCK:
        config = request.app.state.config
        bound = current_paths(config)
        owner_key = bound.project_key if bound is not None else ""
        raw = str(folder or "").strip()
        project_key = ""
        folder_path = ""
        if raw:
            path = lexical_abs(raw)
            if path.is_dir():
                project_key = derive_project_key(path)
                folder_path = str(path)
            else:
                folder_path = raw
    job = _latest_job(request, project_key) if project_key else None
    return {
        "project_key": project_key,
        "owner_project_key": owner_key,
        "folder": folder_path,
        "job": job.snapshot() if job else None,
    }


@router.post("/format")
async def start_format(request: Request, body: FormatBody) -> dict:
    """格式化目录下全部 .rpy；success_count=处理数，written=实际改写。"""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="格式化会直接改写文件且无自动备份，需要 confirm=true")
    with CacheManager.LOCK:
        project_key, folder, owner_key, owner_identity = _resolve_folder(
            request.app.state.config,
            folder=body.folder,
            body_project_key=body.project_key,
            body_owner_key=body.owner_project_key,
        )
    snapshot = str(folder)
    fix_indent = body.fix_indent
    remove_trailing = body.remove_trailing

    def compute(check_cancel, progress, should_stop, touch_result, owner_still):
        del should_stop, touch_result
        check_cancel()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        progress("正在格式化", 20)
        formatter = Formatter()
        success_count = formatter.format_folder(
            snapshot,
            preserve_comments=True,
            fix_indent=fix_indent,
            remove_trailing=remove_trailing,
            encoding="utf-8",
        )
        check_cancel()
        if not owner_still():
            # 无写盘副作用或已写完：若已写则如实返回
            modified = int(getattr(formatter, "last_modified_count", 0) or 0)
            if modified <= 0:
                raise RuntimeError("项目已切换，未执行操作")
        failed = list(formatter.last_failed_files)
        modified = int(getattr(formatter, "last_modified_count", 0) or 0)
        total = success_count + len(failed)
        partial = bool(failed)
        progress("格式化完成", 100)
        message = f"成功处理 {success_count} 个 RPY"
        if partial:
            message += f"；{len(failed)} 个失败"
        return {
            "success": not partial or success_count > 0,
            "partial": partial,
            "action": "format",
            "written": modified > 0,
            "success_count": success_count,
            "modified_count": modified,
            "failed_files": failed,
            "total_files": total,
            "folder": snapshot,
            "message": message,
        }

    return await _start_job(
        request,
        kind=KIND_FORMAT,
        project_key=project_key,
        owner_project_key=owner_key,
        message="准备格式化",
        owner_identity=owner_identity,
        seed={"action": "format", "folder": snapshot, "written": False},
        compute=compute,
    )


async def _start_job(
    request: Request,
    *,
    kind: str,
    project_key: str,
    owner_project_key: str,
    message: str,
    seed: dict[str, Any],
    compute: Callable[..., dict],
    owner_identity: tuple[str, ...] | None = None,
) -> dict:
    engine = _acquire_engine()
    manager = request.app.state.jobs
    try:
        job = manager.create(kind, total=100, cooperative_cancel=True)
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        raise
    job.result = {
        "project_key": project_key,
        "owner_project_key": owner_project_key,
        "message": message,
        "written": False,
        "worker_active": True,
        **seed,
    }
    loop = asyncio.get_running_loop()
    identity = owner_identity
    folder_snapshot = str(seed.get("folder") or "")
    frozen_owner_key = owner_project_key
    frozen_target_key = project_key

    def owner_still() -> bool:
        with CacheManager.LOCK:
            live = request.app.state.config
            bound = current_paths(live)
            live_owner = bound.project_key if bound is not None else ""
        if frozen_owner_key:
            if live_owner != frozen_owner_key:
                return False
            if identity is not None and _project_identity(live) != identity:
                return False
        elif live_owner:
            return False
        if folder_snapshot and derive_project_key(Path(folder_snapshot)) != frozen_target_key:
            return False
        return True

    def check_cancel() -> None:
        if job.cancel_event.is_set():
            raise asyncio.CancelledError()

    def should_stop() -> bool:
        return job.cancel_event.is_set()

    def publish(message_text: str, percent: int) -> None:
        if isinstance(job.result, dict):
            job.result["message"] = message_text
        manager.progress(job.id, done=max(0, min(100, int(percent))), total=100)

    def progress(message_text: str, percent: int = 0) -> None:
        loop.call_soon_threadsafe(lambda: publish(message_text, percent))

    def touch_result(patch: dict[str, Any]) -> None:
        # 同步写入 result，避免取消竞态读到旧的 written=false
        if isinstance(job.result, dict) and job.result.get("worker_active"):
            job.result.update(patch)
        loop.call_soon_threadsafe(lambda: manager.progress(job.id))

    def run_compute() -> dict:
        check_cancel()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        result = compute(check_cancel, progress, should_stop, touch_result, owner_still)
        if isinstance(job.result, dict) and job.result.get("worker_active"):
            job.result.update(result)
        return result

    async def worker(_: Job) -> dict:
        try:
            check_cancel()
            future = loop.run_in_executor(None, run_compute)
            try:
                result = await asyncio.shield(future)
            except asyncio.CancelledError:
                job.cancel_event.set()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.shield(future)
                if isinstance(job.result, dict) and job.result.get("written"):
                    job.result.setdefault("partial", True)
                    job.result.setdefault("success", False)
                    job.result.setdefault("message", "任务已取消（已保留写入结果）")
                    manager.progress(job.id, done=100, total=100)
                    return job.result
                raise
            if isinstance(job.result, dict):
                job.result.update(result)
                if job.cancel_event.is_set() and job.result.get("written"):
                    job.result.setdefault("partial", True)
                    job.result["success"] = False
                    job.result.setdefault("message", "任务已取消（已保留写入结果）")
                    manager.progress(job.id, done=100, total=100)
                    return job.result
                if job.cancel_event.is_set():
                    job.result["message"] = "任务已取消"
                    raise asyncio.CancelledError()
                if job.result.get("success") is False and not job.result.get("partial"):
                    raise RuntimeError(job.result.get("message") or "格式化失败")
            job.cancel_event.clear()
            manager.progress(job.id, done=100, total=100)
            return job.result
        except asyncio.CancelledError:
            if isinstance(job.result, dict) and job.result.get("written"):
                job.result.setdefault("partial", True)
                job.result["success"] = False
                job.result.setdefault("message", "任务已取消（已保留写入结果）")
                manager.progress(job.id, done=100, total=100)
                return job.result
            if isinstance(job.result, dict):
                job.result["message"] = "任务已取消"
            raise
        except Exception as exc:
            if isinstance(job.result, dict):
                job.result["message"] = str(exc)
            raise
        finally:
            if isinstance(job.result, dict):
                job.result["worker_active"] = False
            engine.release_status(Engine.Status.TESTING)

    try:
        await manager.run(job.id, worker)
    except BaseException:
        if isinstance(job.result, dict):
            job.result["worker_active"] = False
        engine.release_status(Engine.Status.TESTING)
        raise
    return {"job": job.snapshot()}
