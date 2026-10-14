"""Formatter 共享：原子写、注释保留、字符串内 Tab。"""
from pathlib import Path

from module.Tool.Formatter import Formatter


def test_preserves_comments_even_when_flag_false(tmp_path: Path):
    path = tmp_path / "c.rpy"
    path.write_text("# keep me\n\tpass  \n", encoding="utf-8")
    assert Formatter().format_file(str(path), preserve_comments=False, fix_indent=True, remove_trailing=True)
    text = path.read_text(encoding="utf-8")
    assert "# keep me" in text
    assert text.startswith("# keep me\n    pass\n") or "    pass" in text


def test_failed_file_tracked(tmp_path: Path, monkeypatch):
    folder = tmp_path
    (folder / "a.rpy").write_text("pass\n", encoding="utf-8")
    formatter = Formatter()

    def fail(self, file_path, *args, **kwargs):
        return False

    monkeypatch.setattr(Formatter, "format_file", fail)
    assert formatter.format_folder(str(folder)) == 0
    assert formatter.last_failed_files
