"""Agent 润色模式：读已译条目、写回标记为 POLISHED。

用户反馈（2026-10-18）：「我汉化完了，你能不能直接按照原文和译文优化和润色
我的翻译」。以前 read_translation_batch 只筛待译条目，已译内容对 Agent 是
不可见的，于是它只能回答「已经译完了」而无事可做。
"""
from __future__ import annotations

from pathlib import Path

from base.Base import Base
from module.Agent.tools.agent_translation_tools import (
    MODE_POLISH,
    MODE_TRANSLATE,
    read_translation_batch,
    write_translation_batch,
)
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheProject import CacheProject
from module.Config import Config


def _config_for(root: Path) -> Config:
    config = Config()
    config.platforms = []
    config.renpy_project_path = str(root)
    config.renpy_game_folder = str(root / "game")
    config.input_folder = str(root / "game" / "tl" / "chinese")
    config.output_folder = str(root / "output")
    config.target_language = "ZH"
    config.max_workers = 1
    config.save = lambda: config
    return config


def _make_item(
    row: int,
    src: str,
    *,
    status: Base.TranslationStatus,
    dst: str = "",
) -> CacheItem:
    item = CacheItem()
    item.set_file_path("game/tl/chinese/script.rpy")
    item.set_row(row)
    item.set_src(src)
    item.set_dst(dst)
    item.set_file_type(CacheItem.FileType.NONE)
    item.set_text_type(CacheItem.TextType.RENPY)
    item.set_status(status)
    return item


def _seed_cache(config: Config, items: list[CacheItem]) -> None:
    output = Path(str(config.output_folder))
    output.mkdir(parents = True, exist_ok = True)
    manager = CacheManager(service = False)
    project = CacheProject()
    manager.set_project(project)
    manager.set_items(items)
    assert manager.save_to_file(project, items, str(output)) is True


def _load_items(config: Config) -> list[CacheItem]:
    manager = CacheManager(service = False)
    manager.load_items_from_file(str(config.output_folder))
    return manager.get_items()


def test_polish_mode_returns_translated_entries_with_current_text(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    _seed_cache(config, [
        _make_item(1, "Hello", status = Base.TranslationStatus.UNTRANSLATED),
        _make_item(2, "World", status = Base.TranslationStatus.TRANSLATED, dst = "世界"),
        _make_item(3, "Skipped", status = Base.TranslationStatus.EXCLUDED, dst = "略过"),
    ])

    result = read_translation_batch(config_loader = lambda: config, mode = MODE_POLISH)

    assert result.success is True
    assert result.data["mode"] == MODE_POLISH
    # 只有已译且有译文的条目，未译与被排除的都不算。
    assert result.data["returned"] == 1
    entry = result.data["items"][0]
    assert entry["src"] == "World"
    assert entry["dst"] == "世界"


def test_translate_mode_ignores_polish_switches(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    _seed_cache(config, [
        _make_item(1, "Hello", status = Base.TranslationStatus.UNTRANSLATED),
        _make_item(2, "World", status = Base.TranslationStatus.TRANSLATED, dst = "世界"),
    ])

    result = read_translation_batch(config_loader = lambda: config)

    assert result.data["mode"] == MODE_TRANSLATE
    assert [entry["src"] for entry in result.data["items"]] == ["Hello"]
    assert "dst" not in result.data["items"][0]


def test_polish_mode_reports_nothing_to_polish(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    _seed_cache(config, [_make_item(1, "Hello", status = Base.TranslationStatus.UNTRANSLATED)])

    result = read_translation_batch(config_loader = lambda: config, mode = MODE_POLISH)

    assert result.success is True
    assert result.data["remaining"] == 0
    assert "润色" in result.message


def test_write_polish_marks_entries_polished(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    _seed_cache(config, [
        _make_item(1, "Hello", status = Base.TranslationStatus.TRANSLATED, dst = "你好"),
    ])

    batch = read_translation_batch(config_loader = lambda: config, mode = MODE_POLISH)
    item_id = batch.data["items"][0]["id"]

    result = write_translation_batch(
        config_loader = lambda: config,
        mode = MODE_POLISH,
        translations = [{"id": item_id, "dst": "您好呀"}],
    )

    assert result.success is True
    assert result.data["written"] == 1
    stored = _load_items(config)[0]
    assert stored.get_dst() == "您好呀"
    # 润色与「新翻译」在状态上要能区分开。
    assert stored.get_status() == Base.TranslationStatus.POLISHED


def test_write_translate_still_marks_translated(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    _seed_cache(config, [_make_item(1, "Hello", status = Base.TranslationStatus.UNTRANSLATED)])

    batch = read_translation_batch(config_loader = lambda: config)
    item_id = batch.data["items"][0]["id"]

    result = write_translation_batch(
        config_loader = lambda: config,
        translations = [{"id": item_id, "dst": "你好"}],
    )

    assert result.success is True
    assert _load_items(config)[0].get_status() == Base.TranslationStatus.TRANSLATED


def test_polished_entries_drop_out_of_polish_batch(tmp_path: Path) -> None:
    """润色完成后再读不应重复返回，否则长任务会永远原地打转。"""

    config = _config_for(tmp_path)
    _seed_cache(config, [
        _make_item(1, "Hello", status = Base.TranslationStatus.POLISHED, dst = "你好"),
    ])

    result = read_translation_batch(config_loader = lambda: config, mode = MODE_POLISH)

    assert result.data["remaining"] == 0
