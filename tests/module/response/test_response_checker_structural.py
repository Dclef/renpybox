# -*- coding: utf-8 -*-
"""ResponseChecker 结构文本判定回归测试。

修复前：带句号的短英文（“Dance.”）被当成标识符、含 and/or/not 的句子被
当成逻辑表达式，导致 src==dst 也被判为“已翻译”，写回大量占位译文。
"""

from base.Base import Base
from module.Cache.CacheItem import CacheItem
from module.Config import Config
from module.Response.ResponseChecker import ResponseChecker


def _item(src: str) -> CacheItem:
    return CacheItem(
        file_path="scene.rpy",
        row=1,
        src=src,
        dst=src,
        tag="string",
        status=Base.TranslationStatus.UNTRANSLATED,
        file_type=CacheItem.FileType.RENPY,
        text_type=CacheItem.TextType.RENPY,
    )


def test_short_word_with_period_is_not_structural():
    for text in ("Dance.", "Annoyed.", "Office.", "First."):
        assert ResponseChecker.is_structural_text(text) is False, text


def test_natural_language_and_or_not_is_not_logic():
    for text in (
        "not ugly",
        "not you",
        "and then she left",
        "Do you want tea or coffee?",
        "{pen=blue}the best dick {i}ever{/i}{/pen} and she's obviously all {pen=indigo}pen{/pen} up.{/pen}",
    ):
        assert ResponseChecker.is_structural_text(text) is False, text


def test_real_identifiers_stay_structural():
    for text in (
        "DesertStalkerEA-100001",
        "pc_camslut_tab",
        "v1.2.3",
        "USB3.0",
    ):
        assert ResponseChecker.is_structural_text(text) is True, text


def test_username_like_string_is_not_structural():
    assert ResponseChecker.is_structural_text("xX~HOTKITTY69~Xx") is False


def test_src_equal_dst_natural_language_is_rejected():
    config = Config()
    for text in ("Dance.", "not ugly"):
        item = _item(text)
        checker = ResponseChecker(config, [item])
        errors = checker.check([text], [text], CacheItem.TextType.RENPY, [item])
        assert errors == [ResponseChecker.Error.LINE_ERROR_SIMILARITY], text
