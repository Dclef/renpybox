import json
from types import SimpleNamespace

from base.Base import Base
from module.Cache.CacheDB import CacheDB
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheProject import CacheProject
from module.Engine.Engine import Engine
from module.Engine.Translator.ProjectAssetsRepository import ProjectAssetsRepository


def _legacy_config(tmp_path, *, sqlite: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        output_folder = str(tmp_path),
        cache_use_sqlite = sqlite,
        renpy_workbench_worldbook_enable = True,
        renpy_workbench_worldbook_data = {"setting_summary": "A floating city"},
        renpy_workbench_character_cards_enable = True,
        renpy_workbench_character_cards = [
            {"name": "Alice", "name_translation": "爱丽丝", "enabled": True},
        ],
        glossary_enable = True,
        glossary_data = [
            {"src": "Sky", "dst": "天空", "info": "setting"},
            {"src": "Cloud", "dst": "", "info": "needs review"},
        ],
        text_preserve_enable = True,
        text_preserve_data = [{"src": "[player]", "comment": "placeholder"}],
        renpy_workbench_generated_worldbook_draft = {"genre": "Fantasy"},
        renpy_workbench_generated_character_drafts = [{"name": "Bob"}],
        renpy_workbench_last_analysis_scope = "full",
    )


def test_legacy_config_is_bootstrapped_once_without_treating_text_preserve_as_dnt(tmp_path) -> None:
    config = _legacy_config(tmp_path)
    repository = ProjectAssetsRepository.from_config(config)

    state = repository.load(config)

    assert state.assets.revision == 1
    assert state.assets.worldbook["setting_summary"] == "A floating city"
    assert [item.source for item in state.assets.glossary] == ["Sky"]
    assert state.assets.do_not_translate == ()
    assert [item["source"] for item in state.analysis_candidates["items"]] == ["Cloud"]
    assert state.analysis_candidates["worldbook_draft"] == {"genre": "Fantasy"}
    assert state.analysis_candidates["character_drafts"][0]["name"] == "Bob"

    config.renpy_workbench_worldbook_data = {"setting_summary": "Changed global setting"}
    reloaded = repository.load(config)
    assert reloaded.assets.worldbook["setting_summary"] == "A floating city"

    persisted = CacheDB(str(tmp_path / "cache" / "cache.db")).get_project()
    assert persisted is not None
    assert persisted.get_project_assets()["revision"] == 1


def test_replace_glossary_confirms_seen_candidate_and_keeps_unseen_candidate(tmp_path) -> None:
    config = _legacy_config(tmp_path)
    config.glossary_data = []
    repository = ProjectAssetsRepository.from_config(config)
    repository.load(config)
    candidates = repository.merge_analysis_terms([
        {"source": "Alice", "target": "", "note": "scan"},
        {"source": "Bob", "target": "鲍勃", "note": "runtime"},
    ])
    alice_id = next(
        item["record_id"] for item in candidates["items"] if item["source"] == "Alice"
    )

    state = repository.replace_glossary(
        [{"src": "Alice", "dst": "爱丽丝", "comment": "confirmed"}],
        enabled = True,
        consumed_candidate_ids = [alice_id],
    )

    assert [(item.origin, item.source, item.target) for item in state.assets.glossary] == [
        ("LOCAL", "Alice", "爱丽丝")
    ]
    assert [item["source"] for item in state.analysis_candidates["items"]] == ["Bob"]


def test_candidate_with_suggested_target_requires_explicit_confirmation(tmp_path) -> None:
    config = _legacy_config(tmp_path)
    config.glossary_data = []
    repository = ProjectAssetsRepository.from_config(config)
    repository.load(config)
    candidates = repository.merge_analysis_terms([
        {"source": "Alice", "target": "爱丽丝", "note": "suggested"},
    ])
    record_id = candidates["items"][0]["record_id"]

    pending = repository.replace_glossary(
        [{
            "record_id": record_id,
            "src": "Alice",
            "dst": "爱丽丝",
            "candidate": True,
            "candidate_confirmed": False,
        }],
        enabled = True,
        consumed_candidate_ids = [record_id],
    )

    assert pending.assets.glossary == ()
    assert pending.analysis_candidates["items"][0]["target"] == "爱丽丝"

    confirmed = repository.replace_glossary(
        [{
            "record_id": record_id,
            "src": "Alice",
            "dst": "爱丽丝",
            "candidate": True,
            "candidate_confirmed": True,
        }],
        enabled = True,
        consumed_candidate_ids = [record_id],
    )

    assert [(term.origin, term.source, term.target) for term in confirmed.assets.glossary] == [
        ("LOCAL", "Alice", "爱丽丝")
    ]
    assert confirmed.analysis_candidates["items"] == []


def test_json_project_only_write_preserves_items_and_run_state(tmp_path) -> None:
    cache_path = tmp_path / "cache"
    cache_path.mkdir()
    project = CacheProject(
        id = "project-1",
        status = Base.TranslationStatus.TRANSLATING,
        extras = {
            "progress": {"line": 4, "total_line": 10},
            "translation_snapshot": {"schema_version": 1, "source_language": "JA"},
        },
    )
    (cache_path / "project.json").write_text(
        json.dumps(project.asdict(), ensure_ascii = False),
        encoding = "utf-8",
    )
    items_path = cache_path / "items.json"
    items_path.write_text('[{"sentinel":true}]', encoding = "utf-8")

    config = _legacy_config(tmp_path, sqlite = False)
    repository = ProjectAssetsRepository.from_config(config)
    state = repository.load(config)
    assets = state.assets.to_dict()
    assets["do_not_translate"] = {
        "enabled": True,
        "items": [{"source": "Ren'Py", "target": ""}],
    }
    repository.save_assets(assets)

    saved = CacheProject.from_dict(
        json.loads((cache_path / "project.json").read_text(encoding = "utf-8"))
    )
    assert saved.get_status() == Base.TranslationStatus.TRANSLATING
    assert saved.get_progress() == {"line": 4, "total_line": 10}
    assert saved.get_translation_snapshot()["source_language"] == "JA"
    assert saved.get_project_assets()["do_not_translate"]["items"][0]["source"] == "Ren'Py"
    assert items_path.read_text(encoding = "utf-8") == '[{"sentinel":true}]'


def test_load_into_config_is_a_transient_project_asset_view(tmp_path) -> None:
    config = _legacy_config(tmp_path)
    repository = ProjectAssetsRepository.from_config(config)
    repository.load(config)
    config.glossary_data = []
    config.renpy_workbench_worldbook_data = {}

    repository.load_into_config(config)

    assert config.glossary_data[0]["src"] == "Sky"
    assert config.renpy_workbench_worldbook_data["setting_summary"] == "A floating city"
    assert config.text_preserve_data == [{"src": "[player]", "comment": "placeholder"}]


def test_existing_sqlite_remains_authoritative_when_setting_is_disabled(tmp_path) -> None:
    cache_path = tmp_path / "cache"
    cache_path.mkdir()
    db_path = cache_path / "cache.db"
    sqlite_project = CacheProject(id = "sqlite-project")
    sqlite_project.set_project_assets({
        "revision": 2,
        "worldbook": {"enabled": True, "data": {"genre": "Mystery"}},
    })
    CacheDB(str(db_path)).set_project(sqlite_project)

    stale_json = CacheProject(id = "json-project")
    json_path = cache_path / "project.json"
    json_path.write_text(json.dumps(stale_json.asdict()), encoding = "utf-8")
    original_json = json_path.read_text(encoding = "utf-8")

    repository = ProjectAssetsRepository(str(tmp_path), cache_use_sqlite = False)
    state = repository.load()
    assets = state.assets.to_dict()
    assets["glossary"] = {
        "enabled": True,
        "items": [{"source": "Door", "target": "门"}],
    }
    repository.save_assets(assets)

    saved = CacheDB(str(db_path)).get_project()
    assert saved is not None
    assert saved.get_id() == "sqlite-project"
    assert saved.get_project_assets()["glossary"]["items"][0]["target"] == "门"
    assert json_path.read_text(encoding = "utf-8") == original_json


def test_analysis_terms_deduplicate_by_nfkc_casefolded_source(tmp_path) -> None:
    repository = ProjectAssetsRepository(str(tmp_path))
    repository.load()

    candidates = repository.merge_analysis_terms([
        {"source": " Alice ", "target": "", "note": "first"},
        {"source": "ＡＬＩＣＥ", "target": "爱丽丝", "note": "latest"},
    ])

    assert len(candidates["items"]) == 1
    assert candidates["items"][0]["origin"] == "ANALYSIS"
    assert candidates["items"][0]["source"] == "Alice"
    assert candidates["items"][0]["target"] == "爱丽丝"
    assert candidates["items"][0]["note"] == "latest"


def test_json_pending_reset_is_recovered_before_asset_read(tmp_path) -> None:
    cache_path = tmp_path / "cache"
    cache_path.mkdir()
    stale = CacheProject(id = "stale")
    (cache_path / "project.json").write_text(
        json.dumps(stale.asdict()),
        encoding = "utf-8",
    )
    (cache_path / "items.json").write_text("[]", encoding = "utf-8")

    recovered = CacheProject(
        id = "recovered",
        status = Base.TranslationStatus.TRANSLATING,
        extras = {
            "progress": {"line": 2, "total_line": 5},
            "project_assets": {
                "revision": 4,
                "worldbook": {"enabled": True, "data": {"genre": "Drama"}},
            },
        },
    )
    journal_path = cache_path / "reset.journal.json"
    journal_path.write_text(
        json.dumps({
            "project": recovered.asdict(),
            "items": [{"src": "restored", "dst": "", "status": "UNTRANSLATED"}],
        }),
        encoding = "utf-8",
    )

    state = ProjectAssetsRepository(
        str(tmp_path),
        cache_use_sqlite = False,
    ).load()

    persisted = CacheProject.from_dict(
        json.loads((cache_path / "project.json").read_text(encoding = "utf-8"))
    )
    assert state.assets.revision == 4
    assert state.assets.worldbook["genre"] == "Drama"
    assert persisted.get_id() == "recovered"
    assert persisted.get_progress() == {"line": 2, "total_line": 5}
    assert json.loads((cache_path / "items.json").read_text(encoding = "utf-8"))[0]["src"] == "restored"
    assert journal_path.exists() is False


def test_explicit_dnt_update_is_project_scoped_and_preserves_other_assets(tmp_path) -> None:
    config = _legacy_config(tmp_path)
    repository = ProjectAssetsRepository.from_config(config)
    before = repository.load(config).assets

    after = repository.replace_do_not_translate(
        [{"src": "Ren'Py", "comment": "product name"}],
        enabled = True,
    )

    assert after.revision == before.revision + 1
    assert after.worldbook == before.worldbook
    assert after.glossary == before.glossary
    assert after.do_not_translate_enabled is True
    assert after.do_not_translate[0].source == "Ren'Py"


def test_live_project_binding_uses_only_initialized_active_output(tmp_path, monkeypatch) -> None:
    disk_project = CacheProject(id = "disk-project")
    disk_project.set_project_assets({
        "revision": 2,
        "worldbook": {"enabled": True, "data": {"source": "disk"}},
    })
    disk_project.set_analysis_candidates({"legacy_config_migrated": True})
    CacheDB(str(tmp_path / "cache" / "cache.db")).set_project(disk_project)

    live_project = CacheProject(id = "live-project")
    live_project.set_project_assets({
        "revision": 3,
        "worldbook": {"enabled": True, "data": {"source": "memory"}},
    })
    live_project.set_analysis_candidates({"legacy_config_migrated": True})
    translator = SimpleNamespace(
        _last_runtime_output_folder = str(tmp_path),
        _active_cache_output_folder = str(tmp_path / "initializing-another-project"),
        cache_manager = SimpleNamespace(get_project = lambda: live_project),
    )
    monkeypatch.setattr(Engine.get(), "translator", translator, raising = False)
    repository = ProjectAssetsRepository(str(tmp_path))

    assert repository.load().assets.worldbook["source"] == "disk"

    translator._active_cache_output_folder = str(tmp_path)
    assert repository.load().assets.worldbook["source"] == "memory"


def test_active_project_is_resolved_while_cache_lock_is_held(tmp_path, monkeypatch) -> None:
    repository = ProjectAssetsRepository(str(tmp_path))
    lock_states: list[bool] = []

    def resolve_active_project() -> None:
        lock_states.append(CacheManager.LOCK._is_owned())
        return None

    monkeypatch.setattr(repository, "_resolve_active_project", resolve_active_project)

    repository.load()
    repository.save_analysis_candidates({"legacy_config_migrated": True})

    assert lock_states == [True, True]
