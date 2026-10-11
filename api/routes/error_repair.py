"""错误修复：扫描 / 自动修复 / lint / 导出报告，对齐 Qt ErrorRepairPage。"""

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
from module.Tool.ErrorRepairer import ErrorRepairer
from module.Tool.LexicalFs import lexical_abs, require_no_link_escape

router = APIRouter(prefix="/api/error-repair", tags=["error-repair"])

KIND_SCAN = "error_repair_scan"
KIND_FIX = "error_repair_fix"
KIND_LINT = "error_repair_lint"
KINDS = (KIND_SCAN, KIND_FIX, KIND_LINT)
_BUSY = "已有任务正在运行或收尾，请稍后再试"

# 进程内按目录身份缓存最近一次成功扫描，扫描失败时保留供导出
_LAST_SCAN: dict[str, dict[str, list[dict]]] = {}


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


def _folder_key(folder: Path) -> str:
    return derive_project_key(folder)


class FolderBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    folder: str = Field(min_length=1, pattern=r"\S")
    project_key: str = ""
    # 绑定项目 owner 快照；与 target project_key 分离，切项目后旧请求必须 409
    owner_project_key: str = ""


class ScanBody(FolderBody):
    check_indent: bool = True
    check_indent_level: bool = False


class FixBody(FolderBody):
    fix_indent: bool = True
    fix_indent_level: bool = False
    fix_quotes: bool = False
    fix_dialogue_quotes: bool = False
    confirm: bool = False


class LintBody(FolderBody):
    game_exe: str = Field(min_length=1, pattern=r"\S")


class ExportBody(FolderBody):
    output_path: str = Field(min_length=1, pattern=r"\S")
    report: dict[str, list[dict]] | None = None


def current_paths(config: Any) -> RenpyProjectPaths | None:
    return RenpyProjectPaths.from_config(config)


def _resolve_folder_operation(
    config: Any,
    *,
    folder: str,
    body_project_key: str,
    body_owner_key: str,
    require_lexical_clean: bool = False,
) -> tuple[str, Path, str, tuple[str, ...] | None]:
    """解析目标目录 + 校验 owner/target 快照。

    - project_key：必须等于目标目录键（若提供）
    - owner_project_key：有绑定时必须精确等于当前 owner；未绑定则必须为空
    """
    bound = current_paths(config)
    owner_key = bound.project_key if bound is not None else ""
    owner_identity = _project_identity(config) if bound is not None else None
    raw = str(folder or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="翻译目录必填")
    resolved = ErrorRepairer.resolve_translation_folder(raw)
    try:
        if require_lexical_clean:
            resolved = require_no_link_escape(resolved, label="翻译目录")
        else:
            resolved = lexical_abs(resolved)
            if not resolved.is_dir():
                raise FileNotFoundError(f"翻译目录不存在: {resolved}")
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if resolved.parent == resolved:
        raise HTTPException(status_code=400, detail="不能对磁盘根目录操作")
    target_key = _folder_key(resolved)
    body_key = str(body_project_key or "").strip()
    body_owner = str(body_owner_key or "").strip()
    if body_key and body_key != target_key:
        raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    if owner_key:
        if body_owner != owner_key:
            raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    elif body_owner:
        raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    return target_key, resolved, owner_key, owner_identity


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


def _describe(folder: Path, *, owner_key: str = "") -> dict[str, Any]:
    key = _folder_key(folder)
    return {
        "project_key": key,
        "folder": str(folder),
        "owner_project_key": owner_key,
        "has_scan_report": key in _LAST_SCAN,
    }


@router.get("")
def read_status(
    request: Request,
    folder: str = Query(default=""),
) -> dict:
    """按翻译目录定位最近任务；始终带回 owner_project_key 快照。"""
    with CacheManager.LOCK:
        config = request.app.state.config
        bound = current_paths(config)
        owner_key = bound.project_key if bound is not None else ""
        raw = str(folder or "").strip()
        if raw:
            try:
                resolved = lexical_abs(ErrorRepairer.resolve_translation_folder(raw))
            except Exception:
                resolved = None
            if resolved is not None and resolved.is_dir():
                payload = _describe(resolved, owner_key=owner_key)
                project_key = payload["project_key"]
            else:
                payload = {
                    "project_key": "",
                    "folder": raw,
                    "owner_project_key": owner_key,
                    "has_scan_report": False,
                }
                project_key = ""
        elif bound is not None and bound.tl_language_dir.is_dir():
            payload = _describe(lexical_abs(bound.tl_language_dir), owner_key=owner_key)
            project_key = payload["project_key"]
        else:
            payload = {
                "project_key": "",
                "folder": "",
                "owner_project_key": owner_key,
                "has_scan_report": False,
            }
            project_key = ""
    job = _latest_job(request, project_key) if project_key else None
    payload["job"] = job.snapshot() if job else None
    return payload


@router.post("/scan")
async def start_scan(request: Request, body: ScanBody) -> dict:
    """扫描错误；引号两类始终开启。扫描可跳过联接子树，不强制拒绝。"""
    with CacheManager.LOCK:
        project_key, folder, owner_key, owner_identity = _resolve_folder_operation(
            request.app.state.config,
            folder=body.folder,
            body_project_key=body.project_key,
            body_owner_key=body.owner_project_key,
            require_lexical_clean=False,
        )
    folder_key = project_key
    check_indent = body.check_indent
    check_indent_level = body.check_indent_level
    snapshot = str(folder)

    def compute(check_cancel, progress, should_stop, touch_result, owner_still):
        del should_stop, touch_result
        check_cancel()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        progress("正在扫描翻译目录", 20)
        repairer = ErrorRepairer()

        def cancelled() -> bool:
            try:
                check_cancel()
            except asyncio.CancelledError:
                return True
            return False

        report = repairer.check_folder(
            snapshot,
            check_indent=check_indent,
            check_indent_level=check_indent_level,
            check_quotes=True,
            check_dialogue_quotes=True,
            encoding="utf-8",
            should_cancel=cancelled,
        )
        check_cancel()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        total = sum(len(v) for v in report.values())
        _LAST_SCAN[folder_key] = report
        progress("扫描完成", 100)
        return {
            "success": True,
            "action": "scan",
            "written": False,
            "report": report,
            "total_issues": total,
            "folder": snapshot,
            "message": f"发现 {total} 个问题" if total else "未发现问题",
        }

    return await _start_job(
        request,
        kind=KIND_SCAN,
        project_key=project_key,
        owner_project_key=owner_key,
        message="准备扫描错误",
        owner_identity=owner_identity,
        seed={"action": "scan", "folder": snapshot, "written": False},
        compute=compute,
    )


@router.post("/fix")
async def start_fix(request: Request, body: FixBody) -> dict:
    """自动修复；写前拒绝联接逃逸；逐文件重验 owner；取消后如实汇报已写增量。"""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="自动修复会直接改写文件，需要 confirm=true")
    with CacheManager.LOCK:
        project_key, folder, owner_key, owner_identity = _resolve_folder_operation(
            request.app.state.config,
            folder=body.folder,
            body_project_key=body.project_key,
            body_owner_key=body.owner_project_key,
            require_lexical_clean=True,
        )
    snapshot = str(folder)
    opts = (
        body.fix_indent,
        body.fix_indent_level,
        body.fix_quotes,
        body.fix_dialogue_quotes,
    )

    def compute(check_cancel, progress, should_stop, touch_result, owner_still):
        del should_stop
        check_cancel()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        progress("正在自动修复", 10)
        # 列表生成后、首写前再验一次，防止切项目后仍写
        repairer = ErrorRepairer()
        files = repairer.get_rpy_files(snapshot)
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        fixed_files = 0
        fixed_items = 0
        failed_files = 0
        for index, rpy in enumerate(files):
            check_cancel()
            if not owner_still():
                raise RuntimeError("项目已切换，未执行操作")
            progress(f"修复 {rpy.name}", 10 + int(80 * index / max(len(files), 1)))
            ok, count = repairer.auto_fix_file(
                str(rpy),
                fix_indent=opts[0],
                fix_indent_level=opts[1],
                fix_quotes=opts[2],
                fix_dialogue_quotes=opts[3],
                encoding="utf-8",
            )
            if not ok:
                failed_files += 1
            elif count > 0:
                fixed_files += 1
                fixed_items += count
            # 任一副作用后立即固化，取消时 worker 能看到 written/partial
            if fixed_files or fixed_items or failed_files:
                touch_result({
                    "written": fixed_files > 0 or fixed_items > 0,
                    "partial": True,
                    "fixed_files": fixed_files,
                    "fixed_items": fixed_items,
                    "failed_files": failed_files,
                    "action": "fix",
                    "folder": snapshot,
                    "message": f"已修复 {fixed_files} 个文件、{fixed_items} 处（进行中）",
                })
            if not owner_still():
                raise RuntimeError("项目已切换，未执行操作")
        partial = failed_files > 0
        progress("修复完成", 100)
        message = f"已修复 {fixed_files} 个文件、{fixed_items} 处"
        if partial:
            message += f"；{failed_files} 个文件失败"
        return {
            "success": not partial or fixed_files > 0 or fixed_items > 0,
            "partial": partial,
            "action": "fix",
            "written": fixed_files > 0 or fixed_items > 0,
            "fixed_files": fixed_files,
            "fixed_items": fixed_items,
            "failed_files": failed_files,
            "folder": snapshot,
            "message": message,
        }

    return await _start_job(
        request,
        kind=KIND_FIX,
        project_key=project_key,
        owner_project_key=owner_key,
        message="准备自动修复",
        owner_identity=owner_identity,
        seed={"action": "fix", "folder": snapshot, "written": False},
        compute=compute,
    )


@router.post("/lint")
async def start_lint(request: Request, body: LintBody) -> dict:
    """深度 lint：None 失败、空串成功；仅过滤选定 TL。"""
    with CacheManager.LOCK:
        project_key, folder, owner_key, owner_identity = _resolve_folder_operation(
            request.app.state.config,
            folder=body.folder,
            body_project_key=body.project_key,
            body_owner_key=body.owner_project_key,
            require_lexical_clean=False,
        )
    exe = Path(body.game_exe).expanduser()
    if not exe.is_file():
        raise HTTPException(status_code=400, detail=f"游戏主程序不存在: {exe}")
    snapshot_folder = str(folder)
    snapshot_exe = str(exe.resolve(strict=False))

    def compute(check_cancel, progress, should_stop, touch_result, owner_still):
        del should_stop, touch_result
        check_cancel()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        progress("正在执行 Ren'Py lint", 30)
        repairer = ErrorRepairer()
        lint_output = repairer.exec_renpy_lint(snapshot_exe)
        if lint_output is None:
            raise RuntimeError("Lint 执行失败（无法启动 Ren'Py Python/入口）")
        check_cancel()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        parsed = repairer.parse_lint_errors(lint_output)
        filtered = repairer.filter_lint_errors(parsed, snapshot_folder)
        lint_file = str(Path(snapshot_exe).parent / "lint_errors.txt") if lint_output else ""
        progress("Lint 完成", 100)
        return {
            "success": True,
            "action": "lint",
            "written": bool(lint_output and Path(lint_file).is_file()),
            "output": lint_output,
            "errors": filtered,
            "error_count": len(filtered),
            "lint_errors_path": lint_file if lint_output else "",
            "folder": snapshot_folder,
            "game_exe": snapshot_exe,
            "message": (
                f"Lint 发现 {len(filtered)} 条与翻译目录相关的问题"
                if filtered
                else "Lint 未发现翻译目录相关问题"
            ),
        }

    return await _start_job(
        request,
        kind=KIND_LINT,
        project_key=project_key,
        owner_project_key=owner_key,
        message="准备执行 Lint",
        owner_identity=owner_identity,
        seed={"action": "lint", "folder": snapshot_folder, "written": False},
        compute=compute,
    )


@router.post("/export")
def export_report(request: Request, body: ExportBody) -> dict:
    """同步导出 XLSX；引擎忙时 409 且无副作用。"""
    engine = _acquire_engine()
    try:
        with CacheManager.LOCK:
            project_key, folder, owner_key, _identity = _resolve_folder_operation(
                request.app.state.config,
                folder=body.folder,
                body_project_key=body.project_key,
                body_owner_key=body.owner_project_key,
                require_lexical_clean=False,
            )
        report = body.report
        if report is None:
            report = _LAST_SCAN.get(project_key)
        if report is None:
            job = _latest_job(request, project_key)
            if job and isinstance(job.result, dict) and job.result.get("action") == "scan":
                candidate = job.result.get("report")
                if isinstance(candidate, dict):
                    report = candidate
        if report is None:
            raise HTTPException(status_code=400, detail="请先扫描错误后再导出")

        output = Path(body.output_path).expanduser()
        output_text = str(output)
        if not output_text.lower().endswith(".xlsx"):
            output_text += ".xlsx"
        ok = ErrorRepairer().export_error_report(report, output_text)
        if not ok:
            raise HTTPException(status_code=500, detail="导出错误报告失败")
        final = Path(output_text)
        if not final.is_file():
            raise HTTPException(status_code=500, detail="导出失败：目标文件未生成")
        return {
            "success": True,
            "output_path": str(final.resolve(strict=False)),
            "folder": str(folder),
            "project_key": project_key,
            "owner_project_key": owner_key,
            "message": f"报告已保存到 {final}",
        }
    finally:
        engine.release_status(Engine.Status.TESTING)


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
            # 冻结时未绑定，运行中又绑上了别的项目 → 拒绝
            return False
        if folder_snapshot and _folder_key(Path(folder_snapshot)) != frozen_target_key:
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
        if not owner_still() and not (isinstance(result, dict) and result.get("written")):
            raise RuntimeError("项目已切换，未执行操作")
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
                if job.result.get("success") is False and job.result.get("written"):
                    raise RuntimeError(job.result.get("message") or "任务失败")
            if isinstance(job.result, dict) and job.result.get("partial") and job.result.get("written"):
                # 正常结束的部分失败：清 cancel，标 done
                if not job.cancel_event.is_set():
                    job.result["partial"] = bool(job.result.get("failed_files"))
                job.cancel_event.clear()
                manager.progress(job.id, done=100, total=100)
                return job.result
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
            if isinstance(job.result, dict) and job.result.get("written"):
                job.result.setdefault("partial", True)
                job.result["success"] = False
                job.result["message"] = str(exc)
            elif isinstance(job.result, dict):
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
