"""AndroidProjectTools：X- 前缀 strip / restore。"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from module.Tool.AndroidProjectTools import (
    AndroidProjectToolsError,
    PREFIX_DEFAULT,
    normalize_prefix,
    rename_prefix,
)


def _rel_set(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path != root
    }


def _make_x_game(tmp_path: Path) -> Path:
    assets = tmp_path / "assets"
    x_game = assets / "x-game"
    (x_game / "x-tl").mkdir(parents=True)
    (x_game / "x-script.rpyc").write_bytes(b"script")
    (x_game / "x-tl" / "x-common.rpy").write_text("label common:\n    pass\n", encoding="utf-8")
    return x_game


def test_normalize_prefix_rejects_empty():
    assert normalize_prefix("  x-  ") == "x-"
    assert normalize_prefix(PREFIX_DEFAULT) == "x-"
    with pytest.raises(AndroidProjectToolsError, match="前缀不能为空"):
        normalize_prefix("   ")
    with pytest.raises(AndroidProjectToolsError, match="前缀不能为空"):
        normalize_prefix(None)


def test_strip_full_tree(tmp_path):
    x_game = _make_x_game(tmp_path)
    result = rename_prefix(x_game, prefix="x-", action="strip", apply=True)
    game = tmp_path / "assets" / "game"
    assert result["success"] is True
    assert result["applied"] is True
    assert result["files"] == 2
    assert result["dirs"] == 2
    assert result["renamed"] == 4
    assert result["skipped"] == 0
    assert result["new_root"] == str(game)
    assert (game / "script.rpyc").is_file()
    assert (game / "tl" / "common.rpy").is_file()
    assert not x_game.exists()


def test_strip_restore_roundtrip(tmp_path):
    x_game = _make_x_game(tmp_path)
    assets = x_game.parent
    before = _rel_set(assets)
    stripped = rename_prefix(x_game, prefix="x-", action="strip", apply=True)
    game = Path(stripped["new_root"])
    restored = rename_prefix(game, prefix="x-", action="restore", apply=True)
    assert restored["new_root"] is not None
    after_root = Path(restored["new_root"]).parent
    assert _rel_set(after_root) == before


def test_dry_run_no_side_effects(tmp_path):
    x_game = _make_x_game(tmp_path)
    before = _rel_set(x_game.parent)
    result = rename_prefix(x_game, prefix="x-", action="strip", apply=False)
    assert result["total"] > 0
    assert result["renamed"] == result["total"]
    assert result["applied"] is False
    assert _rel_set(x_game.parent) == before
    assert x_game.is_dir()
    assert (x_game / "x-script.rpyc").is_file()


def test_conflict_skip(tmp_path):
    folder = tmp_path / "mixed"
    folder.mkdir()
    (folder / "x-a.txt").write_text("x", encoding="utf-8")
    (folder / "a.txt").write_text("a", encoding="utf-8")
    result = rename_prefix(folder, prefix="x-", action="strip", apply=True)
    assert result["skipped"] == 1
    assert (folder / "x-a.txt").is_file()
    assert (folder / "a.txt").is_file()
    assert result["skipped_items"][0]["reason"] == "目标已存在"


def test_case_insensitive_strip(tmp_path):
    folder = tmp_path / "cased"
    folder.mkdir()
    (folder / "X-Script.rpyc").write_bytes(b"x")
    result = rename_prefix(folder, prefix="x-", action="strip", apply=True)
    assert result["renamed"] == 1
    assert (folder / "Script.rpyc").is_file()
    assert not (folder / "X-Script.rpyc").exists()


def test_root_rename_rules(tmp_path):
    assets = tmp_path / "assets"
    x_game = assets / "x-game"
    x_game.mkdir(parents=True)
    (x_game / "x-script.rpyc").write_bytes(b"s")

    # 根为 assets：不改根名
    outer = rename_prefix(assets, prefix="x-", action="strip", apply=True)
    assert outer["new_root"] is None
    assert assets.is_dir()
    assert (assets / "game" / "script.rpyc").is_file()

    # 重建 x-game 根规则
    x_game2 = tmp_path / "pack" / "x-game"
    x_game2.mkdir(parents=True)
    (x_game2 / "x-a.txt").write_text("a", encoding="utf-8")
    stripped = rename_prefix(x_game2, prefix="x-", action="strip", apply=True)
    game = Path(stripped["new_root"])
    assert game.name == "game"
    assert game.is_dir()

    restored = rename_prefix(game, prefix="x-", action="restore", apply=True)
    assert Path(restored["new_root"]).name == "x-game"


def test_symlink_skipped(tmp_path):
    folder = tmp_path / "with_link"
    folder.mkdir()
    (folder / "x-real.txt").write_text("r", encoding="utf-8")
    target = tmp_path / "link_target.txt"
    target.write_text("t", encoding="utf-8")
    link = folder / "x-link.txt"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("无法创建 symlink/junction")
    if not link.exists() and not link.is_symlink():
        pytest.skip("无法创建 symlink/junction")

    result = rename_prefix(folder, prefix="x-", action="strip", apply=True)
    assert any(item["reason"] == "链接/联接" for item in result["skipped_items"])
    assert (folder / "real.txt").is_file()
    assert link.exists() or link.is_symlink()


def test_reject_bad_paths(tmp_path):
    with pytest.raises(AndroidProjectToolsError):
        rename_prefix(Path.cwd().anchor, prefix="x-", action="strip", apply=False)
    with pytest.raises(AndroidProjectToolsError, match="目录不存在"):
        rename_prefix(tmp_path / "missing", prefix="x-", action="strip", apply=False)
    a_file = tmp_path / "a-file.txt"
    a_file.write_text("x", encoding="utf-8")
    with pytest.raises(AndroidProjectToolsError, match="不是目录"):
        rename_prefix(a_file, prefix="x-", action="strip", apply=False)
    with pytest.raises(AndroidProjectToolsError, match="前缀不能为空"):
        rename_prefix(tmp_path, prefix="  ", action="strip", apply=False)
    with pytest.raises(AndroidProjectToolsError, match="strip 或 restore"):
        rename_prefix(tmp_path, prefix="x-", action="move", apply=False)


def test_rename_failure_reports_reason(tmp_path, monkeypatch):
    """改名失败不能漏成裸 OSError：上层要拿到可读原因（已处理计数一并带上）。"""
    folder = tmp_path / "broken"
    folder.mkdir()
    (folder / "x-a.txt").write_text("a", encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise OSError("拒绝访问")

    monkeypatch.setattr(os, "rename", _boom)
    with pytest.raises(AndroidProjectToolsError, match="重命名失败（已处理 0 个）"):
        rename_prefix(folder, prefix="x-", action="strip", apply=True)


def test_limit_exceeded(tmp_path):
    folder = tmp_path / "many"
    folder.mkdir()
    for index in range(5):
        (folder / f"x-file{index}.txt").write_text(str(index), encoding="utf-8")
    with pytest.raises(AndroidProjectToolsError, match="条目过多"):
        rename_prefix(folder, prefix="x-", action="strip", apply=False, limit=3)
