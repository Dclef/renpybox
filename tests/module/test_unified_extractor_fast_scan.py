from pathlib import Path

from module.Extract.UnifiedExtractor import UnifiedExtractor


def test_fast_scan_strings_file_reads_large_strings_blocks_linearly(tmp_path: Path) -> None:
    path = tmp_path / "events.rpy"
    path.write_text(
        'translate chinese strings:\n\n'
        '    old "Keep"\n'
        '    new "保留"\n\n'
        '    # renpybox: replace-only\n'
        '    old "Say \\\"hello\\\""\n'
        '    new "Say \\\"hello\\\""\n',
        encoding="utf-8",
    )

    result = UnifiedExtractor()._fast_scan_strings_file(path)

    assert result is not None
    originals, translations = result
    assert originals == {'Keep', 'Say "hello"'}
    assert translations == {'Keep': '保留'}


def test_fast_scan_strings_file_defers_label_blocks_to_ast(tmp_path: Path) -> None:
    path = tmp_path / "dialogue.rpy"
    path.write_text(
        'translate chinese scene_start:\n'
        '    old "Hello"\n'
        '    new "你好"\n',
        encoding="utf-8",
    )

    assert UnifiedExtractor()._fast_scan_strings_file(path) is None


def test_fast_scan_strings_file_defers_multiline_literals_to_ast(tmp_path: Path) -> None:
    path = tmp_path / "multiline.rpy"
    path.write_text(
        'translate chinese strings:\n'
        '    old """long\n'
        '    text"""\n'
        '    new """长\n'
        '    文本"""\n',
        encoding="utf-8",
    )

    assert UnifiedExtractor()._fast_scan_strings_file(path) is None
