import json
import hashlib
import os
import sqlite3
import threading
from typing import Any

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheProject import CacheProject


class CacheDB(Base):
    """SQLite cache store (items/project only)"""

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
    def items_digest(items: list[CacheItem]) -> str:
        """计算条目集合摘要，用于区分不同翻译代次。"""
        payload = [item.asdict() for item in items]
        encoded = json.dumps(
            payload,
            ensure_ascii = False,
            sort_keys = True,
            separators = (",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

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

    def set_items(self, items: list[CacheItem]) -> None:
        with self.lock:
            conn = self._open()
            try:
                conn.execute("DELETE FROM items")
                for i, item in enumerate(items):
                    data_json = json.dumps(item.asdict(), ensure_ascii = False, separators = (",", ":"))
                    conn.execute("INSERT INTO items (data) VALUES (?)", (data_json,))
                    if i % 200 == 0:
                        conn.commit()
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    ("items_digest", self.items_digest(items)),
                )
                conn.commit()
            finally:
                conn.close()

    def set_translation_cache(
        self,
        project: CacheProject,
        items: list[CacheItem],
    ) -> None:
        """在同一事务中保存项目记录和全部翻译条目。"""
        project_json = json.dumps(project.asdict(), ensure_ascii = False)
        item_rows = [
            (json.dumps(item.asdict(), ensure_ascii = False, separators = (",", ":")),)
            for item in items
        ]

        with self.lock:
            conn = self._open()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM items")
                conn.executemany("INSERT INTO items (data) VALUES (?)", item_rows)
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    ("project", project_json),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    ("items_digest", self.items_digest(items)),
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
        items: list[CacheItem],
        snapshot: Any = None,
        progress: dict[str, Any] | None = None,
    ) -> CacheProject:
        """Atomically replace run data without deleting project-level extras."""
        reset_project = CacheProject.from_dict(project.asdict())
        reset_project.reset_translation_run(snapshot = snapshot, progress = progress)
        project_json = json.dumps(reset_project.asdict(), ensure_ascii = False)
        item_rows = [
            (json.dumps(item.asdict(), ensure_ascii = False, separators = (",", ":")),)
            for item in items
        ]

        with self.lock:
            conn = self._open()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM items")
                conn.executemany("INSERT INTO items (data) VALUES (?)", item_rows)
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    ("project", project_json),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    ("items_digest", self.items_digest(items)),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        return reset_project
