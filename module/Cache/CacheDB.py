import json
import os
import sqlite3
import threading

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
        os.makedirs(os.path.dirname(self.db_path), exist_ok = True)
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
                conn.commit()
            finally:
                conn.close()
