# -*- coding: utf-8 -*-
"""Ren'Py 源码翻译器回归测试。"""

from pathlib import Path

from module.Translate.RenpySourceTranslator import RenpySourceTranslator


def test_scan_file_extracts_short_spoken_dialogue(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.rpy"
    file_path.write_text(
        'label start:\n'
        '    a"Ah...No..."\n',
        encoding="utf-8",
    )

    entries = RenpySourceTranslator().scan_file(file_path)

    assert any(entry.text == "Ah...No..." for entry in entries)


def test_scan_file_extracts_log_addquest_text(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.rpy"
    file_path.write_text(
        'label start:\n'
        '    $ log.addquest("I should dress up and go to the kitchen.")\n',
        encoding="utf-8",
    )

    entries = RenpySourceTranslator().scan_file(file_path)

    assert any(
        entry.text == "I should dress up and go to the kitchen."
        for entry in entries
    )
