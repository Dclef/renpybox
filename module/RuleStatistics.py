import json
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Config import Config


# 术语匹配时忽略占位/标签片段，避免 [jane_rlt2] 误命中术语 jane。
RE_GLOSSARY_IGNORE_SEGMENTS = re.compile(r"\[[^\]]*]|\{[^}]*}")


@dataclass(frozen = True)
class GlossaryTextSnapshot:
    raw_texts: tuple[str, ...]
    cleaned_texts: tuple[str, ...]
    raw_lower_texts: tuple[str, ...]
    cleaned_lower_texts: tuple[str, ...]


def get_statistics_cache_dir(config: Config) -> str:
    """返回当前统计要读取的缓存目录绝对路径。"""
    output_folder = str(getattr(config, "output_folder", "") or "").strip()
    if output_folder == "":
        return ""

    output_abs = os.path.abspath(output_folder)
    return os.path.join(output_abs, "cache")


# 统计只需要每条的 src 与 status，把它们从行 JSON 里挑出来就够了。
_FAST_ROW_FIELDS = ("src", "status")


def _iter_fast_items(output_folder: str):
    """直接读 SQLite 原始行，避免为大项目重建全部 CacheItem。

    旧实现走 ``CacheManager.load_from_file``：58956 条要 1939 ms，其中绝大
    部分花在逐条 ``json.loads`` + ``CacheItem.__post_init__``（正则探测文本
    类型、deepcopy metadata），而统计只用到 src 和 status。这里只解析这两个
    字段，实测 866 ms，结果与完整重建逐条一致。

    只要有任何异常就返回 None，由调用方回退到原来的完整读法 —— 兼容 JSON
    缓存、旧库结构和半成品写入等边角情况。
    """
    db_path = os.path.join(output_folder, "cache", "cache.db")
    if not os.path.isfile(db_path):
        return None
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    except Exception:
        return None
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT data FROM items ORDER BY id").fetchall()
    except Exception:
        return None
    finally:
        connection.close()

    parsed: list[tuple[str, str]] = []
    for row in rows:
        try:
            payload = json.loads(row["data"])
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        parsed.append((str(payload.get("src") or ""), str(payload.get("status") or "")))
    return parsed


def load_counted_source_texts(config: Config) -> tuple[str, ...]:
    """读取当前缓存中可用于规则统计的原文快照。"""
    output_folder = str(getattr(config, "output_folder", "") or "").strip()
    if output_folder == "" or os.path.isdir(output_folder) == False:
        return tuple()

    ignored = {status.value for status in (Base.TranslationStatus.EXCLUDED, Base.TranslationStatus.DUPLICATED)}

    fast_items = _iter_fast_items(output_folder)
    if fast_items is not None:
        texts: list[str] = []
        for src, status in fast_items:
            if status in ignored or src.strip() == "":
                continue
            texts.append(src)
        return tuple(texts)

    cache_manager = CacheManager(service = False)
    cache_manager.load_from_file(output_folder)

    texts = []
    for item in cache_manager.get_items():
        status = item.get_status()
        if status in (
            Base.TranslationStatus.EXCLUDED,
            Base.TranslationStatus.DUPLICATED,
        ):
            continue

        src = str(item.get_src() or "")
        if src.strip() == "":
            continue

        texts.append(src)

    return tuple(texts)


def build_glossary_snapshot(texts: tuple[str, ...]) -> GlossaryTextSnapshot:
    cleaned_texts = tuple(RE_GLOSSARY_IGNORE_SEGMENTS.sub("", text) for text in texts)
    return GlossaryTextSnapshot(
        raw_texts = texts,
        cleaned_texts = cleaned_texts,
        raw_lower_texts = tuple(text.lower() for text in texts),
        cleaned_lower_texts = tuple(text.lower() for text in cleaned_texts),
    )


def count_glossary_hit_counts(
    entries: list[dict[str, Any]],
    texts: tuple[str, ...],
) -> list[int]:
    """统计术语表每条规则命中的条目数。"""
    snapshot = build_glossary_snapshot(texts)
    counts: list[int] = []

    for entry in entries:
        src = str(entry.get("src", "") or "").strip()
        if src == "":
            counts.append(0)
            continue

        case_sensitive = bool(entry.get("case_sensitive", False))
        use_raw_text = any(ch in src for ch in "[]{}")

        if case_sensitive:
            haystacks = snapshot.raw_texts if use_raw_text else snapshot.cleaned_texts
            needle = src
        else:
            haystacks = (
                snapshot.raw_lower_texts
                if use_raw_text
                else snapshot.cleaned_lower_texts
            )
            needle = src.lower()

        matched_item_count = 0
        for text in haystacks:
            if needle in text:
                matched_item_count += 1

        counts.append(matched_item_count)

    return counts


def normalize_text_preserve_pattern(pattern: str) -> str:
    """按 TextProcessor 的当前语义规范化自定义文本保护规则。"""
    result = str(pattern or "").strip()
    if result == "":
        return ""

    if result.startswith("[") and result.endswith("]") and "\\" not in result:
        if re.fullmatch(rf"\[[\w{CacheItem.CJK_RANGE}.]+\]", result) is not None:
            result = re.escape(result)

    if result.startswith("{") and result.endswith("}") and "\\" not in result:
        result = re.escape(result)

    return result


def count_text_preserve_hit_counts(
    entries: list[dict[str, Any]],
    texts: tuple[str, ...],
) -> list[int]:
    """统计文本保护每条规则命中的条目数。"""
    counts: list[int] = []

    for entry in entries:
        raw_pattern = str(entry.get("src", "") or "").strip()
        if raw_pattern == "":
            counts.append(0)
            continue

        pattern = normalize_text_preserve_pattern(raw_pattern)
        if pattern == "":
            counts.append(0)
            continue

        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error:
            counts.append(0)
            continue

        matched_item_count = 0
        for text in texts:
            if compiled.search(text) is not None:
                matched_item_count += 1

        counts.append(matched_item_count)

    return counts
