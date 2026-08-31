from pathlib import Path

from base.Base import Base
from module.Agent.tools.inspection_tools import inspect_translation_project
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheDB import CacheDB
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheProject import CacheProject
from module.Config import Config


def _config_for(root: Path) -> Config:
    config = Config()
    config.renpy_project_path = str(root)
    config.renpy_game_folder = str(root)
    config.renpy_tl_folder = str(root / "game" / "tl" / "chinese")
    config.input_folder = config.renpy_tl_folder
    config.output_folder = str(root / "RenpyBox_Translation" / "chinese")
    return config


def _save_cache(
    config: Config,
    items: list[CacheItem],
    *,
    status: Base.TranslationStatus,
    progress: dict | None = None,
    assets: dict | None = None,
    candidates: dict | None = None,
) -> None:
    project = CacheProject(status=status)
    project.set_progress(progress or {})
    if assets is not None:
        project.set_project_assets(assets)
    if candidates is not None:
        project.set_analysis_candidates(candidates)
    manager = CacheManager(service=False)
    manager.cache_use_sqlite = False
    manager.save_to_file(
        project,
        items,
        config.output_folder,
        strict=True,
    )


def test_project_inspection_requires_current_project(tmp_path) -> None:
    config = Config()
    config.renpy_project_path = ""
    config.renpy_game_folder = ""
    config.renpy_tl_folder = ""
    config.input_folder = ""
    config.output_folder = ""

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is False
    assert result.code == "PROJECT_NOT_SET"


def test_project_inspection_recommends_unpack_for_rpa_only(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "archive.rpa").write_bytes(b"rpa")
    config = _config_for(root)

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["files"] == {
        "status": "need_unpack",
        "rpa_state": "required",
        "unpack_required": True,
        "rpa_count": 1,
        "rpy_count": 0,
        "rpyc_count": 0,
        "tl_file_count": 0,
    }
    assert result.data["next_action_code"] == "UNPACK_RPA"
    assert result.data["cache"]["exists"] is False


def test_project_inspection_does_not_treat_tl_patch_as_source_script(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    tl_dir = game / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    (game / "archive.rpa").write_bytes(b"rpa")
    (tl_dir / "replace_text_auto.rpy").write_text(
        "init python:\n    pass\n",
        encoding="utf-8",
    )
    config = _config_for(root)

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["files"]["rpy_count"] == 0
    assert result.data["files"]["tl_file_count"] == 1
    assert result.data["next_action_code"] == "UNPACK_RPA"


def test_project_inspection_recommends_decompile_for_rpyc_only(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpyc").write_bytes(b"rpyc")
    config = _config_for(root)

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["files"]["status"] == "need_decompile"
    assert result.data["next_action_code"] == "DECOMPILE_SCRIPTS"


def test_project_inspection_decompiles_when_archive_is_retained(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "archive.rpa").write_bytes(b"rpa")
    (game / "script.rpyc").write_bytes(b"rpyc")
    config = _config_for(root)

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["files"]["status"] == "need_decompile"
    assert result.data["next_action_code"] == "DECOMPILE_SCRIPTS"


def test_project_inspection_recommends_translation_for_ready_scripts(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["files"]["status"] == "ready"
    assert result.data["next_action_code"] == "START_TRANSLATION"


def test_project_inspection_does_not_repeat_unpack_when_rpy_is_available(
    tmp_path,
) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "archive.rpa").write_bytes(b"rpa")
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["files"]["status"] == "ready"
    assert result.data["files"]["rpa_state"] == "scripts_present"
    assert result.data["files"]["unpack_required"] is False
    assert result.data["next_action_code"] == "START_TRANSLATION"


def test_project_inspection_decompiles_mixed_scripts(
    tmp_path,
) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "archive.rpa").write_bytes(b"rpa")
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    (game / "script.rpyc").write_bytes(b"rpyc")
    config = _config_for(root)

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["files"]["status"] == "need_decompile"
    assert result.data["files"]["rpa_state"] == "scripts_present"
    assert result.data["files"]["unpack_required"] is False
    assert result.data["next_action_code"] == "DECOMPILE_SCRIPTS"


def test_project_inspection_prioritizes_unapplied_workbench_drafts(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)
    _save_cache(
        config,
        [],
        status=Base.TranslationStatus.UNTRANSLATED,
        candidates={
            "schema_version": 1,
            "worldbook_draft": {"summary": "世界观草稿"},
            "character_drafts": [{"name": "Alice"}],
            "items": [],
        },
    )

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["assets"]["has_effective_assets"] is False
    assert result.data["assets"]["has_drafts"] is True
    assert result.data["assets"]["character_draft_count"] == 1
    assert result.data["next_action_code"] == "REVIEW_WORKBENCH"


def test_project_inspection_ignores_empty_worldbook_draft_fields(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)
    _save_cache(
        config,
        [],
        status=Base.TranslationStatus.UNTRANSLATED,
        candidates={
            "schema_version": 1,
            "worldbook_draft": {
                "summary": "",
                "setting": "",
                "tone": "",
                "narrative_rules": "",
                "format_rules": "",
                "spoiler_notes": "",
            },
            "character_drafts": [],
            "items": [],
        },
    )

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["assets"]["has_drafts"] is False
    assert result.data["next_action_code"] == "START_TRANSLATION"


def test_project_inspection_reports_partial_translation_cache(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)
    items = [
        CacheItem(
            src="Hello",
            dst="你好",
            status=Base.TranslationStatus.TRANSLATED,
        ),
        CacheItem(src="World", status=Base.TranslationStatus.UNTRANSLATED),
    ]
    _save_cache(
        config,
        items,
        status=Base.TranslationStatus.TRANSLATING,
        progress={"line": 1, "total_line": 2},
    )

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["cache"]["item_count"] == 2
    assert result.data["cache"]["completed_count"] == 1
    assert result.data["cache"]["untranslated_count"] == 1
    assert result.data["cache"]["progress"] == {"line": 1, "total_line": 2}
    assert result.data["next_action_code"] == "CONTINUE_TRANSLATION"


def test_project_inspection_attributes_quality_and_caps_samples(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)
    items = []
    for index in range(8):
        items.append(
            CacheItem(
                src=f"Source {index}",
                file_path="game/script.rpy",
                row=index + 1,
                status=Base.TranslationStatus.EXCLUDED,
                retry_count=1,
                metadata={
                    "translation_retry": {
                        "schema_version": 1,
                        "attempt": 1,
                        "reasons": [
                            {"code": "PLACEHOLDER_MISMATCH", "line_indices": [0]}
                        ],
                    }
                },
            )
        )
    _save_cache(
        config,
        items,
        status=Base.TranslationStatus.TRANSLATED,
        progress={"failed_line_count": 8, "total_line": 8, "line": 8},
    )

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["quality"]["failed_count"] == 8
    assert result.data["quality"]["error_type_counts"] == {
        "PLACEHOLDER_MISMATCH": 8
    }
    assert len(result.data["quality"]["samples"]) == 5
    assert result.data["next_action_code"] == "REVIEW_QUALITY"
    assert '"next_action_code": "REVIEW_QUALITY"' in result.model_message()


def test_project_inspection_continues_failed_untranslated_items_before_review(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)
    _save_cache(
        config,
        [
            CacheItem(
                src="Source",
                status=Base.TranslationStatus.UNTRANSLATED,
                retry_count=1,
                metadata={
                    "translation_retry": {
                        "schema_version": 1,
                        "attempt": 1,
                        "reasons": [
                            {"code": "PLACEHOLDER_MISMATCH", "line_indices": [0]}
                        ],
                    }
                },
            )
        ],
        status=Base.TranslationStatus.TRANSLATING,
        progress={"failed_line_count": 1, "total_line": 2, "line": 1},
    )

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["quality"]["failed_count"] == 1
    assert result.data["cache"]["untranslated_count"] == 1
    assert result.data["next_action_code"] == "CONTINUE_TRANSLATION"


def test_project_inspection_recommends_review_after_clean_completion(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)
    _save_cache(
        config,
        [
            CacheItem(
                src="Hello",
                dst="你好",
                status=Base.TranslationStatus.POLISHED,
            )
        ],
        status=Base.TranslationStatus.TRANSLATED,
        progress={"line": 1, "total_line": 1},
    )

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["cache"]["completed_count"] == 1
    assert result.data["next_action_code"] == "REVIEW_TRANSLATION"


def test_project_inspection_recognizes_applied_old_new_without_cache(tmp_path) -> None:
    root = tmp_path / "Game"
    tl_dir = root / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    tl_dir.joinpath("strings.rpy").write_text(
        'translate chinese strings:\n\n'
        '    # renpybox: replace-only\n'
        '    old "Choice"\n'
        '    new "选项"\n',
        encoding="utf-8",
    )
    config = _config_for(root)

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["old_new"]["effective_count"] == 1
    assert result.data["old_new"]["needs_refresh"] is True
    assert result.data["next_action_code"] == "REFRESH_REPLACE_FALLBACK"


def test_project_inspection_reports_corrupt_cache_without_rewriting_it(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)
    cache_dir = Path(config.output_folder) / "cache"
    cache_dir.mkdir(parents=True)
    items_path = cache_dir / "items.json"
    items_path.write_text("not-json", encoding="utf-8")

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["cache"]["exists"] is True
    assert result.data["cache"]["readable"] is False
    assert result.data["cache"]["error_code"] == "CACHE_UNREADABLE"
    assert result.data["next_action_code"] == "REPAIR_CACHE"
    assert items_path.read_text(encoding="utf-8") == "not-json"


def test_project_inspection_does_not_hide_incomplete_json_with_asset_database(
    tmp_path,
) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)
    cache_dir = Path(config.output_folder) / "cache"
    database = cache_dir / CacheManager.CACHE_DB_NAME
    cache_dir.mkdir(parents=True)
    CacheDB(str(database)).set_project(CacheProject())
    items_path = cache_dir / "items.json"
    items_path.write_text("[]", encoding="utf-8")

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["cache"]["exists"] is True
    assert result.data["cache"]["readable"] is False
    assert result.data["cache"]["error_code"] == "CACHE_UNREADABLE"
    assert result.data["next_action_code"] == "REPAIR_CACHE"
    assert items_path.read_text(encoding="utf-8") == "[]"


def test_project_inspection_reads_sqlite_without_touching_cache_files(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)
    cache_dir = Path(config.output_folder) / "cache"
    database = cache_dir / CacheManager.CACHE_DB_NAME
    cache_dir.mkdir(parents=True)
    CacheDB(str(database)).set_translation_cache(
        CacheProject(status=Base.TranslationStatus.TRANSLATED),
        [
            CacheItem(
                src="Hello",
                dst="你好",
                status=Base.TranslationStatus.TRANSLATED,
            )
        ],
    )
    before_names = sorted(item.name for item in cache_dir.iterdir())
    before_bytes = database.read_bytes()
    before_mtime = database.stat().st_mtime_ns

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["cache"]["readable"] is True
    assert result.data["cache"]["completed_count"] == 1
    assert sorted(item.name for item in cache_dir.iterdir()) == before_names
    assert database.read_bytes() == before_bytes
    assert database.stat().st_mtime_ns == before_mtime


def test_project_inspection_does_not_ignore_pending_sqlite_wal(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)
    cache_dir = Path(config.output_folder) / "cache"
    database = cache_dir / CacheManager.CACHE_DB_NAME
    _save_cache(
        config,
        [],
        status=Base.TranslationStatus.TRANSLATED,
    )
    CacheDB(str(database)).set_translation_cache(
        CacheProject(status=Base.TranslationStatus.TRANSLATED),
        [],
    )
    wal_path = database.with_name(f"{database.name}-wal")
    wal_path.write_bytes(b"pending")

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["cache"]["readable"] is False
    assert result.data["cache"]["error_code"] == "CACHE_UNREADABLE"
    assert result.data["next_action_code"] == "REPAIR_CACHE"
    assert wal_path.read_bytes() == b"pending"


def test_project_inspection_rejects_configured_output_from_other_language(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)
    japanese_output = root / "RenpyBox_Translation" / "japanese" / "run"
    config.output_folder = str(japanese_output)
    _save_cache(
        config,
        [
            CacheItem(
                src="Japanese sentinel",
                dst="別言語",
                status=Base.TranslationStatus.TRANSLATED,
            )
        ],
        status=Base.TranslationStatus.TRANSLATED,
    )

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["cache"]["exists"] is False
    assert result.data["cache"]["item_count"] == 0
    assert result.data["next_action_code"] == "START_TRANSLATION"


def test_project_inspection_reads_old_new_from_custom_tl_root(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    custom_tl = root / "tl" / "chinese"
    custom_tl.mkdir(parents=True)
    custom_tl.joinpath("strings.rpy").write_text(
        'translate chinese strings:\n\n'
        '    # renpybox: replace-only\n'
        '    old "Choice"\n'
        '    new "选项"\n',
        encoding="utf-8",
    )
    from module.Extract.ReplaceGenerator import write_replace_script

    write_replace_script(
        custom_tl / "replace_text_auto.rpy",
        [("Choice", "选项")],
        language="chinese",
        use_translate_python=True,
        wrap_existing=True,
    )
    config = _config_for(root)
    config.renpy_tl_folder = str(custom_tl)
    config.input_folder = str(custom_tl)

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["old_new"]["effective_count"] == 1
    assert result.data["old_new"]["hook_exists"] is True
    assert result.data["old_new"]["hook_matches"] is True
    assert result.data["old_new"]["needs_refresh"] is False
    assert result.data["next_action_code"] == "REVIEW_TRANSLATION"


def test_project_inspection_refreshes_stale_replace_compiled_cache(tmp_path) -> None:
    root = tmp_path / "Game"
    tl_dir = root / "game" / "tl" / "chinese"
    tl_dir.mkdir(parents=True)
    tl_dir.joinpath("strings.rpy").write_text(
        'translate chinese strings:\n\n'
        '    # renpybox: replace-only\n'
        '    old "Choice"\n'
        '    new "选项"\n',
        encoding="utf-8",
    )
    from module.Extract.ReplaceGenerator import write_replace_script

    hook = write_replace_script(
        tl_dir / "replace_text_auto.rpy",
        [("Choice", "选项")],
        language="chinese",
        use_translate_python=True,
        wrap_existing=True,
    )
    hook.with_suffix(".rpyc").write_bytes(b"stale")

    result = inspect_translation_project(config_loader=lambda: _config_for(root))

    assert result.data["old_new"]["hook_matches"] is True
    assert result.data["old_new"]["compiled_cache_exists"] is True
    assert result.data["old_new"]["needs_refresh"] is True
    assert result.data["next_action_code"] == "REFRESH_REPLACE_FALLBACK"


def test_project_inspection_prefers_incremental_cache_over_asset_only_database(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)
    main_output = Path(config.output_folder)
    main_database = main_output / "cache" / CacheManager.CACHE_DB_NAME
    main_database.parent.mkdir(parents=True)
    CacheDB(str(main_database)).set_project(CacheProject())

    incremental_output = main_output.parent / "chinese_new"
    config.output_folder = str(incremental_output)
    _save_cache(
        config,
        [
            CacheItem(
                src="Pending",
                status=Base.TranslationStatus.UNTRANSLATED,
            )
        ],
        status=Base.TranslationStatus.TRANSLATING,
    )
    config.output_folder = str(main_output)

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert Path(result.data["cache"]["output_path"]) == incremental_output
    assert result.data["cache"]["item_count"] == 1
    assert result.data["next_action_code"] == "CONTINUE_TRANSLATION"


def test_project_inspection_does_not_hide_corrupt_main_assets_with_delta_cache(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)
    main_output = Path(config.output_folder)
    main_project = main_output / "cache" / "project.json"
    main_project.parent.mkdir(parents=True)
    main_project.write_text("not-json", encoding="utf-8")

    incremental_output = main_output.parent / "chinese_new"
    config.output_folder = str(incremental_output)
    _save_cache(
        config,
        [
            CacheItem(
                src="Pending",
                status=Base.TranslationStatus.UNTRANSLATED,
            )
        ],
        status=Base.TranslationStatus.TRANSLATING,
    )
    config.output_folder = str(main_output)

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert result.data["cache"]["item_count"] == 1
    assert result.data["assets"]["readable"] is False
    assert result.data["assets"]["error_code"] == "ASSET_CACHE_UNREADABLE"
    assert result.data["next_action_code"] == "REPAIR_CACHE"


def test_project_inspection_reports_pending_main_asset_transaction(tmp_path) -> None:
    root = tmp_path / "Game"
    game = root / "game"
    game.mkdir(parents=True)
    (game / "script.rpy").write_text("label start:\n    return\n", encoding="utf-8")
    config = _config_for(root)
    main_output = Path(config.output_folder)
    main_project = main_output / "cache" / "project.json"
    main_project.parent.mkdir(parents=True)
    main_project.write_text("{}", encoding="utf-8")
    journal = main_project.parent / CacheManager.RESET_JOURNAL_NAME
    journal.write_text("{}", encoding="utf-8")

    incremental_output = main_output.parent / "chinese_new"
    config.output_folder = str(incremental_output)
    _save_cache(
        config,
        [
            CacheItem(
                src="Pending",
                status=Base.TranslationStatus.UNTRANSLATED,
            )
        ],
        status=Base.TranslationStatus.TRANSLATING,
    )

    result = inspect_translation_project(config_loader=lambda: config)

    assert result.success is True
    assert Path(result.data["cache"]["output_path"]) == incremental_output
    assert result.data["cache"]["item_count"] == 1
    assert result.data["assets"]["readable"] is False
    assert result.data["assets"]["error_code"] == "ASSET_CACHE_UNREADABLE"
    assert result.data["next_action_code"] == "REPAIR_CACHE"
