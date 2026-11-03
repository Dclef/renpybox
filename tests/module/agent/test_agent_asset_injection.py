"""Agent 翻译路径的资产注入与术语校验用例。

覆盖施工单 `docs/internal/2026-11-03/plan/task-agent-translation-quality.md` §七：

- 术语/禁翻按批注入，且只注入本批命中项
- 注入有字符上限与截断提示
- 资产构建失败不阻断取批
- 译后替换参与写回
- 术语未按译法时退回 UNTRANSLATED，且不记为写回失败
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from base.Base import Base
from module.Agent.tools.agent_translation_tools import (
    MAX_ASSET_CHARS,
    _batch_assets,
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
    config.glossary_enable = False
    config.glossary_data = []
    config.text_preserve_enable = False
    config.text_preserve_data = []
    config.post_translation_replacement_enable = False
    config.post_translation_replacement_data = []
    config.save = lambda: config
    return config


def _make_item(row: int, src: str, *, status: Base.TranslationStatus) -> CacheItem:
    item = CacheItem()
    item.set_file_path("game/tl/chinese/script.rpy")
    item.set_row(row)
    item.set_src(src)
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


def _set_glossary(config: Config, entries: list[dict[str, Any]]) -> None:
    config.glossary_enable = True
    config.glossary_data = entries


# --- 注入 ---------------------------------------------------------------


def test_read_batch_injects_matching_glossary_only(tmp_path: Path) -> None:
    """术语只注入本批命中的，不把整本术语表灌进来。"""

    config = _config_for(tmp_path)
    _set_glossary(config, [
        {"src": "Alice", "dst": "爱丽丝", "info": "角色名"},
        {"src": "Sword", "dst": "剑", "info": ""},
    ])
    _seed_cache(config, [
        _make_item(1, "Alice holds a book.", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    result = read_translation_batch(config_loader = lambda: config)

    assert result.success is True
    # "Sword" 没出现在本批原文里，不该被注入
    assert "Alice -> 爱丽丝" in result.data["glossary"]
    assert "Sword" not in result.data["glossary"]


def test_read_batch_omits_glossary_key_when_no_hit(tmp_path: Path) -> None:
    """没有命中时不返回该键，让模型明确读到「本批无术语约束」。"""

    config = _config_for(tmp_path)
    _set_glossary(config, [{"src": "Alice", "dst": "爱丽丝", "info": ""}])
    _seed_cache(config, [
        _make_item(1, "Hello there.", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    result = read_translation_batch(config_loader = lambda: config)

    assert result.success is True
    assert "glossary" not in result.data


def test_read_batch_skips_glossary_when_disabled(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    config.glossary_enable = False
    config.glossary_data = [{"src": "Alice", "dst": "爱丽丝", "info": ""}]
    _seed_cache(config, [
        _make_item(1, "Alice holds a book.", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    result = read_translation_batch(config_loader = lambda: config)

    assert result.success is True
    assert "glossary" not in result.data


def test_read_batch_injects_do_not_translate(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    config.do_not_translate_enable = True
    config.do_not_translate_data = [{"src": "RenpyBox", "info": "产品名"}]
    _seed_cache(config, [
        _make_item(1, "Powered by RenpyBox.", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    result = read_translation_batch(config_loader = lambda: config)

    assert result.success is True
    assert "do_not_translate" in result.data
    assert "RenpyBox" in result.data["do_not_translate"]


def test_injected_asset_text_is_clipped(tmp_path: Path) -> None:
    """术语极多时必须截断，否则会挤占本批正文与上下文。

    引擎侧先按 ``asset_prompt_token_budget`` 裁剪；这里把该预算调大，
    验证 Agent 侧的硬上限 ``MAX_ASSET_CHARS`` 仍然兜得住。
    """

    config = _config_for(tmp_path)
    config.asset_prompt_max_items = 5000
    config.asset_prompt_token_budget = 500_000
    entries = [
        {"src": f"Term{i:04d}", "dst": f"术语{i:04d}", "info": ""}
        for i in range(2000)
    ]
    _set_glossary(config, entries)
    # 让每条术语都命中：原文把全部术语串起来
    src = " ".join(entry["src"] for entry in entries)

    assets = _batch_assets(config, [{"src": src}])

    assert "glossary" in assets
    assert len(assets["glossary"]) <= MAX_ASSET_CHARS
    # 截断提示要跟着一起给出
    assert "其余未显示" in assets["glossary"]


def test_asset_build_failure_does_not_block_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """术语表损坏不能让取批整体失败。"""

    config = _config_for(tmp_path)
    _seed_cache(config, [
        _make_item(1, "Hello", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    import module.PromptBuilder as prompt_builder

    class _Broken:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise ValueError("术语表损坏")

    monkeypatch.setattr(prompt_builder, "PromptBuilder", _Broken)

    result = read_translation_batch(config_loader = lambda: config)

    assert result.success is True
    assert len(result.data["items"]) == 1


# --- 译后替换 -----------------------------------------------------------


def test_write_applies_post_translation_replacement(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    config.post_translation_replacement_enable = True
    config.post_translation_replacement_data = [
        {"src": "爱丽丝", "dst": "艾莉丝"},
    ]
    _seed_cache(config, [
        _make_item(1, "Alice", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    batch = read_translation_batch(config_loader = lambda: config)
    item_id = batch.data["items"][0]["id"]

    result = write_translation_batch(
        config_loader = lambda: config,
        translations = [{"id": item_id, "dst": "爱丽丝来了"}],
    )

    assert result.success is True
    stored = {item.get_row(): item for item in _load_items(config)}
    assert stored[1].get_dst() == "艾莉丝来了"


# --- 术语校验 -----------------------------------------------------------


def test_glossary_mismatch_rolls_back_to_untranslated(tmp_path: Path) -> None:
    """术语没按译法时退回待译，不自动替换，也不当成写回失败。"""

    config = _config_for(tmp_path)
    _set_glossary(config, [{"src": "Alice", "dst": "爱丽丝", "info": ""}])
    _seed_cache(config, [
        _make_item(1, "Alice smiles.", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    batch = read_translation_batch(config_loader = lambda: config)
    item_id = batch.data["items"][0]["id"]

    # 译文完全没用术语表指定的译法
    result = write_translation_batch(
        config_loader = lambda: config,
        translations = [{"id": item_id, "dst": "那个女孩微笑了"}],
    )

    # 术语失败不是写回失败
    assert result.code != "WRITEBACK_FAILED"
    assert result.data["glossary_failures"][item_id] == ["Alice -> 爱丽丝"]

    stored = {item.get_row(): item for item in _load_items(config)}
    assert stored[1].get_status() == Base.TranslationStatus.UNTRANSLATED
    # 不自动替换：缓存里的草稿仍是模型原样给的、没按术语的译法。
    # （被打回条目不进 checked，不会写进游戏文件；保留草稿是既有行为，
    #  ResponseChecker 那条闸打回时也一样。）
    assert stored[1].get_dst() == "那个女孩微笑了"


def test_glossary_change_rolls_back_again(tmp_path: Path) -> None:
    """退回的条目下一批还能取到，模型有机会重写。"""

    config = _config_for(tmp_path)
    _set_glossary(config, [{"src": "Alice", "dst": "爱丽丝", "info": ""}])
    _seed_cache(config, [
        _make_item(1, "Alice smiles.", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    batch = read_translation_batch(config_loader = lambda: config)
    item_id = batch.data["items"][0]["id"]

    write_translation_batch(
        config_loader = lambda: config,
        translations = [{"id": item_id, "dst": "那个女孩微笑了"}],
    )

    again = read_translation_batch(config_loader = lambda: config)
    assert again.data["remaining"] == 1
    assert again.data["items"][0]["id"] == item_id


def test_glossary_followed_writes_normally(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    _set_glossary(config, [{"src": "Alice", "dst": "爱丽丝", "info": ""}])
    _seed_cache(config, [
        _make_item(1, "Alice smiles.", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    batch = read_translation_batch(config_loader = lambda: config)
    item_id = batch.data["items"][0]["id"]

    result = write_translation_batch(
        config_loader = lambda: config,
        translations = [{"id": item_id, "dst": "爱丽丝微笑了"}],
    )

    assert result.success is True
    assert result.data["written"] == 1
    assert "glossary_failures" not in result.data
    stored = {item.get_row(): item for item in _load_items(config)}
    assert stored[1].get_status() == Base.TranslationStatus.TRANSLATED


def test_glossary_disabled_does_not_roll_back(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    config.glossary_enable = False
    config.glossary_data = [{"src": "Alice", "dst": "爱丽丝", "info": ""}]
    _seed_cache(config, [
        _make_item(1, "Alice smiles.", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    batch = read_translation_batch(config_loader = lambda: config)
    item_id = batch.data["items"][0]["id"]

    result = write_translation_batch(
        config_loader = lambda: config,
        translations = [{"id": item_id, "dst": "那个女孩笑了"}],
    )

    assert result.success is True
    assert result.data["written"] == 1
