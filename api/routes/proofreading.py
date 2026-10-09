"""平行校对台：读取真实缓存、带版本校验的译文编辑与纯文本批量替换。"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import re
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from contextlib import contextmanager
from typing import Iterator, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Renpy.ProjectPaths import RenpyProjectPaths, translation_output_candidates
from module.ResultChecker import ResultChecker, WarningType

router = APIRouter(prefix="/api/proofreading", tags=["proofreading"])


class RowReference(BaseModel):
    id: int = Field(ge=0)
    version: str = Field(min_length=64, max_length=64)


class EditRequest(BaseModel):
    cache_token: str = Field(min_length=64, max_length=64)
    row: RowReference
    dst: str = Field(max_length=100000)


class ReplaceRequest(BaseModel):
    cache_token: str = Field(min_length=64, max_length=64)
    rows: list[RowReference] = Field(min_length=1, max_length=100)
    find: str = Field(min_length=1, max_length=2000)
    replace: str = Field(max_length=10000)
    case_sensitive: bool = True


class SelectionRequest(BaseModel):
    cache_token: str = Field(min_length=64, max_length=64)
    rows: list[RowReference] = Field(min_length=1, max_length=100)


class ExportRequest(BaseModel):
    cache_token: str = Field(min_length=64, max_length=64)


class QualityRequest(BaseModel):
    cache_token: str = Field(min_length=64, max_length=64)
    task: Literal["polish", "proofread"]
    ids: list[int] = Field(min_length=1, max_length=500)
    # 新版携带行版本；旧调用方仍可只传 ids。
    rows: list[RowReference] | None = Field(default=None, min_length=1, max_length=500)


def _key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path)) if path else ""


def _cache_token(config, output: str) -> str:
    # 令牌绑定项目身份及输入/输出配置，不能拿旧页面的索引修改新项目。
    paths = [_key(str(getattr(config, name, "") or "")) for name in (
        "renpy_project_path", "renpy_game_folder", "renpy_tl_folder", "input_folder", "output_folder",
    )]
    return hashlib.sha256(json.dumps([*paths, _key(output)]).encode("utf-8")).hexdigest()


def _version(item: CacheItem) -> str:
    payload = json.dumps(item.asdict(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_cache(config) -> tuple[str, CacheManager]:
    empty_cache = None
    candidates = translation_output_candidates(config)
    for candidate in candidates:
        manager = CacheManager(service=False)
        try:
            manager.load_from_file(str(candidate), strict=True)
        except Exception:
            continue
        if any(item.get_src().strip() for item in manager.get_items()):
            return str(candidate), manager
        if empty_cache is None:
            empty_cache = (str(candidate), manager)
    if empty_cache is not None:
        return empty_cache
    raise HTTPException(status_code=404, detail="没有可读取的完整翻译缓存，请先完成一次翻译。")


def _row(index: int, item: CacheItem, warnings: list[WarningType] | None = None) -> dict:
    return {
        "id": index, "version": _version(item), "src": item.get_src(), "dst": item.get_dst(),
        "status": str(item.get_status()), "file_path": item.get_file_path(), "row": item.get_row(),
        "warnings": [str(warning) for warning in (warnings or [])],
    }


def _readonly() -> bool:
    engine = Engine.get()
    return engine.get_status() != Engine.Status.IDLE or engine.has_stop_barrier() or engine.has_single_tasks()


def _read_snapshot(request: Request, config) -> dict:
    # 只保留当前项目的只读快照；写入、文件代次或设置变化后重新载入。
    paths = translation_output_candidates(config)
    def signature():
        files = []
        for output in paths:
            for name in ("items.json", "project.json", "cache.db", "cache.db-wal", CacheManager.RESET_JOURNAL_NAME):
                path = os.path.join(str(output), "cache", name)
                try:
                    stat = os.stat(path)
                    files.append((path, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino))
                except FileNotFoundError:
                    files.append((path, None))
        return tuple(files)
    config_key = hashlib.sha256(json.dumps(dataclasses.asdict(config), sort_keys=True, default=str).encode()).hexdigest()
    key = (config_key, signature())
    snapshot = getattr(request.app.state, "proofreading_snapshot", None)
    if snapshot is not None and snapshot["key"] == key:
        return snapshot
    output, manager = _load_cache(config)
    visible = [(index, item) for index, item in enumerate(manager.get_items()) if item.get_src().strip()]
    snapshot = {
        "key": key, "output": output, "manager": manager,
        "visible": visible, "files": sorted({item.get_file_path() for _, item in visible}),
        "warnings": {}, "checked": 0, "filter_key": None, "matches": [],
    }
    request.app.state.proofreading_snapshot = snapshot
    return snapshot


@router.get("")
def read_rows(
    request: Request,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    query: str = Query(default="", max_length=2000),
    status: str = Query(default="", max_length=32),
    file_path: str = Query(default="", max_length=2048),
    only_issues: bool = False,
    incremental: bool = False,
    warning: str = Query(default="", max_length=32),
) -> dict:
    """分页返回原译对照。搜索同时匹配原文、译文及相对文件路径。"""
    if status and status not in Base.ITEM_VALID_STATUSES:
        raise HTTPException(status_code=400, detail="未知条目状态")
    if warning and warning not in {str(value) for value in WarningType}:
        raise HTTPException(status_code=400, detail="未知问题类型")
    config = copy.deepcopy(request.app.state.config)
    with CacheManager.LOCK:
        snapshot = _read_snapshot(request, config)
        output, manager = snapshot["output"], snapshot["manager"]
        visible, warnings = snapshot["visible"], snapshot["warnings"]
        checker = ResultChecker(config, [])
        def check(index, item):
            if index not in warnings:
                warnings[index] = checker.check_single_item(item)
            return warnings[index]
        checking = only_issues or bool(warning)
        if checking:
            # 分块检查让第一页及时返回；切换筛选时复用同一份逐行检查结果。
            deadline = time.monotonic() + 0.12 if incremental else float("inf")
            while snapshot["checked"] < len(visible):
                index, item = visible[snapshot["checked"]]
                check(index, item)
                snapshot["checked"] += 1
                if time.monotonic() >= deadline:
                    break
        scan_complete = not checking or snapshot["checked"] == len(visible)
        candidates = visible[:snapshot["checked"]] if checking else visible
        needle = query.casefold().strip()
        filter_key = (needle, status, file_path, only_issues, warning, snapshot["checked"] if checking else 0)
        if snapshot["filter_key"] != filter_key:
            snapshot["matches"] = [
                (index, item) for index, item in candidates
                if (not status or item.get_status() == status)
                and (not file_path or item.get_file_path() == file_path)
                and (not needle or needle in "\n".join((item.get_src(), item.get_dst(), item.get_file_path())).casefold())
                and (not only_issues or bool(check(index, item)))
                and (not warning or warning in check(index, item))
            ]
            snapshot["filter_key"] = filter_key
        matches = snapshot["matches"]
        page = min(page, max(1, (len(matches) + limit - 1) // limit))
        return {
            "cache_token": _cache_token(config, output), "cache_folder": output,
            "total": len(visible), "matched": len(matches), "page": page, "limit": limit,
            "files": snapshot["files"], "readonly": _readonly(),
            "scan_complete": scan_complete, "checked": snapshot["checked"], "check_total": len(visible),
            "quality_reports": [
                report for key in ("polishing_progress", "proofreading_progress")
                if isinstance(report := manager.get_project().get_extras().get(key), dict)
            ],
            "items": [_row(index, item, check(index, item)) for index, item in matches[(page - 1) * limit:page * limit]],
        }


def _flush_pending_results(output: str, manager: CacheManager) -> None:
    runtime = _runtime_cache(output)
    if runtime is not None and runtime.require_flag:
        # 先保存翻译器的待落盘结果，再检查页面行版本，避免旧译文覆盖新结果。
        try:
            saved = runtime.save_to_file(runtime.get_project(), runtime.get_items(), output, strict=True)
            if saved is not True:
                raise RuntimeError("未确认缓存保存成功")
            manager.load_from_file(output, strict=True)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"翻译结果待保存，请稍后重试：{exc}") from exc


@contextmanager
def _write_access(request: Request, token: str) -> Iterator[tuple[str, CacheManager]]:
    engine = Engine.get()
    # 原子占用现有引擎状态，翻译/质量任务无法在校对落盘中途启动。
    if not engine.try_set_status(Engine.Status.IDLE, Engine.Status.AGENT):
        raise HTTPException(status_code=409, detail="任务正在运行或停止收尾，校对台暂时只读。")
    try:
        config = copy.deepcopy(request.app.state.config)
        with CacheManager.LOCK:
            output, manager = _load_cache(config)
            if token != _cache_token(config, output):
                raise HTTPException(status_code=409, detail="项目或缓存目录已切换，请刷新后再保存。")
            _flush_pending_results(output, manager)
            yield output, manager
    finally:
        engine.release_status(Engine.Status.AGENT)


def _targets(manager: CacheManager, references: list[RowReference]) -> list[tuple[int, CacheItem]]:
    items = manager.get_items()
    result = []
    seen = set()
    for ref in references:
        if ref.id in seen:
            continue
        if ref.id >= len(items) or _version(items[ref.id]) != ref.version:
            raise HTTPException(status_code=409, detail="译文或缓存条目已更新，请刷新后再编辑。")
        seen.add(ref.id)
        result.append((ref.id, items[ref.id]))
    return result


def _set_translation(item: CacheItem, dst: str) -> None:
    item.set_dst(dst)
    if dst and not Base.is_item_completed(item.get_status()):
        item.set_status(Base.TranslationStatus.TRANSLATED)


def _runtime_cache(output: str):
    translator = getattr(Engine.get(), "translator", None)
    runtime = getattr(translator, "cache_manager", None)
    runtime_output = str(getattr(translator, "_active_cache_output_folder", "") or getattr(translator, "_last_runtime_output_folder", "") or "")
    return runtime if runtime is not None and _key(runtime_output) == _key(output) else None


def _save(request: Request, output: str, manager: CacheManager, token: str) -> None:
    request.app.state.proofreading_snapshot = None
    if token != _cache_token(request.app.state.config, output):
        raise HTTPException(status_code=409, detail="项目配置已变化，本次编辑未保存，请重新载入。")
    try:
        saved = manager.save_to_file(manager.get_project(), manager.get_items(), output, strict=True)
        if saved is not True:
            raise RuntimeError("未确认缓存保存成功")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"译文保存失败：{exc}") from exc
    # 停止后的翻译器仍有自动保存缓存。同步同一项目的内存，避免旧快照覆盖刚保存的译文。
    runtime = _runtime_cache(output)
    if runtime is not None:
        runtime.set_project(manager.get_project())
        runtime.set_items(manager.get_items())
        runtime.require_flag = False


@router.patch("/item")
def edit_item(request: Request, body: EditRequest) -> dict:
    """校验行版本后立即将译文保存到当前项目缓存。"""
    with _write_access(request, body.cache_token) as (output, manager):
        index, item = _targets(manager, [body.row])[0]
        _set_translation(item, body.dst)
        _save(request, output, manager, body.cache_token)
        return {"ok": True, "item": _row(index, item)}


@router.post("/replace")
def replace_rows(request: Request, body: ReplaceRequest) -> dict:
    """对当前页或所选行做纯文本替换；任一版本冲突时整批不写入。"""
    pattern = re.compile(re.escape(body.find), flags=0 if body.case_sensitive else re.IGNORECASE)
    with _write_access(request, body.cache_token) as (output, manager):
        targets = _targets(manager, body.rows)
        changed = 0
        for _, item in targets:
            dst = pattern.sub(lambda _: body.replace, item.get_dst())
            if dst != item.get_dst():
                _set_translation(item, dst)
                changed += 1
        if changed:
            _save(request, output, manager, body.cache_token)
        return {"ok": True, "changed": changed}


@router.post("/reset")
def reset_rows(request: Request, body: SelectionRequest) -> dict:
    """仅重置已确认的选中行；全部版本通过后一次保存。"""
    with _write_access(request, body.cache_token) as (output, manager):
        targets = _targets(manager, body.rows)
        for _, item in targets:
            item.reset_translation()
        _save(request, output, manager, body.cache_token)
        return {"ok": True, "changed": len(targets)}


@router.post("/confirm")
def confirm_rows(request: Request, body: SelectionRequest) -> dict:
    """人工确认已有译文，仅清除达到重试阈值的警告与重试原因。"""
    with _write_access(request, body.cache_token) as (output, manager):
        targets = _targets(manager, body.rows)
        checker = ResultChecker(request.app.state.config, [item for _, item in targets])
        changed = 0
        for _, item in targets:
            if item.get_dst().strip() and WarningType.RETRY_THRESHOLD in checker.check_single_item(item):
                item.set_retry_count(0)
                metadata = item.get_metadata()
                metadata.pop(CacheItem.TRANSLATION_RETRY_KEY, None)
                item.set_metadata(metadata)
                changed += 1
        if changed:
            _save(request, output, manager, body.cache_token)
        return {"ok": True, "changed": changed}


@router.get("/report")
def read_quality_report(request: Request) -> dict:
    """汇总缓存中的翻译错误，并补入当前质量任务的实时错误计数。"""
    from module.Engine.Quality.QualityTaskCoordinator import QualityTaskCoordinator
    from module.Engine.Quality.TranslationQualityReport import build_translation_quality_report

    with CacheManager.LOCK:
        snapshot = _read_snapshot(request, copy.deepcopy(request.app.state.config))
        manager = snapshot["manager"]
        extras = manager.get_project().get_extras()
        saved = extras.get("progress", extras)
        progress = dict(saved) if isinstance(saved, Mapping) else {}
        coordinator = QualityTaskCoordinator.get()
        get_progress = getattr(coordinator, "get_progress", None)
        active = get_progress() if callable(get_progress) else None
        if active is not None:
            active_counts = active.as_dict().get("error_type_counts", {})
            saved_counts = progress.get("error_type_counts", {})
            merged_counts = dict(saved_counts) if isinstance(saved_counts, Mapping) else {}
            if isinstance(active_counts, Mapping):
                for code, count in active_counts.items():
                    previous = merged_counts.get(code, 0)
                    merged_counts[code] = max(
                        previous if type(previous) is int and previous >= 0 else 0,
                        count if type(count) is int and count >= 0 else 0,
                    )
            progress["error_type_counts"] = merged_counts
        return build_translation_quality_report(manager.get_items(), progress).as_dict()


@router.post("/export")
def export_rows(request: Request, body: ExportRequest) -> dict:
    """先确认当前缓存保存成功，再按原文件格式写入实际输出目录。"""
    from module.File.FileManager import FileManager
    with _write_access(request, body.cache_token) as (output, manager):
        _save(request, output, manager, body.cache_token)
        config = copy.deepcopy(request.app.state.config)
        config.output_folder = output
        try:
            FileManager(config).write_to_path(manager.get_items())
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"译文文件写入失败：{exc}") from exc
        return {"ok": True, "output_folder": output}


@router.post("/locate")
def locate_row(request: Request, body: SelectionRequest) -> dict:
    """按当前缓存条目定位译文行，返回有限上下文，不接受任意文件路径。"""
    if len(body.rows) != 1:
        raise HTTPException(status_code=400, detail="每次只能定位一条译文。")
    config = copy.deepcopy(request.app.state.config)
    with CacheManager.LOCK:
        snapshot = _read_snapshot(request, config)
        output, manager = snapshot["output"], snapshot["manager"]
        if body.cache_token != _cache_token(config, output):
            raise HTTPException(status_code=409, detail="项目已变化，请刷新后定位。")
        _, item = _targets(manager, body.rows)[0]
        relative = Path(item.get_file_path())
        extra = item.get_extra_field()
        meta = extra.get("renpy", {}) if isinstance(extra, dict) else {}
        pair = meta.get("pair", {}) if isinstance(meta, dict) else {}
        row = int(pair.get("target_line") or item.get_row() or 0)
    if relative.is_absolute() or ".." in relative.parts or row < 1:
        raise HTTPException(status_code=400, detail="条目缺少有效的相对路径或行号。")
    paths = RenpyProjectPaths.from_config(config)
    bases = [paths.tl_language_dir, paths.translation_output_dir] if paths else []
    bases.append(Path(output))
    for base in bases:
        candidate = (base / relative).resolve()
        if not candidate.is_relative_to(base.resolve()) or not candidate.is_file():
            continue
        lines = []
        try:
            with candidate.open(encoding="utf-8-sig", errors="replace") as stream:
                for number, text in enumerate(stream, 1):
                    if number >= max(1, row - 20):
                        lines.append({"number": number, "text": text.rstrip("\r\n")[:2000]})
                    if number >= row + 20:
                        break
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"读取译文文件失败：{exc}") from exc
        if not any(line["number"] == row for line in lines):
            raise HTTPException(status_code=404, detail="译文文件已变化，目标行不存在。")
        return {"path": str(candidate), "row": row, "lines": lines}
    raise HTTPException(status_code=404, detail="找不到译文文件，请先导出译文。")


def _retranslate_state(request: Request) -> dict:
    task = getattr(request.app.state, "proofreading_retranslate", None)
    return {key: value for key, value in task.items() if key != "cancel"} if task else {"state": "IDLE"}


@router.get("/retranslate")
def read_retranslate(request: Request) -> dict:
    return _retranslate_state(request)


@router.post("/retranslate/cancel")
def cancel_retranslate(request: Request) -> dict:
    task = getattr(request.app.state, "proofreading_retranslate", None)
    if not task or task["state"] not in ("RUNNING", "CANCELLING"):
        raise HTTPException(status_code=409, detail="当前没有正在重译的任务。")
    task["cancel"].set()
    task["state"] = "CANCELLING"
    return _retranslate_state(request)


@router.post("/retranslate")
def retranslate_rows(request: Request, body: SelectionRequest) -> dict:
    """复用旧版批量重译引擎；请求后台执行，取消后仍保存已完成结果。"""
    engine = Engine.get()
    config = copy.deepcopy(request.app.state.config)
    with CacheManager.LOCK:
        if _readonly():
            raise HTTPException(status_code=409, detail="任务正在运行，暂时不能重译。")
        output, manager = _load_cache(config)
        if body.cache_token != _cache_token(config, output):
            raise HTTPException(status_code=409, detail="项目已变化，请刷新后重译。")
        _flush_pending_results(output, manager)
        targets = _targets(manager, body.rows)
        if not config.get_platform(config.activate_platform):
            raise HTTPException(status_code=400, detail="请先选择有效的翻译接口。")
        # 额外登记一个任务覆盖翻译开始前和保存后的间隙，避免其他写入插入。
        if not engine.try_begin_single_task():
            raise HTTPException(status_code=409, detail="引擎忙碌，请稍后重试。")
        task = {"state": "RUNNING", "total": len(targets), "done": 0, "updated": 0, "failed": 0, "error": "", "cancel": threading.Event()}
        request.app.state.proofreading_retranslate = task
    config.output_folder = output

    def run():
        terminal = "FAILED"
        try:
            successful = set()
            def completed(item, success):
                task["done"] += 1
                if success:
                    successful.add(id(item))
                else:
                    task["failed"] += 1
            engine.translate_items([item for _, item in targets], config, completed, should_cancel=task["cancel"].is_set)
            with CacheManager.LOCK:
                latest_output, latest = _load_cache(config)
                if latest_output != output:
                    raise RuntimeError("缓存位置变化，重译结果未写入。")
                _targets(latest, body.rows)
                for index, item in targets:
                    if id(item) in successful:
                        latest.get_items()[index] = item
                if successful:
                    _save(request, output, latest, body.cache_token)
                    task["updated"] = len(successful)
            terminal = "CANCELLED" if task["cancel"].is_set() else "COMPLETED"
        except Exception as exc:
            task["error"] = str(getattr(exc, "detail", exc))
        finally:
            engine.end_single_task()
            task["state"] = terminal
    try:
        threading.Thread(target=run, name="PROOFREADING_RETRANSLATE", daemon=True).start()
    except Exception:
        task["state"] = "FAILED"
        engine.end_single_task()
        raise
    return _retranslate_state(request)


@router.post("/quality")
def start_quality(request: Request, body: QualityRequest) -> dict:
    """对选中缓存条目启动 AI 润色或校对。进度经 TRANSLATION_UPDATE 推送。"""
    if _readonly():
        raise HTTPException(status_code=409, detail="任务正在运行，请结束后再开始校对或润色。")
    config = copy.deepcopy(request.app.state.config)
    with CacheManager.LOCK:
        output, manager = _load_cache(config)
        if body.cache_token != _cache_token(config, output):
            raise HTTPException(status_code=409, detail="项目或缓存已变化，请刷新后再开始。")
        _flush_pending_results(output, manager)
        if body.rows is not None:
            if {row.id for row in body.rows} != set(body.ids):
                raise HTTPException(status_code=400, detail="行版本与选中条目不一致，请刷新后再试。")
            _targets(manager, body.rows)
        items = manager.get_items()
        selected = []
        skipped = 0
        for index in dict.fromkeys(body.ids):
            if index < 0 or index >= len(items):
                raise HTTPException(status_code=400, detail="选中的条目不存在，请刷新后再试。")
            item = items[index]
            eligible = (
                Base.is_item_polishable(item.get_status())
                if body.task == "polish"
                else Base.is_item_proofreadable(item.get_status())
            )
            if eligible:
                selected.append(item)
            else:
                skipped += 1
        if not selected:
            detail = "选中的条目里没有可润色的译文。润色只处理已翻译的句子。" if body.task == "polish" else "选中的条目里没有可校对的译文。"
            raise HTTPException(status_code=400, detail=detail)
        runtime = copy.deepcopy(config)
        runtime.output_folder = output
        from module.Engine.Quality.QualityTaskCoordinator import QualityTaskCoordinator
        coordinator = QualityTaskCoordinator.get()
        # 在缓存锁内启动，避免加载后到启动前被另一条编辑请求改写。
        started = (
            coordinator.start_polishing(runtime, items, selected)
            if body.task == "polish"
            else coordinator.start_proofreading(runtime, items, selected)
        )
        if not started:
            raise HTTPException(status_code=409, detail="质量任务未能启动，请确认没有其他任务在运行。")
        return {"ok": True, "accepted": len(selected), "skipped": skipped, "task": body.task}


@router.post("/quality/cancel")
def cancel_quality() -> dict:
    from module.Engine.Quality.QualityTaskCoordinator import QualityTaskCoordinator
    if not QualityTaskCoordinator.get().cancel():
        raise HTTPException(status_code=409, detail="当前没有进行中的校对或润色。")
    return {"ok": True}
