"""写回判定共享模块（``module/File/WritebackVerdict.py``）的单元测试。

这些纯函数同时被 RENPY（tl 文件写回）与 RENPYSOURCE（源码写回）引用，
所以用例分两层：

1. 直接锁定每个函数对边界输入（空串、None、list、纯标记、超长文本）的语义；
2. 用参数化回归 RENPY 的私有委托方法，保证它和共享实现逐条同源——一旦
   有人把判定逻辑改回各自实现，这里会立刻红灯。
"""

import pytest

from module.File import WritebackVerdict
from module.File.RENPY import RENPY


# --------------------------------------------------------------------------
# has_translated_value：条目里是否确实有一份与原文不同的译文
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "target", "expected"),
    [
        ("原文", "", False),
        ("原文", None, False),
        ("原文", "原文", False),
        ("原文", "译文", True),
        ("原文", [], False),
        ("原文", ["译文"], True),
        # 类型不同即视为不同值：list 与 str 永不相等，所以 (["a"], "a") 算有译文。
        # 这是 RENPY 原实现（str 分支只和源码比相等）的逐字保留，不是缺陷。
        ("a", ["a"], True),
        # 同类型且内容一致（list vs list）则视为没有译文。
        (["a"], ["a"], False),
        # 非 str / list 的类型一律视为没有译文。
        ("原文", 123, False),
        ("原文", b"\xe8\xaf\x91", False),
    ],
)
def test_has_translated_value(source, target, expected):
    assert WritebackVerdict.has_translated_value(source, target) is expected


# --------------------------------------------------------------------------
# normalize_compare_value：写回前后比较用的归一化
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("  甲  ", "甲"),
        ("", ""),
        (["a", None, "b"], "a|b"),
        (["甲", "乙"], "甲|乙"),
        # None 被丢弃，其余元素保持原始顺序。
        (["甲", None, "乙", "丙"], "甲|乙|丙"),
        (["第一信号", 2, "第三信号"], "第一信号|2|第三信号"),
        # str 分支是 str(value or "")：0 这类假值会归一化成空串。
        (0, ""),
    ],
)
def test_normalize_compare_value(value, expected):
    assert WritebackVerdict.normalize_compare_value(value) == expected


# --------------------------------------------------------------------------
# is_untranslatable_markup：去掉标签/颜色码后是否还有可译字符
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("{color=#a54a54a}{/color}", True),
        ("{i}…{/i}", True),
        ("{b}Hello{/b}", False),
        ("#a54a54a", True),
        ("123 :!?", True),
        ("", True),
        (None, True),
        ("第一信号。", False),
        (123, True),
    ],
)
def test_is_untranslatable_markup(text, expected):
    assert WritebackVerdict.is_untranslatable_markup(text) is expected


# --------------------------------------------------------------------------
# truncate_sample：报告/错误信息里的单行短样例
# --------------------------------------------------------------------------


def test_truncate_sample_converts_real_newlines_to_literal_escape():
    result = WritebackVerdict.truncate_sample("甲\n乙\r\n丙\r丁", limit=80)

    # 结果必须真的只有一行：真实换行都被替换成字面反斜杠 n。
    assert "\n" not in result
    assert "\r" not in result
    assert result == "甲\\n乙\\n丙\\n丁"
    assert len(result) <= 80


def test_truncate_sample_keeps_short_text_unchanged():
    assert WritebackVerdict.truncate_sample("单行信号", limit=80) == "单行信号"
    # 长度恰好等于 limit 时属于 "<= limit"，同样原样返回。
    exactly = "x" * 20
    assert WritebackVerdict.truncate_sample(exactly, limit=20) == exactly


def test_truncate_sample_trims_long_text_to_exact_limit():
    result = WritebackVerdict.truncate_sample("a" * 100, limit=20)

    assert result == "a" * 19 + "…"
    assert result.endswith("…")
    assert len(result) == 20


def test_truncate_sample_uses_default_limit_of_80():
    assert len(WritebackVerdict.truncate_sample("b" * 200)) == 80


# --------------------------------------------------------------------------
# 委托一致性回归：RENPY 的私有方法必须与共享实现结果完全一致
# --------------------------------------------------------------------------

# 覆盖 list、None、空串、中文、纯空白、同值等边界组合。
DELEGATION_VALUE_SAMPLES = [
    ("原文", "译文"),
    ("原文", ""),
    ("原文", None),
    ("原文", "原文"),
    ("原文", []),
    ("原文", ["译文"]),
    ("a", ["a"]),
    (["a"], ["a"]),
    ("第一信号。", "第一信号。"),
    ("  空白  ", "甲"),
    ("原文", 123),
]


@pytest.mark.parametrize(("source", "target"), DELEGATION_VALUE_SAMPLES)
def test_renpy_delegates_has_translated_value(source, target):
    assert RENPY._has_translated_value(source, target) is WritebackVerdict.has_translated_value(
        source, target
    )


NORMALIZE_VALUE_SAMPLES = [
    None,
    "",
    "  甲  ",
    "甲",
    [],
    ["a", None, "b"],
    ["甲", "乙"],
    ["第一信号", 2, "第三信号"],
    "  ",
    0,
]


@pytest.mark.parametrize("value", NORMALIZE_VALUE_SAMPLES)
def test_renpy_delegates_normalize_compare_value(value):
    assert RENPY._normalize_compare_value(value) == WritebackVerdict.normalize_compare_value(value)
