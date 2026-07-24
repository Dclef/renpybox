import json
import threading

import pytest

from base.Base import Base
from module.Cache.CacheDB import CacheDB
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheLoadError, CacheManager
from module.Cache.CacheProject import CacheProject
from module.Engine.Translator.TranslationTaskContext import TranslationTaskContext


def _project_with_run_data() -> CacheProject:
    context = TranslationTaskContext.from_config(
        {"source_language": "JA", "target_language": "ZH"},
        {
            "revision": 3,
            "glossary": {
                "enabled": True,
                "items": [{"source": "Alice", "target": "爱丽丝"}],
            },
        },
        created_at = "2026-07-24T02:05:00+00:00",
    )
    return CacheProject.from_dict({
        "id": "project-1",
        "status": Base.TranslationStatus.TRANSLATING,
        "extras": {
            "schema_version": 2,
            "progress": {"line": 2, "total_line": 10},
            "project_assets": context.assets.to_dict(),
            "analysis_candidates": {"schema_version": 1, "items": [{"source": "Bob"}]},
            "translation_snapshot": context.to_snapshot(),
            "quality_progress": {"line": 1},
            "custom_long_lived_data": {"keep": True},
        },
    })


def test_legacy_flat_progress_is_migrated_at_read_boundary() -> None:
    project = CacheProject.from_dict({
        "extras": {
            "line": 4,
            "total_line": 9,
            "time": 1.5,
            "unknown_long_lived": {"keep": True},
        },
    })
    extras = project.get_extras()

    assert extras["schema_version"] == 2
    assert extras["progress"] == {"line": 4, "total_line": 9, "time": 1.5}
    assert extras["unknown_long_lived"] == {"keep": True}
    assert "line" not in {key for key in extras if key != "progress"}
    assert CacheProject.migrate_extras(extras) == extras


def test_cache_extras_reject_unsupported_future_schema() -> None:
    with pytest.raises(ValueError, match = "Unsupported cache extras schema"):
        CacheProject(extras = {"schema_version": 999})


def test_partition_accessors_do_not_expose_mutable_internal_data() -> None:
    project = _project_with_run_data()
    progress = project.get_progress()
    assets = project.get_project_assets()
    snapshot = project.get_translation_snapshot()

    progress["line"] = 99
    assets["revision"] = 99
    snapshot["target_language"] = "EN"

    assert project.get_progress()["line"] == 2
    assert project.get_project_assets()["revision"] == 3
    assert project.get_translation_snapshot()["target_language"] == "ZH"


def test_snapshot_persistence_boundary_strips_raw_credentials() -> None:
    project = CacheProject()
    project.set_translation_snapshot({
        "schema_version": 1,
        "api_key": "secret",
        "nested": {"token": "nested-secret", "model": "kept"},
    })

    assert project.get_translation_snapshot() == {
        "schema_version": 1,
        "nested": {"model": "kept"},
    }


def test_project_asset_and_candidate_setters_write_versioned_partitions() -> None:
    project = CacheProject()
    project.set_project_assets({
        "revision": 2,
        "glossary": {
            "enabled": True,
            "items": [{"src": " Alice ", "dst": " 爱丽丝 "}],
        },
    })
    project.set_analysis_candidates({"items": [{"source": "Bob"}]})

    assets = project.get_project_assets()
    candidates = project.get_analysis_candidates()
    assert assets["schema_version"] == 1
    assert assets["glossary"]["items"][0]["source"] == "Alice"
    assert candidates == {"schema_version": 1, "items": [{"source": "Bob"}]}


def test_legacy_set_extras_updates_progress_without_losing_assets() -> None:
    project = _project_with_run_data()
    project.set_extras({"line": 6, "total_line": 10})

    assert project.get_progress() == {"line": 6, "total_line": 10}
    assert project.get_project_assets()["revision"] == 3
    assert project.get_analysis_candidates()["items"] == [{"source": "Bob"}]


def test_reset_translation_run_preserves_long_lived_partitions() -> None:
    project = _project_with_run_data()
    project.reset_translation_run()
    extras = project.get_extras()

    assert project.get_status() == Base.TranslationStatus.UNTRANSLATED
    assert extras["progress"] == {}
    assert extras["translation_snapshot"] == {}
    assert "quality_progress" not in extras
    assert extras["project_assets"]["revision"] == 3
    assert extras["analysis_candidates"]["items"] == [{"source": "Bob"}]
    assert extras["custom_long_lived_data"] == {"keep": True}


def test_cache_project_rejects_item_only_statuses() -> None:
    with pytest.raises(ValueError, match = "Invalid cache project status"):
        CacheProject(status = Base.TranslationStatus.POLISHED)

    project = CacheProject()
    with pytest.raises(ValueError, match = "Invalid cache project status"):
        project.set_status(Base.TranslationStatus.EXCLUDED)

    project.set_status("TRANSLATED")
    assert project.get_status() == Base.TranslationStatus.TRANSLATED


def test_sqlite_snapshot_roundtrip_and_atomic_run_reset(tmp_path) -> None:
    db = CacheDB(str(tmp_path / "cache.db"))
    project = _project_with_run_data()
    original_snapshot = project.get_translation_snapshot()
    replacement_items = [CacheItem(src = "new source")]

    db.set_project(project)
    loaded = db.get_project()
    assert loaded is not None
    assert loaded.get_translation_snapshot() == original_snapshot

    reset_project = db.reset_translation_run(loaded, replacement_items)
    reloaded = db.get_project()
    assert reloaded is not None
    assert reset_project.get_translation_snapshot() is None
    assert reloaded.get_progress() == {}
    assert reloaded.get_project_assets()["revision"] == 3
    assert reloaded.get_analysis_candidates()["items"] == [{"source": "Bob"}]
    assert [item.get_src() for item in db.get_items()] == ["new source"]


def test_sqlite_run_reset_persists_new_snapshot_progress_and_items_together(tmp_path) -> None:
    db = CacheDB(str(tmp_path / "cache.db"))
    project = _project_with_run_data()
    new_context = TranslationTaskContext.from_config(
        {"source_language": "EN", "target_language": "ZH"},
        project.get_project_assets(),
        created_at = "2026-07-24T03:00:00+00:00",
    )

    db.set_project(project)
    reset_project = db.reset_translation_run(
        project,
        [CacheItem(src = "new run")],
        snapshot = new_context,
        progress = {"line": 0, "total_line": 1},
    )
    reloaded = db.get_project()

    assert reloaded is not None
    assert reset_project.get_translation_snapshot() == new_context.to_snapshot()
    assert reloaded.get_translation_snapshot() == new_context.to_snapshot()
    assert reloaded.get_progress() == {"line": 0, "total_line": 1}
    assert [item.get_src() for item in db.get_items()] == ["new run"]


def test_cache_manager_in_memory_reset_keeps_assets_and_replaces_items() -> None:
    manager = CacheManager(service = False)
    manager.set_project(_project_with_run_data())
    manager.set_items([CacheItem(src = "old source")])

    manager.reset_translation_run([CacheItem(src = "new source")])

    assert manager.get_project().get_project_assets()["revision"] == 3
    assert manager.get_project().get_translation_snapshot() is None
    assert [item.get_src() for item in manager.get_items()] == ["new source"]


def test_cache_manager_reset_accepts_initial_snapshot_and_progress() -> None:
    manager = CacheManager(service = False)
    manager.set_project(_project_with_run_data())
    context = TranslationTaskContext.from_config(
        {"source_language": "JA", "target_language": "EN"},
        manager.get_project().get_project_assets(),
        created_at = "2026-07-24T03:00:00+00:00",
    )

    manager.reset_translation_run(
        [CacheItem(src = "source")],
        snapshot = context,
        progress = {"line": 0, "total_line": 1},
    )

    assert manager.get_project().get_translation_snapshot() == context.to_snapshot()
    assert manager.get_project().get_progress() == {"line": 0, "total_line": 1}


def test_same_translation_reset_uses_completed_helper_and_clears_quality_origin() -> None:
    polished = CacheItem(src = "same", dst = "same", status = Base.TranslationStatus.TRANSLATED)
    polished.set_quality_result("same", CacheItem.QualityOrigin.POLISHER)
    translated_in_past = CacheItem(
        src = "legacy",
        dst = "legacy",
        status = Base.TranslationStatus.TRANSLATED_IN_PAST,
    )
    manager = CacheManager(service = False)
    manager.set_items([polished, translated_in_past])

    assert manager.reset_same_translation_items() == 2
    assert polished.get_status() == Base.TranslationStatus.UNTRANSLATED
    assert polished.get_dst() == ""
    assert polished.get_quality_origin() is None
    assert translated_in_past.get_status() == Base.TranslationStatus.UNTRANSLATED


def test_json_cache_snapshot_roundtrip_and_run_reset(tmp_path) -> None:
    manager = CacheManager(service = False)
    manager.cache_use_sqlite = False
    manager.set_project(_project_with_run_data())
    manager.set_items([CacheItem(src = "old source")])
    manager.save_to_file(manager.get_project(), manager.get_items(), str(tmp_path))

    loaded = CacheManager(service = False)
    loaded.cache_use_sqlite = False
    loaded.load_from_file(str(tmp_path))
    assert loaded.get_project().get_translation_snapshot() is not None
    assert loaded.get_project().get_project_assets()["revision"] == 3

    loaded.reset_translation_run([CacheItem(src = "new source")], str(tmp_path))
    reloaded = CacheManager(service = False)
    reloaded.cache_use_sqlite = False
    reloaded.load_from_file(str(tmp_path))
    assert reloaded.get_project().get_translation_snapshot() is None
    assert reloaded.get_project().get_project_assets()["revision"] == 3
    assert [item.get_src() for item in reloaded.get_items()] == ["new source"]


def test_json_cache_recovers_interrupted_cross_file_transaction(tmp_path) -> None:
    cache_path = tmp_path / "cache"
    cache_path.mkdir()
    stale_project = CacheProject(id = "stale")
    committed_project = _project_with_run_data()
    (cache_path / "items.json").write_text(
        json.dumps([CacheItem(src = "stale item").asdict()]),
        encoding = "utf-8",
    )
    (cache_path / "project.json").write_text(
        json.dumps(stale_project.asdict()),
        encoding = "utf-8",
    )
    journal_path = cache_path / CacheManager.RESET_JOURNAL_NAME
    journal_path.write_text(
        json.dumps({
            "project": committed_project.asdict(),
            "items": [CacheItem(src = "committed item").asdict()],
        }),
        encoding = "utf-8",
    )

    manager = CacheManager(service = False)
    manager.cache_use_sqlite = False
    manager.load_from_file(str(tmp_path))

    assert manager.get_project().get_id() == committed_project.get_id()
    assert [item.get_src() for item in manager.get_items()] == ["committed item"]
    assert journal_path.exists() is False


def test_strict_cache_load_keeps_memory_state_when_existing_cache_is_corrupt(tmp_path) -> None:
    cache_path = tmp_path / "cache"
    cache_path.mkdir()
    (cache_path / "items.json").write_text("[]", encoding = "utf-8")
    (cache_path / "project.json").write_text("{broken", encoding = "utf-8")

    manager = CacheManager(service = False)
    manager.cache_use_sqlite = False
    manager.set_project(CacheProject(id = "in-memory"))
    manager.set_items([CacheItem(src = "keep me")])

    with pytest.raises(CacheLoadError):
        manager.load_from_file(str(tmp_path), strict = True)

    assert manager.get_project().get_id() == "in-memory"
    assert [item.get_src() for item in manager.get_items()] == ["keep me"]
    assert (cache_path / "project.json").read_text(encoding = "utf-8") == "{broken"


def test_pending_autosave_cannot_overwrite_a_completed_reset(tmp_path, monkeypatch) -> None:
    manager = CacheManager(service = False)
    manager.cache_use_sqlite = False
    manager.set_project(CacheProject(id = "project"))
    manager.set_items([CacheItem(src = "old")])
    manager.require_save_to_file(str(tmp_path))
    manager.last_require_time = 0

    entered = threading.Event()
    release = threading.Event()
    original_save = manager._save_translation_run_to_json

    def blocking_save(output_path, project, items):
        entered.set()
        assert release.wait(timeout = 5)
        original_save(output_path, project, items)

    monkeypatch.setattr(manager, "_save_translation_run_to_json", blocking_save)
    autosave = threading.Thread(target = lambda: manager._run_pending_save(now = 100))
    autosave.start()
    assert entered.wait(timeout = 5)

    reset = threading.Thread(
        target = lambda: manager.reset_translation_run(
            [CacheItem(src = "new")],
            str(tmp_path),
        )
    )
    reset.start()
    release.set()
    autosave.join(timeout = 5)
    reset.join(timeout = 5)
    assert not autosave.is_alive()
    assert not reset.is_alive()

    loaded = CacheManager(service = False)
    loaded.cache_use_sqlite = False
    loaded.load_from_file(str(tmp_path), strict = True)
    assert [item.get_src() for item in loaded.get_items()] == ["new"]


def test_cache_project_serialization_contains_only_versioned_extras() -> None:
    project = CacheProject.from_dict({"extras": {"line": 1}})

    payload = json.loads(json.dumps(project.asdict()))

    assert payload["extras"]["schema_version"] == 2
    assert payload["extras"]["progress"] == {"line": 1}
    assert "line" not in payload["extras"]
