from __future__ import annotations

import hashlib
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
)

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
                if field in list_fields:
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
