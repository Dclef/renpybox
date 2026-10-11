"""网页/AI 翻译向导：复用 TlTextExporter / HtmlTextConverter，对齐 Qt HtmlImportPage。"""

from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.jobs import Job
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Extract.TlTextExporter import (
    TlTextExporterError,
    apply_translations_to_tl,
    extract_pending_from_tl,
    resolve_apply_output_dir,
)
from module.Tool.HtmlTextConverter import (
    EXCEL_COLUMN_ORIGINAL,
    EXCEL_COLUMN_TRANSLATION,
    default_sibling_output,
    excel_to_txt,
    html_to_txt,
    txt_to_html,
)

router = APIRouter(prefix="/api/html-import", tags=["html-import"])

KIND_EXTRACT = "html_import_extract"
KIND_APPLY = "html_import_apply"
KIND_HTML_TO_TXT = "html_import_html_to_txt"
KIND_TXT_TO_HTML = "html_import_txt_to_html"
KIND_EXCEL_TO_TXT = "html_import_excel_to_txt"
KINDS = (
    KIND_EXTRACT,
    KIND_APPLY,
    KIND_HTML_TO_TXT,
    KIND_TXT_TO_HTML,
    KIND_EXCEL_TO_TXT,
)
_BUSY = "已有任务正在运行或收尾，请稍后再试"
_EXCEL_COLUMNS = {EXCEL_COLUMN_ORIGINAL, EXCEL_COLUMN_TRANSLATION}


def _norm(value: str) -> str:
    return os.path.normcase(os.path.abspath(value)) if value else ""


def _project_identity(config: Any) -> tuple[str, ...]:
    """冻结 owner 身份：未绑定时为各字段空串组成的 tuple，绝不能用 None 跳过守卫。"""
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


def _target_key(*parts: str) -> str:
    joined = "|".join(_norm(part) for part in parts if str(part or "").strip())
    return joined or "html-import"


def _parse_owner_identity(value: Any) -> list[str] | None:
    """可选 owner 快照：缺省/None 兼容旧客户端；否则必须是纯字符串 list/tuple。"""
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise ValueError("owner_identity 必须是字符串列表")
    if not all(isinstance(item, str) for item in value):
        raise ValueError("owner_identity 每项必须是字符串")
    return list(value)


def _reject_stale_owner(body_identity: list[str] | None, live: tuple[str, ...]) -> None:
    """请求携带快照且与当前配置不一致时，创建任务前 409。"""
    if body_identity is None:
        return
    if tuple(body_identity) != live:
        raise HTTPException(status_code=409, detail="项目身份已变化，请刷新后再试")


class _OwnerSnapshotBody(BaseModel):
    """POST 可选 owner_identity；严格校验 list/tuple[str]，缺省兼容旧客户端。"""

    owner_identity: list[str] | None = None

    @field_validator("owner_identity", mode="before")
    @classmethod
    def _validate_owner_identity(cls, value: Any) -> list[str] | None:
        return _parse_owner_identity(value)


class ExtractBody(_OwnerSnapshotBody):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    tl_dir: str = Field(min_length=1)
    txt_output: str = ""
    manifest_output: str = ""


class ApplyBody(_OwnerSnapshotBody):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    manifest_path: str = Field(min_length=1)
    translated_txt: str = Field(min_length=1)
    output_tl_dir: str = ""
    source_tl_dir: str = ""
    confirm_overwrite: bool = False


class HtmlToTxtBody(_OwnerSnapshotBody):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    html_path: str = Field(min_length=1)
    txt_output: str = ""
    pairs: bool = False
    confirm_overwrite: bool = False


class TxtToHtmlBody(_OwnerSnapshotBody):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    txt_path: str = Field(min_length=1)
    html_output: str = ""
    keep_data: bool = False
    confirm_overwrite: bool = False


class ExcelToTxtBody(_OwnerSnapshotBody):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    excel_path: str = Field(min_length=1)
    txt_output: str = ""
    column: Literal["原文", "译文"] = "译文"
    confirm_overwrite: bool = False


def _acquire_engine() -> Engine:
    engine = Engine.get()
    if not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
        raise HTTPException(status_code=409, detail=_BUSY)
    return engine


def _latest_job(request: Request, project_key: str) -> Job | None:
    return next(
        (
            job
            for job in request.app.state.jobs.list()
            if job.kind in KINDS
            and isinstance(job.result, dict)
            and job.result.get("project_key") == project_key
        ),
        None,
    )


def _require_existing_dir(path_text: str, label: str) -> Path:
    text = str(path_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail=f"{label}不能为空")
    path = Path(text).expanduser()
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"{label}不存在")
    return path


def _require_existing_file(path_text: str, label: str) -> Path:
    text = str(path_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail=f"{label}不能为空")
    path = Path(text).expanduser()
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"{label}不存在")
    return path


def _ensure_overwrite(path: Path, *, confirm: bool, label: str) -> None:
    if path.exists() and not confirm:
        raise HTTPException(status_code=400, detail=f"{label}已存在，需确认覆盖")


def _job_key(body_key: str, *parts: str) -> str:
    """任务键优先使用前端从 status 冻结的 project_key，保证同页轮询一致。"""
    body = str(body_key or "").strip()
    if body:
        return body
    return _target_key(*parts)


@router.get("")
def read_status(
    request: Request,
    tl_dir: str = Query(default=""),
    manifest_path: str = Query(default=""),
) -> dict:
    """独立路径工具状态；不强制绑定项目。"""
    tl_text = str(tl_dir or "").strip()
    manifest_text = str(manifest_path or "").strip()
    key = _target_key(tl_text or manifest_text or "idle")
    default_txt = ""
    default_output = ""
    if tl_text:
        default_txt = str(Path(tl_text) / "pending_translate.txt")
    if manifest_text:
        try:
            default_output = str(resolve_apply_output_dir(manifest_text))
        except Exception:
            default_output = str(Path(manifest_text).parent / "translated_tl")
    with CacheManager.LOCK:
        owner = _project_identity(request.app.state.config)
    payload = {
        "project_key": key,
        "tl_dir": tl_text,
        "manifest_path": manifest_text,
        "default_txt_output": default_txt,
        "default_output_tl_dir": default_output,
        "owner_identity": list(owner),
        "requires_project": False,
        "job": None,
    }
    job = _latest_job(request, key)
    if job is not None:
        payload["job"] = job.snapshot()
    return payload


@router.post("/extract")
async def extract_pending(request: Request, body: ExtractBody) -> dict:
    with CacheManager.LOCK:
        owner = _project_identity(request.app.state.config)
    _reject_stale_owner(body.owner_identity, owner)
    tl_dir = _require_existing_dir(body.tl_dir, "TL 目录")
    txt_output = Path(body.txt_output.strip()) if body.txt_output.strip() else tl_dir / "pending_translate.txt"
    manifest_output = (
        Path(body.manifest_output.strip())
        if body.manifest_output.strip()
        else txt_output.with_suffix(".manifest.json")
    )
    target_key = _job_key(body.project_key, str(tl_dir))

    def compute(check_cancel, progress, should_stop, touch_result) -> dict:
        del should_stop
        check_cancel()
        progress("正在导出待翻译文本", 10)
        check_cancel()  # 写前再校验冻结 owner（含空→绑定）
        count, manifest = extract_pending_from_tl(tl_dir, txt_output, manifest_output)
        # 执行器已写入：立即固化，取消/失败时 worker 可读到 written/partial
        touch_result({
            "written": True,
            "partial": True,
            "success": False,
            "action": "extract",
            "count": count,
            "txt_path": str(txt_output.resolve()),
            "manifest_path": str(Path(manifest).resolve()),
            "tl_dir": str(tl_dir.resolve()),
            "message": f"已导出 {count} 条待翻译文本（写入完成，收尾中）",
        })
        check_cancel()
        progress("导出完成", 100)
        return {
            "success": True,
            "written": True,
            "partial": False,
            "action": "extract",
            "count": count,
            "txt_path": str(txt_output.resolve()),
            "manifest_path": str(Path(manifest).resolve()),
            "tl_dir": str(tl_dir.resolve()),
            "message": f"已导出 {count} 条待翻译文本",
        }

    return await _start_job(
        request,
        kind=KIND_EXTRACT,
        project_key=target_key,
        message="导出待翻译文本",
        seed={
            "action": "extract",
            "tl_dir": str(tl_dir),
            "txt_path": str(txt_output),
            "manifest_path": str(manifest_output),
        },
        compute=compute,
        owner_identity=owner,
    )


@router.post("/apply")
async def apply_translations(request: Request, body: ApplyBody) -> dict:
    with CacheManager.LOCK:
        owner = _project_identity(request.app.state.config)
    _reject_stale_owner(body.owner_identity, owner)
    manifest_path = _require_existing_file(body.manifest_path, "行号清单")
    translated_txt = _require_existing_file(body.translated_txt, "译文 TXT")
    output_tl_dir = resolve_apply_output_dir(manifest_path, body.output_tl_dir or None)
    source_tl = body.source_tl_dir.strip() or None
    if output_tl_dir.exists() and not body.confirm_overwrite:
        raise HTTPException(status_code=400, detail=f"输出目录已存在，需确认覆盖: {output_tl_dir}")
    target_key = _job_key(body.project_key, str(manifest_path), str(output_tl_dir))

    def compute(check_cancel, progress, should_stop, touch_result) -> dict:
        del should_stop
        check_cancel()
        progress("正在回填译文", 10)
        check_cancel()  # 写前再校验冻结 owner（含空→绑定）
        try:
            filled, out_dir = apply_translations_to_tl(
                manifest_path,
                translated_txt,
                output_tl_dir,
                source_tl_dir=source_tl,
                confirm_overwrite=bool(body.confirm_overwrite),
            )
        except TlTextExporterError as exc:
            raise RuntimeError(str(exc)) from exc
        touch_result({
            "written": True,
            "partial": True,
            "success": False,
            "action": "apply",
            "filled": filled,
            "output_tl_dir": str(Path(out_dir).resolve()),
            "manifest_path": str(manifest_path.resolve()),
            "translated_txt": str(translated_txt.resolve()),
            "message": f"已回填 {filled} 条译文（写入完成，收尾中）",
        })
        check_cancel()
        progress("回填完成", 100)
        return {
            "success": True,
            "written": True,
            "partial": False,
            "action": "apply",
            "filled": filled,
            "output_tl_dir": str(Path(out_dir).resolve()),
            "manifest_path": str(manifest_path.resolve()),
            "translated_txt": str(translated_txt.resolve()),
            "message": f"已回填 {filled} 条译文",
        }

    return await _start_job(
        request,
        kind=KIND_APPLY,
        project_key=target_key,
        message="回填译文生成新 TL",
        seed={
            "action": "apply",
            "manifest_path": str(manifest_path),
            "translated_txt": str(translated_txt),
            "output_tl_dir": str(output_tl_dir),
        },
        compute=compute,
        owner_identity=owner,
    )


@router.post("/html-to-txt")
async def convert_html_to_txt(request: Request, body: HtmlToTxtBody) -> dict:
    with CacheManager.LOCK:
        owner = _project_identity(request.app.state.config)
    _reject_stale_owner(body.owner_identity, owner)
    html_path = _require_existing_file(body.html_path, "HTML 文件")
    txt_output = (
        Path(body.txt_output.strip())
        if body.txt_output.strip()
        else default_sibling_output(html_path, ".txt")
    )
    _ensure_overwrite(txt_output, confirm=body.confirm_overwrite, label="TXT 输出")
    target_key = _job_key(body.project_key, str(html_path), str(txt_output))

    def compute(check_cancel, progress, should_stop, touch_result) -> dict:
        del should_stop
        check_cancel()
        progress("HTML → TXT", 20)
        check_cancel()
        count, written = html_to_txt(html_path, txt_output, pairs=body.pairs)
        touch_result({
            "written": True,
            "partial": True,
            "success": False,
            "action": "html_to_txt",
            "count": count,
            "output_path": str(written.resolve()),
            "message": f"已导出 {count} 行（写入完成，收尾中）",
        })
        check_cancel()
        progress("完成", 100)
        return {
            "success": True,
            "written": True,
            "partial": False,
            "action": "html_to_txt",
            "count": count,
            "output_path": str(written.resolve()),
            "message": f"已导出 {count} 行",
        }

    return await _start_job(
        request,
        kind=KIND_HTML_TO_TXT,
        project_key=target_key,
        message="HTML → TXT",
        seed={"action": "html_to_txt", "output_path": str(txt_output)},
        compute=compute,
        owner_identity=owner,
    )


@router.post("/txt-to-html")
async def convert_txt_to_html(request: Request, body: TxtToHtmlBody) -> dict:
    with CacheManager.LOCK:
        owner = _project_identity(request.app.state.config)
    _reject_stale_owner(body.owner_identity, owner)
    txt_path = _require_existing_file(body.txt_path, "TXT 文件")
    html_output = (
        Path(body.html_output.strip())
        if body.html_output.strip()
        else default_sibling_output(txt_path, ".html")
    )
    _ensure_overwrite(html_output, confirm=body.confirm_overwrite, label="HTML 输出")
    target_key = _job_key(body.project_key, str(txt_path), str(html_output))

    def compute(check_cancel, progress, should_stop, touch_result) -> dict:
        del should_stop
        check_cancel()
        progress("TXT → HTML", 20)
        check_cancel()
        count, written = txt_to_html(txt_path, html_output, keep_data=body.keep_data)
        touch_result({
            "written": True,
            "partial": True,
            "success": False,
            "action": "txt_to_html",
            "count": count,
            "output_path": str(written.resolve()),
            "message": f"已生成 HTML（{count} 行）（写入完成，收尾中）",
        })
        check_cancel()
        progress("完成", 100)
        return {
            "success": True,
            "written": True,
            "partial": False,
            "action": "txt_to_html",
            "count": count,
            "output_path": str(written.resolve()),
            "message": f"已生成 HTML（{count} 行）",
        }

    return await _start_job(
        request,
        kind=KIND_TXT_TO_HTML,
        project_key=target_key,
        message="TXT → HTML",
        seed={"action": "txt_to_html", "output_path": str(html_output)},
        compute=compute,
        owner_identity=owner,
    )


@router.post("/excel-to-txt")
async def convert_excel_to_txt(request: Request, body: ExcelToTxtBody) -> dict:
    with CacheManager.LOCK:
        owner = _project_identity(request.app.state.config)
    _reject_stale_owner(body.owner_identity, owner)
    excel_path = _require_existing_file(body.excel_path, "Excel 文件")
    if body.column not in _EXCEL_COLUMNS:
        raise HTTPException(status_code=400, detail="导出列无效")
    txt_output = (
        Path(body.txt_output.strip())
        if body.txt_output.strip()
        else default_sibling_output(excel_path, ".txt")
    )
    _ensure_overwrite(txt_output, confirm=body.confirm_overwrite, label="TXT 输出")
    target_key = _job_key(body.project_key, str(excel_path), str(txt_output))

    def compute(check_cancel, progress, should_stop, touch_result) -> dict:
        del should_stop
        check_cancel()
        progress("Excel → TXT", 20)
        check_cancel()
        try:
            count, written = excel_to_txt(excel_path, txt_output, column=body.column)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        touch_result({
            "written": True,
            "partial": True,
            "success": False,
            "action": "excel_to_txt",
            "count": count,
            "output_path": str(written.resolve()),
            "column": body.column,
            "message": f"已导出 {count} 行（写入完成，收尾中）",
        })
        check_cancel()
        progress("完成", 100)
        return {
            "success": True,
            "written": True,
            "partial": False,
            "action": "excel_to_txt",
            "count": count,
            "output_path": str(written.resolve()),
            "column": body.column,
            "message": f"已导出 {count} 行",
        }

    return await _start_job(
        request,
        kind=KIND_EXCEL_TO_TXT,
        project_key=target_key,
        message="Excel → TXT",
        seed={"action": "excel_to_txt", "output_path": str(txt_output)},
        compute=compute,
        owner_identity=owner,
    )


async def _start_job(
    request: Request,
    *,
    kind: str,
    project_key: str,
    message: str,
    seed: dict[str, Any],
    compute: Callable[..., dict],
    owner_identity: tuple[str, ...],
) -> dict:
    engine = _acquire_engine()
    manager = request.app.state.jobs
    try:
        job = manager.create(kind, total=100, cooperative_cancel=True)
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        raise
    # 冻结 owner（含全空字段）与 target 键；未绑定不得写成 None 而跳过守卫
    frozen_owner = tuple(owner_identity)
    job.result = {
        "project_key": project_key,
        "message": message,
        "written": False,
        "partial": False,
        "worker_active": True,
        "owner_identity": list(frozen_owner),
        **seed,
    }
    loop = asyncio.get_running_loop()

    def owner_still() -> bool:
        # 取消 truthiness：空串 tuple 也必须与 live 逐项比较
        with CacheManager.LOCK:
            live = request.app.state.config
        return _project_identity(live) == frozen_owner

    def check_cancel() -> None:
        """协作取消 + 冻结 owner；切项目/空→绑定后尚未写入时禁止继续。"""
        if job.cancel_event.is_set():
            raise asyncio.CancelledError()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")

    def should_stop() -> bool:
        return job.cancel_event.is_set()

    def publish(message_text: str, percent: int) -> None:
        if isinstance(job.result, dict):
            job.result["message"] = message_text
        manager.progress(job.id, done=max(0, min(100, int(percent))), total=100)

    def progress(message_text: str, percent: int = 0) -> None:
        loop.call_soon_threadsafe(lambda: publish(message_text, percent))

    def touch_result(patch: dict[str, Any]) -> None:
        # 同步固化 written/partial，避免取消竞态读到旧快照
        if isinstance(job.result, dict) and job.result.get("worker_active"):
            job.result.update(patch)
        loop.call_soon_threadsafe(lambda: manager.progress(job.id))

    def run_compute() -> dict:
        check_cancel()
        result = compute(check_cancel, progress, should_stop, touch_result)
        if isinstance(job.result, dict) and job.result.get("worker_active"):
            job.result.update(result)
        return result

    def _mark_partial_cancel() -> dict:
        assert isinstance(job.result, dict)
        job.result["written"] = True
        job.result["partial"] = True
        job.result["success"] = False
        job.result.setdefault("message", "任务已取消（已保留写入结果）")
        manager.progress(job.id, done=100, total=100)
        return job.result

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
                    return _mark_partial_cancel()
                raise
            if isinstance(job.result, dict):
                job.result.update(result)
                if job.cancel_event.is_set() and job.result.get("written"):
                    return _mark_partial_cancel()
                if job.cancel_event.is_set():
                    job.result["message"] = "任务已取消"
                    raise asyncio.CancelledError()
            manager.progress(job.id, done=100, total=100)
            return job.result
        except asyncio.CancelledError:
            if isinstance(job.result, dict) and job.result.get("written"):
                return _mark_partial_cancel()
            if isinstance(job.result, dict):
                job.result["message"] = "任务已取消"
            raise
        except Exception as exc:
            if isinstance(job.result, dict) and job.result.get("written"):
                job.result["partial"] = True
                job.result["success"] = False
                job.result["message"] = str(exc) or job.result.get("message") or "任务失败"
                if job.cancel_event.is_set():
                    manager.progress(job.id, done=100, total=100)
                    return job.result
                raise
            if job.cancel_event.is_set():
                if isinstance(job.result, dict):
                    job.result["message"] = "任务已取消"
                raise asyncio.CancelledError() from exc
            if isinstance(job.result, dict):
                job.result["message"] = str(exc)
                job.result["written"] = bool(job.result.get("written"))
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
