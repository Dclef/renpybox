"""Agent 原型保护（占位符）用例。

覆盖施工单 `docs/internal/2026-11-03/plan/task-agent-placeholder-and-metrics.md` §七。

背景：引擎侧靠 `TextProcessor.pre_process` 产出 `<vN/>` 占位符，再由
`ResponseChecker.RE_PRESERVE_TOKEN` 做成对校验；Agent 路径不经过它，
那段校验一直空转。模型改坏 `[player_name]` 会让游戏 `NameError`，程序没拦。
"""

from __future__ import annotations

from pathlib import Path

from base.Base import Base
from module.Agent.tools.agent_translation_tools import (
    _PlaceholderGuard,
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


# --- 保护 ---------------------------------------------------------------


def test_guard_protects_variables_and_tags() -> None:
    guard = _PlaceholderGuard()

    protected = guard.protect("你好 [player_name]，这里是 {b}起点{/b}。")

    assert "[player_name]" not in protected
    assert "{b}" not in protected
    assert protected.count("<v") == 3
    # REGEX_RENPY 里花括号规则在方括号规则之前（CacheItem.py:89/94），
    # 所以编号按「先花括号、后方括号」分配。
    assert guard.codes["<v0/>"] == "{b}"
    assert guard.codes["<v1/>"] == "{/b}"
    assert guard.codes["<v2/>"] == "[player_name]"


def test_guard_numbers_globally_within_batch() -> None:
    """按行从 0 编号会让两行都有 <v0/>，还原时张冠李戴。"""

    guard = _PlaceholderGuard()
    first = guard.protect("[a]")
    second = guard.protect("[b]")

    assert first == "<v0/>"
    assert second == "<v1/>"
    assert guard.codes["<v0/>"] == "[a]"
    assert guard.codes["<v1/>"] == "[b]"


def test_guard_restore_round_trips() -> None:
    guard = _PlaceholderGuard()
    protected = guard.protect("[player_name] 说 {b}你好{/b}")

    restored, problems = guard.restore(protected)

    assert problems == []
    assert "[player_name]" in restored
    assert "{b}" in restored
    assert "<v0/>" not in restored


def test_guard_reports_missing_placeholder() -> None:
    guard = _PlaceholderGuard()
    guard.protect("[player_name]")

    restored, problems = guard.restore("名字都没了")

    assert problems
    assert any("missing" in item for item in problems)


def test_guard_reports_unexpected_placeholder() -> None:
    guard = _PlaceholderGuard()
    guard.protect("[player_name]")

    _restored, problems = guard.restore("[player_name] 还有 <v99/>")

    assert any("unexpected" in item for item in problems)


# --- 取批接入 -----------------------------------------------------------


def test_read_batch_protects_and_exposes_mapping(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    _seed_cache(config, [
        _make_item(1, "你好 [player_name]", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    result = read_translation_batch(config_loader = lambda: config)

    assert result.success is True
    src = result.data["items"][0]["src"]
    assert "[player_name]" not in src
    assert result.data["protected_placeholders"]["<v0/>"] == "[player_name]"


def test_read_batch_omits_mapping_without_placeholders(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    _seed_cache(config, [
        _make_item(1, "纯文本没有占位符", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    result = read_translation_batch(config_loader = lambda: config)

    assert result.success is True
    assert "protected_placeholders" not in result.data


# --- 写回还原 -----------------------------------------------------------


def test_write_restores_placeholder(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    _seed_cache(config, [
        _make_item(1, "你好 [player_name]", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    batch = read_translation_batch(config_loader = lambda: config)
    item_id = batch.data["items"][0]["id"]
    placeholders = batch.data["protected_placeholders"]

    result = write_translation_batch(
        config_loader = lambda: config,
        translations = [{"id": item_id, "dst": "你好 <v0/>"}],
        protected_placeholders = placeholders,
    )

    assert result.success is True
    stored = {item.get_row(): item for item in _load_items(config)}
    # 落盘必须是游戏能认的 [player_name]，不能残留 <v0/>
    assert stored[1].get_dst() == "你好 [player_name]"
    assert "<v0/>" not in stored[1].get_dst()


def test_write_rolls_back_when_placeholder_dropped(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    _seed_cache(config, [
        _make_item(1, "你好 [player_name]", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    batch = read_translation_batch(config_loader = lambda: config)
    item_id = batch.data["items"][0]["id"]
    placeholders = batch.data["protected_placeholders"]

    result = write_translation_batch(
        config_loader = lambda: config,
        translations = [{"id": item_id, "dst": "你好呀"}],
        protected_placeholders = placeholders,
    )

    assert result.code == "PLACEHOLDER_MISMATCH"
    assert item_id in result.data["placeholder_failures"]
    stored = {item.get_row(): item for item in _load_items(config)}
    assert stored[1].get_status() == Base.TranslationStatus.UNTRANSLATED


def test_write_rolls_back_on_invented_placeholder(tmp_path: Path) -> None:
    config = _config_for(tmp_path)
    _seed_cache(config, [
        _make_item(1, "你好 [player_name]", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    batch = read_translation_batch(config_loader = lambda: config)
    item_id = batch.data["items"][0]["id"]

    result = write_translation_batch(
        config_loader = lambda: config,
        translations = [{"id": item_id, "dst": "你好 <v0/> 还有 <v7/>"}],
        protected_placeholders = batch.data["protected_placeholders"],
    )

    assert result.code == "PLACEHOLDER_MISMATCH"
    assert item_id in result.data["placeholder_failures"]


def test_write_skips_check_without_mapping(tmp_path: Path) -> None:
    """模型没回传占位表（旧会话或自造调用）时不能误判。"""

    config = _config_for(tmp_path)
    _seed_cache(config, [
        _make_item(1, "你好 [player_name]", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    batch = read_translation_batch(config_loader = lambda: config)
    item_id = batch.data["items"][0]["id"]

    result = write_translation_batch(
        config_loader = lambda: config,
        translations = [{"id": item_id, "dst": "你好呀"}],
    )

    assert result.success is True
    assert "placeholder_failures" not in result.data


def test_restore_happens_before_post_replacement(tmp_path: Path) -> None:
    """还原必须在译后替换之前，否则替换规则会作用在占位符上。"""

    config = _config_for(tmp_path)
    config.post_translation_replacement_enable = True
    # 规则作用在还原后的中文变量文本上：只有先还原才能替换到
    config.post_translation_replacement_data = [{"src": "[player_name]", "dst": "[主角]"}]
    _seed_cache(config, [
        _make_item(1, "你好 [player_name]", status = Base.TranslationStatus.UNTRANSLATED),
    ])

    batch = read_translation_batch(config_loader = lambda: config)
    item_id = batch.data["items"][0]["id"]

    result = write_translation_batch(
        config_loader = lambda: config,
        translations = [{"id": item_id, "dst": "你好 <v0/>"}],
        protected_placeholders = batch.data["protected_placeholders"],
    )

    assert result.success is True
    stored = {item.get_row(): item for item in _load_items(config)}
    # 先还原成 [player_name]，再被替换成 [主角]
    assert stored[1].get_dst() == "你好 [主角]"
