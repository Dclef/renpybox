"""只读统计可润色 / 可校对的条目数。

润色与校对都是「只处理已有译文」的任务，开始前先报数能省掉一轮试错：用户
反馈（2026-10-18）「这种润色能不能直接看需要润色的条数，然后直接润色需要
润色的条数，这样节省token」。Agent 侧同样需要这个数字，避免先瞎读一批才
发现没有可润色的条目。

计数优先直读 SQLite（58956 条约 0.5s），拿不到再退回内存遍历（2.3s）。
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

from base.Base import Base
from module.Cache.CacheManager import CacheManager


def count_quality_candidates(output_folder: str, manager: CacheManager | None = None) -> dict[str, int]:
    """返回 ``{"polish": n, "proofread": n, "total": n}``。

    ``output_folder`` 是翻译输出目录（缓存位于其下的 ``cache/``）。SQLite
    直读失败或不是 SQLite 缓存时，用传入的 ``manager`` 兜底；两者都拿不到
    就返回全 0，调用方无需区分「没有条目」和「读不到缓存」。
    """

    # 绑定工程文件（.rbox）时缓存直接在 .rbox 里；否则是 <输出>/cache/cache.db。
    db_path = CacheManager.db_path_for(output_folder)
    counts = _count_from_sqlite(db_path)
    if counts is not None:
        return counts
    if manager is None:
        return {"polish": 0, "proofread": 0, "total": 0}
    return _count_from_manager(manager)


def _count_from_sqlite(db_path: str) -> dict[str, int] | None:
    if not os.path.isfile(db_path):
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri = True)
        try:
            total = int(conn.execute("SELECT COUNT(*) FROM items").fetchone()[0])
            polish = _count_statuses(conn, Base.ITEM_POLISHABLE_STATUSES)
            proofread = _count_statuses(conn, Base.ITEM_PROOFREADABLE_STATUSES)
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - 缓存结构异常时退回内存口径
        return None
    return {"polish": polish, "proofread": proofread, "total": total}


def _count_statuses(conn: sqlite3.Connection, statuses: Any) -> int:
    """按状态集合统计「有译文」的条目数，占位符随集合大小生成。"""

    values = [str(status) for status in sorted(statuses, key = str)]
    if not values:
        return 0
    placeholders = ", ".join("?" for _ in values)
    sql = (
        "SELECT COUNT(*) FROM items "
        f"WHERE json_extract(data,'$.status') IN ({placeholders}) "
        "AND TRIM(COALESCE(json_extract(data,'$.dst'),'')) <> ''"
    )
    row = conn.execute(sql, values).fetchone()
    return int(row[0]) if row is not None else 0


def _count_from_manager(manager: CacheManager) -> dict[str, int]:
    counts = {"polish": 0, "proofread": 0, "total": 0}
    for item in manager.get_items():
        counts["total"] += 1
        status = item.get_status()
        if str(item.get_dst() or "").strip() == "":
            continue
        if Base.is_item_polishable(status):
            counts["polish"] += 1
        if Base.is_item_proofreadable(status):
            counts["proofread"] += 1
    return counts
