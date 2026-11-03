"""写回判定共享工具：纯函数、无状态、无副作用。

RENPY（tl 文件）与 RENPYSOURCE（源码）两条写回链路都需要回答同类问题：
"这条条目到底有没有值得写回的译文"、"两边写回结果是否等价"。此前这些判定
在两处各自实现了一份，语义漂移风险高，所以集中到这里，供两边共同引用。

本模块只做判定：不读写文件、不改条目状态、不打日志。
"""

from __future__ import annotations

import re

# Ren'Py 行内标签（{color=#fff}、{b}、{/b} …）与 #rrggbb[aa] / #rgb 颜色码。
RE_RENPY_TEXT_TAG = re.compile(r"\{[^{}]*\}")
RE_RENPY_COLOR_CODE = re.compile(r"#[0-9a-fA-F]{3,8}")


def has_translated_value(source, target) -> bool:
    """条目里是否确实存有一份与原文不同的译文。

    与 RENPY.py 原实现逐字一致：str 要求非空且不等于原文，list 要求非空且
    不等于原文，其他类型一律视为"没有译文"。
    """
    if isinstance(target, str):
        return target != "" and target != source
    if isinstance(target, list):
        return bool(target) and target != source
    return False


def normalize_compare_value(value) -> str:
    """归一化后比较写回结果，避免列表/空白差异造成误报。"""
    if isinstance(value, list):
        return "|".join(str(v) for v in value if v is not None)
    return str(value or "").strip()


def is_untranslatable_markup(text) -> bool:
    """判断文本去掉 Ren'Py 标签、颜色码、标点与空白后是否还有可译字符。"""
    if not isinstance(text, str):
        return True
    stripped = RE_RENPY_COLOR_CODE.sub("", RE_RENPY_TEXT_TAG.sub("", text))
    # isalpha() 同时覆盖拉丁字母与汉字；剩下的标点/数字/空白都不算可译内容。
    return not any(char.isalpha() for char in stripped)


def truncate_sample(text, limit: int = 80) -> str:
    """把样例文本压成单行短串，避免报告与错误信息过长。"""
    value = text if isinstance(text, str) else str(text)
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    return value if len(value) <= limit else value[: limit - 1] + "…"
