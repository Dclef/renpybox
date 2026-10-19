"""可润色/可校对条数统计的口径测试。

用户诉求（2026-10-18）：「润色能不能直接看需要润色的条数，然后直接润色需要
润色的条数，这样节省token」。这里锁住三条：SQL 口径与内存口径一致、空目录
不会抛、已有译文的 POLISHED 条目算可校对但不算可润色。
"""

from __future__ import annotations

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheProject import CacheProject
from module.Cache.QualityCandidates import count_quality_candidates


def _item(status, *, dst: str = "", src: str = "source") -> CacheItem:
    return CacheItem(src = src, dst = dst, status = status)


def _save(tmp_path, items: list[CacheItem], *, sqlite: bool = True) -> str:
    manager = CacheManager(service = False)
    manager.cache_use_sqlite = sqlite
    manager.save_to_file(
        CacheProject(id = "quality-candidates"),
        items,
        str(tmp_path),
        strict = True,
    )
    return str(tmp_path)


def _expected(items: list[CacheItem]) -> dict[str, int]:
    counts = {"polish": 0, "proofread": 0, "total": 0}
    for item in items:
        counts["total"] += 1
        if not str(item.get_dst() or "").strip():
            continue
        if Base.is_item_polishable(item.get_status()):
            counts["polish"] += 1
        if Base.is_item_proofreadable(item.get_status()):
            counts["proofread"] += 1
    return counts


def test_counts_match_status_rules(tmp_path) -> None:
    items = [
        _item(Base.TranslationStatus.TRANSLATED, dst = "译文1"),
        _item(Base.TranslationStatus.POLISHED, dst = "译文2"),
        _item(Base.TranslationStatus.UNTRANSLATED),
        _item(Base.TranslationStatus.TRANSLATED, dst = "   "),
        _item(Base.TranslationStatus.EXCLUDED, dst = "不译"),
    ]
    output = _save(tmp_path, items)

    counts = count_quality_candidates(output)

    assert counts == _expected(items)
    # 只有一条真正待润色（POLISHED 已润过、空译文不算）。
    assert counts["polish"] == 1
    # 可校对同时覆盖 TRANSLATED 与 POLISHED，两条都有译文。
    assert counts["proofread"] == 2


def test_missing_output_returns_zero() -> None:
    counts = count_quality_candidates("D:/definitely-not-a-real-output-dir")

    assert counts == {"polish": 0, "proofread": 0, "total": 0}


def test_manager_fallback_is_used_without_sqlite(tmp_path) -> None:
    """JSON 缓存没有 cache.db 时，用传入的 manager 兜底统计。"""

    items = [
        _item(Base.TranslationStatus.TRANSLATED, dst = "译文1"),
        _item(Base.TranslationStatus.UNTRANSLATED),
    ]
    _save(tmp_path, items, sqlite = False)

    manager = CacheManager(service = False)
    manager.cache_use_sqlite = False
    manager.load_from_file(str(tmp_path), strict = True)
    assert not (tmp_path / "cache" / CacheManager.CACHE_DB_NAME).is_file()

    counts = count_quality_candidates(str(tmp_path), manager)

    assert counts == {"polish": 1, "proofread": 1, "total": 2}
