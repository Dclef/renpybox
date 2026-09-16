import json
import hashlib
import os
import sqlite3
import threading
import time
from collections.abc import Iterable, Iterator
from typing import Any

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheProject import CacheProject


class CacheDB(Base):
    """SQLite cache store (items/project only)"""

    ROW_YIELD_INTERVAL = 512

    def __init__(self, db_path: str) -> None:
        super().__init__()
        self.db_path = db_path
        self.lock = threading.Lock()

    def _open(self) -> sqlite3.Connection:
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok = True)
        conn = sqlite3.connect(self.db_path, check_same_thread = False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        self._ensure_schema(conn)
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_meta_key ON meta(key)")
        conn.commit()

    @staticmethod
    def _digest_json(data: dict) -> str:
        return json.dumps(
            data,
            ensure_ascii = False,
            sort_keys = True,
            separators = (",", ":"),
        )

    @staticmethod
    def _row_json(data: dict) -> str:
        return json.dumps(data, ensure_ascii = False, separators = (",", ":"))

    @classmethod
    def _iter_item_rows(
        cls,
        items: Iterable[CacheItem],
        digest: Any,
    ) -> Iterator[tuple[str]]:
        """边生成 SQLite 行边计算摘要，避免大项目保存时复制整批条目。"""
        digest.update(b"[")
        first = True
        for index, item in enumerate(items, 1):
            if index % cls.ROW_YIELD_INTERVAL == 0:
                time.sleep(0)
            data = item.asdict()
            if first:
                first = False
            else:
                digest.update(b",")
            digest.update(cls._digest_json(data).encode("utf-8"))
            yield (cls._row_json(data),)
        digest.update(b"]")

    @classmethod
    def items_digest(cls, items: Iterable[CacheItem]) -> str:
        """计算条目集合摘要，用于区分不同翻译代次。"""
        digest = hashlib.sha256()
        for _row in cls._iter_item_rows(items, digest):
            pass
        return digest.hexdigest()

    def get_items_digest(self) -> str | None:
        """读取 SQLite 最近一次条目事务摘要；旧库没有时返回 None。"""
        if not os.path.isfile(self.db_path):
            return None
        with self.lock:
            conn = self._open()
            try:
                row = conn.execute(
                    "SELECT value FROM meta WHERE key = ?",
                    ("items_digest",),
                ).fetchone()
                return str(row["value"]) if row is not None else None
            finally:
                conn.close()

    def get_project(self) -> CacheProject | None:
        if not os.path.isfile(self.db_path):
            return None

        with self.lock:
            conn = self._open()
            try:
                row = conn.execute(
                    "SELECT value FROM meta WHERE key = ?",
                    ("project",),
                ).fetchone()
                if row is None:
                    return None
                return CacheProject.from_dict(json.loads(row["value"]))
            finally:
                conn.close()

    def set_project(self, project: CacheProject) -> None:
        with self.lock:
            conn = self._open()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    ("project", json.dumps(project.asdict(), ensure_ascii = False)),
                )
                conn.commit()
            finally:
                conn.close()

    def get_items(self) -> list[CacheItem]:
        if not os.path.isfile(self.db_path):
            return []

        with self.lock:
            conn = self._open()
            try:
                rows = conn.execute("SELECT data FROM items ORDER BY id").fetchall()
                return [CacheItem.from_dict(json.loads(row["data"])) for row in rows]
            finally:
                conn.close()

    def set_items(self, items: Iterable[CacheItem]) -> None:
        with self.lock:
            conn = self._open()
            try:
                digest = hashlib.sha256()
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM items")
                conn.executemany(
                    "INSERT INTO items (data) VALUES (?)",
                    self._iter_item_rows(items, digest),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    ("items_digest", digest.hexdigest()),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def set_translation_cache(
        self,
        project: CacheProject,
        items: Iterable[CacheItem],
    ) -> None:
        """在同一事务中保存项目记录和全部翻译条目。"""
        project_json = json.dumps(project.asdict(), ensure_ascii = False)

        with self.lock:
            conn = self._open()
            try:
                digest = hashlib.sha256()
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM items")
                conn.executemany(
                    "INSERT INTO items (data) VALUES (?)",
                    self._iter_item_rows(items, digest),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    ("project", project_json),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    ("items_digest", digest.hexdigest()),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def reset_translation_run(
        self,
        project: CacheProject,
        items: Iterable[CacheItem],
        snapshot: Any = None,
        progress: dict[str, Any] | None = None,
    ) -> CacheProject:
        """Atomically replace run data without deleting project-level extras."""
        reset_project = CacheProject.from_dict(project.asdict())
        reset_project.reset_translation_run(snapshot = snapshot, progress = progress)
        project_json = json.dumps(reset_project.asdict(), ensure_ascii = False)

        with self.lock:
            conn = self._open()
            try:
                digest = hashlib.sha256()
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM items")
                conn.executemany(
                    "INSERT INTO items (data) VALUES (?)",
                    self._iter_item_rows(items, digest),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    ("project", project_json),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    ("items_digest", digest.hexdigest()),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        return reset_project
