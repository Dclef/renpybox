"""词库 / 禁翻 API：Excel、统计、候选扫描、分类、翻译；无 Qt。"""

from __future__ import annotations

import inspect

import asyncio
import contextlib
import copy
import os
import time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from api.jobs import Job
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.Localizer.Localizer import Localizer
from module.Agent.AgentService import AgentService
from module.Extract.GlossaryCandidateService import (
    extract_character_candidates,
    extract_glossary_candidates,
)
from module.Renpy.ProjectPaths import RenpyProjectPaths
from module.Tool import LexiconOps
from module.Tool.LexiconOps import LexiconOpsError

router = APIRouter(prefix="/api/lexicon", tags=["lexicon"])

LEXICON_KINDS = (
    "lexicon_statistics",
    "lexicon_scan_candidates",
    "lexicon_translate",
    "lexicon_scan_characters",
    "lexicon_preserve_rescan",
)


class ExcelImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["glossary", "preserve"]
    content_base64: str = Field(min_length=1)
    filename: str = ""


class ExcelExportBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["glossary", "preserve"]
    rows: list[dict[str, Any]] = Field(default_factory=list)


class StatisticsBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["glossary", "preserve"]
    rows: list[dict[str, Any]] = Field(default_factory=list)
    project_key: str = ""
    output_folder: str | None = None


class ProjectKeyBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_key: str = ""
    output_folder: str | None = None
    confirm: bool = False
    # 可选：与当前前端草稿合并，避免晚到结果盖掉未保存编辑
    rows: list[dict[str, Any]] | None = None


class ExtractionBody(ProjectKeyBody):
    resume: bool = True
    force: bool = False


def _extraction_options(extractor, body: ExtractionBody, **extra) -> dict[str, Any]:
    try:
        parameters = inspect.signature(extractor).parameters
    except (TypeError, ValueError):
        return {}
    variadic = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
    return {key: value for key, value in {'resume': body.resume, 'force': body.force, 'checkpoint_enabled': True, **extra}.items()
            if variadic or key in parameters}


def _checkpointed_compute(compute, checkpoints):
    # Do not seal a fully extracted checkpoint until the API has safely applied
    # the result. A cancellation, persistence failure or process exit before
    # then leaves every committed block available without another model call.
    def wrapped(check_cancel, progress, publish_event_callback=None):
        latest = {}
        def event(details):
            latest.clear()
            latest.update(copy.deepcopy(details))
            if publish_event_callback is not None:
                publish_event_callback(details)
        payload = compute(check_cancel, progress, event)
        check_cancel()
        if checkpoints:
            checkpoint = checkpoints[-1]
            checkpoint.finish()
            metadata = checkpoint.metadata()
            payload = {**payload, **metadata}
            if latest and publish_event_callback is not None:
                publish_event_callback({**latest, **metadata})
        return payload
    return wrapped


class ClassifyBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class TranslateBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["llm", "fast"]
    rows: list[dict[str, Any]] = Field(default_factory=list)
    engine: Literal["bing", "google"] = "bing"
    confirm: bool = False
    project_key: str = ""
    output_folder: str | None = None


def _project_key(config: Any) -> str:
    paths = RenpyProjectPaths.from_config(config)
    if paths is None:
        return ""
    return paths.project_key


def _latest_lexicon_job(request: Request, project_key: str | None = None) -> Job | None:
    key = project_key if project_key is not None else _project_key(request.app.state.config)
    return next(
        (
            job
            for job in request.app.state.jobs.list()
            if job.kind in LEXICON_KINDS
            and isinstance(job.result, dict)
            and job.result.get("project_key") == key
            and job.result.get("output_folder", "") == request.app.state.config.output_folder
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


def _agent_platform(config: Any) -> tuple[dict[str, Any] | None, str]:
    """按配置的 Agent 接口取平台；-1 视为未配置，绝不回落到翻译平台。"""
    platform, reason = AgentService._platform(config)
    return platform, ("" if platform is not None else str(reason or ""))


def _known_sources(rows: Any, state: Any) -> set[str]:
    """收集已有原文（表格行 + 项目候选），规范化后用来判断候选是否已存在。"""
    known: set[str] = set()
    for row in rows or []:
        if isinstance(row, dict):
            key = LexiconOps.normalize_glossary_src(row.get("src", ""))
            if key:
                known.add(key)
    items = getattr(getattr(state, "assets", None), "glossary", [])
    candidates = state.analysis_candidates.get("items", [])
    for item in list(items) + list(candidates):
        data = item.to_dict() if hasattr(item, "to_dict") else item
        if isinstance(data, dict):
            key = LexiconOps.normalize_glossary_src(data.get("source", data.get("src", "")))
            if key:
                known.add(key)
    return known


def _fresh_entries(rows: Any, state: Any, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """只保留尚不存在的候选，避免覆盖已有译文/注释或重新启用禁用项。"""
    known = _known_sources(rows, state)
    fresh: list[dict[str, Any]] = []
    seen: set[tuple[str, bool]] = set()
    for entry in entries:
        raw_src = entry.get("src", entry.get("source", ""))
        key = LexiconOps.normalize_glossary_src(str(raw_src or ""))
        regex = bool(entry.get("regex", False))
        if not key or key in known:
            continue
        if (key, regex) in seen:
            continue
        seen.add((key, regex))
        fresh.append(dict(entry))
    return fresh


def _fresh_names(rows: Any, state: Any, names: list[str]) -> list[str]:
    """只补缺失的人名，已存在的条目（含用户禁用/已确认的）一律不动。"""
    known = _known_sources(rows, state)
    fresh: list[str] = []
    for name in names:
        key = LexiconOps.normalize_glossary_src(str(name or ""))
        if not key or key in known or name in fresh:
            continue
        fresh.append(name)
    return fresh


class _ErrorSummary(str):
    """短摘要。warnings 挂在字符串上，随异常参数进入 job.result，不拼进文案。"""


def _agent_error(payload: dict[str, Any], fallback: str) -> str:
    warnings = [str(item) for item in payload.get("warnings", []) if str(item).strip()]
    if not warnings:
        return fallback
    more = Localizer.get().agent_error_more.format(count=len(warnings) - 1) if len(warnings) > 1 else ""
    # job.error 会再加「异常类名: 」前缀，摘要本身压到 183，两处都短于 200。
    room = 183 - len(more)
    first = warnings[0]
    if len(first) > 160:
        first = first[:160] + "…"
    if room < 1:
        text = more[:183]
    elif len(first) > room:
        text = (first[:room - 1] + "…") if room > 1 else first[:room]
        text += more
    else:
        text = first + more
    summary = _ErrorSummary(text)
    summary.warnings = warnings
    return summary


def _repository(config: Any) -> ProjectAssetsRepository:
    return ProjectAssetsRepository.from_config(config)


def _storage_key(repository: ProjectAssetsRepository) -> str:
    if not repository.has_storage:
        return ""
    return os.path.normcase(os.path.abspath(repository.output_folder))



def _identity(config: Any) -> tuple[str, ...]:
    return tuple(os.path.normcase(os.path.abspath(str(getattr(config, name, "") or ""))) if getattr(config, name, "") else "" for name in (
        "renpy_project_path", "renpy_game_folder", "renpy_tl_folder", "input_folder", "output_folder",
    ))


def _validate_rows(rows) -> None:
    if rows is None:
        return
    if len(rows) > 50000:
        raise HTTPException(status_code=400, detail="词表超过50000行限制")
    for row in rows:
        for name in ("src", "dst", "info", "comment", "type", "record_id"):
            if name in row and (not isinstance(row[name], str) or len(row[name]) > 100000):
                raise HTTPException(status_code=400, detail=f"词表 {name} 必须是文字且不超过100000字符")
        for name in ("enabled", "regex", "case_sensitive", "candidate", "candidate_confirmed"):
            if name in row and not isinstance(row[name], bool):
                raise HTTPException(status_code=400, detail=f"词表 {name} 必须是布尔值")


def _snapshot(request: Request, key: str, output_folder: str | None = None):
    with CacheManager.LOCK:
        config = copy.deepcopy(request.app.state.config)
        if output_folder is not None and os.path.normcase(os.path.abspath(output_folder)) != os.path.normcase(os.path.abspath(config.output_folder)):
            raise HTTPException(status_code=409, detail="项目输出目录已切换，请重新加载")
        return config, _ensure_path_snapshot(key, config)


def _check_current(request: Request, config: Any, check_cancel) -> None:
    check_cancel()
    if _identity(request.app.state.config) != _identity(config):
        raise LexiconOpsError("项目已切换，未保存本次结果")


def _rows_from_state(state) -> list[dict]:
    metadata = state.analysis_candidates.get("glossary_metadata", {})
    rows = []
    for candidate, items in ((False, state.assets.glossary), (True, state.analysis_candidates.get("items", []))):
        for item in items:
            data = item.to_dict() if hasattr(item, "to_dict") else item
            meta = metadata.get(data.get("record_id", ""), {})
            rows.append({
                "record_id": data.get("record_id", ""), "src": data.get("source", data.get("src", "")),
                "dst": data.get("target", data.get("dst", "")), "comment": data.get("note", data.get("comment", "")),
                "type": meta.get("type", ""), "case_sensitive": bool(meta.get("case_sensitive", False)),
                "enabled": bool(data.get("enabled", True)), "regex": bool(data.get("regex", False)), "candidate": candidate,
            })
    return rows


def _candidate_ids(rows, candidates) -> list[str]:
    by_source = {(LexiconOps.normalize_glossary_src(item.get("source", item.get("src", ""))), bool(item.get("regex", False))): str(item.get("record_id", "")) for item in candidates.get("items", [])}
    ids = []
    for row in rows:
        if not row.get("candidate"):
            continue
        identifier = by_source.get((LexiconOps.normalize_glossary_src(row.get("src", "")), bool(row.get("regex", False))))
        if identifier:
            row["record_id"] = identifier
            ids.append(identifier)
    return list(dict.fromkeys(ids))


def _save_fields(request: Request, fields: dict) -> None:
    # 先严格落盘再更新运行配置，只保存本动作拥有的字段。
    live = request.app.state.config
    updated = copy.deepcopy(live)
    for name, value in fields.items():
        setattr(updated, name, value)
    updated.save(strict=True)
    for name in fields:
        setattr(live, name, getattr(updated, name))

async def _run_lexicon_job(
    request: Request,
    *,
    kind: str,
    project_key: str,
    message: str,
    compute,
    config_snapshot=None,
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
        "output_folder": getattr(config_snapshot, "output_folder", ""),
        "kind": kind,
    }
    loop = asyncio.get_running_loop()

    def check_cancel() -> None:
        if job.cancel_event.is_set():
            raise asyncio.CancelledError()

    def publish(message_text: str, *, done: int | None = None, total: int | None = None) -> None:
        if job.cancel_event.is_set():
            return
        if not isinstance(job.result, dict) or not job.result.get("worker_active"):
            return
        job.result["message"] = message_text
        manager.progress(job.id, done=done, total=total)

    def progress(message_text: str, done: int | None = None, total: int | None = None) -> None:
        if job.cancel_event.is_set():
            return
        loop.call_soon_threadsafe(lambda: publish(message_text, done=done, total=total))

    def publish_event(details: dict) -> None:
        """结构化执行摘要：只挂到 extraction_progress，绝不写进最终 entries。"""
        if job.cancel_event.is_set():
            return
        snapshot = copy.deepcopy(details)
        loop.call_soon_threadsafe(lambda: store_event(snapshot))

    def store_event(details: dict) -> None:
        if not isinstance(job.result, dict) or not job.result.get("worker_active"):
            return
        if job.cancel_event.is_set():
            return
        if config_snapshot is not None and _identity(request.app.state.config) != _identity(config_snapshot):
            return
        job.result["extraction_progress"] = details
        # 复用既有推送通道，不额外开一条事件总线。
        manager.progress(job.id)

    async def worker(_: Job) -> dict:
        try:
            check_cancel()
            def run_compute():
                from module.Engine.TaskRequester import TaskRequester
                bind = getattr(TaskRequester, "bind_run_cancel_event", None)
                unbind = getattr(TaskRequester, "unbind_run_cancel_event", None)
                if bind:
                    bind(job.cancel_event)
                try:
                    # 旧 compute 只接两个参数：按签名决定是否传事件回调，保持向后兼容。
                    try:
                        accepted = len(
                            [
                                parameter
                                for parameter in inspect.signature(compute).parameters.values()
                                if parameter.kind
                                in (
                                    inspect.Parameter.POSITIONAL_ONLY,
                                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                )
                            ]
                        )
                    except (TypeError, ValueError):
                        accepted = 3
                    if accepted >= 3:
                        return compute(check_cancel, progress, publish_event)
                    return compute(check_cancel, progress)
                finally:
                    if unbind:
                        unbind()
            future = loop.run_in_executor(None, run_compute)
            try:
                result = await asyncio.shield(future)
            except asyncio.CancelledError:
                job.cancel_event.set()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.shield(future)
                raise
            if isinstance(result, dict):
                job.result.update(result)
            check_cancel()
            if not result.get("success", True):
                job.result.update(result)
                job.result["message"] = result.get("message") or "任务失败"
                raise RuntimeError(job.result["message"])
            job.result.update(result)
            job.result["message"] = result.get("message") or "完成"
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
                carried = exc.args[0] if getattr(exc, "args", None) else None
                carried_warnings = getattr(carried, "warnings", None)
                if isinstance(carried_warnings, list):
                    job.result["warnings"] = list(carried_warnings)
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
def read_lexicon(request: Request) -> dict:
    """返回当前项目最近一次词库相关任务。"""
    with CacheManager.LOCK:
        job = _latest_lexicon_job(request)
        return {"job": job.snapshot() if job else None, "project_key": _project_key(request.app.state.config), "output_folder": request.app.state.config.output_folder, 'extraction_capabilities': {'checkpoint_resume': True}}


@router.post("/excel/import")
def excel_import(body: ExcelImportBody) -> dict:
    try:
        data = LexiconOps.decode_content_base64(body.content_base64)
        if body.kind == "glossary":
            rows = LexiconOps.import_glossary_excel_bytes(data)
        else:
            rows = LexiconOps.import_preserve_excel_bytes(data)
    except LexiconOpsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Excel 导入失败: {exc}") from exc
    return {"rows": rows, "count": len(rows)}


@router.post("/excel/export")
def excel_export(body: ExcelExportBody) -> dict:
    _validate_rows(body.rows)
    if not isinstance(body.rows, list):
        raise HTTPException(status_code=400, detail="rows 必须是列表")
    if not body.rows:
        raise HTTPException(status_code=400, detail="空表不能导出")
    try:
        if body.kind == "glossary":
            data = LexiconOps.export_glossary_excel_bytes(body.rows)
            filename = "glossary.xlsx"
        else:
            data = LexiconOps.export_preserve_excel_bytes(body.rows)
            filename = "text_preserve.xlsx"
    except LexiconOpsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Excel 导出失败: {exc}") from exc
    return {
        "filename": filename,
        "content_base64": LexiconOps.encode_content_base64(data),
        "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }


@router.post("/statistics")
async def start_statistics(request: Request, body: StatisticsBody) -> dict:
    _validate_rows(body.rows)
    if not body.rows:
        raise HTTPException(status_code=400, detail="没有可统计的条目")
    config, key = _snapshot(request, body.project_key, body.output_folder)
    rows = copy.deepcopy(body.rows)
    def compute(check_cancel, progress):
        check_cancel()
        progress("正在统计命中…")
        operation = LexiconOps.run_glossary_hit_statistics if body.kind == "glossary" else LexiconOps.run_preserve_hit_statistics
        result = operation(config, rows)
        with CacheManager.LOCK:
            _check_current(request, config, check_cancel)
        return {**result, "kind": body.kind, "project_key": key}
    return await _run_lexicon_job(request, kind="lexicon_statistics", project_key=key, message="准备统计", compute=compute, config_snapshot=config)


@router.post("/glossary/scan-candidates")
async def scan_glossary_candidates(request: Request, body: ExtractionBody) -> dict:
    if not body.confirm:
        raise HTTPException(status_code=400, detail=Localizer.get().lexicon_agent_confirm_glossary)
    _validate_rows(body.rows)
    config, key = _snapshot(request, body.project_key, body.output_folder)
    source, _ = LexiconOps.resolve_renpy_scan_paths(config)
    if source is None:
        raise HTTPException(status_code=400, detail="无法解析游戏目录，请先设置项目路径")
    # 术语候选全部由 Agent 判定：平台取配置的 Agent 接口，未配置直接失败，不回退规则。
    platform, agent_reason = _agent_platform(config)
    checkpoints = []
    def compute(check_cancel, progress, publish_event_callback = None):
        check_cancel()
        if platform is None:
            # 未配置 Agent 接口：明确失败，不用规则候选兜底。
            raise LexiconOpsError(Localizer.get().lexicon_agent_unset_glossary or agent_reason)
        def cancelled():
            try:
                check_cancel()
            except asyncio.CancelledError:
                return True
            return False
        payload = extract_glossary_candidates(config=config, target_path=str(source), platform=platform,
            progress_callback=lambda message, percent: progress(str(message), done=int(percent), total=100), cancel_callback=cancelled,
            event_callback=publish_event_callback, **_extraction_options(extract_glossary_candidates, body, checkpoint_completion=checkpoints.append))
        entries = payload.get("entries", [])
        if str(payload.get("status") or "completed") == "failed":
            # 全部分块失败或未配置 Agent：如实失败，不清空也不改写现有词库。
            raise LexiconOpsError(_agent_error(payload, agent_reason or Localizer.get().lexicon_agent_result_unavailable))
        if not entries:
            # 合法零候选：不写入，但必须回传当前完整词表，避免前端把表格清空。
            with CacheManager.LOCK:
                _check_current(request, config, check_cancel)
                repository = _repository(config)
                state = repository.load(config)
                rows = copy.deepcopy(body.rows) if body.rows is not None else _rows_from_state(state)
                candidates = state.analysis_candidates
                ids = _candidate_ids(rows, candidates)
                _check_current(request, config, check_cancel)
            return {**payload, "success": True, "message": Localizer.get().lexicon_agent_no_terms,
                "entries": rows, "added": 0, "updated": 0, "count_map": {}, "project_key": key,
                "storage_key": _storage_key(repository), "revision": state.assets.revision,
                "candidate_ids": ids, "raw_entries": [], "written": False}
        with CacheManager.LOCK:
            _check_current(request, config, check_cancel)
            repository = _repository(config)
            state = repository.load(config)
            rows = copy.deepcopy(body.rows) if body.rows is not None else _rows_from_state(state)
            # 只新增不存在的候选：已有条目的译文、注释与禁用状态一律不动。
            fresh = _fresh_entries(rows, state, entries)
            if not fresh:
                # 没有新候选时也要回传现有候选 ID，否则前端会丢掉候选标记。
                ids = _candidate_ids(rows, state.analysis_candidates)
                return {**payload, "success": True, "message": Localizer.get().lexicon_agent_terms_existing,
                    "entries": rows, "added": 0, "updated": 0, "count_map": {}, "project_key": key,
                    "storage_key": _storage_key(repository), "revision": state.assets.revision,
                    "candidate_ids": ids, "raw_entries": [], "written": False}
            merged, added, updated, counts = LexiconOps.merge_candidate_entries(rows, fresh)
            _check_current(request, config, check_cancel)
            candidates = repository.merge_analysis_terms(fresh)
            ids = _candidate_ids(merged, candidates)
            saved = repository.load(config)
        return {**payload, "success": True, "message": Localizer.get().lexicon_agent_terms_done, "entries": merged,
            "added": added, "updated": updated, "count_map": counts, "project_key": key,
            "storage_key": _storage_key(repository), "revision": saved.assets.revision,
            "candidate_ids": ids, "raw_entries": fresh, "written": True}
    return await _run_lexicon_job(request, kind="lexicon_scan_candidates", project_key=key, message="准备扫描术语候选", compute=_checkpointed_compute(compute, checkpoints), config_snapshot=config)


@router.post("/glossary/scan-characters")
async def scan_glossary_characters(request: Request, body: ExtractionBody) -> dict:
    if not body.confirm:
        raise HTTPException(status_code=400, detail=Localizer.get().lexicon_agent_confirm_characters)
    _validate_rows(body.rows)
    config, key = _snapshot(request, body.project_key, body.output_folder)
    source, _tl_root = LexiconOps.resolve_renpy_scan_paths(config)
    if source is None:
        raise HTTPException(status_code=400, detail="无法解析游戏目录")
    # 人名同样交给 Agent：先让模型抽取，再按模型给出的类别筛出角色，不重建旧候选。
    platform, agent_reason = _agent_platform(config)
    checkpoints = []
    def compute(check_cancel, progress, publish_event_callback = None):
        check_cancel()
        if platform is None:
            raise LexiconOpsError(Localizer.get().lexicon_agent_unset_characters or agent_reason)
        def cancelled():
            try:
                check_cancel()
            except asyncio.CancelledError:
                return True
            return False
        payload = extract_character_candidates(config=config, target_path=str(source), platform=platform,
            progress_callback=lambda message, percent: progress(str(message), done=int(percent), total=100), cancel_callback=cancelled,
            event_callback=publish_event_callback, **_extraction_options(extract_character_candidates, body, checkpoint_completion=checkpoints.append))
        names = [str(item) for item in payload.get("names", []) if str(item).strip()]
        if str(payload.get("status") or "completed") == "failed":
            raise LexiconOpsError(_agent_error(payload, agent_reason or Localizer.get().lexicon_agent_result_unavailable))
        if not names:
            # 零候选也要回传当前完整词表与候选 ID，避免前端清空表格。
            with CacheManager.LOCK:
                _check_current(request, config, check_cancel)
                repository = _repository(config)
                state = repository.load(config)
                rows = copy.deepcopy(body.rows) if body.rows is not None else _rows_from_state(state)
                ids = _candidate_ids(rows, state.analysis_candidates)
                _check_current(request, config, check_cancel)
            return {**payload, "success": True, "new_entries": [], "rows_delta": [], "removed_auto": 0,
                "entries": rows, "kept_count": len(rows),
                "message": Localizer.get().lexicon_agent_no_names, "written": False,
                "project_key": key, "candidate_ids": ids, "raw_entries": [],
                "storage_key": _storage_key(repository), "revision": state.assets.revision}
        progress(f"正在写入 {len(names)} 个角色候选…", done=80, total=100)
        with CacheManager.LOCK:
            _check_current(request, config, check_cancel)
            repository = _repository(config)
            state = repository.load(config)
            rows = copy.deepcopy(body.rows) if body.rows is not None else _rows_from_state(state)
            # 只在缺失时补候选：不重建、不覆盖，也不会把用户禁用的候选重新启用。
            fresh_names = _fresh_names(rows, state, names)
            if not fresh_names:
                ids = _candidate_ids(rows, state.analysis_candidates)
                return {**payload, "success": True, "new_entries": [], "rows_delta": [], "removed_auto": 0,
                    "entries": rows, "kept_count": len(rows),
                    "message": Localizer.get().lexicon_agent_names_existing,
                    "project_key": key, "candidate_ids": ids, "storage_key": _storage_key(repository),
                    "revision": state.assets.revision, "written": False, "warnings": payload.get("warnings", [])}
            # The Agent already decided the entity type. The legacy builder
            # filters word shapes and removes old automatic rows; neither is
            # allowed for this append-only Agent entry point.
            kept, removed_auto = rows, 0
            note = Localizer.get().lexicon_agent_character_candidate
            new_entries = [
                {"src": name, "dst": "", "info": note, "comment": note,
                 "type": "角色", "candidate": True, "candidate_confirmed": False,
                 "case_sensitive": False}
                for name in fresh_names
            ]
            _check_current(request, config, check_cancel)
            candidates = repository.merge_analysis_terms(new_entries)
            merged = kept + new_entries
            ids = _candidate_ids(merged, candidates)
            saved = repository.load(config)
            warnings = list(payload.get("warnings", []))
            auto_cache = dict(getattr(request.app.state.config, "glossary_auto_scan_cache", {}) or {})
            auto_cache[str(source.resolve())] = time.time()
            try:
                _save_fields(request, {"glossary_auto_scan_cache": auto_cache})
            except Exception:
                warnings.append("候选已保存，但扫描时间缓存保存失败")
        return {**payload, "success": True, "entries": merged, "new_entries": new_entries, "rows_delta": new_entries, "raw_entries": new_entries,
            "removed_auto": removed_auto, "kept_count": len(kept), "message": Localizer.get().lexicon_agent_names_done.format(count = len(new_entries)),
            "project_key": key, "candidate_ids": ids, "storage_key": _storage_key(repository), "revision": saved.assets.revision, "written": True, "warnings": warnings}
    return await _run_lexicon_job(request, kind="lexicon_scan_characters", project_key=key, message="准备扫描角色名字", compute=_checkpointed_compute(compute, checkpoints), config_snapshot=config)


@router.post("/glossary/classify")
def classify_glossary(body: ClassifyBody) -> dict:
    _validate_rows(body.rows)
    ner_count, kw_count, rows = LexiconOps.auto_classify_entries(body.rows)
    return {"rows": rows, "ner_count": ner_count, "kw_count": kw_count,
        "warnings": [] if ner_count else ["NER未识别可用分类；已使用关键词规则兜底"]}


@router.post("/glossary/translate")
async def translate_glossary(request: Request, body: TranslateBody) -> dict:
    _validate_rows(body.rows)
    if not body.confirm:
        raise HTTPException(status_code=400, detail="翻译会调用外部服务，需要 confirm=true")
    config, key = _snapshot(request, body.project_key, body.output_folder)
    tasks = LexiconOps.collect_glossary_translate_tasks(body.rows)
    if not tasks:
        raise HTTPException(status_code=400, detail="没有需要翻译的条目")
    platform = copy.deepcopy(config.get_platform(config.activate_platform))
    rows = copy.deepcopy(body.rows)
    def compute(check_cancel, progress):
        results = []
        warnings = []
        try:
            for start in range(0, len(tasks), 30):
                check_cancel()
                batch = tasks[start:start + 30]
                progress("正在翻译术语…", done=start, total=len(tasks))
                if body.mode == "fast":
                    source = LexiconOps.map_language_to_fasttranslator_code(config.source_language, is_target=False, traditional_chinese_enable=config.traditional_chinese_enable)
                    target = LexiconOps.map_language_to_fasttranslator_code(config.target_language, is_target=True, traditional_chinese_enable=config.traditional_chinese_enable)
                    translated = LexiconOps.translate_glossary_fast(batch, source_lang=source, target_lang=target, engine=body.engine)
                else:
                    translated = LexiconOps.translate_glossary_llm(batch, config, platform or {}, batch_size=30)
                results.extend(translated)
        except asyncio.CancelledError:
            warnings.append("已请求取消；保留本次已完成批次的译文草稿")
        except Exception as exc:
            warnings.append(f"翻译请求失败：{exc}")
        with CacheManager.LOCK:
            if _identity(request.app.state.config) != _identity(config):
                raise LexiconOpsError("项目已切换，未应用本次翻译结果")
        valid = [(index, str(dst).strip()) for index, dst in results if isinstance(dst, str) and dst.strip() and dst.strip() != rows[index].get("src", "").strip()]
        failed = len(tasks) - len(valid)
        return {"success": bool(valid), "message": f"已翻译 {len(valid)} 条；{failed} 条未获得有效译文",
            "results": [[index, dst] for index, dst in valid], "row_snapshots": rows,
            "failed_count": failed, "warnings": warnings + ([f"{failed} 条未获得有效译文"] if failed else []),
            "project_key": key, "row_count": len(rows)}
    return await _run_lexicon_job(request, kind="lexicon_translate", project_key=key, message="准备翻译术语", compute=compute, config_snapshot=config)


@router.post("/preserve/rescan-variables")
async def rescan_preserve_variables(request: Request, body: ProjectKeyBody) -> dict:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="重扫会覆盖禁翻表，需要 confirm=true")
    config, key = _snapshot(request, body.project_key, body.output_folder)
    def compute(check_cancel, progress):
        check_cancel()
        progress("正在扫描禁翻变量…")
        result = LexiconOps.scan_preserve_variables(config, check_cancel)
        with CacheManager.LOCK:
            _check_current(request, config, check_cancel)
            entries = result["entries"]
            _save_fields(request, {"text_preserve_data": entries, "text_preserve_enable": bool(result["enabled"])})
        return {**result, "rows": LexiconOps.normalize_preserve_rows(entries), "project_key": key, "written": True}
    return await _run_lexicon_job(request, kind="lexicon_preserve_rescan", project_key=key, message="准备扫描禁翻变量", compute=compute, config_snapshot=config)
