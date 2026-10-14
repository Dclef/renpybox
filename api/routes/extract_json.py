"""文本提取 JSON：复用 RenpyExtractor / JsonImporter，对齐 Qt ExtractTab。"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import os
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from api.jobs import Job
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Extract.RenpyExtractor import RenpyExtractor
from module.Extract.GameExtractionRules import project_key as derive_project_key
from module.Renpy.json_handler import JsonExporter, JsonImporter
from module.Renpy import renpy_extract as rx
from module.Renpy.ProjectPaths import RenpyProjectPaths

router = APIRouter(prefix="/api/extract-json", tags=["extract-json"])

KIND_PREVIEW = "extract_json_preview"
KIND_EXPORT = "extract_json_export"
KIND_IMPORT = "extract_json_import"
KIND_CLEANUP = "extract_json_cleanup"
KIND_EXPORT_TL = "extract_json_export_tl"
KINDS = (KIND_PREVIEW, KIND_EXPORT, KIND_IMPORT, KIND_CLEANUP, KIND_EXPORT_TL)
_BUSY = "已有任务正在运行或收尾，请稍后再试"
def _norm(value: str) -> str:
    return os.path.normcase(os.path.abspath(value)) if value else ""


def _project_identity(config: Any) -> tuple[str, ...]:
    """绑定项目 owner 身份；与手动 game_file 目标键分开。"""
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


class PreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    game_file: str = ""
    language: str = "chinese"
    ensure_official: bool = True


class ExportJsonBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    game_file: str = ""
    language: str = "chinese"
    output_path: str = Field(min_length=1)
    force_extract: bool = True
    include_metadata: bool = True


class ImportApplyBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    game_file: str = ""
    language: str = "chinese"
    json_path: str = Field(min_length=1)
    backup: bool = True


class CleanupBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    game_file: str = ""
    language: str = "chinese"


class ExportTlJsonBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    game_file: str = ""
    language: str = "chinese"
    output_path: str = Field(min_length=1)
    include_metadata: bool = True


def current_paths(config: Any) -> RenpyProjectPaths | None:
    return RenpyProjectPaths.from_config(config)


def _resolve_operation(
    config: Any,
    *,
    game_file: str,
    body_project_key: str,
    language: str = "chinese",
) -> tuple[str, str, Path, RenpyProjectPaths | None]:
    """解析任务上下文：未绑定项目时仅凭 game_file；任务键始终为目标键。

    body_project_key 可匹配目标键，或（已绑定且手选其它目录时）匹配 owner 键；
    不把合法目标 B 强卡成绑定 A。
    """
    bound = current_paths(config)
    fallback_root = bound.project_root if bound is not None else Path.cwd()
    game_text = str(game_file or "").strip()
    if not game_text:
        if bound is None:
            raise HTTPException(status_code=400, detail="game_file 必填")
        target, project_root = resolve_game_target("", bound.project_root)
    else:
        target, project_root = resolve_game_target(game_text, fallback_root)

    # 任务键用带语言的路径键，与 GET status / 绑定项目一致
    paths = RenpyProjectPaths.from_path(project_root, language)
    resolved_key = paths.project_key if paths is not None else derive_project_key(project_root)
    body_key = str(body_project_key or "").strip()
    if body_key:
        allowed = {resolved_key}
        if bound is not None:
            allowed.add(bound.project_key)
        if body_key not in allowed:
            raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    return resolved_key, target, project_root, bound


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


def _safe_language(language: str) -> str:
    name = str(language or "").strip() or "chinese"
    if name in {".", ".."} or any(ch in name for ch in '/\\<>:"|?*'):
        raise HTTPException(status_code=400, detail="语言名无效")
    return name


def resolve_game_target(raw: str, fallback_root: Path) -> tuple[str, Path]:
    """解析 EXE / 项目根；返回 (target_for_extractor, project_root)。"""
    text = str(raw or "").strip()
    if not text:
        root = fallback_root
        return str(root), root
    path = Path(text).expanduser().resolve(strict=False)
    if path.is_file():
        return str(path), path.parent
    if path.name.lower() == "game":
        return str(path.parent), path.parent
    if (path / "game").is_dir():
        return str(path), path
    raise HTTPException(status_code=400, detail="未找到有效的游戏可执行文件或项目目录")


def _tl_dir(project_root: Path, language: str) -> Path:
    return project_root / "game" / "tl" / language


def _describe_json_target(
    project_root: Path,
    *,
    language: str,
    default_game_file: str,
    owner_key: str = "",
) -> dict[str, Any]:
    # 与 RenpyProjectPaths.project_key 对齐（含语言段），避免仅路径派生丢语言
    paths = RenpyProjectPaths.from_path(project_root, language)
    key = paths.project_key if paths is not None else derive_project_key(project_root)
    game_dir = project_root / "game"
    return {
        "project_key": key,
        "project_root": str(project_root),
        "game_dir": str(game_dir) if game_dir.is_dir() else "",
        "language": language,
        "tl_dir": str(_tl_dir(project_root, language)),
        "default_game_file": default_game_file or str(project_root),
        "owner_project_key": owner_key,
    }


@router.get("")
def read_status(
    request: Request,
    game_file: str = Query(default=""),
    language: str = Query(default="chinese"),
) -> dict:
    """绑定/手动目标状态与最近 JSON 工具任务；可按 game_file+language 定位目标任务。"""
    lang = _safe_language(language)
    with CacheManager.LOCK:
        config = request.app.state.config
        bound = current_paths(config)
        owner_key = bound.project_key if bound is not None else ""
        raw = str(game_file or "").strip()
        if raw:
            try:
                _, project_root = resolve_game_target(
                    raw,
                    bound.project_root if bound is not None else Path.cwd(),
                )
            except HTTPException:
                payload = {
                    "project_key": "",
                    "project_root": "",
                    "game_dir": "",
                    "language": lang,
                    "tl_dir": "",
                    "default_game_file": "",
                    "owner_project_key": owner_key,
                }
                project_key = ""
            else:
                payload = _describe_json_target(
                    project_root,
                    language=lang,
                    default_game_file=raw,
                    owner_key=owner_key,
                )
                project_key = payload["project_key"]
        elif bound is not None and bound.game_dir.is_dir():
            language_bound = bound.language or lang
            payload = _describe_json_target(
                bound.project_root,
                language=language_bound,
                default_game_file=str(bound.project_root),
                owner_key=owner_key,
            )
            project_key = bound.project_key
        else:
            payload = {
                "project_key": "",
                "project_root": "",
                "game_dir": "",
                "language": lang,
                "tl_dir": "",
                "default_game_file": "",
                "owner_project_key": "",
            }
            project_key = ""
    job = _latest_job(request, project_key) if project_key else None
    payload["job"] = job.snapshot() if job else None
    return payload


@router.post("/preview")
async def preview(request: Request, body: PreviewBody) -> dict:
    """统计可导出条目：文件数 + 条目数。"""
    language = _safe_language(body.language)
    with CacheManager.LOCK:
        project_key, target, project_root, bound = _resolve_operation(
            request.app.state.config,
            game_file=body.game_file,
            body_project_key=body.project_key,
            language=language,
        )
        owner_identity = _project_identity(request.app.state.config) if bound is not None else None
    return await _start_job(
        request,
        kind=KIND_PREVIEW,
        project_key=project_key,
        message="准备预览抽取条目",
        owner_identity=owner_identity,
        seed={
            "action": "preview",
            "language": language,
            "game_file": target,
            "project_root": str(project_root),
            "written": False,
        },
        compute=lambda check_cancel, progress, should_stop: _run_preview(
            target, language, ensure_official=body.ensure_official,
            check_cancel=check_cancel, progress=progress, should_stop=should_stop,
        ),
    )


@router.post("/export-json")
async def export_json(request: Request, body: ExportJsonBody) -> dict:
    """官方抽取后导出结构化 JSON 到用户路径。"""
    language = _safe_language(body.language)
    output = Path(body.output_path).expanduser()
    with CacheManager.LOCK:
        project_key, target, project_root, bound = _resolve_operation(
            request.app.state.config,
            game_file=body.game_file,
            body_project_key=body.project_key,
            language=language,
        )
        owner_identity = _project_identity(request.app.state.config) if bound is not None else None
    return await _start_job(
        request,
        kind=KIND_EXPORT,
        project_key=project_key,
        message="准备导出 JSON",
        owner_identity=owner_identity,
        seed={
            "action": "export_json",
            "language": language,
            "game_file": target,
            "output_path": str(output),
            "project_root": str(project_root),
            "written": False,
        },
        compute=lambda check_cancel, progress, should_stop: _run_export_json(
            target, language, str(output),
            force_extract=body.force_extract,
            include_metadata=body.include_metadata,
            check_cancel=check_cancel, progress=progress, should_stop=should_stop,
        ),
    )


@router.post("/import-apply")
async def import_apply(request: Request, body: ImportApplyBody) -> dict:
    """从 JSON 导入并应用到 tl/<lang>。"""
    language = _safe_language(body.language)
    json_path = Path(body.json_path).expanduser()
    if not json_path.is_file():
        raise HTTPException(status_code=400, detail="JSON 文件不存在")
    with CacheManager.LOCK:
        project_key, target, project_root, bound = _resolve_operation(
            request.app.state.config,
            game_file=body.game_file,
            body_project_key=body.project_key,
            language=language,
        )
        if not (project_root / "game").is_dir():
            raise HTTPException(status_code=400, detail="未找到 game 目录")
        owner_identity = _project_identity(request.app.state.config) if bound is not None else None
    return await _start_job(
        request,
        kind=KIND_IMPORT,
        project_key=project_key,
        message="准备导入 JSON 到 TL",
        owner_identity=owner_identity,
        seed={
            "action": "import_apply",
            "language": language,
            "json_path": str(json_path),
            "project_root": str(project_root),
            "game_file": target,
            "written": False,
        },
        compute=lambda check_cancel, progress, should_stop: _run_import(
            str(project_root), language, str(json_path),
            backup=body.backup,
            check_cancel=check_cancel, progress=progress, should_stop=should_stop,
        ),
    )


@router.post("/cleanup")
async def cleanup(request: Request, body: CleanupBody) -> dict:
    """清理 tl 重复条目与多余空行。"""
    language = _safe_language(body.language)
    with CacheManager.LOCK:
        project_key, _, project_root, bound = _resolve_operation(
            request.app.state.config,
            game_file=body.game_file,
            body_project_key=body.project_key,
            language=language,
        )
        tl_dir = _tl_dir(project_root, language)
        if not tl_dir.is_dir():
            raise HTTPException(status_code=400, detail=f"未找到 tl 目录: {tl_dir}")
        duplicate_action = str(
            getattr(request.app.state.config, "renpy_duplicate_string_action", "comment") or "comment"
        )
        owner_identity = _project_identity(request.app.state.config) if bound is not None else None
    return await _start_job(
        request,
        kind=KIND_CLEANUP,
        project_key=project_key,
        message="准备清理 TL 重复",
        owner_identity=owner_identity,
        seed={
            "action": "cleanup",
            "language": language,
            "tl_dir": str(tl_dir),
            "project_root": str(project_root),
            "written": False,
        },
        compute=lambda check_cancel, progress, should_stop: _run_cleanup(
            str(tl_dir), duplicate_action=duplicate_action,
            check_cancel=check_cancel, progress=progress, should_stop=should_stop,
        ),
    )


@router.post("/export-tl-json")
async def export_tl_json(request: Request, body: ExportTlJsonBody) -> dict:
    """把已有 tl 导出为 JSON（不跑官方抽取）。"""
    language = _safe_language(body.language)
    output = Path(body.output_path).expanduser()
    with CacheManager.LOCK:
        project_key, _, project_root, bound = _resolve_operation(
            request.app.state.config,
            game_file=body.game_file,
            body_project_key=body.project_key,
            language=language,
        )
        tl_dir = _tl_dir(project_root, language)
        if not tl_dir.is_dir():
            raise HTTPException(status_code=400, detail=f"未找到 tl 目录: {tl_dir}")
        owner_identity = _project_identity(request.app.state.config) if bound is not None else None
    return await _start_job(
        request,
        kind=KIND_EXPORT_TL,
        project_key=project_key,
        message="准备导出 TL JSON",
        owner_identity=owner_identity,
        seed={
            "action": "export_tl_json",
            "language": language,
            "tl_dir": str(tl_dir),
            "output_path": str(output),
            "project_root": str(project_root),
            "written": False,
        },
        compute=lambda check_cancel, progress, should_stop: _run_export_tl(
            project_root, language, str(output), include_metadata=body.include_metadata,
            check_cancel=check_cancel, progress=progress, should_stop=should_stop,
        ),
    )


def _run_preview(
    game_file: str,
    language: str,
    *,
    ensure_official: bool,
    check_cancel: Callable[[], None],
    progress: Callable[[str, int], None],
    should_stop: Callable[[], bool],
) -> dict:
    check_cancel()
    progress("正在统计条目", 20)
    extractor = RenpyExtractor()
    entries = extractor.collect_entries(
        game_file,
        language,
        ensure_official=ensure_official,
        force=False,
        should_stop=should_stop,
        progress_callback=lambda msg: progress(msg, 40),
    )
    check_cancel()
    file_count: dict[str, int] = {}
    for entry in entries:
        name = entry.get("file", "unknown")
        file_count[name] = file_count.get(name, 0) + 1
    progress("预览完成", 100)
    return {
        "success": True,
        "written": False,
        "file_count": len(file_count),
        "entry_count": len(entries),
        "language": language,
        "message": f"找到 {len(file_count)} 个文件、{len(entries)} 条文本",
    }


def _run_export_json(
    game_file: str,
    language: str,
    output_path: str,
    *,
    force_extract: bool,
    include_metadata: bool,
    check_cancel: Callable[[], None],
    progress: Callable[[str, int], None],
    should_stop: Callable[[], bool],
) -> dict:
    check_cancel()
    progress("正在抽取并导出 JSON", 30)
    extractor = RenpyExtractor()
    ok = extractor.export_to_json(
        game_file,
        language,
        output_path,
        include_metadata=include_metadata,
        force_extract=force_extract,
        should_stop=should_stop,
        progress_callback=lambda msg: progress(msg, 50),
    )
    # 文件已落盘时，取消也必须带回 written 副作用，不能先 check_cancel 丢结果
    written = bool(ok and Path(output_path).is_file())
    if written:
        progress("导出完成", 100)
        cancelled = should_stop()
        return {
            "success": not cancelled,
            "written": True,
            "partial": cancelled,
            "output_path": output_path,
            "language": language,
            "message": (
                f"JSON 已导出到 {output_path}（随后取消）"
                if cancelled
                else f"JSON 已导出到 {output_path}"
            ),
        }
    check_cancel()
    raise RuntimeError("未提取到文本，导出已跳过")


def _run_import(
    project_root: str,
    language: str,
    json_path: str,
    *,
    backup: bool,
    check_cancel: Callable[[], None],
    progress: Callable[[str, int], None],
    should_stop: Callable[[], bool],
) -> dict:
    check_cancel()
    progress("正在导入 JSON", 20)
    importer = JsonImporter()
    translations = importer.import_translations(json_path)
    check_cancel()
    if not translations:
        raise RuntimeError("JSON 中没有可用翻译条目")
    progress("正在应用到 TL", 60)
    apply_meta: dict[str, Any] = {}
    ok = importer.apply_translations(
        translations,
        project_root,
        target_language=language,
        backup=backup,
        should_stop=should_stop,
        result_meta=apply_meta,
    )
    # 必须先提取副作用元数据，再决定取消终态；禁止 check_cancel 先抛丢 written_files
    written_files = list(apply_meta.get("written_files") or [])
    backup_paths = list(apply_meta.get("backup_paths") or [])
    partial = bool(apply_meta.get("partial")) or (bool(written_files) and (not ok or should_stop()))
    base = {
        "language": language,
        "written_files": written_files,
        "backup_paths": backup_paths,
        "partial": partial,
    }
    if written_files:
        progress("导入已写入" if ok and not partial else "导入已部分写入", 90 if partial else 100)
        total_files = len(written_files) if partial else len(translations)
        total_entries = 0 if partial else sum(len(items) for items in translations.values())
        return {
            "success": bool(ok) and not partial,
            "written": True,
            "file_count": total_files,
            "entry_count": total_entries,
            "message": (
                "导入已取消或失败，部分文件已写入"
                if partial or not ok
                else f"已应用到 tl/{language}：{total_files} 个文件、{total_entries} 条"
            ),
            **base,
        }
    check_cancel()
    raise RuntimeError("应用翻译失败")


def _run_cleanup(
    tl_dir: str,
    *,
    duplicate_action: str,
    check_cancel: Callable[[], None],
    progress: Callable[[str, int], None],
    should_stop: Callable[[], bool],
) -> dict:
    check_cancel()
    progress("正在清理重复条目", 40)
    meta: dict[str, Any] = {}
    try:
        rx.remove_repeat_extracted_from_tl(
            tl_dir,
            is_py2=False,
            duplicate_action=duplicate_action,
            should_stop=should_stop,
            progress_callback=lambda msg: progress(str(msg), 60),
            result_meta=meta,
        )
    except rx.ExtractionCancelled:
        written_files = list(meta.get("written_files") or [])
        if written_files:
            progress("清理已部分写入后取消", 90)
            return {
                "success": False,
                "written": True,
                "partial": True,
                "written_files": written_files,
                "tl_dir": tl_dir,
                "message": f"TL 清理已写入后取消：{tl_dir}",
            }
        raise asyncio.CancelledError()
    written_files = list(meta.get("written_files") or [])
    cancelled = should_stop()
    written = bool(written_files)
    progress("清理完成", 100)
    return {
        "success": not cancelled,
        "written": written,
        "partial": bool(cancelled and written),
        "written_files": written_files,
        "tl_dir": tl_dir,
        "message": (
            f"TL 清理已写入后取消：{tl_dir}"
            if cancelled and written
            else (
                f"TL 清理完成（无文件变更）：{tl_dir}"
                if not written
                else f"TL 清理完成：{tl_dir}"
            )
        ),
    }


def _run_export_tl(
    project_root: Path,
    language: str,
    output_path: str,
    *,
    include_metadata: bool,
    check_cancel: Callable[[], None],
    progress: Callable[[str, int], None],
    should_stop: Callable[[], bool],
) -> dict:
    check_cancel()
    progress("正在读取 TL", 20)
    extractor = RenpyExtractor()
    entries = extractor._parse_tl_directory(project_root, language)
    data: dict[str, list[dict]] = {}
    for entry in entries:
        if should_stop():
            raise asyncio.CancelledError()
        check_cancel()
        if entry.get("type") != "strings":
            continue
        rel = str(entry.get("file") or "")
        if not rel:
            continue
        data.setdefault(rel, []).append({
            "line": entry.get("line", 0),
            "original": entry.get("original", ""),
            "translation": entry.get("translation", ""),
            "type": "strings",
            "status": "pending",
        })
    if should_stop():
        raise asyncio.CancelledError()
    if not data:
        raise RuntimeError("TL 中没有可导出条目")
    progress("正在写入 JSON", 80)
    exporter = JsonExporter()
    if not exporter.export(copy.deepcopy(data), output_path, include_metadata=include_metadata):
        raise RuntimeError("TL JSON 导出失败")
    total_files = len(data)
    total_entries = sum(len(v) for v in data.values())
    cancelled = should_stop()
    progress("导出完成", 100)
    return {
        "success": not cancelled,
        "written": True,
        "partial": cancelled,
        "output_path": output_path,
        "file_count": total_files,
        "entry_count": total_entries,
        "message": (
            f"已导出 {total_files} 个文件、{total_entries} 条（随后取消）"
            if cancelled
            else f"已导出 {total_files} 个文件、{total_entries} 条"
        ),
    }


async def _start_job(
    request: Request,
    *,
    kind: str,
    project_key: str,
    message: str,
    seed: dict[str, Any],
    compute: Callable[
        [Callable[[], None], Callable[[str, int], None], Callable[[], bool]],
        dict,
    ],
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
        "message": message,
        "written": False,
        "worker_active": True,
        **seed,
    }
    loop = asyncio.get_running_loop()
    snapshot_root = str(seed.get("project_root") or "")
    snapshot_language = str(seed.get("language") or "chinese")
    identity = owner_identity

    def owner_still() -> bool:
        # 有绑定 owner：校验配置身份未切换；无绑定：校验目标根仍对应任务键
        if identity is not None:
            with CacheManager.LOCK:
                live = request.app.state.config
            return _project_identity(live) == identity
        if snapshot_root:
            paths = RenpyProjectPaths.from_path(Path(snapshot_root), snapshot_language)
            if paths is not None:
                return paths.project_key == project_key
            return derive_project_key(Path(snapshot_root)) == project_key
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

    def run_compute() -> dict:
        check_cancel()
        if not owner_still():
            raise RuntimeError("项目已切换，未执行操作")
        check_cancel()
        result = compute(check_cancel, progress, should_stop)
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
                    # 保留副作用；不 clear cancel，终态保持 cancelled
                    job.result.setdefault("partial", True)
                    job.result.setdefault("success", False)
                    job.result.setdefault("message", "任务已取消（已保留写入结果）")
                    manager.progress(job.id, done=100, total=100)
                    return job.result
                raise
            if isinstance(job.result, dict):
                job.result.update(result)
                if job.cancel_event.is_set() and job.result.get("written"):
                    # 已有副作用：保留 payload，取消标志不清，终态 cancelled
                    job.result.setdefault("partial", True)
                    job.result["success"] = False
                    if not job.result.get("message"):
                        job.result["message"] = "任务已取消（已保留写入结果）"
                    manager.progress(job.id, done=100, total=100)
                    return job.result
                if job.cancel_event.is_set():
                    job.result["message"] = "任务已取消"
                    raise asyncio.CancelledError()
                if job.result.get("written") and job.result.get("success") is False:
                    # 失败部分写入：保留 result，抛错使 JobManager 记 failed
                    raise RuntimeError(
                        job.result.get("message") or "任务失败（已保留写入结果）"
                    )
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
                job.result["message"] = (
                    str(exc) or job.result.get("message") or "任务结束（已保留写入结果）"
                )
                if job.cancel_event.is_set():
                    # 取消路径：保持 cancel 标志 → cancelled
                    manager.progress(job.id, done=100, total=100)
                    return job.result
                # 非取消失败：再抛一次让 JobManager 记 failed（result 已含副作用）
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
