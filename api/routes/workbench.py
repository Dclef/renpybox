"""工作台和项目词库接口：复用项目资产仓库，避免写入全局配置。"""

from __future__ import annotations

import copy
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from module.Cache.CacheManager import CacheManager
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.PromptBuilder import PromptBuilder
from module.Workbench.WorkbenchData import (
    WORLD_FIELDS,
    merge_character_card,
    normalize_character_cards,
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
            cards = {card["id"]: card for card in normalize_character_cards(config.renpy_workbench_character_cards)}
            for card in drafts:
                cards[card["id"]] = merge_character_card(cards[card["id"]], card) if card["id"] in cards else card
            config.renpy_workbench_character_cards = list(cards.values())
            config.renpy_workbench_character_cards_enable = True
        config.renpy_workbench_generated_worldbook_draft = {}
        config.renpy_workbench_generated_character_drafts = []
        state = repository.save_workbench_view(config)
        return _snapshot(repository, config, state)


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