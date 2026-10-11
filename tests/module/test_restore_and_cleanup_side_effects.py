"""恢复 CSV 安全预检 / 取消，以及清理副作用与合并快照（真实临时目录）。"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from module.Extract.UnifiedExtractor import UnifiedExtractor
from module.Renpy.renpy_extract import ExtractionCancelled, remove_repeat_extracted_from_tl


def _tl_project(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "Game"
    tl = root / "game" / "tl" / "chinese"
    tl.mkdir(parents=True)
    return root, tl


def _write_manifest(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as writer:
        out = csv.writer(writer)
        out.writerow(["file", "old", "new", "restore"])
        out.writerows(rows)


def test_restore_rejects_symlink_escape_without_side_effects(tmp_path):
    if os.name != "nt" and not hasattr(os, "symlink"):
        pytest.skip("无 symlink")
    root, tl = _tl_project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tl / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("无法创建目录 symlink")
    manifest = tl / "_filtered_suspicious" / "t1" / "restore_manifest.csv"
    _write_manifest(manifest, [("link/escaped.rpy", "Hello", "你好", "1")])
    before = set(outside.rglob("*"))
    result = UnifiedExtractor().restore_flagged_suspicious_entries(
        root, "chinese", manifest_path=manifest
    )
    assert result.success is False
    assert "非法" in (result.message or "") or "越" in (result.message or "")
    assert result.written_files == []
    assert set(outside.rglob("*")) == before
    assert not (outside / "escaped.rpy").exists()


def test_restore_mixed_invalid_fails_before_any_write(tmp_path):
    root, tl = _tl_project(tmp_path)
    safe = tl / "safe.rpy"
    safe.write_text('translate chinese strings:\n    old "A"\n    new "甲"\n', encoding="utf-8")
    original = safe.read_text(encoding="utf-8")
    manifest = tl / "_filtered_suspicious" / "t1" / "restore_manifest.csv"
    _write_manifest(
        manifest,
        [
            ("safe.rpy", "Hello", "你好", "1"),
            ("../escape.rpy", "Bad", "坏", "1"),
        ],
    )
    result = UnifiedExtractor().restore_flagged_suspicious_entries(
        root, "chinese", manifest_path=manifest
    )
    assert result.success is False
    assert result.written_files == []
    assert safe.read_text(encoding="utf-8") == original
    assert not (root / "game" / "tl" / "escape.rpy").exists()
    assert "你好" not in safe.read_text(encoding="utf-8")


def test_restore_cancel_after_first_file_keeps_partial(tmp_path):
    root, tl = _tl_project(tmp_path)
    manifest = tl / "_filtered_suspicious" / "t1" / "restore_manifest.csv"
    _write_manifest(
        manifest,
        [
            ("a.rpy", "A", "甲", "1"),
            ("b.rpy", "B", "乙", "1"),
        ],
    )
    extractor = UnifiedExtractor()
    seen = {"n": 0}

    def cancel_after_first() -> bool:
        seen["n"] += 1
        return seen["n"] > 1

    extractor.set_cancel_callback(cancel_after_first)
    result = extractor.restore_flagged_suspicious_entries(
        root, "chinese", manifest_path=manifest
    )
    assert result.cancelled is True
    assert result.success is False
    assert len(result.written_files) == 1
    assert (tl / "a.rpy").is_file()
    assert "甲" in (tl / "a.rpy").read_text(encoding="utf-8")
    assert not (tl / "b.rpy").exists()


def test_restore_valid_csv_keeps_translation(tmp_path):
    root, tl = _tl_project(tmp_path)
    target = tl / "common.rpy"
    target.write_text('translate chinese strings:\n    old "Hi"\n    new "旧"\n', encoding="utf-8")
    manifest = tl / "_filtered_suspicious" / "t1" / "restore_manifest.csv"
    _write_manifest(manifest, [("common.rpy", "Hello", "你好", "1")])
    result = UnifiedExtractor().restore_flagged_suspicious_entries(
        root, "chinese", manifest_path=manifest
    )
    assert result.success is True
    text = target.read_text(encoding="utf-8")
    assert 'old "Hi"' in text
    assert 'new "旧"' in text
    assert 'old "Hello"' in text
    assert 'new "你好"' in text


def test_restore_read_failure_leaves_existing_bytes_unchanged(tmp_path, monkeypatch):
    """现有目标 read_text 失败：不得 atomic 空替换，原文件字节不变。"""
    root, tl = _tl_project(tmp_path)
    safe = tl / "safe.rpy"
    original = b'translate chinese strings:\n    old "KEEP"\n    new "ORIGINAL"\n'
    safe.write_bytes(original)
    manifest = tl / "_filtered_suspicious" / "t1" / "restore_manifest.csv"
    _write_manifest(manifest, [("safe.rpy", "Hello", "你好", "1")])
    real_read_text = Path.read_text

    def gated_read_text(self, *args, **kwargs):
        if self.resolve() == safe.resolve():
            raise OSError("stub read failure")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", gated_read_text)
    result = UnifiedExtractor().restore_flagged_suspicious_entries(
        root, "chinese", manifest_path=manifest
    )
    assert result.success is False
    assert result.cancelled is False
    assert result.written_files == []
    assert "恢复失败" in (result.message or "")
    assert safe.read_bytes() == original


def test_restore_second_atomic_oserror_keeps_first_written(tmp_path, monkeypatch):
    """第1文件已写、第2次 atomic 受控 OSError：保留 written_files，不写第2文件。"""
    from module.Extract import UnifiedExtractor as ue_mod

    root, tl = _tl_project(tmp_path)
    manifest = tl / "_filtered_suspicious" / "t1" / "restore_manifest.csv"
    _write_manifest(
        manifest,
        [
            ("a.rpy", "A", "甲", "1"),
            ("b.rpy", "B", "乙", "1"),
        ],
    )
    real_atomic = ue_mod.atomic_write_text
    calls = {"n": 0}

    def gated_atomic(path, text, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError("stub atomic failure")
        return real_atomic(path, text, **kwargs)

    monkeypatch.setattr(ue_mod, "atomic_write_text", gated_atomic)
    result = UnifiedExtractor().restore_flagged_suspicious_entries(
        root, "chinese", manifest_path=manifest
    )
    assert result.success is False
    assert result.cancelled is False
    assert len(result.written_files) == 1
    assert Path(result.written_files[0]).name == "a.rpy"
    assert (tl / "a.rpy").is_file()
    assert "甲" in (tl / "a.rpy").read_text(encoding="utf-8")
    assert not (tl / "b.rpy").exists()


def test_remove_repeat_cancel_keeps_written_meta(tmp_path, monkeypatch):
    tl = tmp_path / "tl"
    tl.mkdir()
    a = tl / "a.rpy"
    b = tl / "b.rpy"
    a.write_text(
        'translate chinese strings:\n    old "X"\n    new "1"\n    old "X"\n    new "2"\n',
        encoding="utf-8",
    )
    b.write_text(
        'translate chinese strings:\n    old "Y"\n    new "1"\n    old "Y"\n    new "2"\n',
        encoding="utf-8",
    )
    from module.Renpy import renpy_extract as rx

    real = rx.remove_repeat_for_file
    state = {"stop": False}

    def gated(path, duplicate_action="comment"):
        ok = real(path, duplicate_action=duplicate_action)
        if Path(path).name == "a.rpy" and ok:
            state["stop"] = True
        return ok

    monkeypatch.setattr(rx, "remove_repeat_for_file", gated)
    meta: dict = {}
    with pytest.raises(ExtractionCancelled):
        remove_repeat_extracted_from_tl(
            str(tl),
            is_py2=False,
            should_stop=lambda: state["stop"],
            result_meta=meta,
        )
    assert meta.get("written") is True
    assert meta.get("partial") is True
    assert any(Path(p).name == "a.rpy" for p in meta.get("written_files") or [])


def test_merge_clean_duplicates_uses_config_snapshot(tmp_path, monkeypatch):
    """clean_duplicates 全程用快照，不再 Config.load；动作与磁盘相反。"""
    import types

    root = tmp_path / "project"
    tl = root / "game" / "tl" / "chinese"
    staging = root / "game" / "tl" / "chinese_new"
    target = tl / "src" / "plot" / "chapter.rpy"
    staged = staging / "src" / "plot" / "extra.rpy"
    target.parent.mkdir(parents=True)
    staged.parent.mkdir(parents=True)
    target.write_text(
        'translate chinese strings:\n\n'
        '    old "Hi"\n'
        '    new "你好"\n',
        encoding="utf-8",
    )
    staged.write_text(
        'translate chinese strings:\n\n'
        '    old "New"\n'
        '    new "新"\n',
        encoding="utf-8",
    )
    load_calls = {"n": 0}

    class CountingConfig:
        def load(self):
            load_calls["n"] += 1
            return SimpleNamespace(
                renpy_duplicate_string_action="delete",
                renpy_remove_string_duplicates=False,
            )

    monkeypatch.setattr("module.Extract.UnifiedExtractor.Config", CountingConfig)
    seen = {}

    def capture_remove(tl_dir, is_py2, **kwargs):
        seen["duplicate_action"] = kwargs.get("duplicate_action")
        return None

    monkeypatch.setattr(
        "module.Extract.UnifiedExtractor.rx.remove_repeat_extracted_from_tl",
        capture_remove,
    )
    snapshot = SimpleNamespace(
        renpy_duplicate_string_action="comment",
        renpy_remove_string_duplicates=False,
        renpy_project_path=str(root),
        renpy_game_folder=str(root / "game"),
        renpy_tl_folder=str(tl),
    )
    extractor = UnifiedExtractor.__new__(UnifiedExtractor)
    extractor.logger = types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )
    extractor._progress_callback = None
    extractor._cancel_callback = None
    result = extractor.merge_incremental_folder(
        root,
        "chinese",
        staging,
        clean_duplicates=True,
        config_snapshot=snapshot,
    )
    assert result.success is True
    assert load_calls["n"] == 0
    assert seen.get("duplicate_action") == "comment"
    merged = tl / "src" / "plot" / "extra.rpy"
    assert merged.is_file()
    assert 'old "New"' in merged.read_text(encoding="utf-8")
