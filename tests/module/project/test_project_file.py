import os
import sqlite3
from pathlib import Path

import pytest

from base.Base import Base
from module.Cache.CacheDB import CacheDB
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheProject import CacheProject
from module.Project import ProjectFile as project_file_module
from module.Project.ProjectFile import ProjectFile, ProjectFileError


def _project() -> CacheProject:
    return CacheProject(
        id = "demo-project",
        status = Base.TranslationStatus.TRANSLATING,
        extras = {
            "progress": {"line": 1, "total_line": 2},
            "custom_partition": {"note": "保留"},
        },
    )


def _items() -> list[CacheItem]:
    return [
        CacheItem(
            src = "Hello",
            dst = "你好",
            name_src = "Alice",
            name_dst = "爱丽丝",
            extra_field = {"context": "intro", "nested": [1, 2]},
            tag = "t1",
            row = 3,
            file_type = CacheItem.FileType.RENPY,
            file_path = "game/script.rpy",
            text_type = CacheItem.TextType.RENPY,
            status = Base.TranslationStatus.TRANSLATED,
            metadata = {"note": "kept"},
        ),
        CacheItem(src = "Bye", file_path = "game/script.rpy", row = 4),
    ]


def _settings() -> dict:
    return {
        "target_language": "ZH",
        "glossary": [{"src": "Alice", "dst": "爱丽丝"}],
        "batch_size": 8,
    }


def _export(path: Path, items: list[CacheItem] | None = None, **kwargs):
    return ProjectFile.export(
        path,
        kwargs.pop("project", _project()),
        _items() if items is None else items,
        project_root = kwargs.pop("project_root", "E:/Games/Demo"),
        settings = kwargs.pop("settings", _settings()),
        app_version = kwargs.pop("app_version", "1.2.3"),
    )


def _tamper(path: Path, *statements: tuple[str, tuple]) -> None:
    conn = sqlite3.connect(str(path))
    try:
        for sql, params in statements:
            conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _assert_only(directory: Path, *names: str) -> None:
    assert sorted(os.listdir(directory)) == sorted(names)


def test_export_load_roundtrip_preserves_project_items_settings_and_digest(tmp_path) -> None:
    path = tmp_path / "demo.rbox"
    project = _project()
    items = _items()

    info = _export(path, items, project = project)
    snapshot = ProjectFile.load(path)

    assert info.path == str(path)
    assert info.schema_version == ProjectFile.SCHEMA_VERSION
    assert info.app_version == "1.2.3"
    assert info.project_root == "E:/Games/Demo"
    assert info.item_count == 2
    assert info.items_digest == CacheDB.items_digest(items)
    assert info.created_at == info.updated_at
    assert ProjectFile.inspect(path) == info
    assert snapshot.info == info
    assert snapshot.project.asdict() == project.asdict()
    assert snapshot.project.get_extras()["custom_partition"] == {"note": "保留"}
    assert [item.asdict() for item in snapshot.items] == [item.asdict() for item in items]
    assert snapshot.settings == _settings()
    _assert_only(tmp_path, "demo.rbox")


def test_export_writes_single_delete_mode_sqlite_with_namespaced_meta(tmp_path) -> None:
    path = tmp_path / "demo.rbox"
    _export(path)

    header = path.read_bytes()[:100]
    assert header.startswith(b"SQLite format 3\x00")
    assert header[18] == 1 and header[19] == 1

    conn = sqlite3.connect(str(path))
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert conn.execute("PRAGMA application_id").fetchone()[0] == ProjectFile.APPLICATION_ID
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        settings_keys = [row[0] for row in conn.execute("SELECT key FROM settings ORDER BY key")]
    finally:
        conn.close()

    assert meta["rbox.format"] == "renpybox.project"
    assert meta["rbox.schema_version"] == "1"
    assert meta["rbox.item_count"] == "2"
    assert meta["rbox.items_digest"] == meta["items_digest"]
    assert {"project", "rbox.app_version", "rbox.created_at", "rbox.updated_at", "rbox.project_root"} <= set(meta)
    assert settings_keys == ["batch_size", "glossary", "target_language"]
    _assert_only(tmp_path, "demo.rbox")


def test_rbox_is_readable_by_cache_db_in_delete_mode_without_sidecars(tmp_path) -> None:
    path = tmp_path / "demo.rbox"
    items = _items()
    _export(path, items)

    store = CacheDB(str(path), journal_mode = "DELETE")
    assert store.get_project().asdict() == _project().asdict()
    assert [item.asdict() for item in store.get_items()] == [item.asdict() for item in items]
    assert store.get_items_digest() == CacheDB.items_digest(items)
    assert ProjectFile.inspect(path).item_count == 2
    _assert_only(tmp_path, "demo.rbox")


def test_suffix_is_case_insensitive_and_other_suffixes_are_rejected(tmp_path) -> None:
    upper = tmp_path / "Demo.RBOX"
    _export(upper)
    assert ProjectFile.load(upper).info.item_count == 2

    for name in ("demo.db", "demo.rbox.bak", "demo"):
        with pytest.raises(ProjectFileError) as excinfo:
            _export(tmp_path / name)
        assert excinfo.value.code == ProjectFileError.INVALID_PATH
        with pytest.raises(ProjectFileError) as excinfo:
            ProjectFile.inspect(tmp_path / name)
        assert excinfo.value.code == ProjectFileError.INVALID_PATH

    (tmp_path / "folder.rbox").mkdir()
    with pytest.raises(ProjectFileError) as excinfo:
        _export(tmp_path / "folder.rbox")
    assert excinfo.value.code == ProjectFileError.INVALID_PATH

    with pytest.raises(ProjectFileError) as excinfo:
        ProjectFile.load(tmp_path / "missing.rbox")
    assert excinfo.value.code == ProjectFileError.NOT_FOUND
    _assert_only(tmp_path, "Demo.RBOX", "folder.rbox")


def test_non_project_files_are_rejected_as_invalid_format(tmp_path) -> None:
    text_file = tmp_path / "text.rbox"
    text_file.write_text("not sqlite", encoding = "utf-8")
    plain_cache = tmp_path / "cache.rbox"
    CacheDB(str(plain_cache), journal_mode = "DELETE").set_translation_cache(_project(), _items())
    wrong_magic = tmp_path / "magic.rbox"
    _export(wrong_magic)
    _tamper(wrong_magic, ("UPDATE meta SET value = ? WHERE key = ?", ("other.project", "rbox.format")))

    for path in (text_file, plain_cache, wrong_magic):
        for reader in (ProjectFile.inspect, ProjectFile.load):
            with pytest.raises(ProjectFileError) as excinfo:
                reader(path)
            assert excinfo.value.code == ProjectFileError.INVALID_FORMAT


def test_future_and_malformed_schema_versions_are_rejected(tmp_path) -> None:
    future = tmp_path / "future.rbox"
    _export(future)
    _tamper(
        future,
        ("UPDATE meta SET value = ? WHERE key = ?", ("2", "rbox.schema_version")),
        ("PRAGMA user_version=2", ()),
    )
    for reader in (ProjectFile.inspect, ProjectFile.load):
        with pytest.raises(ProjectFileError) as excinfo:
            reader(future)
        assert excinfo.value.code == ProjectFileError.UNSUPPORTED_SCHEMA

    malformed = tmp_path / "malformed.rbox"
    _export(malformed)
    _tamper(malformed, ("UPDATE meta SET value = ? WHERE key = ?", ("one", "rbox.schema_version")))
    with pytest.raises(ProjectFileError) as excinfo:
        ProjectFile.inspect(malformed)
    assert excinfo.value.code == ProjectFileError.INVALID_FORMAT

    bad_time = tmp_path / "bad-time.rbox"
    _export(bad_time)
    _tamper(bad_time, ("UPDATE meta SET value = ? WHERE key = ?", ("yesterday", "rbox.created_at")))
    with pytest.raises(ProjectFileError) as excinfo:
        ProjectFile.inspect(bad_time)
    assert excinfo.value.code == ProjectFileError.INVALID_FORMAT


def test_tampered_items_fail_digest_check_on_load(tmp_path) -> None:
    path = tmp_path / "demo.rbox"
    _export(path)
    conn = sqlite3.connect(str(path))
    try:
        row_id, data = conn.execute("SELECT id, data FROM items ORDER BY id LIMIT 1").fetchone()
        conn.execute("UPDATE items SET data = ? WHERE id = ?", (data.replace("你好", "篡改"), row_id))
        conn.commit()
    finally:
        conn.close()

    assert ProjectFile.inspect(path).item_count == 2
    with pytest.raises(ProjectFileError) as excinfo:
        ProjectFile.load(path)
    assert excinfo.value.code == ProjectFileError.CORRUPTED


def test_inconsistent_digest_metadata_and_row_count_are_rejected(tmp_path) -> None:
    digest_meta = tmp_path / "digest.rbox"
    _export(digest_meta)
    _tamper(digest_meta, ("UPDATE meta SET value = ? WHERE key = ?", ("0" * 64, "rbox.items_digest")))

    row_count = tmp_path / "count.rbox"
    _export(row_count)
    _tamper(row_count, ("DELETE FROM items WHERE id = (SELECT MAX(id) FROM items)", ()))

    for path in (digest_meta, row_count):
        with pytest.raises(ProjectFileError) as excinfo:
            ProjectFile.inspect(path)
        assert excinfo.value.code == ProjectFileError.CORRUPTED


def test_malformed_settings_fail_load(tmp_path) -> None:
    path = tmp_path / "demo.rbox"
    _export(path)
    _tamper(path, ("UPDATE settings SET value = ? WHERE key = ?", ("{not json", "glossary")))

    with pytest.raises(ProjectFileError) as excinfo:
        ProjectFile.load(path)
    assert excinfo.value.code == ProjectFileError.CORRUPTED


@pytest.mark.parametrize(
    "statement",
    [
        ("INSERT INTO settings (key, value) VALUES (?, ?)", ("openai_api_key", '"sk-123"')),
        ("INSERT INTO settings (key, value) VALUES (?, ?)", ("Password", '"hunter2"')),
        ("UPDATE settings SET value = ? WHERE key = ?", ('[{"src":"Alice","api_key":"sk-123"}]', "glossary")),
        ("UPDATE settings SET value = ? WHERE key = ?", ('{"nested":{"refresh_token":"x"}}', "batch_size")),
    ],
)
def test_tampered_settings_with_secrets_fail_load(tmp_path, statement) -> None:
    path = tmp_path / "demo.rbox"
    _export(path)
    _tamper(path, statement)

    with pytest.raises(ProjectFileError) as excinfo:
        ProjectFile.load(path)
    assert excinfo.value.code == ProjectFileError.INVALID_FORMAT
    assert "secrets" in str(excinfo.value)
    _assert_only(tmp_path, "demo.rbox")


def test_wal_mode_file_is_rejected_without_creating_sidecars(tmp_path) -> None:
    path = tmp_path / "demo.rbox"
    _export(path)
    conn = sqlite3.connect(str(path))
    try:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    finally:
        conn.close()
    _assert_only(tmp_path, "demo.rbox")

    with pytest.raises(ProjectFileError) as excinfo:
        ProjectFile.load(path)
    assert excinfo.value.code == ProjectFileError.INVALID_FORMAT
    _assert_only(tmp_path, "demo.rbox")


def test_overwrite_replaces_content_and_keeps_created_at(tmp_path) -> None:
    path = tmp_path / "demo.rbox"
    first = _export(path)
    _tamper(path, ("UPDATE meta SET value = ? WHERE key = ?", ("2020-01-01T00:00:00+00:00", "rbox.created_at")))

    second = _export(path, [CacheItem(src = "only")], settings = {"target_language": "JA"})
    snapshot = ProjectFile.load(path)

    assert second.created_at == "2020-01-01T00:00:00+00:00"
    assert second.updated_at >= first.updated_at
    assert [item.get_src() for item in snapshot.items] == ["only"]
    assert snapshot.settings == {"target_language": "JA"}
    _assert_only(tmp_path, "demo.rbox")


@pytest.mark.parametrize(
    ("items", "settings"),
    [
        (None, {"bad": object()}),
        (None, {"ratio": float("nan")}),
        (None, {"platforms": [{"name": "x", "api_key": ["sk-123"]}]}),
        (None, {"openai_api_key": "sk-123"}),
        ([CacheItem(src = "fine"), "not an item"], {}),
    ],
)
def test_failed_export_keeps_existing_file_and_removes_temp(tmp_path, items, settings) -> None:
    path = tmp_path / "demo.rbox"
    _export(path)
    original = path.read_bytes()

    with pytest.raises(ProjectFileError) as excinfo:
        _export(path, items, settings = settings)

    assert excinfo.value.code == ProjectFileError.INVALID_ARGUMENT
    assert path.read_bytes() == original
    _assert_only(tmp_path, "demo.rbox")


def test_replace_failure_keeps_existing_file_and_removes_temp(tmp_path, monkeypatch) -> None:
    path = tmp_path / "demo.rbox"
    _export(path)
    original = path.read_bytes()

    def fail_replace(src, dst):
        raise PermissionError("target is locked")

    monkeypatch.setattr(project_file_module.os, "replace", fail_replace)
    with pytest.raises(ProjectFileError) as excinfo:
        _export(path, [CacheItem(src = "new")])

    assert excinfo.value.code == ProjectFileError.WRITE_FAILED
    assert path.read_bytes() == original
    _assert_only(tmp_path, "demo.rbox")


def test_export_does_not_mutate_caller_data(tmp_path) -> None:
    project = _project()
    items = _items()
    settings = _settings()
    before = (project.asdict(), [item.asdict() for item in items], _settings())

    _export(tmp_path / "demo.rbox", items, project = project, settings = settings)

    assert (project.asdict(), [item.asdict() for item in items], settings) == before
