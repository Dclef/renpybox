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
from module.Engine import LiveActivity
from module.Engine.Engine import Engine
from module.Engine.TaskRequester import TaskRequester
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.PromptBuilder import PromptBuilder
from module.Workbench.AnalysisService import AnalysisResult, AnalysisServiceError, WorkbenchAnalysisService
from module.Workbench.RelationMiner import RELATION_WORDS as _RELATION_WORDS
from module.Workbench.WorkbenchData import (
    RELATION_SAMPLE_LIMIT,
    RELATION_SOURCE_AI,
    RELATION_SOURCE_REJECTED,
    RELATION_SOURCE_RULE,
    WORLD_FIELDS,
    merge_imported_character_cards,
    merge_relations,
    normalize_character_card,
    normalize_character_cards,
    normalize_relation_chapters,
    normalize_text,
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


@router.get("/activity")
def read_activity() -> dict:
    """模型请求的实时进度：思考/正文增量 + 已耗时。

    前端在等待期间轮询这个接口，把「已耗时 15 秒」换成像样的实时输出。
    故意不加 CacheManager.LOCK：分析请求期间这把锁是放开的，抢锁会互相等。
    """
    return LiveActivity.snapshot()


class CharacterCleanRequest(AssetVersion):
    """角色清洗请求：让模型给扫描出来的名字归类，可选分批大小。"""
    batch_size: int = Field(default = 0, ge = 0, le = 200)


class RelationAnalyzeRequest(AssetVersion):
    """关系 AI 复核请求：只复核有源码证据的候选边。"""

    ref: Literal["规则证据", "全部"] = "规则证据"
    max_pairs: int = Field(default = 0, ge = 0, le = 500)


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
        # 共现是按源码重算的证据，重扫就该整体替换，不能和旧结果求并集。
        if seed.get("co_occurrence"):
            card["co_occurrence"] = seed["co_occurrence"]
        # 关系按来源整批替换：manual / rejected 永远保留，AI 的边不会被一次重扫清掉，
        # 只有本次来源（rule）的旧边被替换；撞上已否决边的来料由 merge_relations 丢掉，
        # 否则用户否决一次、扫一次就复活一次。
        if seed.get("relations"):
            card["relations"] = merge_relations(card.get("relations"), seed["relations"], RELATION_SOURCE_RULE)
        # 头像是目录约定的直接命中，重扫结果直接覆盖。
        card["avatar"] = seed.get("avatar") or card.get("avatar")
        # 台词数是扫描统计量，重扫一定刷新；解析出 0 时保留旧值，免得一次失败把数字抹掉。
        card["line_count"] = int(seed.get("line_count") or 0) or int(card.get("line_count") or 0)
    return sorted(cards.values(), key = lambda card: card["name"].casefold())


def _collect_rule_edges(cards: list[dict]) -> list[dict]:
    """把角色卡里 source=rule 的关系边整理成复核候选。

    只收有源码证据的边：note 里带着 RelationMiner 的首条原文；
    AI 编不出来的边不会出现在这里，模型也就没有自由发挥的空间。
    count/samples 用扫描时存下来的真实命中次数与多条证据，缺了才回落到 note。
    正式卡排在前面时同一条边只收首次出现的，避免正式+草稿重复计数。
    """
    # 关系词 -> 触发它的称谓词（可能有多个称谓词映射到同一个关系词，取第一个）。
    word_by_relation: dict[str, str] = {}
    for word, (relation, _category) in _RELATION_WORDS.items():
        word_by_relation.setdefault(relation, word)
    candidates: list[dict] = []
    # 逐张规范，不用 normalize_character_cards：它按 id 去重，
    # 正式卡和「同一角色」的草稿 id 相同，会被合并成一张，草稿上的规则边就复核不到了。
    seen: set[tuple[str, str, str]] = set()
    for raw in cards:
        card = normalize_character_card(raw)
        if card["name"] == "":
            continue
        for item in card.get("relations", []):
            if item.get("source") != RELATION_SOURCE_RULE:
                continue
            # 同一条边可能同时躺在正式资料和草稿里（应用过草稿、又重扫过）。
            # 按 (from, to, relation) 去重，先到先得——调用方保证正式卡在前，
            # 否则 count 会被算两遍，模型看到的「命中次数」直接虚高。
            key = (
                card["name"].casefold(),
                normalize_text(item.get("target", "")).casefold(),
                normalize_text(item.get("relation", "")).casefold(),
            )
            if key in seen:
                continue
            seen.add(key)
            note = str(item.get("note", ""))
            fallback = note[len("证据："):] if note.startswith("证据：") else note
            samples = [
                normalize_text(text) for text in (item.get("samples") or []) if normalize_text(text)
            ] or ([fallback] if fallback else [])
            candidates.append({
                "from": card["name"],
                "to": item.get("target", ""),
                "word": word_by_relation.get(item.get("relation", ""), ""),
                "relation": item.get("relation", ""),
                "category": item.get("category", ""),
                "count": int(item.get("count") or 1),
                "samples": samples[:RELATION_SAMPLE_LIMIT],
                # 章节证据跟着候选走：复核提示词用不上它，但写回时得原样还回去，
                # 否则一次「AI 复核」就把时间线赖以成图的数据抹了。
                "chapters": normalize_relation_chapters(item.get("chapters", [])),
            })
    return candidates


def _group_rule_edges(edges: list[dict]) -> list[dict]:
    """按 (from, to) 把同一对人物的多条规则边合并成一条复核候选。

    一对人物可能被多个称谓词挖出多条边（姐姐 / 家人 / 小姐），
    但复核问的是「这两个人是什么关系」，拆成多条只会让模型给出互相矛盾的结论。
    """
    grouped: dict[tuple[str, str], dict] = {}
    for edge in edges:
        key = (
            normalize_text(edge.get("from", "")).casefold(),
            normalize_text(edge.get("to", "")).casefold(),
        )
        current = grouped.get(key)
        if current is None:
            grouped[key] = {
                **edge,
                "relations": [edge.get("relation", "")],
                "count": max(int(edge.get("count") or 1), 1),
                "samples": list(edge.get("samples") or []),
                "chapters": normalize_relation_chapters(edge.get("chapters", [])),
            }
            continue
        current["count"] = int(current["count"]) + max(int(edge.get("count") or 1), 1)
        current["samples"] = (list(current["samples"]) + list(edge.get("samples") or []))[:RELATION_SAMPLE_LIMIT]
        # 章节按文件合并：同文件 count 相加、samples 去重截 2、行号取最早。
        # normalize_relation_chapters 已经实现了这套合并规则，直接复用别抄第二遍。
        current["chapters"] = normalize_relation_chapters(
            list(current.get("chapters") or []) + list(edge.get("chapters") or [])
        )
        relation = edge.get("relation", "")
        if relation and relation not in current["relations"]:
            current["relations"].append(relation)
        # 主语按正式资料优先：调用方已按「正式在前」的顺序传入。
        if not current.get("word") and edge.get("word"):
            current["word"] = edge.get("word")
    return list(grouped.values())


def _clean_candidates(cards: list[dict]) -> tuple[list[dict], dict[str, dict]]:
    """把草稿角色卡整理成清洗候选；返回候选列表和「名字 -> 卡」的索引。"""
    candidates: list[dict] = []
    index: dict[str, dict] = {}
    for card in cards:
        name = normalize_text(card.get("name", ""))
        if name == "":
            continue
        variable = next(
            (word for word in card.get("match_keywords", []) if normalize_text(word).casefold() != name.casefold()),
            "",
        )
        candidates.append({
            "name": name,
            "lines": int(card.get("line_count") or 0),
            "variable": variable,
            "samples": list(card.get("sample_lines", []))[:2],
        })
        index[name.casefold()] = card
    return candidates, index


def _apply_clean(cards: list[dict], judged: dict[str, dict]) -> tuple[list[dict], int, int]:
    """按判定重写草稿：noise 丢掉，其余补阵营/主角标记，并把依据写进 note。

    只改草稿，不碰正式角色资料——清洗的是扫描结果，用户已经确认过的卡不动。
    这里也绝不改 relations：清洗只回答「谁是人」，关系归 AI 复核那条线管，
    顺手改关系会让用户改好的边莫名消失。
    """
    kept: list[dict] = []
    dropped = 0
    enriched = 0
    for card in cards:
        key = normalize_text(card.get("name", "")).casefold()
        verdict = judged.get(key)
        if verdict is None:
            kept.append(card)
            continue
        if verdict["role"] == "noise":
            dropped += 1
            continue
        changed = False
        if verdict["faction"] and not normalize_text(card.get("faction", "")):
            card["faction"] = verdict["faction"]
            changed = True
        # 只有在判定主角时才置位：判成 side/walkon 不清用户手工勾过的 is_primary，
        # 那是人工标记，模型无权推翻。
        if verdict["role"] == "main" and not bool(card.get("is_primary")):
            card["is_primary"] = True
            changed = True
        note = verdict["note"]
        if note:
            existing = normalize_text(card.get("prompt_notes", ""))
            marker = f"AI 清洗：{note}"
            if marker not in existing:
                card["prompt_notes"] = normalize_text(existing + chr(10) + marker) if existing else marker
                changed = True
        if changed:
            enriched += 1
        kept.append(card)
    return kept, dropped, enriched


@router.post("/characters/clean")
def clean_characters(request: Request, body: CharacterCleanRequest) -> dict:
    """让模型清洗扫描出来的角色草稿。

    扫描是机械的：每句台词的说话人都被收进来，所以名单里混着报幕员、音效、
    未解析的占位符、群戏标签。这一步只做归类，服务端按输入名单过滤，
    模型编出来的名字直接丢弃；结果写回「待审核草稿」，正式资料不动。
    """
    service = WorkbenchAnalysisService()
    with CacheManager.LOCK:
        repository, config, state = _load(request, body)
        drafts = normalize_character_cards(config.renpy_workbench_generated_character_drafts)
        candidates, _ = _clean_candidates(drafts)
        worldbook = normalize_worldbook(config.renpy_workbench_worldbook_data)
        draft_world = normalize_worldbook(config.renpy_workbench_generated_worldbook_draft)
        if any(draft_world.values()) and not any(worldbook.values()):
            worldbook = draft_world
    if not candidates:
        raise HTTPException(status_code = 400, detail = "没有待清洗的角色草稿：先跑一次角色扫描")
    try:
        # 模型调用放在锁外，避免长时间占住全局缓存锁。
        result = service.clean_characters(
            config, candidates, worldbook, batch_size = body.batch_size or None,
        )
    except AnalysisServiceError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc

    with CacheManager.LOCK:
        repository, config, state = _load(request, body)
        drafts = normalize_character_cards(config.renpy_workbench_generated_character_drafts)
        kept, dropped, enriched = _apply_clean(drafts, result["judged"])
        config.renpy_workbench_generated_character_drafts = normalize_character_cards(kept)
        state = repository.save_workbench_view(config)
    return {
        "ok": True,
        "judged": len(result["judged"]),
        "dropped": dropped,
        "enriched": enriched,
        "think": result.get("think", ""),
        "usage": {
            "prompt_tokens": result["prompt_tokens"],
            "completion_tokens": result["completion_tokens"],
        },
        "snapshot": _snapshot(repository, config, state),
    }


def _apply_relation_review(
    cards: list[dict],
    applied: dict[tuple[str, str], dict],
    rejected: dict[tuple[str, str], dict],
) -> tuple[list[dict], set[tuple[str, str]], set[tuple[str, str]]]:
    """把复核结论写进一批角色卡；返回 (卡片, 确认的对, 否决的对)。

    keep=true：该对人物的全部规则边合成一条 source=ai 的边，关系词/类别用模型结论，
    count 取这些规则边的命中次数之和，samples 合并去重。
    keep=false：该对人物的规则边换成 source=rejected 的留档边，每个原关系词各一条，
    note 写「AI 否决：<reason>」，relation/category/count/samples 原样保留。
    否决的边不再画线，但数据必须留着——否则下次重扫又会长回来，用户否决一百次也没用。

    只改 relations 字段，绝不删除角色卡。
    返回的集合是「人物对」，调用方据此报边对数：一张卡可能挂着好几条规则边，
    按条数报会让用户看到的数字对不上人。
    """
    confirmed: set[tuple[str, str]] = set()
    vetoed: set[tuple[str, str]] = set()
    for card in cards:
        relations = list(card.get("relations", []) or [])
        if not relations:
            continue
        owner = normalize_text(card.get("name", "")).casefold()
        # 先把同一对的规则边收拢：复核问的是「这两个人是什么关系」，
        # 不是「每个称谓词各是什么关系」，拆开问只会拿到互相矛盾的答案。
        grouped: dict[tuple[str, str], list[dict]] = {}
        kept: list[dict] = []
        for item in relations:
            target = normalize_text(item.get("target", ""))
            pair_key = (owner, target.casefold())
            if (
                item.get("source") == RELATION_SOURCE_RULE
                and (pair_key in applied or pair_key in rejected)
            ):
                grouped.setdefault(pair_key, []).append(item)
                continue
            kept.append(item)
        for pair_key, items in grouped.items():
            target = normalize_text(items[0].get("target", ""))
            miss = rejected.get(pair_key)
            if miss is not None:
                vetoed.add(pair_key)
                # 每个原关系词留一条：粒度比「一对人一条」细，用户看得见到底哪条判定被否了。
                for item in items:
                    kept.append({
                        "target": target,
                        "relation": item.get("relation", ""),
                        "category": item.get("category", ""),
                        "note": f"AI 否决：{miss['reason']}" if miss.get("reason") else "AI 否决",
                        "source": RELATION_SOURCE_REJECTED,
                        "count": max(int(item.get("count") or 1), 1),
                        "samples": list(item.get("samples") or [])[:RELATION_SAMPLE_LIMIT],
                        # 否决边保留原章节：用户想看「被否的这条证据出现在哪几章」时还得有数据。
                        "chapters": list(item.get("chapters") or []),
                    })
                continue
            pair = applied[pair_key]
            confirmed.add(pair_key)
            count = 0
            samples: list[str] = []
            chapters: list[dict] = []
            for item in items:
                count += max(int(item.get("count") or 1), 1)
                note = normalize_text(item.get("note", ""))
                fallback = note[len("证据："):] if note.startswith("证据：") else note
                for sample in (list(item.get("samples") or []) or ([fallback] if fallback else [])):
                    text = normalize_text(sample)
                    if text and text not in samples:
                        samples.append(text)
                chapters.extend(list(item.get("chapters") or []))
            kept.append({
                "target": target,
                "relation": normalize_text(pair.get("relation", "")) or items[0].get("relation", ""),
                "category": pair.get("category", "") or items[0].get("category", ""),
                # note 留首条证据，兼容只读 note 的旧显示。
                "note": normalize_text(items[0].get("note", "")),
                "source": RELATION_SOURCE_AI,
                "count": count,
                "samples": samples[:RELATION_SAMPLE_LIMIT],
                # 合并后的 ai 边也得带着章节：复核不该让时间线少掉一列证据。
                "chapters": normalize_relation_chapters(chapters),
            })
        card["relations"] = kept
    return cards, confirmed, vetoed


@router.post("/relations/analyze")
def analyze_relations(request: Request, body: RelationAnalyzeRequest) -> dict:
    """AI 复核规则挖出的候选关系，结果写回角色卡。

    keep=true 用 source=ai 覆盖该对的规则边；keep=false 把该对换成 source=rejected
    的留档边（图上不画线、重扫也不会复活）。候选同时来自正式资料和草稿，
    否则用户没点「应用草稿」时这条复核线上一条边都拿不到。
    """
    service = WorkbenchAnalysisService()
    # 复核要请求模型，先在锁内取快照；模型调用放锁外，避免长时间占住全局缓存锁。
    with CacheManager.LOCK:
        repository, config, state = _load(request, body)
        cards = normalize_character_cards(config.renpy_workbench_character_cards)
        drafts = normalize_character_cards(config.renpy_workbench_generated_character_drafts)
        # 正式资料在前：同一 from/to 冲突时以正式卡的证据为准。
        # 目前只复核规则边：manual 是人定的不用复核，AI 边已经复核过，rejected 已否决。
        unique_edges = _group_rule_edges(_collect_rule_edges(cards + drafts))
        worldbook = normalize_worldbook(config.renpy_workbench_worldbook_data)
        draft = normalize_worldbook(config.renpy_workbench_generated_worldbook_draft)
        if any(draft.values()) and not any(worldbook.values()):
            worldbook = draft

    try:
        result = service.analyze_relations(config, unique_edges, worldbook, max_pairs = body.max_pairs or None)
    except AnalysisServiceError as exc:
        raise HTTPException(status_code = 400, detail = str(exc)) from exc

    applied = {(str(item["from"]).casefold(), str(item["to"]).casefold()): item for item in result["applied"]}
    rejected = {(str(item["from"]).casefold(), str(item["to"]).casefold()): item for item in result["rejected"]}

    with CacheManager.LOCK:
        repository, config, state = _load(request, body)
        if state.assets.revision != body.revision:
            raise HTTPException(status_code = 409, detail = "项目资料已更新，请重新加载后再复核")
        # 正式资料与草稿各写各的集合，绝不合并：草稿是待审区，混进正式资料等于替用户点了「应用」。
        cards, applied_here, rejected_here = _apply_relation_review(
            normalize_character_cards(config.renpy_workbench_character_cards), applied, rejected,
        )
        drafts, draft_applied, draft_rejected = _apply_relation_review(
            normalize_character_cards(config.renpy_workbench_generated_character_drafts), applied, rejected,
        )
        config.renpy_workbench_character_cards = normalize_character_cards(cards)
        config.renpy_workbench_generated_character_drafts = normalize_character_cards(drafts)
        state = repository.save_workbench_view(config)
    return {
        "ok": True,
        # 计数用「边对数」：一张卡可能挂着好几条规则边，按条数报会让用户看到的数字对不上人。
        "applied": len(applied_here | draft_applied),
        "rejected": len(rejected_here | draft_rejected),
        "think": result.get("think", ""),
        "usage": {
            "prompt_tokens": result["prompt_tokens"],
            "completion_tokens": result["completion_tokens"],
        },
        "snapshot": _snapshot(repository, config, state),
    }


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

    def publish_progress(message: str, percent: int | None = None) -> None:
        if job.result["worker_active"]:
            job.result["message"] = message
            if isinstance(percent, int):
                manager.progress(job.id, done = max(0, min(100, percent)), total = 100)
            else:
                manager.progress(job.id)

    def progress(message: str, percent: int | None = None) -> None:
        check_cancel()
        loop.call_soon_threadsafe(publish_progress, message, percent)

    service.progress_callback = progress

    def analyze() -> AnalysisResult:
        check_cancel()
        if body.action == "scan":
            progress("正在读取项目文本…", 5)
            items, summary = service.load_scope_items(config, body.scope)
            check_cancel()
            progress(f"已读取 {len(items)} 条文本，正在扫描角色台词…", 45)
            candidates = service.scanner.build_candidates(
                config,
                items,
                service.resolve_project_root(config),
                lambda text: progress(text, 75),
            )
            progress(f"角色扫描完成，共 {len(candidates)} 个候选", 98)
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