# -*- coding: utf-8 -*-
"""Ren'Py TL 抽取/写回的关键回归测试。"""

from module.Renpy.renpy_tl_core import parse_tl_document
from module.Renpy.renpy_tl_io import RenpyTlItemExtractor
from module.Renpy.renpy_tl_io import RenpyTlLineUpdater


def _extract_single_item(text: str):
    doc = parse_tl_document(text.strip().splitlines())
    items = RenpyTlItemExtractor().extract(doc, "sample.rpy")
    assert len(items) == 1
    return items[0]


def test_extract_ignores_trailing_cb_name_argument() -> None:
    text = """
# game/charpters/relationships.rpy:66
translate chinese relationships_f8b6714e:

    # "This is karen, wife of Marco." (cb_name="kr")
    "This is karen, wife of Marco." (cb_name="卡雷")
"""
    item = _extract_single_item(text)
    extra = item.get_extra_field()
    renpy = extra["renpy"]

    assert item.get_name_src() is None
    assert item.get_src() == "This is karen, wife of Marco."
    assert item.get_dst() == "This is karen, wife of Marco."
    assert renpy["slots"] == [{"role": "DIALOGUE", "lit_index": 0}]


def test_writeback_preserves_trailing_cb_name_argument() -> None:
    text = """
# game/charpters/relationships.rpy:24
translate chinese relationships_0aae1c29:

    # "This is Marco, the main investor and partner in the company your father founded, and husband of Karen." (cb_name="mr")
    "" (cb_name="mr")
"""
    lines = text.strip().splitlines()
    item = _extract_single_item(text)
    item.set_dst("这是 Marco，你父亲创办的公司里的主要投资人兼合伙人，也是 Karen 的丈夫。")

    assert RenpyTlLineUpdater().apply_item(lines, item) is True
    assert lines[-1] == '    "这是 Marco，你父亲创办的公司里的主要投资人兼合伙人，也是 Karen 的丈夫。" (cb_name="mr")'


def test_writeback_preserves_trailing_function_argument_string() -> None:
    text = """
# game/chapter_5.rpy:220
translate schinese chapter_5_79f2f130:

    # "Man" "Pleasure to meet you." with PushMove("x")
    "Man" "" with PushMove("x")
"""
    lines = text.strip().splitlines()
    item = _extract_single_item(text)
    item.set_dst("很高兴见到你。")

    assert RenpyTlLineUpdater().apply_item(lines, item) is True
    assert lines[-1] == '    "Man" "很高兴见到你。" with PushMove("x")'
