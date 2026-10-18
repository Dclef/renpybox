"""一条龙的术语库 / 禁翻库预处理。

解包、抽取、翻译之外，用户还希望一条龙顺手把词库准备好（2026-10-18 反馈：
「一条龙应该也把自动扫描术语库的自动去重和移除可能不是术语的词语，然后禁翻
库也要一起弄啊」）。这里把三件事做成纯函数 + 一个薄编排层：

1. 扫描角色名 -> 术语候选（复用 LexiconOps 的扫描与合并规则）；
2. 去重（同 src 大小写不敏感合并，保留人工词条）；
3. 过滤掉明显不是术语的条目（动词短语、整句、占位符、纯符号……）；
4. 扫出 [variable] 写进禁翻表。

本模块不依赖 api，也不直接写配置：调用方拿到计划后自己落盘，这样 Agent 工具
和 HTTP 路由可以共用同一份规则，不会两边分叉。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from module.Tool import LexiconOps


# 明显不是术语的条目：动词短语、界面按钮、整句、代词。
# 这些在英文 Ren'Py 工程里极常见（Buy / Calculate Progress / Everyone），
# 以前全都进了候选表，用户看到 200 多条垃圾候选（2026-10-18 反馈）。
NOT_TERM_PHRASES = frozenset(
    {
        "buy", "sell", "back", "next", "cancel", "confirm", "yes", "no", "ok",
        "continue", "start", "load", "save", "quit", "exit", "return", "close",
        "open", "settings", "options", "preferences", "gallery", "extras",
        "main menu", "load game", "new game", "save game", "quick save",
        "quick load", "auto", "skip", "history", "help", "about", "credits",
        "calculate progress", "progress", "day", "night", "morning", "evening",
        "everyone", "someone", "anyone", "nobody", "people", "crowd", "voice",
        "unknown", "narrator", "you", "me", "us", "them", "he", "she", "they",
        "him", "her", "his", "hers", "their", "theirs", "it", "its",
        "soldier", "soldiers", "villager", "villagers", "guard", "guards",
        "girl", "girls", "woman", "women", "man", "men", "boy", "boys",
        "master", "mistress", "sir", "madam", "miss", "mister",
    }
)

# 这些后缀说明是动作/进度而不是专有名词。
NOT_TERM_SUFFIXES = ("progress", "loading", "complete", "completed", "failed")


@dataclass
class GlossaryPrepResult:
    """术语库预处理的产物与统计。"""

    entries: list[dict[str, Any]] = field(default_factory=list)
    added: int = 0
    removed_duplicate: int = 0
    removed_not_term: int = 0
    scanned: int = 0
    kept_existing: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed_duplicate or self.removed_not_term)

    def summary(self) -> str:
        return (
            f"术语库：扫描 {self.scanned} 个名字，"
            f"新增 {self.added} 条，"
            f"去重 {self.removed_duplicate} 条，"
            f"过滤非术语 {self.removed_not_term} 条"
        )


def looks_like_term(text: str) -> bool:
    """判断一个自动候选值不值得进术语表。

    刻意保守：只在明确是垃圾时返回 False，宁可漏过滤也不要误删用户想保留的
    专有名词。人工词条永远不会走到这里。
    """
    value = LexiconOps.clean_text_for_classify(str(text or ""))
    if not value:
        return False

    lowered = value.casefold().strip()
    if lowered in NOT_TERM_PHRASES:
        return False
    if any(lowered.endswith(suffix) for suffix in NOT_TERM_SUFFIXES):
        return False

    # 整句：带句末标点的不是术语
    if any(ch in value for ch in ".?!。？！"):
        return False
    # 纯符号或纯数字
    if not any(ch.isalpha() for ch in value):
        return False

    words = value.split()
    if not words or len(words) > 4:
        return False
    # 全小写的多词短语基本是普通搭配，专有名词通常有首字母大写
    if len(words) > 1 and value == lowered:
        return False

    return LexiconOps.is_probable_name(value)


def filter_not_terms(entries: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """去掉自动生成的、明显不是术语的候选；人工词条原样保留。"""
    kept: list[dict[str, Any]] = []
    removed = 0
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        item = dict(entry)
        automatic = bool(item.get("candidate")) and not bool(item.get("candidate_confirmed"))
        if automatic and not looks_like_term(str(item.get("src", "") or "")):
            removed += 1
            continue
        kept.append(item)
    return kept, removed


def dedupe_entries(entries: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """按规范化 src 去重，保留人工词条优先；返回 (结果, 去重条数)。"""
    rows = [dict(item) for item in entries if isinstance(item, Mapping)]
    manual = [item for item in rows if not item.get("candidate")]
    automatic = [item for item in rows if item.get("candidate")]

    merged_manual = LexiconOps.dedupe_glossary_entries(manual)
    merged_auto = LexiconOps.dedupe_glossary_entries(automatic)

    manual_keys = {
        LexiconOps.normalize_glossary_src(str(item.get("src", "") or ""))
        for item in merged_manual
    }
    survivors = [
        item
        for item in merged_auto
        if LexiconOps.normalize_glossary_src(str(item.get("src", "") or "")) not in manual_keys
    ]
    total = len(rows)
    kept = len(merged_manual) + len(survivors)
    return merged_manual + survivors, max(0, total - kept)


def prepare_glossary(
    config: Any,
    existing_rows: Sequence[Mapping[str, Any]],
    *,
    scan_names: Callable[[], set[str]] | None = None,
    enabled: bool = True,
) -> GlossaryPrepResult:
    """扫描角色名并更新术语候选，返回可直接落盘的行。

    ``existing_rows`` 是当前术语表全量行（含人工词条与旧候选）。返回的
    ``entries`` 只有「候选」部分，人工词条由调用方保持不动。
    """
    if not enabled:
        return GlossaryPrepResult()

    names: set[str] = set()
    if scan_names is not None:
        try:
            names = set(scan_names() or ())
        except Exception:
            names = set()

    kept_existing = [dict(row) for row in existing_rows if isinstance(row, Mapping)]

    manual = [row for row in kept_existing if not row.get("candidate")]
    existing_auto = [row for row in kept_existing if row.get("candidate")]

    # 用扫描结果重建自动候选，同时保留用户已确认过的候选。
    confirmed_auto = [row for row in existing_auto if row.get("candidate_confirmed")]
    # 注意返回值顺序是 (保留的手工词条, 新候选, 被移除的自动条目数)。
    _kept_manual, generated, _removed_auto = LexiconOps.build_character_scan_entries(
        manual, names
    )

    pool: list[dict[str, Any]] = []
    pool.extend(confirmed_auto)
    for entry in generated:
        pool.append(
            {
                "src": entry.get("src", ""),
                "dst": entry.get("dst", ""),
                "type": entry.get("type", ""),
                "info": entry.get("info", ""),
                "comment": entry.get("comment", ""),
                "case_sensitive": False,
                "candidate": True,
                "candidate_confirmed": False,
                "enabled": True,
                "regex": False,
            }
        )

    filtered, removed_not_term = filter_not_terms(pool)
    deduped, removed_duplicate = dedupe_entries(filtered)

    before = {
        LexiconOps.normalize_glossary_src(str(row.get("src", "") or ""))
        for row in existing_auto
    }
    added = sum(
        1
        for item in deduped
        if LexiconOps.normalize_glossary_src(str(item.get("src", "") or "")) not in before
    )

    return GlossaryPrepResult(
        entries=deduped,
        added=added,
        removed_duplicate=removed_duplicate,
        removed_not_term=removed_not_term,
        scanned=len(names),
        kept_existing=len(manual),
    )


@dataclass
class PreservePrepResult:
    """禁翻库预处理的产物。"""

    entries: list[dict[str, Any]] = field(default_factory=list)
    added: int = 0
    enabled: bool = False
    scanned: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.added)

    def summary(self) -> str:
        return f"禁翻库：扫描 {self.scanned} 个变量引用，新增 {self.added} 条"


def prepare_preserve(
    config: Any,
    existing_entries: Sequence[Mapping[str, Any]],
    *,
    cancel_check: Callable[[], bool] | None = None,
    enabled: bool = True,
) -> PreservePrepResult:
    """扫描 [variable] 并合并进禁翻表；已有条目不动，只补新增。"""
    if not enabled:
        return PreservePrepResult()

    try:
        result = LexiconOps.scan_preserve_variables(config, cancel_check)
    except Exception:
        return PreservePrepResult()

    scanned_entries = list(result.get("entries", []) or [])
    existing = [
        LexiconOps.normalize_preserve_src(str(item.get("src", "") or ""))
        for item in existing_entries
        if isinstance(item, Mapping)
    ]
    seen = {key for key in existing if key}

    merged: list[dict[str, Any]] = [
        {"src": str(item.get("src", "") or ""), "comment": str(item.get("comment", item.get("info", "")) or "")}
        for item in existing_entries
        if isinstance(item, Mapping) and str(item.get("src", "") or "").strip()
    ]
    added = 0
    for entry in scanned_entries:
        src = str(entry.get("src", "") or "").strip()
        if not src:
            continue
        key = LexiconOps.normalize_preserve_src(src)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append({"src": src, "comment": ""})
        added += 1

    return PreservePrepResult(
        entries=merged,
        added=added,
        enabled=bool(result.get("enabled", True)) or bool(merged),
        scanned=len(scanned_entries),
    )


__all__ = [
    "GlossaryPrepResult",
    "NOT_TERM_PHRASES",
    "NOT_TERM_SUFFIXES",
    "PreservePrepResult",
    "dedupe_entries",
    "filter_not_terms",
    "looks_like_term",
    "prepare_glossary",
    "prepare_preserve",
]
