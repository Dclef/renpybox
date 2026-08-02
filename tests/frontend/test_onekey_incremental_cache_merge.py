import hashlib
from pathlib import Path

import pytest

from base.Base import Base
from frontend.RenpyToolbox.OneKeyTranslatePage import (
    apply_translation_files_transactionally,
    merge_incremental_translation_cache,
    preserve_incremental_translation_cache,
)
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheProject import CacheProject


def _save_json_cache(output, project, items) -> None:
    """用确定性的 JSON 后端准备主/增量缓存。"""
    manager = CacheManager(service = False)
    manager.cache_use_sqlite = False
    assert manager.save_to_file(
        project,
        items,
        str(output),
        strict = True,
    )


def _item(*, row: int, src: str, dst: str, tag: str = "dialogue") -> CacheItem:
    return CacheItem(
        file_path = "script.rpy",
        row = row,
        src = src,
        dst = dst,
        tag = tag,
        status = Base.TranslationStatus.TRANSLATED,
    )


def _ast_item(
    *,
    row: int,
    src: str,
    dst: str,
    digest: str,
    template_line: int = 43,
    label: str = "fictional_scene_12345678",
) -> CacheItem:
    item = _item(row=row, src=src, dst=dst)
    item.set_extra_field({
        "renpy": {
            "block": {
                "lang": "chinese",
                "label": label,
                "kind": "LABEL",
                "header_line": 40,
            },
            "pair": {"template_line": template_line, "target_line": row},
            "digest": {"template_raw_sha1": digest},
        }
    })
    return item


def _strings_ast_item(
    *,
    row: int,
    header_line: int,
    src: str,
    dst: str,
    digest: str,
    file_path: str = "script.rpy",
) -> CacheItem:
    item = _item(row=row, src=src, dst=dst, tag="string")
    item.set_file_path(file_path)
    item.set_extra_field({
        "renpy": {
            "block": {
                "lang": "chinese",
                "label": "strings",
                "kind": "STRINGS",
                "header_line": header_line,
            },
            "pair": {
                "template_line": header_line + 2,
                "target_line": header_line + 3,
            },
            "digest": {"template_raw_sha1": digest},
        }
    })
    return item


def test_merge_incremental_cache_overrides_duplicates_and_preserves_main_assets(tmp_path):
    main_output = tmp_path / "RenpyBox_Translation" / "chinese"
    incremental_output = tmp_path / "RenpyBox_Translation" / "chinese_new"

    main_project = CacheProject(id = "main-project")
    main_project.set_project_assets({
        "revision": 7,
        "worldbook": {
            "enabled": True,
            "data": {"setting": "蒸汽都市"},
        },
        "glossary": {
            "enabled": True,
            "items": [{"source": "Alice", "target": "爱丽丝"}],
        },
    })
    main_project.set_analysis_candidates({
        "items": [{"source": "Alice", "kind": "character"}],
    })
    main_items = [
        _item(row = 1, src = "Main only", dst = "主缓存独有"),
        _item(row = 2, src = "Shared", dst = "旧译文"),
    ]
    _save_json_cache(main_output, main_project, main_items)

    # 增量缓存的项目资产为空；合并后必须继续保留主缓存中的工作台数据。
    incremental_project = CacheProject(id = "incremental-project")
    incremental_items = [
        _item(row = 2, src = "Shared", dst = "增量新译文"),
        _item(row = 3, src = "Incremental only", dst = "增量独有"),
    ]
    _save_json_cache(incremental_output, incremental_project, incremental_items)

    assert merge_incremental_translation_cache(incremental_output, main_output) is True

    # 模拟校对页的严格载入边界，确保合并结果不是只写了一半的缓存。
    loaded = CacheManager(service = False)
    loaded.load_from_file(str(main_output), strict = True)
    items_by_row = {item.get_row(): item for item in loaded.get_items()}

    assert sorted(items_by_row) == [1, 2, 3]
    assert items_by_row[1].get_dst() == "主缓存独有"
    assert items_by_row[2].get_dst() == "增量新译文"
    assert items_by_row[3].get_dst() == "增量独有"

    assets = loaded.get_project().get_project_assets()
    assert assets["revision"] == 7
    assert assets["worldbook"]["data"] == {"setting": "蒸汽都市"}
    glossary_item = assets["glossary"]["items"][0]
    assert glossary_item["source"] == "Alice"
    assert glossary_item["target"] == "爱丽丝"
    assert loaded.get_project().get_analysis_candidates()["items"] == [
        {"source": "Alice", "kind": "character"},
    ]


def test_merge_incremental_cache_keeps_newer_main_workbench_assets(tmp_path):
    """增量任务较早启动时，不能用旧角色卡/世界观覆盖主缓存。"""
    main_output = tmp_path / "RenpyBox_Translation" / "chinese"
    incremental_output = tmp_path / "RenpyBox_Translation" / "chinese_new"

    main_project = CacheProject(id = "main-project")
    main_project.set_project_assets({
        "revision": 9,
        "character_cards": {
            "enabled": True,
            "items": [{"name": "Alice", "name_translation": "新爱丽丝"}],
        },
        "worldbook": {
            "enabled": True,
            "data": {"setting": "更新后的世界观"},
        },
    })
    _save_json_cache(main_output, main_project, [_item(row = 1, src = "主条目", dst = "主译文")])

    incremental_project = CacheProject(id = "incremental-project")
    incremental_project.set_project_assets({
        "revision": 4,
        "character_cards": {
            "enabled": True,
            "items": [{"name": "Alice", "name_translation": "旧爱丽丝"}],
        },
        "worldbook": {
            "enabled": True,
            "data": {"setting": "旧世界观"},
        },
    })
    _save_json_cache(
        incremental_output,
        incremental_project,
        [_item(row = 2, src = "增量条目", dst = "增量译文")],
    )

    assert merge_incremental_translation_cache(incremental_output, main_output) is True

    loaded = CacheManager(service = False)
    loaded.load_from_file(str(main_output), strict = True)
    assets = loaded.get_project().get_project_assets()
    assert assets["revision"] == 9
    assert assets["worldbook"]["data"]["setting"] == "更新后的世界观"
    assert assets["character_cards"]["items"][0]["name_translation"] == "新爱丽丝"


def test_merge_incremental_cache_prefers_main_assets_when_legacy_revisions_match(tmp_path):
    main_output = tmp_path / "RenpyBox_Translation" / "chinese"
    incremental_output = tmp_path / "RenpyBox_Translation" / "chinese_new"

    main_project = CacheProject(id = "main-project")
    main_project.set_project_assets({
        "revision": 0,
        "worldbook": {"enabled": True, "data": {"setting": "稳定世界观"}},
    })
    incremental_project = CacheProject(id = "incremental-project")
    incremental_project.set_project_assets({
        "revision": 0,
        "worldbook": {"enabled": True, "data": {"setting": "旧运行快照"}},
    })
    item = _item(row = 1, src = "Line", dst = "译文")
    _save_json_cache(main_output, main_project, [item])
    _save_json_cache(incremental_output, incremental_project, [item])

    assert merge_incremental_translation_cache(incremental_output, main_output) is True

    loaded = CacheManager(service = False)
    loaded.load_from_file(str(main_output), strict = True)
    assert loaded.get_project().get_project_assets()["worldbook"]["data"]["setting"] == "稳定世界观"


def test_reextract_preserves_previous_incremental_output(tmp_path):
    output = tmp_path / "RenpyBox_Translation" / "chinese_new"
    output.mkdir(parents = True)
    (output / "cache").mkdir()
    (output / "cache" / "items.json").write_text("[]", encoding = "utf-8")
    (output / "unfinished-note.txt").write_text("待应用译文", encoding = "utf-8")

    backup = preserve_incremental_translation_cache(output, stamp = "fixed")

    assert backup == output.parent / "chinese_new.backup-fixed"
    assert not output.exists()
    assert (backup / "unfinished-note.txt").read_text(encoding = "utf-8") == "待应用译文"


def test_reextract_backup_name_does_not_overwrite_previous_backup(tmp_path):
    parent = tmp_path / "RenpyBox_Translation"
    output = parent / "chinese_new"
    old_backup = parent / "chinese_new.backup-fixed"
    old_backup.mkdir(parents = True)
    (old_backup / "keep.txt").write_text("old", encoding = "utf-8")
    output.mkdir()

    backup = preserve_incremental_translation_cache(output, stamp = "fixed")

    assert backup == parent / "chinese_new.backup-fixed-1"
    assert (old_backup / "keep.txt").read_text(encoding = "utf-8") == "old"


def test_cache_merge_uses_ast_identity_across_file_line_shifts(tmp_path):
    main_output = tmp_path / "cache" / "main"
    incremental_output = tmp_path / "cache" / "delta"
    main_item = _ast_item(
        row=44,
        src="The copper moon is rising.",
        dst="旧译文",
        digest="stable-template",
    )
    shifted_item = _ast_item(
        row=144,
        src="The copper moon is rising.",
        dst="铜色月亮正在升起。",
        digest="stable-template",
    )
    _save_json_cache(main_output, CacheProject(id="main"), [main_item])
    _save_json_cache(incremental_output, CacheProject(id="delta"), [shifted_item])

    assert merge_incremental_translation_cache(incremental_output, main_output) is True
    loaded = CacheManager(service=False)
    loaded.load_from_file(str(main_output), strict=True)
    assert len(loaded.get_items()) == 1
    assert loaded.get_items()[0].get_dst() == "铜色月亮正在升起。"


def test_cache_merge_replaces_changed_source_at_same_ast_location(tmp_path):
    main_output = tmp_path / "cache" / "main"
    incremental_output = tmp_path / "cache" / "delta"
    old_item = _ast_item(
        row=44,
        src="The glass comet is dim.",
        dst="玻璃彗星很暗。",
        digest="old-template",
    )
    changed_item = _ast_item(
        row=44,
        src="The glass comet is brilliant.",
        dst="玻璃彗星十分明亮。",
        digest="new-template",
    )
    _save_json_cache(main_output, CacheProject(id="main"), [old_item])
    _save_json_cache(incremental_output, CacheProject(id="delta"), [changed_item])

    assert merge_incremental_translation_cache(incremental_output, main_output) is True
    loaded = CacheManager(service=False)
    loaded.load_from_file(str(main_output), strict=True)
    items = loaded.get_items()
    assert len(items) == 1
    assert items[0].get_src() == "The glass comet is brilliant."
    assert items[0].get_dst() == "玻璃彗星十分明亮。"


def test_cache_merge_removes_vanished_items_from_changed_numbered_block(tmp_path):
    main_output = tmp_path / "cache" / "main"
    incremental_output = tmp_path / "cache" / "delta"
    label = "fictional_relay_87654321"
    main_items = [
        _ast_item(
            row=44,
            src="The fictional relay opens.",
            dst="虚构中继器打开了。",
            digest="relay-open",
            template_line=43,
            label=label,
        ),
        _ast_item(
            row=46,
            src="The fictional relay hums.",
            dst="虚构中继器发出嗡鸣。",
            digest="relay-hum",
            template_line=45,
            label=label,
        ),
        _ast_item(
            row=48,
            src="The fictional relay closes.",
            dst="虚构中继器关闭了。",
            digest="relay-close",
            template_line=47,
            label=label,
        ),
    ]
    incremental_items = [
        _ast_item(
            row=44,
            src="The fictional relay opens.",
            dst="新的虚构中继器打开译文。",
            digest="relay-open",
            template_line=43,
            label=label,
        ),
        _ast_item(
            row=46,
            src="The fictional relay closes.",
            dst="新的虚构中继器关闭译文。",
            digest="relay-close",
            template_line=45,
            label=label,
        ),
    ]
    _save_json_cache(main_output, CacheProject(id="main"), main_items)
    _save_json_cache(incremental_output, CacheProject(id="delta"), incremental_items)

    assert merge_incremental_translation_cache(incremental_output, main_output) is True
    loaded = CacheManager(service=False)
    loaded.load_from_file(str(main_output), strict=True)
    items = loaded.get_items()

    assert [item.get_src() for item in items] == [
        "The fictional relay opens.",
        "The fictional relay closes.",
    ]
    assert [item.get_dst() for item in items] == [
        "新的虚构中继器打开译文。",
        "新的虚构中继器关闭译文。",
    ]


def test_cache_merge_preserves_newer_main_translation_in_numbered_block(tmp_path):
    main_output = tmp_path / "cache" / "main"
    incremental_output = tmp_path / "cache" / "delta"
    label = "fictional_lantern_24681357"
    template_line = '    # pilot "The fictional lantern glows."'
    digest = hashlib.sha1(template_line.encode("utf-8")).hexdigest()
    proofread = _ast_item(
        row=44,
        src="The fictional lantern glows.",
        dst="人工校对后的虚构灯笼译文。",
        digest=digest,
        template_line=43,
        label=label,
    )
    vanished = _ast_item(
        row=46,
        src="The fictional lantern flickers.",
        dst="即将被删除的虚构译文。",
        digest="lantern-flickers",
        template_line=45,
        label=label,
    )
    stale_incremental = _ast_item(
        row=144,
        src="The fictional lantern glows.",
        dst="较早增量任务中的虚构灯笼译文。",
        digest=digest,
        template_line=43,
        label=label,
    )
    _save_json_cache(main_output, CacheProject(id="main"), [proofread, vanished])
    _save_json_cache(
        incremental_output,
        CacheProject(id="delta"),
        [stale_incremental],
    )
    (main_output / "script.rpy").write_text(
        'translate chinese fictional_lantern_24681357:\n\n\n'
        f'{template_line}\n'
        '    pilot "人工校对后的虚构灯笼译文。"\n',
        encoding="utf-8",
    )

    assert merge_incremental_translation_cache(incremental_output, main_output) is True
    loaded = CacheManager(service=False)
    loaded.load_from_file(str(main_output), strict=True)
    items = loaded.get_items()

    assert len(items) == 1
    assert items[0].get_src() == "The fictional lantern glows."
    assert items[0].get_dst() == "人工校对后的虚构灯笼译文。"


def test_cache_merge_does_not_evict_another_strings_block_at_same_offset(tmp_path):
    main_output = tmp_path / "cache" / "main"
    incremental_output = tmp_path / "cache" / "delta"
    first_old = _strings_ast_item(
        row=12,
        header_line=10,
        src="The fictional north lens is dim.",
        dst="虚构的北侧镜片很暗。",
        digest="north-old-template",
    )
    second_kept = _strings_ast_item(
        row=22,
        header_line=20,
        src="The fictional south lens is clear.",
        dst="虚构的南侧镜片很清晰。",
        digest="south-template",
    )
    first_changed = _strings_ast_item(
        row=12,
        header_line=10,
        src="The fictional north lens is bright.",
        dst="虚构的北侧镜片很明亮。",
        digest="north-new-template",
    )
    _save_json_cache(
        main_output,
        CacheProject(id="main"),
        [first_old, second_kept],
    )
    _save_json_cache(
        incremental_output,
        CacheProject(id="delta"),
        [first_changed],
    )

    assert merge_incremental_translation_cache(incremental_output, main_output) is True
    loaded = CacheManager(service=False)
    loaded.load_from_file(str(main_output), strict=True)
    items_by_src = {item.get_src(): item for item in loaded.get_items()}

    assert "The fictional north lens is dim." in items_by_src
    assert "The fictional north lens is bright." in items_by_src
    assert items_by_src["The fictional south lens is clear."].get_dst() == (
        "虚构的南侧镜片很清晰。"
    )


def test_cache_merge_uses_global_strings_identity_and_keeps_main_location(tmp_path):
    main_output = tmp_path / "cache" / "main"
    incremental_output = tmp_path / "cache" / "delta"
    original = "Align the fictional telescope"
    main_placeholder = _strings_ast_item(
        row=12,
        header_line=10,
        src=original,
        dst=original,
        digest="main-placeholder-template",
        file_path="menus/telescope.rpy",
    )
    incremental_translation = _strings_ast_item(
        row=32,
        header_line=30,
        src=original,
        dst="校准虚构望远镜",
        digest="incremental-translated-template",
        file_path="updates/night.rpy",
    )
    _save_json_cache(
        main_output,
        CacheProject(id="main"),
        [main_placeholder],
    )
    _save_json_cache(
        incremental_output,
        CacheProject(id="delta"),
        [incremental_translation],
    )

    assert merge_incremental_translation_cache(incremental_output, main_output) is True
    loaded = CacheManager(service=False)
    loaded.load_from_file(str(main_output), strict=True)
    items = loaded.get_items()

    assert len(items) == 1
    assert items[0].get_src() == original
    assert items[0].get_dst() == "校准虚构望远镜"
    assert items[0].get_file_path() == "menus/telescope.rpy"


def test_cache_merge_preserves_proofread_main_strings_translation(tmp_path):
    main_output = tmp_path / "cache" / "main"
    incremental_output = tmp_path / "cache" / "delta"
    original = "Polish the fictional moon compass"
    proofread_main = _strings_ast_item(
        row=18,
        header_line=16,
        src=original,
        dst="润色后的虚构月光罗盘译文",
        digest="proofread-main-template",
        file_path="menus/moon_compass.rpy",
    )
    stale_incremental = _strings_ast_item(
        row=48,
        header_line=46,
        src=original,
        dst="较早的虚构月光罗盘译文",
        digest="stale-incremental-template",
        file_path="updates/moon_compass.rpy",
    )
    _save_json_cache(main_output, CacheProject(id="main"), [proofread_main])
    _save_json_cache(
        incremental_output,
        CacheProject(id="delta"),
        [stale_incremental],
    )

    assert merge_incremental_translation_cache(incremental_output, main_output) is True
    loaded = CacheManager(service=False)
    loaded.load_from_file(str(main_output), strict=True)
    items = loaded.get_items()

    assert len(items) == 1
    assert items[0].get_src() == original
    assert items[0].get_dst() == "润色后的虚构月光罗盘译文"
    assert items[0].get_file_path() == "menus/moon_compass.rpy"


def test_cache_merge_json_fallback_invalidates_stale_sqlite(tmp_path, monkeypatch):
    main_output = tmp_path / "cache" / "main"
    incremental_output = tmp_path / "cache" / "delta"
    main_item = _item(
        row=1,
        src="Existing fictional sextant",
        dst="已有虚构六分仪译文",
    )
    incremental_item = _item(
        row=2,
        src="New fictional sextant",
        dst="新增虚构六分仪译文",
    )

    main_manager = CacheManager(service=False)
    main_manager.cache_use_sqlite = True
    assert main_manager.save_to_file(
        CacheProject(id="main"), [main_item], str(main_output), strict=True
    )
    _save_json_cache(
        incremental_output,
        CacheProject(id="delta"),
        [incremental_item],
    )
    stale_db = main_output / "cache" / CacheManager.CACHE_DB_NAME
    assert stale_db.is_file()

    real_save = CacheManager.save_to_file
    failed_sqlite_once = False

    def fail_first_main_sqlite_save(
        manager, project, items, output_folder, *, strict=False
    ):
        nonlocal failed_sqlite_once
        if (
            Path(output_folder) == main_output
            and manager._should_use_sqlite(output_folder)
            and not failed_sqlite_once
        ):
            failed_sqlite_once = True
            return False
        return real_save(
            manager, project, items, output_folder, strict=strict
        )

    monkeypatch.setattr(CacheManager, "save_to_file", fail_first_main_sqlite_save)

    assert merge_incremental_translation_cache(incremental_output, main_output) is True
    assert failed_sqlite_once is True
    assert not stale_db.exists()

    fresh_manager = CacheManager(service=False)
    fresh_manager.load_from_file(str(main_output), strict=True)
    assert {item.get_src() for item in fresh_manager.get_items()} == {
        "Existing fictional sextant",
        "New fictional sextant",
    }


def test_full_apply_rolls_back_all_files_when_later_copy_fails(tmp_path, monkeypatch):
    output = tmp_path / "output"
    target = tmp_path / "target"
    output.mkdir()
    target.mkdir()
    first_source = output / "first.rpy"
    second_source = output / "second.rpy"
    first_target = target / "first.rpy"
    second_target = target / "second.rpy"
    first_source.write_text("new nebula\n", encoding="utf-8")
    second_source.write_text("new aurora\n", encoding="utf-8")
    first_target.write_text("old nebula\n", encoding="utf-8")
    second_target.write_text("old aurora\n", encoding="utf-8")

    import shutil as real_shutil

    real_copy2 = real_shutil.copy2

    def fail_second_source(src, dst, *args, **kwargs):
        if Path(src).resolve() == second_source.resolve():
            raise OSError("fictional disk interruption")
        return real_copy2(src, dst, *args, **kwargs)

    monkeypatch.setattr(
        "frontend.RenpyToolbox.OneKeyTranslatePage.shutil.copy2",
        fail_second_source,
    )

    with pytest.raises(RuntimeError, match="已回滚"):
        apply_translation_files_transactionally(
            [first_source, second_source], output, target
        )

    assert first_target.read_text(encoding="utf-8") == "old nebula\n"
    assert second_target.read_text(encoding="utf-8") == "old aurora\n"


def _make_test_symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")


def test_transactional_apply_preserves_symlink_and_updates_referent(tmp_path):
    output = tmp_path / "output"
    target = tmp_path / "target"
    shared = tmp_path / "shared"
    output.mkdir()
    target.mkdir()
    shared.mkdir()
    source = output / "fictional_linked.rpy"
    link = target / "fictional_linked.rpy"
    referent = shared / "fictional_linked.rpy"
    source.write_text("new fictional link translation\n", encoding="utf-8")
    referent.write_text("old fictional link translation\n", encoding="utf-8")
    _make_test_symlink(link, referent)

    assert apply_translation_files_transactionally([source], output, target) == 1

    assert link.is_symlink()
    assert referent.read_text(encoding="utf-8") == "new fictional link translation\n"


def test_transactional_apply_creates_dangling_symlink_referent(tmp_path):
    output = tmp_path / "output"
    target = tmp_path / "target"
    shared = tmp_path / "shared"
    output.mkdir()
    target.mkdir()
    shared.mkdir()
    source = output / "fictional_pending.rpy"
    link = target / "fictional_pending.rpy"
    referent = shared / "fictional_pending.rpy"
    source.write_text("new fictional pending translation\n", encoding="utf-8")
    _make_test_symlink(link, Path("..") / "shared" / referent.name)

    assert link.is_symlink()
    assert not referent.exists()
    assert apply_translation_files_transactionally([source], output, target) == 1

    assert link.is_symlink()
    assert referent.read_text(encoding="utf-8") == (
        "new fictional pending translation\n"
    )


def test_transactional_apply_rolls_back_created_symlink_referent(
    tmp_path, monkeypatch
):
    output = tmp_path / "output"
    target = tmp_path / "target"
    shared = tmp_path / "shared"
    output.mkdir()
    target.mkdir()
    shared.mkdir()
    first_source = output / "first_pending.rpy"
    second_source = output / "second_regular.rpy"
    link = target / "first_pending.rpy"
    referent = shared / "first_pending.rpy"
    first_source.write_text("new fictional pending value\n", encoding="utf-8")
    second_source.write_text("new fictional regular value\n", encoding="utf-8")
    _make_test_symlink(link, Path("..") / "shared" / referent.name)

    import shutil as real_shutil

    real_copy2 = real_shutil.copy2

    def fail_second_source(src, dst, *args, **kwargs):
        if Path(src).resolve() == second_source.resolve():
            raise OSError("fictional dangling-link batch interruption")
        return real_copy2(src, dst, *args, **kwargs)

    monkeypatch.setattr(
        "frontend.RenpyToolbox.OneKeyTranslatePage.shutil.copy2",
        fail_second_source,
    )

    with pytest.raises(RuntimeError, match="已回滚"):
        apply_translation_files_transactionally(
            [first_source, second_source], output, target
        )

    assert link.is_symlink()
    assert not referent.exists()


def test_transactional_apply_rolls_back_symlink_referent(tmp_path, monkeypatch):
    output = tmp_path / "output"
    target = tmp_path / "target"
    shared = tmp_path / "shared"
    output.mkdir()
    target.mkdir()
    shared.mkdir()
    first_source = output / "first_linked.rpy"
    second_source = output / "second_regular.rpy"
    link = target / "first_linked.rpy"
    referent = shared / "first_linked.rpy"
    first_source.write_text("new fictional linked value\n", encoding="utf-8")
    second_source.write_text("new fictional regular value\n", encoding="utf-8")
    referent.write_text("old fictional linked value\n", encoding="utf-8")
    _make_test_symlink(link, referent)

    import shutil as real_shutil

    real_copy2 = real_shutil.copy2

    def fail_second_source(src, dst, *args, **kwargs):
        if Path(src).resolve() == second_source.resolve():
            raise OSError("fictional symlink batch interruption")
        return real_copy2(src, dst, *args, **kwargs)

    monkeypatch.setattr(
        "frontend.RenpyToolbox.OneKeyTranslatePage.shutil.copy2",
        fail_second_source,
    )

    with pytest.raises(RuntimeError, match="已回滚"):
        apply_translation_files_transactionally(
            [first_source, second_source], output, target
        )

    assert link.is_symlink()
    assert referent.read_text(encoding="utf-8") == "old fictional linked value\n"


def test_transactional_apply_uses_lexical_path_for_symlinked_source(tmp_path):
    output = tmp_path / "output"
    target = tmp_path / "target"
    shared = tmp_path / "shared"
    output.mkdir()
    target.mkdir()
    shared.mkdir()
    referent = shared / "fictional_external.rpy"
    source_link = output / "fictional_alias.rpy"
    referent.write_text("fictional external translation\n", encoding="utf-8")
    _make_test_symlink(source_link, referent)

    assert apply_translation_files_transactionally(
        [source_link], output, target
    ) == 1

    applied = target / "fictional_alias.rpy"
    assert applied.read_text(encoding="utf-8") == "fictional external translation\n"
    assert not (target / "fictional_external.rpy").exists()


def test_transactional_apply_rejects_symlink_escaping_target(tmp_path):
    output = tmp_path / "output"
    target = tmp_path / "game" / "tl" / "chinese"
    outside = tmp_path / "outside"
    output.mkdir()
    target.mkdir(parents=True)
    outside.mkdir()
    source = output / "fictional_escape.rpy"
    link = target / "fictional_escape.rpy"
    referent = outside / "fictional_escape.rpy"
    source.write_text("new fictional translation\n", encoding="utf-8")
    referent.write_text("old secret content\n", encoding="utf-8")
    _make_test_symlink(link, referent)

    with pytest.raises(RuntimeError, match="翻译目录之外"):
        apply_translation_files_transactionally([source], output, target)

    # 项目外的文件不得被覆盖。
    assert referent.read_text(encoding="utf-8") == "old secret content\n"


def test_transactional_apply_preserves_backups_when_rollback_fails(
    tmp_path, monkeypatch
):
    import os

    output = tmp_path / "output"
    target = tmp_path / "game" / "tl" / "chinese"
    output.mkdir()
    target.mkdir(parents=True)
    first = output / "first.rpy"
    second = output / "second.rpy"
    first.write_text("A", encoding="utf-8")
    second.write_text("B", encoding="utf-8")
    (target / "first.rpy").write_text("A-old", encoding="utf-8")

    real_replace = os.replace

    def failing_replace(src, dst):
        dst_text = str(dst)
        src_text = str(src)
        if dst_text.endswith("second.rpy"):
            raise PermissionError("simulated apply failure")
        if dst_text.endswith("first.rpy") and "rollback" in src_text:
            raise PermissionError("simulated rollback failure")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(RuntimeError) as exc_info:
        apply_translation_files_transactionally(
            [first, second], output, target
        )

    message = str(exc_info.value)
    assert "备份" in message
    # 回滚失败时备份目录必须保留（带 rollback- 后缀），而不是被删除。
    leftovers = list(Path(tmp_path / "game" / "tl").glob(".renpybox-apply-*"))
    assert leftovers, "backup root must be preserved when rollback fails"
