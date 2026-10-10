"""一键翻译：检测、解包/反编译/抽取、路径准备与应用译文。

翻译启停复用 /api/translation，不在此另建翻译器。
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import os
from pathlib import Path, PureWindowsPath
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from api.jobs import Job
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Extract.ReplaceGenerator import (
    clear_declined_candidates,
    declined_candidates_path,
    load_declined_candidates,
)
from module.Extract.UnifiedExtractor import UnifiedExtractor
from module.OneKey.flow import (
    apply_full_translation,
    apply_incremental_translation,
    configure_incremental_translation_paths,
    configure_main_translation_paths,
    detect_game_status,
    existing_translation_summary,
    extract_project_text,
    prepare_extraction_paths,
    resolve_extraction_incremental,
)
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Tool.ArchiveOps import decompile_target, unpack_game
from module.Tool.RenpyDecompiler import RenpyDecompiler

router = APIRouter(prefix="/api/onekey", tags=["onekey"])

ONEKEY_KINDS = ("onekey_prepare", "onekey_apply")


class OneKeyBase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    game_dir: str = ""
    language: str = Field(min_length=1, max_length=64)


class DetectBody(OneKeyBase):
    pass


class PrepareBody(OneKeyBase):
    incremental: bool = False
    # None 为旧 API 调用，沿用 incremental 字段；auto 按是否已有译文自动选择。
    mode: Literal["auto", "full", "incremental"] | None = None
    confirm_write: bool = False
    # None 为旧 API 调用，保留自动查找游戏 EXE；False 表示明确关闭官方抽取。
    official_extract: bool | None = None
    exe_path: str | None = None
    # None 表示沿用已保存配置；UnifiedExtractor 从磁盘配置读取，因此显式值会先落盘。
    supplement_mode: Literal["off", "precise", "aggressive"] | None = None
    inject_ui_pack: bool | None = None


class ApplyBody(OneKeyBase):
    incremental: bool = False
    confirm: bool = False
    incremental_output: str | None = None
    incremental_target: str | None = None
    main_output: str | None = None
    # None 表示读取 renpy_incremental_auto_merge_cleanup；只影响增量合并后的去重清理。
    auto_merge_cleanup: bool | None = None


class DeclinedClearBody(OneKeyBase):
    confirm: bool = False


def _norm(value: str) -> str:
    return os.path.normcase(os.path.abspath(value)) if value else ""


def _safe_language(language: str) -> str:
    text = str(language or "").strip()
    if (
        not text or text.endswith((".", " ")) or PureWindowsPath(text).is_reserved()
        or any(ord(char) < 32 or char in '<>:"/\\|?*' for char in text)
        or text in {".", ".."}
    ):
        raise HTTPException(status_code=400, detail="语言目录名非法")
    return text


def _resolve_game_snapshot(config: Any, game_dir: str, language: str) -> tuple[RenpyProjectPaths, str]:
    language = _safe_language(language)
    raw = str(game_dir or "").strip() or getattr(config, "renpy_project_path", "") or getattr(config, "renpy_game_folder", "")
    if not raw:
        raise HTTPException(status_code=400, detail="请先选择游戏目录")
    paths = RenpyProjectPaths.from_path(raw, language)
    if paths is None or not paths.game_dir.is_dir():
        raise HTTPException(status_code=400, detail="路径不是有效的 Ren'Py 项目")
    if paths.language != language:
        raise HTTPException(status_code=400, detail="语言名不能是保留目录或增量目录名")
    return paths, language


def _ensure_project_key(body_key: str, paths: RenpyProjectPaths) -> str:
    current = paths.project_key
    if body_key and body_key != current:
        raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
    return current


def _acquire_engine() -> Engine:
    engine = Engine.get()
    if engine.has_stop_barrier() or engine.has_single_tasks():
        raise HTTPException(status_code=409, detail="已有任务正在运行或收尾，请稍后再试")
    if not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
        raise HTTPException(status_code=409, detail="已有任务正在运行或收尾，请稍后再试")
    return engine


def _project_identity(config: Any) -> tuple[str, ...]:
    return tuple(_norm(str(getattr(config, field, "") or "")) for field in (
        "renpy_project_path", "renpy_game_folder", "renpy_tl_folder", "input_folder", "output_folder",
    ))


def _persist_project_paths(live: Any, configured: Any) -> None:
    """只在磁盘保存成功后更新共享配置，保留任务期间其他设置改动。"""
    fields = (
        "renpy_project_path", "renpy_game_folder", "renpy_tl_folder",
        "input_folder", "output_folder", "renpy_source_translate", "renpy_hook_translate",
    )
    candidate = copy.deepcopy(live)
    for field in fields:
        setattr(candidate, field, getattr(configured, field))
    candidate.save(strict=True)
    for field in fields:
        setattr(live, field, getattr(candidate, field))


def _persist_fields(live: Any, values: dict[str, Any]) -> None:
    """抽取选项先写盘再更新共享配置；写盘失败时共享配置保持原样。"""
    if not values:
        return
    candidate = copy.deepcopy(live)
    for field, value in values.items():
        setattr(candidate, field, value)
    candidate.save(strict=True)
    for field, value in values.items():
        setattr(live, field, value)


def _derived_layout(paths: RenpyProjectPaths) -> dict:
    """返回由项目身份派生的写入范围，供确认框逐项展示。"""
    language = paths.language
    return {
        "tl_dir": str(paths.tl_language_dir),
        "incremental_dir": str(paths.tl_root / f"{language}_new"),
        "output_dir": str(paths.translation_output_dir),
        "incremental_output_dir": str(paths.translation_output_dir.parent / f"{language}_new"),
        "full_backup_pattern": str(paths.project_root / f"tl_backup_{language}_<时间戳>"),
        "ui_pack_dir": str(paths.tl_language_dir / "base_box"),
    }


def _latest_job(request: Request, kind: str | None = None, project_key: str | None = None) -> Job | None:
    key = project_key
    if key is None:
        paths = RenpyProjectPaths.from_config(request.app.state.config)
        key = paths.project_key if paths else ""
    kinds = (kind,) if kind else ONEKEY_KINDS
    return next(
        (
            job for job in request.app.state.jobs.list()
            if job.kind in kinds and isinstance(job.result, dict)
            and (
                job.result.get("project_key") == key
                or job.result.get("owner_identity") == _project_identity(request.app.state.config)
            )
        ),
        None,
    )


@router.get("")
def read_onekey(request: Request) -> dict:
    """返回当前项目最近一次一键准备或应用任务。"""
    job = _latest_job(request)
    return {"job": job.snapshot() if job else None}


@router.post("/detect")
def detect(request: Request, body: DetectBody) -> dict:
    """同步检测是否需要解包/反编译。"""
    with CacheManager.LOCK:
        config = request.app.state.config
        paths, language = _resolve_game_snapshot(config, body.game_dir, body.language)
        project_key = _ensure_project_key(body.project_key, paths)
    status, message = detect_game_status(str(paths.project_root), language)
    auto_exe = RenpyDecompiler()._find_game_exe(paths.project_root)
    if auto_exe is not None:
        resolved = Path(auto_exe).resolve()
        # 只展示会被 prepare 接受的 EXE，避免确认框显示一个随后被拒绝的路径。
        auto_exe = str(resolved) if resolved.is_file() and resolved.parent == paths.project_root else None
    return {
        "project_key": project_key,
        "game_dir": str(paths.game_dir),
        "project_root": str(paths.project_root),
        "language": language,
        "status": status,
        "message": message,
        "existing_translation": existing_translation_summary(paths),
        "layout": _derived_layout(paths),
        "auto_exe": auto_exe,
        "declined_count": len(load_declined_candidates(paths.project_root, language)),
        "declined_path": str(declined_candidates_path(paths.project_root, language)),
    }


@router.post("/declined/clear")
def clear_declined(request: Request, body: DeclinedClearBody) -> dict:
    """确认后清除当前项目的大写缩写“判定不译”清单（旧 Qt 同名按钮）。"""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="清除判定不译清单需要 confirm=true")
    with CacheManager.LOCK:
        paths, language = _resolve_game_snapshot(request.app.state.config, body.game_dir, body.language)
        project_key = _ensure_project_key(body.project_key, paths)
    # 翻译收尾会追加该清单，运行期间清除会与写入竞争。
    engine = _acquire_engine()
    try:
        cleared = clear_declined_candidates(paths.project_root, language)
    finally:
        engine.release_status(Engine.Status.TESTING)
    if declined_candidates_path(paths.project_root, language).exists():
        # 旧函数删除失败时只记日志并返回 0，这里不能把失败报告成“清单为空”。
        raise HTTPException(status_code=500, detail="判定不译清单删除失败，请检查文件占用或权限")
    return {"project_key": project_key, "language": language, "cleared": cleared}


@router.post("/prepare")
async def prepare(request: Request, body: PrepareBody) -> dict:
    """检测 → 必要解包/反编译 → 抽取 → 配置翻译路径。不自动启动收费翻译。"""
    if not body.confirm_write:
        raise HTTPException(status_code=400, detail="抽取可能写入文件，需要 confirm_write=true")
    with CacheManager.LOCK:
        live = request.app.state.config
        paths, language = _resolve_game_snapshot(live, body.game_dir, body.language)
        project_key = _ensure_project_key(body.project_key, paths)
        owner_identity = _project_identity(live)
        config = copy.deepcopy(live)
    game_root = str(paths.project_root)
    game_dir = str(paths.game_dir)
    existing = existing_translation_summary(paths)
    if body.mode is None:
        incremental = bool(body.incremental)
    else:
        incremental = resolve_extraction_incremental(body.mode, bool(existing["exists"]))
    if body.official_extract is False and body.supplement_mode == "off":
        raise HTTPException(status_code=400, detail="未启用官方抽取时不能选择“仅官方抽取”，否则没有可执行的抽取方式")
    if body.official_extract is False:
        selected_exe = None
    else:
        selected_exe = body.exe_path or RenpyDecompiler()._find_game_exe(paths.project_root)
    exe_path = None
    if selected_exe:
        executable = Path(selected_exe).resolve()
        if not executable.is_file() or executable.suffix.lower() != ".exe" or executable.parent != paths.project_root:
            raise HTTPException(status_code=400, detail="游戏可执行文件必须位于当前项目根目录")
        exe_path = str(executable)
    # 与旧 Qt 下拉框一致：off 即“仅官方抽取”，同步关闭补充抽取总开关。
    option_values: dict[str, Any] = {}
    if body.supplement_mode is not None:
        option_values["extract_supplement_mode"] = body.supplement_mode
        option_values["extract_use_custom"] = body.supplement_mode != "off"
    if body.inject_ui_pack is not None:
        option_values["onekey_inject_base_box"] = bool(body.inject_ui_pack)
    if exe_path and not getattr(live, "extract_use_official", True):
        # 抽取器还会检查该开关；用户已明确选择并确认 EXE，不能被旧配置静默跳过。
        option_values["extract_use_official"] = True
    engine = _acquire_engine()
    manager = request.app.state.jobs
    try:
        with CacheManager.LOCK:
            live = request.app.state.config
            if _project_identity(live) != owner_identity:
                raise HTTPException(status_code=409, detail="项目已切换，请重新加载后再操作")
            try:
                _persist_fields(live, option_values)
            except Exception:
                raise HTTPException(status_code=500, detail="抽取选项保存失败，未开始准备") from None
        job = manager.create("onekey_prepare", cooperative_cancel=True)
    except BaseException:
        engine.release_status(Engine.Status.TESTING)
        raise
    job.result = {
        "project_key": project_key,
        "game_dir": game_dir,
        "project_root": game_root,
        "owner_identity": owner_identity,
        "language": language,
        "incremental": incremental,
        "mode": body.mode or ("incremental" if incremental else "full"),
        "existing_translation": existing,
        "official_exe": exe_path,
        "supplement_mode": str(getattr(live, "extract_supplement_mode", "precise") or "precise")
        if getattr(live, "extract_use_custom", True) else "off",
        "inject_ui_pack": bool(getattr(live, "onekey_inject_base_box", False)),
        "message": "准备检测项目",
        "worker_active": True,
        "stage": "detect",
    }
    loop = asyncio.get_running_loop()

    def check_cancel() -> None:
        if job.cancel_event.is_set():
            raise asyncio.CancelledError()

    def publish(message: str, *, stage: str | None = None, done: int | None = None, total: int | None = None) -> None:
        if not isinstance(job.result, dict) or not job.result.get("worker_active"):
            return
        job.result["message"] = message
        if stage:
            job.result["stage"] = stage
        manager.progress(job.id, done=done, total=total)

    def progress(message: str, percent: int = 0, *, stage: str | None = None) -> None:
        # 子进程日志可能由读取线程回调，取消只能在任务阶段边界检查。
        if job.cancel_event.is_set():
            return
        loop.call_soon_threadsafe(
            lambda: publish(message, stage=stage, done=percent, total=100 if percent else None)
        )

    def compute() -> dict:
        check_cancel()
        progress("正在检测脚本状态", 5, stage="detect")
        status, message = detect_game_status(
            game_root, language, cancel_check=lambda: job.cancel_event.is_set(),
        )
        if status == "cancelled":
            raise asyncio.CancelledError()
        if status == "error":
            raise RuntimeError(message or "脚本检测失败")
        if status == "empty":
            raise RuntimeError(message or "没有可抽取的脚本")
        job.result["detect_status"] = status
        job.result["detect_message"] = message

        if status == "need_unpack":
            progress("正在解包 RPA", 15, stage="unpack")
            unpack = unpack_game(game_dir, direct=True, script_only=False, progress_callback=lambda m: progress(m, 20, stage="unpack"))
            check_cancel()
            if not unpack.get("success"):
                raise RuntimeError(unpack.get("message") or "解包失败")
            job.result["unpack"] = {k: unpack[k] for k in ("success", "method", "count", "archives_removed") if k in unpack}
            status, message = detect_game_status(
                game_root, language, cancel_check=lambda: job.cancel_event.is_set(),
            )
            if status == "cancelled":
                raise asyncio.CancelledError()

        if status == "need_decompile":
            progress("正在反编译脚本", 30, stage="decompile")
            decompiled = decompile_target(
                game_root,
                overwrite=False,
                use_unren=True,
                fallback_unren_options="2x",
                progress_callback=lambda m: progress(m, 35, stage="decompile"),
            )
            check_cancel()
            if not decompiled.get("success"):
                raise RuntimeError(decompiled.get("message") or "反编译失败")
            job.result["decompile"] = {
                "success": True,
                "method": decompiled.get("method"),
                "overwrite": False,
            }
            status, message = detect_game_status(
                game_root, language, cancel_check=lambda: job.cancel_event.is_set(),
            )
            if status == "cancelled":
                raise asyncio.CancelledError()

        check_cancel()
        if status != "ready":
            raise RuntimeError(message or "预处理后仍无可抽取脚本")
        progress("正在配置翻译路径", 45, stage="paths")
        prepared = prepare_extraction_paths(config, game_root, language, incremental=incremental)
        check_cancel()
        progress("正在抽取文本", 55, stage="extract")

        def extract_progress(msg: str, pct: int) -> None:
            progress(msg, max(55, min(90, 55 + int(pct * 0.35))), stage="extract")

        success, extract_message, result = extract_project_text(
            game_root,
            language,
            incremental=incremental,
            exe_path=exe_path,
            output_to_separate_folder=True,
            progress_callback=extract_progress,
            cancel_check=lambda: job.cancel_event.is_set(),
        )
        if getattr(result, "cancelled", False) or job.cancel_event.is_set():
            raise asyncio.CancelledError()
        if not success:
            raise RuntimeError(extract_message or "文本抽取失败")

        # 把路径写回共享配置（仍锁定在快照项目）；不再二次备份增量缓存。
        with CacheManager.LOCK:
            live_config = request.app.state.config
            if _project_identity(live_config) != owner_identity:
                raise RuntimeError("项目或翻译路径已切换，本次路径配置未写入")
            configured = copy.deepcopy(live_config)
            if incremental:
                configure_incremental_translation_paths(
                    configured, game_root, language, Path(prepared["incremental_dir"]),
                )
            else:
                configure_main_translation_paths(
                    configured, game_root, language, remember_run=True,
                )
            _persist_project_paths(live_config, configured)

        payload = {
            "project_key": project_key,
            "game_dir": game_dir,
            "project_root": game_root,
            "language": language,
            "incremental": incremental,
            "detect_status": "ready",
            "message": extract_message,
            "stage": "ready",
            "tl_dir": prepared["main_tl_dir"],
            "output_dir": prepared["output_dir"],
            "incremental_dir": prepared["incremental_dir"],
            "main_output_dir": prepared["main_output_dir"],
            "preserved_cache": prepared["preserved_cache"],
            "input_folder": str(getattr(config, "input_folder", "") or ""),
            "output_folder": str(getattr(config, "output_folder", "") or ""),
            "extraction_success": True,
            "worker_active": True,
        }
        if result is not None:
            payload["incremental_dir"] = str(getattr(result, "incremental_dir", None) or prepared["incremental_dir"] or "")
            payload["tl_dir"] = str(getattr(result, "tl_dir", None) or prepared["main_tl_dir"])
        return payload

    async def worker(_: Job) -> dict:
        try:
            check_cancel()
            future = loop.run_in_executor(None, compute)
            try:
                result = await asyncio.shield(future)
            except asyncio.CancelledError:
                job.cancel_event.set()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.shield(future)
                raise
            check_cancel()
            job.result.update(result)
            manager.progress(job.id, done=100, total=100)
            return job.result
        except asyncio.CancelledError:
            if isinstance(job.result, dict):
                job.result["message"] = "任务已取消，未启动翻译"
                job.result["stage"] = "cancelled"
            raise
        except Exception as exc:
            if job.cancel_event.is_set():
                if isinstance(job.result, dict):
                    job.result["message"] = "任务已取消，未启动翻译"
                    job.result["stage"] = "cancelled"
                raise asyncio.CancelledError() from exc
            if isinstance(job.result, dict):
                job.result["message"] = str(exc)
                job.result["stage"] = "failed"
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


@router.post("/apply")
async def apply(request: Request, body: ApplyBody) -> dict:
    """确认后应用译文；增量模式走合并+缓存迁移。"""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="应用译文会覆盖游戏内文件，需要 confirm=true")
    with CacheManager.LOCK:
        live = request.app.state.config
        paths, language = _resolve_game_snapshot(live, body.game_dir, body.language)
        project_key = _ensure_project_key(body.project_key, paths)
        current_paths = RenpyProjectPaths.from_config(live)
        if current_paths is None or current_paths.project_key != project_key:
            raise HTTPException(status_code=409, detail="项目或语言已切换，请重新加载后再应用")
        config = copy.deepcopy(live)
    game_root = str(paths.project_root)
    incremental = bool(body.incremental)
    auto_merge_cleanup = (
        bool(getattr(config, "renpy_incremental_auto_merge_cleanup", True))
        if body.auto_merge_cleanup is None else bool(body.auto_merge_cleanup)
    )
    main_output = paths.translation_output_dir
    input_dir = paths.application_target_dir
    incremental_dir = paths.tl_root / f"{paths.language}_new"
    output_dir = main_output.parent / f"{paths.language}_new" if incremental else main_output
    expected_target = incremental_dir if incremental else input_dir
    # 删除与覆盖目标只能由项目身份派生；请求路径只用于检测页面快照是否过期。
    for supplied, expected in (
        (body.incremental_output, output_dir),
        (body.incremental_target, expected_target),
        (body.main_output, main_output),
        (None, input_dir),
    ):
        if expected.resolve() != expected or (supplied and Path(supplied).resolve() != expected):
            raise HTTPException(status_code=400, detail="应用路径与当前项目不一致，或目录包含符号链接")
    if not output_dir.is_dir():
        raise HTTPException(status_code=400, detail="找不到翻译输出目录")
    engine = _acquire_engine()
    manager = request.app.state.jobs
    try:
        job = manager.create("onekey_apply", cooperative_cancel=True)
    except Exception:
        engine.release_status(Engine.Status.TESTING)
        raise
    job.result = {
        "project_key": project_key,
        "game_dir": str(paths.game_dir),
        "language": language,
        "incremental": incremental,
        "auto_merge_cleanup": auto_merge_cleanup,
        "message": "准备应用译文",
        "worker_active": True,
        "stage": "apply",
    }
    loop = asyncio.get_running_loop()

    def check_cancel() -> None:
        if job.cancel_event.is_set():
            raise asyncio.CancelledError()

    def publish(message: str, done: int | None = None) -> None:
        if isinstance(job.result, dict) and job.result.get("worker_active"):
            job.result["message"] = message
            manager.progress(job.id, done=done, total=100)

    def progress(message: str, percent: int = 0) -> None:
        # 应用中的合并、缓存迁移和路径恢复是一个收尾段，不能从回调中断事务。
        loop.call_soon_threadsafe(lambda: publish(message, done=percent))

    def compute() -> dict:
        check_cancel()
        extractor = UnifiedExtractor()
        if incremental:
            if input_dir is None:
                raise RuntimeError("增量应用缺少目标目录")
            ok, message, payload = apply_incremental_translation(
                extractor=extractor,
                config=config,
                game_dir=game_root,
                tl_name=language,
                output_dir=Path(output_dir),
                main_output=Path(main_output),
                incremental_dir=incremental_dir,
                progress_callback=progress,
                clean_duplicates=auto_merge_cleanup,
            )
        else:
            files = [
                path for path in Path(output_dir).rglob("*.rpy")
                if path.is_file()
            ]
            if not files:
                raise RuntimeError("输出目录中没有可应用的 .rpy 文件")
            if input_dir is None:
                raise RuntimeError("应用目标目录无效")
            ok, message, payload = apply_full_translation(
                config=config,
                output_files=files,
                output_dir=Path(output_dir),
                input_dir=Path(input_dir),
                project_root=game_root,
                project_language=language,
                progress_callback=progress,
            )
        if not ok:
            raise RuntimeError(message or "应用译文失败")
        # 同步配置到共享实例（仅当项目未切换）。
        with CacheManager.LOCK:
            live_config = request.app.state.config
            live_paths = RenpyProjectPaths.from_config(live_config)
            if live_paths is not None and live_paths.project_key == project_key:
                _persist_project_paths(live_config, config)
        return {
            "project_key": project_key,
            "message": message,
            "stage": "done",
            "incremental": incremental,
            "payload": payload or {},
            "worker_active": True,
        }

    async def worker(_: Job) -> dict:
        try:
            check_cancel()
            future = loop.run_in_executor(None, compute)
            try:
                result = await asyncio.shield(future)
            except asyncio.CancelledError:
                job.cancel_event.set()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.shield(future)
                raise
            job.result.update(result)
            manager.progress(job.id, done=100, total=100)
            return job.result
        except asyncio.CancelledError:
            if isinstance(job.result, dict):
                job.result["message"] = "任务已取消"
                job.result["stage"] = "cancelled"
            raise
        except Exception as exc:
            if job.cancel_event.is_set():
                if isinstance(job.result, dict):
                    job.result["message"] = "任务已取消"
                raise asyncio.CancelledError() from exc
            if isinstance(job.result, dict):
                job.result["message"] = str(exc)
                job.result["stage"] = "failed"
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
