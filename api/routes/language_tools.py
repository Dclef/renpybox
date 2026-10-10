"""语言入口与默认语言：只操作当前绑定项目，写入走协作取消任务。"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from api.jobs import Job
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Tool.LanguageTools import (
    DEFAULT_SCRIPT_NAME,
    HOOK_NAME,
    LanguageToolsError,
    contained_game,
    describe_paths,
    ensure_file_target,
    ensure_hook_resource,
    ensure_tl,
    install_default_language,
    install_language_entrance,
    render_default_script,
)

router = APIRouter(prefix="/api/language-tools", tags=["language-tools"])

KINDS = ("language_entrance", "language_default")
_BUSY = "已有任务正在运行或收尾，请稍后再试"


class EntranceBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    confirm: bool = False


class DefaultBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    language: str = ""
    confirm: bool = False


def current_paths(config: Any) -> RenpyProjectPaths | None:
    return RenpyProjectPaths.from_config(config)


def _http(exc: LanguageToolsError, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail=str(exc))


def _bound_paths(config: Any) -> RenpyProjectPaths:
    paths = current_paths(config)
    if paths is None or not paths.game_dir.is_dir():
        raise HTTPException(status_code=400, detail="未绑定游戏项目")
    return paths


def _match_project(body_key: str, paths: RenpyProjectPaths) -> str:
    if not str(body_key or "").strip():
        raise HTTPException(status_code=400, detail="project_key 必填")
    if body_key != paths.project_key:
        raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    return paths.project_key


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


def _prepare_target(paths: RenpyProjectPaths, name: str, *, language: str | None = None) -> str:
    try:
        game = contained_game(paths)
        if language is not None:
            ensure_tl(game, language)
            render_default_script(language)
        else:
            ensure_hook_resource()
        return str(ensure_file_target(game, name))
    except LanguageToolsError as exc:
        raise _http(exc) from exc


@router.get("")
def read_language_tools(request: Request) -> dict:
    """返回绑定项目的语言工具状态，以及该项目最近一次任务。"""
    with CacheManager.LOCK:
        paths = _bound_paths(request.app.state.config)
        try:
            payload = describe_paths(paths)
        except LanguageToolsError as exc:
            raise _http(exc) from exc
        project_key = paths.project_key
    job = _latest_job(request, project_key)
    payload["job"] = job.snapshot() if job else None
    return payload


@router.post("/entrance")
async def write_entrance(request: Request, body: EntranceBody) -> dict:
    """确认后把语言入口写入当前项目的 game 目录。"""
    _require_key_and_confirm(body.project_key, body.confirm, HOOK_NAME)
    with CacheManager.LOCK:
        paths = _bound_paths(request.app.state.config)
        project_key = _match_project(body.project_key, paths)
        target = _prepare_target(paths, HOOK_NAME)
        snapshot = str(paths.project_root)
    return await _start_job(
        request,
        kind="language_entrance",
        action="entrance",
        project_key=project_key,
        target=target,
        language=None,
        message="准备写入语言入口",
        operation=lambda: install_language_entrance(snapshot),
    )


@router.post("/default")
async def write_default(request: Request, body: DefaultBody) -> dict:
    """确认后为当前项目写入默认语言脚本。"""
    _require_key_and_confirm(body.project_key, body.confirm, DEFAULT_SCRIPT_NAME)
    with CacheManager.LOCK:
        paths = _bound_paths(request.app.state.config)
        project_key = _match_project(body.project_key, paths)
        target = _prepare_target(paths, DEFAULT_SCRIPT_NAME, language=body.language)
        snapshot = str(paths.project_root)
    return await _start_job(
        request,
        kind="language_default",
        action="default",
        project_key=project_key,
        target=target,
        language=body.language,
        message="准备写入默认语言",
        operation=lambda: install_default_language(snapshot, body.language),
    )


def _require_key_and_confirm(project_key: str, confirm: bool, filename: str) -> None:
    if not str(project_key or "").strip():
        raise HTTPException(status_code=400, detail="project_key 必填")
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail=f"写入将覆盖 {filename}，需要 confirm=true",
        )


async def _start_job(
    request: Request,
    *,
    kind: str,
    action: str,
    project_key: str,
    target: str,
    language: str | None,
    message: str,
    operation: Callable[[], dict],
) -> dict:
    engine = _acquire_engine()
    manager = request.app.state.jobs
    try:
        job = manager.create(kind, total=1, cooperative_cancel=True)
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        raise
    job.result = {
        "project_key": project_key,
        "action": action,
        "path": target,
        "message": message,
        "written": False,
        "worker_active": True,
        "language": language,
    }
    loop = asyncio.get_running_loop()

    def project_still() -> bool:
        with CacheManager.LOCK:
            current = current_paths(request.app.state.config)
        return current is not None and current.project_key == project_key

    def compute() -> dict:
        # 线程开始后先核对取消和项目，不一致就不写；原子写一旦开始则由写入函数收尾。
        if job.cancel_event.is_set():
            raise asyncio.CancelledError()
        if not project_still():
            raise RuntimeError("项目已切换，未写入")
        if job.cancel_event.is_set():
            raise asyncio.CancelledError()
        result = operation()
        if isinstance(job.result, dict) and job.result.get("worker_active"):
            job.result.update(result)
        return result

    async def worker(_: Job) -> dict:
        try:
            if job.cancel_event.is_set():
                raise asyncio.CancelledError()
            future = loop.run_in_executor(None, compute)
            try:
                result = await asyncio.shield(future)
            except asyncio.CancelledError:
                job.cancel_event.set()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.shield(future)
                raise
            if isinstance(job.result, dict):
                job.result.update(result)
                if job.cancel_event.is_set():
                    job.result["message"] = "任务已取消"
                    raise asyncio.CancelledError()
            manager.progress(job.id, done=1, total=1)
            return job.result
        except asyncio.CancelledError:
            if isinstance(job.result, dict):
                job.result["message"] = "任务已取消"
            raise
        except Exception as exc:
            if job.cancel_event.is_set():
                if isinstance(job.result, dict):
                    job.result["message"] = "任务已取消"
                raise asyncio.CancelledError() from exc
            if isinstance(job.result, dict):
                job.result["message"] = str(exc)
                job.result["written"] = False
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
