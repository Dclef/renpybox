"""词库 / 禁翻 API：Excel、统计、候选扫描、分类、翻译；无 Qt。"""

from __future__ import annotations

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
from module.Extract.GlossaryCandidateService import extract_glossary_candidates
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
            def run_compute():
                from module.Engine.TaskRequester import TaskRequester
                bind = getattr(TaskRequester, "bind_run_cancel_event", None)
                unbind = getattr(TaskRequester, "unbind_run_cancel_event", None)
                if bind:
                    bind(job.cancel_event)
                try:
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
        return {"job": job.snapshot() if job else None, "project_key": _project_key(request.app.state.config), "output_folder": request.app.state.config.output_folder}


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
async def scan_glossary_candidates(request: Request, body: ProjectKeyBody) -> dict:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="扫描术语候选可能调用外部模型，需要 confirm=true")
    _validate_rows(body.rows)
    config, key = _snapshot(request, body.project_key, body.output_folder)
    source, _ = LexiconOps.resolve_renpy_scan_paths(config)
    if source is None:
        raise HTTPException(status_code=400, detail="无法解析游戏目录，请先设置项目路径")
    platform = copy.deepcopy(config.get_platform(config.activate_platform))
    def compute(check_cancel, progress):
        check_cancel()
        def cancelled():
            try:
                check_cancel()
            except asyncio.CancelledError:
                return True
            return False
        payload = extract_glossary_candidates(config=config, target_path=str(source), platform=platform,
            progress_callback=lambda message, percent: progress(str(message), done=int(percent), total=100), cancel_callback=cancelled)
        entries = payload.get("entries", [])
        if not entries:
            raise LexiconOpsError("未生成可用术语候选：" + "；".join(payload.get("warnings", [])))
        with CacheManager.LOCK:
            _check_current(request, config, check_cancel)
            repository = _repository(config)
            state = repository.load(config)
            rows = copy.deepcopy(body.rows) if body.rows is not None else _rows_from_state(state)
            merged, added, updated, counts = LexiconOps.merge_candidate_entries(rows, entries)
            _check_current(request, config, check_cancel)
            candidates = repository.merge_analysis_terms(entries)
            ids = _candidate_ids(merged, candidates)
            saved = repository.load(config)
        return {**payload, "success": True, "message": "术语候选扫描完成", "entries": merged,
            "added": added, "updated": updated, "count_map": counts, "project_key": key,
            "storage_key": _storage_key(repository), "revision": saved.assets.revision,
            "candidate_ids": ids, "raw_entries": entries, "written": True}
    return await _run_lexicon_job(request, kind="lexicon_scan_candidates", project_key=key, message="准备扫描术语候选", compute=compute, config_snapshot=config)


@router.post("/glossary/scan-characters")
async def scan_glossary_characters(request: Request, body: ProjectKeyBody) -> dict:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="扫描将替换旧自动角色候选，需要 confirm=true")
    _validate_rows(body.rows)
    config, key = _snapshot(request, body.project_key, body.output_folder)
    source, tl_root = LexiconOps.resolve_renpy_scan_paths(config)
    if source is None:
        raise HTTPException(status_code=400, detail="无法解析游戏目录")
    def compute(check_cancel, progress):
        check_cancel()
        progress("正在扫描角色名字…")
        names = LexiconOps.extract_names_from_source(source, check_cancel)
        names |= LexiconOps.extract_names_from_miss_files(source, LexiconOps.effective_tl_name(config, tl_root), check_cancel)
        if not names:
            return {"success": True, "new_entries": [], "rows_delta": [], "removed_auto": 0, "message": "未找到角色名"}
        with CacheManager.LOCK:
            _check_current(request, config, check_cancel)
            repository = _repository(config)
            state = repository.load(config)
            rows = copy.deepcopy(body.rows) if body.rows is not None else _rows_from_state(state)
            kept, new_entries, removed_auto = LexiconOps.build_character_scan_entries(rows, names)
            removed_ids = {row.get("record_id", "") for row in rows if row.get("candidate") and LexiconOps._is_auto_character_entry(row)}
            _check_current(request, config, check_cancel)
            candidates = repository.replace_analysis_terms(new_entries, removed_record_ids=removed_ids)
            merged = kept + new_entries
            ids = _candidate_ids(merged, candidates)
            saved = repository.load(config)
            warnings = []
            auto_cache = dict(getattr(request.app.state.config, "glossary_auto_scan_cache", {}) or {})
            auto_cache[str(source.resolve())] = time.time()
            try:
                _save_fields(request, {"glossary_auto_scan_cache": auto_cache})
            except Exception:
                warnings.append("候选已保存，但扫描时间缓存保存失败")
        return {"success": True, "entries": merged, "new_entries": new_entries, "rows_delta": new_entries,
            "removed_auto": removed_auto, "kept_count": len(kept), "message": f"找到 {len(new_entries)} 个角色名候选",
            "project_key": key, "candidate_ids": ids, "storage_key": _storage_key(repository), "revision": saved.assets.revision, "written": True, "warnings": warnings}
    return await _run_lexicon_job(request, kind="lexicon_scan_characters", project_key=key, message="准备扫描角色名字", compute=compute, config_snapshot=config)


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
