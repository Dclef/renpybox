"""解包、反编译与打包：长任务走 JobManager，协作取消后才释放引擎。"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from api.jobs import Job
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Localizer.Localizer import Localizer
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Tool.ArchiveOps import (
    PackerUnpackError,
    cleanup_decompiled_rpyc,
    cleanup_unpack_artifacts,
    decompile_target,
    pack_directory,
    parse_rpa_size_limit,
    resolve_game_dir,
    resolve_pack_output,
    unpack_game,
)

router = APIRouter(prefix="/api/archive", tags=["archive"])

ARCHIVE_KINDS = (
    "archive_unpack",
    "archive_decompile",
    "archive_pack",
    "archive_cleanup_temp",
    "archive_cleanup_rpyc",
)


class ArchivePathBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, pattern=r"\S")
    project_key: str = ""


class UnpackBody(ArchivePathBody):
    direct: bool = True
    script_only: bool = False


class DecompileBody(ArchivePathBody):
    overwrite: bool = False
    use_unren: bool = True
    confirm_overwrite: bool = False


class PackBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_dir: str = Field(min_length=1, pattern=r"\S")
    # 留空时由服务端按源目录重新推导，不信任前端拼出的路径。
    output_file: str = ""
    # None 表示未勾选分卷；勾选后才按容量格式解析。
    max_part_size: str | None = None
    project_key: str = ""
    confirm: bool = False


def _project_key(config: Any) -> str:
    paths = RenpyProjectPaths.from_config(config)
    if paths is None:
        return ""
    return paths.project_key


def _latest_archive_job(request: Request, project_key: str | None = None) -> Job | None:
    key = project_key if project_key is not None else _project_key(request.app.state.config)
    return next(
        (
            job for job in request.app.state.jobs.list()
            if job.kind in ARCHIVE_KINDS and isinstance(job.result, dict)
            and job.result.get("project_key") == key
        ),
        None,
    )


def _acquire_engine() -> Engine:
    engine = Engine.get()
    if not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
        raise HTTPException(status_code=409, detail="已有任务正在运行或收尾，请稍后再试")
    return engine


def _ensure_path_snapshot(body_key: str, config: Any) -> str:
    current = _project_key(config)
    if body_key and body_key != current:
        raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    return current or body_key


async def _run_archive_job(
    request: Request,
    *,
    kind: str,
    project_key: str,
    message: str,
    compute,
    path_label: str,
    output_file: str | None = None,
    cancellable: bool = False,
) -> dict:
    engine = _acquire_engine()
    manager = request.app.state.jobs
    try:
        # 不可取消的任务也走协作模式，避免通用取消接口直接打断仍在写盘的线程。
        job = manager.create(kind, cooperative_cancel=True)
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        raise
    job.result = {
        "project_key": project_key,
        "message": message,
        "worker_active": True,
        "path": path_label,
        "cancellable": cancellable,
    }
    if output_file is not None:
        job.result["output_file"] = output_file
    loop = asyncio.get_running_loop()

    def cancel_requested() -> bool:
        return cancellable and job.cancel_event.is_set()

    def check_cancel() -> None:
        if cancel_requested():
            raise asyncio.CancelledError()

    def publish(message_text: str, *, done: int | None = None, total: int | None = None) -> None:
        if not isinstance(job.result, dict) or not job.result.get("worker_active"):
            return
        job.result["message"] = message_text
        manager.progress(job.id, done=done, total=total)

    def progress(message_text: str, done: int | None = None, total: int | None = None) -> None:
        # 子进程日志可能来自读取线程，不能用异常中断它并堵塞管道。
        if cancel_requested():
            return
        loop.call_soon_threadsafe(lambda: publish(message_text, done=done, total=total))

    async def worker(_: Job) -> dict:
        try:
            check_cancel()
            future = loop.run_in_executor(None, lambda: compute(check_cancel, progress))
            try:
                result = await asyncio.shield(future)
            except asyncio.CancelledError:
                job.cancel_event.set()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.shield(future)
                raise
            if not result.get("success"):
                check_cancel()
                job.result.update(result)
                job.result["message"] = result.get("message") or "任务失败"
                raise RuntimeError(job.result["message"])
            # 结果已写盘发布，迟到的取消请求不能再把 done 改成 cancelled。
            job.cancel_event.clear()
            job.result.update(result)
            job.result["message"] = result.get("message") or "完成"
            manager.progress(job.id, done=1, total=1)
            return job.result
        except asyncio.CancelledError:
            if isinstance(job.result, dict):
                job.result["message"] = "任务已取消"
            raise
        except Exception as exc:
            if cancel_requested():
                if isinstance(job.result, dict):
                    job.result["message"] = "任务已取消"
                raise asyncio.CancelledError() from exc
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


@router.get("")
def read_archive(request: Request) -> dict:
    """返回当前项目最近一次解包/反编译/打包任务。"""
    job = _latest_archive_job(request)
    return {"job": job.snapshot() if job else None}


@router.post("/unpack")
async def start_unpack(request: Request, body: UnpackBody) -> dict:
    """解包 RPA；永不删除源档。"""
    with CacheManager.LOCK:
        config = request.app.state.config
        project_key = _ensure_path_snapshot(body.project_key, config)
    try:
        game_dir = resolve_game_dir(body.path)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not game_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"游戏目录不存在：{game_dir}")
    snapshot_dir = str(game_dir)

    def compute(check_cancel, progress):
        check_cancel()
        try:
            return unpack_game(
                snapshot_dir,
                direct=body.direct,
                script_only=body.script_only,
                progress_callback=lambda message: progress(message),
            )
        except PackerUnpackError as exc:
            return {
                "success": False,
                "level": "error",
                "message": Localizer.get().pack_unpack_error(exc.code),
                "code": exc.code,
                "archives_removed": False,
            }

    return await _run_archive_job(
        request,
        kind="archive_unpack",
        project_key=project_key,
        message=Localizer.get().pack_unpack_preparing,
        compute=compute,
        path_label=snapshot_dir,
    )


@router.post("/decompile")
async def start_decompile(request: Request, body: DecompileBody) -> dict:
    """反编译 rpyc；覆盖已有 rpy 需显式确认。"""
    if body.overwrite and not body.confirm_overwrite:
        raise HTTPException(status_code=400, detail="覆盖已有 .rpy 需要 confirm_overwrite=true")
    with CacheManager.LOCK:
        config = request.app.state.config
        project_key = _ensure_path_snapshot(body.project_key, config)
    try:
        game_dir = resolve_game_dir(body.path)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    snapshot_target = str(Path(body.path).expanduser().resolve())

    def compute(check_cancel, progress):
        check_cancel()
        return decompile_target(
            snapshot_target,
            overwrite=body.overwrite,
            use_unren=body.use_unren,
            fallback_unren_options="2x",
            progress_callback=lambda message: progress(message),
        )

    return await _run_archive_job(
        request,
        kind="archive_decompile",
        project_key=project_key,
        message=Localizer.get().pack_unpack_preparing,
        compute=compute,
        path_label=snapshot_target,
    )


@router.post("/pack")
async def start_pack(request: Request, body: PackBody) -> dict:
    """打包目录为 RPA；写入前需 confirm。"""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="打包会写入输出文件，需要 confirm=true")
    with CacheManager.LOCK:
        config = request.app.state.config
        project_key = _ensure_path_snapshot(body.project_key, config)
    try:
        source = Path(body.source_dir).expanduser().resolve()
        output = resolve_pack_output(source, body.output_file)
        max_part = None if body.max_part_size is None else parse_rpa_size_limit(body.max_part_size)
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    snapshot_source = str(source)
    snapshot_output = str(output)

    def compute(check_cancel, progress):
        def stop_check() -> bool:
            try:
                check_cancel()
            except asyncio.CancelledError:
                return True
            return False

        try:
            return pack_directory(
                snapshot_source,
                snapshot_output,
                max_part_size_bytes=max_part,
                progress_callback=lambda current, total, filename: progress(
                    Localizer.get().pack_unpack_packing.format(current=current, total=total, filename=filename),
                    done=current,
                    total=total or 1,
                ),
                stop_check=stop_check,
            )
        except Exception as exc:
            if stop_check():
                raise
            # 与 Qt5 PackWorker 一致：失败统一加“打包失败”前缀。
            raise RuntimeError(Localizer.get().pack_unpack_packaging_failed.format(
                message=Localizer.localize(str(exc), "Packaging failed. Check the logs for details."),
            )) from exc

    return await _run_archive_job(
        request,
        kind="archive_pack",
        project_key=project_key,
        message=Localizer.get().pack_unpack_scanning_files,
        compute=compute,
        path_label=snapshot_source,
        output_file=snapshot_output,
        cancellable=True,
    )


@router.post("/cleanup-temp")
async def start_cleanup_temp(request: Request, body: ArchivePathBody) -> dict:
    """按白名单清理解包/反编译遗留的临时文件；逐项检查取消。"""
    with CacheManager.LOCK:
        config = request.app.state.config
        project_key = _ensure_path_snapshot(body.project_key, config)
    try:
        game_dir = resolve_game_dir(body.path)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    snapshot_dir = str(game_dir)

    def compute(check_cancel, progress):
        def stop_check() -> bool:
            try:
                check_cancel()
            except asyncio.CancelledError:
                return True
            return False

        check_cancel()
        progress(Localizer.get().pack_unpack_cleaning_temporary_files)
        return cleanup_unpack_artifacts(snapshot_dir, stop_check=stop_check)

    return await _run_archive_job(
        request,
        kind="archive_cleanup_temp",
        project_key=project_key,
        message=Localizer.get().pack_unpack_preparing_cleanup,
        compute=compute,
        path_label=snapshot_dir,
    )


@router.post("/cleanup-rpyc")
async def start_cleanup_rpyc(request: Request, body: ArchivePathBody) -> dict:
    """删除已有同名 .rpy 的 .rpyc；开始删除前可取消。"""
    with CacheManager.LOCK:
        config = request.app.state.config
        project_key = _ensure_path_snapshot(body.project_key, config)
    try:
        game_dir = resolve_game_dir(body.path)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    snapshot_dir = str(game_dir)

    def compute(check_cancel, progress):
        check_cancel()
        progress(Localizer.get().pack_unpack_cleaning_rpyc_files)
        return cleanup_decompiled_rpyc(snapshot_dir)

    return await _run_archive_job(
        request,
        kind="archive_cleanup_rpyc",
        project_key=project_key,
        message=Localizer.get().pack_unpack_preparing_cleanup,
        compute=compute,
        path_label=snapshot_dir,
    )
