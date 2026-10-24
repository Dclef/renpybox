from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any, Mapping


WORLD_FIELDS: tuple[str, ...] = (
    "project_name",
    "genre",
    "setting_summary",
    "era_background",
    "tone_style",
    "narrative_rules",
    "format_rules",
    "spoiler_notes",
    "reference_notes",
)

CHARACTER_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "aliases",
    "name_translation",
    "match_keywords",
    "identity",
    "personality",
    "speech_style",
    "relationship_notes",
    "prompt_notes",
    "sample_lines",
    "enabled",
    "is_primary",
    "faction",
    "relations",
    "co_occurrence",
    "avatar",
    # 扫描出来的台词句数。图谱按它定节点大小、名册按它排序，
    # 不能拿 sample_lines 的长度顶替——那是抽样，最多几十条。
    "line_count",
)

# 关系类别：既决定图谱里的连线颜色，也决定 relationship_notes 的措辞。
RELATION_CATEGORIES: tuple[str, ...] = ("family", "romantic", "friendly", "hostile", "work", "other")
RELATION_CATEGORY_LABELS: dict[str, str] = {
    "family": "亲属",
    "romantic": "恋慕",
    "friendly": "友好",
    "hostile": "敌对",
    "work": "主从同僚",
    "other": "其他",
}
# 关系来源决定「谁能覆盖谁」：manual 永远保留，AI 重算和规则重扫各管各的那批。
# rule 是 RelationMiner 从源码挖出来的证据边，重扫时整批替换；
# 它不能顺手清掉 ai 的结论，否则一次「扫描」就把模型分析过的关系抹了。
RELATION_SOURCE_MANUAL = "manual"
RELATION_SOURCE_AI = "ai"
RELATION_SOURCE_RULE = "rule"
# rejected 是「AI 复核判定误判」的留档边：图上不画线，但数据必须留住——
# 用户否决过一次，重扫或换个模型再算都不该让它自己复活。
RELATION_SOURCE_REJECTED = "rejected"
RELATION_SOURCES: tuple[str, ...] = (
    RELATION_SOURCE_MANUAL,
    RELATION_SOURCE_AI,
    RELATION_SOURCE_RULE,
    RELATION_SOURCE_REJECTED,
)
# 会被任何一次重扫/重算整批保留、只增不减的来源。
RELATION_PINNED_SOURCES: tuple[str, ...] = (RELATION_SOURCE_MANUAL, RELATION_SOURCE_REJECTED)
RELATION_LIMIT = 64
# 每条边最多留几条源码证据；证据是模型判断的唯一依据，只留第一条太单薄。
RELATION_SAMPLE_LIMIT = 3
RELATION_SAMPLE_MAX_CHARS = 120
# 章节证据：这条关系在各剧本文件里的命中分布，前端「关系时间线」按它画矩阵。
# 上限对齐 RelationMiner：列太多图就看不清了，解析端先截一刀，这里再兜一次。
RELATION_CHAPTER_LIMIT = 32
RELATION_CHAPTER_SAMPLE_LIMIT = 2

ANALYSIS_SCOPE_CURRENT = "current"
ANALYSIS_SCOPE_FULL = "full"


def normalize_text(value: Any) -> str:
    """将任意输入规范为字符串。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def normalize_text_list(values: Any, *, unique: bool = True) -> list[str]:
    """规范化字符串列表，并去重。"""
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_text(value)
        if text == "":
            continue
        key = text.casefold()
        if unique and key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def build_character_id(name: str) -> str:
    """根据角色名构建稳定 ID。"""
    cleaned = normalize_text(name).casefold() or "unknown"
    digest = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[:12]
    return f"character_{digest}"


def normalize_relation_category(value: Any) -> str:
    """关系类别只认白名单，其余归到「其他」。"""
    text = normalize_text(value).casefold()
    return text if text in RELATION_CATEGORIES else "other"


def normalize_relation_source(value: Any) -> str:
    """关系来源：人工、AI、规则扫描或已否决；来源不明的按人工处理，避免被重算覆盖。"""
    text = normalize_text(value).casefold()
    return text if text in RELATION_SOURCES else RELATION_SOURCE_MANUAL


def normalize_relation_samples(values: Any) -> list[str]:
    """规范化关系证据：去空、去重、截断，最多留 RELATION_SAMPLE_LIMIT 条。

    证据是模型复核时唯一的判断依据，多留几条比只留第一条靠谱得多。
    """
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_text(value)
        if text == "":
            continue
        if len(text) > RELATION_SAMPLE_MAX_CHARS:
            text = text[:RELATION_SAMPLE_MAX_CHARS]
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= RELATION_SAMPLE_LIMIT:
            break
    return result


def relation_chapter_key(name: str) -> tuple:
    """章节排序键：把文件名切成「文本/数字」交替的块，数字块按数值比较。

    events2 要排在 events10 前面——纯字典序会反过来，时间线的列顺序就乱了。
    """
    parts = re.split(r"(\d+)", normalize_text(name).casefold())
    return tuple((1, int(part)) if part.isdigit() else (0, part) for part in parts if part != "")


def _as_list(values: Any) -> list[Any]:
    """把可能是标量的输入统一成列表。"""
    if values is None:
        return []
    if isinstance(values, (list, tuple)):
        return list(values)
    return [values]


def normalize_relation_chapters_samples(values: Any) -> list[str]:
    """章节里的证据原文：去空、去重、截断，最多 RELATION_CHAPTER_SAMPLE_LIMIT 条。"""
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_text(value)
        if text == "":
            continue
        if len(text) > RELATION_SAMPLE_MAX_CHARS:
            text = text[:RELATION_SAMPLE_MAX_CHARS]
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= RELATION_CHAPTER_SAMPLE_LIMIT:
            break
    return result


def normalize_relation_chapters(values: Any) -> list[dict[str, Any]]:
    """规范化章节证据：每项 {file, line, count, samples}。

    file 为空视为脏数据直接丢掉（没有文件名这个格子就没法落到矩阵列上）；
    count ≥ 1、samples 最多 2 条每条 120 字、总项数不超过 RELATION_CHAPTER_LIMIT；
    同一文件出现多次时合并 count 并并集证据，行号取最早的那次。
    """
    if values is None:
        return []
    if isinstance(values, Mapping):
        values = [values]
    if not isinstance(values, (list, tuple)):
        return []

    merged: dict[str, dict[str, Any]] = {}
    for raw in values:
        source: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
        name = normalize_text(source.get("file", "")).replace("\\", "/").lstrip("/")
        if name == "" or ".." in name.split("/"):
            continue
        count = normalize_positive_int(source.get("count", 1))
        line = normalize_positive_int(source.get("line", 1))
        chapter = merged.get(name.casefold())
        if chapter is None:
            chapter = {"file": name, "line": line if line > 0 else 1, "count": 0, "samples": []}
            merged[name.casefold()] = chapter
        else:
            # 同一文件重复出现：行号留最早命中的那次，次数相加。
            earliest = line if line > 0 else 1
            chapter["line"] = min(chapter["line"], earliest)
        chapter["count"] += count if count > 0 else 1
        chapter["samples"] = normalize_relation_chapters_samples(
            list(chapter["samples"]) + _as_list(source.get("samples"))
        )

    result = sorted(merged.values(), key = lambda item: relation_chapter_key(item["file"]))
    if len(result) > RELATION_CHAPTER_LIMIT:
        # 章节太多时优先保留命中次数最多的那些，再按自然序输出：
        # 时间线只关心「这段关系集中在哪几章」，稀薄的长尾可以牺牲。
        busiest = sorted(result, key = lambda item: -int(item["count"]))[:RELATION_CHAPTER_LIMIT]
        keep = {item["file"].casefold() for item in busiest}
        result = [item for item in result if item["file"].casefold() in keep]
    return result


def normalize_relation(raw: Any) -> dict[str, Any] | None:
    """规范化单条人物关系；没有对象名时视为无效。

    count 是这条边被源码命中的次数，samples 是最多三条原文证据：
    少了它们，模型只能凭一个关系词猜，复核等于白算。
    """
    source: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
    target = normalize_text(source.get("target", ""))
    if target == "":
        return None
    count = normalize_positive_int(source.get("count", 1))
    return {
        "target": target,
        "relation": normalize_text(source.get("relation", "")),
        "category": normalize_relation_category(source.get("category", "")),
        "note": normalize_text(source.get("note", "")),
        "source": normalize_relation_source(source.get("source", "")),
        # 缺省视作 1：老数据没有这个键，但它确实代表一条命中的边。
        "count": count if count > 0 else 1,
        "samples": normalize_relation_samples(source.get("samples", [])),
        # 章节证据：老数据没有这个键时给空列表，前端按「没有章节信息」处理。
        "chapters": normalize_relation_chapters(source.get("chapters", [])),
    }


def normalize_relations(values: Any) -> list[dict[str, Any]]:
    """规范化人物关系列表：按「对象 + 关系词」去重，人工关系优先。"""
    if values is None:
        return []
    if isinstance(values, Mapping):
        values = [values]
    if not isinstance(values, (list, tuple)):
        return []

    result: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], int] = {}
    for raw in values:
        item = normalize_relation(raw)
        if item is None:
            continue
        key = (item["target"].casefold(), item["relation"].casefold())
        index = seen.get(key)
        if index is not None:
            existing = result[index]
            if existing["source"] != RELATION_SOURCE_MANUAL and item["source"] == RELATION_SOURCE_MANUAL:
                # 人工结论胜出，但证据不能丢：把重复项的 count/samples/chapters 并进来。
                item["count"] = max(int(existing.get("count", 0)), int(item.get("count", 0)))
                item["samples"] = normalize_relation_samples(
                    list(existing.get("samples", [])) + list(item.get("samples", []))
                )
                item["chapters"] = normalize_relation_chapters(
                    list(existing.get("chapters", [])) + list(item.get("chapters", []))
                )
                result[index] = item
                continue
            # 同一对边被重复写入时保留较大的 count 与并集证据，别把抹平的次数当真相。
            existing["count"] = max(int(existing.get("count", 0)), int(item.get("count", 0)))
            existing["samples"] = normalize_relation_samples(
                list(existing.get("samples", [])) + list(item.get("samples", []))
            )
            # 章节按文件合并：同文件的 count 相加、samples 去重、行号取最早。
            existing["chapters"] = normalize_relation_chapters(
                list(existing.get("chapters", [])) + list(item.get("chapters", []))
            )
            continue
        seen[key] = len(result)
        result.append(item)
    return result[:RELATION_LIMIT]


def normalize_co_occurrence(values: Any) -> dict[str, int]:
    """规范化共现证据：只留正数，按次数降序。"""
    if not isinstance(values, Mapping):
        return {}

    counts: dict[str, int] = {}
    for name, count in values.items():
        cleaned = normalize_text(name)
        if cleaned == "":
            continue
        try:
            weight = int(count)
        except (TypeError, ValueError):
            continue
        if weight > 0:
            counts[cleaned] = max(weight, counts.get(cleaned, 0))
    return dict(sorted(counts.items(), key = lambda pair: (-pair[1], pair[0].casefold())))


def normalize_avatar(raw: Any) -> dict[str, Any] | None:
    """规范化头像：只接受 game/ 内的相对路径，其余一律当作没有头像。

    没有头像（None）是正常状态，前端据此画首字色块；这里不生成任何图片。
    路径同时保留 relative_path 与 relative 两个键：模块内统一用 relative_path，
    前端组件读的是 relative，两个都给一份省得来回转换。
    """
    source: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
    relative = normalize_text(source.get("relative_path") or source.get("relative", ""))
    relative = relative.replace("\\", "/").lstrip("/")
    if relative == "" or ".." in relative.split("/"):
        return None
    try:
        width = int(source.get("width", 0))
        height = int(source.get("height", 0))
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return {
        "kind": normalize_text(source.get("kind", "")),
        "relative_path": relative,
        "relative": relative,
        "width": width,
        "height": height,
    }


def normalize_positive_int(raw: Any) -> int:
    """把扫描出来的计数规范成非负整数：解析不出来就当作 0（还没扫过）。"""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def merge_relations(
    base: Any,
    incoming: Any,
    source: str = RELATION_SOURCE_AI,
) -> list[dict[str, Any]]:
    """按来源整批替换地合并关系。

    规则（顺序即优先级）：
    1. base 里 source == manual 的行永远保留，重扫和重算都动不了；
    2. base 里 source == rejected 的行同样永远保留——那是用户否决过的边，
       重扫或换个模型再算都不该让它自己复活，否则「否决」等于没做；
    3. base 里既不是 manual、也不是本次写入来源的行保留——一次 rule 重扫
       不能把 ai 已经分析出来的边清掉，反之亦然；
    4. 本次写入来源的行整批替换，旧结论不残留；
    5. 同一 target + relation 冲突时 manual 优先（由 normalize_relations 保证）。

    传入来源统一归一化：来源不明的按 manual 处理，避免被重扫误删。
    """
    incoming_source = normalize_relation_source(source)
    pinned: list[dict[str, Any]] = []
    vetoed: set[tuple[str, str]] = set()
    others: list[dict[str, Any]] = []
    for item in normalize_relations(base):
        # manual 与 rejected 都是「用户的既有结论」，任何自动流程都只增不减。
        if item["source"] in RELATION_PINNED_SOURCES:
            pinned.append(item)
            if item["source"] == RELATION_SOURCE_REJECTED:
                vetoed.add((item["target"].casefold(), item["relation"].casefold()))
        elif item["source"] != incoming_source:
            others.append(item)
    # 已否决的边连证据都不能被新扫描污染：同 target+relation 的来料直接丢掉。
    # 只靠「先到先得」不够——normalize_relations 去重时会取较大的 count 并并集 samples，
    # 否决边的命中次数和证据会被新规则边改写，留档就失真了。
    fresh = [
        item for item in normalize_relations(incoming)
        if (item["target"].casefold(), item["relation"].casefold()) not in vetoed
    ]
    # pinned 排在最前：同一 target+relation 冲突时 normalize_relations 保留先到的那条。
    return normalize_relations(pinned + fresh + others)


def create_default_worldbook() -> dict[str, str]:
    """创建默认世界观数据。"""
    return {field: "" for field in WORLD_FIELDS}


def normalize_worldbook(data: Any) -> dict[str, str]:
    """规范化世界观数据。"""
    result = create_default_worldbook()
    if not isinstance(data, dict):
        return result

    for field in WORLD_FIELDS:
        result[field] = normalize_text(data.get(field, ""))
    return result


def create_default_character_card(name: str = "") -> dict[str, Any]:
    """创建默认角色卡。"""
    normalized_name = normalize_text(name)
    return {
        "id": build_character_id(normalized_name),
        "name": normalized_name,
        "aliases": [],
        "name_translation": "",
        "match_keywords": [normalized_name] if normalized_name else [],
        "identity": "",
        "personality": "",
        "speech_style": "",
        "relationship_notes": "",
        "prompt_notes": "",
        "sample_lines": [],
        "enabled": True,
        "is_primary": False,
        "faction": "",
        "relations": [],
        "co_occurrence": {},
        # 头像由扫描按目录约定填；None 表示没有合适图片，前端画首字色块兜底。
        "avatar": None,
        # 扫描时统计的台词句数；0 表示还没扫过。
        "line_count": 0,
    }


def normalize_character_card(data: Any) -> dict[str, Any]:
    """规范化角色卡数据。"""
    seed = data if isinstance(data, dict) else {}
    card = create_default_character_card(normalize_text(seed.get("name", "")))
    card["id"] = normalize_text(seed.get("id", "")) or build_character_id(card["name"])
    card["name"] = normalize_text(seed.get("name", "")) or card["name"]
    card["aliases"] = normalize_text_list(seed.get("aliases", []))
    card["name_translation"] = normalize_text(seed.get("name_translation", ""))
    card["match_keywords"] = normalize_text_list(seed.get("match_keywords", []))
    if card["name"] != "":
        if card["name"].casefold() not in {v.casefold() for v in card["match_keywords"]}:
            card["match_keywords"].insert(0, card["name"])
    card["identity"] = normalize_text(seed.get("identity", ""))
    card["personality"] = normalize_text(seed.get("personality", ""))
    card["speech_style"] = normalize_text(seed.get("speech_style", ""))
    card["relationship_notes"] = normalize_text(seed.get("relationship_notes", ""))
    card["prompt_notes"] = normalize_text(seed.get("prompt_notes", ""))
    card["sample_lines"] = normalize_text_list(seed.get("sample_lines", []))
    card["enabled"] = bool(seed.get("enabled", True))
    card["is_primary"] = bool(seed.get("is_primary", False))
    card["faction"] = normalize_text(seed.get("faction", ""))
    card["relations"] = normalize_relations(seed.get("relations", []))
    card["co_occurrence"] = normalize_co_occurrence(seed.get("co_occurrence", {}))
    card["avatar"] = normalize_avatar(seed.get("avatar"))
    card["line_count"] = normalize_positive_int(seed.get("line_count"))
    return card


def normalize_character_cards(cards: Any) -> list[dict[str, Any]]:
    """规范化角色卡列表。"""
    if not isinstance(cards, list):
        return []

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in cards:
        card = normalize_character_card(raw)
        if card["name"] == "":
            continue
        key = card["id"] or build_character_id(card["name"])
        if key in seen:
            continue
        seen.add(key)
        result.append(card)
    return result


def find_character_card(cards: list[dict[str, Any]], card_id: str) -> dict[str, Any] | None:
    """按 ID 查找角色卡。"""
    target = normalize_text(card_id)
    if target == "":
        return None
    for card in normalize_character_cards(cards):
        if card.get("id") == target:
            return deepcopy(card)
    return None


def merge_character_card(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """以 overlay 覆盖 base，返回新的角色卡。"""
    current = normalize_character_card(base)
    incoming = normalize_character_card(overlay)

    for field in (
        "name",
        "name_translation",
        "identity",
        "personality",
        "speech_style",
        "relationship_notes",
        "prompt_notes",
    ):
        current[field] = incoming.get(field, current[field])

    current["aliases"] = normalize_text_list(current.get("aliases", []) + incoming.get("aliases", []))
    current["match_keywords"] = normalize_text_list(
        current.get("match_keywords", []) + incoming.get("match_keywords", [])
    )
    current["sample_lines"] = normalize_text_list(
        incoming.get("sample_lines", []) or current.get("sample_lines", []),
        unique = True,
    )
    current["enabled"] = bool(incoming.get("enabled", current.get("enabled", True)))
    current["is_primary"] = bool(incoming.get("is_primary", current.get("is_primary", False)))
    current["faction"] = incoming.get("faction", "") or current.get("faction", "")
    current["relations"] = merge_relations(current.get("relations", []), incoming.get("relations", []))
    # 头像来自目录约定，空值不能把已有头像清掉（导入的角色卡通常不带头像）。
    current["avatar"] = incoming.get("avatar") or current.get("avatar")
    # 台词数是扫描统计出来的，导入的卡片里通常没有，同样不能被 0 覆盖。
    current["line_count"] = max(current.get("line_count", 0), incoming.get("line_count", 0))
    current["id"] = incoming.get("id") or current["id"] or build_character_id(current["name"])
    return current


def merge_imported_worldbook(base: Any, incoming: Any) -> dict[str, str]:
    """合并导入的世界观，仅覆盖文件中明确提供的字段。"""
    current = normalize_worldbook(base)
    if not isinstance(incoming, Mapping):
        return current

    for field in WORLD_FIELDS:
        if field in incoming:
            current[field] = normalize_text(incoming.get(field))
    return current


def merge_imported_character_cards(
    base_cards: Any,
    incoming_cards: Any,
) -> list[dict[str, Any]]:
    """合并批量导入角色卡，缺失字段不会清空已有内容。"""
    result = normalize_character_cards(base_cards)
    if not isinstance(incoming_cards, list):
        return result

    id_to_index = {card["id"]: index for index, card in enumerate(result)}
    name_to_index = {
        normalize_text(card.get("name", "")).casefold(): index
        for index, card in enumerate(result)
        if normalize_text(card.get("name", ""))
    }
    list_fields = {"aliases", "match_keywords", "sample_lines"}

    for raw in incoming_cards:
        if not isinstance(raw, Mapping):
            continue
        incoming = normalize_character_card(dict(raw))
        if incoming["name"] == "":
            continue

        index = id_to_index.get(incoming["id"])
        if index is None:
            index = name_to_index.get(incoming["name"].casefold())
        if index is None:
            result.append(incoming)
            index = len(result) - 1
        else:
            merged = dict(result[index])
            for field in CHARACTER_FIELDS:
                if field not in raw or field == "id":
                    continue
                if field == "relations":
                    merged["relations"] = merge_relations(merged.get("relations", []), incoming.get("relations", []))
                elif field == "avatar":
                    merged["avatar"] = incoming.get("avatar") or merged.get("avatar")
                elif field == "line_count":
                    # 导入文件里的台词数多半是旧值或缺省，取大的那个，不让它把扫描结果压小。
                    merged["line_count"] = max(merged.get("line_count", 0), incoming.get("line_count", 0))
                elif field in list_fields:
                    merged[field] = normalize_text_list(
                        merged.get(field, []) + incoming.get(field, [])
                    )
                else:
                    merged[field] = incoming[field]
            result[index] = normalize_character_card(merged)

        card = result[index]
        id_to_index[card["id"]] = index
        name_to_index[card["name"].casefold()] = index

    return result


def parse_workbench_exchange(data: Any) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """解析工作台 JSON；支持完整导出对象或直接的角色卡数组。"""
    if isinstance(data, list):
        cards = [
            dict(card)
            for card in data
            if isinstance(card, Mapping) and normalize_character_card(dict(card))["name"]
        ]
        if cards == []:
            raise ValueError("JSON 中没有有效角色卡")
        return {}, cards
    if not isinstance(data, Mapping):
        raise ValueError("JSON 顶层必须是对象或角色卡数组")

    worldbook: dict[str, str] = {}
    for key in ("worldbook", "worldbook_draft"):
        section = data.get(key)
        if isinstance(section, Mapping) and isinstance(section.get("data"), Mapping):
            section = section.get("data")
        if isinstance(section, Mapping):
            for field in WORLD_FIELDS:
                if field in section:
                    worldbook[field] = normalize_text(section.get(field))

    cards: list[dict[str, Any]] = []
    for key in ("character_cards", "character_drafts"):
        section = data.get(key)
        if isinstance(section, Mapping):
            section = section.get("items")
        if isinstance(section, list):
            cards.extend(
                dict(card)
                for card in section
                if isinstance(card, Mapping) and normalize_character_card(dict(card))["name"]
            )

    if not any(worldbook.values()) and cards == []:
        raise ValueError("JSON 中没有可导入的世界观或角色卡")
    return worldbook, cards


def normalize_analysis_scope(scope: str) -> str:
    """规范化分析范围。"""
    if str(scope).strip().lower() == ANALYSIS_SCOPE_FULL:
        return ANALYSIS_SCOPE_FULL
    return ANALYSIS_SCOPE_CURRENT
