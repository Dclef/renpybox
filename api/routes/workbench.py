"""工作台和项目词库接口：复用项目资产仓库，避免写入全局配置。"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import os
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from api.jobs import Job
from module.Cache.CacheManager import CacheManager
from module.Engine.Engine import Engine
from module.Engine.TaskRequester import TaskRequester
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.PromptBuilder import PromptBuilder
from module.Workbench.AnalysisService import AnalysisResult, AnalysisServiceError, WorkbenchAnalysisService
from module.Workbench.WorkbenchData import (
    WORLD_FIELDS,
    merge_imported_character_cards,
    normalize_character_cards,
    normalize_text_list,
    normalize_worldbook,
)

router = APIRouter(prefix = "/api/workbench", tags = ["workbench"])


class AssetVersion(BaseModel):
    model_config = ConfigDict(extra = "forbid", strict = True)
    storage_key: str
    revision: int = Field(ge = 0)


class WorkbenchPatch(AssetVersion):
    worldbook: dict[str, str]
    characters: list[dict[str, Any]]
    worldbook_enabled: bool
    characters_enabled: bool


class AnalysisRequest(AssetVersion):
    action: Literal["scan", "all", "worldbook", "characters"]
    scope: Literal["current", "full"] = "current"


class PreviewRequest(AssetVersion):
    sample: str


class GlossaryPatch(AssetVersion):
    rows: list[dict[str, Any]]
    enabled: bool
    candidate_ids: list[str] = Field(default_factory = list)


def _repository(config: Any) -> ProjectAssetsRepository:
    repository = ProjectAssetsRepository.from_config(config)
    if not repository.has_storage:
        raise HTTPException(status_code = 409, detail = "请先在项目设置中选择项目或输出目录")
    return repository


def _key(repository: ProjectAssetsRepository) -> str:
    return os.path.normcase(os.path.abspath(repository.output_folder))


def _load(request: Request, version: AssetVersion | None = None):
    # 用临时配置视图叠加项目资产；错误或写失败不能污染共享运行配置。
    config = copy.deepcopy(request.app.state.config)
    repository = _repository(config)
    if version is not None and version.storage_key != _key(repository):
        raise HTTPException(status_code = 409, detail = "项目已切换，请重新加载当前项目资料后保存")
    state = repository.load_into_config(config)
    if version is not None and version.revision != state.assets.revision:
        raise HTTPException(status_code = 409, detail = "项目资料已更新，请重新加载后再保存，当前编辑内容仍保留")
    return repository, config, state


def _snapshot(repository: ProjectAssetsRepository, config: Any, state) -> dict[str, Any]:
    return {
        "storage_key": _key(repository),
        "revision": state.assets.revision,
        "worldbook": dict(config.renpy_workbench_worldbook_data),
        "characters": normalize_character_cards(config.renpy_workbench_character_cards),
        "worldbook_enabled": bool(config.renpy_workbench_worldbook_enable),
        "characters_enabled": bool(config.renpy_workbench_character_cards_enable),
        "worldbook_draft": normalize_worldbook(config.renpy_workbench_generated_worldbook_draft),
        "character_drafts": normalize_character_cards(config.renpy_workbench_generated_character_drafts),
    }


@router.get("")
def read_workbench(request: Request) -> dict[str, Any]:
    """读取当前项目的正式资料与尚未应用的草稿。"""
    with CacheManager.LOCK:
        return _snapshot(*_load(request))


@router.patch("")
def save_workbench(request: Request, body: WorkbenchPatch) -> dict[str, Any]:
    """保存世界观与角色卡；只替换工作台拥有的字段，保留词库和候选。"""
    unknown = set(body.worldbook) - set(WORLD_FIELDS)
    if unknown:
        raise HTTPException(status_code = 400, detail = "不支持的世界观字段：" + "、".join(sorted(unknown)))
    ids: set[str] = set()
    for card in body.characters:
        name = card.get("name")
        if not isinstance(name, str) or not name.strip():
            raise HTTPException(status_code = 400, detail = "角色名称不能为空")
        for field in ("aliases", "match_keywords", "sample_lines"):
            value = card.get(field, [])
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise HTTPException(status_code = 400, detail = f"{field} 必须是文字列表")
        for field in ("id", "name_translation", "identity", "personality", "speech_style", "relationship_notes", "prompt_notes"):
            if field in card and not isinstance(card[field], str):
                raise HTTPException(status_code = 400, detail = f"{field} 必须是文字")
        for field in ("enabled", "is_primary"):
            if field in card and not isinstance(card[field], bool):
                raise HTTPException(status_code = 400, detail = f"{field} 必须是布尔值")
        card_id = str(card.get("id", "")).strip()
        if card_id and card_id in ids:
            raise HTTPException(status_code = 400, detail = "角色 ID 重复，请重新加载项目资料")
        ids.add(card_id)
    if len(normalize_character_cards(body.characters)) != len(body.characters):
        raise HTTPException(status_code = 400, detail = "角色 ID 或名称重复，无法保存")
    with CacheManager.LOCK:
        repository, config, _ = _load(request, body)
        config.renpy_workbench_worldbook_data = {**config.renpy_workbench_worldbook_data, **body.worldbook}
        config.renpy_workbench_character_cards = normalize_character_cards(body.characters)
        config.renpy_workbench_worldbook_enable = body.worldbook_enabled
        config.renpy_workbench_character_cards_enable = body.characters_enabled
        state = repository.save_workbench_view(config)
        return _snapshot(repository, config, state)


@router.post("/apply-drafts")
def apply_drafts(request: Request, body: AssetVersion) -> dict[str, Any]:
    """按原工作台规则应用草稿，空世界观字段保留正式内容。"""
    with CacheManager.LOCK:
        repository, config, _ = _load(request, body)
        draft = normalize_worldbook(config.renpy_workbench_generated_worldbook_draft)
        drafts = normalize_character_cards(config.renpy_workbench_generated_character_drafts)
        if not any(draft.values()) and not drafts:
            raise HTTPException(status_code = 409, detail = "当前没有可应用的草稿")
        if any(draft.values()):
            current = config.renpy_workbench_worldbook_data
            config.renpy_workbench_worldbook_data = {**current, **{
                field: value or current.get(field, "") for field, value in draft.items()
            }}
            config.renpy_workbench_worldbook_enable = True
        if drafts:
            config.renpy_workbench_character_cards = merge_imported_character_cards(
                config.renpy_workbench_character_cards, _draft_overlays(drafts),
            )
            config.renpy_workbench_character_cards_enable = True
        config.renpy_workbench_generated_worldbook_draft = {}
        config.renpy_workbench_generated_character_drafts = []
        state = repository.save_workbench_view(config)
        return _snapshot(repository, config, state)


def _draft_overlays(cards: list[dict]) -> list[dict]:
    # 扫描和模型的空值、默认开关不能清空已有角色资料或启停状态。
    return [{key: value for key, value in card.items() if value and key not in {"enabled", "is_primary"}}
            for card in normalize_character_cards(cards)]


def _drafts(config: Any) -> tuple[dict, list]:
    return (
        normalize_worldbook(config.renpy_workbench_generated_worldbook_draft),
        normalize_character_cards(config.renpy_workbench_generated_character_drafts),
    )


def _merge_scan_drafts(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """沿用旧工作台的扫描合并规则，只补充空字段和候选线索。"""
    cards = {card["id"]: card for card in normalize_character_cards(existing)}
    for seed in normalize_character_cards(incoming):
        card = cards.setdefault(seed["id"], seed)
        for field in ("aliases", "match_keywords"):
            card[field] = normalize_text_list(card[field] + seed[field])
        for field in ("name_translation", "prompt_notes", "sample_lines"):
            if not card[field]:
                card[field] = seed[field]
    return sorted(cards.values(), key = lambda card: card["name"].casefold())


@router.get("/analysis")
def read_analysis(request: Request) -> dict:
    """返回当前项目最近一次扫描或 AI 草稿任务，包含真实线程收尾状态。"""
    repository = ProjectAssetsRepository.from_config(request.app.state.config)
    key = _key(repository) if repository.has_storage else None
    job = next((job for job in request.app.state.jobs.list()
                if job.kind == "workbench_analysis" and isinstance(job.result, dict)
                and job.result.get("storage_key") == key), None)
    return {"job": job.snapshot() if job else None}


@router.post("/analysis")
async def start_analysis(request: Request, body: AnalysisRequest) -> dict:
    """后台扫描或生成资料草稿；显式应用前不会覆盖正式资料。"""
    engine = Engine.get()
    with CacheManager.LOCK:
        _, config, _ = _load(request, body)
        original_drafts = _drafts(config)
        if not engine.try_set_status(Engine.Status.IDLE, Engine.Status.TESTING):
            raise HTTPException(status_code = 409, detail = "已有任务正在运行或收尾，请稍后再试")
    manager = request.app.state.jobs
    try:
        service = WorkbenchAnalysisService()
        if body.action != "scan":
            service.ensure_analysis_ready(config, engine_reserved = True)
        job = manager.create("workbench_analysis", cooperative_cancel = True)
    except Exception as exc:
        engine.release_status(Engine.Status.TESTING)
        if isinstance(exc, AnalysisServiceError):
            raise HTTPException(status_code = 400, detail = str(exc)) from exc
        raise
    job.result = {
        "storage_key": body.storage_key, "action": body.action, "scope": body.scope,
        "message": "准备扫描角色" if body.action == "scan" else "准备生成资料草稿",
        "worker_active": True,
    }
    loop = asyncio.get_running_loop()

    def check_cancel() -> None:
        if job.cancel_event.is_set():
            raise asyncio.CancelledError()

    def publish_progress(message: str) -> None:
        if job.result["worker_active"]:
            job.result["message"] = message
            manager.progress(job.id)

    def progress(message: str) -> None:
        check_cancel()
        loop.call_soon_threadsafe(publish_progress, message)

    service.progress_callback = progress

    def analyze() -> AnalysisResult:
        check_cancel()
        if body.action == "scan":
            progress("正在读取项目文本并扫描角色")
            items, summary = service.load_scope_items(config, body.scope)
            check_cancel()
            candidates = service.scanner.build_candidates(config, items, service.resolve_project_root(config))
            return AnalysisResult(body.scope, {}, [candidate.as_card_seed() for candidate in candidates], source_summary = summary)
        operation = {
            "all": service.analyze_all, "worldbook": service.generate_worldbook_only,
            "characters": service.generate_character_only,
        }[body.action]
        return operation(config, body.scope, engine_reserved = True)

    def compute() -> AnalysisResult:
        TaskRequester.bind_run_cancel_event(job.cancel_event)
        try:
            return analyze()
        finally:
            TaskRequester.unbind_run_cancel_event()

    async def worker(_: Job) -> dict:
        try:
            check_cancel()
            future = loop.run_in_executor(None, compute)
            try:
                result = await asyncio.shield(future)
            except asyncio.CancelledError:
                job.cancel_event.set()
                # 关闭时也必须等同步请求退出，不能提前释放引擎或写入晚到结果。
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.shield(future)
                raise
            check_cancel()
            # 与取消路由在同一事件循环串行提交，版本检查和短事务之间不让出执行权。
            with CacheManager.LOCK:
                repository, current, _ = _load(request, body)
                if _drafts(current) != original_drafts:
                    raise HTTPException(status_code = 409, detail = "项目草稿已更新，本次结果未保存，请重新加载")
                if body.action == "scan":
                    current.renpy_workbench_generated_character_drafts = _merge_scan_drafts(original_drafts[1], result.character_drafts)
                else:
                    current.renpy_workbench_generated_worldbook_draft = {
                        **original_drafts[0], **{key: value for key, value in normalize_worldbook(result.worldbook_draft).items() if value},
                    }
                    # 保留未命中的旧草稿和空值旧字段，新内容只更新待审核资料。
                    incoming = _draft_overlays(result.character_drafts)
                    current.renpy_workbench_generated_character_drafts = merge_imported_character_cards(original_drafts[1], incoming)
                current.renpy_workbench_last_analysis_scope = body.scope
                repository.save_workbench_view(current)
            job.result.update(
                message = "角色扫描完成，候选已存为草稿" if body.action == "scan" else "分析完成，资料已存为草稿",
                source_summary = result.source_summary,
                worldbook_fields = sum(bool(value) for value in result.worldbook_draft.values()),
                character_count = len(result.character_drafts),
            )
            manager.progress(job.id, done = 1, total = 1)
            return job.result
        except asyncio.CancelledError:
            job.result["message"] = "任务已取消，未保存本次结果"
            raise
        except Exception as exc:
            if job.cancel_event.is_set():
                job.result["message"] = "任务已取消，未保存本次结果"
                raise asyncio.CancelledError() from exc
            job.result["message"] = "任务失败，未保存本次结果"
            if isinstance(exc, HTTPException):
                raise RuntimeError(str(exc.detail)) from exc
            raise
        finally:
            job.result["worker_active"] = False
            engine.release_status(Engine.Status.TESTING)

    try:
        await manager.run(job.id, worker)
    except BaseException:
        job.result["worker_active"] = False
        engine.release_status(Engine.Status.TESTING)
        raise
    return {"job": job.snapshot()}


@router.post("/preview")
def preview(request: Request, body: PreviewRequest) -> dict[str, Any]:
    """复用翻译提示词构造器，预览已保存资料的角色命中与上下文。"""
    with CacheManager.LOCK:
        _, config, _ = _load(request, body)
    sources = [line.strip() for line in body.sample.splitlines() if line.strip()]
    builder = PromptBuilder(config)
    world_context = builder.build_worldbook_context()
    character_context = builder.build_character_context(sources, [])
    return {
        "world_context": world_context,
        "character_context": character_context,
        "matched_names": [card["name"] for card in builder.match_character_cards(sources, [])],
        "context": "\n\n".join(part for part in (world_context, character_context) if part),
    }


def _glossary_snapshot(repository: ProjectAssetsRepository, config: Any, state) -> dict[str, Any]:
    metadata = state.analysis_candidates.get("glossary_metadata", {})
    rows = []
    for candidate, items in ((False, state.assets.glossary), (True, state.analysis_candidates.get("items", []))):
        for item in items:
            data = item.to_dict() if hasattr(item, "to_dict") else item
            meta = metadata.get(data["record_id"], {})
            rows.append({
                "record_id": data["record_id"], "src": data["source"], "dst": data["target"],
                "info": data["note"], "regex": data["regex"], "enabled": data["enabled"],
                "case_sensitive": bool(meta.get("case_sensitive", False)),
                "type": str(meta.get("type", "")), "candidate": candidate,
                # 候选确认由前端展示；API 只给原始 type + candidate 标志
                "candidate_confirmed": False if candidate else bool(meta.get("candidate_confirmed", False)),
            })
    return {
        "storage_key": _key(repository), "revision": state.assets.revision,
        "rows": rows, "enabled": state.assets.glossary_enabled,
        "candidate_ids": [row["record_id"] for row in rows if row["candidate"]],
    }


@router.get("/glossary")
def read_glossary(request: Request) -> dict[str, Any]:
    """读取正式术语和未确认候选；有译文的 AI 候选也保持候选身份。"""
    with CacheManager.LOCK:
        return _glossary_snapshot(*_load(request))


@router.patch("/glossary")
def save_glossary(request: Request, body: GlossaryPatch) -> dict[str, Any]:
    """替换用户见过的词条；未出现在旧快照中的新候选保留。"""
    for row in body.rows:
        for field in ("src", "dst", "info", "type"):
            if not isinstance(row.get(field, ""), str):
                raise HTTPException(status_code = 400, detail = f"词库 {field} 必须是文字")
        for field in ("enabled", "regex", "case_sensitive", "candidate", "candidate_confirmed"):
            if field in row and not isinstance(row[field], bool):
                raise HTTPException(status_code = 400, detail = f"词库 {field} 必须是布尔值")
        if not row.get("src", "").strip():
            raise HTTPException(status_code = 400, detail = "术语原文不能为空")
    with CacheManager.LOCK:
        repository, config, _ = _load(request, body)
        state = repository.replace_glossary(body.rows, enabled = body.enabled, consumed_candidate_ids = body.candidate_ids)
        return _glossary_snapshot(repository, config, state)