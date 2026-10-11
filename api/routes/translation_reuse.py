"""更新翻译复用：预览只读 / 执行写入，对齐 Qt TranslationReusePage。"""

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
from module.Extract.UnifiedExtractor import TranslationReuseResult, UnifiedExtractor
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Tool.LexicalFs import lexical_abs, require_no_link_escape

router = APIRouter(prefix="/api/translation-reuse", tags=["translation-reuse"])

KIND_PREVIEW = "translation_reuse_preview"
KIND_EXECUTE = "translation_reuse_execute"
KINDS = (KIND_PREVIEW, KIND_EXECUTE)
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


def _pair_key(source: Path, target: Path) -> str:
    return derive_project_key(target) + "::reuse::" + derive_project_key(source)


class ReuseBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_dir: str = Field(min_length=1, pattern=r"\S")
    target_dir: str = Field(min_length=1, pattern=r"\S")
    project_key: str = ""
    owner_project_key: str = ""
    confirm: bool = False


def current_paths(config: Any) -> RenpyProjectPaths | None:
    return RenpyProjectPaths.from_config(config)


def _resolve_reuse(
    config: Any,
    *,
    source_dir: str,
    target_dir: str,
    body_project_key: str,
    body_owner_key: str = "",
    validate_owner: bool = True,
) -> tuple[str, Path, Path, str, tuple[str, ...] | None]:
    bound = current_paths(config)
    owner_key = bound.project_key if bound is not None else ""
    owner_identity = _project_identity(config) if bound is not None else None
    try:
        # 写入/预览均守 lexical 边界：含向外联接则拒绝，不 resolve 放行
        source = require_no_link_escape(source_dir, label="旧译文目录")
        target = require_no_link_escape(target_dir, label="目标译文目录")
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if source == target:
        raise HTTPException(status_code=400, detail="旧译文目录和目标译文目录不能相同")
    if source in target.parents or target in source.parents:
        raise HTTPException(status_code=400, detail="旧译文与目标译文目录不能互相包含")
    if source.parent == source or target.parent == target:
        raise HTTPException(status_code=400, detail="不能对磁盘根目录操作")
    target_key = _pair_key(source, target)
    body_key = str(body_project_key or "").strip()
    body_owner = str(body_owner_key or "").strip()
    if body_key and body_key != target_key:
        raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    if validate_owner:
        if owner_key:
            if body_owner != owner_key:
                raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
        elif body_owner:
            raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    return target_key, source, target, owner_key, owner_identity


def _result_payload(result: TranslationReuseResult, *, action: str, source: Path, target: Path) -> dict[str, Any]:
    failed = list(result.failed_files or [])
    written = action == "execute" and (result.applied_entries > 0 or result.hook_updated)
    partial = bool(failed) and written
    success = not failed or (action == "preview")
    if action == "execute" and failed and result.applied_entries == 0 and not result.hook_updated:
        success = False
    message_parts = [
        f"可复用 {result.reusable_entries}",
        f"冲突 {result.conflicts}",
        f"已复用 {result.already_reused}",
        f"未匹配 {result.unmatched_entries}",
    ]
    if action == "execute":
        message_parts.insert(0, f"已写入 {result.applied_entries} 条")
    if result.hook_updated:
        message_parts.append("已更新替换钩子")
    if result.backup_path is not None:
        message_parts.append(f"备份 {result.backup_path}")
    if failed:
        message_parts.append(f"{len(failed)} 个文件写入失败")
    return {
        "success": success,
        "partial": partial,
        "action": action,
        "written": written,
        "source_dir": str(source),
        "target_dir": str(target),
        "source_translations": result.source_translations,
        "target_entries": result.target_entries,
        "matched_entries": result.matched_entries,
        "reusable_entries": result.reusable_entries,
        "applied_entries": result.applied_entries,
        "already_reused": result.already_reused,
        "conflicts": result.conflicts,
        "unmatched_entries": result.unmatched_entries,
        "hook_updated": result.hook_updated,
        "backup_path": str(result.backup_path) if result.backup_path is not None else "",
        "failed_files": failed,
        "message": "；".join(message_parts),
    }


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
def read_status(
    request: Request,
    source_dir: str = Query(default=""),
    target_dir: str = Query(default=""),
) -> dict:
    """按源/目标路径对定位最近复用任务。"""
    with CacheManager.LOCK:
        config = request.app.state.config
        bound = current_paths(config)
        owner_key = bound.project_key if bound is not None else ""
        default_target = ""
        if bound is not None and bound.tl_language_dir.is_dir():
            default_target = str(bound.tl_language_dir)
        src = str(source_dir or "").strip()
        tgt = str(target_dir or "").strip() or default_target
        project_key = ""
        source: Path = Path(src) if src else Path()
        target: Path = Path(tgt) if tgt else Path()
        if src and tgt:
            try:
                project_key, source, target, _, _ = _resolve_reuse(
                    config,
                    source_dir=src,
                    target_dir=tgt,
                    body_project_key="",
                    body_owner_key="",
                    validate_owner=False,
                )
            except HTTPException:
                project_key = ""
    job = _latest_job(request, project_key) if project_key else None
    return {
        "project_key": project_key,
        "owner_project_key": owner_key,
        "source_dir": str(source) if src else "",
        "target_dir": str(target) if tgt else default_target,
        "default_target_dir": default_target,
        "job": job.snapshot() if job else None,
    }


@router.post("/preview")
async def preview(request: Request, body: ReuseBody) -> dict:
    """只读预览；不写盘、不备份、不更新钩子。"""
    with CacheManager.LOCK:
        project_key, source, target, owner_key, owner_identity = _resolve_reuse(
            request.app.state.config,
            source_dir=body.source_dir,
            target_dir=body.target_dir,
            body_project_key=body.project_key,
            body_owner_key=body.owner_project_key,
        )
    snap_src, snap_tgt = str(source), str(target)

    def compute(check_cancel, progress, should_stop, touch_result, owner_still):
        del should_stop, touch_result
        check_cancel()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        progress("正在预览复用", 30)
        result = UnifiedExtractor().preview_translation_reuse(snap_src, snap_tgt)
        check_cancel()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        progress("预览完成", 100)
        return _result_payload(result, action="preview", source=Path(snap_src), target=Path(snap_tgt))

    return await _start_job(
        request,
        kind=KIND_PREVIEW,
        project_key=project_key,
        owner_project_key=owner_key,
        message="准备预览复用",
        owner_identity=owner_identity,
        seed={
            "action": "preview",
            "source_dir": snap_src,
            "target_dir": snap_tgt,
            "written": False,
        },
        compute=compute,
    )


@router.post("/execute")
async def execute(request: Request, body: ReuseBody) -> dict:
    """执行复用：共享内部先预览再备份再写入；需 confirm。"""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="执行复用会改写目标译文并自动备份，需要 confirm=true")
    with CacheManager.LOCK:
        project_key, source, target, owner_key, owner_identity = _resolve_reuse(
            request.app.state.config,
            source_dir=body.source_dir,
            target_dir=body.target_dir,
            body_project_key=body.project_key,
            body_owner_key=body.owner_project_key,
        )
    snap_src, snap_tgt = str(source), str(target)

    def compute(check_cancel, progress, should_stop, touch_result, owner_still):
        del should_stop
        check_cancel()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        progress("正在复用译文", 20)
        # 备份/写盘前再验
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        result = UnifiedExtractor().reuse_translations(snap_src, snap_tgt)
        payload = _result_payload(result, action="execute", source=Path(snap_src), target=Path(snap_tgt))
        if payload.get("written"):
            touch_result({**payload, "partial": True})
        check_cancel()
        if not owner_still() and not payload.get("written"):
            raise RuntimeError("项目已切换，未执行操作")
        progress("复用完成", 100)
        return payload

    return await _start_job(
        request,
        kind=KIND_EXECUTE,
        project_key=project_key,
        owner_project_key=owner_key,
        message="准备执行复用",
        owner_identity=owner_identity,
        seed={
            "action": "execute",
            "source_dir": snap_src,
            "target_dir": snap_tgt,
            "written": False,
        },
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
    pair_src = str(seed.get("source_dir") or "")
    pair_tgt = str(seed.get("target_dir") or "")
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
        if pair_src and pair_tgt and _pair_key(Path(pair_src), Path(pair_tgt)) != frozen_target_key:
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
                if job.result.get("success") is False:
                    raise RuntimeError(job.result.get("message") or "复用失败")
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
