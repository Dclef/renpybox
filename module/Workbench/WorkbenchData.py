from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any


WORLD_FIELDS: tuple[str, ...] = (
    "project_name",
    "genre",
    "setting_summary",
    "era_background",
    "tone_style",
    "narrative_rules",
    "format_rules",
    "spoiler_notes",
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


def normalize_analysis_scope(scope: str) -> str:
    """规范化分析范围。"""
    if str(scope).strip().lower() == ANALYSIS_SCOPE_FULL:
        return ANALYSIS_SCOPE_FULL
    return ANALYSIS_SCOPE_CURRENT
