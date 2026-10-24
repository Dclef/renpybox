"""剧情蓝图用的译文索引：把应用翻译缓存读成「源文件 + 原文 → 译文」的按序队列。

缓存条目里的 `file_path` 是相对 `game/` 的源脚本路径（不是 tl 文件），`src` 是去掉
引号与说话人后的对白原文——正好能和蓝图扫描出来的 say 行对上。同一个文件里同一句
原文可能出现多次，所以按出现顺序排队取用，避免重复句把「已译行数」算多。

来源有两个：sqlite 缓存（`cache/cache.db`，直接只读查询，比逐条建对象快一倍多）
与旧的 `items.json` 文件缓存。同一份缓存按 mtime + size 做进程内缓存，蓝图页面
每点一个 label 都来问一次，不会重复解析。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from module.Cache.CacheManager import CacheManager
from module.Renpy.ProjectPaths import translation_output_candidates

_LOCK = threading.Lock()
_MEMO: dict[str, tuple[tuple[float, int], "TranslationIndex"]] = {}


class TranslationIndex:
    """(源文件, 原文) → 译文队列；`take()` 按顺序取一条，取完即消耗。

    `_queues` 是不可变的共享表，消耗进度记在每个实例自己的 `_counters` 里，
    所以同一份缓存可以从 `from_cache()` 反复 `fork()` 出互不干扰的索引。
    """

    def __init__(
        self,
        queues: dict[tuple[str, str], tuple[str, ...]] | None = None,
        counters: dict[tuple[str, str], int] | None = None,
    ) -> None:
        self._queues = queues or {}
        self._counters = counters if counters is not None else {}

    @classmethod
    def empty(cls) -> "TranslationIndex":
        return cls({})

    @classmethod
    def from_cache(cls, config: Any) -> tuple["TranslationIndex", str]:
        """读当前工程的翻译缓存；读不到就返回空索引（蓝图只用 tl 数据兜底）。"""
        for candidate in translation_output_candidates(config):
            path = Path(candidate)
            stamp = _stamp(path)
            key = str(path)
            with _LOCK:
                cached = _MEMO.get(key)
                if cached is not None and cached[0] == stamp:
                    return cached[1].fork(), key
            index = _load(path)
            with _LOCK:
                _MEMO[key] = (stamp, index)
            if len(index) > 0:
                return index.fork(), key
        return cls.empty(), ""

    def fork(self) -> "TranslationIndex":
        """复制一份「未消耗」的索引；读缓存的人各拿一份，互不影响。"""
        return TranslationIndex(self._queues, {})

    def take(self, relative: str, src: str) -> str | None:
        key = (relative, src)
        queue = self._queues.get(key)
        if not queue:
            return None
        position = self._counters.get(key, 0)
        if position >= len(queue):
            return None
        self._counters[key] = position + 1
        return queue[position]

    def peek(self, relative: str, src: str) -> str | None:
        queue = self._queues.get((relative, src))
        if not queue:
            return None
        position = self._counters.get((relative, src), 0)
        return queue[position] if position < len(queue) else None

    def __len__(self) -> int:
        return sum(len(queue) for queue in self._queues.values())


def _db_path(candidate: Path) -> Path | None:
    for path in (candidate / "cache" / "cache.db", candidate / "cache.db"):
        if path.is_file():
            return path
    return None


def _stamp(candidate: Path) -> tuple[float, int]:
    db = _db_path(candidate)
    if db is not None:
        try:
            stat = db.stat()
            return (stat.st_mtime, stat.st_size)
        except OSError:
            pass
    for name in ("items.json", "project.json"):
        try:
            stat = (candidate / name).stat()
        except OSError:
            continue
        return (stat.st_mtime, stat.st_size)
    try:
        stat = candidate.stat()
    except OSError:
        return (0.0, 0)
    return (stat.st_mtime, stat.st_size)


def _load(candidate: Path) -> "TranslationIndex":
    db = _db_path(candidate)
    if db is not None:
        index = _load_sqlite(db)
        if len(index) > 0:
            return index
    return _load_manager(candidate)


def _load_sqlite(db: Path) -> "TranslationIndex":
    queues: dict[tuple[str, str], list[str]] = {}
    try:
        connection = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri = True)
    except sqlite3.Error:
        return TranslationIndex.empty()
    try:
        cursor = connection.execute("select data from items")
        for (payload,) in cursor:
            try:
                item = json.loads(payload)
            except (TypeError, ValueError):
                continue
            _collect(queues, item)
    except sqlite3.Error:
        return TranslationIndex.empty()
    finally:
        connection.close()
    return TranslationIndex({key: tuple(value) for key, value in queues.items()})


def _load_manager(candidate: Path) -> "TranslationIndex":
    manager = CacheManager(service = False)
    try:
        manager.load_from_file(str(candidate), strict = True)
    except Exception:  # noqa: BLE001 - 缓存损坏不能拖垮蓝图，退回 tl 口径
        return TranslationIndex.empty()
    queues: dict[tuple[str, str], list[str]] = {}
    for item in manager.get_items():
        _collect(
            queues,
            {
                "src": item.get_src(),
                "dst": item.get_dst(),
                "file_path": item.get_file_path(),
            },
        )
    return TranslationIndex({key: tuple(value) for key, value in queues.items()})


def _collect(queues: dict[tuple[str, str], list[str]], item: dict) -> None:
    src = str(item.get("src") or "").strip()
    dst = str(item.get("dst") or "").strip()
    relative = relative_source(item.get("file_path"))
    if not src or not dst or dst == src or not relative:
        return
    queues.setdefault((relative, src), []).append(dst)


def relative_source(value: Any) -> str:
    """把缓存里的源文件路径规范成相对 game/ 的形式（正斜杠）。"""
    path = str(value or "").replace("\\", "/").strip()
    while path.startswith("./"):
        path = path[2:]
    if path.casefold().startswith("game/"):
        path = path[len("game/") :]
    return path
