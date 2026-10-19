"""``POST /api/project/file/{inspect,export,import,legacy/inspect,legacy/export}``：.rbox 与缓存互转。"""

import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import project
from base.Base import Base
from base.BaseLanguage import BaseLanguage
from module.Cache.CacheDB import CacheDB
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheProject import CacheProject
from module.Config import Config
from module.Engine.Engine import Engine
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository
from module.Engine.Translator.TranslationTaskContext import ProjectAssets, TermAsset
from module.Localizer.Localizer import Localizer
from module.Project.ProjectFile import ProjectFile
from module.Renpy.ProjectPaths import RenpyProjectPaths, resolve_translation_output


@pytest.fixture(autouse = True)
def fresh_engine(monkeypatch) -> Engine:
    engine = Engine()
    monkeypatch.setattr(Engine, "__instance__", engine, raising = False)
    return engine


@pytest.fixture
def config(tmp_path: Path) -> Config:
    value = Config()
    value.input_folder = str(tmp_path / "input")
    value.output_folder = str(tmp_path / "output")
    value.renpy_project_path = value.renpy_game_folder = value.renpy_tl_folder = ""
    value.target_language = BaseLanguage.Enum.ZH
    value.text_preserve_enable = False
    value.max_workers = 16
    value.platforms = [{"id": 0, "name": "demo", "api_key": ["sk-live"]}]
    value.save(strict = True)
    return value


def _client(config: Config) -> TestClient:
    app = FastAPI()
    app.include_router(project.router)
    app.state.config = config
    return TestClient(app)


def _cache_dir(config: Config) -> Path:
    return Path(config.output_folder) / "cache"


def _items(*texts: str) -> list[CacheItem]:
    return [
        CacheItem(
            src = text,
            dst = f"{text}-译",
            file_path = "game/script.rpy",
            row = index,
            status = Base.TranslationStatus.TRANSLATED,
        )
        for index, text in enumerate(texts, 1)
    ]


def _project(name: str) -> CacheProject:
    return CacheProject(id = name, extras = {"custom_partition": {"note": name}})


def _write_sqlite_cache(config: Config, project: CacheProject, items: list[CacheItem]) -> None:
    CacheDB(str(_cache_dir(config) / CacheManager.CACHE_DB_NAME)).set_translation_cache(project, items)


def _write_json_cache(config: Config, project: CacheProject, items: list[CacheItem]) -> None:
    cache = _cache_dir(config)
    cache.mkdir(parents = True, exist_ok = True)
    (cache / "items.json").write_text(json.dumps([item.asdict() for item in items], ensure_ascii = False), encoding = "utf-8")
    (cache / "project.json").write_text(json.dumps(project.asdict(), ensure_ascii = False), encoding = "utf-8")


def _read_cache(config: Config, *, use_sqlite: bool = True) -> tuple[CacheProject, list[str]]:
    manager = CacheManager(service = False)
    manager.cache_use_sqlite = use_sqlite
    manager.load_from_file(config.output_folder, strict = True)
    return manager.get_project(), [item.get_src() for item in manager.get_items()]


def _rbox(tmp_path: Path, name: str = "demo.rbox", *, settings: dict | None = None, items=None, project_root = "E:/Games/Other") -> Path:
    path = tmp_path / name
    ProjectFile.export(
        path,
        _project("imported"),
        _items("new-1", "new-2", "new-3") if items is None else items,
        project_root = project_root,
        settings = {"target_language": "JA", "text_preserve_enable": True} if settings is None else settings,
        app_version = "test",
    )
    return path


def _tamper(path: Path, sql: str, params: tuple) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _cache_snapshot(config: Config) -> dict[str, bytes]:
    cache = _cache_dir(config)
    if not cache.is_dir():
        return {}
    return {
        str(path.relative_to(cache)): path.read_bytes()
        for path in sorted(cache.rglob("*"))
        if path.is_file()
    }


# ---------- inspect ----------

def test_inspect_reports_metadata_without_touching_engine_or_cache(tmp_path, config, fresh_engine) -> None:
    path = _rbox(tmp_path)
    fresh_engine.set_status(Engine.Status.TRANSLATING)

    with _client(config) as client:
        response = client.post("/api/project/file/inspect", json = {"path": str(path)})

    assert response.status_code == 200
    body = response.json()
    assert body["info"]["item_count"] == 3
    assert body["info"]["project_root"] == "E:/Games/Other"
    assert body["info"]["schema_version"] == ProjectFile.SCHEMA_VERSION
    assert body["output_folder"] == str(Path(config.output_folder))
    assert body["project_root_matches"] is False
    assert fresh_engine.get_status() == Engine.Status.TRANSLATING
    assert not _cache_dir(config).exists()


@pytest.mark.parametrize(
    ("name", "content", "status"),
    [
        ("missing.rbox", None, 404),
        ("text.rbox", "not sqlite", 400),
        ("demo.db", "", 400),
    ],
)
def test_inspect_rejects_invalid_files(tmp_path, config, name, content, status) -> None:
    path = tmp_path / name
    if content is not None:
        path.write_text(content, encoding = "utf-8")

    with _client(config) as client:
        response = client.post("/api/project/file/inspect", json = {"path": str(path)})

    assert response.status_code == status
    assert "工程文件不可用" in response.json()["detail"]


# ---------- export ----------

def test_export_reads_legacy_json_cache_without_migrating_it(tmp_path, config, fresh_engine) -> None:
    game = tmp_path / "Game" / "game"
    (game / "tl" / "chinese").mkdir(parents = True)
    (game / "script.rpy").write_text("label start:\n", encoding = "utf-8")
    config.renpy_project_path = str(tmp_path / "Game")
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(game / "tl" / "chinese")
    config.input_folder = str(game / "tl" / "chinese")
    config.output_folder = str(tmp_path / "Game" / "RenpyBox_Translation" / "chinese")
    config.target_language = BaseLanguage.Enum.JA
    items = _items("old-1", "old-2")
    _write_json_cache(config, _project("legacy"), items)
    before = _cache_snapshot(config)
    target = tmp_path / "out" / "legacy.rbox"
    target.parent.mkdir()

    with _client(config) as client:
        response = client.post("/api/project/file/export", json = {"path": str(target)})

    assert response.status_code == 200, response.text
    assert _cache_snapshot(config) == before
    assert not (_cache_dir(config) / CacheManager.CACHE_DB_NAME).exists()
    assert fresh_engine.get_status() == Engine.Status.IDLE

    snapshot = ProjectFile.load(target)
    assert [item.asdict() for item in snapshot.items] == [item.asdict() for item in items]
    # 快照会补齐 schema 迁移后的项目资产分区，其余项目字段原样保留。
    migrated = ("project_assets", "analysis_candidates")
    raw, exported = _project("legacy").asdict(), snapshot.project.asdict()
    assert {k: v for k, v in exported.items() if k != "extras"} == {k: v for k, v in raw.items() if k != "extras"}
    assert {k: v for k, v in exported["extras"].items() if k not in migrated} == {
        k: v for k, v in raw["extras"].items() if k not in migrated
    }
    assert ProjectAssets.from_dict(snapshot.project.get_project_assets()).revision == 1
    assert snapshot.project.get_analysis_candidates()["legacy_config_migrated"] is True
    assert snapshot.info.project_root == str(tmp_path / "Game")
    assert snapshot.settings["target_language"] == "JA"
    assert set(snapshot.settings) <= set(project.PROJECT_FILE_SETTINGS)
    for excluded in ("platforms", "output_folder", "input_folder", "renpy_project_path", "max_workers", "proxy_url", "theme"):
        assert excluded not in snapshot.settings
    assert sorted(snapshot.settings) == response.json()["settings"]
    assert response.json()["project_root_matches"] is True
    assert response.json()["output_folder"] == config.output_folder
    assert sorted(os.listdir(target.parent)) == ["legacy.rbox"]


def test_export_includes_legacy_global_assets_without_bootstrapping_live_cache(tmp_path, config, fresh_engine) -> None:
    game = tmp_path / "Game" / "game"
    (game / "tl" / "chinese").mkdir(parents = True)
    (game / "script.rpy").write_text("label start:\n", encoding = "utf-8")
    config.renpy_project_path = str(tmp_path / "Game")
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(game / "tl" / "chinese")
    config.input_folder = str(game / "tl" / "chinese")
    config.output_folder = str(tmp_path / "Game" / "CustomOutput" / "chinese")
    config.glossary_enable = True
    config.glossary_data = [
        {"src": "Sky", "dst": "天空", "info": "setting", "type": "地点"},
        {"src": "Cloud", "dst": "", "info": "needs review"},
    ]
    config.renpy_workbench_worldbook_enable = True
    config.renpy_workbench_worldbook_data = {"setting_summary": "Old global world"}
    config.renpy_workbench_character_cards_enable = True
    config.renpy_workbench_character_cards = [{"name": "Alice", "name_translation": "爱丽丝"}]
    config.renpy_workbench_generated_worldbook_draft = {"genre": "Old draft"}
    config.renpy_workbench_generated_character_drafts = [{"name": "Bob"}]
    canonical = RenpyProjectPaths.from_config(config).translation_output_dir
    assert project._path_key(canonical) != project._path_key(config.output_folder)

    items = _items("line-1")
    _write_sqlite_cache(config, _project("legacy-assets"), items)
    runtime = CacheManager(service = False)
    runtime.load_from_file(config.output_folder, strict = True)
    runtime_before = runtime.get_project().asdict()
    fresh_engine.translator = SimpleNamespace(cache_manager = runtime, _active_cache_output_folder = config.output_folder)
    before = _cache_snapshot(config)
    config_before = Path(Config.CONFIG_PATH).read_bytes()
    target = tmp_path / "legacy-assets.rbox"

    with _client(config) as client:
        response = client.post("/api/project/file/export", json = {"path": str(target)})

    assert response.status_code == 200, response.text
    assert response.json()["output_folder"] == config.output_folder
    assert _cache_snapshot(config) == before
    assert runtime.get_project().asdict() == runtime_before
    assert not canonical.exists()
    assert Path(Config.CONFIG_PATH).read_bytes() == config_before

    snapshot = ProjectFile.load(target)
    assert [item.asdict() for item in snapshot.items] == [item.asdict() for item in items]
    assert snapshot.project.get_id() == "legacy-assets"
    assert snapshot.project.get_extras()["custom_partition"] == {"note": "legacy-assets"}
    assets = ProjectAssets.from_dict(snapshot.project.get_project_assets())
    assert assets.revision == 1
    assert assets.glossary_enabled is True
    assert [(term.source, term.target, term.note) for term in assets.glossary] == [("Sky", "天空", "setting")]
    # Ren'Py 项目不继承旧全局工作台内容。
    assert assets.worldbook_enabled is False and assets.worldbook.to_dict() == {}
    assert assets.character_cards_enabled is False and assets.character_cards == ()
    candidates = snapshot.project.get_analysis_candidates()
    assert candidates["legacy_config_migrated"] is True
    assert [(item["source"], item["target"]) for item in candidates["items"]] == [("Cloud", "")]
    assert candidates.get("worldbook_draft", {}) == {}
    assert candidates.get("character_drafts", []) == []
    sky_id = TermAsset.build_record_id("LOCAL", "Sky", False)
    assert candidates["glossary_metadata"][sky_id]["type"] == "地点"


def test_export_keeps_existing_project_assets_over_legacy_globals(tmp_path, config) -> None:
    stored = _project("stored")
    stored.set_project_assets({
        "revision": 3,
        "glossary": {"enabled": True, "items": [{"source": "Door", "target": "门"}]},
    })
    stored.set_analysis_candidates({"legacy_config_migrated": True, "items": [{"source": "Gate", "target": ""}]})
    _write_sqlite_cache(config, stored, _items("line-1"))
    config.glossary_data = [{"src": "Sky", "dst": "天空"}, {"src": "Cloud", "dst": ""}]
    before = _cache_snapshot(config)

    with _client(config) as client:
        response = client.post("/api/project/file/export", json = {"path": str(tmp_path / "stored.rbox")})

    assert response.status_code == 200, response.text
    assert _cache_snapshot(config) == before
    exported = ProjectFile.load(tmp_path / "stored.rbox").project
    disk = CacheDB(str(_cache_dir(config) / CacheManager.CACHE_DB_NAME)).get_project()
    assert exported.get_project_assets() == disk.get_project_assets()
    assert exported.get_analysis_candidates() == disk.get_analysis_candidates()


def test_export_flushes_pending_runtime_results_first(tmp_path, config, fresh_engine) -> None:
    _write_sqlite_cache(config, _project("disk"), _items("disk-1"))
    runtime = CacheManager(service = False)
    runtime.set_project(_project("runtime"))
    runtime.set_items(_items("runtime-1", "runtime-2"))
    runtime.require_save_to_file(config.output_folder)
    fresh_engine.translator = SimpleNamespace(cache_manager = runtime, _active_cache_output_folder = config.output_folder)

    with _client(config) as client:
        response = client.post("/api/project/file/export", json = {"path": str(tmp_path / "live.rbox")})

    assert response.status_code == 200, response.text
    assert [item.get_src() for item in ProjectFile.load(tmp_path / "live.rbox").items] == ["runtime-1", "runtime-2"]
    assert runtime.require_flag is False


def test_export_without_cache_returns_404_and_releases_engine(tmp_path, config, fresh_engine) -> None:
    with _client(config) as client:
        response = client.post("/api/project/file/export", json = {"path": str(tmp_path / "empty.rbox")})

    assert response.status_code == 404
    assert fresh_engine.get_status() == Engine.Status.IDLE
    assert not (tmp_path / "empty.rbox").exists()


def test_export_bad_target_path_releases_engine(tmp_path, config, fresh_engine) -> None:
    _write_sqlite_cache(config, _project("disk"), _items("disk-1"))

    with _client(config) as client:
        response = client.post("/api/project/file/export", json = {"path": str(tmp_path / "missing-dir" / "x.rbox")})

    assert response.status_code == 400
    assert fresh_engine.get_status() == Engine.Status.IDLE


# ---------- busy engine ----------

@pytest.mark.parametrize("route", ["export", "import"])
@pytest.mark.parametrize("busy", ["translating", "barrier", "single"])
def test_busy_engine_rejects_without_side_effects(tmp_path, config, fresh_engine, route, busy) -> None:
    _write_sqlite_cache(config, _project("disk"), _items("disk-1"))
    path = _rbox(tmp_path, "input.rbox")
    before = _cache_snapshot(config)
    if busy == "translating":
        fresh_engine.set_status(Engine.Status.TRANSLATING)
    elif busy == "barrier":
        fresh_engine.set_stop_barrier(True)
    else:
        assert fresh_engine.try_begin_single_task()
    target = tmp_path / "busy.rbox" if route == "export" else path

    with _client(config) as client:
        response = client.post(f"/api/project/file/{route}", json = {"path": str(target)})

    assert response.status_code == 409
    assert _cache_snapshot(config) == before
    assert config.target_language == BaseLanguage.Enum.ZH
    expected = Engine.Status.TRANSLATING if busy == "translating" else Engine.Status.IDLE
    assert fresh_engine.get_status() == expected
    if route == "export":
        assert not target.exists()


def test_busy_project_file_api_error_uses_english_localizer(tmp_path, config, fresh_engine, monkeypatch) -> None:
    path = tmp_path / "blocked.rbox"
    fresh_engine.set_status(Engine.Status.TRANSLATING)
    monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)

    with _client(config) as client:
        response = client.post("/api/project/file/export", json = {"path": str(path)})

    assert response.status_code == 409
    assert response.json()["detail"] == Localizer.get().project_file_api_busy
    assert "task is running" in response.json()["detail"]
    assert not path.exists()


# ---------- import ----------

def test_import_backs_up_and_replaces_cache_and_applies_only_allowlisted_settings(tmp_path, config, fresh_engine) -> None:
    _write_sqlite_cache(config, _project("old"), _items("old-1", "old-2"))
    original_paths = {
        name: getattr(config, name)
        for name in ("input_folder", "output_folder", "renpy_project_path", "renpy_game_folder", "renpy_tl_folder")
    }
    path = _rbox(tmp_path, settings = {
        "target_language": "JA",
        "text_preserve_enable": True,
        "translation_custom_style": "冷峻",
        "output_folder": str(tmp_path / "hijack"),
        "renpy_project_path": str(tmp_path / "OtherGame"),
        "max_workers": 1,
        "platforms": [{"id": 0, "name": "evil"}],
    })

    with _client(config) as client:
        response = client.post("/api/project/file/import", json = {"path": str(path)})

    assert response.status_code == 200, response.text
    body = response.json()
    assert fresh_engine.get_status() == Engine.Status.IDLE
    assert body["item_count"] == 3
    assert body["applied_settings"] == ["target_language", "text_preserve_enable", "translation_custom_style"]
    assert body["ignored_settings"] == ["max_workers", "output_folder", "platforms", "renpy_project_path"]

    imported_project, imported_items = _read_cache(config)
    assert imported_items == ["new-1", "new-2", "new-3"]
    assert imported_project.get_extras()["custom_partition"] == {"note": "imported"}

    backup = Path(body["backup_folder"])
    assert backup.parent == _cache_dir(config) / "backup"
    assert CacheManager.CACHE_DB_NAME in os.listdir(backup)
    backup_store = CacheDB(str(backup / CacheManager.CACHE_DB_NAME))
    assert [item.get_src() for item in backup_store.get_items()] == ["old-1", "old-2"]
    assert backup_store.get_project().get_id() == "old"

    assert config.target_language == BaseLanguage.Enum.JA
    assert config.text_preserve_enable is True
    assert config.translation_custom_style == "冷峻"
    assert config.max_workers == 16
    assert config.platforms == [{"id": 0, "name": "demo", "api_key": ["sk-live"]}]
    for name, value in original_paths.items():
        assert getattr(config, name) == value

    saved = Config().load()
    assert saved.target_language == "JA"
    assert saved.text_preserve_enable is True
    assert saved.max_workers == 16
    assert saved.output_folder == original_paths["output_folder"]
    assert saved.renpy_project_path == ""


def test_import_into_legacy_json_cache_keeps_json_backend(tmp_path, config) -> None:
    config.cache_use_sqlite = False
    _write_json_cache(config, _project("old"), _items("old-1"))
    path = _rbox(tmp_path)

    with _client(config) as client:
        response = client.post("/api/project/file/import", json = {"path": str(path)})

    assert response.status_code == 200, response.text
    assert not (_cache_dir(config) / CacheManager.CACHE_DB_NAME).exists()
    assert _read_cache(config, use_sqlite = False)[1] == ["new-1", "new-2", "new-3"]
    backup = Path(response.json()["backup_folder"])
    assert sorted(os.listdir(backup)) == ["items.json", "project.json"]
    assert [entry["src"] for entry in json.loads((backup / "items.json").read_text(encoding = "utf-8"))] == ["old-1"]


def test_import_without_existing_cache_creates_cache_and_no_backup(tmp_path, config) -> None:
    path = _rbox(tmp_path)

    with _client(config) as client:
        response = client.post("/api/project/file/import", json = {"path": str(path)})

    assert response.status_code == 200, response.text
    assert response.json()["backup_folder"] == ""
    assert _read_cache(config)[1] == ["new-1", "new-2", "new-3"]


def test_export_then_import_roundtrip_restores_items_exactly(tmp_path, config) -> None:
    items = _items("a", "b")
    items[1].set_status(Base.TranslationStatus.UNTRANSLATED)
    _write_sqlite_cache(config, _project("source"), items)
    path = tmp_path / "roundtrip.rbox"

    with _client(config) as client:
        assert client.post("/api/project/file/export", json = {"path": str(path)}).status_code == 200
        _write_sqlite_cache(config, _project("changed"), _items("changed"))
        response = client.post("/api/project/file/import", json = {"path": str(path)})

    assert response.status_code == 200, response.text
    manager = CacheManager(service = False)
    manager.load_from_file(config.output_folder, strict = True)
    assert [item.asdict() for item in manager.get_items()] == [item.asdict() for item in items]
    assert manager.get_project().get_id() == "source"


@pytest.mark.parametrize("damage", ["digest", "secret", "bad_setting", "format"])
def test_invalid_import_is_rejected_before_any_side_effect(tmp_path, config, fresh_engine, damage) -> None:
    _write_sqlite_cache(config, _project("old"), _items("old-1"))
    path = _rbox(tmp_path)
    if damage == "digest":
        _tamper(path, "UPDATE items SET data = replace(data, 'new-1', 'evil') WHERE id = 1", ())
    elif damage == "secret":
        _tamper(path, "INSERT INTO settings (key, value) VALUES (?, ?)", ("openai_api_key", '"sk-123"'))
    elif damage == "bad_setting":
        _tamper(path, "UPDATE settings SET value = ? WHERE key = ?", ('"XX"', "target_language"))
    else:
        _tamper(path, "UPDATE meta SET value = ? WHERE key = ?", ("other.project", "rbox.format"))
    before = _cache_snapshot(config)
    config_before = Path(Config.CONFIG_PATH).read_bytes()

    with _client(config) as client:
        response = client.post("/api/project/file/import", json = {"path": str(path)})

    assert response.status_code == 400
    assert _cache_snapshot(config) == before
    assert not (_cache_dir(config) / "backup").exists()
    assert Path(Config.CONFIG_PATH).read_bytes() == config_before
    assert config.target_language == BaseLanguage.Enum.ZH
    assert fresh_engine.get_status() == Engine.Status.IDLE


def test_config_save_failure_restores_cache_and_keeps_config(tmp_path, config, fresh_engine, monkeypatch) -> None:
    _write_sqlite_cache(config, _project("old"), _items("old-1", "old-2"))
    path = _rbox(tmp_path)
    config_before = Path(Config.CONFIG_PATH).read_bytes()

    def fail_save(self, path = None, *, strict = False):
        raise PermissionError("config.json is locked")

    monkeypatch.setattr(Config, "save", fail_save)
    with _client(config) as client:
        response = client.post("/api/project/file/import", json = {"path": str(path)})

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "配置保存失败" in detail and "已恢复导入前的缓存" in detail
    project_value, items = _read_cache(config)
    assert items == ["old-1", "old-2"]
    assert project_value.get_id() == "old"
    assert config.target_language == BaseLanguage.Enum.ZH
    assert config.text_preserve_enable is False
    assert Path(Config.CONFIG_PATH).read_bytes() == config_before
    backups = list((_cache_dir(config) / "backup").iterdir())
    assert len(backups) == 1 and str(backups[0]) in detail
    assert fresh_engine.get_status() == Engine.Status.IDLE


def test_failed_cache_install_restores_previous_files(tmp_path, config, fresh_engine, monkeypatch) -> None:
    _write_sqlite_cache(config, _project("old"), _items("old-1"))
    path = _rbox(tmp_path)
    original_install = project._install_cache

    def half_install(*args, **kwargs):
        original_install(*args, **kwargs)
        raise RuntimeError("disk full")

    monkeypatch.setattr(project, "_install_cache", half_install)
    with _client(config) as client:
        response = client.post("/api/project/file/import", json = {"path": str(path)})

    assert response.status_code == 500
    assert "写入导入缓存失败" in response.json()["detail"]
    assert _read_cache(config)[1] == ["old-1"]
    assert config.target_language == BaseLanguage.Enum.ZH
    assert fresh_engine.get_status() == Engine.Status.IDLE


def test_failed_install_into_empty_output_removes_partial_cache(tmp_path, config, monkeypatch) -> None:
    path = _rbox(tmp_path)
    original_install = project._install_cache

    def half_install(*args, **kwargs):
        original_install(*args, **kwargs)
        raise RuntimeError("verify failed")

    monkeypatch.setattr(project, "_install_cache", half_install)
    with _client(config) as client:
        response = client.post("/api/project/file/import", json = {"path": str(path)})

    assert response.status_code == 500
    assert _cache_snapshot(config) == {}


def test_import_flushes_and_updates_matching_runtime_cache(tmp_path, config, fresh_engine) -> None:
    _write_sqlite_cache(config, _project("disk"), _items("disk-1"))
    runtime = CacheManager(service = False)
    runtime.set_project(_project("runtime"))
    runtime.set_items(_items("pending-1"))
    runtime.require_save_to_file(config.output_folder)
    fresh_engine.translator = SimpleNamespace(cache_manager = runtime, _active_cache_output_folder = config.output_folder)
    path = _rbox(tmp_path)

    with _client(config) as client:
        response = client.post("/api/project/file/import", json = {"path": str(path)})

    assert response.status_code == 200, response.text
    backup = Path(response.json()["backup_folder"])
    assert [item.get_src() for item in CacheDB(str(backup / CacheManager.CACHE_DB_NAME)).get_items()] == ["pending-1"]
    assert [item.get_src() for item in runtime.get_items()] == ["new-1", "new-2", "new-3"]
    assert runtime.get_project().get_id() == "imported"
    assert runtime.require_flag is False


def _bind_custom_output(tmp_path: Path, config: Config) -> Path:
    """绑定 Ren'Py 项目但把输出指向自定义目录，返回工作台资产所在的规范输出目录。"""
    game = tmp_path / "Game" / "game"
    (game / "tl" / "chinese").mkdir(parents = True)
    (game / "script.rpy").write_text("label start:\n", encoding = "utf-8")
    config.renpy_project_path = str(tmp_path / "Game")
    config.renpy_game_folder = str(game)
    config.renpy_tl_folder = str(game / "tl" / "chinese")
    config.input_folder = str(game / "tl" / "chinese")
    config.output_folder = str(tmp_path / "Game" / "CustomOutput" / "chinese")
    canonical = RenpyProjectPaths.from_config(config).translation_output_dir
    assert project._path_key(canonical) != project._path_key(config.output_folder)
    return canonical


def _canonical_project() -> CacheProject:
    value = CacheProject(
        id = "canonical",
        status = Base.TranslationStatus.TRANSLATING,
        extras = {"custom_partition": {"note": "canonical"}},
    )
    value.set_progress({"line": 4, "total_line": 9})
    value.set_project_assets({
        "revision": 5,
        "glossary": {"enabled": True, "items": [{"source": "Door", "target": "门"}]},
    })
    value.set_analysis_candidates({"legacy_config_migrated": True, "items": [{"source": "Gate", "target": ""}]})
    return value


def _setup_custom_output_import(tmp_path: Path, config: Config) -> tuple[Path, Path]:
    canonical = _bind_custom_output(tmp_path, config)
    _write_sqlite_cache(config, _project("old-custom"), _items("old-1", "old-2"))
    CacheDB(str(canonical / "cache" / CacheManager.CACHE_DB_NAME)).set_translation_cache(
        _canonical_project(),
        _items("canon-1"),
    )
    imported = _project("imported")
    imported.set_project_assets({
        "revision": 2,
        "glossary": {"enabled": True, "items": [{"source": "Sky", "target": "天空"}]},
    })
    imported.set_analysis_candidates({"legacy_config_migrated": True, "items": [{"source": "Cloud", "target": ""}]})
    path = tmp_path / "assets.rbox"
    ProjectFile.export(
        path,
        imported,
        _items("new-1", "new-2", "new-3"),
        project_root = str(tmp_path / "Game"),
        settings = {"target_language": "JA"},
        app_version = "test",
    )
    return canonical, path


def _db_state(cache_dir: Path) -> tuple[dict, list[str]]:
    store = CacheDB(str(cache_dir / CacheManager.CACHE_DB_NAME))
    return store.get_project().asdict(), [item.get_src() for item in store.get_items()]


def _glossary(state) -> list[tuple[str, str]]:
    return [(term.source, term.target) for term in state.assets.glossary]


def test_import_into_custom_output_syncs_canonical_project_assets(tmp_path, config) -> None:
    canonical, path = _setup_custom_output_import(tmp_path, config)
    paths_before = {
        name: getattr(config, name)
        for name in ("input_folder", "output_folder", "renpy_project_path", "renpy_game_folder", "renpy_tl_folder")
    }
    canonical_before, _ = _db_state(canonical / "cache")

    with _client(config) as client:
        response = client.post("/api/project/file/import", json = {"path": str(path)})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["output_folder"] == config.output_folder
    assert body["assets_output_folder"] == str(canonical)
    for name, value in paths_before.items():
        assert getattr(config, name) == value

    # 条目只进入自定义输出；规范输出只换资产分区，条目和项目其它字段不动。
    assert _read_cache(config)[1] == ["new-1", "new-2", "new-3"]
    canonical_after, canonical_items = _db_state(canonical / "cache")
    assert canonical_items == ["canon-1"]
    for key in ("id", "status"):
        assert canonical_after[key] == canonical_before[key]
    keep = lambda extras: {k: v for k, v in extras.items() if k not in ("project_assets", "analysis_candidates")}
    assert keep(canonical_after["extras"]) == keep(canonical_before["extras"])

    state = ProjectAssetsRepository.from_config(config).load(config)
    assert _glossary(state) == [("Sky", "天空")]
    assert [item["source"] for item in state.analysis_candidates["items"]] == ["Cloud"]
    assert state.assets.revision == 6

    custom_backup = Path(body["backup_folder"])
    assets_backup = Path(body["assets_backup_folder"])
    assert custom_backup.parent == _cache_dir(config) / "backup"
    assert assets_backup.parent == canonical / "cache" / "backup"
    assert [item.get_src() for item in CacheDB(str(custom_backup / CacheManager.CACHE_DB_NAME)).get_items()] == ["old-1", "old-2"]
    assert _db_state(assets_backup) == (canonical_before, ["canon-1"])


def test_custom_output_import_config_failure_rolls_back_both_caches_and_runtime(
    tmp_path,
    config,
    fresh_engine,
    monkeypatch,
) -> None:
    canonical, path = _setup_custom_output_import(tmp_path, config)
    runtime = CacheManager(service = False)
    runtime.load_from_file(str(canonical), strict = True)
    fresh_engine.translator = SimpleNamespace(cache_manager = runtime, _active_cache_output_folder = str(canonical))
    runtime_project = runtime.get_project()
    runtime_before = runtime_project.asdict()
    runtime_items_before = [item.asdict() for item in runtime.get_items()]
    canonical_before = _db_state(canonical / "cache")
    custom_before = _read_cache(config)
    config_before = Path(Config.CONFIG_PATH).read_bytes()
    published: list[list[tuple[str, str]]] = []

    def fail_save(self, path = None, *, strict = False):
        assets = ProjectAssets.from_dict(runtime.get_project().get_project_assets())
        published.append([(term.source, term.target) for term in assets.glossary])
        raise PermissionError("config.json is locked")

    monkeypatch.setattr(Config, "save", fail_save)
    with _client(config) as client:
        response = client.post("/api/project/file/import", json = {"path": str(path)})

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "配置保存失败" in detail and "已恢复导入前的缓存" in detail
    # 同步确实发布到了运行态，回滚后只还原资产分区，对象与条目都保持原样。
    assert published == [[("Sky", "天空")]]
    assert runtime.get_project() is runtime_project
    assert runtime_project.asdict() == runtime_before
    assert [item.asdict() for item in runtime.get_items()] == runtime_items_before

    assert _db_state(canonical / "cache") == canonical_before
    restored_project, restored_items = _read_cache(config)
    assert restored_items == custom_before[1]
    assert restored_project.get_id() == "old-custom"
    assert _glossary(ProjectAssetsRepository.from_config(config).load(config)) == [("Door", "门")]

    custom_backups = list((_cache_dir(config) / "backup").iterdir())
    canonical_backups = list((canonical / "cache" / "backup").iterdir())
    assert len(custom_backups) == 1 and str(custom_backups[0]) in detail
    assert len(canonical_backups) == 1 and str(canonical_backups[0]) in detail
    assert config.target_language == BaseLanguage.Enum.ZH
    assert Path(Config.CONFIG_PATH).read_bytes() == config_before
    assert fresh_engine.get_status() == Engine.Status.IDLE


def test_custom_output_import_asset_sync_failure_rolls_back_both_caches(
    tmp_path,
    config,
    fresh_engine,
    monkeypatch,
) -> None:
    canonical, path = _setup_custom_output_import(tmp_path, config)
    canonical_before = _db_state(canonical / "cache")
    config_before = Path(Config.CONFIG_PATH).read_bytes()

    def fail_sync(self, *args, **kwargs):
        raise OSError("canonical cache is locked")

    monkeypatch.setattr(ProjectAssetsRepository, "replace_asset_sections", fail_sync)
    with _client(config) as client:
        response = client.post("/api/project/file/import", json = {"path": str(path)})

    assert response.status_code == 500
    assert "同步项目资料失败" in response.json()["detail"]
    assert _read_cache(config)[1] == ["old-1", "old-2"]
    assert _db_state(canonical / "cache") == canonical_before
    assert config.target_language == BaseLanguage.Enum.ZH
    assert Path(Config.CONFIG_PATH).read_bytes() == config_before
    assert fresh_engine.get_status() == Engine.Status.IDLE


def test_import_into_canonical_output_keeps_single_backup(tmp_path, config) -> None:
    canonical = _bind_custom_output(tmp_path, config)
    config.output_folder = str(canonical)
    _write_sqlite_cache(config, _project("old"), _items("old-1"))
    path = _rbox(tmp_path)

    with _client(config) as client:
        response = client.post("/api/project/file/import", json = {"path": str(path)})

    assert response.status_code == 200, response.text
    body = response.json()
    assert Path(body["backup_folder"]).parent == canonical / "cache" / "backup"
    assert body["assets_output_folder"] == ""
    assert body["assets_backup_folder"] == ""
    assert len(list((canonical / "cache" / "backup").iterdir())) == 1


def _tree_bytes(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _write_json_at(output: Path, project: CacheProject, items: list[CacheItem]) -> None:
    cache = output / "cache"
    cache.mkdir(parents = True, exist_ok = True)
    (cache / "items.json").write_text(json.dumps([item.asdict() for item in items], ensure_ascii = False), encoding = "utf-8")
    (cache / "project.json").write_text(json.dumps(project.asdict(), ensure_ascii = False), encoding = "utf-8")


def _write_sqlite_at(output: Path, project: CacheProject, items: list[CacheItem]) -> None:
    CacheDB(str(output / "cache" / CacheManager.CACHE_DB_NAME)).set_translation_cache(project, items)


def _bind_game(tmp_path: Path, config: Config) -> None:
    _bind_custom_output(tmp_path, config)


def test_import_leaves_runtime_cache_of_other_output_alone(tmp_path, config, fresh_engine) -> None:
    runtime = CacheManager(service = False)
    runtime.set_items(_items("other-project"))
    other = str(tmp_path / "other-output")
    runtime.require_save_to_file(other)
    fresh_engine.translator = SimpleNamespace(cache_manager = runtime, _active_cache_output_folder = other)
    path = _rbox(tmp_path)

    with _client(config) as client:
        assert client.post("/api/project/file/import", json = {"path": str(path)}).status_code == 200

    assert [item.get_src() for item in runtime.get_items()] == ["other-project"]
    assert runtime.require_flag is True
    assert not Path(other).exists()


# ---------- legacy cache ----------

def _path_fields(config: Config) -> dict[str, str]:
    return {
        name: getattr(config, name)
        for name in ("input_folder", "output_folder", "renpy_project_path", "renpy_game_folder", "renpy_tl_folder")
    }


def test_legacy_json_outside_project_exports_current_settings_without_touching_source(tmp_path, config, fresh_engine) -> None:
    _bind_game(tmp_path, config)
    _write_sqlite_at(Path(config.output_folder), _project("live"), _items("live-only"))
    live_before = _tree_bytes(Path(config.output_folder))
    game_script = Path(config.renpy_game_folder) / "script.rpy"
    script_before = game_script.read_bytes()
    legacy = tmp_path / "old-outside"
    stale = _items("stale-1")
    current = _items("legacy-1", "legacy-2")
    _write_json_at(legacy, _project("stale"), stale)
    journal = {
        "project": _project("legacy").asdict(),
        "items": [item.asdict() for item in current],
    }
    (legacy / "cache" / CacheManager.RESET_JOURNAL_NAME).write_text(
        json.dumps(journal, ensure_ascii = False, separators = (",", ":")),
        encoding = "utf-8",
    )
    (legacy / "config.json").write_text('{"target_language":"EN","api_key":"sk-old"}', encoding = "utf-8")
    config.target_language = BaseLanguage.Enum.JA
    config.text_preserve_enable = True
    before = _tree_bytes(legacy)
    config_before = Path(Config.CONFIG_PATH).read_bytes()
    paths_before = _path_fields(config)
    target = tmp_path / "from-json.rbox"

    with _client(config) as client:
        inspected = client.post("/api/project/file/legacy/inspect", json = {"folder": str(legacy)})
        via_cache = client.post("/api/project/file/legacy/inspect", json = {"folder": str(legacy / "cache")})
        exported = client.post(
            "/api/project/file/legacy/export",
            json = {"folder": str(legacy), "path": str(target)},
        )

    assert inspected.status_code == 200, inspected.text
    inspect_body = inspected.json()
    assert set(inspect_body) == {
        "output_folder", "cache_folder", "cache_format", "item_count", "current_project_root", "settings",
    }
    assert Path(inspect_body["output_folder"]) == legacy
    assert Path(inspect_body["cache_folder"]) == legacy / "cache"
    assert inspect_body["cache_format"] == "json"
    assert inspect_body["item_count"] == 2
    assert inspect_body["current_project_root"] == str(tmp_path / "Game")
    assert inspect_body["settings"] == sorted(project._export_settings(config))
    assert via_cache.json()["output_folder"] == inspect_body["output_folder"]
    assert via_cache.json()["cache_folder"] == inspect_body["cache_folder"]
    assert via_cache.json()["item_count"] == 2

    assert exported.status_code == 200, exported.text
    body = exported.json()
    assert body["source_output_folder"] == inspect_body["output_folder"]
    assert body["output_folder"] == config.output_folder
    assert body["output_folder"] != body["source_output_folder"]
    assert body["current_project_root"] == str(tmp_path / "Game")
    assert body["project_root_matches"] is True
    assert body["settings"] == inspect_body["settings"]
    assert "target_language" in body["settings"]
    for excluded in ("platforms", "output_folder", "input_folder", "renpy_project_path", "max_workers", "api_key"):
        assert excluded not in body["settings"]

    snapshot = ProjectFile.load(target)
    assert [item.asdict() for item in snapshot.items] == [item.asdict() for item in current]
    assert snapshot.info.project_root == str(tmp_path / "Game")
    assert snapshot.settings["target_language"] == "JA"
    assert snapshot.settings["text_preserve_enable"] is True
    assert set(snapshot.settings) <= set(project.PROJECT_FILE_SETTINGS)
    assert b"sk-live" not in target.read_bytes()
    assert b"sk-old" not in target.read_bytes()
    assert _tree_bytes(legacy) == before
    assert not (legacy / "cache" / CacheManager.CACHE_DB_NAME).exists()
    assert not (legacy / "cache" / f"{CacheManager.CACHE_DB_NAME}-wal").exists()
    assert not (legacy / "cache" / f"{CacheManager.CACHE_DB_NAME}-shm").exists()
    assert _tree_bytes(Path(config.output_folder)) == live_before
    assert game_script.read_bytes() == script_before
    assert Path(Config.CONFIG_PATH).read_bytes() == config_before
    assert _path_fields(config) == paths_before
    assert fresh_engine.get_status() == Engine.Status.IDLE


def test_legacy_sqlite_subfolder_and_wal_keep_source_bytes(tmp_path, config, fresh_engine) -> None:
    _bind_game(tmp_path, config)
    _write_sqlite_at(Path(config.output_folder), _project("live"), _items("live-only"))
    live_before = _tree_bytes(Path(config.output_folder))
    legacy = tmp_path / "old-sqlite"
    _write_sqlite_at(legacy, _project("base"), _items("base-1"))
    db_path = legacy / "cache" / CacheManager.CACHE_DB_NAME
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        updated = _items("from-wal")
        connection.execute("DELETE FROM items")
        connection.execute(
            "INSERT INTO items (data) VALUES (?)",
            (json.dumps(updated[0].asdict(), ensure_ascii = False, separators = (",", ":")),),
        )
        connection.commit()
        isolated = tmp_path / "db-only.db"
        isolated.write_bytes(db_path.read_bytes())
        with sqlite3.connect(str(isolated)) as alone:
            alone_row = json.loads(alone.execute("SELECT data FROM items").fetchone()[0])
        assert alone_row["src"] == "base-1"
        assert (legacy / "cache" / f"{CacheManager.CACHE_DB_NAME}-wal").is_file()
        before = _tree_bytes(legacy)
        names_before = sorted(path.name for path in (legacy / "cache").iterdir())
        target = tmp_path / "from-sqlite.rbox"

        with _client(config) as client:
            inspected = client.post(
                "/api/project/file/legacy/inspect",
                json = {"folder": str(legacy / "cache")},
            )
            exported = client.post(
                "/api/project/file/legacy/export",
                json = {"folder": str(legacy), "path": str(target)},
            )
        assert inspected.status_code == 200, inspected.text
        assert inspected.json()["cache_format"] == "sqlite"
        assert Path(inspected.json()["output_folder"]) == legacy
        assert Path(inspected.json()["cache_folder"]) == legacy / "cache"
        assert inspected.json()["item_count"] == 1
        assert exported.status_code == 200, exported.text
        assert exported.json()["source_output_folder"] == str(legacy)
        assert [item.asdict() for item in ProjectFile.load(target).items] == [item.asdict() for item in updated]
        # 先比较源文件，再关闭本测试的 WAL 写连接；关闭它本身会 checkpoint 并删除旁路文件。
        assert _tree_bytes(legacy) == before
        assert sorted(path.name for path in (legacy / "cache").iterdir()) == names_before
        assert _tree_bytes(Path(config.output_folder)) == live_before
        assert fresh_engine.get_status() == Engine.Status.IDLE
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("folder_name", "prepare", "status", "detail"),
    [
        ("missing", None, 404, "没有可迁移"),
        ("empty", "empty", 404, "没有可迁移"),
        ("file", "file", 400, "旧缓存目录无效"),
        ("truncated-db", "truncated-db", 400, "不完整或已损坏"),
        ("broken-json", "broken-json", 400, "不完整或已损坏"),
        ("bad-journal", "bad-journal", 400, "不完整或已损坏"),
        ("bad-db-hides-json", "bad-db-hides-json", 400, "不完整或已损坏"),
    ],
)
def test_legacy_malformed_or_missing_cache_is_refused(tmp_path, config, fresh_engine, folder_name, prepare, status, detail) -> None:
    _bind_game(tmp_path, config)
    folder = tmp_path / folder_name
    if prepare == "empty":
        folder.mkdir()
    elif prepare == "file":
        folder.write_text("cache.db", encoding = "utf-8")
    elif prepare == "truncated-db":
        (folder / "cache").mkdir(parents = True)
        (folder / "cache" / CacheManager.CACHE_DB_NAME).write_bytes(b"not a database")
    elif prepare == "broken-json":
        (folder / "cache").mkdir(parents = True)
        (folder / "cache" / "items.json").write_text("{", encoding = "utf-8")
        (folder / "cache" / "project.json").write_text("{}", encoding = "utf-8")
    elif prepare == "bad-journal":
        _write_json_at(folder, _project("ok"), _items("ok-1"))
        (folder / "cache" / CacheManager.RESET_JOURNAL_NAME).write_text("{", encoding = "utf-8")
    elif prepare == "bad-db-hides-json":
        _write_json_at(folder, _project("ok"), _items("ok-1"))
        (folder / "cache" / CacheManager.CACHE_DB_NAME).write_bytes(b"not a database")
    before = _tree_bytes(folder) if folder.exists() else {}
    target = tmp_path / "refused.rbox"

    with _client(config) as client:
        inspected = client.post("/api/project/file/legacy/inspect", json = {"folder": str(folder)})
        exported = client.post(
            "/api/project/file/legacy/export",
            json = {"folder": str(folder), "path": str(target)},
        )

    assert inspected.status_code == status, inspected.text
    assert detail in inspected.json()["detail"]
    assert exported.status_code == status, exported.text
    assert detail in exported.json()["detail"]
    assert _tree_bytes(folder) == before if folder.exists() else True
    assert not target.exists()
    assert fresh_engine.get_status() == Engine.Status.IDLE


def test_legacy_export_requires_current_game_binding(tmp_path, config, fresh_engine, monkeypatch) -> None:
    legacy = tmp_path / "old-outside"
    _write_json_at(legacy, _project("legacy"), _items("row-1"))
    before = _tree_bytes(legacy)
    target = tmp_path / "unbound.rbox"

    with _client(config) as client:
        inspected = client.post("/api/project/file/legacy/inspect", json = {"folder": str(legacy)})
        exported = client.post(
            "/api/project/file/legacy/export",
            json = {"folder": str(legacy), "path": str(target)},
        )
        monkeypatch.setattr(Localizer, "APP_LANGUAGE", BaseLanguage.Enum.EN)
        english = client.post(
            "/api/project/file/legacy/export",
            json = {"folder": str(legacy), "path": str(target)},
        )

    assert inspected.status_code == 200, inspected.text
    assert inspected.json()["current_project_root"] == ""
    assert exported.status_code == 400
    assert "绑定当前 Ren'Py" in exported.json()["detail"]
    assert english.status_code == 400
    assert english.json()["detail"] == Localizer.get().project_file_api_legacy_unbound
    assert _tree_bytes(legacy) == before
    assert not target.exists()
    assert fresh_engine.get_status() == Engine.Status.IDLE


@pytest.mark.parametrize("route", ["inspect", "export"])
@pytest.mark.parametrize("busy", ["translating", "barrier", "single"])
def test_legacy_busy_engine_rejects_without_side_effects(tmp_path, config, fresh_engine, route, busy) -> None:
    _bind_game(tmp_path, config)
    legacy = tmp_path / "old-outside"
    _write_json_at(legacy, _project("legacy"), _items("kept"))
    before = _tree_bytes(legacy)
    if busy == "translating":
        fresh_engine.set_status(Engine.Status.TRANSLATING)
    elif busy == "barrier":
        fresh_engine.set_stop_barrier(True)
    else:
        assert fresh_engine.try_begin_single_task()
    target = tmp_path / "busy.rbox"
    payload = {"folder": str(legacy)}
    if route == "export":
        payload["path"] = str(target)

    with _client(config) as client:
        response = client.post(f"/api/project/file/legacy/{route}", json = payload)

    assert response.status_code == 409
    assert response.json()["detail"] == Localizer.get().project_file_api_busy
    assert _tree_bytes(legacy) == before
    assert not target.exists()
    expected = Engine.Status.TRANSLATING if busy == "translating" else Engine.Status.IDLE
    assert fresh_engine.get_status() == expected


def test_legacy_export_leaves_pending_runtime_and_live_cache_intact(tmp_path, config, fresh_engine) -> None:
    _bind_game(tmp_path, config)
    live = Path(config.output_folder)
    _write_sqlite_at(live, _project("live"), _items("live-1"))
    live_before = _tree_bytes(live)
    legacy = tmp_path / "old-outside"
    disk_items = _items("disk-1", "disk-2")
    _write_sqlite_at(legacy, _project("disk"), disk_items)
    before = _tree_bytes(legacy)
    runtime = CacheManager(service = False)
    runtime.set_project(_project("pending"))
    runtime.set_items(_items("pending-1"))
    runtime.require_save_to_file(str(legacy))
    fresh_engine.translator = SimpleNamespace(
        cache_manager = runtime,
        _active_cache_output_folder = str(legacy),
    )
    paths_before = _path_fields(config)
    target = tmp_path / "disk.rbox"

    with _client(config) as client:
        response = client.post(
            "/api/project/file/legacy/export",
            json = {"folder": str(legacy), "path": str(target)},
        )

    assert response.status_code == 200, response.text
    assert [item.asdict() for item in ProjectFile.load(target).items] == [item.asdict() for item in disk_items]
    assert [item.get_src() for item in runtime.get_items()] == ["pending-1"]
    assert runtime.require_flag is True
    assert _tree_bytes(legacy) == before
    assert _tree_bytes(live) == live_before
    assert _path_fields(config) == paths_before
    assert fresh_engine.get_status() == Engine.Status.IDLE


def test_legacy_export_refuses_destinations_that_clobber_source_or_live_files(tmp_path, config, fresh_engine) -> None:
    _bind_game(tmp_path, config)
    live = Path(config.output_folder)
    _write_sqlite_at(live, _project("live"), _items("live-1"))
    legacy = tmp_path / "old-outside"
    _write_sqlite_at(legacy, _project("disk"), _items("disk-1"))
    note = legacy / "notes.txt"
    note.write_text("keep", encoding = "utf-8")
    script = Path(config.renpy_game_folder) / "script.rpy"
    before = {
        "legacy": _tree_bytes(legacy),
        "live": _tree_bytes(live),
        "script": script.read_bytes(),
    }
    destinations = [
        legacy / "cache" / CacheManager.CACHE_DB_NAME,
        legacy / "cache" / "moved.rbox",
        live / "cache" / CacheManager.CACHE_DB_NAME,
        note,
        script,
    ]

    with _client(config) as client:
        for destination in destinations:
            response = client.post(
                "/api/project/file/legacy/export",
                json = {"folder": str(legacy), "path": str(destination)},
            )
            assert response.status_code == 400, response.text
            assert "另选一个 .rbox" in response.json()["detail"]

    assert _tree_bytes(legacy) == before["legacy"]
    assert _tree_bytes(live) == before["live"]
    assert script.read_bytes() == before["script"]
    assert not (legacy / "cache" / "moved.rbox").exists()
    assert fresh_engine.get_status() == Engine.Status.IDLE
