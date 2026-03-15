import os
import re
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


def load_counted_source_texts(config: Config) -> tuple[str, ...]:
    """读取当前缓存中可用于规则统计的原文快照。"""
    output_folder = str(getattr(config, "output_folder", "") or "").strip()
    if output_folder == "" or os.path.isdir(output_folder) == False:
        return tuple()

    cache_manager = CacheManager(service = False)
    cache_manager.load_from_file(output_folder)

    texts: list[str] = []
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
