import os
import sqlite3

import pytest

from module.Cache.CacheDB import CacheDB
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheProject import CacheProject


def _journal_mode(path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()


def test_cache_db_defaults_to_wal_for_live_caches(tmp_path) -> None:
    path = tmp_path / "cache.db"
    db = CacheDB(str(path))

    db.set_translation_cache(CacheProject(id = "live"), [CacheItem(src = "a")])

    assert db.journal_mode == "WAL"
    assert _journal_mode(path) == "wal"
    assert [item.get_src() for item in db.get_items()] == ["a"]


def test_cache_db_delete_mode_leaves_no_sidecars(tmp_path) -> None:
    path = tmp_path / "single.db"
    db = CacheDB(str(path), journal_mode = "delete")

    db.set_translation_cache(CacheProject(id = "single"), [CacheItem(src = "a")])
    db.set_items([CacheItem(src = "b")])

    assert db.journal_mode == "DELETE"
    assert _journal_mode(path) == "delete"
    assert [item.get_src() for item in db.get_items()] == ["b"]
    assert sorted(os.listdir(tmp_path)) == ["single.db"]


@pytest.mark.parametrize("mode", ["bogus", "WAL; DROP TABLE items", "", None, "MEMORY"])
def test_cache_db_rejects_unsupported_journal_modes(tmp_path, mode) -> None:
    with pytest.raises(ValueError, match = "journal mode"):
        CacheDB(str(tmp_path / "cache.db"), journal_mode = mode)
    assert not (tmp_path / "cache.db").exists()
