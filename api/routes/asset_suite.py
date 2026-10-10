"""结构导出、Emoji、批量修正与姓名提取：长任务走 JobManager。"""

from __future__ import annotations

import asyncio
import base64
import contextlib
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from api.jobs import Job
from base.BaseLanguage import BaseLanguage
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Extract.EmojiReplacer import (
    apply_replacements_dir,
    backup_folder,
    load_default_mapping,
)
from module.Extract.HakimiSuiteRunner import HakimiSuiteRunner
from module.Localizer.Localizer import Localizer
from module.Project.ProjectStore import ProjectStore
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Tool.AssetSuiteOps import (
    AssetSuiteCancelled,
    AssetSuiteError,
    apply_batch_corrections,
    export_batch_correction_workbook,
    export_name_glossary,
    extract_character_names,
    raise_if_cancelled,
    resolve_existing_dir,
)

router = APIRouter(prefix="/api/asset-suite", tags=["asset-suite"])

KINDS = (
    "asset_structure",
    "asset_emoji",
    "asset_corrections_export",
    "asset_corrections_apply",
    "asset_names_extract",
)
_BUSY = "已有任务正在运行或收尾，请稍后再试"


class StructureBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, pattern=r"\S")
    language: str = "chinese"
    mode: Literal["1", "2", "3"] | int = "1"
    use_official: bool = False
    exe_path: str = ""
    gen_emoji: bool = False
    project_key: str = ""
    confirm_overwrite: bool = False


class EmojiBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, pattern=r"\S")
    target_dir: str = Field(min_length=1, pattern=r"\S")
    mode: Literal["prepare", "restore"] = "prepare"
    project_key: str = ""
    confirm: bool = False


class CorrectionsExportBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    input_dir: str = Field(min_length=1, pattern=r"\S")
    output_dir: str = Field(min_length=1, pattern=r"\S")
    project_key: str = ""
    confirm_overwrite: bool = False


class CorrectionsApplyBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    workbook: str = Field(min_length=1, pattern=r"\S")
    translation_root: str = Field(min_length=1, pattern=r"\S")
    project_key: str = ""
    confirm: bool = False


class NamesExtractBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    input_dir: str = Field(min_length=1, pattern=r"\S")
    project_key: str = ""


class NamesExportBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    entries: list[dict[str, Any]]
    format: Literal["txt", "json"] = "txt"
    output_file: str = ""
    confirm_overwrite: bool = False
    project_key: str = ""


def _project_key(config: Any) -> str:
    paths = RenpyProjectPaths.from_config(config)
    return paths.project_key if paths is not None else ""


def _ensure_path_snapshot(body_key: str, config: Any) -> str:
    current = _project_key(config)
    if body_key and body_key != current:
        raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    return current or body_key


def _latest_job(request: Request, project_key: str | None = None) -> Job | None:
    key = project_key if project_key is not None else _project_key(request.app.state.config)
    return next(
        (
            job
            for job in request.app.state.jobs.list()
            if job.kind in KINDS
            and isinstance(job.result, dict)
            and job.result.get("project_key") == key
        ),
        None,
    )


def _acquire_engine() -> Engine:
    engine = Engine.get()
    if not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
        raise HTTPException(status_code=409, detail=_BUSY)
    return engine


def _resolve_project_root(raw: str) -> Path:
    path = Path(raw).expanduser().resolve(strict=False)
    root = path.parent if path.is_file() else path
    if root.name.lower() == "game":
        root = root.parent
    if not (root / "game").is_dir():
        raise HTTPException(status_code=400, detail=f"未找到 game 目录：{root / 'game'}")
    return root


async def _run_job(
    request: Request,
    *,
    kind: str,
    project_key: str,
    message: str,
    seed: dict[str, Any],
    compute: Callable[[Callable[[], None], Callable[[str, int | None, int | None], None]], dict],
) -> dict:
    engine = _acquire_engine()
    manager = request.app.state.jobs
    try:
        job = manager.create(kind, cooperative_cancel=True)
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        raise
    job.result = {
        "project_key": project_key,
        "message": message,
        "worker_active": True,
        **seed,
    }
    loop = asyncio.get_running_loop()

    def check_cancel() -> None:
        if job.cancel_event.is_set():
            raise asyncio.CancelledError()

    def publish(message_text: str, *, done: int | None = None, total: int | None = None) -> None:
        if not isinstance(job.result, dict) or not job.result.get("worker_active"):
            return
        job.result["message"] = message_text
        manager.progress(job.id, done=done, total=total)

    def progress(message_text: str, done: int | None = None, total: int | None = None) -> None:
        if job.cancel_event.is_set():
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
            job.result.update(result)
            check_cancel()
            if not result.get("success", True) and result.get("level") == "error":
                job.result["message"] = result.get("message") or "任务失败"
                raise RuntimeError(job.result["message"])
            job.result["message"] = result.get("message") or "完成"
            manager.progress(job.id, done=1, total=1)
            return job.result
        except asyncio.CancelledError:
            if isinstance(job.result, dict):
                job.result["message"] = "任务已取消"
            raise
        except Exception as exc:
            if job.cancel_event.is_set() or isinstance(exc, AssetSuiteCancelled):
                if isinstance(job.result, dict):
                    if isinstance(exc, AssetSuiteCancelled):
                        job.result.update(exc.result)
                    job.result["message"] = job.result.get("message") if job.result.get("cancelled") else "任务已取消"
                raise asyncio.CancelledError() from exc
            if isinstance(job.result, dict):
                if isinstance(exc, AssetSuiteError):
                    job.result.update(exc.result)
                job.result["message"] = str(exc)
                job.result["success"] = False
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


@router.get("/status")
def read_status(request: Request) -> dict:
    """返回当前项目相关的最近一次资源套件任务。"""
    with CacheManager.LOCK:
        key = _project_key(request.app.state.config)
    job = _latest_job(request, key)
    return {"job": job.snapshot() if job else None, "project_key": key}


@router.post("/structure")
async def start_structure(request: Request, body: StructureBody) -> dict:
    """生成终极结构导出（HakimiSuiteRunner）。"""
    with CacheManager.LOCK:
        config = request.app.state.config
        project_key = _ensure_path_snapshot(body.project_key, config)
        bound_key = _project_key(config)
    try:
        root = _resolve_project_root(body.path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    mode = str(body.mode).strip() or "1"
    if mode not in {"1", "2", "3"}:
        raise HTTPException(status_code=400, detail="mode 仅支持 1/2/3")
    exe = body.exe_path.strip() if body.use_official and body.exe_path.strip() else None
    path_snapshot = str(root)
    language = body.language.strip() or "chinese"

    def compute(check_cancel, progress) -> dict:
        def cancel() -> bool:
            try:
                check_cancel()
            except asyncio.CancelledError:
                return True
            return False

        runner = HakimiSuiteRunner()
        try:
            result = runner.run(
                path_snapshot,
                language,
                use_official=body.use_official,
                exe_path=exe,
                gen_emoji=body.gen_emoji,
                mode=mode,
                confirm_overwrite=body.confirm_overwrite,
                cancel_check=cancel,
                progress_callback=lambda message, done=None, total=None: progress(message, done, total),
            )
        except FileExistsError as exc:
            raise RuntimeError(str(exc)) from exc
        except AssetSuiteError:
            raise
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

        # 取消与项目身份在锁内再次核对，避免旧任务写回当前配置。
        with CacheManager.LOCK:
            check_cancel()
            current = _project_key(request.app.state.config)
            current_paths = RenpyProjectPaths.from_config(request.app.state.config)
            same_target = current_paths is not None and current_paths.project_root.resolve() == Path(path_snapshot).resolve()
            if bound_key and current == bound_key and current == project_key and same_target:
                ProjectStore.get().set_game_folder(request.app.state.config, str(Path(path_snapshot) / "game"))
                check_cancel()
                ProjectStore.get().persist(request.app.state.config, emit=False)

        payload = {
            "success": True,
            "level": "warning" if result.warnings or result.partial else "success",
            "operation": "structure",
            "path": path_snapshot,
            "output_dir": str(result.base_dir) if result.base_dir else "",
            "names_count": result.names_count,
            "others_count": result.others_count,
            "replace_count": result.replace_count,
            "deleted_count": result.deleted_count,
            "emoji_replacements": result.emoji_replacements,
            "emoji_dir": str(result.emoji_dir) if result.emoji_dir else "",
            "warnings": result.warnings,
            "backup_path": result.backup_path,
            "written": result.written,
            "partial": result.partial,
            "message": (
                f"结构导出完成：角色 {result.names_count} / 其他 {result.others_count} / 替换 {result.replace_count}"
            ),
        }
        return payload

    return await _run_job(
        request,
        kind="asset_structure",
        project_key=project_key,
        message="准备生成结构…",
        seed={"operation": "structure", "path": path_snapshot},
        compute=compute,
    )


@router.post("/emoji")
async def start_emoji(request: Request, body: EmojiBody) -> dict:
    """对目标 RPY 目录执行译前准备或译后还原。"""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Emoji 原地替换需要 confirm=true")
    with CacheManager.LOCK:
        config = request.app.state.config
        project_key = _ensure_path_snapshot(body.project_key, config)
    try:
        project_root = _resolve_project_root(body.path)
        target = resolve_existing_dir(body.target_dir, label="目标目录")
    except AssetSuiteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    root_snapshot = str(project_root)
    target_snapshot = str(target)

    def compute(check_cancel, progress) -> dict:
        def cancel() -> bool:
            try:
                check_cancel()
            except asyncio.CancelledError:
                return True
            return False

        progress("加载映射表…")
        mapping = load_default_mapping(Path(root_snapshot), body.mode)
        raise_if_cancelled(cancel)
        progress("备份目标目录…")
        backup = backup_folder(Path(target_snapshot), project_root=Path(root_snapshot), cancel_check=cancel)
        raise_if_cancelled(cancel)
        progress("执行替换…")
        details: dict = {}
        try:
            success, failed, changed = apply_replacements_dir(
                Path(target_snapshot),
                mapping,
                is_restore=(body.mode == "restore"),
                cancel_check=cancel,
                details=details,
            )
        except AssetSuiteCancelled as exc:
            exc.result["backup_path"] = str(backup)
            raise
        level = "success"
        if success == 0 and failed == 0:
            level = "warning"
        elif failed and success == 0:
            level = "error"
        elif failed:
            level = "warning"
        return {
            "success": level != "error",
            "level": level,
            "operation": "emoji",
            "mode": body.mode,
            "path": root_snapshot,
            "target_dir": target_snapshot,
            "backup_path": str(backup),
            "success_files": success,
            "failed_files": failed,
            "changed_count": changed,
            "message": f"已处理 {success} 个文件，失败 {failed}，变更 {changed}",
            "partial": failed > 0 and success > 0,
            **details,
        }

    return await _run_job(
        request,
        kind="asset_emoji",
        project_key=project_key,
        message="准备 Emoji 替换…",
        seed={"operation": "emoji", "path": root_snapshot, "target_dir": target_snapshot},
        compute=compute,
    )


@router.post("/corrections/export")
async def start_corrections_export(request: Request, body: CorrectionsExportBody) -> dict:
    """从结果检查 JSON 生成批量修正工作簿。"""
    with CacheManager.LOCK:
        config = request.app.state.config
        project_key = _ensure_path_snapshot(body.project_key, config)
    english = Localizer.get_app_language() == BaseLanguage.Enum.EN

    def compute(check_cancel, progress) -> dict:
        def cancel() -> bool:
            try:
                check_cancel()
            except asyncio.CancelledError:
                return True
            return False

        progress("扫描结果检查文件…")
        try:
            result = export_batch_correction_workbook(
                body.input_dir,
                body.output_dir,
                english=english,
                confirm_overwrite=body.confirm_overwrite,
                cancel_check=cancel,
            )
        except AssetSuiteCancelled:
            raise
        except AssetSuiteError as exc:
            raise RuntimeError(str(exc)) from exc
        result["operation"] = "corrections_export"
        return result

    return await _run_job(
        request,
        kind="asset_corrections_export",
        project_key=project_key,
        message="准备生成修正数据…",
        seed={"operation": "corrections_export", "path": body.input_dir},
        compute=compute,
    )


@router.post("/corrections/apply")
async def start_corrections_apply(request: Request, body: CorrectionsApplyBody) -> dict:
    """把批量修正工作簿注入译文目录（原地写入）。"""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="注入会原地修改译文，需要 confirm=true")
    with CacheManager.LOCK:
        config = request.app.state.config
        project_key = _ensure_path_snapshot(body.project_key, config)

    def compute(check_cancel, progress) -> dict:
        def cancel() -> bool:
            try:
                check_cancel()
            except asyncio.CancelledError:
                return True
            return False

        progress("注入修正数据…")
        try:
            result = apply_batch_corrections(
                body.workbook,
                body.translation_root,
                confirm=True,
                cancel_check=cancel,
            )
        except AssetSuiteCancelled:
            raise
        except AssetSuiteError as exc:
            raise RuntimeError(str(exc)) from exc
        result["operation"] = "corrections_apply"
        result["path"] = body.translation_root
        result["workbook"] = body.workbook
        return result

    return await _run_job(
        request,
        kind="asset_corrections_apply",
        project_key=project_key,
        message="准备注入修正…",
        seed={"operation": "corrections_apply", "path": body.translation_root},
        compute=compute,
    )


@router.post("/names/extract")
async def start_names_extract(request: Request, body: NamesExtractBody) -> dict:
    """递归扫描输入目录，提取角色姓名字段。"""
    with CacheManager.LOCK:
        config = request.app.state.config
        project_key = _ensure_path_snapshot(body.project_key, config)

    def compute(check_cancel, progress) -> dict:
        def cancel() -> bool:
            try:
                check_cancel()
            except asyncio.CancelledError:
                return True
            return False

        progress("提取姓名字段…")
        try:
            result = extract_character_names(body.input_dir, cancel_check=cancel)
        except AssetSuiteCancelled:
            raise
        except AssetSuiteError as exc:
            raise RuntimeError(str(exc)) from exc
        result["operation"] = "names_extract"
        result["path"] = body.input_dir
        # 空结果不算失败，但不伪造成功绿灯覆盖 draft：由前端保留旧 draft
        if result.get("empty"):
            result["success"] = True
            result["level"] = "warning"
        return result

    return await _run_job(
        request,
        kind="asset_names_extract",
        project_key=project_key,
        message="准备提取姓名…",
        seed={"operation": "names_extract", "path": body.input_dir},
        compute=compute,
    )


@router.post("/names/export")
def export_names(request: Request, body: NamesExportBody) -> dict:
    """导出姓名术语表为 TXT 或 JSON（可直接下载，不必落盘）。"""
    with CacheManager.LOCK:
        config = request.app.state.config
        _ensure_path_snapshot(body.project_key, config)
    try:
        result = export_name_glossary(
            body.entries,
            format=body.format,
            output_file=body.output_file or None,
            confirm_overwrite=body.confirm_overwrite,
        )
    except AssetSuiteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    content = result.get("content") or ""
    result["content_base64"] = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return result
