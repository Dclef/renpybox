"""字体引用只扫描源码，忽略编译脚本，并在扫描内部响应取消。"""
from __future__ import annotations

from pathlib import Path

import pytest

from module.Tool.FontReplacer import FontReplacer


def _reject_compiled_read(path):
    raise AssertionError(f"字体扫描不应读取编译脚本: {path}")


def test_scan_reads_sources_and_ignores_compiled_scripts(tmp_path, monkeypatch):
    game = tmp_path / "game"
    game.mkdir()
    (game / "gui.rpy").write_text('define gui.text_font = "source.ttf"\n', encoding="utf-8")
    (game / "mod.rpym").write_text('define gui.name_text_font = "module.otf"\n', encoding="utf-8")
    (game / "gui.rpyc").write_bytes(b"\x00stale.ttf\x00")
    (game / "mod.rpymc").write_bytes(b"\x00stale-module.otf\x00")
    (game / "only.rpyc").write_bytes(b"\x00orphan.ttf\x00")
    (game / "only.rpymc").write_bytes(b"\x00orphan.otf\x00")
    backup = game / "fonts_backup" / "old"
    backup.mkdir(parents=True)
    (backup / "old.rpy").write_text('font = "backup.ttf"', encoding="utf-8")
    (backup / "old.rpyc").write_bytes(b"\x00backup.ttf\x00")
    (backup / "unused.ttf").write_bytes(b"backup")
    (game / "current.TTF").write_bytes(b"font")
    monkeypatch.setattr(Path, "read_bytes", _reject_compiled_read)
    replacer = FontReplacer()
    assert replacer.scan_fonts(str(game)) == ["module.otf", "source.ttf"]
    assert [rel for rel, _ in replacer.discover_font_files(str(game))] == ["current.TTF"]


@pytest.mark.parametrize("extension", [".rpyc", ".rpymc"])
def test_compiled_only_project_has_no_source_font_references(tmp_path, monkeypatch, extension):
    game = tmp_path / "game"
    game.mkdir()
    (game / f"only{extension}").write_bytes(b"\x00compiled.ttf\x00")
    monkeypatch.setattr(Path, "read_bytes", _reject_compiled_read)
    assert FontReplacer().scan_fonts(str(game)) == []


@pytest.mark.parametrize("extension", [".rpy", ".rpym"])
def test_unreadable_source_does_not_fall_back_to_compiled_script(tmp_path, monkeypatch, extension):
    game = tmp_path / "game"
    game.mkdir()
    source = game / f"gui{extension}"
    source.write_text("# unreadable", encoding="utf-8")
    source.with_suffix(extension + "c").write_bytes(b"\x00fallback.ttf\x00")
    real_read = Path.read_text

    def read(path, *args, **kwargs):
        if path == source:
            raise OSError("synthetic read failure")
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(Path, "read_bytes", _reject_compiled_read)
    assert FontReplacer().scan_fonts(str(game)) == []


@pytest.mark.parametrize("method", ["scan_fonts", "discover_font_files"])
def test_scan_cancellation_propagates_during_directory_walk(tmp_path, method):
    game = tmp_path / "game"
    game.mkdir()
    (game / "irrelevant.png").write_bytes(b"asset")
    calls = 0

    def check_cancel():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("scan cancelled during traversal")

    with pytest.raises(RuntimeError, match="scan cancelled during traversal"):
        getattr(FontReplacer(), method)(str(game), check_cancel=check_cancel)


def test_cancellation_is_not_swallowed_during_script_scan(tmp_path, monkeypatch):
    game = tmp_path / "game"
    game.mkdir()
    (game / "gui.rpy").write_text('font = "main.ttf"', encoding="utf-8")
    cancelled = False
    real_read = Path.read_text

    def read(path, *args, **kwargs):
        nonlocal cancelled
        content = real_read(path, *args, **kwargs)
        cancelled = True
        return content

    def check_cancel():
        if cancelled:
            raise RuntimeError("scan cancelled during read")

    monkeypatch.setattr(Path, "read_text", read)
    with pytest.raises(RuntimeError, match="scan cancelled during read"):
        FontReplacer().scan_fonts(str(game), check_cancel=check_cancel)
