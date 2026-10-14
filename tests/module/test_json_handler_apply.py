"""JsonImporter 写前预检与原子写：真实临时目录副作用。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from module.Renpy.json_handler import JsonImporter, plan_tl_write_targets


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "Game"
    (root / "game" / "tl" / "chinese").mkdir(parents=True)
    return root


def test_plan_rejects_normcase_duplicates(tmp_path):
    root = _project(tmp_path)
    tl = root / "game" / "tl" / "chinese"
    with pytest.raises(ValueError, match="重复"):
        plan_tl_write_targets(
            {
                "a.rpy": [{"original": "A", "translation": "甲"}],
                "./a.rpy": [{"original": "B", "translation": "乙"}],
            },
            tl,
            backup=True,
        )


def test_plan_rejects_backup_symlink_escape(tmp_path):
    if os.name != "nt" and not hasattr(os, "symlink"):
        pytest.skip("无 symlink")
    root = _project(tmp_path)
    tl = root / "game" / "tl" / "chinese"
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    target = tl / "safe.rpy"
    target.write_text('translate chinese strings:\n    old "A"\n    new ""\n', encoding="utf-8")
    bak = tl / "safe.rpy.bak"
    try:
        bak.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("无法创建 symlink")
    with pytest.raises(ValueError, match="越出|链接|备份"):
        plan_tl_write_targets(
            {"safe.rpy": [{"original": "A", "translation": "甲"}]},
            tl,
            backup=True,
        )
    assert outside.read_text(encoding="utf-8") == "secret"


def test_apply_no_mkdir_before_validation_failure(tmp_path):
    root = tmp_path / "Bare"
    (root / "game").mkdir(parents=True)
    # 无 tl；traversal 应在 mkdir 前失败
    importer = JsonImporter()
    meta: dict = {}
    with pytest.raises(ValueError):
        importer.apply_translations(
            {"../escape.rpy": [{"original": "A", "translation": "甲"}]},
            str(root),
            target_language="chinese",
            backup=True,
            result_meta=meta,
        )
    assert not (root / "game" / "tl").exists()
    assert meta.get("written_files") == []


def test_apply_atomic_write_and_empty_translation_falls_back(tmp_path):
    root = _project(tmp_path)
    tl = root / "game" / "tl" / "chinese"
    existing = tl / "script.rpy"
    existing.write_text('translate chinese strings:\n    old "Hi"\n    new "旧"\n', encoding="utf-8")
    importer = JsonImporter()
    meta: dict = {}
    ok = importer.apply_translations(
        {
            "script.rpy": [
                {"original": "Hi", "translation": "", "type": "strings", "line": 1},
                {"original": "Hi", "translation": "重复应跳过", "type": "strings", "line": 2},
            ]
        },
        str(root),
        target_language="chinese",
        backup=True,
        result_meta=meta,
    )
    assert ok is True
    text = existing.read_text(encoding="utf-8")
    assert 'old "Hi"' in text
    # 空译回退 original
    assert 'new "Hi"' in text
    assert "重复应跳过" not in text
    assert meta["written_files"]
    assert meta["backup_paths"]
    assert (tl / "script.rpy.bak").is_file()


def test_apply_stop_midway_marks_partial(tmp_path):
    root = _project(tmp_path)
    importer = JsonImporter()
    meta: dict = {}
    stop_after = {"n": 0}

    def should_stop():
        stop_after["n"] += 1
        return stop_after["n"] > 1

    ok = importer.apply_translations(
        {
            "a.rpy": [{"original": "A", "translation": "甲"}],
            "b.rpy": [{"original": "B", "translation": "乙"}],
        },
        str(root),
        target_language="chinese",
        backup=False,
        should_stop=should_stop,
        result_meta=meta,
    )
    assert ok is False
    assert meta.get("partial") is True
    assert len(meta.get("written_files") or []) == 1
    assert (root / "game" / "tl" / "chinese" / "a.rpy").is_file()
    assert not (root / "game" / "tl" / "chinese" / "b.rpy").exists()


def test_apply_rejects_tl_root_symlink_before_mkdir(tmp_path):
    """game/tl 指向外部时，预检失败且不得在外部创建语言目录。"""
    if os.name != "nt" and not hasattr(os, "symlink"):
        pytest.skip("无 symlink")
    root = tmp_path / "Game"
    (root / "game").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    tl_link = root / "game" / "tl"
    try:
        tl_link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("无法创建目录 symlink")
    importer = JsonImporter()
    meta: dict = {}
    with pytest.raises(ValueError, match="越界|TL"):
        importer.apply_translations(
            {"a.rpy": [{"original": "A", "translation": "甲"}]},
            str(root),
            target_language="chinese",
            backup=False,
            result_meta=meta,
        )
    assert meta.get("written_files") == []
    assert not (outside / "chinese").exists()
