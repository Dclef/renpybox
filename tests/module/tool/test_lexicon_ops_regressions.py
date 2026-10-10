"""词表数据丢失回归；只使用临时文件与网络替身。"""
from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from module.Tool import LexiconOps


@pytest.mark.parametrize("kind", ["glossary", "preserve"])
def test_formula_cells_are_preserved_as_text_or_explicitly_rejected(kind):
    book = Workbook()
    sheet = book.active
    sheet.append(["原文", "译文", "备注"] if kind == "glossary" else ["原文", "备注"])
    sheet.append(["=Alice", "爱丽丝", "=note"] if kind == "glossary" else ["=Alice", "=note"])
    buffer = io.BytesIO()
    book.save(buffer)
    reader = LexiconOps.import_glossary_excel_bytes if kind == "glossary" else LexiconOps.import_preserve_excel_bytes
    try:
        rows = reader(buffer.getvalue())
    except LexiconOps.LexiconOpsError as exc:
        assert "公式" in str(exc)
        return
    assert len(rows) == 1, "公式原文不能静默丢行"
    assert rows[0]["src"] == "=Alice"
    assert rows[0]["comment"] == "=note"
    if kind == "glossary":
        assert rows[0]["dst"] == "爱丽丝"


def test_variable_scan_read_failure_cannot_be_empty_success(tmp_path, monkeypatch):
    game = tmp_path / "game"
    game.mkdir()
    script = game / "script.rpy"
    script.write_text('"Hi [player]"', encoding="utf-8")
    config = SimpleNamespace(input_folder=str(game), output_folder="", renpy_game_folder=str(game))
    real_read = Path.read_text

    def unreadable(path, *args, **kwargs):
        if path == script:
            raise OSError("模拟源码读取失败")
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable)
    with pytest.raises((LexiconOps.LexiconOpsError, OSError)):
        LexiconOps.scan_preserve_variables(config)

def test_candidate_scan_keeps_literal_and_regex_rules_separate():
    rows = [
        {"src": "a.b", "dst": "字面译文", "regex": False, "record_id": "literal"},
        {"src": "a.b", "dst": "正则译文", "regex": True, "record_id": "pattern"},
    ]
    merged, added, updated, counts = LexiconOps.merge_candidate_entries(
        rows,
        [{"source": "a.b", "regex": True, "count": 3}, {"source": "Other", "count": 1}],
    )
    assert [(row["record_id"], row["dst"], row["regex"]) for row in merged[:2]] == [
        ("literal", "字面译文", False), ("pattern", "正则译文", True),
    ]
    assert added == 1
    assert counts["a.b"] == 3
