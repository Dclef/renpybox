"""全项目解析缓存：指纹失效、副本隔离与容量淘汰。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from module.Workbench.AnalysisService import WorkbenchAnalysisService


def make_config(game_dir: Path):
    return SimpleNamespace(
        input_folder = str(game_dir),
        output_folder = str(game_dir / "output"),
        project_dir = str(game_dir.parent),
        renpy_source_translate = True,
        renpy_hook_translate = False,
        language = "chinese",
    )


def build_project(tmp_path: Path, lines: list[str]) -> Path:
    root = tmp_path / "project"
    game = root / "game"
    game.mkdir(parents = True)
    (game / "script.rpy").write_text("\n".join(lines), encoding = "utf-8")
    return root


def test_cache_hit_skips_second_parse(tmp_path, monkeypatch):
    root = build_project(tmp_path, ['e "Hello there."', 'e "Second line."', 'e "Third line."'])
    calls: list[int] = []

    class FakeProject:
        pass

    class FakeManager:
        def __init__(self, config):
            self.config = config

        def read_from_path(self):
            calls.append(1)
            from module.Cache.CacheItem import CacheItem

            item = CacheItem()
            item.set_src("Hello there.")
            return FakeProject(), [item]

    from module.Workbench import AnalysisService as service_module

    monkeypatch.setattr(service_module, "FileManager", FakeManager)

    service = WorkbenchAnalysisService()
    service._full_project_cache.clear()
    config = make_config(root / "game")

    first = service.load_full_project_items(config)
    second = service.load_full_project_items(config)

    assert len(first) == 1
    assert [item.get_src() for item in second] == [item.get_src() for item in first]
    assert len(calls) == 1  # 第二轮命中缓存，没有重新解析


def test_cache_invalidates_when_source_changes(tmp_path, monkeypatch):
    root = build_project(tmp_path, ['e "Hello there."'])
    calls: list[int] = []

    class FakeProject:
        pass

    class FakeManager:
        def __init__(self, config):
            self.config = config

        def read_from_path(self):
            calls.append(1)
            from module.Cache.CacheItem import CacheItem

            item = CacheItem()
            item.set_src("Hello there.")
            return FakeProject(), [item]

    from module.Workbench import AnalysisService as service_module

    monkeypatch.setattr(service_module, "FileManager", FakeManager)

    service = WorkbenchAnalysisService()
    service._full_project_cache.clear()
    game = root / "game"
    config = make_config(game)

    service.load_full_project_items(config)
    script = game / "script.rpy"
    script.write_text('e "Hello there."\ne "Another one."', encoding = "utf-8")
    service.load_full_project_items(config)

    assert len(calls) == 2


def test_cached_items_are_returned_as_copies(tmp_path, monkeypatch):
    root = build_project(tmp_path, ['e "Hello there."'])

    class FakeProject:
        pass

    class FakeManager:
        def __init__(self, config):
            self.config = config

        def read_from_path(self):
            from module.Cache.CacheItem import CacheItem

            item = CacheItem()
            item.set_src("Hello there.")
            return FakeProject(), [item]

    from module.Workbench import AnalysisService as service_module

    monkeypatch.setattr(service_module, "FileManager", FakeManager)

    service = WorkbenchAnalysisService()
    service._full_project_cache.clear()
    config = make_config(root / "game")

    first = service.load_full_project_items(config)
    first.clear()
    second = service.load_full_project_items(config)

    assert len(second) == 1


def test_cache_evicts_beyond_limit(tmp_path):
    WorkbenchAnalysisService._full_project_cache.clear()
    total = WorkbenchAnalysisService.FULL_PROJECT_CACHE_LIMIT + 2
    for index in range(total):
        WorkbenchAnalysisService._remember_full_project(f"key-{index}", (index, 0.0, index), [])

    assert len(WorkbenchAnalysisService._full_project_cache) == WorkbenchAnalysisService.FULL_PROJECT_CACHE_LIMIT
    assert "key-0" not in WorkbenchAnalysisService._full_project_cache
    assert f"key-{total - 1}" in WorkbenchAnalysisService._full_project_cache


def test_fingerprint_ignores_translation_dirs(tmp_path):
    root = build_project(tmp_path, ['e "Hello there."'])
    game = root / "game"
    tl_dir = game / "tl" / "chinese"
    tl_dir.mkdir(parents = True)
    (tl_dir / "script.rpy").write_text('e "你好。"', encoding = "utf-8")

    fingerprint = WorkbenchAnalysisService._source_fingerprint(game)

    assert fingerprint[0] == 1  # tl 目录下的脚本不计入指纹
