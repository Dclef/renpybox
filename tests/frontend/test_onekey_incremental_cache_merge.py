from base.Base import Base
from frontend.RenpyToolbox.OneKeyTranslatePage import (
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
